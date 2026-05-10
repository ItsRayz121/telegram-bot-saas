"""
Resolves which AI key + provider to use for any AI feature.

Single source of truth — all paths:
  resolve_ai_provider_for_group(user_id, group_id, telegram_group_id)
      → group key → workspace key → platform key
  get_workspace_ai_key(user)
      → workspace key → platform key
"""

from datetime import datetime, timedelta
from .. import config as _cfg


def resolve_ai_provider_for_group(user_id: int, group_id=None, telegram_group_id=None) -> dict:
    """Single resolver for ALL group-scoped AI calls (KB, embeddings, hub reply, extraction).

    Priority:
      1. Group-specific UserApiKey
      2. User's workspace UserApiKey
      3. Platform OpenRouter key (quota enforced by tier)

    Returns { provider, api_key, model, base_url, source }
    Raises QuotaExceededError if on platform key and quota exhausted.
    Returns { api_key: "" } if nothing is configured.
    """
    from ..models import UserApiKey, User
    from ..utils.encryption import decrypt_value, DecryptionError
    import logging
    _log = logging.getLogger(__name__)

    # 1. Group-specific key
    try:
        q = UserApiKey.query.filter_by(is_active=True)
        if telegram_group_id:
            q = q.filter_by(telegram_group_id=str(telegram_group_id))
        elif group_id:
            q = q.filter_by(group_id=group_id)
        else:
            q = None

        if q is not None:
            record = q.order_by(UserApiKey.created_at.desc()).first()
            if record:
                try:
                    api_key = decrypt_value(record.api_key_encrypted)
                    if api_key:
                        return {
                            "provider": record.provider,
                            "api_key": api_key,
                            "model": record.model_name or _default_model(record.provider),
                            "base_url": record.base_url or _default_base_url(record.provider),
                            "source": "group",
                        }
                except DecryptionError:
                    _log.error("resolve_ai_provider_for_group: group key decryption failed group=%s", group_id or telegram_group_id)
    except Exception as exc:
        _log.warning("resolve_ai_provider_for_group: group key lookup failed: %s", exc)

    # 2+3. Workspace key → platform key via existing resolver
    user = User.query.get(user_id)
    if not user:
        return {"api_key": "", "provider": "openai", "model": "gpt-4o-mini", "source": "none"}

    return get_workspace_ai_key(user)


class QuotaExceededError(Exception):
    """Raised when a user's daily platform AI token quota is exhausted."""


def get_workspace_ai_key(user) -> dict:
    """Return { provider, api_key, model } for the given user's workspace.

    Checks for a workspace-scoped UserApiKey first; falls back to the
    platform-wide OpenRouter key from environment config.

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
    tier = user.subscription_tier
    daily_limit = 500000 if tier == "enterprise" else (200000 if tier == "pro" else 10000)
    if user.workspace_ai_tokens_today >= daily_limit:
        raise QuotaExceededError(
            f"Daily AI token limit ({daily_limit:,}) reached. "
            "Quota resets in 24 hours or add your own API key in AI Settings."
        )

    if _cfg.Config.PLATFORM_OPENROUTER_API_KEY:
        return {
            "provider": "openrouter",
            "api_key": _cfg.Config.PLATFORM_OPENROUTER_API_KEY,
            "model": "openai/gpt-4o-mini",
            "base_url": "https://openrouter.ai/api/v1",
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
        "custom": "gpt-4o-mini",
    }
    return defaults.get(provider, "")


def _default_base_url(provider: str) -> str:
    defaults = {
        "openrouter": "https://openrouter.ai/api/v1",
        "anthropic": "https://api.anthropic.com",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
    }
    return defaults.get(provider, "")
