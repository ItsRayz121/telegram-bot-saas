from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, Member
from ..config import Config
from ..middleware.rate_limit import rate_limit

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


def admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        if user.email not in Config.ADMIN_EMAILS:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/users", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=60)
def list_users():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    search = request.args.get("search", "")
    query = User.query
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) |
            (User.full_name.ilike(f"%{search}%"))
        )
    query = query.order_by(User.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "users": [u.to_dict() for u in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
        "per_page": per_page,
    })


@admin_bp.route("/users/<int:user_id>", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=60)
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user_data = user.to_dict()
    user_data["bots"] = [b.to_dict() for b in user.bots]
    return jsonify({"user": user_data})


@admin_bp.route("/users/<int:user_id>/subscription", methods=["PUT"])
@admin_required
@rate_limit(requests_per_minute=30)
def update_subscription(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json()
    tier = data.get("tier")
    if tier not in ("free", "pro", "enterprise"):
        return jsonify({"error": "Invalid tier"}), 400
    user.subscription_tier = tier
    if tier == "free":
        user.subscription_expires = None
    else:
        expires_str = data.get("expires")
        if expires_str:
            try:
                user.subscription_expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid expires format"}), 400
    db.session.commit()
    return jsonify({"user": user.to_dict(), "message": "Subscription updated"})


@admin_bp.route("/users/<int:user_id>/ban", methods=["POST"])
@admin_required
@rate_limit(requests_per_minute=30)
def ban_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.email in Config.ADMIN_EMAILS:
        return jsonify({"error": "Cannot ban an admin"}), 403
    data = request.get_json() or {}
    user.is_banned = True
    user.ban_reason = data.get("reason", "Violation of terms of service")
    db.session.commit()
    return jsonify({"message": "User banned", "user": user.to_dict()})


@admin_bp.route("/users/<int:user_id>/unban", methods=["POST"])
@admin_required
@rate_limit(requests_per_minute=30)
def unban_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.is_banned = False
    user.ban_reason = None
    db.session.commit()
    return jsonify({"message": "User unbanned", "user": user.to_dict()})


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
@rate_limit(requests_per_minute=10)
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.email in Config.ADMIN_EMAILS:
        return jsonify({"error": "Cannot delete an admin"}), 403
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted"})


@admin_bp.route("/stats", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=30)
def get_stats():
    total_users = User.query.count()
    total_bots = Bot.query.count()
    total_groups = Group.query.count()
    total_members = Member.query.count()
    active_bots = Bot.query.filter_by(is_active=True).count()
    free_users = User.query.filter_by(subscription_tier="free").count()
    pro_users = User.query.filter_by(subscription_tier="pro").count()
    enterprise_users = User.query.filter_by(subscription_tier="enterprise").count()
    banned_users = User.query.filter_by(is_banned=True).count()
    return jsonify({
        "stats": {
            "total_users": total_users,
            "free_users": free_users,
            "pro_users": pro_users,
            "enterprise_users": enterprise_users,
            "banned_users": banned_users,
            "total_bots": total_bots,
            "active_bots": active_bots,
            "total_groups": total_groups,
            "total_members": total_members,
        }
    })


@admin_bp.route("/my-plan", methods=["PUT"])
@admin_required
@rate_limit(requests_per_minute=30)
def set_own_plan():
    """Allow admin/developer to freely switch their own subscription plan."""
    user = _get_current_user()
    data = request.get_json()
    tier = data.get("tier")
    if tier not in ("free", "pro", "enterprise"):
        return jsonify({"error": "Invalid tier. Must be free, pro, or enterprise"}), 400
    user.subscription_tier = tier
    user.subscription_expires = None
    db.session.commit()
    return jsonify({"user": user.to_dict(), "message": f"Plan switched to {tier}"}), 200


@admin_bp.route("/bots", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=30)
def list_all_bots():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    query = Bot.query.order_by(Bot.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    bots_data = []
    for bot in paginated.items:
        bd = bot.to_dict()
        bd["owner_email"] = bot.owner.email if bot.owner else None
        bots_data.append(bd)
    return jsonify({
        "bots": bots_data,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
        "per_page": per_page,
    })
