"""
Endpoints for linking a website user account to their Telegram identity.

Flow:
  1. User calls POST /api/telegram/generate-connect-code (JWT-auth).
  2. Backend returns a one-time code and a deep-link URL.
  3. User opens that URL → Telegram opens @telegizer_bot with /start connect_<code>.
  4. Bot looks up the code, sets User.telegram_user_id, marks code used.
  5. Frontend polls GET /api/telegram/connection-status until connected.
"""

import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, TelegramConnectCode, UserTelegramAccount
from ..config import Config
from ..middleware.rate_limit import rate_limit

telegram_account_bp = Blueprint("telegram_account", __name__, url_prefix="/api/telegram")


def _current_user():
    return User.query.get(int(get_jwt_identity()))


@telegram_account_bp.route("/generate-connect-code", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def generate_connect_code():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if not user.email_verified:
        return jsonify({"error": "Verify your email before connecting Telegram"}), 403

    # Invalidate any existing unused codes for this user
    TelegramConnectCode.query.filter_by(user_id=user.id, used_at=None).update(
        {"expires_at": datetime.utcnow()}
    )
    db.session.flush()

    code = TelegramConnectCode.generate()
    # Ensure uniqueness (astronomically unlikely to collide, but be safe)
    while TelegramConnectCode.query.filter_by(code=code).first():
        code = TelegramConnectCode.generate()

    tc = TelegramConnectCode(
        code=code,
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db.session.add(tc)
    db.session.commit()

    bot_username = (Config.TELEGRAM_BOT_USERNAME or "telegizer_bot").strip().lstrip("@")
    url = f"https://t.me/{bot_username}?start=connect_{code}"

    return jsonify({
        "code": code,
        "url": url,
        "expires_in": 900,
    })


@telegram_account_bp.route("/connection-status", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def connection_status():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Check UserTelegramAccount junction table first (multi-account), then legacy field
    primary = UserTelegramAccount.query.filter_by(user_id=user.id, is_primary=True).first()
    any_linked = UserTelegramAccount.query.filter_by(user_id=user.id).first()
    connected = bool(primary or any_linked or user.telegram_user_id)
    tg_acct = primary or any_linked
    return jsonify({
        "connected": connected,
        "telegram_username": (tg_acct.telegram_username if tg_acct else None) or user.telegram_username,
        "telegram_first_name": (tg_acct.telegram_first_name if tg_acct else None) or user.telegram_first_name,
        "connected_at": user.telegram_connected_at.isoformat() if user.telegram_connected_at else None,
    })


@telegram_account_bp.route("/disconnect", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def disconnect_telegram():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    has_junction = UserTelegramAccount.query.filter_by(user_id=user.id).first()
    if not user.telegram_user_id and not has_junction:
        return jsonify({"error": "No Telegram account connected"}), 400

    # Block disconnect if Telegram is the user's only identity — they'd lock themselves out
    if not user.email or not user.password_hash:
        return jsonify({
            "error": "Cannot disconnect Telegram — it is your only login method. "
                     "Add an email and password first via 'Protect your account'.",
            "code": "TELEGRAM_ONLY_ACCOUNT",
        }), 400

    # Remove all junction table rows for this user
    UserTelegramAccount.query.filter_by(user_id=user.id).delete()
    # Clear legacy field too
    user.telegram_user_id = None
    user.telegram_username = None
    user.telegram_connected_at = None
    db.session.commit()

    return jsonify({"message": "Telegram account disconnected"})
