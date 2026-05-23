"""Public platform stats — no auth required. Powers the landing page live counters."""
from datetime import datetime, timedelta
from flask import Blueprint, jsonify
from sqlalchemy import func
from ..models import db, TelegramGroup, OfficialMember, BotEvent, AutoReplyLog
from ..middleware.rate_limit import rate_limit

platform_stats_bp = Blueprint("platform_stats", __name__)

MOD_EVENT_TYPES = {
    "ban", "mute", "warn", "kick", "delete_message",
    "spam_removed", "link_removed", "flood_muted",
}


@platform_stats_bp.route("/api/platform-stats", methods=["GET"])
@rate_limit(max_requests=60, window_seconds=60)
def get_platform_stats():
    """Return aggregate platform stats for the public landing page."""
    active_groups = TelegramGroup.query.filter(
        TelegramGroup.bot_status == "active",
        TelegramGroup.is_disabled == False,
    ).all()

    total_groups = len(active_groups)
    total_members = sum(g.member_count or 0 for g in active_groups)

    mod_actions = db.session.query(func.count(BotEvent.id)).filter(
        BotEvent.event_type.in_(MOD_EVENT_TYPES),
    ).scalar() or 0

    ai_replies = db.session.query(func.count(AutoReplyLog.id)).scalar() or 0

    # Groups added in last 7 days
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_groups_this_week = TelegramGroup.query.filter(
        TelegramGroup.bot_status == "active",
        TelegramGroup.is_disabled == False,
        TelegramGroup.linked_at >= week_ago,
    ).count()

    return jsonify({
        "total_groups": total_groups,
        "total_members": total_members,
        "total_mod_actions": mod_actions,
        "total_ai_replies": ai_replies,
        "new_groups_this_week": new_groups_this_week,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    })
