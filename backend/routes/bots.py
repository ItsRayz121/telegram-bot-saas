import requests as http_requests
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, Bot, Group
from ..middleware.rate_limit import rate_limit

bots_bp = Blueprint("bots", __name__, url_prefix="/api/bots")


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


@bots_bp.route("", methods=["GET"])
@jwt_required()
def get_bots():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bots = Bot.query.filter_by(user_id=user.id).all()
    return jsonify({"bots": [b.to_dict() for b in bots]}), 200


@bots_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_bot():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    max_bots = current_app.config["MAX_BOTS"].get(user.subscription_tier, 1)
    current_count = Bot.query.filter_by(user_id=user.id).count()
    if current_count >= max_bots:
        return jsonify({
            "error": f"Bot limit reached ({max_bots} bots for {user.subscription_tier} tier). Upgrade to add more.",
        }), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    token = data.get("bot_token", "").strip()
    if not token:
        return jsonify({"error": "bot_token is required"}), 400

    if Bot.query.filter_by(bot_token=token).first():
        return jsonify({"error": "This bot token is already registered"}), 409

    try:
        resp = http_requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        resp.raise_for_status()
        bot_info = resp.json()
        if not bot_info.get("ok"):
            return jsonify({"error": "Invalid bot token"}), 400

        result = bot_info["result"]
        bot_username = result.get("username", "")
        bot_name = result.get("first_name", "")
    except http_requests.exceptions.Timeout:
        return jsonify({"error": "Telegram API timeout. Check your token."}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to validate bot token: {str(e)}"}), 400

    bot = Bot(
        user_id=user.id,
        bot_token=token,
        bot_username=bot_username,
        bot_name=bot_name,
        is_active=True,
    )
    db.session.add(bot)
    db.session.commit()

    try:
        from ..bot_manager import bot_manager
        bot_manager.start_bot(bot.id, token, current_app._get_current_object())
    except Exception as e:
        current_app.logger.error(f"Failed to start bot {bot.id}: {e}")

    try:
        from ..notifications import send_bot_added_notification
        send_bot_added_notification(user.email, user.full_name, bot_name, bot_username)
    except Exception:
        pass

    return jsonify({"bot": bot.to_dict(), "message": "Bot added successfully"}), 201


@bots_bp.route("/<int:bot_id>", methods=["DELETE"])
@jwt_required()
def delete_bot(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    try:
        from ..bot_manager import bot_manager
        bot_manager.stop_bot(bot_id)
    except Exception as e:
        current_app.logger.error(f"Failed to stop bot {bot_id}: {e}")

    db.session.delete(bot)
    db.session.commit()

    return jsonify({"message": "Bot deleted successfully"}), 200


@bots_bp.route("/<int:bot_id>", methods=["GET"])
@jwt_required()
def get_bot(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    return jsonify({"bot": bot.to_dict()}), 200


@bots_bp.route("/<int:bot_id>/groups", methods=["GET"])
@jwt_required()
def get_bot_groups(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    groups = Group.query.filter_by(bot_id=bot_id).all()
    return jsonify({"groups": [g.to_dict() for g in groups]}), 200


@bots_bp.route("/<int:bot_id>/toggle", methods=["POST"])
@jwt_required()
def toggle_bot(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    from ..bot_manager import bot_manager

    if bot.is_active:
        bot_manager.stop_bot(bot_id)
        bot.is_active = False
        msg = "Bot stopped"
    else:
        bot.is_active = True
        bot_manager.start_bot(bot_id, bot.bot_token, current_app._get_current_object())
        msg = "Bot started"

    db.session.commit()
    return jsonify({"message": msg, "is_active": bot.is_active}), 200
