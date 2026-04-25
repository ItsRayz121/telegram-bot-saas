import bcrypt
import logging
import threading
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity, get_jwt
)

from ..models import db, User, PasswordResetToken, Referral
from ..middleware.rate_limit import rate_limit
from ..config import Config

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
@rate_limit(requests_per_minute=10)
def register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    full_name = data.get("full_name", "").strip()
    ref_code = data.get("ref", "").strip() or ""

    if not email or not password or not full_name:
        return jsonify({"error": "Email, password, and full_name are required"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "Invalid email format"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    import secrets as _secrets
    user = User(
        email=email,
        password_hash=pw_hash,
        full_name=full_name,
        referral_code=_secrets.token_urlsafe(8)[:10],
    )
    db.session.add(user)
    db.session.flush()  # get user.id before commit

    # Handle referral — find referrer by code, prevent self-referral
    if ref_code:
        referrer = User.query.filter_by(referral_code=ref_code).first()
        if referrer and referrer.id != user.id:
            existing = Referral.query.filter_by(referred_user_id=user.id).first()
            if not existing:
                referral = Referral(
                    referrer_user_id=referrer.id,
                    referred_user_id=user.id,
                    referral_code=ref_code,
                )
                db.session.add(referral)
                # Check milestones for referrer in a background thread
                try:
                    from flask import current_app
                    from ..routes.referrals import _apply_referral_rewards
                    _app = current_app._get_current_object()
                    _referrer_id = referrer.id

                    def _reward():
                        try:
                            with _app.app_context():
                                r = User.query.get(_referrer_id)
                                if r:
                                    _apply_referral_rewards(r)
                        except Exception as exc:
                            logger.warning("Referral reward check failed: %s", exc)

                    threading.Thread(target=_reward, daemon=True).start()
                except Exception:
                    pass

    db.session.commit()

    # Send welcome email asynchronously — never block the response on SMTP.
    # smtplib is synchronous and can hang if the mail server is unreachable,
    # which previously caused gunicorn to time out AFTER the DB commit, making
    # the frontend show "Registration failed" even though the account existed.
    try:
        from flask import current_app
        from ..notifications import send_welcome_email
        _app = current_app._get_current_object()
        _email_copy, _name_copy = email, full_name

        def _send_welcome():
            try:
                with _app.app_context():
                    send_welcome_email(_email_copy, _name_copy)
            except Exception as exc:
                logger.warning("Welcome email failed for %s: %s", _email_copy, exc)

        threading.Thread(target=_send_welcome, daemon=True).start()
    except Exception:
        pass

    token = create_access_token(identity=str(user.id))
    return jsonify({"token": token, "user": user.to_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
@rate_limit(requests_per_minute=20)
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return jsonify({"error": "Invalid credentials"}), 401

    if user.is_banned:
        return jsonify({"error": f"Account banned: {user.ban_reason or 'No reason provided'}"}), 403

    # Developer/admin accounts always have enterprise access
    if user.email in Config.ADMIN_EMAILS and user.subscription_tier != "enterprise":
        user.subscription_tier = "enterprise"
        user.subscription_expires = None
        db.session.commit()

    token = create_access_token(identity=str(user.id))
    user_data = user.to_dict()
    user_data["is_admin"] = user.email in Config.ADMIN_EMAILS
    return jsonify({"token": token, "user": user_data}), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_me():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404
    user_data = user.to_dict()
    user_data["is_admin"] = user.email in Config.ADMIN_EMAILS
    return jsonify({"user": user_data}), 200


@auth_bp.route("/forgot-password", methods=["POST"])
@rate_limit(requests_per_minute=5)
def forgot_password():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    # Always return 200 to avoid leaking which emails exist
    if user and not user.is_banned:
        # Invalidate any existing unused tokens
        PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({"used": True})
        db.session.flush()

        reset_token = PasswordResetToken.create_for_user(user.id)
        db.session.add(reset_token)
        db.session.commit()

        try:
            from flask import current_app
            from ..notifications import send_password_reset_email
            _app = current_app._get_current_object()
            _uemail, _uname, _tok = user.email, user.full_name, reset_token.token

            def _send_reset():
                try:
                    with _app.app_context():
                        send_password_reset_email(_uemail, _uname, _tok)
                except Exception as exc:
                    logger.warning("Password reset email failed for %s: %s", _uemail, exc)

            threading.Thread(target=_send_reset, daemon=True).start()
        except Exception:
            pass

    return jsonify({"message": "If that email exists, a reset link has been sent."}), 200


@auth_bp.route("/reset-password", methods=["POST"])
@rate_limit(requests_per_minute=10)
def reset_password():
    data = request.get_json() or {}
    token_str = data.get("token", "").strip()
    new_password = data.get("new_password", "")

    if not token_str or not new_password:
        return jsonify({"error": "token and new_password are required"}), 400

    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    reset_token = PasswordResetToken.query.filter_by(token=token_str).first()
    if not reset_token or not reset_token.is_valid:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    user = User.query.get(reset_token.user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    reset_token.used = True
    db.session.commit()

    return jsonify({"message": "Password reset successfully. You can now log in."}), 200


@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def change_password():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    if not bcrypt.checkpw(current_password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return jsonify({"error": "Current password is incorrect"}), 401

    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    user.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.session.commit()

    return jsonify({"message": "Password updated successfully"}), 200


@auth_bp.route("/account", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=3)
def delete_account():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    password = data.get("password", "")
    if not password:
        return jsonify({"error": "Password is required to delete account"}), 400

    if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return jsonify({"error": "Incorrect password"}), 401

    # Prevent admins from self-deleting via API
    if user.email in Config.ADMIN_EMAILS:
        return jsonify({"error": "Admin accounts cannot be deleted via API"}), 403

    # Stop all running bots before deletion
    try:
        from ..bot_manager import bot_manager
        for bot in user.bots:
            try:
                bot_manager.stop_bot(bot.id)
            except Exception:
                pass
    except Exception:
        pass

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Account deleted successfully"}), 200


def _get_redis():
    """Return a Redis client or None if unavailable."""
    try:
        import redis
        r = redis.from_url(Config.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        r.ping()
        return r
    except Exception:
        return None


def is_token_revoked(jwt_payload: dict) -> bool:
    """Called by flask-jwt-extended token_in_blocklist_loader."""
    jti = jwt_payload.get("jti")
    if not jti:
        return False
    r = _get_redis()
    if r is None:
        return False
    try:
        return r.exists(f"jwt_blocklist:{jti}") == 1
    except Exception:
        return False


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def logout():
    """Revoke the current access token by adding its jti to the Redis blocklist."""
    jwt_data = get_jwt()
    jti = jwt_data.get("jti")
    exp = jwt_data.get("exp")
    if jti:
        r = _get_redis()
        if r:
            try:
                import time
                ttl = max(int(exp - time.time()), 1) if exp else 7 * 24 * 3600
                r.setex(f"jwt_blocklist:{jti}", ttl, "revoked")
            except Exception as exc:
                logger.warning("Could not add jti to blocklist: %s", exc)
    return jsonify({"message": "Logged out successfully"}), 200
