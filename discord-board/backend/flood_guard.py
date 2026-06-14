"""Per-user flood / message-rate guard for Guildizer.

Distinct from raid_guard, which detects *multi-user* coordinated attacks. This
catches a *single* member spamming N messages within a short window and returns
a moderation decision the bot enforces (timeout by default).

Pure helper + a process-local sliding-window registry keyed by (guild_id,
user_id) — same shape as the other moderation evaluators, so it slots straight
into the on_message decision chain and unit-tests on its own.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

_DEFAULTS = {
    "enabled": False,
    "max_messages": 5,
    "window_seconds": 10,
    "action": "timeout",
    "timeout_minutes": 10,
}
_VALID_ACTIONS = {"delete", "warn", "timeout", "kick", "ban"}

# (guild_id, user_id) -> deque[monotonic timestamps]
_hits: dict = defaultdict(deque)


def get_config(cfg: dict) -> dict:
    """Merge a guild's automod.flood section over the defaults."""
    flood = ((cfg or {}).get("automod") or {}).get("flood") or {}
    merged = dict(_DEFAULTS)
    for key, val in flood.items():
        if val is not None and key in merged:
            merged[key] = val
    return merged


def check(guild_id, user_id, cfg: dict) -> dict | None:
    """Record this message; return a decision dict when the member exceeds the
    configured rate within the window, else None.

    On a trip the window is cleared so the bot acts once per burst rather than on
    every subsequent message.
    """
    conf = get_config(cfg)
    if not conf.get("enabled"):
        return None
    window = max(2, int(conf.get("window_seconds", 10) or 10))
    limit = max(2, int(conf.get("max_messages", 5) or 5))
    now = time.monotonic()
    key = (guild_id, user_id)
    dq = _hits[key]
    dq.append(now)
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        dq.clear()
        action = conf.get("action", "timeout")
        if action not in _VALID_ACTIONS:
            action = "timeout"
        return {
            "category": "flood",
            "action": action,
            "matched": str(limit),
            "detail": f"Flood: {limit}+ messages in {window}s",
            "timeout_minutes": max(1, int(conf.get("timeout_minutes", 10) or 10)),
        }
    return None


def reset(guild_id=None) -> None:
    """Drop tracked windows — for tests and on guild leave."""
    if guild_id is None:
        _hits.clear()
        return
    for key in [k for k in _hits if k[0] == guild_id]:
        _hits.pop(key, None)
