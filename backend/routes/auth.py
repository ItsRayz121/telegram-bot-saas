import bcrypt
import hashlib
import hmac
import logging
import secrets
import threading
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt,
)

from ..models import db, User, PasswordResetToken, Referral, RevokedToken, SuspiciousActivity
from ..middleware.rate_limit import rate_limit
from ..middleware.csrf import generate_csrf_token
from ..config import Config

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _attach_admin_fields(user_data, user):
    """Add RBAC fields (is_admin, admin_role, admin_permissions) to a user dict.

    Single source of truth so login / 2FA / register / /me all agree. Uses
    backend.admin_rbac so the email-allowlist bootstrap and the admin_role
    column are both honoured.
    """
    from .. import admin_rbac as rbac
    role = rbac.resolve_admin_role(user)
    user_data["is_admin"] = role is not None
    user_data["admin_role"] = role
    user_data["admin_permissions"] = sorted(rbac.get_permissions(user))
    return user_data


# ── 1-D-01: Cookie auth helpers ────────────────────────────────────────────────

def _is_secure() -> bool:
    # Default True in production (PostgreSQL) so auth cookies always have Secure flag.
    is_prod = "postgres" in (current_app.config.get("SQLALCHEMY_DATABASE_URI") or "")
    return current_app.config.get("JWT_COOKIE_SECURE", is_prod)


def _set_auth_cookies(response, access_token: str, refresh_token: str = None):
    """Attach httpOnly JWT cookies and a JS-readable CSRF cookie to the response."""
    secure = _is_secure()
    response.set_cookie(
        "access_token", access_token,
        httponly=True, secure=secure, samesite="Strict",
        max_age=86400,
    )
    if refresh_token:
        response.set_cookie(
            "refresh_token", refresh_token,
            httponly=True, secure=secure, samesite="Strict",
            path="/api/auth/refresh",
            max_age=2592000,
        )
    # CSRF cookie — readable by JS, paired with X-CSRF-Token header (1-D-02).
    # max_age matches the access cookie: if it were a session cookie it could
    # expire before the access token, leaving a cookie-authenticated browser
    # unable to pass the CSRF check until the next login.
    response.set_cookie(
        "csrf_token", generate_csrf_token(),
        httponly=False, secure=secure, samesite="Strict",
        max_age=86400,
    )
    return response


def _clear_auth_cookies(response):
    """Expire all auth cookies on logout."""
    for name, path in [("access_token", "/"), ("refresh_token", "/api/auth/refresh"), ("csrf_token", "/"), ("totp_trusted", "/")]:
        response.set_cookie(name, "", expires=0, path=path)
    return response

_MAX_FAILED_ATTEMPTS = 10

_TOTP_TRUSTED_TTL = 48 * 3600  # 48 hours in seconds


def _set_totp_trusted_cookie(response, user_id: int):
    """After successful 2FA, stamp this browser as trusted for 48 hours."""
    token = secrets.token_urlsafe(32)
    _r = _get_redis()
    if _r:
        _r.setex(f"totp_trusted:{user_id}", _TOTP_TRUSTED_TTL, token)
    secure = _is_secure()
    response.set_cookie(
        "totp_trusted", f"{user_id}:{token}",
        httponly=True, secure=secure, samesite="Strict",
        max_age=_TOTP_TRUSTED_TTL,
    )


def _check_totp_trusted(user_id: int) -> bool:
    """Return True if this browser has a valid 48-hour trusted-device token."""
    cookie = request.cookies.get("totp_trusted", "")
    if not cookie:
        return False
    parts = cookie.split(":", 1)
    if len(parts) != 2:
        return False
    cookie_uid, token = parts
    if cookie_uid != str(user_id):
        return False
    _r = _get_redis()
    if not _r:
        return False
    stored = _r.get(f"totp_trusted:{user_id}")
    return stored == token


_LOCKOUT_MINUTES = 15

# Anti-abuse thresholds
_IP_SIGNUP_LIMIT = 3    # max new accounts per IP in 24h before hard block
_DEV_SIGNUP_LIMIT = 2   # max new accounts per device in 24h before flagging


# ── Helpers ────────────────────────────────────────────────────────────────────

_redis_client = None  # module-level client backed by a connection pool


def _get_redis():
    """Return a pooled Redis client or None if unavailable.

    This runs on EVERY authenticated request (token_in_blocklist_loader), so it
    must reuse a connection pool — previously it opened and pinged a brand-new
    TCP connection per request, adding latency and connection churn.
    """
    global _redis_client
    try:
        import redis
        if _redis_client is None:
            _redis_client = redis.from_url(
                Config.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            )
        _redis_client.ping()
        return _redis_client
    except Exception:
        # Drop the client so the next call rebuilds it (e.g. Redis restarted)
        _redis_client = None
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
    """Send verification email in a background thread (used at registration — non-blocking).
    Failures are logged to Sentry/logger; the user can resend via the dashboard."""
    from ..notifications import send_verification_email

    def _send():
        try:
            with app.app_context():
                send_verification_email(user_email, user_name, token)
        except Exception as exc:
            logger.error("Verification email failed for %s: %s", user_email, exc)
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(exc)
            except Exception:
                pass

    threading.Thread(target=_send, daemon=True).start()


# ── Anti-abuse helpers ─────────────────────────────────────────────────────────

def _hash_identifier(value: str) -> str:
    """Return HMAC-SHA256 hex digest keyed with SECRET_KEY. Prevents rainbow-table attacks on stored IP/device hashes."""
    return hmac.new(Config.SECRET_KEY.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _get_client_ip() -> str:
    """Extract real client IP.

    Only trust X-Forwarded-For when the direct TCP peer (remote_addr) is a
    known private/loopback range — i.e. we are sitting behind a local reverse
    proxy (nginx, Railway's internal router, etc.).  If the request arrives
    directly from the public internet we ignore the header to prevent spoofing.
    """
    import ipaddress

    remote = request.remote_addr or "0.0.0.0"
    try:
        remote_ip = ipaddress.ip_address(remote)
        trusted_proxy = remote_ip.is_private or remote_ip.is_loopback
    except ValueError:
        trusted_proxy = False

    if trusted_proxy:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    return remote


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
    # Platform kill-switch: admins can pause new sign-ups from the admin panel.
    from .. import platform_config as pc
    if not pc.is_feature_enabled("registrations_enabled"):
        return jsonify({
            "error": "New registrations are temporarily disabled. Please check back later.",
            "code": "REGISTRATIONS_DISABLED",
        }), 403

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

    # 1-D-05: ToS acceptance required
    if not data.get("tos_accepted"):
        return jsonify({"error": "You must accept the Terms of Service to register.", "code": "TOS_REQUIRED"}), 400

    # AUP acceptance required
    if not data.get("aup_accepted"):
        return jsonify({"error": "You must accept the Acceptable Use Policy to register.", "code": "AUP_REQUIRED"}), 400

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
        tos_version_accepted="2.0",  # 1-D-05
        tos_accepted_at=datetime.utcnow(),
        aup_accepted_at=datetime.utcnow(),
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

    # 2-D-01: start 14-day Pro trial for new users (only if no referral shortcut already set tier)
    if user.subscription_tier == "free" and not user.trial_used:
        from datetime import timedelta as _td
        user.trial_ends_at = datetime.utcnow() + _td(days=14)
        user.trial_used = True
        user.subscription_tier = "pro"

    db.session.commit()

    # Send verification email asynchronously
    try:
        from flask import current_app
        _send_verification_email_async(
            current_app._get_current_object(), email, full_name, verification_token
        )
    except Exception:
        pass

    # Send welcome email asynchronously (fire-and-forget)
    try:
        from ..notifications import send_welcome_email
        import threading
        _app = current_app._get_current_object()
        def _send_welcome():
            try:
                with _app.app_context():
                    send_welcome_email(email, full_name)
            except Exception as exc:
                logger.error("Welcome email failed for %s: %s", email, exc)
        threading.Thread(target=_send_welcome, daemon=True).start()
    except Exception:
        pass

    # Issue a limited-scope token until the user verifies their email.
    # The _enforce_email_verification middleware blocks all /api routes for
    # email_verify_pending scope except /verify-email and /resend-verification.
    token = create_access_token(
        identity=str(user.id),
        expires_delta=timedelta(hours=24),
        additional_claims={"scope": "email_verify_pending"},
    )
    refresh_token = create_refresh_token(identity=str(user.id))
    resp = jsonify({"token": token, "user": user.to_dict()})  # token also in body for TMA
    _set_auth_cookies(resp, token, refresh_token)
    return resp, 201


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

    # Password check — Telegram-only users have no password_hash
    if not user.password_hash:
        return jsonify({
            "error": "This account uses Telegram login. Open the Telegizer Mini App to sign in.",
            "code": "TELEGRAM_ONLY_ACCOUNT",
        }), 401

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

    # 2FA check — skip entirely if browser carries a valid 48-hour trusted-device token
    if user.totp_enabled and user.totp_secret and not _check_totp_trusted(user.id):
        if not totp_code:
            # Return indicator that 2FA is required; do NOT issue full JWT yet
            nonce = secrets.token_hex(16)
            _r = _get_redis()
            if _r:
                _r.setex(f"totp_nonce:{user.id}", 90, nonce)
            pending_token = create_access_token(
                identity=str(user.id),
                expires_delta=timedelta(seconds=90),
                additional_claims={"scope": "totp_pending", "nonce": nonce},
            )
            return jsonify({
                "requires_2fa": True,
                "totp_pending_token": pending_token,
            }), 200

        # Validate TOTP code (and backup codes)
        if not _verify_totp(user, totp_code):
            return jsonify({"error": "Invalid 2FA code"}), 401

    # Admin auto-promotion
    if user.email.lower() in Config.ADMIN_EMAILS and user.subscription_tier != "enterprise":
        user.subscription_tier = "enterprise"
        user.subscription_expires = None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    user_data = user.to_dict()
    _attach_admin_fields(user_data, user)
    resp = jsonify({"token": token, "user": user_data})  # token also in body for TMA
    _set_auth_cookies(resp, token, refresh_token)
    return resp, 200


# ── 2FA login completion (submit code after receives requires_2fa) ─────────────

@auth_bp.route("/verify-totp-login", methods=["POST"])
@rate_limit(requests_per_minute=3)
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
    token_nonce = decoded.get("nonce", "")
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Verify one-time nonce to prevent replay of stolen pending tokens
    _r = _get_redis()
    if _r:
        stored_nonce = _r.get(f"totp_nonce:{user.id}")
        if not stored_nonce or stored_nonce != token_nonce:
            return jsonify({"error": "Session expired or already used. Please log in again."}), 401
        # Delete nonce before TOTP check — any failure requires a fresh login
        _r.delete(f"totp_nonce:{user.id}")

    if not _verify_totp(user, totp_code):
        return jsonify({"error": "Invalid 2FA code"}), 401

    # Admin auto-promotion
    if user.email.lower() in Config.ADMIN_EMAILS and user.subscription_tier != "enterprise":
        user.subscription_tier = "enterprise"
        user.subscription_expires = None
        db.session.commit()

    token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    user_data = user.to_dict()
    _attach_admin_fields(user_data, user)
    resp = jsonify({"token": token, "user": user_data})
    _set_auth_cookies(resp, token, refresh_token)
    _set_totp_trusted_cookie(resp, user.id)  # trust this browser for 48 hours
    return resp, 200


def _verify_totp(user: User, code: str) -> bool:
    """Verify a TOTP code or a backup code against the user's credentials."""
    try:
        import pyotp
        # user.totp_secret property auto-decrypts; returns None on DecryptionError
        secret = user.totp_secret
        if not secret:
            if user._totp_secret_enc:
                logger.error("TOTP secret decryption failed for user %s — ENCRYPTION_KEY may have changed", user.id)
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
    """Return True and remove the code if it matches a stored backup code.

    Supports three storage formats (newest first):
    - List-of-dicts: [{"id": uuid, "hash": bcrypt_hash}, ...] — current format.
    - Indexed dict: {sha256_of_plain -> bcrypt_hash} — legacy format.
    - Plain list: [bcrypt_hash, ...] — oldest format.
    Rate-limited to 5 attempts/min per user via Redis.
    """
    import hashlib
    if not user.totp_backup_codes:
        return False
    code_clean = code.replace("-", "").strip().lower()

    # Rate-limit backup code attempts per user (5/min)
    _r = _get_redis()
    if _r:
        rate_key = f"backup_code_attempts:{user.id}"
        attempts = int(_r.get(rate_key) or 0)
        if attempts >= 5:
            return False  # treat as failure; caller returns 401
        _r.incr(rate_key)
        _r.expire(rate_key, 60)

    stored = user.totp_backup_codes
    matched = False
    remaining = None

    if isinstance(stored, list) and stored and isinstance(stored[0], dict):
        # Current list-of-dicts format
        remaining = []
        for entry in stored:
            if not matched:
                try:
                    if bcrypt.checkpw(code_clean.encode(), entry["hash"].encode()):
                        matched = True
                        continue  # drop this entry (single-use)
                except Exception:
                    pass
            remaining.append(entry)
    elif isinstance(stored, dict):
        # Legacy indexed-dict format
        sha = hashlib.sha256(code_clean.encode()).hexdigest()
        bcrypt_hash = stored.get(sha)
        if bcrypt_hash:
            try:
                if bcrypt.checkpw(code_clean.encode(), bcrypt_hash.encode()):
                    matched = True
                    remaining = {k: v for k, v in stored.items() if k != sha}
            except Exception:
                pass
    else:
        # Oldest list-of-hashes format
        remaining = []
        for bcrypt_hash in stored:
            if not matched:
                try:
                    if bcrypt.checkpw(code_clean.encode(), bcrypt_hash.encode()):
                        matched = True
                        continue
                except Exception:
                    pass
            remaining.append(bcrypt_hash)

    if matched and remaining is not None:
        if _r:
            _r.delete(f"backup_code_attempts:{user.id}")  # reset counter on success
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
    email = data.get("email", "").strip().lower()
    if not token:
        return jsonify({"error": "Verification token is required"}), 400

    # Per-email brute-force counter (5 failures/hr locks the email)
    _r = _get_redis()
    _email_fail_key = f"verify_fail:{email}" if email else None
    if _r and _email_fail_key:
        fails = int(_r.get(_email_fail_key) or 0)
        if fails >= 5:
            return jsonify({"error": "Too many failed verification attempts. Try again in 1 hour."}), 429

    user = User.query.filter_by(email_verification_token=token).first()
    if not user:
        if _r and _email_fail_key:
            _r.incr(_email_fail_key)
            _r.expire(_email_fail_key, 3600)
        return jsonify({"error": "Invalid or expired verification link"}), 400

    if user.email_verification_expires and datetime.utcnow() > user.email_verification_expires:
        if _r and _email_fail_key:
            _r.incr(_email_fail_key)
            _r.expire(_email_fail_key, 3600)
        return jsonify({"error": "Verification link has expired. Please request a new one."}), 400

    # Clear failure counter on success
    if _r and _email_fail_key:
        _r.delete(_email_fail_key)

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
            _referred_first_name = user.full_name.split()[0] if user.full_name else "Someone"

            def _reward():
                try:
                    with _app.app_context():
                        from ..notifications import send_referral_conversion_email
                        r = User.query.get(_referrer_id)
                        if r:
                            _apply_referral_rewards(r)
                            from ..models import Referral as _Referral
                            total = _Referral.query.filter_by(
                                referrer_user_id=r.id, status="approved"
                            ).count()
                            try:
                                send_referral_conversion_email(
                                    r.email,
                                    r.full_name.split()[0] if r.full_name else r.email,
                                    _referred_first_name,
                                    total,
                                )
                            except Exception as mail_exc:
                                logger.warning("Referral conversion email failed: %s", mail_exc)
                except Exception as exc:
                    logger.warning("Referral reward check failed: %s", exc)

            threading.Thread(target=_reward, daemon=True).start()
        except Exception:
            pass

    logger.info("Email verified for user %s", user.id)
    # Issue a full-scope JWT now that email is verified.
    # The registration endpoint issues email_verify_pending scope, so the
    # frontend needs to swap it for a real token to access protected routes.
    token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    return jsonify({
        "message": "Email verified successfully!",
        "email_verified": True,
        "token": token,
        "refresh_token": refresh_token,
        "user": user.to_dict(),
    }), 200


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

    # Cooldown: allow at most one resend per hour (token expires 24h from issue,
    # so cooldown_end = issued_at + 1h = expires_at - 23h)
    if user.email_verification_expires:
        cooldown_end = user.email_verification_expires - timedelta(hours=23)
        if datetime.utcnow() < cooldown_end:
            return jsonify({
                "error": "A verification email was sent recently. Please wait a few minutes before requesting another.",
                "code": "RESEND_COOLDOWN",
            }), 429

    verification_token = user.generate_verification_token()
    db.session.commit()

    # Send synchronously so we can report actual delivery status to the frontend
    try:
        from ..notifications import send_verification_email
        send_verification_email(user.email, user.full_name, verification_token)
    except Exception as exc:
        logger.error("Verification resend failed for user %s: %s", user.id, exc)
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass
        return jsonify({
            "error": "Failed to send verification email. Please try again later or contact support.",
            "code": "EMAIL_SEND_FAILED",
        }), 502

    return jsonify({
        "message": "Verification email sent! Check your inbox and spam folder.",
    }), 200


# ── Standard auth routes ───────────────────────────────────────────────────────

def _mark_onboarding_step(user, step):
    """Mark a single onboarding step complete for a user. Idempotent."""
    steps = list(user.onboarding_completed_steps or [])
    if step not in steps:
        steps.append(step)
        user.onboarding_completed_steps = steps
        db.session.commit()


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_me():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Lazy backfill: auto-mark onboarding steps for users who already did the actions
    try:
        steps = list(user.onboarding_completed_steps or [])
        changed = False
        if "automod_enabled" not in steps:
            from ..models import TelegramGroup
            groups = TelegramGroup.query.filter_by(owner_user_id=user.id).all()
            if any((g.settings or {}).get("automod") for g in groups):
                steps.append("automod_enabled")
                changed = True
        if "schedule_created" not in steps:
            from ..models import TelegramGroup as _TG, OfficialScheduledMessage as _OSM
            has_sched = _OSM.query.join(
                _TG, _OSM.telegram_group_id == _TG.telegram_group_id
            ).filter(_TG.owner_user_id == user.id).first()
            if has_sched:
                steps.append("schedule_created")
                changed = True
        if changed:
            user.onboarding_completed_steps = steps
            db.session.commit()
    except Exception:
        pass

    user_data = user.to_dict()
    _attach_admin_fields(user_data, user)
    return jsonify({"user": user_data}), 200


@auth_bp.route("/me", methods=["PATCH"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def update_me():
    """Update mutable profile fields: full_name, timezone."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}

    if "full_name" in data:
        name = data["full_name"].strip()
        if not name or len(name) > 255:
            return jsonify({"error": "full_name must be 1–255 characters"}), 400
        user.full_name = name

    if "timezone" in data:
        tz_str = data["timezone"].strip()
        try:
            import pytz
            pytz.timezone(tz_str)  # validates IANA timezone name
        except Exception:
            return jsonify({"error": f"Invalid timezone: {tz_str!r}. Use an IANA timezone name (e.g. 'America/New_York')."}), 400
        user.timezone = tz_str

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save profile"}), 500

    user_data = user.to_dict()
    _attach_admin_fields(user_data, user)
    return jsonify({"user": user_data}), 200


@auth_bp.route("/me/tour", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def set_tour_state():
    """Mark the product tour completed/dismissed, or reset it.

    Server-side persistence so the tour never re-appears across refreshes,
    browsers, or Telegram webview sessions (where localStorage is unreliable).
    Body: {"completed": true|false}. Reset (false) is used by Settings →
    Retake Onboarding Tour.
    """
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    user.onboarding_tour_completed = bool(data.get("completed", True))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to save tour state"}), 500

    return jsonify({"onboarding_tour_completed": user.onboarding_tour_completed}), 200


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
        try:
            PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({"used": True})
            db.session.flush()

            raw_token, reset_token = PasswordResetToken.create_for_user(user.id)
            db.session.add(reset_token)
            db.session.commit()
        except Exception as db_exc:
            db.session.rollback()
            logger.error("Failed to create password reset token for user %s: %s", user.id, db_exc)
            # Return generic 200 — never reveal internal errors to the client
            return jsonify({"message": "If that email exists, a reset link has been sent."}), 200

        try:
            from flask import current_app
            from ..notifications import send_password_reset_email
            _app = current_app._get_current_object()
            _uemail, _uname = user.email, user.full_name

            def _send_reset():
                try:
                    with _app.app_context():
                        send_password_reset_email(_uemail, _uname, raw_token)
                except Exception as exc:
                    logger.error("Password reset email failed for %s: %s", _uemail, exc)
                    try:
                        import sentry_sdk
                        sentry_sdk.capture_exception(exc)
                    except Exception:
                        pass

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

    reset_token = PasswordResetToken.find_valid(token_str)
    if not reset_token:
        return jsonify({"error": "Invalid or expired reset token"}), 400

    user = User.query.get(reset_token.user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Mark token used BEFORE updating password in the same transaction.
    # This closes the race window where two simultaneous requests with the
    # same token both pass the validity check before either commits.
    try:
        reset_token.used = True
        db.session.flush()  # acquires row lock before password update
        user.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to reset password. Please try again."}), 500

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

    if not user.password_hash:
        return jsonify({"error": "This account uses Telegram login and has no password set.", "code": "TELEGRAM_ONLY_ACCOUNT"}), 400
    if not bcrypt.checkpw(current_password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return jsonify({"error": "Current password is incorrect"}), 401

    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400
    if len(new_password) > 128:
        return jsonify({"error": "Password too long"}), 400

    user.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.session.commit()

    return jsonify({"message": "Password updated successfully"}), 200


def _purge_user_data(user):
    """Delete or detach every row referencing users.id that has no DB-level
    ON DELETE CASCADE. Without this, db.session.delete(user) raises
    IntegrityError for any active account — breaking the GDPR right to erasure
    promised in the Privacy Policy.

    Order matters only loosely: user-scoped bulk deletes are independent;
    TelegramGroup/CustomBot are deleted as ORM instances so their own
    child-cascade relationships fire.
    """
    from ..models import (
        PasswordResetToken, UserApiKey, PendingInvoice, PaymentHistory,
        SubscriptionRenewal, PromoCode, PromoCodeUsage, UserNotification,
        Note, DigestLog, BotDMMessage, PendingReminderState, Task,
        AutoReplyLog, WorkspaceKnowledgeDocument, Meeting,
        AssistantConversationState, WorkspaceReminder, AutomationWorkflow,
        ForwardRule, CustomBot, TelegramGroup, TelegramGroupLinkCode,
        AutoResponse, InviteLink, SuspiciousActivity, EngagementCampaign,
        PlatformSetting, ComplianceRequest,
    )
    from ..assistant.hub_models import HubExtractionBatch

    uid = user.id

    # Owned content — hard delete (right to erasure).
    for model, col in [
        (PasswordResetToken, PasswordResetToken.user_id),
        (UserApiKey, UserApiKey.user_id),
        (PendingInvoice, PendingInvoice.user_id),
        (PaymentHistory, PaymentHistory.user_id),
        (SubscriptionRenewal, SubscriptionRenewal.user_id),
        (PromoCodeUsage, PromoCodeUsage.user_id),
        (UserNotification, UserNotification.user_id),
        (Note, Note.user_id),
        (DigestLog, DigestLog.user_id),
        (BotDMMessage, BotDMMessage.user_id),
        (PendingReminderState, PendingReminderState.user_id),
        (Task, Task.user_id),
        (AutoReplyLog, AutoReplyLog.user_id),
        (WorkspaceKnowledgeDocument, WorkspaceKnowledgeDocument.user_id),
        (Meeting, Meeting.owner_user_id),
        (AssistantConversationState, AssistantConversationState.user_id),
        (WorkspaceReminder, WorkspaceReminder.owner_user_id),
        (AutomationWorkflow, AutomationWorkflow.owner_user_id),
        (ForwardRule, ForwardRule.owner_user_id),
        (HubExtractionBatch, HubExtractionBatch.user_id),
    ]:
        model.query.filter(col == uid).delete(synchronize_session=False)

    # Referrals reference the user from both sides.
    Referral.query.filter(
        (Referral.referrer_user_id == uid) | (Referral.referred_user_id == uid)
    ).delete(synchronize_session=False)

    # Group/bot configurations — instance deletes so ORM child cascades
    # (members, commands, warnings, events, ...) fire.
    for grp in TelegramGroup.query.filter_by(owner_user_id=uid).all():
        db.session.delete(grp)
    for cbot in CustomBot.query.filter_by(owner_user_id=uid).all():
        db.session.delete(cbot)

    # Nullable references — detach instead of deleting shared/audit rows.
    TelegramGroupLinkCode.query.filter_by(user_id=uid).update(
        {"user_id": None}, synchronize_session=False)
    AutoResponse.query.filter_by(owner_user_id=uid).update(
        {"owner_user_id": None}, synchronize_session=False)
    InviteLink.query.filter_by(created_by_user_id=uid).update(
        {"created_by_user_id": None}, synchronize_session=False)
    SuspiciousActivity.query.filter_by(user_id=uid).update(
        {"user_id": None}, synchronize_session=False)
    EngagementCampaign.query.filter_by(owner_user_id=uid).update(
        {"owner_user_id": None}, synchronize_session=False)
    PromoCode.query.filter_by(created_by_user_id=uid).update(
        {"created_by_user_id": None}, synchronize_session=False)
    PlatformSetting.query.filter_by(updated_by=uid).update(
        {"updated_by": None}, synchronize_session=False)
    ComplianceRequest.query.filter_by(user_id=uid).update(
        {"user_id": None}, synchronize_session=False)
    ComplianceRequest.query.filter_by(handled_by=uid).update(
        {"handled_by": None}, synchronize_session=False)


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

    if not user.password_hash:
        return jsonify({"error": "This account uses Telegram login. Use the Mini App to manage your account.", "code": "TELEGRAM_ONLY_ACCOUNT"}), 400
    if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return jsonify({"error": "Incorrect password"}), 401

    if user.email and user.email.lower() in Config.ADMIN_EMAILS:
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

    try:
        _purge_user_data(user)
        db.session.delete(user)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("Account deletion failed for user %s: %s", user.id, exc, exc_info=True)
        return jsonify({
            "error": "Account deletion failed. Please contact support@telegizer.com and we will delete your account manually.",
            "code": "DELETE_FAILED",
        }), 500
    return jsonify({"message": "Account deleted successfully"}), 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
@rate_limit(requests_per_minute=20)
def refresh_access_token():
    """Issue a new access token using a valid refresh token."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user or user.is_banned:
        return jsonify({"error": "User not found"}), 404
    new_token = create_access_token(identity=str(user_id))
    resp = jsonify({"token": new_token})
    _set_auth_cookies(resp, new_token)  # rotate access cookie; refresh cookie untouched
    return resp, 200


@auth_bp.route("/onboarding", methods=["PATCH"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_onboarding():
    """2-B-01: Mark onboarding steps as completed. Body: { "step": "email_verified" }"""
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = request.get_json(silent=True) or {}
    step = body.get("step")
    valid_steps = {"email_verified", "bot_connected", "group_linked", "feature_configured", "ai_enabled", "automod_enabled", "schedule_created"}
    if step and step in valid_steps:
        steps = list(user.onboarding_completed_steps or [])
        if step not in steps:
            steps.append(step)
            user.onboarding_completed_steps = steps
            db.session.commit()
    return jsonify({"onboarding_completed_steps": user.onboarding_completed_steps or []}), 200


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
    resp = jsonify({"message": "Logged out successfully"})
    _clear_auth_cookies(resp)
    return resp, 200
