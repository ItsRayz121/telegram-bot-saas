"""Discord UI for campaign proof flows: a persistent "Submit proof" button per
campaign/task, a proof modal, and — for X raids / X social-tasks with action
targets — an ephemeral per-action panel with a live checklist and a Verify button.
Buttons survive bot restarts via DynamicItem (custom_id carries the campaign +
task ids); register once with bot.add_dynamic_items(ProofButton).
"""
from __future__ import annotations

import asyncio
import logging
import re

import discord

import campaign_runtime as cr
import social_handles

log = logging.getLogger("guildizer.campaigns")

ACCENT = 0x5865F2

# Per-action presentation, shared by the panel and the announcement embed.
ACTION_LABELS = {
    "like": "❤️ Like", "retweet": "🔁 Repost", "comment": "💬 Comment",
    "quote": "❝ Quote", "follow": "➕ Follow",
}
GOAL_LABELS = {
    "likes": "❤️ Likes", "retweets": "🔁 Reposts", "comments": "💬 Comments",
    "quotes": "❝ Quotes", "follows": "➕ Follows",
}
# How long we wait for a member to upload their screenshot after submitting.
SCREENSHOT_WAIT_SECONDS = 120


def _result_text(status: str, reward: int) -> str:
    if status == "verified":
        return f"✅ Verified! +{reward} XP" if reward else "✅ Verified — thanks!"
    if status == "pending":
        return "📝 Submitted — an admin will review it shortly. Thanks!"
    if status == "duplicate":
        return "🙌 You've already submitted for this one."
    if status == "full":
        return "🚫 This campaign has reached its participant limit."
    return "This campaign is closed."


def _needs_screenshot(ctx: dict) -> bool:
    """A Discord modal can't accept a file, so a screenshot is collected in a
    follow-up message instead. True when the campaign asks for one."""
    if ctx.get("verification_mode") == "screenshot":
        return True
    return any(f.get("field_type") == "screenshot" for f in (ctx.get("fields") or []))


async def _collect_screenshot(interaction: discord.Interaction, cid: int) -> None:
    """Ask for an image in the channel and attach it to the member's submission.
    Best-effort: a timeout just leaves the submission without an image."""
    await interaction.followup.send(
        f"📸 Now upload your screenshot as an image in this channel "
        f"(within {SCREENSHOT_WAIT_SECONDS // 60} minutes) and I'll attach it to your submission.",
        ephemeral=True,
    )

    def check(m: discord.Message) -> bool:
        return (
            m.author.id == interaction.user.id
            and m.channel.id == interaction.channel_id
            and any((a.content_type or "").startswith("image/") for a in m.attachments)
        )

    try:
        msg = await interaction.client.wait_for("message", check=check, timeout=SCREENSHOT_WAIT_SECONDS)
    except asyncio.TimeoutError:
        await interaction.followup.send(
            "⏳ No screenshot received — an admin may ask you for it during review.",
            ephemeral=True,
        )
        return
    image = next(a for a in msg.attachments if (a.content_type or "").startswith("image/"))
    ok = await asyncio.to_thread(cr.attach_screenshot, cid, interaction.user.id, image.url)
    await interaction.followup.send(
        "✅ Screenshot attached to your submission." if ok
        else "⚠️ Couldn't attach that screenshot — an admin will follow up.",
        ephemeral=True,
    )


class ProofModal(discord.ui.Modal):
    def __init__(self, cid: int, tid: int, title: str, fields: list[dict] | None = None,
                 prompt_label: str = "Your proof (link or text)",
                 prompt_short: bool = False, needs_screenshot: bool = False) -> None:
        super().__init__(title=f"Submit proof · {title}"[:45])
        self.cid = cid
        self.tid = tid
        self.needs_screenshot = needs_screenshot
        # When a screenshot is the real proof (collected as an upload after this
        # modal), the text input is just an optional caption — don't force it, or a
        # member with nothing to type can't submit at all.
        self.value = discord.ui.TextInput(
            label=("Add a note (optional)" if needs_screenshot else prompt_label)[:45],
            style=discord.TextStyle.short if prompt_short else discord.TextStyle.paragraph,
            required=not needs_screenshot,
            max_length=120 if prompt_short else 500,
        )
        self.add_item(self.value)
        # up to 4 admin-defined inputs (modal cap is 5 components total). A
        # screenshot field has no text input — it's collected as an upload after.
        self.custom_inputs: list[tuple[str, discord.ui.TextInput]] = []
        for f in (fields or [])[:4]:
            if f.get("field_type") == "screenshot":
                continue
            inp = discord.ui.TextInput(
                label=str(f["label"])[:45],
                placeholder=str(f.get("example") or "")[:100] or None,
                required=bool(f.get("required", True)),
                max_length=300,
            )
            self.add_item(inp)
            self.custom_inputs.append((f.get("key") or str(f["label"])[:45], inp))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        extra = {key: str(inp.value) for key, inp in self.custom_inputs if str(inp.value).strip()}
        status, reward = await asyncio.to_thread(
            cr.create_submission, self.cid, self.tid,
            interaction.user.id, str(interaction.user), str(self.value), extra or None,
        )
        await interaction.response.send_message(_result_text(status, reward), ephemeral=True)
        if self.needs_screenshot and status in ("pending", "verified"):
            await _collect_screenshot(interaction, self.cid)


class MySubmissionButton(discord.ui.DynamicItem[discord.ui.Button], template=r"gz:mysub:(?P<cid>\d+)"):
    """"My submission": a private (ephemeral) summary of what THIS member has done. It stays on
    the post after the campaign ends, when everything else is gone."""

    def __init__(self, cid: int) -> None:
        self.cid = cid
        super().__init__(discord.ui.Button(label="📋 My submission", style=discord.ButtonStyle.secondary,
                                           custom_id=f"gz:mysub:{cid}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["cid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        info = await asyncio.to_thread(cr.my_submissions, self.cid, interaction.user.id)
        if info is None:
            await interaction.response.send_message("This campaign no longer exists.", ephemeral=True)
            return
        head = f"**{info['title'][:200]}**" + ("" if info["open"] else " (ended)")
        await interaction.response.send_message(head + "\n" + "\n".join(info["lines"])[:1800], ephemeral=True)


class ProofButton(discord.ui.DynamicItem[discord.ui.Button], template=r"gz:proof:(?P<cid>\d+):(?P<tid>\d+)"):
    def __init__(self, cid: int, tid: int, label: str = "Submit proof", honor: bool = False) -> None:
        self.cid = cid
        self.tid = tid
        super().__init__(
            discord.ui.Button(
                label=label[:80],
                style=discord.ButtonStyle.success if honor else discord.ButtonStyle.primary,
                custom_id=f"gz:proof:{cid}:{tid}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["cid"]), int(match["tid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        ctx = await asyncio.to_thread(cr.submit_context, self.cid, self.tid)
        if ctx is None:
            await interaction.response.send_message("This campaign is closed.", ephemeral=True)
            return
        if ctx.get("full"):
            await interaction.response.send_message(
                "🚫 This campaign has reached its participant limit.", ephemeral=True)
            return
        fields = ctx.get("fields") or []
        needs_shot = _needs_screenshot(ctx)
        # A task done with buttons alone (open the link, then Verify): show the panel.
        if self.tid and ctx.get("panel") == "x":
            status = await asyncio.to_thread(cr.task_submission_status, self.cid, self.tid, interaction.user.id)
            if status in ("verified", "pending"):
                await interaction.response.send_message(
                    "Already verified ✅" if status == "verified"
                    else "Already submitted. Waiting for review 🕓", ephemeral=True)
                return
            saved = await asyncio.to_thread(social_handles.get_handle, interaction.user.id)
            if saved:
                await interaction.response.send_message(
                    _task_panel_text(ctx, saved), view=TaskPanelView(self.cid, self.tid, ctx, saved),
                    ephemeral=True)
            else:
                await interaction.response.send_modal(HandleModal(self.cid, ctx, tid=self.tid))
            return
        # Auto-verify raid: ask for the participant's X @username so the bot can
        # confirm reposts / comments / quotes / follows live against twitterapi.io.
        if ctx.get("type") == "raid" and ctx.get("auto_verify_x"):
            await interaction.response.send_modal(
                ProofModal(self.cid, self.tid, ctx["title"], fields,
                           prompt_label="Your X @username", prompt_short=True)
            )
            return
        # One-tap modes with nothing to collect: honor is instant, auto verifies
        # the member is in the server (which, to have clicked, they are).
        if ctx["verification_mode"] in ("honor", "auto") and not fields and not needs_shot:
            status, reward = await asyncio.to_thread(
                cr.create_submission, self.cid, self.tid,
                interaction.user.id, str(interaction.user), None,
            )
            await interaction.response.send_message(_result_text(status, reward), ephemeral=True)
        else:
            prompt = ("Paste the link to your content" if ctx["verification_mode"] == "link"
                      else "Your proof (link or text)")
            await interaction.response.send_modal(
                ProofModal(self.cid, self.tid, ctx["title"], fields,
                           prompt_label=prompt, needs_screenshot=needs_shot)
            )


# ── Ephemeral per-action panel (no DM) ────────────────────────────────────────
# An X raid — or an X social-task with action targets — posts ONE public "Start"
# button. Each member who taps it gets a PRIVATE (ephemeral) panel in the same
# channel: an optional X-handle prompt, a live per-action checklist and a Verify
# button. Only they ever see their own progress or rejection.

def _panel_text(title: str, actions: list[str], statuses: dict,
                *, note: str | None = None, handle: str | None = None) -> str:
    lines = [f"**{title[:200]}**",
             "_Do each action on X, then tap **Verify my actions**._"]
    if handle:
        lines.append(f"Verifying as **@{handle}** (tap **Change handle** if that's wrong)")
    lines.append("")
    for act in actions:
        st = statuses.get(act)
        if st == "verified":
            mark, suffix = "✅", ""
        elif st == "manual":
            mark, suffix = "🕓", " — submitted for review"
        elif st == "failed":
            mark, suffix = "❌", " — not detected yet"
        else:
            mark, suffix = "⬜", ""
        lines.append(f"{mark} {ACTION_LABELS.get(act, act)}{suffix}")
    if note:
        lines += ["", note]
    return "\n".join(lines)


class HandleModal(discord.ui.Modal):
    """Collects the member's X @username so their actions can be verified live."""

    def __init__(self, cid: int, ctx: dict, current: str | None = None, tid: int | None = None) -> None:
        super().__init__(title="Your X username")
        self.cid = cid
        self.tid = tid          # set when asked from a task panel: we return to it
        self.ctx = ctx
        self.handle = discord.ui.TextInput(
            label="Your X @username", placeholder="@yourhandle", default=current,
            style=discord.TextStyle.short, required=True, max_length=120,
        )
        self.add_item(self.handle)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Saved once per Discord account and reused by every campaign.
        saved = await asyncio.to_thread(social_handles.set_handle, interaction.user.id, str(self.handle.value))
        if saved == social_handles.TAKEN:
            await interaction.response.send_message(
                "That X handle is already linked to another Discord account, so it can't be used "
                "here. If it's really yours, ask a server admin for help, or try a different handle.",
                ephemeral=True)
            return
        if not saved:
            await interaction.response.send_message(
                "That doesn't look like an X username. Tap **Start** again and enter it like "
                "`@yourname`.", ephemeral=True)
            return
        if self.tid:
            await interaction.response.send_message(
                _task_panel_text(self.ctx, saved), view=TaskPanelView(self.cid, self.tid, self.ctx, saved),
                ephemeral=True)
            return
        view = ActionPanelView(self.cid, self.ctx, saved)
        statuses = await asyncio.to_thread(cr.action_status_map, self.cid, interaction.user.id)
        await interaction.response.send_message(
            _panel_text(self.ctx["title"], self.ctx["actions"], statuses, handle=saved),
            view=view, ephemeral=True,
        )


class ExtraFieldsModal(discord.ui.Modal):
    """The campaign's configured proof fields (wallet / UID / link for a reward).

    The per-action flow verifies the X actions themselves, so these extras are
    collected once at the end and merged into the SAME submission — never a
    second row."""

    def __init__(self, cid: int, fields: list[dict], title: str) -> None:
        super().__init__(title=f"Your details · {title}"[:45])
        self.cid = cid
        self.wants_screenshot = any((f or {}).get("field_type") == "screenshot" for f in (fields or []))
        self.inputs: list[tuple[str, discord.ui.TextInput]] = []
        for f in (fields or [])[:5]:
            if f.get("field_type") == "screenshot":
                continue
            inp = discord.ui.TextInput(
                label=str(f["label"])[:45],
                placeholder=str(f.get("example") or "")[:100] or None,
                required=bool(f.get("required", True)),
                max_length=300,
            )
            self.add_item(inp)
            self.inputs.append((f.get("key") or str(f["label"])[:45], inp))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = {k: str(inp.value) for k, inp in self.inputs if str(inp.value).strip()}
        await asyncio.to_thread(
            cr.attach_action_extra_fields, self.cid, interaction.user.id, answers,
            str(interaction.user),
        )
        await interaction.response.edit_message(
            content="✅ **All done — thanks!** Your details were saved with your submission.",
            view=None,
        )
        # A screenshot extra can't live in a modal (no file input), so collect it as
        # a follow-up upload — otherwise a configured screenshot field is never asked.
        if self.wants_screenshot:
            await _collect_screenshot(interaction, self.cid)


class ExtraFieldsView(discord.ui.View):
    """Shown after the actions are done when the campaign also collects extras.
    A modal must be an interaction's FIRST response, and Verify already deferred,
    so the extras get their own button."""

    def __init__(self, cid: int, fields: list[dict], title: str) -> None:
        super().__init__(timeout=600)
        self.cid = cid
        self.fields = fields
        self.ctitle = title
        # Whether the modal would have any text inputs at all — a modal made purely
        # of screenshot fields would have zero components, which Discord rejects.
        self.has_text = any((f or {}).get("field_type") != "screenshot" for f in (fields or []))
        self.wants_screenshot = any((f or {}).get("field_type") == "screenshot" for f in (fields or []))

    @discord.ui.button(label="Add your details", style=discord.ButtonStyle.primary)
    async def add_details(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.has_text:
            await interaction.response.send_modal(ExtraFieldsModal(self.cid, self.fields, self.ctitle))
            return
        # Only a screenshot to collect — no modal (it would be empty). Go straight
        # to the follow-up upload.
        await interaction.response.edit_message(content="📸 One last step — upload your screenshot below.", view=None)
        if self.wants_screenshot:
            await _collect_screenshot(interaction, self.cid)


class ActionPanelView(discord.ui.View):
    """The participant's private (ephemeral) panel. Not persistent — it's a live
    session; if the bot restarts the member just taps the public Start button again."""

    def __init__(self, cid: int, ctx: dict, handle: str | None = None) -> None:
        super().__init__(timeout=900)
        self.cid = cid
        self.ctx = ctx
        self.handle = handle
        for act in ctx["actions"]:
            self.add_item(_ActionOpenButton(cid, act, ctx.get("task_url")))
        self.add_item(_VerifyButton(cid))
        if ctx.get("auto_verify_x"):
            self.add_item(_ChangeHandleButton(cid, ctx))


class _ActionOpenButton(discord.ui.Button):
    """Records that the member opened the post for this action (the like-soak gate
    measures from here), then hands them the link."""

    def __init__(self, cid: int, action: str, task_url: str | None) -> None:
        super().__init__(label=ACTION_LABELS.get(action, action),
                         style=discord.ButtonStyle.secondary)
        self.cid = cid
        self.action = action
        self.task_url = task_url

    async def callback(self, interaction: discord.Interaction) -> None:
        await asyncio.to_thread(
            cr.record_action_open, self.cid, interaction.user.id,
            str(interaction.user), self.action,
        )
        target = self.task_url or "the post"
        await interaction.response.send_message(
            f"{ACTION_LABELS.get(self.action, self.action)} → open {target} and do it, "
            "then come back and tap **Verify my actions**.",
            ephemeral=True,
        )


class _ChangeHandleButton(discord.ui.Button):
    def __init__(self, cid: int, ctx: dict) -> None:
        super().__init__(label="Change handle", style=discord.ButtonStyle.secondary)
        self.cid = cid
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(HandleModal(self.cid, self.ctx, self.view.handle))


class _VerifyButton(discord.ui.Button):
    def __init__(self, cid: int) -> None:
        super().__init__(label="Verify my actions", style=discord.ButtonStyle.success)
        self.cid = cid

    async def callback(self, interaction: discord.Interaction) -> None:
        # The live X checks are slow, so defer. That rules out opening a modal
        # from here — the extras get their own button (see ExtraFieldsView).
        await interaction.response.defer()
        view: ActionPanelView = self.view
        ctx = view.ctx
        notes: list[str] = []

        for act in ctx["actions"]:
            statuses = await asyncio.to_thread(cr.action_status_map, self.cid, interaction.user.id)
            if statuses.get(act) in ("verified", "manual"):
                continue
            wait = await asyncio.to_thread(
                cr.action_retry_remaining, self.cid, interaction.user.id, act)
            if wait:
                notes.append(f"⏳ {ACTION_LABELS.get(act, act)}: try again in {wait}s.")
                continue
            res = await asyncio.to_thread(
                cr.verify_user_action, self.cid, interaction.user.id,
                str(interaction.user), act, view.handle,
            )
            if res["status"] == "closed":
                await interaction.edit_original_response(content="This campaign is closed.", view=None)
                return
            if res["status"] in ("need_open", "cooldown"):
                notes.append(f"⏳ {ACTION_LABELS.get(act, act)}: {res['detail']}")

        # Derive the outcome from the final status map, not from the last verify
        # call — actions already settled on a previous tap are skipped above.
        statuses = await asyncio.to_thread(cr.action_status_map, self.cid, interaction.user.id)
        completed = all(statuses.get(a) == "verified" for a in ctx["actions"])
        all_submitted = all(statuses.get(a) in ("verified", "manual") for a in ctx["actions"])

        if not all_submitted:
            note = "\n".join(notes) if notes else (
                "⏳ Not all actions confirmed yet. Do them on X, wait ~30s, then tap **Verify** again.")
            await interaction.edit_original_response(
                content=_panel_text(ctx["title"], ctx["actions"], statuses, note=note, handle=view.handle), view=view)
            return

        # Every action has a result. Collect the campaign's extra proof fields
        # (wallet / UID / link) once, merged into this same submission.
        pending_extras = (ctx.get("fields") and not await asyncio.to_thread(
            cr.action_extra_collected, self.cid, interaction.user.id))
        closing = ("✅ **All done — reward granted!**" if completed
                   else "🕓 **Submitted.** Some actions need an admin's review.")
        if pending_extras:
            await interaction.edit_original_response(
                content=_panel_text(ctx["title"], ctx["actions"], statuses, handle=view.handle,
                                    note=f"{closing}\n\nOne last step — tap **Add your details**."),
                view=ExtraFieldsView(self.cid, ctx["fields"], ctx["title"]),
            )
        else:
            await interaction.edit_original_response(
                content=_panel_text(ctx["title"], ctx["actions"], statuses, note=closing, handle=view.handle),
                view=None,
            )


# ── Task panel: open the link, then Verify (no typing) ────────────────────────
_TASK_VERIFY_COOLDOWN = 30        # seconds between Verify taps on the same task
_TASK_AUTO_TRIES = 3              # failed checks before it is sent to the admins
_task_tries: dict = {}            # (user_id, tid) -> (tries, last_tap_monotonic)
_GOAL_NAMES = {"likes": "Like", "retweets": "Repost", "comments": "Comment", "quotes": "Quote", "follows": "Follow"}


def _task_panel_text(ctx: dict, handle: str | None, note: str | None = None) -> str:
    lines = [f"**{str(ctx['title'])[:200]}**",
             "1️⃣ Tap **Open on X** and do it.",
             "2️⃣ Come back and tap **Verify**. It is checked automatically."]
    if handle:
        lines.append(f"Checking **@{handle}** (tap **Change handle** if that's wrong)")
    if note:
        lines += ["", note]
    return "\n".join(lines)


def _task_checklist(results: dict) -> str:
    out = []
    for key, name in _GOAL_NAMES.items():
        r = (results or {}).get(key)
        if not r:
            continue
        st = r.get("status")
        out.append(f"{'✅' if st == 'verified' else '🕓' if st == 'manual' else '❌' if st == 'failed' else '⏳'} {name}")
    return "\n".join(out)


class TaskPanelView(discord.ui.View):
    """The member's private panel for a button-verified task: a link button, Verify,
    Change handle. A live session (not persistent): after a restart they tap the task again."""

    def __init__(self, cid: int, tid: int, ctx: dict, handle: str | None) -> None:
        super().__init__(timeout=900)
        self.cid, self.tid, self.ctx, self.handle = cid, tid, ctx, handle
        url = str(ctx.get("task_url") or "").strip()
        # Discord refuses a malformed / over-long link button, which would break the whole panel.
        if re.match(r"^https?://[^\s<>\"']{3,500}$", url):
            self.add_item(discord.ui.Button(label="🐦 Open on X", style=discord.ButtonStyle.link, url=url))
        self.add_item(_TaskVerifyButton())
        self.add_item(_TaskChangeHandleButton())


class _TaskChangeHandleButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Change handle", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        v: TaskPanelView = self.view
        await interaction.response.send_modal(HandleModal(v.cid, v.ctx, v.handle, tid=v.tid))


class _TaskVerifyButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="✅ Verify", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction) -> None:
        import time
        v: TaskPanelView = self.view
        key = (interaction.user.id, v.tid)
        now = time.monotonic()
        tries, last = _task_tries.get(key, (0, 0.0))
        wait = int(_TASK_VERIFY_COOLDOWN - (now - last))
        if last and wait > 0:
            await interaction.response.send_message(f"⏳ Please wait {wait}s, then tap Verify again.", ephemeral=True)
            return
        status = await asyncio.to_thread(cr.task_submission_status, v.cid, v.tid, interaction.user.id)
        if status in ("verified", "pending"):
            await interaction.response.send_message(
                "Already verified ✅" if status == "verified" else "Already submitted. Waiting for review 🕓",
                ephemeral=True)
            return
        await interaction.response.defer()           # the live X check can be slow
        result = await asyncio.to_thread(cr.check_task_x, v.cid, v.tid, v.handle)
        overall = result.get("overall")
        if overall == "closed":
            await interaction.edit_original_response(content="This campaign is closed.", view=None)
            return
        if overall == "verified":
            _task_tries.pop(key, None)
            st, reward = await asyncio.to_thread(
                cr.create_submission, v.cid, v.tid, interaction.user.id, str(interaction.user), None,
                None, None, True)
            await interaction.edit_original_response(content=_result_text(st, reward), view=None)
            return
        tries += 1
        _task_tries[key] = (tries, now)
        if len(_task_tries) > 5000:
            for k in [k for k, x in _task_tries.items() if now - x[1] > 3600]:
                _task_tries.pop(k, None)
        checklist = _task_checklist(result.get("results") or {})
        if tries >= _TASK_AUTO_TRIES:
            _task_tries.pop(key, None)
            st, reward = await asyncio.to_thread(
                cr.create_submission, v.cid, v.tid, interaction.user.id, str(interaction.user), None)
            await interaction.edit_original_response(
                content=((checklist + "\n\n") if checklist else "")
                + ("🕓 I couldn't confirm it yet, so it was sent to the admins. It is also re-checked "
                   "automatically for the next 30 minutes." if st == "pending" else _result_text(st, reward)),
                view=None)
            return
        note = ((checklist + "\n\n") if checklist else "") + (
            f"⏳ Not detected yet ({tries}/{_TASK_AUTO_TRIES}). Do it on X, wait about 30 seconds, "
            "then tap Verify again.")
        await interaction.edit_original_response(content=_task_panel_text(v.ctx, v.handle, note), view=v)


class ActionStartButton(discord.ui.DynamicItem[discord.ui.Button],
                        template=r"gz:actstart:(?P<cid>\d+)"):
    """Persistent public button on an action-driven campaign — survives restarts."""

    def __init__(self, cid: int, label: str = "🐦 Start") -> None:
        self.cid = cid
        super().__init__(discord.ui.Button(
            label=label[:80], style=discord.ButtonStyle.primary,
            custom_id=f"gz:actstart:{cid}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["cid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _open_action_panel(interaction, self.cid)


class RaidStartButton(discord.ui.DynamicItem[discord.ui.Button],
                      template=r"gz:raidstart:(?P<cid>\d+)"):
    """Legacy custom_id on raid posts made before the panel was generalized.
    Kept registered so those messages keep working after a redeploy."""

    def __init__(self, cid: int) -> None:
        self.cid = cid
        super().__init__(discord.ui.Button(
            label="🐦 Start raid", style=discord.ButtonStyle.primary,
            custom_id=f"gz:raidstart:{cid}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["cid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _open_action_panel(interaction, self.cid)


async def _open_action_panel(interaction: discord.Interaction, cid: int) -> None:
    ctx = await asyncio.to_thread(cr.action_context, cid)
    if ctx is None:
        await interaction.response.send_message("This campaign is closed.", ephemeral=True)
        return
    if ctx.get("full"):
        await interaction.response.send_message(
            "🚫 This campaign has reached its participant limit.", ephemeral=True)
        return
    # Live verification needs the member's X handle; manual review doesn't.
    if ctx.get("auto_verify_x"):
        # Already saved a handle (any earlier campaign)? Skip the typing: go straight
        # to the panel with Verify and Change handle.
        saved = await asyncio.to_thread(social_handles.get_handle, interaction.user.id)
        if saved:
            statuses = await asyncio.to_thread(cr.action_status_map, cid, interaction.user.id)
            await interaction.response.send_message(
                _panel_text(ctx["title"], ctx["actions"], statuses, handle=saved),
                view=ActionPanelView(cid, ctx, saved), ephemeral=True,
            )
            return
        await interaction.response.send_modal(HandleModal(cid, ctx))
        return
    statuses = await asyncio.to_thread(cr.action_status_map, cid, interaction.user.id)
    await interaction.response.send_message(
        _panel_text(ctx["title"], ctx["actions"], statuses),
        view=ActionPanelView(cid, ctx), ephemeral=True,
    )


def _deadline_text(ends_at) -> str:
    if not ends_at:
        return ""
    # Discord renders <t:unix:R> as a live "in 3 hours" relative timestamp.
    return f"<t:{int(ends_at.timestamp())}:R>"


def build_embed(data: dict, brand: str = "Guildizer") -> discord.Embed:
    embed = discord.Embed(title=data["title"][:256], description=(data["description"] or None), color=ACCENT)
    if data["tasks"]:
        for t in data["tasks"]:
            val = t["description"] or ""
            if t["task_url"]:
                val += f"\n🔗 {t['task_url']}"
            if t["reward_xp"]:
                val += f"\n🎁 {t['reward_xp']} XP"
            embed.add_field(name=t["title"][:256], value=(val.strip() or "—")[:1024], inline=False)
    else:
        if data["task_url"]:
            embed.add_field(name="Task", value=data["task_url"][:1024], inline=False)
        reward = f"{data['reward_xp']} XP" if data["reward_xp"] else ""
        if data.get("action_xp"):
            _lbl = {"like": "Like", "retweet": "Retweet", "comment": "Comment", "quote": "Quote", "follow": "Follow"}
            reward = " · ".join(f"{_lbl.get(a, a)} {x}" for a, x in data["action_xp"].items()) + f" (total {data['reward_xp']} XP)"
        if data["reward_label"]:
            reward = (reward + " · " if reward else "") + data["reward_label"]
        if reward:
            embed.add_field(name="Reward", value=reward[:1024], inline=False)

    # What members actually submit — sets expectations before they tap.
    if data.get("proof_summary"):
        embed.add_field(name="📝 Proof", value=data["proof_summary"][:1024], inline=False)

    # Action targets. A raid always shows them; a social task only when the owner
    # opted in via "Show targets publicly".
    goals = data.get("raid_goals") or (data.get("social_targets") if data.get("show_targets") else {}) or {}
    if goals:
        progress = data.get("progress") or {}
        parts = []
        for k, v in goals.items():
            if not v:
                continue
            done = progress.get(k, 0)
            left = max(0, int(v) - int(done))
            parts.append(f"{GOAL_LABELS.get(k, k)}: {done}/{v}" + (f" ({left} left)" if left else " ✅"))
        if parts:
            name = "🎯 Raid goals" if data.get("type") == "raid" else "🎯 Targets"
            embed.add_field(name=name, value=" · ".join(parts)[:1024], inline=False)
        if data.get("auto_verify_x"):
            embed.add_field(
                name="⚡ Auto-verified",
                value="Tap **Start**, enter your X @username, and verify — reposts, "
                      "comments, quotes and follows are confirmed automatically, privately to you.",
                inline=False,
            )

    deadline = _deadline_text(data.get("ends_at"))
    if deadline:
        embed.add_field(name="⏳ Ends", value=deadline, inline=False)

    # White-label bots brand the footer with their own name, not ours.
    embed.set_footer(text=f"{brand} • tap a button below to take part")
    return embed


def build_view(data: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    # An ended campaign keeps only "My submission": there is nothing left to take part in.
    if data.get("is_open") is False:
        view.add_item(discord.ui.Button(label="🏁 Closed", style=discord.ButtonStyle.secondary, disabled=True,
                                        custom_id=f"gz:closed:{data['id']}"))
        view.add_item(MySubmissionButton(data["id"]))
        return view
    # Action-driven campaigns (X raid, or an X social task with targets) get ONE
    # public Start button; each member gets a private ephemeral panel (no DM).
    # Everything else keeps the per-task proof buttons.
    if data.get("has_action_flow"):
        label = "🐦 Start raid" if data.get("type") == "raid" else "🐦 Start tasks"
        view.add_item(ActionStartButton(data["id"], label=label))
        view.add_item(MySubmissionButton(data["id"]))
        return view
    tasks = data["tasks"][:25]
    if tasks:
        for t in tasks:
            view.add_item(ProofButton(
                data["id"], t["id"],
                label=cr.task_button_label(t), honor=(t["verification_mode"] in ("honor", "auto")),
            ))
    else:
        view.add_item(ProofButton(
            data["id"], 0, label="Submit proof",
            honor=(data["verification_mode"] in ("honor", "auto")),
        ))
    if len(view.children) < 25:             # Discord allows 25 buttons per message
        view.add_item(MySubmissionButton(data["id"]))
    return view


async def post_campaign(bot, cid: int) -> None:
    """(Re)post a campaign announcement with proof buttons into its channel."""
    data = await asyncio.to_thread(cr.load_for_post, cid)
    if not data or not data["channel_id"]:
        await asyncio.to_thread(cr.mark_post_failed, cid, "no announcement channel set")
        return
    channel = bot.get_channel(int(data["channel_id"]))
    if channel is None or not hasattr(channel, "send"):
        await asyncio.to_thread(cr.mark_post_failed, cid, "channel not found")
        return

    # Remove the previous announcement from wherever it actually lives — the admin
    # may have re-pointed the campaign at a different channel since it was posted.
    if data["message_id"]:
        old_channel = bot.get_channel(int(data.get("posted_channel_id") or data["channel_id"]))
        if old_channel is not None:
            try:
                old = await old_channel.fetch_message(int(data["message_id"]))
                await old.delete()
            except Exception:  # noqa: BLE001 — old message may be gone; ignore
                pass

    brand = (bot.user.name if bot.user else None) or "Guildizer"
    try:
        msg = await channel.send(embed=build_embed(data, brand=brand), view=build_view(data))
        if data.get("pin_message"):
            try:
                await msg.pin()
            except discord.HTTPException:
                log.info("could not pin campaign %s (missing permission or pin limit)", cid)
        await asyncio.to_thread(cr.mark_posted, cid, msg.id)
        log.info("Posted campaign %s to channel %s", cid, data["channel_id"])
    except discord.Forbidden:
        await asyncio.to_thread(cr.mark_post_failed, cid, "missing permission to post")
    except discord.HTTPException as exc:
        await asyncio.to_thread(cr.mark_post_failed, cid, str(exc))


async def close_post(bot, cid: int) -> bool:
    """The campaign ended (or was closed): switch its announcement to the ended form in place
    - a closing note on the embed, only "My submission" left, unpinned. Nothing is deleted or
    re-posted. Returns True when handled (also when the post is already gone)."""
    data = await asyncio.to_thread(cr.load_for_post, cid)
    if not data:
        return True
    guild = bot.get_guild(int(data["guild_id"]))
    if guild is None:
        return False                                   # another bot serves this server
    await asyncio.to_thread(cr.mark_closed, cid)       # ends an expired campaign, like Telegizer's job
    data = await asyncio.to_thread(cr.load_for_post, cid)
    if data.get("is_open"):
        return True                                    # the owner extended it meanwhile
    channel = bot.get_channel(int(data.get("posted_channel_id") or data["channel_id"] or 0))
    msg = None
    if channel is not None and data["message_id"]:
        try:
            msg = await channel.fetch_message(int(data["message_id"]))
        except discord.NotFound:
            msg = None
        except discord.HTTPException:
            return False                               # try again on the next tick
    if msg is not None:
        brand = (bot.user.name if bot.user else None) or "Guildizer"
        embed = build_embed(data, brand=brand)
        embed.set_footer(text="🏁 This campaign has ended. New submissions are closed.")
        try:
            await msg.edit(embed=embed, view=build_view(data))
            if data.get("pin_message"):
                try:
                    await msg.unpin()
                except discord.HTTPException:
                    pass
        except discord.Forbidden:
            log.info("no permission to edit the ended post of campaign %s", cid)
        except discord.HTTPException as exc:
            log.info("could not edit the ended post of campaign %s: %s", cid, exc)
            return False
    await asyncio.to_thread(cr.mark_closed, cid, flag_post=True)
    return True


async def unpost_campaign(bot, cid: int) -> None:
    """Delete a campaign's channel announcement. Submissions and rewards are kept
    and the campaign can be posted again afterwards."""
    target = await asyncio.to_thread(cr.unpost_target, cid)
    if not target:
        await asyncio.to_thread(cr.mark_unposted, cid, None)
        return
    channel_id, message_id = target
    channel = bot.get_channel(int(channel_id))
    if channel is None:
        await asyncio.to_thread(cr.mark_unposted, cid, None)
        return
    try:
        msg = await channel.fetch_message(int(message_id))
        await msg.delete()
    except discord.NotFound:
        pass  # already gone — treat as deleted
    except discord.Forbidden:
        await asyncio.to_thread(cr.mark_unposted, cid, "missing permission to delete the post")
        return
    except discord.HTTPException as exc:
        await asyncio.to_thread(cr.mark_unposted, cid, str(exc))
        return
    await asyncio.to_thread(cr.mark_unposted, cid, None)
    log.info("Deleted campaign %s announcement", cid)


def review_notice_text(item: dict) -> str:
    """The DM a member gets after a review. Pure; also used by the dashboard preview."""
    if item["status"] == "verified":
        reward = item["reward"]
        return (f"\u2705 Your submission for **{item['title']}** was approved"
                + (f" \u2014 +{reward} XP!" if reward else "!"))
    text = f"\u274c Your submission for **{item['title']}** was rejected."
    if item.get("reason"):
        text += f"\n> {item['reason']}"
    if item.get("allow_resubmit"):
        text += "\nYou can submit again."
    return text


def preview_button_labels(data: dict) -> list[str]:
    """Labels of the buttons build_view() would attach (dashboard preview; keep in step with build_view)."""
    if data.get("has_action_flow"):
        return ["\U0001f426 Start raid" if data.get("type") == "raid" else "\U0001f426 Start tasks"]
    tasks = data["tasks"][:25]
    if tasks:
        return [f"Submit: {t['title']}" for t in tasks]
    return ["Submit proof"]


async def deliver_review_notices(bot, serves_fn=None) -> None:
    """DM members the outcome of a reviewed submission. Best-effort: a closed DM
    is recorded on the submission, never retried forever.

    `serves_fn(guild_id) -> bool` scopes delivery to the guilds this bot identity
    owns, so in a multi-bot deployment a custom bot never grabs (and fails, and
    thereby marks) a notice that belongs to the official bot — unserved notices are
    left pending for the right identity to pick up."""
    for item in await asyncio.to_thread(cr.submissions_to_notify):
        if serves_fn is not None and not serves_fn(item["guild_id"]):
            continue
        try:
            user = bot.get_user(int(item["user_id"])) or await bot.fetch_user(int(item["user_id"]))
        except Exception:  # noqa: BLE001
            await asyncio.to_thread(cr.mark_notified, item["id"], False, "user not found")
            continue
        text = review_notice_text(item)
        try:
            await user.send(text)
            await asyncio.to_thread(cr.mark_notified, item["id"], True)
        except discord.Forbidden:
            await asyncio.to_thread(cr.mark_notified, item["id"], False, "member has DMs closed")
        except discord.HTTPException as exc:
            await asyncio.to_thread(cr.mark_notified, item["id"], False, str(exc))
