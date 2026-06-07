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


def _existing_submission(campaign_id, telegram_user_id):
    from .models import EngagementSubmission
    return EngagementSubmission.query.filter_by(
        campaign_id=campaign_id, telegram_user_id=str(telegram_user_id)
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


def _render_my_submission(campaign, sub):
    """A full, readable summary of the participant's own submission."""
    fields = {f.key: f for f in campaign.custom_fields.all()}
    lines = [
        "📋 <b>Your Submission</b>",
        f"Campaign: {html.escape(campaign.title or '')}",
    ]
    payload = sub.payload or {}
    for key, value in payload.items():
        if value in (None, "", "[screenshot]"):
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


# ── Entry: /start eng_<id>  and  /start engmy_<id> ────────────────────────────

async def on_start(update, context, payload, *, flask_app, lineage, bot_id=None):
    """Handle an `eng_*` deep-link. Returns True if it consumed the update."""
    if not payload or not (payload.startswith("eng_") or payload.startswith("engmy_")):
        return False
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return False

    is_my = payload.startswith("engmy_")
    raw_id = payload[len("engmy_"):] if is_my else payload[len("eng_"):]
    try:
        campaign_id = int(raw_id)
    except (TypeError, ValueError):
        return False

    with flask_app.app_context():
        campaign = _load_campaign(campaign_id, lineage, bot_id)
        if not campaign:
            await msg.reply_text("This campaign is no longer available.")
            return True

        if is_my:
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

        # Anti-spam cooldown between rapid taps.
        _ck = (lineage, user.id)
        _now = time.monotonic()
        if _now - _last_participate.get(_ck, 0) < _PARTICIPATE_COOLDOWN:
            await msg.reply_text("Please wait a moment before trying again.")
            return True
        _last_participate[_ck] = _now

        if campaign.one_per_user:
            existing = _existing_submission(campaign_id, user.id)
            allow_resubmit = bool((campaign.settings or {}).get("allow_resubmit"))
            if existing and not (existing.status == "rejected" and allow_resubmit):
                await msg.reply_text(
                    _render_my_submission(campaign, existing),
                    parse_mode="HTML", disable_web_page_preview=True,
                )
                return True

        # Optional membership gate (anti-farming): must be a real member first.
        if (campaign.settings or {}).get("require_membership") and campaign.verification_mode != "auto":
            from .engagement_verify import verify_telegram_join
            if not await verify_telegram_join(context.bot, _verify_chat_ref(campaign, lineage), user.id):
                await msg.reply_text("Please join the group/channel first, then tap the button again.")
                return True

        fields = _ordered_fields(campaign)
        title = html.escape(campaign.title)

        # ── Auto-verify: Telegram channel/group join ─────────────────────────
        force_verified = False
        if campaign.verification_mode == "auto":
            from .engagement_verify import verify_telegram_join
            chat_ref = _verify_chat_ref(campaign, lineage)
            ok = await verify_telegram_join(context.bot, chat_ref, user.id)
            if not ok:
                target = chat_ref if isinstance(chat_ref, str) and chat_ref.startswith("@") else "the required channel/group"
                await msg.reply_text(
                    f"You don’t appear to be a member yet. Please join {html.escape(str(target))}, "
                    "then tap the button again."
                )
                return True
            force_verified = True

        if not fields:
            # No proof fields → finalize straight away.
            await _finalize(msg, context, flask_app, campaign_id, {}, None, None,
                            user=user, lineage=lineage, bot_id=bot_id,
                            forced_status="verified" if force_verified else None)
            return True

        # Start field-by-field collection.
        context.user_data["eng"] = {
            "cid": campaign_id, "fields": fields, "idx": 0,
            "answers": {}, "file_id": None, "file_hash": None,
            "lineage": lineage, "bot_id": bot_id,
            "force_verified": force_verified,
            "platform": campaign.platform,
        }
        intro = f"🚀 <b>{title}</b>\nLet’s collect your submission. {len(fields)} step(s)."
        await msg.reply_text(intro, parse_mode="HTML")
        await _ask_field(msg, fields[0])
    return True


def _verify_chat_ref(campaign, lineage):
    """Resolve the chat to check membership in for an auto-verify campaign:
    an explicit settings['verify_chat'], else the campaign's own group/channel."""
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
    context.user_data.pop("eng", None)
    with flask_app.app_context():
        await _finalize(msg, context, flask_app, state["cid"], answers, f_id, f_hash,
                        user=update.effective_user, lineage=lineage, bot_id=bot_id,
                        forced_status=forced)
    return True


# ── Callbacks (eng_cancel; future inline actions) ─────────────────────────────

async def on_callback(update, context, *, flask_app, lineage, bot_id=None):
    query = update.callback_query
    if not query or not (query.data or "").startswith("eng_"):
        return False
    data = query.data
    if data == "eng_cancel":
        context.user_data.pop("eng", None)
        await query.answer("Cancelled")
        try:
            await query.edit_message_text("Submission cancelled.")
        except Exception:
            pass
        return True
    await query.answer()
    return True


# ── Finalize: create the submission + reply ───────────────────────────────────

async def _finalize(message, context, flask_app, campaign_id, answers, file_id, file_hash,
                    *, user, lineage, bot_id=None, forced_status=None):
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
    footer = _promo_footer(campaign, lineage, str(user.id))
    if sub.status == "verified":
        bonus = f" +{campaign.reward_xp} XP added." if campaign.reward_xp else ""
        await message.reply_text(f"✅ Verified!{bonus} Thanks for taking part.{footer}",
                                 parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.reply_text(
            f"✅ Submission received. Your proof is now under review.{footer}",
            parse_mode="HTML", disable_web_page_preview=True)
