import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..models import db, User, Referral, REFERRAL_MILESTONES
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

referrals_bp = Blueprint("referrals", __name__, url_prefix="/api/referrals")


def _get_user():
    return User.query.get(int(get_jwt_identity()))


def _apply_referral_rewards(referrer: User):
    """Check referral milestones and award Pro days for any newly crossed thresholds."""
    total = Referral.query.filter_by(referrer_user_id=referrer.id).count()

    for required, reward_days in REFERRAL_MILESTONES:
        if total < required:
            break

        # Check if this milestone was already rewarded by looking at any referral row
        already_given = db.session.query(
            db.exists().where(
                Referral.referrer_user_id == referrer.id,
                Referral.rewards_given.contains([required])
            )
        ).scalar()

        if already_given:
            continue

        # Award reward_days of Pro
        now = datetime.utcnow()
        if referrer.subscription_tier == "free" or referrer.subscription_expires is None:
            referrer.subscription_tier = "pro"
            referrer.subscription_expires = now + timedelta(days=reward_days)
        else:
            # Extend existing subscription
            base = max(referrer.subscription_expires, now)
            referrer.subscription_expires = base + timedelta(days=reward_days)
            if referrer.subscription_tier == "free":
                referrer.subscription_tier = "pro"

        # Mark this milestone as rewarded on the most-recent referral row
        last_ref = Referral.query.filter_by(referrer_user_id=referrer.id).order_by(
            Referral.created_at.desc()
        ).first()
        if last_ref:
            given = list(last_ref.rewards_given or [])
            given.append(required)
            last_ref.rewards_given = given

        logger.info(
            f"[REFERRAL] Milestone {required} reached for user {referrer.id} "
            f"— awarded {reward_days} days Pro"
        )

    db.session.commit()


@referrals_bp.route("/stats", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_stats():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Ensure the user has a referral code
    user.get_or_create_referral_code()
    db.session.commit()

    total = Referral.query.filter_by(referrer_user_id=user.id).count()

    # Milestone progress
    milestones = []
    for required, reward_days in REFERRAL_MILESTONES:
        already_given = db.session.query(
            db.exists().where(
                Referral.referrer_user_id == user.id,
                Referral.rewards_given.contains([required])
            )
        ).scalar()
        milestones.append({
            "required": required,
            "reward_days": reward_days,
            "reached": total >= required,
            "rewarded": bool(already_given),
        })

    return jsonify({
        "referral_code": user.referral_code,
        "total_referrals": total,
        "milestones": milestones,
    })


@referrals_bp.route("/leaderboard", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def leaderboard():
    """Monthly top referrers leaderboard with current user rank."""
    current_user_id = int(get_jwt_identity())
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    rows = (
        db.session.query(Referral.referrer_user_id, func.count(Referral.id).label("cnt"))
        .filter(Referral.created_at >= start_of_month)
        .group_by(Referral.referrer_user_id)
        .order_by(func.count(Referral.id).desc())
        .limit(10)
        .all()
    )

    board = []
    current_rank = None
    for rank, (referrer_id, cnt) in enumerate(rows, start=1):
        u = User.query.get(referrer_id)
        if not u:
            continue
        name = u.full_name
        if len(name) > 18:
            name = name[:17] + "…"
        entry = {
            "rank": rank,
            "name": name,
            "referrals": cnt,
            "is_current_user": referrer_id == current_user_id,
        }
        board.append(entry)
        if referrer_id == current_user_id:
            current_rank = rank

    # Current user's monthly count (even if not in top 10)
    current_user_count = (
        db.session.query(func.count(Referral.id))
        .filter(Referral.referrer_user_id == current_user_id,
                Referral.created_at >= start_of_month)
        .scalar() or 0
    )

    return jsonify({
        "leaderboard": board,
        "current_user_rank": current_rank,
        "current_user_count": current_user_count,
        "month": now.strftime("%B %Y"),
    })


@referrals_bp.route("/apply-rewards", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def apply_rewards():
    """Manually trigger reward check — called automatically after register but also available via UI."""
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _apply_referral_rewards(user)
    return jsonify({"status": "ok"})
