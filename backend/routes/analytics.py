from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from models import db, User, Bot, Group, Member, AuditLog
from config import Config
from middleware.rate_limit import rate_limit

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api")


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


def _compute_analytics(group_ids, days):
    cutoff = datetime.utcnow() - timedelta(days=days)

    member_growth = []
    for i in range(days):
        day = datetime.utcnow() - timedelta(days=days - i - 1)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
        count = Member.query.filter(
            Member.group_id.in_(group_ids),
            Member.joined_at >= day_start,
            Member.joined_at <= day_end,
        ).count()
        member_growth.append({"date": day_start.strftime("%Y-%m-%d"), "new_members": count})

    mod_actions = (
        db.session.query(AuditLog.action_type, func.count(AuditLog.id).label("count"))
        .filter(AuditLog.group_id.in_(group_ids), AuditLog.timestamp >= cutoff)
        .group_by(AuditLog.action_type)
        .all()
    )
    mod_action_data = [{"action": a, "count": c} for a, c in mod_actions]

    top_members = (
        Member.query.filter(Member.group_id.in_(group_ids))
        .order_by(Member.xp.desc())
        .limit(10)
        .all()
    )
    top_members_data = [
        {
            "username": m.username or m.first_name,
            "xp": m.xp,
            "level": m.level,
            "telegram_user_id": m.telegram_user_id,
        }
        for m in top_members
    ]

    level_dist_raw = (
        db.session.query(Member.level, func.count(Member.id).label("count"))
        .filter(Member.group_id.in_(group_ids))
        .group_by(Member.level)
        .order_by(Member.level)
        .all()
    )
    level_dist = [{"level": lvl, "count": cnt} for lvl, cnt in level_dist_raw]

    total_members = Member.query.filter(Member.group_id.in_(group_ids)).count()
    new_members = Member.query.filter(
        Member.group_id.in_(group_ids), Member.joined_at >= cutoff
    ).count()
    total_mod_actions = sum(r["count"] for r in mod_action_data)

    return {
        "member_growth": member_growth,
        "mod_actions": mod_action_data,
        "top_members": top_members_data,
        "level_distribution": level_dist,
        "summary": {
            "total_members": total_members,
            "new_members": new_members,
            "total_mod_actions": total_mod_actions,
        },
    }


@analytics_bp.route("/bots/<int:bot_id>/analytics", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_bot_analytics(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404
    days = min(request.args.get("days", 30, type=int), 90)
    groups = Group.query.filter_by(bot_id=bot.id).all()
    group_ids = [g.id for g in groups]
    if not group_ids:
        return jsonify({
            "analytics": {
                "member_growth": [],
                "mod_actions": [],
                "top_members": [],
                "level_distribution": [],
                "summary": {"total_members": 0, "new_members": 0, "total_mod_actions": 0},
                "total_groups": 0,
            }
        })
    data = _compute_analytics(group_ids, days)
    data["total_groups"] = len(group_ids)
    return jsonify({"analytics": data})


@analytics_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/analytics", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_group_analytics(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    if not group:
        return jsonify({"error": "Group not found"}), 404
    days = min(request.args.get("days", 30, type=int), 90)
    data = _compute_analytics([group.id], days)
    data["group"] = group.to_dict()
    return jsonify({"analytics": data})


@analytics_bp.route("/platform/stats", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def get_platform_stats():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.email not in Config.ADMIN_EMAILS:
        return jsonify({"error": "Admin access required"}), 403
    total_users = User.query.count()
    total_bots = Bot.query.count()
    total_groups = Group.query.count()
    total_members = Member.query.count()
    active_bots = Bot.query.filter_by(is_active=True).count()
    pro_users = User.query.filter_by(subscription_tier="pro").count()
    enterprise_users = User.query.filter_by(subscription_tier="enterprise").count()
    cutoff_30 = datetime.utcnow() - timedelta(days=30)
    new_users_30d = User.query.filter(User.created_at >= cutoff_30).count()
    new_bots_30d = Bot.query.filter(Bot.created_at >= cutoff_30).count()
    return jsonify({
        "stats": {
            "total_users": total_users,
            "total_bots": total_bots,
            "total_groups": total_groups,
            "total_members": total_members,
            "active_bots": active_bots,
            "pro_users": pro_users,
            "enterprise_users": enterprise_users,
            "new_users_30d": new_users_30d,
            "new_bots_30d": new_bots_30d,
        }
    })
