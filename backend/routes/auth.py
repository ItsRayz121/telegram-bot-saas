import bcrypt
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

from ..models import db, User, PasswordResetToken
from ..middleware.rate_limit import rate_limit
from ..config import Config

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
    user = User(email=email, password_hash=pw_hash, full_name=full_name)
    db.session.add(user)
    db.session.commit()

    try:
        from flask import current_app
        from ..notifications import send_welcome_email
        with current_app.app_context():
            send_welcome_email(email, full_name)
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
    return jsonify({"token": token, "user": user.to_dict()}), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_me():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user.to_dict()}), 200


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
            with current_app.app_context():
                send_password_reset_email(user.email, user.full_name, reset_token.token)
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
