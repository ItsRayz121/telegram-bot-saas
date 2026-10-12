"""Run-at-most-once-at-a-time guard for heavy, synchronous admin sweeps.

Rate limits cap how often a heavy endpoint can be *started*; they don't stop a second sweep starting
while the first is still running, and each sweep holds a web thread for its whole (throttled) run.
Stacked sweeps can pin every gunicorn thread. This answers 409 instead of queueing another one.

Process-local by design (production runs one web process); a second process would at worst allow
one sweep per process, still bounded.
"""
import threading
from functools import wraps

from flask import jsonify

_LOCKS: dict = {}
_GUARD = threading.Lock()


def single_flight(name: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            with _GUARD:
                lock = _LOCKS.setdefault(name, threading.Lock())
            if not lock.acquire(blocking=False):
                return jsonify({
                    "error": "This job is already running. Wait for it to finish, then try again.",
                    "code": "ALREADY_RUNNING",
                }), 409
            try:
                return fn(*args, **kwargs)
            finally:
                lock.release()
        return wrapper
    return deco


def clamp_sweep_limit(raw, default: int = 500, maximum: int = 1000):
    """Parse an optional admin-supplied sweep size: junk or <1 -> default, huge -> maximum."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    if n < 1:
        return default
    return min(n, maximum)
