"""
Telegram Mini App authentication.

Telegram sends an initData string in the WebApp.initData property.
We verify its HMAC-SHA256 signature using the bot token, then issue
a short-lived JWT so the Mini App can call all existing API endpoints.

POST /api/miniapp/auth   { "init_data": "<raw initData string>" }
  → { "token": "<jwt>", "user": {...}, "groups": [...] }

GET  /api/miniapp/me     (JWT-auth) — return current user + groups
"""
import hashlib
import hmac
import json
import logging
import time
import urllib.parse

from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from ..models import db, User, TelegramGroup
from ..config import Config

miniapp_bp = Blueprint("miniapp", __name__, url_prefix="/api/miniapp")
_log = logging.getLogger(__name__)

_MAX_AGE_SECONDS = 3600  # reject initData older than 1 hour


def _verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Validate Telegram WebApp initData HMAC.
    Returns the parsed data dict on success, None on failure.
    """
    try:
        params = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = params.pop("hash", None)
        if not received_hash:
            return None

        # Build data-check string: sorted key=value pairs joined by \n
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

        # HMAC key = HMAC-SHA256("WebAppData", bot_token)
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected, received_hash):
            return None

        # Age check
        auth_date = int(params.get("auth_date", 0))
        if time.time() - auth_date > _MAX_AGE_SECONDS:
            return None

        result = dict(params)
        if "user" in result:
            result["user"] = json.loads(result["user"])
        return result
    except Exception as exc:
        _log.debug("initData verification failed: %s", exc)
        return None


def _user_groups(user: User):
    groups = TelegramGroup.query.filter_by(
        owner_user_id=user.id, is_disabled=False
    ).order_by(TelegramGroup.created_at.desc()).all()
    return [
        {
            "id": g.id,
            "telegram_group_id": g.telegram_group_id,
            "name": g.name,
            "bot_status": g.bot_status,
            "member_count": g.member_count,
        }
        for g in groups
    ]


# ── Auth ──────────────────────────────────────────────────────────────────────

@miniapp_bp.route("/auth", methods=["POST"])
def miniapp_auth():
    data = request.get_json() or {}
    init_data = (data.get("init_data") or "").strip()

    if not init_data:
        return jsonify({"error": "init_data is required"}), 400

    bot_token = (Config.TELEGRAM_BOT_TOKEN or "").strip()
    if not bot_token:
        return jsonify({"error": "Bot not configured"}), 503

    parsed = _verify_init_data(init_data, bot_token)
    if not parsed:
        return jsonify({"error": "Invalid or expired initData"}), 401

    tg_user = parsed.get("user", {})
    tg_id = str(tg_user.get("id", ""))
    if not tg_id:
        return jsonify({"error": "No user in initData"}), 400

    # Find the linked website account
    user = User.query.filter_by(telegram_user_id=tg_id).first()
    if not user:
        return jsonify({
            "error": "No Telegizer account linked to this Telegram account.",
            "code": "NOT_LINKED",
            "link_url": "https://telegizer.com/settings",
        }), 404

    if user.is_banned:
        return jsonify({"error": "Account suspended"}), 403

    token = create_access_token(identity=str(user.id))
    return jsonify({
        "token": token,
        "user": user.to_dict(),
        "groups": _user_groups(user),
    })


# ── Me (used after token is stored) ──────────────────────────────────────────

@miniapp_bp.route("/me", methods=["GET"])
@jwt_required()
def miniapp_me():
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "user": user.to_dict(),
        "groups": _user_groups(user),
    })
