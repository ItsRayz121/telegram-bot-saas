"""
API routes for user-owned custom bots (bring-your-own-token).
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, CustomBot, TelegramGroup
from ..middleware.rate_limit import rate_limit
from ..config import Config

custom_bots_bp = Blueprint("custom_bots", __name__, url_prefix="/api/custom-bots")


def _current_user():
    return User.query.get(int(get_jwt_identity()))


# ── List user's custom bots ────────────────────────────────────────────────────

@custom_bots_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_custom_bots():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bots = CustomBot.query.filter_by(owner_user_id=user.id).order_by(
        CustomBot.created_at.desc()
    ).all()
    return jsonify({"bots": [b.to_dict() for b in bots]})


# ── Add a custom bot ───────────────────────────────────────────────────────────

@custom_bots_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def add_custom_bot():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    max_bots = Config.MAX_CUSTOM_BOTS.get(user.subscription_tier, 0)
    current_count = CustomBot.query.filter_by(owner_user_id=user.id).count()
    if current_count >= max_bots:
        return jsonify({
            "error": f"Custom bots are available on Pro/Enterprise plans. "
                     f"Upgrade to connect your own bot token.",
            "limit": max_bots,
        }), 403

    data = request.get_json() or {}
    bot_token = (data.get("bot_token") or "").strip()
    bot_username = (data.get("bot_username") or "").strip().lstrip("@")

    if not bot_token:
        return jsonify({"error": "bot_token is required"}), 400
    if not bot_username:
        return jsonify({"error": "bot_username is required"}), 400

    # Basic token format check (1234567890:AAAA...)
    if ":" not in bot_token or len(bot_token) < 30:
        return jsonify({"error": "Invalid bot token format"}), 400

    # Verify token with Telegram
    bot_name = None
    try:
        import requests as _req
        resp = _req.get(
            f"https://api.telegram.org/bot{bot_token}/getMe",
            timeout=10,
        )
        result = resp.json()
        if not result.get("ok"):
            return jsonify({"error": "Telegram rejected this bot token. Check it is correct."}), 400
        tg_data = result.get("result", {})
        bot_name = tg_data.get("first_name")
        bot_username = tg_data.get("username") or bot_username
    except Exception as exc:
        return jsonify({"error": f"Could not verify token with Telegram: {exc}"}), 502

    custom_bot = CustomBot(
        owner_user_id=user.id,
        bot_name=bot_name,
        bot_username=bot_username,
        status="active",
    )
    custom_bot.set_token(bot_token)
    db.session.add(custom_bot)
    db.session.commit()

    return jsonify({"bot": custom_bot.to_dict(), "message": "Custom bot connected successfully"}), 201


# ── Get a custom bot ───────────────────────────────────────────────────────────

@custom_bots_bp.route("/<int:bot_id>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_custom_bot(bot_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = CustomBot.query.filter_by(id=bot_id, owner_user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    data = bot.to_dict()
    data["linked_groups"] = [g.to_dict() for g in bot.linked_groups]
    return jsonify({"bot": data})


# ── Disconnect / delete a custom bot ──────────────────────────────────────────

@custom_bots_bp.route("/<int:bot_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def delete_custom_bot(bot_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = CustomBot.query.filter_by(id=bot_id, owner_user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    # Unlink any groups that used this custom bot
    TelegramGroup.query.filter_by(linked_bot_id=bot_id).update({
        "linked_bot_id": None,
        "linked_via_bot_type": "official",
    })

    db.session.delete(bot)
    db.session.commit()

    return jsonify({"message": "Custom bot disconnected"})
