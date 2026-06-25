"""
Assistant Hub — Daily digest builder and delivery.

build_and_deliver_digest(bot_id, user_id, flask_app):
  - Pulls tasks, reminders, decisions, meetings created since last digest
  - Formats compact or detailed text per user's settings
  - Sends via Telegram DM
  - Creates HubDigest record
  - Updates last_delivered_at

Called by the scheduler cron (hub_send_daily_digests) once per day.
"""
import logging
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

_log = logging.getLogger(__name__)


def _fmt_local(dt, tz_name, fmt_str, fallback=""):
    """Format a naive-UTC datetime in the user's timezone for DM display."""
    if not dt:
        return fallback
    try:
        if tz_name and ZoneInfo is not None:
            dt = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name))
    except Exception:
        pass
    return dt.strftime(fmt_str)


def _user_tz(user_id) -> str:
    from ..assistant.hub_models import HubMemoryGlobal
    mg = HubMemoryGlobal.query.filter_by(user_id=user_id).first()
    return (mg.timezone if mg and mg.timezone else "UTC") or "UTC"


def deliver_all_due_digests(flask_app=None) -> int:
    """
    Check every user's official bot settings. If digest is enabled and
    the configured time has passed today with no digest yet sent, build and deliver.
    Returns count of digests sent.
    """
    ctx = flask_app.app_context() if flask_app else None
    if ctx:
        ctx.push()
    try:
        return _deliver_all()
    finally:
        if ctx:
            ctx.pop()


def _deliver_all() -> int:
    from ..assistant.hub_models import HubBotIdentity, HubBotSettings, HubDigest
    from ..models import db
    from ..assistant.hub_settings_resolver import get_effective_settings

    now = datetime.utcnow()
    today = now.date()
    sent = 0

    bots = HubBotIdentity.query.filter_by(bot_type="official", is_active=True).all()
    for bot in bots:
        try:
            settings = get_effective_settings(bot.id)
            if not settings.get("digest_enabled"):
                continue

            digest_time_str = settings.get("digest_time", "21:00") or "21:00"
            parts = str(digest_time_str).split(":")
            digest_hour, digest_min = int(parts[0]), int(parts[1])

            # Only fire if current UTC time >= digest_time today
            if now.hour < digest_hour or (now.hour == digest_hour and now.minute < digest_min):
                continue

            # Check if we already sent today
            already_sent = HubDigest.query.filter(
                HubDigest.bot_id == bot.id,
                HubDigest.user_id == bot.user_id,
                db.func.date(HubDigest.delivered_at) == today,
                HubDigest.delivered_at.isnot(None),
            ).first()
            if already_sent:
                continue

            result = _build_and_deliver(bot.id, bot.user_id, settings)
            if result:
                sent += 1
        except Exception as exc:
            _log.error("hub_digest: failed for bot=%s: %s", bot.id, exc)

    return sent


def build_and_deliver_digest(bot_id: str, user_id: int, flask_app=None) -> bool:
    """Direct call: build and deliver a digest for a specific bot + user."""
    ctx = flask_app.app_context() if flask_app else None
    if ctx:
        ctx.push()
    try:
        from ..assistant.hub_settings_resolver import get_effective_settings
        settings = get_effective_settings(bot_id)
        return _build_and_deliver(bot_id, user_id, settings)
    finally:
        if ctx:
            ctx.pop()


def _build_and_deliver(bot_id: str, user_id: int, settings: dict) -> bool:
    from ..assistant.hub_models import (
        HubTask, HubReminder, HubDecision, HubMeeting, HubDigest,
        HubConnectedGroup,
    )
    from ..models import db, User, UserTelegramAccount

    # Window: since previous digest (up to 25 hours ago to not miss items)
    since = datetime.utcnow() - timedelta(hours=25)

    tasks = HubTask.query.filter(
        HubTask.bot_id == bot_id,
        HubTask.user_id == user_id,
        HubTask.status == "pending",
        HubTask.created_at >= since,
    ).limit(20).all()

    reminders = HubReminder.query.filter(
        HubReminder.bot_id == bot_id,
        HubReminder.user_id == user_id,
        HubReminder.delivered_at.is_(None),
        HubReminder.dismissed_at.is_(None),
        HubReminder.remind_at >= datetime.utcnow(),
        HubReminder.remind_at <= datetime.utcnow() + timedelta(hours=24),
    ).limit(10).all()

    decisions = HubDecision.query.filter(
        HubDecision.bot_id == bot_id,
        HubDecision.user_id == user_id,
        HubDecision.dismissed_at.is_(None),
        HubDecision.created_at >= since,
    ).limit(10).all()

    meetings = HubMeeting.query.filter(
        HubMeeting.bot_id == bot_id,
        HubMeeting.user_id == user_id,
        HubMeeting.dismissed_at.is_(None),
        HubMeeting.scheduled_at >= datetime.utcnow(),
        HubMeeting.scheduled_at <= datetime.utcnow() + timedelta(hours=48),
    ).limit(10).all()

    total_items = len(tasks) + len(reminders) + len(decisions) + len(meetings)
    if total_items == 0:
        return False  # nothing to send

    fmt = settings.get("digest_format", "compact") or "compact"
    text = _format_digest(tasks, reminders, decisions, meetings, fmt, _user_tz(user_id))

    # Find Telegram chat ID
    user = User.query.get(user_id)
    if not user:
        return False
    tg_account = UserTelegramAccount.query.filter_by(user_id=user_id).first()
    tg_id = (tg_account.telegram_user_id if tg_account else None) or getattr(user, "telegram_user_id", None)
    if not tg_id:
        return False

    from .hub_token import resolve_hub_send_token
    bot_token = resolve_hub_send_token(bot_id)
    if not bot_token:
        return False

    from ..telegram_safe import safe_send_message
    if not safe_send_message(bot_token, tg_id, text, parse_mode="Markdown", timeout=15):
        _log.error("hub_digest: Telegram DM failed user=%s", user_id)
        return False

    # Record the digest
    group_ids = list({t.source_group_id for t in tasks + decisions + meetings if t.source_group_id})
    digest = HubDigest(
        user_id=user_id,
        bot_id=bot_id,
        period="daily",
        item_count=total_items,
        groups_included=group_ids,
        delivered_at=datetime.utcnow(),
        delivery_method="telegram_dm",
    )
    db.session.add(digest)
    db.session.commit()
    _log.info("hub_digest: sent digest user=%s items=%d", user_id, total_items)
    return True


def _format_digest(tasks, reminders, decisions, meetings, fmt: str, tz_name: str = "UTC") -> str:
    now = datetime.utcnow()
    today_str = now.strftime("%B %d")
    lines = [f"*📋 Daily Digest — {today_str}*\n"]

    from .hub_crypto import _dec
    if fmt == "compact":
        if tasks:
            lines.append(f"*Tasks ({len(tasks)})*")
            for t in tasks[:5]:
                due = f" · due {t.due_date}" if t.due_date else ""
                assignee = f" ({t.assignee_name})" if t.assignee_name else ""
                lines.append(f"• {_dec(t.title)}{assignee}{due}")
            if len(tasks) > 5:
                lines.append(f"  _+{len(tasks)-5} more_")
            lines.append("")

        if meetings:
            lines.append(f"*Meetings ({len(meetings)})*")
            for m in meetings[:5]:
                when = _fmt_local(m.scheduled_at, tz_name, "%b %d %H:%M", "TBD")
                lines.append(f"• {_dec(m.title) or 'Meeting'} · {when}")
            lines.append("")

        if decisions:
            lines.append(f"*Decisions ({len(decisions)})*")
            for d in decisions[:5]:
                made = f" — {d.made_by}" if d.made_by else ""
                lines.append(f"• {_dec(d.content)[:100]}{made}")
            lines.append("")

        if reminders:
            lines.append(f"*Upcoming Reminders ({len(reminders)})*")
            for r in reminders[:5]:
                when = _fmt_local(r.remind_at, tz_name, "%b %d %H:%M")
                lines.append(f"• {_dec(r.content)[:80]} · {when}")
    else:
        # detailed
        if tasks:
            lines.append(f"*📌 Tasks — {len(tasks)} pending*")
            for t in tasks:
                priority_emoji = {"high": "🔴", "normal": "🟡", "low": "🟢"}.get(t.priority, "·")
                due = f"\n  Due: {t.due_date}" if t.due_date else ""
                assignee = f"\n  Assignee: {t.assignee_name}" if t.assignee_name else ""
                lines.append(f"{priority_emoji} {_dec(t.title)}{assignee}{due}")
            lines.append("")

        if meetings:
            lines.append(f"*📅 Upcoming Meetings — {len(meetings)}*")
            for m in meetings:
                when = _fmt_local(m.scheduled_at, tz_name, "%A %b %d at %H:%M", "TBD")
                participants = f"\n  With: {', '.join(m.participants[:5])}" if m.participants else ""
                lines.append(f"• *{_dec(m.title) or 'Meeting'}* — {when}{participants}")
            lines.append("")

        if decisions:
            lines.append(f"*✅ Decisions — {len(decisions)}*")
            for d in decisions:
                made = f"\n  By: {d.made_by}" if d.made_by else ""
                lines.append(f"• {_dec(d.content)}{made}")
            lines.append("")

        if reminders:
            lines.append(f"*🔔 Upcoming Reminders — {len(reminders)}*")
            for r in reminders:
                when = _fmt_local(r.remind_at, tz_name, "%A %b %d at %H:%M")
                lines.append(f"• {_dec(r.content)}\n  _{when}_")

    return "\n".join(lines).strip()


def deliver_due_reminders(flask_app=None) -> int:
    """
    Cron: check reminders due within next 5 minutes.
    Send Telegram DM and mark delivered_at.
    """
    ctx = flask_app.app_context() if flask_app else None
    if ctx:
        ctx.push()
    try:
        return _deliver_due_reminders()
    finally:
        if ctx:
            ctx.pop()


def _deliver_due_reminders() -> int:
    from ..assistant.hub_models import HubReminder
    from ..models import db, User, UserTelegramAccount
    from .hub_token import resolve_hub_send_token

    now = datetime.utcnow()
    window_end = now + timedelta(minutes=5)

    due = HubReminder.query.filter(
        HubReminder.remind_at <= window_end,
        HubReminder.remind_at > now - timedelta(minutes=10),
        HubReminder.delivered_at.is_(None),
        HubReminder.dismissed_at.is_(None),
    ).all()

    sent = 0

    for reminder in due:
        try:
            user = User.query.get(reminder.user_id)
            if not user:
                continue
            tg_account = UserTelegramAccount.query.filter_by(user_id=reminder.user_id).first()
            tg_id = (tg_account.telegram_user_id if tg_account else None) or getattr(user, "telegram_user_id", None)
            # Reminders are assistant-lineage — send via the reminder's own Hub bot
            # (Echo or a custom assistant bot), never the group-management bot.
            bot_token = resolve_hub_send_token(getattr(reminder, "bot_id", None))
            if not tg_id or not bot_token:
                continue

            from .hub_crypto import _dec
            from ..telegram_safe import safe_send_message
            text = f"🔔 *Reminder*\n{_dec(reminder.content)}"
            safe_send_message(bot_token, tg_id, text, parse_mode="Markdown")
            reminder.delivered_at = datetime.utcnow()
            sent += 1
        except Exception as exc:
            _log.debug("hub_digest: reminder delivery failed id=%s: %s", reminder.id, exc)

    if sent:
        db.session.commit()

    return sent
