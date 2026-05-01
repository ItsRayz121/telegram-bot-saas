import base64
import hashlib
import hmac
import os
import logging

logger = logging.getLogger(__name__)


class DecryptionError(Exception):
    """Raised when a ciphertext cannot be decrypted with any available key.

    Callers must handle this explicitly — never silently swallow it, as doing
    so would surface raw ciphertext as a value (e.g. a bot token or TOTP secret)
    which would then silently fail downstream in a very confusing way.
    """


def _fernet_from_secret(secret: str):
    from cryptography.fernet import Fernet
    key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def _get_fernet():
    """Return Fernet instance keyed from ENCRYPTION_KEY (required)."""
    secret = os.environ.get("ENCRYPTION_KEY")
    if not secret:
        raise RuntimeError(
            "ENCRYPTION_KEY environment variable is required for token encryption. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "Migration: set ENCRYPTION_KEY_OLD to your current SECRET_KEY value so existing "
            "encrypted records continue to decrypt during the transition period."
        )
    return _fernet_from_secret(secret)


def _get_legacy_fernets():
    """Return Fernet instances for backward-compatible decryption during key rotation.

    Priority order:
      1. ENCRYPTION_KEY_OLD  — explicit old encryption key (set this when rotating)
      2. SECRET_KEY          — original fallback used before ENCRYPTION_KEY existed

    Once all encrypted records have been re-saved under ENCRYPTION_KEY these
    env vars can be removed.
    """
    candidates = []
    old = os.environ.get("ENCRYPTION_KEY_OLD") or os.environ.get("SECRET_KEY")
    if old:
        try:
            candidates.append(_fernet_from_secret(old))
        except Exception:
            pass
    return candidates


def encrypt_value(plaintext: str) -> str:
    """Encrypt plaintext with the current ENCRYPTION_KEY.

    Raises RuntimeError if ENCRYPTION_KEY is not configured.
    Raises EncryptionError on any other failure — never silently returns empty string.
    """
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str, _re_encrypt_callback=None) -> str:
    """Decrypt a Fernet-encrypted value.

    Tries ENCRYPTION_KEY first, then legacy keys (ENCRYPTION_KEY_OLD / SECRET_KEY)
    for backward compatibility during key rotation.

    Args:
        ciphertext: The encrypted value from the database.
        _re_encrypt_callback: Optional callable(new_ciphertext) — called when the
            value was decrypted with a legacy key so the caller can re-save it
            under the current key, enabling eventual old-key retirement.

    Raises:
        DecryptionError: If no available key can decrypt the ciphertext. Callers
            must handle this — never swallow it silently.
    """
    if not ciphertext:
        return ""

    from cryptography.fernet import InvalidToken

    # Primary key
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        pass

    # Legacy keys — try each; if successful, optionally re-encrypt under current key
    for f in _get_legacy_fernets():
        try:
            plaintext = f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
            if _re_encrypt_callback is not None:
                try:
                    new_ciphertext = encrypt_value(plaintext)
                    _re_encrypt_callback(new_ciphertext)
                except Exception as cb_exc:
                    logger.warning("decrypt_value: re-encrypt callback failed: %s", cb_exc)
            return plaintext
        except (InvalidToken, Exception):
            pass

    raise DecryptionError(
        "Failed to decrypt value with any available key. "
        "Check ENCRYPTION_KEY config and ensure ENCRYPTION_KEY_OLD is set during rotation."
    )


def startup_encryption_selfcheck(app):
    """Run a round-trip encryption self-check at app startup.

    Call this once inside create_app() after db.init_app(app).
    Logs a CRITICAL error (and captures to Sentry) if the current key cannot
    encrypt and then decrypt a test value — this would mean ALL encrypted fields
    in the database are broken.

    Also spot-checks any CustomBot tokens to detect silent key-rotation corruption.
    """
    sentinel = "telegizer-selfcheck-ok"
    try:
        ct = encrypt_value(sentinel)
        pt = decrypt_value(ct)
        assert pt == sentinel, f"Round-trip mismatch: got {pt!r}"
        logger.info("[startup] Encryption self-check passed.")
    except Exception as e:
        logger.critical(
            "[startup] ENCRYPTION SELF-CHECK FAILED — encrypted fields may be unreadable. "
            "Error: %s", e
        )
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(e)
        except Exception:
            pass
        return

    # Spot-check bot tokens — runs inside the app context
    with app.app_context():
        try:
            from ..models import CustomBot
            broken = []
            for bot in CustomBot.query.limit(50).all():
                try:
                    token = bot.get_token()
                    if not token or ":" not in token or len(token) < 20:
                        broken.append(bot.id)
                except Exception:
                    broken.append(bot.id)
            if broken:
                msg = f"[startup] CustomBot token decrypt failed for bot IDs: {broken}"
                logger.critical(msg)
                try:
                    import sentry_sdk
                    sentry_sdk.capture_message(msg, level="critical")
                except Exception:
                    pass
            else:
                logger.info("[startup] CustomBot token spot-check passed (%d bots checked).", min(50, CustomBot.query.count()))
        except Exception as e:
            logger.warning("[startup] Could not run CustomBot token spot-check: %s", e)


def hash_token(token: str) -> str:
    """Return HMAC-SHA256 hex digest keyed with ENCRYPTION_KEY for uniqueness checks.
    Prevents rainbow-table attacks on stored token hashes."""
    if not token:
        return ""
    key = os.environ.get("ENCRYPTION_KEY") or os.environ.get("SECRET_KEY", "")
    return hmac.new(key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def mask_key(key: str) -> str:
    """Return masked version: first 4 chars + **** + last 4 chars."""
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]
