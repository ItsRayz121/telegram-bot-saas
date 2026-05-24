"""Custom-bot group CRM routes — mirrors /api/crm/* but targets the Member model."""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, Member
from ..middleware.rate_limit import rate_limit

custom_bot_crm_bp = Blueprint("custom_bot_crm", __name__)

CRM_TAGS = ["VIP", "Lead", "Partner", "Ambassador", "At Risk", "Inactive", "Spammer", "New"]


def _get_current_user():
    return User.query.get(int(get_jwt_identity()))


def _get_bot_and_group(user, bot_id, group_id):
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return None, None, (jsonify({"error": "Bot not found"}), 404)
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    if not group:
        return bot, None, (jsonify({"error": "Group not found"}), 404)
    return bot, group, None


# ── Member list ────────────────────────────────────────────────────────────────

@custom_bot_crm_bp.route("/api/bots/<int:bot_id>/groups/<int:group_id>/crm/members", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_members(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err

    q = Member.query.filter_by(group_id=group.id)

    tag = request.args.get("tag")
    if tag:
        q = q.filter(
            Member.crm_tags.isnot(None),
            Member.crm_tags.contains([tag])
        )

    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search}%"
        q = q.filter(
            db.or_(
                Member.username.ilike(like),
                Member.first_name.ilike(like),
            )
        )

    is_verified = request.args.get("is_verified")
    if is_verified:
        q = q.filter(Member.is_verified == (is_verified.lower() == "true"))

    has_warnings = request.args.get("has_warnings")
    if has_warnings and has_warnings.lower() == "true":
        q = q.filter(Member.warnings > 0)

    period = request.args.get("period")
    if period and period != "all":
        days_map = {"7d": 7, "30d": 30, "90d": 90}
        days = days_map.get(period)
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            q = q.filter(Member.joined_at >= cutoff)

    min_score = request.args.get("min_score", type=int)
    if min_score is not None:
        q = q.filter(Member.engagement_score >= min_score)

    sort = request.args.get("sort", "score")
    if sort == "messages" or sort == "xp":
        q = q.order_by(Member.xp.desc())
    elif sort == "joined":
        q = q.order_by(Member.joined_at.desc())
    elif sort == "warnings":
        q = q.order_by(Member.warnings.desc())
    else:
        q = q.order_by(Member.engagement_score.desc().nullslast())

    page = request.args.get("page", 1, type=int)
    per_page = 25
    total = q.count()
    members = q.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "members": [m.to_dict() for m in members],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "available_tags": CRM_TAGS,
    })


# ── Compute / refresh all scores ──────────────────────────────────────────────

@custom_bot_crm_bp.route("/api/bots/<int:bot_id>/groups/<int:group_id>/crm/compute-scores", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def compute_scores(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err

    members = Member.query.filter_by(group_id=group.id).all()
    for m in members:
        m.engagement_score = m.compute_engagement_score()
    db.session.commit()
    return jsonify({"updated": len(members)})


# ── Individual member update (tags + notes) ───────────────────────────────────

@custom_bot_crm_bp.route("/api/bots/<int:bot_id>/groups/<int:group_id>/crm/members/<user_id>", methods=["PATCH"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def update_member(bot_id, group_id, user_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err

    member = Member.query.filter_by(
        group_id=group.id,
        telegram_user_id=str(user_id),
    ).first_or_404()

    data = request.get_json() or {}

    if "crm_tags" in data:
        member.crm_tags = [t for t in (data["crm_tags"] or []) if t in CRM_TAGS]

    if "crm_notes" in data:
        member.crm_notes = (data["crm_notes"] or "").strip() or None

    member.engagement_score = member.compute_engagement_score()
    db.session.commit()
    return jsonify(member.to_dict())


# ── Single member detail ──────────────────────────────────────────────────────

@custom_bot_crm_bp.route("/api/bots/<int:bot_id>/groups/<int:group_id>/crm/members/<user_id>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_member(bot_id, group_id, user_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err

    member = Member.query.filter_by(
        group_id=group.id,
        telegram_user_id=str(user_id),
    ).first_or_404()

    return jsonify(member.to_dict())


# ── Group-level CRM overview stats ────────────────────────────────────────────

@custom_bot_crm_bp.route("/api/bots/<int:bot_id>/groups/<int:group_id>/crm/overview", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def overview(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err

    all_members = Member.query.filter_by(group_id=group.id).all()
    total = len(all_members)
    if not total:
        return jsonify({"total": 0, "avg_score": 0, "tag_breakdown": {}, "tier_breakdown": {}})

    scored = [m for m in all_members if m.engagement_score is not None]
    avg_score = round(sum(m.engagement_score for m in scored) / len(scored), 1) if scored else 0

    tiers = {"Champions (80+)": 0, "Active (50–79)": 0, "Casual (20–49)": 0, "Inactive (<20)": 0}
    for m in all_members:
        s = m.engagement_score or 0
        if s >= 80:   tiers["Champions (80+)"] += 1
        elif s >= 50: tiers["Active (50–79)"] += 1
        elif s >= 20: tiers["Casual (20–49)"] += 1
        else:         tiers["Inactive (<20)"] += 1

    tag_counts = {}
    for m in all_members:
        for t in (m.crm_tags or []):
            tag_counts[t] = tag_counts.get(t, 0) + 1

    week_ago = datetime.utcnow() - timedelta(days=7)
    new_this_week = sum(1 for m in all_members if m.joined_at and m.joined_at >= week_ago)

    return jsonify({
        "total": total,
        "avg_score": avg_score,
        "new_this_week": new_this_week,
        "tier_breakdown": tiers,
        "tag_breakdown": tag_counts,
        "scores_computed": len(scored),
    })
