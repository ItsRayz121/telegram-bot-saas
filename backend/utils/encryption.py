import base64
import hashlib
import os
import logging

logger = logging.getLogger(__name__)


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
    if not plaintext:
        return ""
    try:
        return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        return ""


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted value.

    Tries ENCRYPTION_KEY first, then legacy keys (ENCRYPTION_KEY_OLD / SECRET_KEY)
    for backward compatibility during key rotation.  Falls back to returning the
    raw value unchanged so callers continue to work with any pre-encryption
    plaintext rows still in the DB.
    """
    if not ciphertext:
        return ""

    # Primary key
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        pass

    # Legacy keys (key rotation / first deployment after adding ENCRYPTION_KEY)
    for f in _get_legacy_fernets():
        try:
            return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except Exception:
            pass

    # Final fallback: plaintext stored before encryption was introduced.
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
