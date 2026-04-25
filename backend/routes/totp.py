"""2FA / TOTP management endpoints.

Supported flows:
  POST /api/auth/2fa/setup       → generate secret + QR URI (requires auth)
  POST /api/auth/2fa/enable      → confirm code and enable 2FA
  POST /api/auth/2fa/disable     → disable 2FA (requires password + totp code)
  GET  /api/auth/2fa/backup-codes → list remaining backup codes count
  POST /api/auth/2fa/regenerate-backup-codes → regenerate backup codes
"""

import logging
import secrets
import bcrypt
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

totp_bp = Blueprint("totp", __name__, url_prefix="/api/auth/2fa")

_BACKUP_CODE_COUNT = 8


def _generate_backup_codes():
    """Generate 8 random backup codes, return (plaintext_list, hashed_list)."""
    plain = [secrets.token_hex(4).upper() + "-" + secrets.token_hex(4).upper() for _ in range(_BACKUP_CODE_COUNT)]
    hashed = [bcrypt.hashpw(c.replace("-", "").lower().encode(), bcrypt.gensalt()).decode() for c in plain]
    return plain, hashed


def _require_paid_or_admin(user):
    from datetime import datetime
    from ..config import Config
    is_admin = user.email in Config.ADMIN_EMAILS
    is_paid = user.subscription_tier in ("pro", "enterprise")
    is_expired = (
        is_paid
        and user.subscription_expires is not None
        and datetime.utcnow() > user.subscription_expires
    )
    if not is_admin and (not is_paid or is_expired):
        return jsonify({
            "error": "2FA is available for Pro and Enterprise subscribers.",
            "code": "FEATURE_REQUIRES_PRO",
            "upgrade_url": "/pricing",
        }), 403
    return None


@totp_bp.route("/setup", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def setup_totp():
    """Generate a new TOTP secret and provisioning URI. Does NOT enable 2FA yet."""
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404

    err = _require_paid_or_admin(user)
    if err:
        return err

    try:
        import pyotp
        from ..utils.encryption import encrypt_value
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name="BotForge")

        # Store encrypted secret temporarily (not enabled until confirmed)
        user.totp_secret = encrypt_value(secret)
        user.totp_enabled = False  # still pending confirmation
        db.session.commit()

        return jsonify({
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "message": "Scan the QR code in your authenticator app, then call /enable with a valid code.",
        })
    except ImportError:
        return jsonify({"error": "2FA is not available on this server (pyotp not installed)"}), 503
    except Exception as e:
        logger.error("TOTP setup error: %s", e, exc_info=True)
        return jsonify({"error": "Failed to set up 2FA"}), 500


@totp_bp.route("/enable", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def enable_totp():
    """Confirm TOTP setup by validating a code, then enable 2FA and issue backup codes."""
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404

    err = _require_paid_or_admin(user)
    if err:
        return err

    data = request.get_json() or {}
    code = data.get("totp_code", "").strip()
    if not code:
        return jsonify({"error": "totp_code is required"}), 400

    if not user.totp_secret:
        return jsonify({"error": "Run /setup first to generate a secret"}), 400

    try:
        import pyotp
        from ..utils.encryption import decrypt_value
        secret = decrypt_value(user.totp_secret)
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            return jsonify({"error": "Invalid code. Check your authenticator app."}), 400

        plain_codes, hashed_codes = _generate_backup_codes()
        user.totp_enabled = True
        user.totp_backup_codes = hashed_codes
        db.session.commit()

        logger.info("2FA enabled for user %s", user.id)
        return jsonify({
            "message": "2FA enabled successfully.",
            "backup_codes": plain_codes,
            "warning": "Save these backup codes in a safe place. They will not be shown again.",
        })
    except Exception as e:
        logger.error("TOTP enable error: %s", e, exc_info=True)
        return jsonify({"error": "Failed to enable 2FA"}), 500


@totp_bp.route("/disable", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def disable_totp():
    """Disable 2FA. Requires current password and a valid TOTP code."""
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404

    if not user.totp_enabled:
        return jsonify({"message": "2FA is not enabled"}), 200

    data = request.get_json() or {}
    password = data.get("password", "")
    code = data.get("totp_code", "").strip()

    if not password or not code:
        return jsonify({"error": "password and totp_code are required"}), 400

    if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        return jsonify({"error": "Incorrect password"}), 401

    # Validate TOTP or backup code
    from ..routes.auth import _verify_totp
    if not _verify_totp(user, code):
        return jsonify({"error": "Invalid 2FA code"}), 401

    user.totp_enabled = False
    user.totp_secret = None
    user.totp_backup_codes = None
    db.session.commit()

    logger.info("2FA disabled for user %s", user.id)
    return jsonify({"message": "2FA disabled successfully."})


@totp_bp.route("/backup-codes", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def get_backup_code_count():
    """Return how many backup codes remain (count only, never the codes themselves)."""
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404
    count = len(user.totp_backup_codes) if user.totp_backup_codes else 0
    return jsonify({"backup_codes_remaining": count, "totp_enabled": user.totp_enabled})


@totp_bp.route("/regenerate-backup-codes", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=3)
def regenerate_backup_codes():
    """Generate a fresh set of backup codes. Requires TOTP code to prevent abuse."""
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404

    if not user.totp_enabled:
        return jsonify({"error": "2FA is not enabled"}), 400

    data = request.get_json() or {}
    code = data.get("totp_code", "").strip()
    if not code:
        return jsonify({"error": "totp_code is required"}), 400

    from ..routes.auth import _verify_totp
    if not _verify_totp(user, code):
        return jsonify({"error": "Invalid 2FA code"}), 401

    plain_codes, hashed_codes = _generate_backup_codes()
    user.totp_backup_codes = hashed_codes
    db.session.commit()

    return jsonify({
        "backup_codes": plain_codes,
        "warning": "Previous backup codes are now invalid. Save these in a safe place.",
    })
