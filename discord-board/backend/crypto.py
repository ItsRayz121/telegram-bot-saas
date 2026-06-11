"""Fernet encryption for custom-bot tokens at rest. Self-contained — no Telegizer imports.

Key comes from GUILDIZER_ENCRYPTION_KEY (a Fernet key: 32 url-safe base64 bytes,
generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
If unset, a key is derived from FLASK_SECRET_KEY so local dev works without setup —
fine for dev, but production must set a real key: rotating the Flask secret would
otherwise orphan every stored token.
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from config import Config

log = logging.getLogger("guildizer.crypto")

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = Config.ENCRYPTION_KEY
        if not key:
            log.warning(
                "GUILDIZER_ENCRYPTION_KEY not set — deriving from FLASK_SECRET_KEY. "
                "Set a dedicated key in production."
            )
            digest = hashlib.sha256(Config.SECRET_KEY.encode()).digest()
            key = base64.urlsafe_b64encode(digest).decode()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_token(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_token(ciphertext: str) -> str | None:
    """Decrypt a stored token. Returns None (never raises) if the key changed
    or the value is corrupt — callers mark the bot status=error instead of crashing."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        log.error("Failed to decrypt a stored bot token (key changed or value corrupt).")
        return None
