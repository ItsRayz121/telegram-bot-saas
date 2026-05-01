"""
Resolves which AI key + provider to use for workspace-level assistant features
(Notes, Digests, Hub). Priority: user's workspace key → platform Gemini key.
"""

from .. import config as _cfg


def get_workspace_ai_key(user) -> dict:
    """Return { provider, api_key, model } for the given user's workspace.

    Checks for a workspace-scoped UserApiKey first; falls back to the
    platform-wide Gemini Flash key from environment config.
    """
    from ..models import UserApiKey

    user_key = (
        UserApiKey.query
        .filter_by(user_id=user.id, scope="workspace", is_active=True)
        .order_by(UserApiKey.updated_at.desc())
        .first()
    )

    if user_key:
        from ..utils.encryption import decrypt_value, DecryptionError
        import logging
        try:
            api_key = decrypt_value(user_key.api_key_encrypted)
        except DecryptionError:
            logging.getLogger(__name__).error(
                "ai_key_resolver: workspace key decryption failed for user %s — falling back to platform key", user.id
            )
            api_key = None
        if api_key:
            return {
                "provider": user_key.provider,
                "api_key": api_key,
                "model": user_key.model_name or _default_model(user_key.provider),
                "source": "user",
            }

    return {
        "provider": "gemini",
        "api_key": _cfg.Config.PLATFORM_GEMINI_API_KEY,
        "model": "gemini-2.0-flash",
        "source": "platform",
    }


def _default_model(provider: str) -> str:
    defaults = {
        "gemini": "gemini-2.0-flash",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-haiku-4-5-20251001",
        "openrouter": "google/gemini-flash-1.5",
    }
    return defaults.get(provider, "")
