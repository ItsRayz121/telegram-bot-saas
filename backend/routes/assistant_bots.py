"""
API routes for the user's personal Assistant Bot (bring-your-own-token, Pro+).
"""

import logging
import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, AssistantBot
from ..middleware.rate_limit import rate_limit

assistant_bots_bp = Blueprint("assistant_bots", __name__, url_prefix="/api/assistant-bot")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
_log = logging.getLogger("assistant_bots")


def _current_user():
    return User.query.get(int(get_jwt_identity()))


def _require_pro(user):
    if user.subscription_tier not in ("pro", "enterprise"):
        return jsonify({"error": "Assistant Bot is a Pro/Enterprise feature. Upgrade to connect your own bot."}), 403
    return None


def _validate_token(bot_token: str):
    """Call Telegram getMe to validate token and fetch bot info. Returns (username, name) or raises ValueError."""
    try:
        resp = requests.get(TELEGRAM_API.format(token=bot_token, method="getMe"), timeout=8)
        data = resp.json()
    except Exception:
        raise ValueError("Could not reach Telegram API — check your internet connection.")
    if not data.get("ok"):
        raise ValueError("Invalid bot token — Telegram rejected it.")
    result = data["result"]
    return result.get("username"), result.get("first_name")


def _register_webhook(bot_token: str):
    """Tell Telegram to send updates for this bot to our webhook endpoint."""
    try:
        from .telegram_updates import make_webhook_url
        url = make_webhook_url(bot_token)
        resp = requests.post(
            TELEGRAM_API.format(token=bot_token, method="setWebhook"),
            json={"url": url, "allowed_updates": ["message", "edited_message", "callback_query"]},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            _log.warning("setWebhook failed: %s", data)
        else:
            _log.info("Webhook registered for assistant bot: %s", url)
    except Exception as exc:
        _log.warning("_register_webhook error: %s", exc)


def _deregister_webhook(bot_token: str):
    """Remove the Telegram webhook for this bot token."""
    try:
        requests.post(
            TELEGRAM_API.format(token=bot_token, method="deleteWebhook"),
            json={"drop_pending_updates": False},
            timeout=10,
        )
    except Exception as exc:
        _log.warning("_deregister_webhook error: %s", exc)


# ── GET /api/assistant-bot/spaces ────────────────────────────────────────────

@assistant_bots_bp.route("/spaces", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_spaces():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    from ..models import AssistantBot, AssistantSpace
    bot = AssistantBot.query.filter_by(user_id=user.id).first()
    if not bot:
        return jsonify({"spaces": []})

    spaces = AssistantSpace.query.filter_by(assistant_bot_id=bot.id).order_by(
        AssistantSpace.last_seen_at.desc()
    ).all()
    return jsonify({"spaces": [s.to_dict() for s in spaces]})


# ── GET /api/assistant-bot ────────────────────────────────────────────────────

@assistant_bots_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_assistant_bot():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = AssistantBot.query.filter_by(user_id=user.id).first()
    return jsonify({"bot": bot.to_dict() if bot else None})


# ── POST /api/assistant-bot ───────────────────────────────────────────────────

@assistant_bots_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def create_assistant_bot():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    gate = _require_pro(user)
    if gate:
        return gate

    if AssistantBot.query.filter_by(user_id=user.id).first():
        return jsonify({"error": "You already have an assistant bot. Use PUT to update it."}), 409

    data = request.get_json() or {}
    bot_token = (data.get("bot_token") or "").strip()
    if not bot_token:
        return jsonify({"error": "bot_token is required"}), 400

    try:
        username, name = _validate_token(bot_token)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422

    bot = AssistantBot(user_id=user.id, bot_username=username, bot_name=name)
    bot.bot_token = bot_token
    db.session.add(bot)
    db.session.commit()

    _register_webhook(bot_token)

    return jsonify({"bot": bot.to_dict()}), 201


# ── PUT /api/assistant-bot ────────────────────────────────────────────────────

@assistant_bots_bp.route("", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def update_assistant_bot():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    gate = _require_pro(user)
    if gate:
        return gate

    bot = AssistantBot.query.filter_by(user_id=user.id).first()
    if not bot:
        return jsonify({"error": "No assistant bot found. Use POST to create one."}), 404

    data = request.get_json() or {}
    old_token = bot.bot_token

    if "bot_token" in data:
        new_token = (data["bot_token"] or "").strip()
        if not new_token:
            return jsonify({"error": "bot_token cannot be empty"}), 400
        try:
            username, name = _validate_token(new_token)
        except ValueError as e:
            return jsonify({"error": str(e)}), 422
        # Deregister old webhook before saving new token
        if old_token and old_token != new_token:
            _deregister_webhook(old_token)
        bot.bot_token = new_token
        bot.bot_username = username
        bot.bot_name = name

    if "is_active" in data:
        bot.is_active = bool(data["is_active"])

    db.session.commit()

    # Re-register webhook with new token (or re-enable if toggled active)
    current_token = bot.bot_token
    if current_token and bot.is_active:
        _register_webhook(current_token)
    elif current_token and not bot.is_active:
        _deregister_webhook(current_token)

    return jsonify({"bot": bot.to_dict()})


# ── DELETE /api/assistant-bot ─────────────────────────────────────────────────

@assistant_bots_bp.route("", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def delete_assistant_bot():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = AssistantBot.query.filter_by(user_id=user.id).first()
    if not bot:
        return jsonify({"error": "No assistant bot found"}), 404

    raw_token = bot.bot_token
    db.session.delete(bot)
    db.session.commit()

    if raw_token:
        _deregister_webhook(raw_token)

    return jsonify({"message": "Assistant bot removed."})
