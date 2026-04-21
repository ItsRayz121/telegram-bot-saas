from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, Member, AuditLog, ScheduledMessage, Raid
from ..middleware.rate_limit import rate_limit

settings_bp = Blueprint("settings", __name__, url_prefix="/api")


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


def _get_bot_and_group(user, bot_id, group_id):
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return None, None, (jsonify({"error": "Bot not found"}), 404)
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    if not group:
        return bot, None, (jsonify({"error": "Group not found"}), 404)
    return bot, group, None


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/settings", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_group_settings(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    return jsonify({"settings": group.settings, "group": group.to_dict()})


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/settings", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_group_settings(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    current = group.settings or {}
    current.update(data)
    group.settings = current
    db.session.commit()
    return jsonify({"settings": group.settings, "message": "Settings updated"})


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/members", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_members(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    search = request.args.get("search", "")
    query = Member.query.filter_by(group_id=group.id)
    if search:
        query = query.filter(
            (Member.username.ilike(f"%{search}%")) |
            (Member.first_name.ilike(f"%{search}%"))
        )
    query = query.order_by(Member.xp.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "members": [m.to_dict() for m in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
        "per_page": per_page,
    })


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/audit-logs", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_audit_logs(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    action_type = request.args.get("action_type", "")
    query = AuditLog.query.filter_by(group_id=group.id)
    if action_type:
        query = query.filter_by(action_type=action_type)
    query = query.order_by(AuditLog.timestamp.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "logs": [log.to_dict() for log in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
        "per_page": per_page,
    })


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/scheduled-messages", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_scheduled_messages(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    messages = ScheduledMessage.query.filter_by(group_id=group.id).order_by(ScheduledMessage.send_at).all()
    return jsonify({"scheduled_messages": [m.to_dict() for m in messages]})


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/scheduled-messages", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_scheduled_message(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    required = ["title", "message_text", "send_at"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400
    try:
        send_at = datetime.fromisoformat(data["send_at"].replace("Z", "+00:00"))
    except ValueError:
        return jsonify({"error": "Invalid send_at format"}), 400
    stop_date = None
    if data.get("stop_date"):
        try:
            stop_date = datetime.fromisoformat(data["stop_date"].replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": "Invalid stop_date format"}), 400
    msg = ScheduledMessage(
        group_id=group.id,
        title=data["title"],
        message_text=data["message_text"],
        media_url=data.get("media_url"),
        buttons=data.get("buttons"),
        send_at=send_at,
        repeat_interval=data.get("repeat_interval"),
        stop_date=stop_date,
        pin_message=data.get("pin_message", False),
        auto_delete_after=data.get("auto_delete_after"),
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({"scheduled_message": msg.to_dict(), "message": "Scheduled message created"}), 201


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/raids", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def create_raid(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    if user.subscription_tier == "free":
        return jsonify({"error": "Raids require a Pro or Enterprise subscription"}), 403
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    if not data.get("tweet_url"):
        return jsonify({"error": "tweet_url is required"}), 400
    duration_hours = data.get("duration_hours", 24)
    ends_at = datetime.utcnow().replace(microsecond=0)
    from datetime import timedelta
    ends_at = ends_at + timedelta(hours=duration_hours)
    raid = Raid(
        group_id=group.id,
        tweet_url=data["tweet_url"],
        goals=data.get("goals", {}),
        duration_hours=duration_hours,
        xp_reward=data.get("xp_reward", 100),
        pin_message=data.get("pin_message", True),
        reminders_enabled=data.get("reminders_enabled", True),
        is_active=True,
        ends_at=ends_at,
        participants={},
    )
    db.session.add(raid)
    db.session.commit()
    return jsonify({"raid": raid.to_dict(), "message": "Raid created"}), 201
