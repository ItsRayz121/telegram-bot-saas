"""Smart per-user slow mode for Guildizer (Telegizer parity).

Enforces a *steady* minimum gap between a single member's messages. Three things
in this space, kept distinct:

  - ``flood_guard`` — burst detection (N messages in M seconds).
  - Discord's *native* per-channel Slowmode (``rate_limit_per_user``) — set from
    the dashboard via ``discord_api.set_channel_slowmode``; blocks posting up
    front but is per channel and has no level/role exemptions.
  - this module — the reactive smart layer: a member's message that lands sooner
    than ``seconds_between_messages`` after their previous ACCEPTED message is
    removed. The baseline only advances on accepted messages, so the next
    allowed time is measured from the last good post — exactly like Telegram's
    native slow mode, ported here for parity. Adds per-level exemptions and
    harsher actions (warn / timeout) on top of native Slowmode.

Pure helper + a process-local registry keyed by ``(guild_id, user_id)``, same
shape as ``flood_guard``, so it slots straight into the on_message decision
chain and unit-tests on its own.
"""
from __future__ import annotations

import time

_DEFAULTS = {
    "enabled": False,
    "seconds_between_messages": 60,
    "action": "delete",          # delete | warn | timeout
    "timeout_minutes": 5,
    "exempt_min_level": 0,       # 0 = no level exemption
    "notify": True,
}
_VALID_ACTIONS = {"delete", "warn", "timeout"}

# (guild_id, user_id) -> monotonic timestamp of last ACCEPTED message
_last_ok: dict = {}
# (guild_id, user_id) -> monotonic timestamp of last heavier (warn/timeout) action
_last_act: dict = {}


def get_config(cfg: dict) -> dict:
    """Merge a guild's automod.slow_mode section over the defaults."""
    sm = ((cfg or {}).get("automod") or {}).get("slow_mode") or {}
    merged = dict(_DEFAULTS)
    for key, val in sm.items():
        if val is not None and key in merged:
            merged[key] = val
    return merged


def accept(guild_id, user_id) -> None:
    """Advance the baseline manually. Used when the caller decides a would-be
    violation is exempt (e.g. high level), so the member isn't acted on but the
    pacing window still moves forward."""
    _last_ok[(guild_id, user_id)] = time.monotonic()


def check(guild_id, user_id, cfg: dict) -> dict | None:
    """Record this message; return a decision dict when it lands inside the gap
    after the member's last accepted message, else None (and advance baseline).

    On a violation the baseline is NOT advanced — the next allowed post stays
    measured from the last accepted one. The default action ("delete") removes
    every too-fast message silently; heavier actions (warn / timeout) are
    throttled to once per gap so the bot itself never looks like a spammer
    (anti-ban). The caller applies the optional level exemption (a DB lookup we
    keep off this hot path) only when this returns a decision.
    """
    conf = get_config(cfg)
    if not conf.get("enabled"):
        return None
    gap = max(5, int(conf.get("seconds_between_messages", 60) or 60))
    now = time.monotonic()
    key = (guild_id, user_id)

    last = _last_ok.get(key)
    if last is not None and now - last < gap:
        remaining = max(1, int(gap - (now - last)))
        action = conf.get("action", "delete")
        if action not in _VALID_ACTIONS:
            action = "delete"
        detail = f"Slow mode: {gap}s between messages (~{remaining}s left)"
        if action == "delete":
            return {"category": "slow_mode", "action": "delete",
                    "matched": str(gap), "detail": detail}
        # Heavier action — throttle to once per gap; in between, delete silently
        # so a repeat offender still gets every message removed without the bot
        # spamming warnings/timeouts.
        last_act = _last_act.get(key)
        if last_act is None or now - last_act >= gap:
            _last_act[key] = now
            dec = {"category": "slow_mode", "action": action,
                   "matched": str(gap), "detail": detail}
            if action == "timeout":
                dec["timeout_minutes"] = max(1, int(conf.get("timeout_minutes", 5) or 5))
            return dec
        return {"category": "slow_mode", "action": "delete",
                "matched": str(gap), "detail": detail}

    # Accepted — this becomes the new baseline.
    _last_ok[key] = now
    return None


def sweep(max_age_seconds: float = 3600) -> None:
    """Drop per-(guild,user) windows whose last hit is stale, so the registry
    stays bounded. Called from the same periodic sweeper as flood_guard — both
    are high-cardinality (one key per chatty member)."""
    cutoff = time.monotonic() - max_age_seconds
    for key in [k for k, t in _last_ok.items() if t < cutoff]:
        _last_ok.pop(key, None)
        _last_act.pop(key, None)
    for key in [k for k, t in _last_act.items() if t < cutoff]:
        _last_act.pop(key, None)


def reset(guild_id=None) -> None:
    """Drop tracked windows — for tests and on guild leave."""
    if guild_id is None:
        _last_ok.clear()
        _last_act.clear()
        return
    for store in (_last_ok, _last_act):
        for key in [k for k in store if k[0] == guild_id]:
            store.pop(key, None)
