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

logger = logging.getLogger(__name__)


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


# ── Message helpers ───────────────────────────────────────────────────────────

def _cancel_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton("✖ Cancel", callback_data="eng_cancel")]])


async def _ask_field(message, field):
    label = html.escape(field["label"])
    hint = {
        "screenshot": "📷 Send a screenshot (photo).",
        "url": "🔗 Send the link.",
        "wallet": "Send your wallet address.",
        "uid": "Send your UID.",
        "tx_hash": "Send the transaction hash.",
        "username": "Send your username / handle.",
    }.get(field["field_type"], "Type your answer.")
    suffix = "" if field.get("required", True) else "  (optional — send “-” to skip)"
    await message.reply_text(
        f"<b>{label}</b>\n{hint}{suffix}",
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
                status_line = {
                    "pending": "🟡 Pending admin review",
                    "verified": "✅ Verified",
                    "rejected": "❌ Rejected",
                }.get(sub.status, sub.status)
                extra = f"\nReason: {html.escape(sub.review_reason)}" if sub.review_reason else ""
                await msg.reply_text(
                    f"<b>{html.escape(campaign.title)}</b>\nStatus: {status_line}{extra}",
                    parse_mode="HTML",
                )
            return True

        # ── Begin participation ──
        if not campaign.is_open:
            await msg.reply_text("This campaign is closed. The submission window has ended.")
            return True

        if campaign.one_per_user and _existing_submission(campaign_id, user.id):
            await msg.reply_text("You have already submitted for this task.")
            return True

        fields = _ordered_fields(campaign)
        title = html.escape(campaign.title)

        if not fields:
            # No proof fields → finalize straight away (honor → verified, else pending).
            await _finalize(msg, context, flask_app, campaign_id, {}, None, None,
                            user=user, lineage=lineage, bot_id=bot_id)
            return True

        # Start field-by-field collection.
        context.user_data["eng"] = {
            "cid": campaign_id, "fields": fields, "idx": 0,
            "answers": {}, "file_id": None, "file_hash": None,
            "lineage": lineage, "bot_id": bot_id,
        }
        intro = f"🚀 <b>{title}</b>\nLet’s collect your submission. {len(fields)} step(s)."
        await msg.reply_text(intro, parse_mode="HTML")
        await _ask_field(msg, fields[0])
    return True


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
        if not text and not required:
            value = ""
        elif text == "-" and not required:
            value = ""
        elif not text:
            await _ask_field(msg, field)
            return True
        else:
            value = text

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
    context.user_data.pop("eng", None)
    with flask_app.app_context():
        await _finalize(msg, context, flask_app, state["cid"], answers, f_id, f_hash,
                        user=update.effective_user, lineage=lineage, bot_id=bot_id)
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
                    *, user, lineage, bot_id=None):
    """Create the EngagementSubmission and reply with status. Assumes an app
    context is active OR creates one."""
    from .models import db, EngagementCampaign, EngagementSubmission, OfficialMember
    from . import engagement as eng

    tg_user_id = str(user.id)
    tg_username = user.username

    def _do():
        campaign = EngagementCampaign.query.get(campaign_id)
        if not campaign:
            return None, "This campaign is no longer available."
        if not campaign.is_open:
            return None, "This campaign is closed. The submission window has ended."
        if campaign.one_per_user:
            dupe = EngagementSubmission.query.filter_by(
                campaign_id=campaign_id, telegram_user_id=tg_user_id
            ).first()
            if dupe:
                return None, "You have already submitted for this task."

        member_id = None
        scope = "official" if lineage == "official" else "custom"
        if lineage == "official":
            m = OfficialMember.query.filter_by(
                telegram_group_id=campaign.telegram_group_id,
                telegram_user_id=tg_user_id,
            ).first()
            member_id = m.id if m else None

        status = "verified" if campaign.verification_mode == "honor" else "pending"
        sub = EngagementSubmission(
            campaign_id=campaign_id,
            telegram_user_id=tg_user_id,
            telegram_username=tg_username,
            member_id=member_id,
            scope=scope,
            status=status,
            payload=answers or {},
            file_id=file_id,
            file_hash=file_hash,
        )
        db.session.add(sub)
        db.session.commit()

        if status == "verified":
            eng.award_submission(campaign, sub)

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
    if sub.status == "verified":
        bonus = f" (+{campaign.reward_xp} XP)" if campaign.reward_xp else ""
        await message.reply_text(f"✅ Verified!{bonus} Thanks for taking part.")
    else:
        await message.reply_text("Submitted successfully ✅\nPending admin review.")
