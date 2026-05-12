"""
Redis-backed circuit breaker for external AI provider calls.

States:
  CLOSED  — normal operation, requests go through
  OPEN    — failure threshold hit, requests fail fast for OPEN_DURATION_S
  HALF-OPEN — auto-reset after OPEN_DURATION_S, next request is a probe

Usage:
    from ..utils.circuit_breaker import is_open, record_failure, record_success, AICircuitOpenError

    if is_open(provider):
        raise AICircuitOpenError(provider)
    try:
        result = call_ai_api(...)
        record_success(provider)
        return result
    except Exception:
        record_failure(provider)
        raise
"""
import logging

_log = logging.getLogger(__name__)

FAILURE_THRESHOLD = 3   # failures within FAILURE_WINDOW_S to open circuit
FAILURE_WINDOW_S  = 60  # sliding window for failure counting
OPEN_DURATION_S   = 300 # circuit stays open for 5 min (then auto half-open)


class AICircuitOpenError(Exception):
    """Raised when a provider's circuit is open — fail fast, don't call API."""
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(
            f"AI provider '{provider}' is temporarily unavailable. "
            "Please try again in a few minutes."
        )


def _get_redis():
    try:
        import redis as _redis
        from flask import current_app
        r = _redis.from_url(
            current_app.config.get("REDIS_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        r.ping()
        return r
    except Exception as exc:
        _log.debug("circuit_breaker: Redis unavailable (%s) — circuit always CLOSED", exc)
        return None


def is_open(provider: str) -> bool:
    """Return True if the circuit is OPEN (requests should fail fast)."""
    r = _get_redis()
    if r is None:
        return False  # can't check → assume closed
    try:
        return bool(r.exists(f"circuit_open:{provider}"))
    except Exception:
        return False


def record_failure(provider: str) -> None:
    """Increment failure counter. Open circuit if threshold reached."""
    r = _get_redis()
    if r is None:
        return
    try:
        key_failures = f"circuit_failures:{provider}"
        key_open     = f"circuit_open:{provider}"
        pipe = r.pipeline()
        pipe.incr(key_failures)
        pipe.expire(key_failures, FAILURE_WINDOW_S)
        results = pipe.execute()
        count = results[0]
        if count >= FAILURE_THRESHOLD:
            r.setex(key_open, OPEN_DURATION_S, 1)
            _log.warning(
                "circuit_breaker: OPENED for provider=%s (failures=%d in %ds window)",
                provider, count, FAILURE_WINDOW_S,
            )
    except Exception as exc:
        _log.debug("circuit_breaker: record_failure error: %s", exc)


def record_success(provider: str) -> None:
    """Reset circuit state on a successful call."""
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(f"circuit_failures:{provider}", f"circuit_open:{provider}")
    except Exception as exc:
        _log.debug("circuit_breaker: record_success error: %s", exc)
