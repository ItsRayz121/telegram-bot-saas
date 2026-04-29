"""Community CRM — member engagement scores, tags, and notes."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, OfficialMember, TelegramGroup, User

crm_bp = Blueprint("crm", __name__)

CRM_TAGS = ["VIP", "Lead", "Partner", "Ambassador", "At Risk", "Inactive", "Spammer", "New"]


def _get_user():
    return User.query.get(int(get_jwt_identity()))


def _check_group_owner(user, group_id):
    return TelegramGroup.query.filter_by(
        telegram_group_id=str(group_id), user_id=user.id
    ).first()


# ── Member list ───────────────────────────────────────────────────────────────

@crm_bp.route("/api/crm/<group_id>/members", methods=["GET"])
@jwt_required()
def list_members(group_id):
    user = _get_user()
    if not _check_group_owner(user, group_id):
        return jsonify({"error": "Group not found"}), 404

    q = OfficialMember.query.filter_by(telegram_group_id=str(group_id))

    # Filters
    tag = request.args.get("tag")
    if tag:
        q = q.filter(OfficialMember.crm_tags.contains([tag]))

    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search}%"
        q = q.filter(
            db.or_(
                OfficialMember.username.ilike(like),
                OfficialMember.first_name.ilike(like),
            )
        )

    min_score = request.args.get("min_score", type=int)
    if min_score is not None:
        q = q.filter(OfficialMember.engagement_score >= min_score)

    sort = request.args.get("sort", "score")
    if sort == "messages":
        q = q.order_by(OfficialMember.message_count.desc())
    elif sort == "xp":
        q = q.order_by(OfficialMember.xp.desc())
    elif sort == "joined":
        q = q.order_by(OfficialMember.joined_at.desc())
    elif sort == "warnings":
        q = q.order_by(OfficialMember.warnings.desc())
    else:
        q = q.order_by(OfficialMember.engagement_score.desc().nullslast())

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


# ── Compute / refresh all scores for a group ─────────────────────────────────

@crm_bp.route("/api/crm/<group_id>/compute-scores", methods=["POST"])
@jwt_required()
def compute_scores(group_id):
    user = _get_user()
    if not _check_group_owner(user, group_id):
        return jsonify({"error": "Group not found"}), 404

    members = OfficialMember.query.filter_by(telegram_group_id=str(group_id)).all()
    for m in members:
        m.engagement_score = m.compute_engagement_score()

    db.session.commit()
    return jsonify({"updated": len(members)})


# ── Individual member update (tags + notes) ───────────────────────────────────

@crm_bp.route("/api/crm/<group_id>/members/<user_id>", methods=["PATCH"])
@jwt_required()
def update_member(group_id, user_id):
    user = _get_user()
    if not _check_group_owner(user, group_id):
        return jsonify({"error": "Group not found"}), 404

    member = OfficialMember.query.filter_by(
        telegram_group_id=str(group_id),
        telegram_user_id=str(user_id),
    ).first_or_404()

    data = request.get_json() or {}

    if "crm_tags" in data:
        tags = [t for t in (data["crm_tags"] or []) if t in CRM_TAGS]
        member.crm_tags = tags

    if "crm_notes" in data:
        member.crm_notes = (data["crm_notes"] or "").strip() or None

    # Refresh score on update
    member.engagement_score = member.compute_engagement_score()
    db.session.commit()
    return jsonify(member.to_dict())


# ── Single member detail ──────────────────────────────────────────────────────

@crm_bp.route("/api/crm/<group_id>/members/<user_id>", methods=["GET"])
@jwt_required()
def get_member(group_id, user_id):
    user = _get_user()
    if not _check_group_owner(user, group_id):
        return jsonify({"error": "Group not found"}), 404

    member = OfficialMember.query.filter_by(
        telegram_group_id=str(group_id),
        telegram_user_id=str(user_id),
    ).first_or_404()

    return jsonify(member.to_dict())


# ── Group-level CRM overview stats ────────────────────────────────────────────

@crm_bp.route("/api/crm/<group_id>/overview", methods=["GET"])
@jwt_required()
def overview(group_id):
    user = _get_user()
    if not _check_group_owner(user, group_id):
        return jsonify({"error": "Group not found"}), 404

    from datetime import datetime, timedelta
    all_members = OfficialMember.query.filter_by(telegram_group_id=str(group_id)).all()
    total = len(all_members)
    if not total:
        return jsonify({"total": 0, "avg_score": 0, "tag_breakdown": {}, "tier_breakdown": {}})

    scored = [m for m in all_members if m.engagement_score is not None]
    avg_score = round(sum(m.engagement_score for m in scored) / len(scored), 1) if scored else 0

    # Tier breakdown
    tiers = {"Champions (80+)": 0, "Active (50–79)": 0, "Casual (20–49)": 0, "Inactive (<20)": 0}
    for m in all_members:
        s = m.engagement_score or 0
        if s >= 80:   tiers["Champions (80+)"] += 1
        elif s >= 50: tiers["Active (50–79)"] += 1
        elif s >= 20: tiers["Casual (20–49)"] += 1
        else:         tiers["Inactive (<20)"] += 1

    # Tag breakdown
    tag_counts = {}
    for m in all_members:
        for t in (m.crm_tags or []):
            tag_counts[t] = tag_counts.get(t, 0) + 1

    # Recent joiners (last 7 days)
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
