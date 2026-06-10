"""Behavior-based raid detection for Guildizer.

Copied (not imported) from the Telegizer raid guard. The detection philosophy is
unchanged: we do NOT lock on raw join-rate (healthy spikes trip that); we detect
the *behaviour* of a raid — many DISTINCT accounts tripping the content filter, or
many DISTINCT accounts posting the SAME text, inside a short window.

Once detected, the guild enters a temporary lockdown: members who join while it's
active are auto-restricted (timeout) or kicked. Lockdown auto-expires; expiry is
checked lazily so a worker restart simply clears it. Manual lockdown is persisted
in the DB (ModerationSettings.manual_lockdown_until) and passed in by the caller.

Pure except for module-level per-process windows. Discord-side actions (timeout /
kick) live in the bot, not here, so this stays unit-testable.
"""
from __future__ import annotations

import hashlib
from collections import deque
from datetime import datetime, timedelta

_DEFAULTS = {
    "rg_enabled": False,
    "rg_window_seconds": 60,
    "rg_trigger_violators": 5,
    "rg_duplicate_threshold": 5,
    "rg_lockdown_minutes": 10,
    "min_text_len": 8,
}

# Per-process sliding windows + active-lockdown registry, keyed by guild_id (str).
_violations: dict = {}   # gid -> deque[(user_id, ts)]
_dupes: dict = {}        # gid -> deque[(user_id, text_hash, ts)]
_active: dict = {}       # gid -> lockdown-expiry datetime


def get_config(cfg: dict) -> dict:
    merged = dict(_DEFAULTS)
    try:
        merged.update({k: v for k, v in (cfg or {}).items() if v is not None})
    except Exception:
        pass
    return merged


# ── auto-lockdown state ───────────────────────────────────────────────────────
def is_active(guild_id) -> bool:
    gid = str(guild_id)
    exp = _active.get(gid)
    if not exp:
        return False
    if datetime.utcnow() >= exp:
        _active.pop(gid, None)
        return False
    return True


def seconds_remaining(guild_id) -> int:
    exp = _active.get(str(guild_id))
    if not exp:
        return 0
    return max(0, int((exp - datetime.utcnow()).total_seconds()))


def activate(guild_id, minutes) -> None:
    _active[str(guild_id)] = datetime.utcnow() + timedelta(minutes=max(1, int(minutes)))


def deactivate(guild_id) -> None:
    _active.pop(str(guild_id), None)


# ── manual emergency lockdown (persisted in DB, passed in) ────────────────────
def manual_active(manual_until) -> bool:
    """manual_until: a datetime (naive UTC) or None."""
    return bool(manual_until and datetime.utcnow() < manual_until)


def is_locked_down(guild_id, manual_until) -> bool:
    """True under EITHER an auto-detected raid lockdown OR a manual one."""
    return is_active(guild_id) or manual_active(manual_until)


# ── behavioral detectors ──────────────────────────────────────────────────────
def _prune(dq: deque, cutoff: datetime) -> None:
    while dq and dq[0][-1] < cutoff:
        dq.popleft()


def note_violation(guild_id, user_id, cfg: dict) -> bool:
    """Record a content-filter violation. Returns True only on the call that
    newly activates raid mode (so the caller alerts exactly once)."""
    c = get_config(cfg)
    if not c.get("rg_enabled") or user_id is None:
        return False
    gid = str(guild_id)
    if is_active(gid):
        return False
    now = datetime.utcnow()
    dq = _violations.setdefault(gid, deque())
    dq.append((user_id, now))
    _prune(dq, now - timedelta(seconds=int(c.get("rg_window_seconds", 60))))
    distinct = {item[0] for item in dq}
    if len(distinct) >= max(2, int(c.get("rg_trigger_violators", 5))):
        activate(gid, c.get("rg_lockdown_minutes", 10))
        dq.clear()
        return True
    return False


def note_message(guild_id, user_id, text, cfg: dict) -> bool:
    """Record a message for duplicate-flood detection (many distinct accounts
    posting identical text). Returns True only on the activating call."""
    c = get_config(cfg)
    if not c.get("rg_enabled") or user_id is None or not text:
        return False
    t = text.strip()
    if len(t) < int(c.get("min_text_len", 8)):
        return False
    gid = str(guild_id)
    if is_active(gid):
        return False
    now = datetime.utcnow()
    h = hashlib.sha1(t.lower().encode("utf-8", "ignore")).hexdigest()
    dq = _dupes.setdefault(gid, deque())
    dq.append((user_id, h, now))
    _prune(dq, now - timedelta(seconds=int(c.get("rg_window_seconds", 60))))
    distinct_for_text = {u for (u, hh, _ts) in dq if hh == h}
    if len(distinct_for_text) >= max(2, int(c.get("rg_duplicate_threshold", 5))):
        activate(gid, c.get("rg_lockdown_minutes", 10))
        dq.clear()
        return True
    return False


def activation_notice(seconds_left: int = 0) -> str:
    mins = max(1, round(seconds_left / 60)) if seconds_left else None
    tail = f" for ~{mins} min" if mins else ""
    return (
        "🛡️ **Raid mode activated** — I detected coordinated spam from multiple "
        f"accounts. New members are being automatically restricted{tail} until "
        "things settle. Admins can lift this anytime from the dashboard."
    )
