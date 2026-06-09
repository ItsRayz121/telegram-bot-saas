import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..models import db, User, Referral, REFERRAL_MILESTONES
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

referrals_bp = Blueprint("referrals", __name__, url_prefix="/api/referrals")


def _get_user():
    return User.query.get(int(get_jwt_identity()))


def _apply_referral_rewards(referrer: User):
    """Check referral milestones and award Pro days for any newly crossed thresholds.
    Only approved referrals count — pending/suspicious/rejected are excluded.

    A PostgreSQL advisory lock keyed to the referrer's user ID serialises
    concurrent calls so two simultaneous webhooks can never double-award
    the same milestone.
    """
    # Acquire a session-level advisory lock for this referrer.
    # The lock is automatically released at commit/rollback so there is no
    # risk of starving other users.
    try:
        from sqlalchemy import text as _text
        db.session.execute(_text("SELECT pg_advisory_xact_lock(:uid)"), {"uid": referrer.id})
    except Exception:
        pass  # SQLite / unavailable — best-effort, proceeds without lock

    total = Referral.query.filter_by(referrer_user_id=referrer.id, status="approved").count()

    # Load all rewards_given lists for this referrer in one query (Python-side check)
    all_refs = Referral.query.filter_by(referrer_user_id=referrer.id).with_entities(Referral.rewards_given).all()
    rewarded_milestones = set()
    for (rg,) in all_refs:
        for m in (rg or []):
            rewarded_milestones.add(m)

    for required, reward_days in REFERRAL_MILESTONES:
        if total < required:
            break

        if required in rewarded_milestones:
            continue

        # Award reward_days of Pro
        now = datetime.utcnow()
        if referrer.subscription_tier == "free" or referrer.subscription_expires is None:
            referrer.subscription_tier = "pro"
            referrer.subscription_expires = now + timedelta(days=reward_days)
        else:
            base = max(referrer.subscription_expires, now)
            referrer.subscription_expires = base + timedelta(days=reward_days)
            if referrer.subscription_tier == "free":
                referrer.subscription_tier = "pro"

        # Mark this milestone as rewarded — store on the earliest (first) referral
        # row for this referrer, so the marker survives row deletions of later refs.
        first_ref = Referral.query.filter_by(referrer_user_id=referrer.id).order_by(
            Referral.created_at.asc()
        ).first()
        if first_ref:
            given = list(first_ref.rewards_given or [])
            if required not in given:
                given.append(required)
                first_ref.rewards_given = given

        logger.info(
            "[REFERRAL] Milestone %d reached for user %d — awarded %d days Pro",
            required, referrer.id, reward_days,
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

    total_all = Referral.query.filter_by(referrer_user_id=user.id).count()
    # Only approved referrals count toward milestones
    total_approved = Referral.query.filter_by(referrer_user_id=user.id, status="approved").count()

    # Milestone progress — check rewards_given in Python to avoid JSON query issues
    all_refs = Referral.query.filter_by(referrer_user_id=user.id).with_entities(Referral.rewards_given).all()
    rewarded_milestones = set()
    for (rg,) in all_refs:
        for m in (rg or []):
            rewarded_milestones.add(m)

    milestones = []
    for required, reward_days in REFERRAL_MILESTONES:
        milestones.append({
            "required": required,
            "reward_days": reward_days,
            "reached": total_approved >= required,
            "rewarded": required in rewarded_milestones,
        })

    return jsonify({
        "referral_code": user.referral_code,
        "total_referrals": total_all,
        "approved_referrals": total_approved,
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
        .filter(Referral.created_at >= start_of_month, Referral.status == "approved")
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

    # Current user's approved monthly count (even if not in top 10)
    current_user_count = (
        db.session.query(func.count(Referral.id))
        .filter(Referral.referrer_user_id == current_user_id,
                Referral.created_at >= start_of_month,
                Referral.status == "approved")
        .scalar() or 0
    )

    return jsonify({
        "leaderboard": board,
        "current_user_rank": current_rank,
        "current_user_count": current_user_count,
        "month": now.strftime("%B %Y"),
    })


@referrals_bp.route("/lookup", methods=["GET"])
@rate_limit(requests_per_minute=30)
def lookup_referral():
    """Public endpoint: return referrer's first name for a given referral code.
    Never exposes email or other PII. Used by the /join referral landing page."""
    code = (request.args.get("code") or "").strip()
    if not code or len(code) > 32:
        return jsonify({"valid": False}), 200
    referrer = User.query.filter_by(referral_code=code).first()
    if not referrer or referrer.is_banned:
        return jsonify({"valid": False}), 200
    # Return only first name — enough for social proof, no PII leak
    first_name = (referrer.full_name or "").split()[0] if referrer.full_name else "A friend"
    return jsonify({"valid": True, "referrer_first_name": first_name}), 200


@referrals_bp.route("/apply-rewards", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def apply_rewards():
    """Manually trigger reward check — called automatically after register but also available via UI."""
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    from .. import platform_config as _pc
    if not _pc.is_feature_enabled("referrals_enabled"):
        return jsonify({"status": "disabled"}), 200
    _apply_referral_rewards(user)
    return jsonify({"status": "ok"})
