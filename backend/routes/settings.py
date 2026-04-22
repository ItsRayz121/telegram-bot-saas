import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, Member, AuditLog, ScheduledMessage, Raid, AutoResponse, ReportedMessage
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)
settings_bp = Blueprint("settings", __name__, url_prefix="/api")


def _deep_merge(base: dict, override: dict):
    """Recursively merge override into base in-place, preserving nested dicts."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


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
    current = dict(group.settings or {})
    _deep_merge(current, data)
    group.settings = current
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(group, "settings")
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
    try:
        messages = ScheduledMessage.query.filter_by(group_id=group.id).order_by(ScheduledMessage.send_at).all()
        return jsonify({"scheduled_messages": [m.to_dict() for m in messages]})
    except Exception as e:
        logger.error(f"get_scheduled_messages error for group {group_id}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to load scheduled messages: {str(e)}"}), 500


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
        link_preview_enabled=data.get("link_preview_enabled", True),
        topic_id=data.get("topic_id"),
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({"scheduled_message": msg.to_dict(), "message": "Scheduled message created"}), 201


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/scheduled-messages/<int:msg_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_scheduled_message(bot_id, group_id, msg_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    msg = ScheduledMessage.query.filter_by(id=msg_id, group_id=group.id).first()
    if not msg:
        return jsonify({"error": "Scheduled message not found"}), 404
    db.session.delete(msg)
    db.session.commit()
    return jsonify({"success": True})


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


# ── Auto-Responses ──────────────────────────────────────────────────────────

@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/auto-responses", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_auto_responses(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    responses = AutoResponse.query.filter_by(group_id=group.id).order_by(AutoResponse.created_at).all()
    return jsonify({"auto_responses": [r.to_dict() for r in responses]})


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/auto-responses", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_auto_response(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    data = request.get_json()
    if not data or not data.get("trigger_text") or not data.get("response_text"):
        return jsonify({"error": "trigger_text and response_text are required"}), 400
    ar = AutoResponse(
        group_id=group.id,
        trigger_text=data["trigger_text"],
        response_text=data["response_text"],
        match_type=data.get("match_type", "contains"),
        is_case_sensitive=data.get("is_case_sensitive", False),
        is_enabled=data.get("is_enabled", True),
    )
    db.session.add(ar)
    db.session.commit()
    return jsonify({"auto_response": ar.to_dict(), "message": "Auto-response created"}), 201


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/auto-responses/<int:ar_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def update_auto_response(bot_id, group_id, ar_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    ar = AutoResponse.query.filter_by(id=ar_id, group_id=group.id).first()
    if not ar:
        return jsonify({"error": "Auto-response not found"}), 404
    data = request.get_json() or {}
    if "trigger_text" in data:
        ar.trigger_text = data["trigger_text"]
    if "response_text" in data:
        ar.response_text = data["response_text"]
    if "match_type" in data:
        ar.match_type = data["match_type"]
    if "is_case_sensitive" in data:
        ar.is_case_sensitive = data["is_case_sensitive"]
    if "is_enabled" in data:
        ar.is_enabled = data["is_enabled"]
    db.session.commit()
    return jsonify({"auto_response": ar.to_dict(), "message": "Updated"})


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/auto-responses/<int:ar_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def delete_auto_response(bot_id, group_id, ar_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    ar = AutoResponse.query.filter_by(id=ar_id, group_id=group.id).first()
    if not ar:
        return jsonify({"error": "Auto-response not found"}), 404
    db.session.delete(ar)
    db.session.commit()
    return jsonify({"message": "Deleted"})


# ── Reports ─────────────────────────────────────────────────────────────────

@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/reports", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_reports(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    status_filter = request.args.get("status", "")
    query = ReportedMessage.query.filter_by(group_id=group.id)
    if status_filter:
        query = query.filter_by(status=status_filter)
    reports = query.order_by(ReportedMessage.created_at.desc()).all()
    return jsonify({"reports": [r.to_dict() for r in reports]})


@settings_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/reports/<int:report_id>/resolve", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def resolve_report(bot_id, group_id, report_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    bot, group, err = _get_bot_and_group(user, bot_id, group_id)
    if err:
        return err
    report = ReportedMessage.query.filter_by(id=report_id, group_id=group.id).first()
    if not report:
        return jsonify({"error": "Report not found"}), 404
    report.status = "resolved"
    db.session.commit()
    return jsonify({"report": report.to_dict(), "message": "Report resolved"})
