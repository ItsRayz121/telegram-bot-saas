import time
import threading
import functools
import logging
from flask import request, jsonify, current_app

logger = logging.getLogger(__name__)

# ─── In-process fallback rate limiter ────────────────────────────────────────
# Used when Redis is unavailable.  Counts requests per (endpoint, identifier)
# within a rolling 60-second window.  Not shared across gunicorn workers, but
# still protects against abuse on the single process handling the request.

_fallback_lock = threading.Lock()
_fallback_counts: dict = {}   # key -> list[float]   (timestamps)


def _fallback_check(key: str, limit: int) -> bool:
    """Return True if the request should be allowed, False if rate-limited."""
    now = time.time()
    window_start = now - 60.0
    with _fallback_lock:
        timestamps = [t for t in _fallback_counts.get(key, []) if t > window_start]
        if len(timestamps) >= limit:
            _fallback_counts[key] = timestamps
            return False
        timestamps.append(now)
        _fallback_counts[key] = timestamps
        return True


# ─── Client IP resolution ─────────────────────────────────────────────────────
# Railway (and most PaaS) puts the real client IP in X-Forwarded-For.
# We trust only the last address added by the first trusted proxy hop.
# Never trust all XFF headers blindly — an attacker can forge the leftmost entries.

_TRUSTED_PROXY_DEPTH = 1   # number of proxy hops we trust


def _get_client_ip() -> str:
    """Return the real client IP, respecting a single trusted proxy hop."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        # XFF format: "client, proxy1, proxy2"
        # The rightmost entry is added by our trusted proxy; everything to the
        # left of that is from the previous hop.
        parts = [p.strip() for p in xff.split(",")]
        # With TRUSTED_PROXY_DEPTH=1, the real client IP is parts[-1] (last hop
        # added by Railway/Nginx). For deeper chains adjust the slice.
        idx = max(0, len(parts) - _TRUSTED_PROXY_DEPTH)
        ip = parts[idx] if parts else ""
        if ip:
            # Strip IPv6 port notation if present (e.g. "::ffff:1.2.3.4")
            return ip.split("%")[0]
    return request.remote_addr or "unknown"


# ─── Redis helper ─────────────────────────────────────────────────────────────

def _is_production() -> bool:
    """Return True when the app is connected to a PostgreSQL database (production)."""
    try:
        db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        return "postgres" in db_url
    except Exception:
        return False


_redis_client = None  # module-level client backed by a connection pool


def _get_redis():
    """Pooled Redis client — runs on every rate-limited request, so it must not
    open a new TCP connection each time."""
    global _redis_client
    try:
        import redis as redis_lib
        if _redis_client is None:
            _redis_client = redis_lib.from_url(
                current_app.config.get("REDIS_URL", "redis://localhost:6379/0"),
                socket_connect_timeout=1,
                socket_timeout=1,
                health_check_interval=30,
            )
        _redis_client.ping()
        return _redis_client
    except Exception as e:
        logger.warning("[RATE_LIMIT] Redis unavailable: %s", e)
        _redis_client = None
        return None


# ─── Main decorator ───────────────────────────────────────────────────────────

def rate_limit(requests_per_minute=60, per="ip"):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if per == "ip":
                identifier = _get_client_ip()
            elif per == "user":
                from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
                try:
                    verify_jwt_in_request(optional=True)
                    identity = get_jwt_identity()
                    identifier = f"user:{identity}" if identity else _get_client_ip()
                except Exception:
                    identifier = _get_client_ip()
            else:
                identifier = _get_client_ip()

            rl_key = f"rate_limit:{f.__name__}:{identifier}"

            r = _get_redis()
            if r is None:
                if _is_production():
                    # Redis is down — log once, then degrade gracefully.
                    # In-process counter doesn't span workers, but it's far better than
                    # returning 503 for every request and breaking the entire app.
                    logger.warning(
                        "[RATE_LIMIT] Redis unavailable in production — falling back to "
                        "in-process rate limiter. Set REDIS_URL in Railway to restore full protection."
                    )
                if not _fallback_check(rl_key, requests_per_minute):
                    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
                return f(*args, **kwargs)

            # Redis sliding-window rate limiter
            window = 60
            try:
                pipe = r.pipeline()
                now = int(time.time())
                window_start = now - window
                pipe.zremrangebyscore(rl_key, 0, window_start)
                pipe.zadd(rl_key, {str(now): now})
                pipe.zcard(rl_key)
                pipe.expire(rl_key, window)
                results = pipe.execute()
                count = results[2]
                if count > requests_per_minute:
                    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
            except Exception as e:
                logger.warning("[RATE_LIMIT] Redis pipeline error, falling back: %s", e)
                if not _fallback_check(rl_key, requests_per_minute):
                    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

            return f(*args, **kwargs)
        return wrapper
    return decorator


def ip_whitelist(whitelist=None):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            allowed = whitelist or []
            client_ip = _get_client_ip()
            if allowed and client_ip not in allowed:
                return jsonify({"error": "Access denied"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator
