"""Engagement Campaigns — Telegram participation (Phase 4).

Shared DM proof-collection flow + callbacks for BOTH bot lineages. Wired into
each bot purely additively (handlers registered in a separate PTB group that
runs first and only acts on `eng_*` payloads / an active flow), so existing
handlers are never touched.

User journey:
  group post button → deep-link `?start=eng_<id>` → opens private chat →
  bot collects proof field-by-field in DM → creates an EngagementSubmission →
  status reply (Verified / Pending review). `?start=engmy_<id>` shows status.

Conversation state lives in context.user_data['eng'] (per-user, in-process).
Identity is anchored by the campaign id in the deep-link, so one shared bot
serving many groups never mixes submissions (see ENGAGEMENT_CAMPAIGNS_PLAN.md).
"""

import hashlib
import html
import logging
import os
import time

logger = logging.getLogger(__name__)

# Per-user anti-spam cooldown between participation taps (seconds, in-process).
_PARTICIPATE_COOLDOWN = 3.0
_last_participate = {}

# ── Growth promo (Phase 8) — official bot ONLY, subtle, frequency-capped ───────
# Custom bots are white-label and NEVER show Telegizer branding. The footer only
# appears in the participant's private DM (never the group post), at most once per
# _PROMO_INTERVAL per user, with a referral link attributed to the campaign owner.
_PROMO_ENABLED = os.environ.get("ENGAGEMENT_PROMO", "true").lower() in ("1", "true", "yes")
_PROMO_INTERVAL = float(os.environ.get("ENGAGEMENT_PROMO_INTERVAL_DAYS", "3")) * 86400.0
_last_promo = {}


def _promo_footer(campaign, lineage, user_id):
    """Return a one-line HTML promo footer, or '' when it shouldn't show."""
    if lineage != "official" or not _PROMO_ENABLED:
        return ""
    if (campaign.settings or {}).get("hide_branding"):
        return ""
    now = time.monotonic()
    if now - _last_promo.get(user_id, 0) < _PROMO_INTERVAL:
        return ""
    try:
        from .models import User
        from .config import Config
        bot_un = (Config.TELEGRAM_BOT_USERNAME or "telegizer_bot").lstrip("@")
        owner = User.query.get(campaign.owner_user_id) if campaign.owner_user_id else None
        code = getattr(owner, "referral_code", None)
        link = f"https://t.me/{bot_un}?start=ref_{code}" if code else f"https://t.me/{bot_un}"
    except Exception:
        return ""
    _last_promo[user_id] = now
    # Small, professional one-line footer — an embedded hyperlink, never a raw URL.
    return f'\n\n<a href="{html.escape(link, quote=True)}">Manage your Telegram groups with Telegizer.</a>'


# ── DB helpers (run inside flask_app.app_context) ─────────────────────────────

def _load_campaign(campaign_id, lineage, bot_id):
    """Return the campaign iff it belongs to the bot processing this update."""
    from .models import EngagementCampaign, Group
    c = EngagementCampaign.query.get(campaign_id)
    if not c:
        return None
    if lineage == "official":
        return c if c.telegram_group_id else None
    # custom: must belong to one of this bot's groups
    if not c.group_id:
        return None
    grp = Group.query.get(c.group_id)
    if not grp or grp.bot_id != bot_id:
        return None
    return c


def _existing_submission(campaign_id, telegram_user_id, task_id=None):
    from .models import EngagementSubmission
    return EngagementSubmission.query.filter_by(
        campaign_id=campaign_id, task_id=task_id, telegram_user_id=str(telegram_user_id)
    ).order_by(EngagementSubmission.created_at.desc()).first()


def _ordered_fields(campaign):
    # The relationship already declares order_by=EngagementCustomField.order.
    return [f.to_dict() for f in campaign.custom_fields.all()]


_FIELD_TYPE_LABEL = {
    "text": "Text", "url": "URL / Link", "uid": "Exchange UID",
    "wallet": "Wallet address", "screenshot": "Screenshot",
    "tx_hash": "Transaction hash", "username": "Username / handle",
}

_STATUS_LINE = {
    "pending": "🟡 Pending review",
    "verified": "✅ Verified",
    "rejected": "❌ Rejected",
}


_MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


def _render_leaderboard(campaign, lb):
    """A compact, DM-friendly leaderboard rendering for the bot."""
    lines = [
        f"🏆 <b>Leaderboard — {html.escape(campaign.title or '')}</b>",
        f"{lb.get('total_participants', 0)} participant(s)",
        "",
    ]
    entries = lb.get("entries") or []
    if not entries:
        lines.append("No verified participants yet — be the first!")
    else:
        for e in entries:
            badge = _MEDAL.get(e["rank"], f"{e['rank']}.")
            name = (f"@{e['telegram_username']}" if e.get("telegram_username")
                    else f"User {e['telegram_user_id']}")
            cnt = f" — {e['verified_count']} ✓" if e.get("verified_count", 0) != 1 else ""
            xp = f" · +{e['xp_earned']} XP" if e.get("xp_earned") else ""
            lines.append(f"{badge} {html.escape(name)}{cnt}{xp}")
    me = lb.get("me")
    if me and not any(e["telegram_user_id"] == me["telegram_user_id"] for e in entries):
        xp = f" · +{me['xp_earned']} XP" if me.get("xp_earned") else ""
        lines.append("")
        lines.append(f"Your rank: #{me['rank']}{xp}")
    return "\n".join(lines)


def _render_my_submission(campaign, sub):
    """A full, readable summary of the participant's own submission. Resolves the
    field labels from the submission's task (multi-task) or the campaign."""
    from .models import EngagementTask
    title_extra = ""
    if sub.task_id:
        task = EngagementTask.query.get(sub.task_id)
        fields = {f.key: f for f in task.custom_fields.all()} if task else {}
        if task:
            title_extra = f" — {html.escape(task.title or '')}"
    else:
        fields = {f.key: f for f in campaign.custom_fields.all()}
    lines = [
        "📋 <b>Your Submission</b>",
        f"Campaign: {html.escape(campaign.title or '')}{title_extra}",
    ]
    payload = sub.payload or {}
    # Per-action verify submissions store a structured action map, not flat fields.
    actions = payload.get("actions") if isinstance(payload.get("actions"), dict) else None
    if actions:
        from . import engagement as eng
        ordered = [a for _gk, a, _t in eng.campaign_action_goals(campaign)] or list(actions.keys())
        lines.append("")
        for action in ordered:
            emoji, alabel = _ACTION_META.get(action, ("•", action.title()))
            st = (actions.get(action) or {}).get("status")
            mark = {"verified": "✅", "manual": "🕒", "failed": "❌"}.get(st, "⬜")
            lines.append(f"{mark} {emoji} {alabel}")
    for key, value in payload.items():
        if key == "actions" or value in (None, "", "[screenshot]"):
            continue
        f = fields.get(key)
        type_label = _FIELD_TYPE_LABEL.get(getattr(f, "field_type", None), None)
        label = html.escape(getattr(f, "label", None) or key)
        prefix = f"{label}"
        if type_label:
            prefix += f" ({type_label})"
        lines.append(f"{prefix}: {html.escape(str(value))}")
    if sub.file_id:
        lines.append("Screenshot: 📎 uploaded")
    lines.append(f"Status: {_STATUS_LINE.get(sub.status, sub.status)}")
    if sub.created_at:
        lines.append(f"Submitted: {sub.created_at.strftime('%Y-%m-%d %H:%M')} UTC")
    if sub.status == "rejected" and sub.review_reason:
        lines.append(f"Reason: {html.escape(sub.review_reason)}")
    return "\n".join(lines)


# ── Message helpers ───────────────────────────────────────────────────────────

def _cancel_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton("✖ Cancel", callback_data="eng_cancel")]])


def _completed_task_ids(campaign_id, telegram_user_id):
    """Task ids the user has a verified/pending (i.e. non-rejected) submission for."""
    from .models import EngagementSubmission
    rows = EngagementSubmission.query.filter_by(
        campaign_id=campaign_id, telegram_user_id=str(telegram_user_id)
    ).all()
    return {s.task_id for s in rows if s.task_id and s.status in ("verified", "pending")}


def _task_picker(campaign, done_ids):
    """Inline keyboard with one button per task (✓ on already-submitted tasks).
    When settings.sequential_tasks is on, a task stays 🔒 locked until every task
    before it (by order) is done — so members complete them in sequence."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    sequential = bool((campaign.settings or {}).get("sequential_tasks"))
    rows = []
    prior_all_done = True
    for t in campaign.tasks.all():
        is_done = t.id in done_ids
        xp = f" (+{t.reward_xp} XP)" if t.reward_xp else ""
        locked = sequential and not is_done and not prior_all_done
        if locked:
            label = f"🔒 {t.title}{xp}"[:64]
            rows.append([InlineKeyboardButton(label, callback_data=f"englock_{campaign.id}")])
        else:
            mark = "✅ " if is_done else ""
            label = f"{mark}{t.title}{xp}"[:64]
            rows.append([InlineKeyboardButton(label, callback_data=f"engtask_{campaign.id}_{t.id}")])
        prior_all_done = prior_all_done and is_done
    return InlineKeyboardMarkup(rows)


def _default_proof_field(spec):
    """A sensible proof field for a review-based task (manual / screenshot / link)
    that has no configured proof fields — so the bot collects real proof instead
    of accepting an empty submission. `link` mode needs a URL (its validator reads
    any URL-looking answer); everything else is proven by a screenshot.

    Returned as a field dict (the same shape as EngagementCustomField.to_dict) so
    it flows through the normal field-collection path. It is not a DB row."""
    if getattr(spec, "verification_mode", None) == "link":
        return {"key": "proof_url", "label": "Proof link", "field_type": "url",
                "required": True, "example": None}
    return {"key": "proof_screenshot", "label": "Proof screenshot",
            "field_type": "screenshot", "required": True, "example": None}


async def _ask_field(message, field, *, error=None):
    label = html.escape(field["label"])
    hint = {
        "screenshot": "📷 Please upload a screenshot (photo).",
        "url": "🔗 Please submit the link.",
        "wallet": "Please submit your wallet address.",
        "uid": "Please submit your UID.",
        "tx_hash": "Please submit the transaction hash.",
        "username": "Please submit your username / handle.",
    }.get(field["field_type"], "Please type your answer.")
    lines = []
    if error:
        lines.append(f"⚠️ {html.escape(error)}")
    lines.append(f"<b>{label}</b>")
    lines.append(hint)
    example = (field.get("example") or "").strip()
    if example:
        lines.append(f"<i>Example: {html.escape(example)}</i>")
    if not field.get("required", True):
        lines.append("(optional — send “-” to skip)")
    await message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_cancel_keyboard(),
    )


# ── Per-action verify flow (Engagement V3) ────────────────────────────────────
# X raids / X social-tasks: the member does each action (Like/Repost/Comment/
# Quote/Follow) in the DM and taps Verify per action. Likes auto-accept; the rest
# verify live (paid owner) or go to manual review (free owner). The X handle is
# asked ONCE and reused (engagement.get_social_handle / set_social_handle).

_ACTION_META = {
    "like":    ("👍", "Like"),
    "retweet": ("🔁", "Repost"),
    "comment": ("💬", "Comment"),
    "quote":   ("🗨️", "Quote"),
    "follow":  ("➕", "Follow"),
}
_ACTION_VERIFY_LABEL = {
    "verified": "✅ Done",
    "manual": "🕒 In review",
    "failed": "🔁 Verify again",
}


def _action_link(campaign, action):
    """The URL the action button opens — X Web Intent where one exists (so the
    repost/quote/follow dialog pops), else the tweet itself (like/comment)."""
    from urllib.parse import quote
    from . import twitter_verify as _tv
    url = campaign.task_url or ""
    tweet_id = _tv.extract_tweet_id(url)
    if action == "retweet" and tweet_id:
        return f"https://x.com/intent/retweet?tweet_id={tweet_id}"
    if action == "quote" and url:
        return f"https://x.com/intent/tweet?url={quote(url, safe='')}"
    if action == "follow":
        target = _tv.normalize_handle((campaign.settings or {}).get("raid_follow_target")) \
            or _tv.extract_author_handle(url)
        if target:
            return f"https://x.com/intent/follow?screen_name={target}"
    return url or "https://x.com"


def _action_panel(campaign, user_id, handle):
    """Return (html_text, InlineKeyboardMarkup) for the DM action panel."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from . import engagement as eng

    status_map = eng.action_status_map(campaign, user_id)
    lines = [
        f"🚀 <b>{html.escape(campaign.title or '')}</b>",
        "",
        f"Verifying as <b>@{html.escape(handle)}</b>",
        "",
        "Do each action, then tap <b>Verify</b> next to it:",
    ]
    rows = []
    for _gk, action, _target in eng.campaign_action_goals(campaign):
        emoji, label = _ACTION_META.get(action, ("•", action.title()))
        st = status_map.get(action)
        verify_label = _ACTION_VERIFY_LABEL.get(st, "✅ Verify")
        rows.append([
            InlineKeyboardButton(f"{emoji} {label}", url=_action_link(campaign, action)),
            InlineKeyboardButton(verify_label, callback_data=f"engv_{campaign.id}_{action}"),
        ])
    rows.append([InlineKeyboardButton("✏️ Change @username", callback_data=f"engh_{campaign.id}")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def _begin_action_flow(msg, context, campaign, *, user, lineage, bot_id):
    """Entry to the per-action flow: ensure we have the user's X handle (ask once),
    then show the action panel."""
    from . import engagement as eng
    if not campaign.is_open:
        await msg.reply_text("This campaign is closed. The submission window has ended.")
        return
    handle = eng.get_social_handle(user.id, "x")
    if not handle:
        context.user_data["eng_handle"] = {"cid": campaign.id, "lineage": lineage, "bot_id": bot_id}
        await msg.reply_text(
            "First, what's your X (Twitter) <b>@username</b>? "
            "We'll remember it so you won't be asked again.",
            parse_mode="HTML", reply_markup=_cancel_keyboard(),
        )
        return
    text, kb = _action_panel(campaign, user.id, handle)
    await msg.reply_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


# ── Entry: /start eng_<id>  and  /start engmy_<id> ────────────────────────────

async def on_start(update, context, payload, *, flask_app, lineage, bot_id=None):
    """Handle an `eng_*` deep-link. Returns True if it consumed the update."""
    if not payload or not (
        payload.startswith("eng_") or payload.startswith("engmy_") or payload.startswith("englb_")
    ):
        return False
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return False

    is_my = payload.startswith("engmy_")
    is_lb = payload.startswith("englb_")
    prefix = "englb_" if is_lb else ("engmy_" if is_my else "eng_")
    try:
        campaign_id = int(payload[len(prefix):])
    except (TypeError, ValueError):
        return False

    with flask_app.app_context():
        campaign = _load_campaign(campaign_id, lineage, bot_id)
        if not campaign:
            await msg.reply_text("This campaign is no longer available.")
            return True

        if is_lb:
            from . import engagement as eng
            try:
                lb = eng.campaign_leaderboard(campaign, limit=10, require_visible=True,
                                              highlight_user_id=user.id)
            except eng.EngagementError:
                await msg.reply_text("The leaderboard isn’t available for this campaign.")
                return True
            await msg.reply_text(
                _render_leaderboard(campaign, lb),
                parse_mode="HTML", disable_web_page_preview=True,
            )
            return True

        if is_my:
            if campaign.tasks.count() > 0:
                await msg.reply_text(
                    _render_my_status_multi(campaign, user.id),
                    parse_mode="HTML", disable_web_page_preview=True,
                )
                return True
            sub = _existing_submission(campaign_id, user.id)
            if not sub:
                await msg.reply_text("You haven’t submitted to this campaign yet.")
            else:
                await msg.reply_text(
                    _render_my_submission(campaign, sub),
                    parse_mode="HTML", disable_web_page_preview=True,
                )
            return True

        # ── Begin participation ──
        if not campaign.is_open:
            await msg.reply_text("This campaign is closed. The submission window has ended.")
            return True

        # Multi-task → show a task picker; the chosen task is handled in on_callback.
        if campaign.tasks.count() > 0:
            done = _completed_task_ids(campaign.id, user.id)
            await msg.reply_text(
                f"🚀 <b>{html.escape(campaign.title or '')}</b>\nChoose a task to complete:",
                parse_mode="HTML", reply_markup=_task_picker(campaign, done),
            )
            return True

        # X raid / X social-task with targets → per-action DM verify flow.
        from . import engagement as eng
        if eng.has_action_flow(campaign):
            await _begin_action_flow(msg, context, campaign,
                                     user=user, lineage=lineage, bot_id=bot_id)
            return True

        await _begin_task(msg, context, campaign, campaign, None,
                          user=user, lineage=lineage, bot_id=bot_id, flask_app=flask_app)
    return True


async def _begin_task(msg, context, campaign, spec, task_id, *, user, lineage, bot_id, flask_app):
    """Shared 'start collecting proof for this task' flow. `spec` is the campaign
    (single-task) or an EngagementTask (multi-task); task_id mirrors it. Applies
    the anti-spam cooldown, one-per-(campaign,task,user) guard, optional membership
    gate, and auto-verify, then either finalizes (no fields) or starts field
    collection with the spec's fields/platform."""
    # Anti-spam cooldown between rapid taps.
    _ck = (lineage, user.id)
    _now = time.monotonic()
    if _now - _last_participate.get(_ck, 0) < _PARTICIPATE_COOLDOWN:
        await msg.reply_text("Please wait a moment before trying again.")
        return
    _last_participate[_ck] = _now

    if campaign.one_per_user:
        existing = _existing_submission(campaign.id, user.id, task_id)
        allow_resubmit = bool((campaign.settings or {}).get("allow_resubmit"))
        if existing and not (existing.status == "rejected" and allow_resubmit):
            await msg.reply_text(
                _render_my_submission(campaign, existing),
                parse_mode="HTML", disable_web_page_preview=True,
            )
            return

    # Optional membership gate (anti-farming): must be a real member first.
    if (campaign.settings or {}).get("require_membership") and spec.verification_mode != "auto":
        from .engagement_verify import verify_telegram_join
        if not await verify_telegram_join(context.bot, _verify_chat_ref(campaign, lineage, spec), user.id):
            await msg.reply_text("Please join the group/channel first, then tap the button again.")
            return

    fields = [f.to_dict() for f in spec.custom_fields.all()]
    title = html.escape(spec.title or campaign.title or "")

    # ── Auto-verify: Telegram channel/group join ─────────────────────────
    force_verified = False
    if spec.verification_mode == "auto":
        from .engagement_verify import verify_telegram_join
        chat_ref = _verify_chat_ref(campaign, lineage, spec)
        ok = await verify_telegram_join(context.bot, chat_ref, user.id)
        if not ok:
            target = chat_ref if isinstance(chat_ref, str) and chat_ref.startswith("@") else "the required channel/group"
            await msg.reply_text(
                f"You don’t appear to be a member yet. Please join {html.escape(str(target))}, "
                "then tap the button again."
            )
            return
        force_verified = True

    if not fields:
        # Auto-verify (passed above) and honor-based tasks are legitimately
        # one-tap → finalize straight away.
        if force_verified or spec.verification_mode == "honor":
            await _finalize(msg, context, flask_app, campaign.id, {}, None, None,
                            user=user, lineage=lineage, bot_id=bot_id,
                            forced_status="verified" if force_verified else None,
                            task_id=task_id)
            return
        # Manual / screenshot / link review with NO configured proof fields would
        # otherwise create an empty "under review" submission with nothing to
        # review. Collect one sensible default proof so the admin (or the link
        # checker) has something real to act on.
        fields = [_default_proof_field(spec)]

    # Start field-by-field collection.
    context.user_data["eng"] = {
        "cid": campaign.id, "task_id": task_id, "fields": fields, "idx": 0,
        "answers": {}, "file_id": None, "file_hash": None,
        "lineage": lineage, "bot_id": bot_id,
        "force_verified": force_verified,
        "platform": spec.platform,
    }
    intro = f"🚀 <b>{title}</b>\nLet’s collect your submission. {len(fields)} step(s)."
    await msg.reply_text(intro, parse_mode="HTML")
    await _ask_field(msg, fields[0])


def _render_my_status_multi(campaign, telegram_user_id):
    """Per-task progress summary for a multi-task campaign."""
    from .models import EngagementSubmission
    subs = {}
    for s in EngagementSubmission.query.filter_by(
        campaign_id=campaign.id, telegram_user_id=str(telegram_user_id)
    ).order_by(EngagementSubmission.created_at.asc()).all():
        subs[s.task_id] = s
    lines = [f"📋 <b>Your progress — {html.escape(campaign.title or '')}</b>"]
    for t in campaign.tasks.all():
        s = subs.get(t.id)
        status = _STATUS_LINE.get(s.status, s.status) if s else "⬜ Not started"
        lines.append(f"• {html.escape(t.title)} — {status}")
    return "\n".join(lines)


def _verify_chat_ref(campaign, lineage, spec=None):
    """Resolve the chat to check membership in for an auto-verify task/campaign:
    an explicit settings['verify_chat'] (task's, then campaign's), else the
    campaign's own group/channel."""
    explicit = (getattr(spec, "settings", None) or {}).get("verify_chat") if spec is not None else None
    if not explicit:
        explicit = (campaign.settings or {}).get("verify_chat")
    if explicit:
        return explicit
    if lineage == "official":
        try:
            return int(campaign.telegram_group_id)
        except (TypeError, ValueError):
            return campaign.telegram_group_id
    from .models import Group
    grp = Group.query.get(campaign.group_id)
    if not grp:
        return None
    try:
        return int(grp.telegram_group_id)
    except (TypeError, ValueError):
        return grp.telegram_group_id


# ── Private message: collect the current field ────────────────────────────────

async def on_private(update, context, *, flask_app, lineage, bot_id=None):
    """Consume a DM only if a campaign flow is active. Returns True if consumed."""
    # Handle-collection flow (per-action verify): the user is typing their X @username.
    hstate = context.user_data.get("eng_handle")
    if hstate:
        msg = update.effective_message
        user = update.effective_user
        if not msg or not user:
            return False
        from . import engagement as eng
        with flask_app.app_context():
            handle = eng.set_social_handle(user.id, (msg.text or ""), platform="x")
            if not handle:
                await msg.reply_text(
                    "That doesn't look like a username. Please send your X handle, e.g. <code>@yourname</code>.",
                    parse_mode="HTML", reply_markup=_cancel_keyboard(),
                )
                return True
            context.user_data.pop("eng_handle", None)
            campaign = _load_campaign(hstate.get("cid"), lineage, bot_id)
            if not campaign:
                await msg.reply_text(f"Saved @{handle}. This campaign is no longer available.")
                return True
            text, kb = _action_panel(campaign, user.id, handle)
            await msg.reply_text(f"Saved <b>@{html.escape(handle)}</b> ✅", parse_mode="HTML")
            await msg.reply_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        return True

    state = context.user_data.get("eng")
    if not state:
        return False
    msg = update.effective_message
    if not msg:
        return False

    fields = state["fields"]
    idx = state["idx"]
    field = fields[idx]
    ftype = field["field_type"]
    required = field.get("required", True)

    value = None
    file_id = None
    file_hash = None

    if ftype == "screenshot":
        if msg.photo:
            photo = msg.photo[-1]
            file_id = photo.file_id
            file_hash = hashlib.sha256((photo.file_unique_id or photo.file_id).encode()).hexdigest()
            value = "[screenshot]"
        else:
            if not required and (msg.text or "").strip() == "-":
                value = ""
            else:
                await msg.reply_text("Please send a screenshot (photo) for this step.",
                                     reply_markup=_cancel_keyboard())
                return True
    else:
        text = (msg.text or "").strip()
        if (not text or text == "-") and not required:
            value = ""
        elif not text:
            await _ask_field(msg, field)
            return True
        else:
            # Validate by field type (reject UID-as-link, wrong-platform URL, …).
            from .engagement_verify import validate_field_value
            platform = state.get("platform")
            ok, normalized, err = validate_field_value(ftype, text, platform=platform)
            if not ok:
                await _ask_field(msg, field, error=err)
                return True
            value = normalized

    state["answers"][field["key"]] = value
    if file_id:
        state["file_id"] = file_id
        state["file_hash"] = file_hash

    idx += 1
    if idx < len(fields):
        state["idx"] = idx
        await _ask_field(msg, fields[idx])
        return True

    # All fields collected → finalize.
    answers = state["answers"]
    f_id = state.get("file_id")
    f_hash = state.get("file_hash")
    forced = "verified" if state.get("force_verified") else None
    task_id = state.get("task_id")
    context.user_data.pop("eng", None)
    with flask_app.app_context():
        await _finalize(msg, context, flask_app, state["cid"], answers, f_id, f_hash,
                        user=update.effective_user, lineage=lineage, bot_id=bot_id,
                        forced_status=forced, task_id=task_id)
    return True


# ── Callbacks (eng_cancel; future inline actions) ─────────────────────────────

async def on_callback(update, context, *, flask_app, lineage, bot_id=None):
    query = update.callback_query
    if not query or not (query.data or "").startswith(("eng_", "engtask_", "engv_", "engh_", "englock_")):
        return False
    data = query.data
    if data == "eng_cancel":
        context.user_data.pop("eng", None)
        context.user_data.pop("eng_handle", None)
        await query.answer("Cancelled")
        try:
            await query.edit_message_text("Submission cancelled.")
        except Exception:
            pass
        return True

    # Change @username → re-collect the handle.
    if data.startswith("engh_"):
        await query.answer()
        try:
            cid = int(data[len("engh_"):])
        except (ValueError, TypeError):
            return True
        context.user_data["eng_handle"] = {"cid": cid, "lineage": lineage, "bot_id": bot_id}
        try:
            await query.message.reply_text(
                "Send your new X (Twitter) <b>@username</b>:",
                parse_mode="HTML", reply_markup=_cancel_keyboard(),
            )
        except Exception:
            pass
        return True

    # Locked sequential task → tell the user to finish the previous one first.
    if data.startswith("englock_"):
        await query.answer("Finish the previous task first 🔒", show_alert=True)
        return True

    # Per-action Verify tap.
    if data.startswith("engv_"):
        await _handle_action_verify(query, context, data, flask_app=flask_app,
                                    lineage=lineage, bot_id=bot_id)
        return True

    # Multi-task picker → begin the chosen task's proof collection.
    if data.startswith("engtask_"):
        await query.answer()
        try:
            _, cid, tid = data.split("_", 2)
            campaign_id, task_id = int(cid), int(tid)
        except (ValueError, TypeError):
            return True
        msg = query.message
        user = query.from_user
        if not msg or not user:
            return True
        with flask_app.app_context():
            from .models import EngagementTask
            campaign = _load_campaign(campaign_id, lineage, bot_id)
            if not campaign:
                await msg.reply_text("This campaign is no longer available.")
                return True
            if not campaign.is_open:
                await msg.reply_text("This campaign is closed. The submission window has ended.")
                return True
            task = EngagementTask.query.filter_by(id=task_id, campaign_id=campaign_id).first()
            if not task:
                await msg.reply_text("That task is no longer available.")
                return True
            await _begin_task(msg, context, campaign, task, task_id,
                              user=user, lineage=lineage, bot_id=bot_id, flask_app=flask_app)
        return True

    await query.answer()
    return True


async def _handle_action_verify(query, context, data, *, flask_app, lineage, bot_id):
    """Verify one action (engv_<cid>_<action>): enforce the golden-period cooldown,
    run/record the check, toast the result, and refresh the panel in place."""
    from . import engagement as eng
    user = query.from_user
    msg = query.message
    if not user or not msg:
        await query.answer()
        return
    try:
        _, cid, action = data.split("_", 2)
        campaign_id = int(cid)
    except (ValueError, TypeError):
        await query.answer()
        return

    with flask_app.app_context():
        campaign = _load_campaign(campaign_id, lineage, bot_id)
        if not campaign:
            await query.answer("This campaign is no longer available.", show_alert=True)
            return
        if not campaign.is_open:
            await query.answer("This campaign is closed.", show_alert=True)
            return

        handle = eng.get_social_handle(user.id, "x")
        if not handle:
            # Shouldn't happen (panel needs a handle), but recover gracefully.
            context.user_data["eng_handle"] = {"cid": campaign_id, "lineage": lineage, "bot_id": bot_id}
            await query.answer()
            await msg.reply_text(
                "First, send your X (Twitter) <b>@username</b>:",
                parse_mode="HTML", reply_markup=_cancel_keyboard(),
            )
            return

        # Already done? Don't re-check (saves API credits).
        if eng.action_status_map(campaign, user.id).get(action) == "verified":
            await query.answer("Already verified ✅")
            return

        wait = eng.action_retry_remaining(campaign, user.id, action)
        if wait > 0:
            await query.answer(f"Please wait {wait}s, then verify again.", show_alert=True)
            return

        result = eng.verify_user_action(
            campaign, telegram_user_id=user.id, telegram_username=user.username,
            action=action, handle=handle,
        )
        status = result["status"]
        if status == "verified":
            await query.answer("Verified ✅")
        elif status == "manual":
            await query.answer("Submitted for review 🕒")
        else:
            await query.answer(result.get("detail") or "Couldn't detect it — try again shortly.",
                               show_alert=True)

        # Refresh the panel so the button labels reflect the new state.
        try:
            text, kb = _action_panel(campaign, user.id, handle)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb,
                                          disable_web_page_preview=True)
        except Exception:
            pass

        if result.get("completed"):
            footer = _promo_footer(campaign, lineage, str(user.id))
            reward = campaign.reward_xp
            bonus = f" +{reward} XP" if reward else ""
            await msg.reply_text(
                f"🎉 All done!{bonus} Thanks for taking part.{footer}",
                parse_mode="HTML", disable_web_page_preview=True,
            )


# ── Finalize: create the submission + reply ───────────────────────────────────

async def _finalize(message, context, flask_app, campaign_id, answers, file_id, file_hash,
                    *, user, lineage, bot_id=None, forced_status=None, task_id=None):
    """Create the EngagementSubmission (via the shared service) and reply with
    status. Assumes an app context is active OR creates one."""
    from .models import EngagementCampaign
    from . import engagement as eng

    def _do():
        campaign = EngagementCampaign.query.get(campaign_id)
        if not campaign:
            return None, "This campaign is no longer available."
        sub, error = eng.create_submission(
            campaign,
            telegram_user_id=user.id,
            telegram_username=user.username,
            answers=answers,
            file_id=file_id,
            file_hash=file_hash,
            forced_status=forced_status,
            task_id=task_id,
        )
        if error:
            return None, error
        return (campaign, sub), None

    # Run within an app context (caller may already be in one).
    try:
        result, err = _do()
    except RuntimeError:
        with flask_app.app_context():
            result, err = _do()

    if err:
        await message.reply_text(err)
        return
    campaign, sub = result
    # The credited reward is the task's (multi-task) or the campaign's.
    reward = campaign.reward_xp
    if sub.task_id:
        from .models import EngagementTask
        t = EngagementTask.query.get(sub.task_id)
        reward = t.reward_xp if t else 0
    footer = _promo_footer(campaign, lineage, str(user.id))
    if sub.status == "verified":
        bonus = f" +{reward} XP added." if reward else ""
        await message.reply_text(f"✅ Verified!{bonus} Thanks for taking part.{footer}",
                                 parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.reply_text(
            f"✅ Submission received. Your proof is now under review.{footer}",
            parse_mode="HTML", disable_web_page_preview=True)
