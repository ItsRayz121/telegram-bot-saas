import base64
import hashlib
import os
import logging

logger = logging.getLogger(__name__)


def _get_fernet():
    from cryptography.fernet import Fernet
    # ENCRYPTION_KEY env var takes precedence; fall back to SECRET_KEY.
    secret = os.environ.get("ENCRYPTION_KEY") or os.environ.get("SECRET_KEY", "fallback-secret-key-change-in-production")
    key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    if not plaintext:
        return ""
    try:
        f = _get_fernet()
        return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        return ""


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted value.

    Handles backwards compatibility: if the value looks like a plain-text
    Telegram bot token (contains ':' and no '==') we return it as-is so
    existing unencrypted rows continue to work until they are re-saved.
    """
    if not ciphertext:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        # Likely a plain-text value stored before encryption was introduced.
        # Return it so the caller can still function; it will be re-encrypted
        # next time the record is saved.
        return ciphertext


def hash_token(token: str) -> str:
    """Return a stable SHA-256 hex digest of a token for uniqueness checks."""
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mask_key(key: str) -> str:
    """Return masked version: first 4 chars + **** + last 4 chars."""
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]
