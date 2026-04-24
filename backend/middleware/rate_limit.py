import time
import functools
import logging
from flask import request, jsonify, current_app

logger = logging.getLogger(__name__)


def _get_redis():
    try:
        import redis as redis_lib
        r = redis_lib.from_url(current_app.config.get("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        return r
    except Exception as e:
        logger.warning(f"[RATE_LIMIT] Redis unavailable — rate limiting disabled for this request: {e}")
        return None


def rate_limit(requests_per_minute=60, per="ip"):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            r = _get_redis()
            if r is None:
                return f(*args, **kwargs)

            if per == "ip":
                identifier = request.remote_addr or "unknown"
            elif per == "user":
                from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
                try:
                    verify_jwt_in_request(optional=True)
                    identity = get_jwt_identity()
                    identifier = f"user:{identity}" if identity else (request.remote_addr or "unknown")
                except Exception:
                    identifier = request.remote_addr or "unknown"
            else:
                identifier = request.remote_addr or "unknown"

            key = f"rate_limit:{f.__name__}:{identifier}"
            window = 60

            try:
                pipe = r.pipeline()
                now = int(time.time())
                window_start = now - window

                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zadd(key, {str(now): now})
                pipe.zcard(key)
                pipe.expire(key, window)
                results = pipe.execute()
                count = results[2]

                if count > requests_per_minute:
                    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
            except Exception as e:
                logger.error(f"Rate limit Redis error: {e}")

            return f(*args, **kwargs)
        return wrapper
    return decorator


def ip_whitelist(whitelist=None):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            allowed = whitelist or []
            client_ip = request.remote_addr
            if allowed and client_ip not in allowed:
                return jsonify({"error": "Access denied"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator
