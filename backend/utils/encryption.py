import base64
import hashlib
import os
import logging

logger = logging.getLogger(__name__)


def _get_fernet():
    from cryptography.fernet import Fernet
    secret = os.environ.get("SECRET_KEY", "fallback-secret-key-change-in-production")
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
    if not ciphertext:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        return ""


def mask_key(key: str) -> str:
    """Return masked version: first 4 chars + **** + last 4 chars."""
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]
