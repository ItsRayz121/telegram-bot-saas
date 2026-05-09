"""
Thin encrypt/decrypt wrappers for Assistant Hub content fields.

All Hub "ENCRYPTED" fields must go through _enc() on write and _dec() on read.
Falls back to plaintext if ENCRYPTION_KEY is not set (dev only — prod requires it).
"""
import logging
import os

_log = logging.getLogger(__name__)
_WARN_ONCE = False


def _enc(value: str | None) -> str | None:
    """Encrypt a string for storage. Returns None if input is None/empty."""
    if not value:
        return value
    if not os.environ.get("ENCRYPTION_KEY"):
        _warn_missing_key()
        return value
    try:
        from ..utils.encryption import encrypt_value
        return encrypt_value(value)
    except Exception as exc:
        _log.error("hub_crypto: encryption failed: %s", exc)
        raise


def _dec(value: str | None) -> str | None:
    """Decrypt a stored string. Returns the raw value if ENCRYPTION_KEY is absent (dev fallback)."""
    if not value:
        return value
    if not os.environ.get("ENCRYPTION_KEY"):
        return value
    try:
        from ..utils.encryption import decrypt_value, DecryptionError
        return decrypt_value(value)
    except Exception:
        # If decryption fails (e.g. plaintext legacy row), return as-is
        return value


def _warn_missing_key():
    global _WARN_ONCE
    if not _WARN_ONCE:
        _log.warning(
            "ENCRYPTION_KEY not set — Hub content fields stored as plaintext. "
            "Set ENCRYPTION_KEY in production."
        )
        _WARN_ONCE = True
