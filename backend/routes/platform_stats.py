"""Public platform stats — no auth required. Powers the landing page live counters."""
from datetime import datetime, timedelta
from flask import Blueprint, jsonify
from sqlalchemy import func
from ..models import db, TelegramGroup, OfficialMember, BotEvent, AutoReplyLog, Bot
from ..middleware.rate_limit import rate_limit

platform_stats_bp = Blueprint("platform_stats", __name__)


@platform_stats_bp.route("/api/platform/config", methods=["GET"])
@rate_limit(requests_per_minute=120)
def get_public_platform_config():
    """Public (unauthenticated) platform config: branding, links, localization,
    maintenance status and public feature flags. Never returns secrets."""
    from .. import platform_config as pc
    return jsonify(pc.public_config())

MOD_EVENT_TYPES = {
    "ban", "mute", "warn", "kick", "delete_message",
    "spam_removed", "link_removed", "flood_muted",
}


@platform_stats_bp.route("/api/platform-stats", methods=["GET"])
@rate_limit(requests_per_minute=60)
def get_platform_stats():
    """Return aggregate platform stats for the public landing page."""
    week_ago = datetime.utcnow() - timedelta(days=7)

    # Official bot groups (Telegizer shared bot)
    active_official = TelegramGroup.query.filter(
        TelegramGroup.bot_status == "active",
        TelegramGroup.is_disabled == False,
    ).all()
    official_count = len(active_official)
    official_members = sum(g.member_count or 0 for g in active_official)

    # Custom bots (user-owned bots via Bot model)
    custom_bot_count = db.session.query(func.count(Bot.id)).scalar() or 0

    # Total groups = official + custom bot groups (via Bot → Group relationships)
    from ..models import Group
    custom_group_count = db.session.query(func.count(Group.id)).scalar() or 0
    custom_member_count = db.session.query(func.coalesce(func.sum(Group.member_count), 0)).scalar() or 0

    total_groups = official_count + custom_group_count
    total_members = official_members + custom_member_count

    # Moderation actions across ALL event sources
    mod_actions = db.session.query(func.count(BotEvent.id)).filter(
        BotEvent.event_type.in_(MOD_EVENT_TYPES),
    ).scalar() or 0

    # AI replies across all groups
    ai_replies = db.session.query(func.count(AutoReplyLog.id)).scalar() or 0

    # New members tracked in last 7 days (OfficialMember joins)
    new_members_week = db.session.query(func.count(OfficialMember.id)).filter(
        OfficialMember.joined_at >= week_ago,
    ).scalar() or 0

    # New official groups added this week
    new_groups_this_week = TelegramGroup.query.filter(
        TelegramGroup.bot_status == "active",
        TelegramGroup.is_disabled == False,
        TelegramGroup.linked_at >= week_ago,
    ).count()

    return jsonify({
        "total_groups": total_groups,
        "official_groups": official_count,
        "custom_bots": custom_bot_count,
        "total_members": total_members,
        "total_mod_actions": mod_actions,
        "total_ai_replies": ai_replies,
        "new_members_this_week": new_members_week,
        "new_groups_this_week": new_groups_this_week,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    })
