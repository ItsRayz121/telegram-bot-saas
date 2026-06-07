"""Engagement Campaigns — Telegram publishing (Phase 3).

Posts a premium-looking campaign announcement with inline buttons into the
group, for BOTH bot lineages:
  - official bot → get_official_bot_loop(), chat = telegram_group_id
  - custom bot   → bot_manager.active_bots[group.bot_id], chat = group.telegram_group_id

Best-effort: a failed post never breaks campaign create/update (callers wrap
this, and we also guard internally). Participation buttons are Telegram
deep-links (`?start=eng_<id>`) that open the user's private chat with the bot;
the DM handler that makes them functional is added in Phase 4.
"""

import asyncio
import html
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Button label for the primary "do it" action, by campaign type.
_PRIMARY_LABEL = {
    "proof_collection": "📝 Submit Proof",
    "content_submission": "🔗 Submit Content",
    "social_task": "✅ Verify / Submit",
    "giveaway": "🎉 Participate",
}

_TYPE_EMOJI = {
    "proof_collection": "📝",
    "content_submission": "🎥",
    "social_task": "🔥",
    "giveaway": "🎁",
}


def _status_label(campaign):
    """Human status line for the post."""
    if campaign.status != "active":
        return "🔴 Closed"
    if campaign.ends_at:
        remaining = (campaign.ends_at - datetime.utcnow()).total_seconds()
        if remaining <= 0:
            return "🔴 Closed"
        if remaining <= 6 * 3600:
            return "🟠 Ending soon"
    return "🟢 Active"


def _deadline_text(campaign):
    if not campaign.ends_at:
        return None
    now = datetime.utcnow()
    secs = (campaign.ends_at - now).total_seconds()
    if secs <= 0:
        return "ended"
    hours = secs / 3600
    if hours >= 48:
        return f"{int(hours // 24)} days left"
    if hours >= 1:
        return f"{int(hours)}h left"
    return f"{int(secs // 60)}m left"


def build_campaign_message(campaign, bot_username):
    """Return (html_text, InlineKeyboardMarkup) for the group announcement."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    emoji = _TYPE_EMOJI.get(campaign.type, "🚀")
    lines = [f"{emoji} <b>{html.escape(campaign.title or 'New Task')}</b>", ""]

    if campaign.description:
        lines.append(html.escape(campaign.description))
        lines.append("")

    if campaign.reward_label:
        lines.append(f"🎁 <b>Reward:</b> {html.escape(campaign.reward_label)}")
    if campaign.reward_xp:
        lines.append(f"⭐ <b>XP:</b> {campaign.reward_xp}")

    deadline = _deadline_text(campaign)
    if deadline:
        lines.append(f"⏳ <b>Deadline:</b> {deadline}")

    lines.append(f"📊 <b>Status:</b> {_status_label(campaign)}")
    lines.append("")
    lines.append("Tap below to take part 👇")

    text = "\n".join(lines)

    # ── Buttons ──────────────────────────────────────────────────────────────
    # Deep-links open the user's PRIVATE chat with the bot (proof stays private).
    # Phase 4 wires the `/start eng_<id>` handler that makes these functional.
    rows = []
    if campaign.task_url:
        rows.append([InlineKeyboardButton("🔎 Open Task", url=campaign.task_url)])

    primary = _PRIMARY_LABEL.get(campaign.type, "✅ Participate")
    deep = f"https://t.me/{bot_username}?start=eng_{campaign.id}"
    deep_my = f"https://t.me/{bot_username}?start=engmy_{campaign.id}"
    rows.append([
        InlineKeyboardButton(primary, url=deep),
        InlineKeyboardButton("📋 My Submission", url=deep_my),
    ])

    return text, InlineKeyboardMarkup(rows)


def _resolve_target(campaign):
    """Return (bot, loop, chat_id, bot_username) for the campaign's lineage, or
    (None, None, None, None) if the bot isn't available."""
    if campaign.telegram_group_id:  # official lineage
        from .official_bot import get_official_bot_loop
        from .config import Config
        bot, loop = get_official_bot_loop()
        username = (Config.TELEGRAM_BOT_USERNAME or "telegizer_bot").lstrip("@")
        try:
            chat_id = int(campaign.telegram_group_id)
        except (TypeError, ValueError):
            chat_id = campaign.telegram_group_id
        return bot, loop, chat_id, username

    # custom lineage
    from .models import Group, Bot
    group = Group.query.get(campaign.group_id)
    if not group:
        return None, None, None, None
    from .app import bot_manager
    instance = bot_manager.active_bots.get(group.bot_id)
    if not (instance and instance.application and instance.loop and instance.loop.is_running()):
        return None, None, None, None
    bot_rec = Bot.query.get(group.bot_id)
    username = (bot_rec.bot_username if bot_rec and bot_rec.bot_username else "").lstrip("@")
    try:
        chat_id = int(group.telegram_group_id)
    except (TypeError, ValueError):
        chat_id = group.telegram_group_id
    return instance.application.bot, instance.loop, chat_id, username


def publish_campaign(campaign):
    """Post the campaign to its Telegram group and store telegram_message_id.
    Returns True on success. Never raises (best-effort)."""
    from .models import db

    try:
        bot, loop, chat_id, username = _resolve_target(campaign)
        if not bot or not loop:
            logger.info("publish_campaign: bot offline for campaign %s", campaign.id)
            return False

        text, keyboard = build_campaign_message(campaign, username)
        kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
            "disable_web_page_preview": True,
        }
        if campaign.message_thread_id:
            kwargs["message_thread_id"] = campaign.message_thread_id

        sent = asyncio.run_coroutine_threadsafe(
            bot.send_message(**kwargs), loop
        ).result(timeout=15)

        campaign.telegram_message_id = sent.message_id
        db.session.commit()

        if campaign.pin_message:
            try:
                asyncio.run_coroutine_threadsafe(
                    bot.pin_chat_message(
                        chat_id=chat_id, message_id=sent.message_id,
                        disable_notification=True,
                    ),
                    loop,
                ).result(timeout=10)
            except Exception as e:
                logger.warning("publish_campaign pin failed for %s: %s", campaign.id, e)

        return True
    except Exception:
        logger.exception("publish_campaign failed for campaign %s", getattr(campaign, "id", "?"))
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


def close_campaign_post(campaign):
    """On close: strip the participate buttons, unpin, and post a short results
    summary. All best-effort (bot may be offline in this process)."""
    try:
        bot, loop, chat_id, _ = _resolve_target(campaign)
        if not bot or not loop:
            return False
        if campaign.telegram_message_id:
            for coro in (
                bot.edit_message_reply_markup(chat_id=chat_id, message_id=campaign.telegram_message_id, reply_markup=None),
                bot.unpin_chat_message(chat_id=chat_id, message_id=campaign.telegram_message_id),
            ):
                try:
                    asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=10)
                except Exception:
                    pass
        verified = campaign.submissions.filter_by(status="verified").count()
        total = campaign.submissions.count()
        text = (
            f"🏁 <b>{html.escape(campaign.title or 'Campaign')}</b> has closed.\n"
            f"Submissions: {total}  •  Verified: {verified}"
        )
        kwargs = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if campaign.message_thread_id:
            kwargs["message_thread_id"] = campaign.message_thread_id
        try:
            asyncio.run_coroutine_threadsafe(bot.send_message(**kwargs), loop).result(timeout=10)
        except Exception:
            pass
        return True
    except Exception:
        logger.exception("close_campaign_post failed for %s", getattr(campaign, "id", "?"))
        return False


def send_campaign_reminder(campaign):
    """Post a short 'ending soon' nudge into the group. Best-effort."""
    try:
        bot, loop, chat_id, _ = _resolve_target(campaign)
        if not bot or not loop:
            return False
        deadline = _deadline_text(campaign) or "soon"
        text = f"⏳ <b>{html.escape(campaign.title or 'Campaign')}</b> ends {deadline} — last chance to take part!"
        kwargs = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if campaign.message_thread_id:
            kwargs["message_thread_id"] = campaign.message_thread_id
        asyncio.run_coroutine_threadsafe(bot.send_message(**kwargs), loop).result(timeout=10)
        return True
    except Exception:
        logger.exception("send_campaign_reminder failed for %s", getattr(campaign, "id", "?"))
        return False
