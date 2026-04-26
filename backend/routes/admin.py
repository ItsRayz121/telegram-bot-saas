from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, Member, SuspiciousActivity, Referral, TelegramGroup, CustomBot, BotEvent
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


@admin_bp.route("/suspicious", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=30)
def list_suspicious():
    """Return paginated suspicious activity events for admin review."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    event_type = request.args.get("event_type", "")
    reviewed = request.args.get("reviewed", "")

    query = SuspiciousActivity.query.order_by(SuspiciousActivity.created_at.desc())
    if event_type:
        query = query.filter(SuspiciousActivity.event_type == event_type)
    if reviewed == "true":
        query = query.filter(SuspiciousActivity.reviewed == True)
    elif reviewed == "false":
        query = query.filter(SuspiciousActivity.reviewed == False)

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for evt in paginated.items:
        d = evt.to_dict()
        if evt.user_id:
            u = User.query.get(evt.user_id)
            d["user_email"] = u.email if u else None
        else:
            d["user_email"] = None
        items.append(d)

    return jsonify({
        "events": items,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/suspicious/<int:event_id>/dismiss", methods=["POST"])
@admin_required
@rate_limit(requests_per_minute=30)
def dismiss_suspicious(event_id):
    """Mark a suspicious activity event as reviewed/dismissed."""
    event = SuspiciousActivity.query.get(event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404
    event.reviewed = True
    db.session.commit()
    return jsonify({"message": "Event dismissed", "event": event.to_dict()})


@admin_bp.route("/referrals", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=30)
def list_referrals():
    """Return paginated referral records with status filter for abuse review."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    status = request.args.get("status", "")  # pending|approved|suspicious|rejected

    query = Referral.query.order_by(Referral.created_at.desc())
    if status:
        query = query.filter(Referral.status == status)

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for ref in paginated.items:
        d = ref.to_dict()
        referrer = User.query.get(ref.referrer_user_id)
        referred = User.query.get(ref.referred_user_id)
        d["referrer_email"] = referrer.email if referrer else None
        d["referred_email"] = referred.email if referred else None
        d["referred_email_verified"] = referred.email_verified if referred else None
        items.append(d)

    return jsonify({
        "referrals": items,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/referrals/<int:referral_id>/status", methods=["POST"])
@admin_required
@rate_limit(requests_per_minute=30)
def update_referral_status(referral_id):
    """Manually approve or reject a referral."""
    referral = Referral.query.get(referral_id)
    if not referral:
        return jsonify({"error": "Referral not found"}), 404

    data = request.get_json() or {}
    new_status = data.get("status", "")
    if new_status not in ("approved", "rejected", "suspicious", "pending"):
        return jsonify({"error": "status must be one of: approved, rejected, suspicious, pending"}), 400

    old_status = referral.status
    referral.status = new_status
    db.session.commit()

    # If approving a previously non-approved referral, trigger reward check
    if new_status == "approved" and old_status != "approved":
        try:
            from flask import current_app
            from ..routes.referrals import _apply_referral_rewards
            _app = current_app._get_current_object()
            _referrer_id = referral.referrer_user_id

            import threading

            def _reward():
                try:
                    with _app.app_context():
                        r = User.query.get(_referrer_id)
                        if r:
                            _apply_referral_rewards(r)
                except Exception:
                    pass

            threading.Thread(target=_reward, daemon=True).start()
        except Exception:
            pass

    return jsonify({"message": f"Referral status updated to {new_status}", "referral": referral.to_dict()})


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


# ── Official bot ecosystem admin endpoints ─────────────────────────────────────

@admin_bp.route("/telegram-groups", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=30)
def admin_list_telegram_groups():
    """All linked Telegram groups across all users."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    search = request.args.get("search", "")
    status = request.args.get("status", "")

    query = TelegramGroup.query
    if search:
        query = query.filter(
            TelegramGroup.title.ilike(f"%{search}%") |
            TelegramGroup.telegram_group_id.ilike(f"%{search}%")
        )
    if status:
        query = query.filter(TelegramGroup.bot_status == status)
    query = query.order_by(TelegramGroup.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    result = []
    for tg in paginated.items:
        d = tg.to_dict()
        if tg.owner_user_id:
            owner = User.query.get(tg.owner_user_id)
            d["owner_email"] = owner.email if owner else None
            d["owner_name"] = owner.full_name if owner else None
        else:
            d["owner_email"] = None
            d["owner_name"] = None
        d["command_count"] = len(tg.custom_commands)
        result.append(d)

    return jsonify({
        "groups": result,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/telegram-groups/stats", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=30)
def admin_telegram_group_stats():
    total = TelegramGroup.query.count()
    active = TelegramGroup.query.filter_by(bot_status="active").count()
    pending = TelegramGroup.query.filter_by(bot_status="pending").count()
    removed = TelegramGroup.query.filter_by(bot_status="removed").count()
    disabled = TelegramGroup.query.filter_by(is_disabled=True).count()
    total_custom_bots = CustomBot.query.count()
    total_users_with_groups = db.session.query(
        TelegramGroup.owner_user_id
    ).filter(
        TelegramGroup.owner_user_id.isnot(None)
    ).distinct().count()

    return jsonify({
        "stats": {
            "total_linked_groups": total,
            "active_groups": active,
            "pending_groups": pending,
            "removed_groups": removed,
            "disabled_groups": disabled,
            "total_custom_bots": total_custom_bots,
            "users_using_bot": total_users_with_groups,
        }
    })


@admin_bp.route("/telegram-groups/<group_id>/disable", methods=["POST"])
@admin_required
@rate_limit(requests_per_minute=10)
def admin_disable_group(group_id):
    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
    if not tg:
        return jsonify({"error": "Group not found"}), 404
    tg.is_disabled = True
    tg.bot_status = "disabled"
    db.session.commit()
    return jsonify({"message": "Group disabled", "group": tg.to_dict()})


@admin_bp.route("/telegram-groups/<group_id>/unlink", methods=["POST"])
@admin_required
@rate_limit(requests_per_minute=10)
def admin_unlink_group(group_id):
    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
    if not tg:
        return jsonify({"error": "Group not found"}), 404
    tg.owner_user_id = None
    tg.bot_status = "pending"
    tg.linked_at = None
    db.session.commit()

    ev = BotEvent(
        telegram_group_id=tg.telegram_group_id,
        event_type="admin_unlinked",
        message="Admin force-unlinked group",
    )
    db.session.add(ev)
    db.session.commit()

    return jsonify({"message": "Group unlinked by admin", "group": tg.to_dict()})


@admin_bp.route("/telegram-groups/<group_id>/events", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=30)
def admin_group_events(group_id):
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    paginated = BotEvent.query.filter_by(
        telegram_group_id=group_id
    ).order_by(BotEvent.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        "events": [e.to_dict() for e in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/custom-bots", methods=["GET"])
@admin_required
@rate_limit(requests_per_minute=30)
def admin_list_custom_bots():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    paginated = CustomBot.query.order_by(CustomBot.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    result = []
    for bot in paginated.items:
        d = bot.to_dict()
        owner = User.query.get(bot.owner_user_id)
        d["owner_email"] = owner.email if owner else None
        result.append(d)
    return jsonify({
        "bots": result,
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@admin_bp.route("/custom-bots/<int:bot_id>/disable", methods=["POST"])
@admin_required
@rate_limit(requests_per_minute=10)
def admin_disable_custom_bot(bot_id):
    bot = CustomBot.query.get(bot_id)
    if not bot:
        return jsonify({"error": "Bot not found"}), 404
    bot.status = "inactive"
    db.session.commit()
    return jsonify({"message": "Custom bot disabled", "bot": bot.to_dict()})
