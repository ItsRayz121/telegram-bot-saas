"""Discord UI for campaign proof flows: a persistent "Submit proof" button per
campaign/task and a proof modal. Buttons survive bot restarts via DynamicItem
(custom_id carries the campaign + task ids); register once with
bot.add_dynamic_items(ProofButton).
"""
from __future__ import annotations

import asyncio
import logging

import discord

import campaign_runtime as cr

log = logging.getLogger("guildizer.campaigns")

ACCENT = 0x5865F2


def _result_text(status: str, reward: int) -> str:
    if status == "verified":
        return f"✅ Verified! +{reward} XP" if reward else "✅ Verified — thanks!"
    if status == "pending":
        return "📝 Submitted — an admin will review it shortly. Thanks!"
    if status == "duplicate":
        return "🙌 You've already submitted for this one."
    return "This campaign is closed."


class ProofModal(discord.ui.Modal):
    def __init__(self, cid: int, tid: int, title: str, fields: list[dict] | None = None,
                 prompt_label: str = "Your proof (link or text)",
                 prompt_short: bool = False) -> None:
        super().__init__(title=f"Submit proof · {title}"[:45])
        self.cid = cid
        self.tid = tid
        # For an auto-verify raid, prompt_label becomes "Your X @username" (short input)
        # so the bot can confirm the actions live against twitterapi.io.
        self.value = discord.ui.TextInput(
            label=prompt_label[:45],
            style=discord.TextStyle.short if prompt_short else discord.TextStyle.paragraph,
            required=True,
            max_length=120 if prompt_short else 500,
        )
        self.add_item(self.value)
        # up to 4 admin-defined inputs (modal cap is 5 components total)
        self.custom_inputs: list[tuple[str, discord.ui.TextInput]] = []
        for f in (fields or [])[:4]:
            inp = discord.ui.TextInput(
                label=str(f["label"])[:45],
                required=bool(f.get("required", True)),
                max_length=300,
            )
            self.add_item(inp)
            self.custom_inputs.append((str(f["label"])[:45], inp))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        extra = {label: str(inp.value) for label, inp in self.custom_inputs if str(inp.value).strip()}
        status, reward = await asyncio.to_thread(
            cr.create_submission, self.cid, self.tid,
            interaction.user.id, str(interaction.user), str(self.value), extra or None,
        )
        await interaction.response.send_message(_result_text(status, reward), ephemeral=True)


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
        fields = ctx.get("fields") or []
        # Auto-verify raid: ask for the participant's X @username so the bot can
        # confirm reposts / comments / quotes / follows live against twitterapi.io.
        if ctx.get("type") == "raid" and ctx.get("auto_verify_x"):
            await interaction.response.send_modal(
                ProofModal(self.cid, self.tid, ctx["title"], fields,
                           prompt_label="Your X @username", prompt_short=True)
            )
            return
        if ctx["verification_mode"] == "honor" and not fields:
            status, reward = await asyncio.to_thread(
                cr.create_submission, self.cid, self.tid,
                interaction.user.id, str(interaction.user), None,
            )
            await interaction.response.send_message(_result_text(status, reward), ephemeral=True)
        else:
            await interaction.response.send_modal(
                ProofModal(self.cid, self.tid, ctx["title"], fields)
            )


# ── Ephemeral raid panel (no DM) ──────────────────────────────────────────────
# An auto-verify raid posts ONE public "Start raid" button. Each member who taps it
# gets a PRIVATE (ephemeral) panel in the same channel: an X-handle prompt, a live
# per-action checklist and a Verify button. Only they ever see their own progress or
# rejection — Discord-native, no DMs.
_GOAL_LABELS = {"likes": "❤️ Like", "retweets": "🔁 Repost",
                "comments": "💬 Comment", "quotes": "❝ Quote", "follows": "➕ Follow"}


def _panel_text(title: str, goals: dict, results: dict | None, *, status: str | None = None) -> str:
    lines = [f"**{title[:200]}**", "_Tap Verify after you’ve done the actions on X._", ""]
    for k, v in goals.items():
        if not v:
            continue
        r = (results or {}).get(k) or {}
        st = r.get("status")
        if st == "verified":
            mark, note = "✅", ""
        elif k == "likes":
            mark, note = "❤️", " — counted (likes can’t be auto-verified)"
        elif st == "failed":
            mark, note = "❌", " — not detected yet"
        else:
            mark, note = "⬜", ""
        lines.append(f"{mark} {_GOAL_LABELS.get(k, k)}{note}")
    if status == "verified":
        lines += ["", "✅ **All done — reward granted!**"]
    elif status == "pending":
        lines += ["", "⏳ Not all actions confirmed yet. Do them on X, wait ~30s, then tap **Verify** again."]
    return "\n".join(lines)


class RaidHandleModal(discord.ui.Modal):
    def __init__(self, cid: int, goals: dict, ctitle: str) -> None:
        super().__init__(title="Join raid")
        self.cid = cid
        self.goals = goals
        self.ctitle = ctitle
        self.handle = discord.ui.TextInput(
            label="Your X @username", placeholder="@yourhandle",
            style=discord.TextStyle.short, required=True, max_length=120,
        )
        self.add_item(self.handle)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        view = RaidPanelView(self.cid, str(self.handle.value), self.goals, self.ctitle)
        await interaction.response.send_message(
            _panel_text(self.ctitle, self.goals, {}), view=view, ephemeral=True,
        )


class RaidPanelView(discord.ui.View):
    """The participant's private (ephemeral) panel. Not persistent — it's a live
    session; if the bot restarts the member just taps the public Start button again."""

    def __init__(self, cid: int, handle: str, goals: dict, ctitle: str) -> None:
        super().__init__(timeout=600)
        self.cid = cid
        self.handle = handle
        self.goals = goals
        self.ctitle = ctitle

    @discord.ui.button(label="Verify my actions", style=discord.ButtonStyle.success)
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        status, reward, results = await asyncio.to_thread(
            cr.verify_raid_submission, self.cid, interaction.user.id,
            str(interaction.user), self.handle,
        )
        if status in ("closed", "not_raid"):
            await interaction.edit_original_response(content="This raid is closed.", view=None)
            return
        if status in ("verified", "duplicate"):
            for child in self.children:
                child.disabled = True
            await interaction.edit_original_response(
                content=_panel_text(self.ctitle, self.goals, results, status="verified"), view=None)
        else:
            await interaction.edit_original_response(
                content=_panel_text(self.ctitle, self.goals, results, status="pending"), view=self)

    @discord.ui.button(label="Change handle", style=discord.ButtonStyle.secondary)
    async def change_handle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(RaidHandleModal(self.cid, self.goals, self.ctitle))


class RaidStartButton(discord.ui.DynamicItem[discord.ui.Button], template=r"gz:raidstart:(?P<cid>\d+)"):
    """Persistent public button on an auto-verify raid post — survives restarts."""

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
        ctx = await asyncio.to_thread(cr.raid_context, self.cid)
        if ctx is None:
            await interaction.response.send_message("This raid is closed.", ephemeral=True)
            return
        await interaction.response.send_modal(
            RaidHandleModal(self.cid, ctx["goals"], ctx["title"]))


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
        if data["reward_label"]:
            reward = (reward + " · " if reward else "") + data["reward_label"]
        if reward:
            embed.add_field(name="Reward", value=reward[:1024], inline=False)
    # Twitter Raid: show the like/retweet/comment/follow targets in the post.
    goals = data.get("raid_goals") or {}
    if goals:
        _gl = {"likes": "❤️ Likes", "retweets": "🔁 Retweets",
               "comments": "💬 Comments", "follows": "➕ Follows"}
        line = " · ".join(f"{_gl.get(k, k)}: {v}" for k, v in goals.items() if v)
        if line:
            embed.add_field(name="🎯 Raid goals", value=line[:1024], inline=False)
        if data.get("auto_verify_x"):
            embed.add_field(
                name="⚡ Auto-verified",
                value="Tap **Start raid**, enter your X @username, and verify — reposts, "
                      "comments, quotes and follows are confirmed automatically, privately to you.",
                inline=False,
            )
    # White-label bots brand the footer with their own name, not ours.
    embed.set_footer(text=f"{brand} • tap a button below to submit proof")
    return embed


def build_view(data: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    # Auto-verify raid → ONE public "Start raid" button; each member gets a private
    # ephemeral panel (no DM). All other campaigns keep the per-task proof buttons.
    if data.get("type") == "raid" and data.get("auto_verify_x"):
        view.add_item(RaidStartButton(data["id"]))
        return view
    tasks = data["tasks"][:25]
    if tasks:
        for t in tasks:
            view.add_item(ProofButton(
                data["id"], t["id"],
                label=f"Submit: {t['title']}", honor=(t["verification_mode"] == "honor"),
            ))
    else:
        view.add_item(ProofButton(
            data["id"], 0, label="Submit proof",
            honor=(data["verification_mode"] == "honor"),
        ))
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

    if data["message_id"]:
        try:
            old = await channel.fetch_message(int(data["message_id"]))
            await old.delete()
        except Exception:  # noqa: BLE001 — old message may be gone; ignore
            pass

    brand = (bot.user.name if bot.user else None) or "Guildizer"
    try:
        msg = await channel.send(embed=build_embed(data, brand=brand), view=build_view(data))
        await asyncio.to_thread(cr.mark_posted, cid, msg.id)
        log.info("Posted campaign %s to channel %s", cid, data["channel_id"])
    except discord.Forbidden:
        await asyncio.to_thread(cr.mark_post_failed, cid, "missing permission to post")
    except discord.HTTPException as exc:
        await asyncio.to_thread(cr.mark_post_failed, cid, str(exc))
