"""
Resolves which AI key + provider to use for any AI feature.

Single source of truth — all paths:
  resolve_ai_provider_for_group(user_id, group_id, telegram_group_id)
      → group key → workspace key → platform key
  get_workspace_ai_key(user)
      → workspace key → platform key
"""

import logging
from datetime import datetime, date, timedelta
from .. import config as _cfg

_log = logging.getLogger(__name__)

# ─── Custom exceptions ────────────────────────────────────────────────────────

class QuotaExceededError(Exception):
    """Raised when a user's daily platform AI token quota is exhausted."""


class PlatformCostLimitError(Exception):
    """Raised when the platform's daily AI spend budget is reached."""


# ─── Redis helpers ────────────────────────────────────────────────────────────

def _get_redis():
    try:
        import redis as _redis
        from flask import current_app
        r = _redis.from_url(
            current_app.config.get("REDIS_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=1, socket_timeout=1,
        )
        r.ping()
        return r
    except Exception:
        return None


def _redis_check_and_increment(user_id: int, daily_limit: int):
    """Atomically increment the user's daily AI token counter via Redis INCR.

    Returns:
        True  — under the limit (request allowed)
        False — limit exceeded (request blocked)
        None  — Redis unavailable (caller should fall back to DB check)
    """
    r = _get_redis()
    if r is None:
        return None  # signal fallback
    try:
        key = f"ai_tokens:{user_id}:{date.today().isoformat()}"
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)
        results = pipe.execute()
        count = results[0]
        return count <= daily_limit
    except Exception as exc:
        _log.warning("ai_key_resolver: Redis token check error: %s", exc)
        return None


def _check_platform_cost_circuit():
    """Raise PlatformCostLimitError if the daily platform AI spend limit is hit."""
    from .. import ai_config
    limit = ai_config.daily_spend_cap()
    r = _get_redis()
    if r is None:
        return  # Redis down — allow request
    try:
        key = f"platform_ai_spend:{date.today().isoformat()}"
        current_spend = float(r.get(key) or 0)
        if current_spend >= limit:
            _log.warning("Platform AI cost circuit OPEN: $%.4f >= $%.2f today", current_spend, limit)
            raise PlatformCostLimitError(
                "Platform AI temporarily unavailable (daily budget reached). "
                "Add your own API key in AI Settings to continue."
            )
    except PlatformCostLimitError:
        raise
    except Exception as exc:
        _log.debug("_check_platform_cost_circuit: Redis error: %s", exc)


def record_platform_cost(tokens_used: int) -> None:
    """Add estimated USD cost for a platform-key call to the daily Redis counter."""
    r = _get_redis()
    if r is None:
        return
    try:
        # gpt-4o-mini: ~$0.15 / 1M tokens (blended input+output estimate)
        cost = tokens_used * 0.00000015
        key = f"platform_ai_spend:{date.today().isoformat()}"
        pipe = r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, 86400)
        pipe.execute()
    except Exception as exc:
        _log.debug("record_platform_cost: Redis error: %s", exc)


# ─── Main resolvers ───────────────────────────────────────────────────────────

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
        elif group_id is not None:
            # UserApiKey.group_id is an INTEGER FK to telegram_groups.id. Guard against
            # a non-integer id (e.g. a Hub connected-group UUID) so a bad caller can't
            # issue an invalid-integer query that aborts the whole DB transaction.
            try:
                q = q.filter_by(group_id=int(group_id))
            except (TypeError, ValueError):
                q = None
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
        # A failed query leaves the session in an aborted-transaction state, which
        # would make every subsequent query (workspace lookup, batch writes) fail
        # with "current transaction is aborted". Roll back so the fallback can run.
        try:
            from ..models import db
            db.session.rollback()
        except Exception:
            pass

    # 2+3. Workspace key → platform key via existing resolver
    user = User.query.get(user_id)
    if not user:
        return {"api_key": "", "provider": "openai", "model": "gpt-4o-mini", "source": "none"}

    return get_workspace_ai_key(user)


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

    # Platform key path — enforce daily quota (Redis-atomic) + cost circuit breaker.
    # Per-tier limits are admin-editable (ai_config), DB-first with the same
    # hardcoded defaults as before.
    from .. import ai_config
    tier = user.subscription_tier
    daily_limit = ai_config.daily_token_limit(tier)

    # 1. Platform cost circuit breaker — hard stop if daily budget exceeded
    _check_platform_cost_circuit()

    # 2. Per-user quota — atomic Redis INCR (race-condition safe)
    redis_result = _redis_check_and_increment(user.id, daily_limit)
    if redis_result is False:
        raise QuotaExceededError(
            f"Daily AI token limit ({daily_limit:,}) reached. "
            "Quota resets in 24 hours or add your own API key in AI Settings."
        )
    if redis_result is None:
        # Redis unavailable — fall back to DB check (existing behavior)
        _check_and_reset_quota(user)
        if user.workspace_ai_tokens_today >= daily_limit:
            raise QuotaExceededError(
                f"Daily AI token limit ({daily_limit:,}) reached. "
                "Quota resets in 24 hours or add your own API key in AI Settings."
            )

    # Resolve the platform key DB-first (admin vault) with env fallback so it can
    # be rotated from the admin panel without a redeploy.
    from .. import secret_vault as _sv
    _platform_key = _sv.get_secret("PLATFORM_OPENROUTER_API_KEY")
    if _platform_key:
        return {
            "provider": "openrouter",
            "api_key": _platform_key,
            "model": ai_config.default_model(),
            "base_url": ai_config.default_base_url(),
            "source": "platform",
            "daily_limit": daily_limit,
        }

    return {"api_key": "", "provider": "openrouter", "model": "openai/gpt-4o-mini", "source": "platform"}


def record_token_usage(user, tokens_used: int):
    """Increment the user's daily platform token counter after a successful call.

    Call this only when source == "platform"; user-key usage is not tracked here.
    Also increments the platform-wide cost estimate in Redis.
    """
    from ..models import db
    # DB counter (kept for reporting/admin visibility)
    _check_and_reset_quota(user)
    user.workspace_ai_tokens_today = (user.workspace_ai_tokens_today or 0) + tokens_used
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    # Platform cost tracker in Redis
    record_platform_cost(tokens_used)


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
