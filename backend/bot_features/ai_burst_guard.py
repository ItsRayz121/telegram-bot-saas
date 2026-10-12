"""Bound how many cheap per-event platform-AI calls (welcome / level-up) one group can trigger.

A join raid or XP burst would otherwise fire one paid completion per event with no ceiling.
When a group is over its window cap the caller simply falls back to the group's own template,
so members still get a message and nothing breaks.

Per-process and in-memory on purpose: it only has to stop runaway bursts, not meter exactly.
Kill switch: AI_BURST_GUARD=0 disables the cap.
"""
import os
import threading
import time
from collections import deque

_LOCK = threading.Lock()
_HITS: dict = {}
_MAX_KEYS = 5000  # hard bound on memory

DEFAULT_LIMIT = int(os.environ.get("AI_BURST_LIMIT_PER_HOUR", "20"))
WINDOW_SECONDS = 3600


def allow(feature: str, group_key, limit: int | None = None, window: int = WINDOW_SECONDS) -> bool:
    """True if this group may make one more `feature` AI call inside the window (and counts it)."""
    if os.environ.get("AI_BURST_GUARD", "1").strip().lower() in ("0", "false", "no", "off"):
        return True
    limit = DEFAULT_LIMIT if limit is None else limit
    now = time.monotonic()
    key = (feature, str(group_key))
    with _LOCK:
        q = _HITS.get(key)
        if q is None:
            if len(_HITS) >= _MAX_KEYS:
                _prune(now, window)
                if len(_HITS) >= _MAX_KEYS:
                    return False  # saturated: fail closed to the free template
            q = _HITS[key] = deque()
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def _prune(now: float, window: int) -> None:
    for k in [k for k, q in _HITS.items() if not q or now - q[-1] > window]:
        del _HITS[k]


def reset() -> None:
    """Test helper."""
    with _LOCK:
        _HITS.clear()
