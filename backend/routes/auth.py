import bcrypt
import hashlib
import logging
import threading
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity, get_jwt
)

from ..models import db, User, PasswordResetToken, Referral, RevokedToken, SuspiciousActivity
from ..middleware.rate_limit import rate_limit
from ..config import Config

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_MAX_FAILED_ATTEMPTS = 10
_LOCKOUT_MINUTES = 15

# Anti-abuse thresholds
_IP_SIGNUP_LIMIT = 3    # max new accounts per IP in 24h before hard block
_DEV_SIGNUP_LIMIT = 2   # max new accounts per device in 24h before flagging


# ── Helpers ────────────────────────────────────────────────────────────────────

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
    """Called by flask-jwt-extended token_in_blocklist_loader.

    Strategy:
    1. Check Redis blocklist (fast path).
    2. Fall back to the DB revoked_tokens table if Redis is unavailable.
    This means logout always works even during a Redis outage.
    """
    jti = jwt_payload.get("jti")
    if not jti:
        return False

    # Fast path: Redis
    r = _get_redis()
    if r is not None:
        try:
            return r.exists(f"jwt_blocklist:{jti}") == 1
        except Exception:
            pass

    # Fallback: DB revoked_tokens table
    try:
        now = datetime.utcnow()
        record = RevokedToken.query.filter_by(jti=jti).first()
        if record and record.expires_at > now:
            return True
    except Exception as exc:
        logger.warning("DB token blocklist check failed: %s", exc)
    return False


def _revoke_token(jti: str, exp: int):
    """Add token to Redis blocklist AND DB revoked_tokens table."""
    import time as _time

    # Write to Redis
    r = _get_redis()
    if r:
        try:
            ttl = max(int(exp - _time.time()), 1) if exp else 7 * 24 * 3600
            r.setex(f"jwt_blocklist:{jti}", ttl, "revoked")
        except Exception as exc:
            logger.warning("Could not write jti to Redis blocklist: %s", exc)

    # Write to DB (fallback + audit trail)
    try:
        expires_at = datetime.utcfromtimestamp(exp) if exp else datetime.utcnow() + timedelta(days=7)
        if not RevokedToken.query.filter_by(jti=jti).first():
            db.session.add(RevokedToken(jti=jti, expires_at=expires_at))
            db.session.commit()
    except Exception as exc:
        logger.warning("Could not write jti to DB revoked_tokens: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass


def _send_verification_email_async(app, user_email, user_name, token):
    """Send email verification link in a background thread."""
    from ..notifications import send_verification_email

    def _send():
        try:
            with app.app_context():
                send_verification_email(user_email, user_name, token)
        except Exception as exc:
            logger.warning("Verification email failed for %s: %s", user_email, exc)

    threading.Thread(target=_send, daemon=True).start()


# ── Anti-abuse helpers ─────────────────────────────────────────────────────────

def _hash_identifier(value: str) -> str:
    """Return SHA-256 hex digest of the given string. Used for IP and device fingerprint storage."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _get_client_ip() -> str:
    """Extract real client IP, honoring X-Forwarded-For from trusted reverse proxies."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        # Take the first (leftmost) address — the original client IP
        return xff.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def _count_recent_signups_by_ip(ip_hash: str) -> int:
    """Count users created with this IP hash in the past 24 hours."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    return User.query.filter(
        User.signup_ip_hash == ip_hash,
        User.created_at >= cutoff,
    ).count()


def _count_recent_signups_by_device(device_hash: str) -> int:
    """Count users created with this device hash in the past 24 hours."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    return User.query.filter(
        User.device_fingerprint_hash == device_hash,
        User.created_at >= cutoff,
    ).count()


def _log_suspicious(user_id, event_type: str, ip_hash, device_hash, reason: str, metadata=None):
    """Append a SuspiciousActivity record. Failures are logged but never raise."""
    try:
        event = SuspiciousActivity(
            user_id=user_id,
            event_type=event_type,
            ip_hash=ip_hash,
            device_hash=device_hash,
            reason=reason,
            event_metadata=metadata or {},
        )
        db.session.add(event)
        db.session.flush()
    except Exception as exc:
        logger.warning("Failed to log suspicious activity: %s", exc)


# ── Registration ───────────────────────────────────────────────────────────────

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
    # Device fingerprint pre-hashed by client — double-hash before storing
    raw_fingerprint = data.get("device_fingerprint", "").strip()

    if not email or not password or not full_name:
        return jsonify({"error": "Email, password, and full_name are required"}), 400

    # Input length limits
    if len(email) > 255:
        return jsonify({"error": "Email too long"}), 400
    if len(full_name) > 255:
        return jsonify({"error": "Name too long (max 255 characters)"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if len(password) > 128:
        return jsonify({"error": "Password too long (max 128 characters)"}), 400

    import re
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", email):
        return jsonify({"error": "Invalid email format"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    # ── Anti-abuse: hash identifiers (never store raw values) ─────────────────
    client_ip = _get_client_ip()
    ip_hash = _hash_identifier(client_ip) if client_ip else None
    # Client sends a pre-hashed fingerprint; we SHA-256 again for double-blind storage
    device_hash = _hash_identifier(raw_fingerprint) if raw_fingerprint else None

    # IP limit: more than _IP_SIGNUP_LIMIT accounts in 24h from same IP → block
    if ip_hash:
        ip_count = _count_recent_signups_by_ip(ip_hash)
        if ip_count >= _IP_SIGNUP_LIMIT:
            _log_suspicious(None, "ip_limit", ip_hash, device_hash,
                            f"IP created {ip_count + 1} accounts in 24h (limit {_IP_SIGNUP_LIMIT})")
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            return jsonify({
                "error": "Too many accounts were created from this network. "
                         "Please try again later or contact support.",
                "code": "IP_SIGNUP_LIMIT",
            }), 429
    # ──────────────────────────────────────────────────────────────────────────

    import secrets as _secrets
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        email=email,
        password_hash=pw_hash,
        full_name=full_name,
        referral_code=_secrets.token_urlsafe(8)[:10],
        email_verified=False,
        signup_ip_hash=ip_hash,
        device_fingerprint_hash=device_hash,
    )
    # Generate email verification token
    verification_token = user.generate_verification_token()
    db.session.add(user)
    db.session.flush()

    # Device limit: flag account as suspicious if >_DEV_SIGNUP_LIMIT accounts from same device in 24h
    if device_hash:
        dev_count = _count_recent_signups_by_device(device_hash)
        if dev_count > _DEV_SIGNUP_LIMIT:
            user.is_suspicious = True
            _log_suspicious(user.id, "device_limit", ip_hash, device_hash,
                            f"Device created {dev_count} accounts in 24h (limit {_DEV_SIGNUP_LIMIT})")

    # ── Handle referral ────────────────────────────────────────────────────────
    if ref_code:
        referrer = User.query.filter_by(referral_code=ref_code).first()
        if referrer and referrer.id != user.id:
            existing = Referral.query.filter_by(referred_user_id=user.id).first()
            if not existing:
                # Check for device/IP overlap with referrer
                device_match = bool(device_hash and device_hash == referrer.device_fingerprint_hash)
                ip_match = bool(ip_hash and ip_hash == referrer.signup_ip_hash)

                if device_match:
                    # Same device as referrer — block referral reward, flag suspicious
                    referral_status = "suspicious"
                    _log_suspicious(user.id, "referral_device_abuse", ip_hash, device_hash,
                                    "Referred user shares device with referrer",
                                    {"referrer_id": referrer.id})
                elif ip_match:
                    # Same IP — flag as suspicious but allow referral (shared network may be legit)
                    referral_status = "suspicious"
                    _log_suspicious(user.id, "referral_ip_abuse", ip_hash, device_hash,
                                    "Referred user shares IP with referrer",
                                    {"referrer_id": referrer.id})
                else:
                    # Looks clean — will be approved after email verification
                    referral_status = "pending"

                referral = Referral(
                    referrer_user_id=referrer.id,
                    referred_user_id=user.id,
                    referral_code=ref_code,
                    status=referral_status,
                    ip_match=ip_match,
                    device_match=device_match,
                )
                db.session.add(referral)
                # Rewards are NOT granted here — only after email verification

    db.session.commit()

    # Send verification email asynchronously
    try:
        from flask import current_app
        _send_verification_email_async(
            current_app._get_current_object(), email, full_name, verification_token
        )
    except Exception:
        pass

    token = create_access_token(identity=str(user.id))
    return jsonify({"token": token, "user": user.to_dict()}), 201


# ── Login ──────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
@rate_limit(requests_per_minute=20)
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    totp_code = data.get("totp_code", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    # Account lockout check
    if user.is_locked:
        remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60) + 1
        return jsonify({
            "error": f"Account temporarily locked due to too many failed attempts. Try again in {remaining} minute(s).",
            "code": "ACCOUNT_LOCKED",
            "locked_until": user.locked_until.isoformat(),
        }), 429

    # Password check
    if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        # Increment failure counter
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= _MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=_LOCKOUT_MINUTES)
            logger.warning("Account locked after %d failed attempts: %s", user.failed_login_attempts, email)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({"error": "Invalid credentials"}), 401

    if user.is_banned:
        return jsonify({"error": f"Account banned: {user.ban_reason or 'No reason provided'}"}), 403

    # Reset failure counter on successful password check
    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # 2FA check
    if user.totp_enabled and user.totp_secret:
        if not totp_code:
            # Return indicator that 2FA is required; do NOT issue full JWT yet
            import secrets as _s
            pending_token = create_access_token(
                identity=str(user.id),
                expires_delta=timedelta(minutes=5),
                additional_claims={"scope": "totp_pending"},
            )
            return jsonify({
                "requires_2fa": True,
                "totp_pending_token": pending_token,
            }), 200

        # Validate TOTP code (and backup codes)
        if not _verify_totp(user, totp_code):
            return jsonify({"error": "Invalid 2FA code"}), 401

    # Admin auto-promotion
    if user.email in Config.ADMIN_EMAILS and user.subscription_tier != "enterprise":
        user.subscription_tier = "enterprise"
        user.subscription_expires = None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    token = create_access_token(identity=str(user.id))
    user_data = user.to_dict()
    user_data["is_admin"] = user.email in Config.ADMIN_EMAILS
    return jsonify({"token": token, "user": user_data}), 200


# ── 2FA login completion (submit code after receives requires_2fa) ─────────────

@auth_bp.route("/verify-totp-login", methods=["POST"])
@rate_limit(requests_per_minute=10)
def verify_totp_login():
    """Complete login when 2FA is required: validate pending token + TOTP code."""
    from flask_jwt_extended import decode_token
    data = request.get_json() or {}
    pending_token = data.get("totp_pending_token", "").strip()
    totp_code = data.get("totp_code", "").strip()

    if not pending_token or not totp_code:
        return jsonify({"error": "totp_pending_token and totp_code are required"}), 400

    try:
        decoded = decode_token(pending_token)
    except Exception:
        return jsonify({"error": "Invalid or expired session. Please log in again."}), 401

    if decoded.get("scope") != "totp_pending":
        return jsonify({"error": "Invalid token scope"}), 401

    user_id = decoded.get("sub")
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404

    if not _verify_totp(user, totp_code):
        return jsonify({"error": "Invalid 2FA code"}), 401

    # Admin auto-promotion
    if user.email in Config.ADMIN_EMAILS and user.subscription_tier != "enterprise":
        user.subscription_tier = "enterprise"
        user.subscription_expires = None
        db.session.commit()

    token = create_access_token(identity=str(user.id))
    user_data = user.to_dict()
    user_data["is_admin"] = user.email in Config.ADMIN_EMAILS
    return jsonify({"token": token, "user": user_data}), 200


def _verify_totp(user: User, code: str) -> bool:
    """Verify a TOTP code or a backup code against the user's credentials."""
    try:
        import pyotp
        from ..utils.encryption import decrypt_value
        secret = decrypt_value(user.totp_secret)
        if not secret:
            return False
        totp = pyotp.TOTP(secret)
        # Allow 30-second window on each side
        if totp.verify(code, valid_window=1):
            return True
    except Exception as exc:
        logger.warning("TOTP verify error: %s", exc)

    # Check backup codes
    return _consume_backup_code(user, code)


def _consume_backup_code(user: User, code: str) -> bool:
    """Return True and remove the code if it matches a stored backup code."""
    if not user.totp_backup_codes:
        return False
    code_clean = code.replace("-", "").strip().lower()
    remaining = []
    matched = False
    for stored in user.totp_backup_codes:
        if not matched:
            try:
                if bcrypt.checkpw(code_clean.encode(), stored.encode()):
                    matched = True
                    continue  # consume the code
            except Exception:
                pass
        remaining.append(stored)
    if matched:
        user.totp_backup_codes = remaining
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return matched


# ── Email verification ─────────────────────────────────────────────────────────

@auth_bp.route("/verify-email", methods=["POST"])
@rate_limit(requests_per_minute=10)
def verify_email():
    data = request.get_json() or {}
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"error": "Verification token is required"}), 400

    user = User.query.filter_by(email_verification_token=token).first()
    if not user:
        return jsonify({"error": "Invalid or expired verification link"}), 400

    if user.email_verification_expires and datetime.utcnow() > user.email_verification_expires:
        return jsonify({"error": "Verification link has expired. Please request a new one."}), 400

    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_expires = None

    # Approve any pending (non-suspicious) referral and trigger reward check
    referral = Referral.query.filter_by(referred_user_id=user.id, status="pending").first()
    if referral:
        referral.status = "approved"

    db.session.commit()

    # Trigger referral reward check for the referrer in a background thread
    if referral:
        try:
            from flask import current_app
            from ..routes.referrals import _apply_referral_rewards
            _app = current_app._get_current_object()
            _referrer_id = referral.referrer_user_id

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

    logger.info("Email verified for user %s", user.id)
    return jsonify({"message": "Email verified successfully!", "email_verified": True}), 200


@auth_bp.route("/resend-verification", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=3)
def resend_verification():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.email_verified:
        return jsonify({"message": "Email is already verified"}), 200

    # Rate-limit resends: check if a token was recently sent
    if user.email_verification_expires:
        cooldown_end = user.email_verification_expires - timedelta(hours=23)
        if datetime.utcnow() < cooldown_end:
            return jsonify({"error": "A verification email was sent recently. Please wait before requesting another."}), 429

    verification_token = user.generate_verification_token()
    db.session.commit()

    try:
        from flask import current_app
        _send_verification_email_async(
            current_app._get_current_object(), user.email, user.full_name, verification_token
        )
    except Exception:
        pass

    return jsonify({"message": "Verification email sent! Check your inbox."}), 200


# ── Standard auth routes ───────────────────────────────────────────────────────

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
    if len(new_password) > 128:
        return jsonify({"error": "Password too long"}), 400

    reset_token = PasswordResetToken.query.filter_by(token=token_str).first()
    if not reset_token or not reset_token.is_valid:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    user = User.query.get(reset_token.user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    # Reset brute-force counter on successful password reset
    user.failed_login_attempts = 0
    user.locked_until = None
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
    if len(new_password) > 128:
        return jsonify({"error": "Password too long"}), 400

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

    if user.email in Config.ADMIN_EMAILS:
        return jsonify({"error": "Admin accounts cannot be deleted via API"}), 403

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


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def logout():
    """Revoke the current access token in both Redis and DB."""
    jwt_data = get_jwt()
    jti = jwt_data.get("jti")
    exp = jwt_data.get("exp")
    if jti:
        _revoke_token(jti, exp)
    return jsonify({"message": "Logged out successfully"}), 200
