"""
Telegram Report Digest — per-group settings, on-demand send, and scheduler helpers.

Digest config is stored inside group.settings["digest"] JSON to avoid a schema change:
{
  "daily": true,
  "weekly": false,
  "monthly": false,
  "last_daily": "2026-04-24T08:00:00",
  "last_weekly": "2026-04-20T08:00:00",
  "last_monthly": "2026-04-01T08:00:00"
}
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..models import db, User, Bot, Group, AuditLog, ScheduledMessage, Poll, Member, InviteLinkJoin
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

digest_bp = Blueprint("digest", __name__, url_prefix="/api/bots/<int:bot_id>/groups/<int:group_id>/digest")

# ── Auth helper ────────────────────────────────────────────────────────────────

def _get_group_or_404(bot_id, group_id):
    user_id = int(get_jwt_identity())
    bot = Bot.query.filter_by(id=bot_id, user_id=user_id).first()
    if not bot:
        return None, None
    group = Group.query.filter_by(id=group_id, bot_id=bot_id).first()
    return bot, group


# ── Report data builder ────────────────────────────────────────────────────────

def _build_report_data(group_id: int, since: datetime) -> dict:
    """Aggregate report metrics for the period starting at `since` (UTC)."""

    # Moderation actions from audit log
    action_counts = (
        db.session.query(AuditLog.action_type, func.count(AuditLog.id))
        .filter(AuditLog.group_id == group_id, AuditLog.timestamp >= since)
        .group_by(AuditLog.action_type)
        .all()
    )
    actions = {a: c for a, c in action_counts}
    spam_removed = actions.get("delete", 0) + actions.get("automod_delete", 0)
    users_warned = actions.get("warn", 0)
    users_banned = actions.get("ban", 0) + actions.get("tempban", 0)
    users_muted = actions.get("mute", 0) + actions.get("tempmute", 0)
    users_kicked = actions.get("kick", 0)

    # Scheduled messages sent
    scheduled_sent = ScheduledMessage.query.filter(
        ScheduledMessage.group_id == group_id,
        ScheduledMessage.is_sent == True,
        ScheduledMessage.send_at >= since,
    ).count()

    # Polls sent
    polls_sent = Poll.query.filter(
        Poll.group_id == group_id,
        Poll.is_sent == True,
        Poll.scheduled_at >= since,
    ).count()

    # Member count now
    member_count = Member.query.filter_by(group_id=group_id).count()

    # New members joined via invite links in period
    invite_joins = (
        db.session.query(func.count(InviteLinkJoin.id))
        .join(InviteLinkJoin.invite_link)
        .filter(
            InviteLinkJoin.joined_at >= since,
        )
        .scalar() or 0
    )

    total_actions = sum(actions.values())

    return {
        "period_start": since.strftime("%Y-%m-%d %H:%M UTC"),
        "spam_removed": spam_removed,
        "users_warned": users_warned,
        "users_banned": users_banned,
        "users_muted": users_muted,
        "users_kicked": users_kicked,
        "total_mod_actions": total_actions,
        "scheduled_sent": scheduled_sent,
        "polls_sent": polls_sent,
        "member_count": member_count,
        "invite_joins": invite_joins,
    }


def _format_report_message(group_name: str, period_label: str, data: dict) -> str:
    lines = [
        f"📊 *{group_name} — {period_label} Report*",
        f"_{data['period_start']}_",
        "",
        "🛡 *Moderation*",
        f"  • Spam removed: {data['spam_removed']}",
        f"  • Users warned: {data['users_warned']}",
        f"  • Users banned: {data['users_banned']}",
        f"  • Users muted: {data['users_muted']}",
        f"  • Users kicked: {data['users_kicked']}",
        f"  • Total actions: {data['total_mod_actions']}",
        "",
        "📅 *Content*",
        f"  • Scheduled posts sent: {data['scheduled_sent']}",
        f"  • Polls/quizzes sent: {data['polls_sent']}",
        "",
        "👥 *Growth*",
        f"  • Members now: {data['member_count']}",
        f"  • Joined via invite links: {data['invite_joins']}",
        "",
        "⚡ Powered by BotForge",
    ]
    return "\n".join(lines)


async def _send_telegram_report(bot_token: str, chat_id: str, text: str):
    import telegram
    bot = telegram.Bot(token=bot_token)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


def _do_send_report(group: Group, bot: Bot, period_label: str, since: datetime):
    """Build and send a report to the Telegram group. Returns True on success."""
    from ..bot_manager import bot_manager as _bm
    try:
        data = _build_report_data(group.id, since)
        text = _format_report_message(group.group_name or "Your Group", period_label, data)
        instance = _bm.active_bots.get(bot.id)
        if instance and instance.loop and instance.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _send_telegram_report(bot.bot_token, group.telegram_group_id, text),
                instance.loop,
            )
            future.result(timeout=15)
        else:
            # Bot not running in memory — send synchronously via a fresh event loop
            asyncio.run(_send_telegram_report(bot.bot_token, group.telegram_group_id, text))
        return True
    except Exception as exc:
        logger.error(f"[DIGEST] Send failed group={group.id}: {exc}")
        return False


# ── Routes ─────────────────────────────────────────────────────────────────────

@digest_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_digest(bot_id, group_id):
    bot, group = _get_group_or_404(bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    digest = (group.settings or {}).get("digest", {})
    return jsonify({
        "digest": {
            "daily": bool(digest.get("daily")),
            "weekly": bool(digest.get("weekly")),
            "monthly": bool(digest.get("monthly")),
            "last_daily": digest.get("last_daily"),
            "last_weekly": digest.get("last_weekly"),
            "last_monthly": digest.get("last_monthly"),
        }
    })


@digest_bp.route("", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def update_digest(bot_id, group_id):
    bot, group = _get_group_or_404(bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    settings = dict(group.settings or {})
    digest = dict(settings.get("digest", {}))

    for key in ("daily", "weekly", "monthly"):
        if key in data:
            digest[key] = bool(data[key])

    settings["digest"] = digest
    group.settings = settings
    db.session.commit()
    return jsonify({"digest": digest})


@digest_bp.route("/send-now", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def send_now(bot_id, group_id):
    bot, group = _get_group_or_404(bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not bot.is_active:
        return jsonify({"error": "Bot is not active"}), 400

    data = request.get_json() or {}
    period = data.get("period", "weekly")  # daily | weekly | monthly

    period_config = {
        "daily":   ("Daily",   timedelta(days=1)),
        "weekly":  ("Weekly",  timedelta(days=7)),
        "monthly": ("Monthly", timedelta(days=30)),
    }
    label, delta = period_config.get(period, ("Weekly", timedelta(days=7)))
    since = datetime.utcnow() - delta

    ok = _do_send_report(group, bot, f"{label} Report", since)
    if not ok:
        return jsonify({"error": "Failed to send report — check that bot is active in the group"}), 502

    # Update last_sent timestamp
    settings = dict(group.settings or {})
    digest = dict(settings.get("digest", {}))
    digest[f"last_{period}"] = datetime.utcnow().isoformat()
    settings["digest"] = digest
    group.settings = settings
    db.session.commit()

    return jsonify({"status": "sent"})


# ── Scheduler helper (called from app.py) ─────────────────────────────────────

def run_digest_scheduler(app):
    """Called every 60 s from _scheduler_loop. Sends due digest reports."""
    now = datetime.utcnow()
    with app.app_context():
        # Find groups that have at least one digest option enabled
        groups = Group.query.all()
        for group in groups:
            digest = (group.settings or {}).get("digest", {})
            if not any([digest.get("daily"), digest.get("weekly"), digest.get("monthly")]):
                continue

            bot = Bot.query.get(group.bot_id)
            if not bot or not bot.is_active:
                continue

            _check_and_send(group, bot, now, "daily",   timedelta(days=1),  timedelta(hours=23))
            _check_and_send(group, bot, now, "weekly",  timedelta(days=7),  timedelta(hours=23))
            _check_and_send(group, bot, now, "monthly", timedelta(days=30), timedelta(hours=23))

            db.session.commit()


def _check_and_send(group, bot, now, key, period_delta, tolerance):
    digest = (group.settings or {}).get("digest", {})
    if not digest.get(key):
        return

    last_key = f"last_{key}"
    last_sent_str = digest.get(last_key)
    if last_sent_str:
        try:
            last_sent = datetime.fromisoformat(last_sent_str)
            if now - last_sent < period_delta - tolerance:
                return
        except Exception:
            pass

    label_map = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}
    ok = _do_send_report(group, bot, f"{label_map[key]} Report", now - period_delta)
    if ok:
        settings = dict(group.settings or {})
        d = dict(settings.get("digest", {}))
        d[last_key] = now.isoformat()
        settings["digest"] = d
        group.settings = settings
        logger.info(f"[DIGEST] Sent {key} report for group {group.id}")
