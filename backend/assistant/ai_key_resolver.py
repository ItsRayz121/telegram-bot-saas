"""
Resolves which AI key + provider to use for workspace-level assistant features
(Notes, Digests, Hub). Priority: user's workspace key → platform Gemini key.
"""

from datetime import datetime, timedelta
from .. import config as _cfg


class QuotaExceededError(Exception):
    """Raised when a user's daily platform AI token quota is exhausted."""


def get_workspace_ai_key(user) -> dict:
    """Return { provider, api_key, model } for the given user's workspace.

    Checks for a workspace-scoped UserApiKey first; falls back to the
    platform-wide Gemini Flash key from environment config.

    Raises QuotaExceededError if the user has no personal key and the platform
    key daily quota is exhausted.
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

    # Platform key path — enforce daily quota
    _check_and_reset_quota(user)
    daily_limit = 500000 if user.subscription_tier in ("pro", "enterprise") else 10000
    if user.workspace_ai_tokens_today >= daily_limit:
        raise QuotaExceededError(
            f"Daily AI token limit ({daily_limit:,}) reached. "
            "Quota resets in 24 hours or add your own API key in AI Settings."
        )

    # Priority: Ollama (self-hosted) → OpenRouter gpt-4o-mini → direct OpenAI gpt-4o-mini
    if _cfg.Config.PLATFORM_OLLAMA_BASE_URL:
        return {
            "provider": "ollama",
            "api_key": _cfg.Config.PLATFORM_OLLAMA_API_KEY,
            "model": _cfg.Config.PLATFORM_OLLAMA_MODEL,
            "base_url": _cfg.Config.PLATFORM_OLLAMA_BASE_URL.rstrip("/"),
            "source": "platform",
            "daily_limit": daily_limit,
        }

    if _cfg.Config.PLATFORM_OPENROUTER_API_KEY:
        return {
            "provider": "openrouter",
            "api_key": _cfg.Config.PLATFORM_OPENROUTER_API_KEY,
            "model": "openai/gpt-4o-mini",
            "base_url": "https://openrouter.ai/api/v1",
            "source": "platform",
            "daily_limit": daily_limit,
        }

    if _cfg.Config.PLATFORM_OPENAI_API_KEY:
        return {
            "provider": "openai",
            "api_key": _cfg.Config.PLATFORM_OPENAI_API_KEY,
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "source": "platform",
            "daily_limit": daily_limit,
        }

    return {"api_key": "", "provider": "openrouter", "model": "openai/gpt-4o-mini", "source": "platform"}


def record_token_usage(user, tokens_used: int):
    """Increment the user's daily platform token counter after a successful call.

    Call this only when source == "platform"; user-key usage is not tracked here.
    """
    from ..models import db
    _check_and_reset_quota(user)
    user.workspace_ai_tokens_today = (user.workspace_ai_tokens_today or 0) + tokens_used
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _check_and_reset_quota(user):
    """Reset the daily counter if 24 hours have elapsed since last reset."""
    from ..models import db
    now = datetime.utcnow()
    if (
        user.workspace_ai_tokens_reset_at is None
        or (now - user.workspace_ai_tokens_reset_at).total_seconds() >= 86400
    ):
        user.workspace_ai_tokens_today = 0
        user.workspace_ai_tokens_reset_at = now
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def _default_model(provider: str) -> str:
    defaults = {
        "gemini": "gemini-1.5-flash",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-haiku-4-5-20251001",
        "openrouter": "openai/gpt-4o-mini",
        "ollama": "llama3.2",
    }
    return defaults.get(provider, "")
