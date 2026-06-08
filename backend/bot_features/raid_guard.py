"""
Behavior-based raid mode (Phase 3 of the bot-spam protection work).

WHY BEHAVIOR, NOT JOIN-RATE
───────────────────────────
A naive "N joins in M seconds → lock the group" trips constantly on healthy
communities — a shout-out, a product launch, a timezone waking up all spike the
join rate without any abuse. The owner explicitly rejected join-rate locking for
exactly this reason. Instead we detect the *behaviour* of a raid: many DISTINCT
accounts tripping the spam filters, or many DISTINCT accounts posting the SAME
message, inside a short window. Those are coordinated-attack signatures that
ordinary activity does not produce.

Once a raid is detected the group enters a temporary lockdown: members who join
*while the raid is active* are auto-restricted (muted) or kicked so the flood
can't keep growing, and admins are alerted once. The lockdown auto-expires after
`lockdown_minutes` — no persistent timer is needed; expiry is checked lazily on
read, so a process restart simply clears the (safe) lockdown.

Runtime-agnostic and Flask-free, like [bot_guard]: pure functions over a plain
`settings` dict plus module-level per-process windows. Both the official
Telegizer bot and custom bots import it so they raid-protect identically
(per the bot-lineage rule).
"""

import hashlib
import logging
from collections import deque
from datetime import datetime, timedelta

from telegram import ChatPermissions

logger = logging.getLogger(__name__)

# Defaults used when a group predates the raid_guard settings section. OFF by
# default: raids are rare and a false activation restricts genuine newcomers, so
# this is opt-in per group (admins enable it from the dashboard).
_DEFAULTS = {
    "enabled": False,
    "window_seconds": 60,
    "trigger_violators": 5,      # distinct users tripping automod within the window
    "duplicate_threshold": 5,    # distinct users posting identical text within the window
    "min_text_len": 8,           # ignore short/empty messages for duplicate detection
    "lockdown_minutes": 10,
    "lockdown_action": "mute",   # what happens to members who join during a raid: mute | kick
    "notify": True,
}

# Per-process sliding windows + active-lockdown registry, keyed by chat_id (str).
# Per-process only (each runtime imports its own copy). Losing this on restart is
# safe: in-flight windows reset and any active lockdown simply lifts.
_violations: dict = {}   # chat_id -> deque[(user_id, ts)]
_dupes: dict = {}        # chat_id -> deque[(user_id, text_hash, ts)]
_active: dict = {}       # chat_id -> lockdown-expiry datetime


def get_config(settings: dict) -> dict:
    """Return the group's raid_guard config merged over defaults (never raises)."""
    merged = dict(_DEFAULTS)
    try:
        merged.update(settings.get("raid_guard", {}) or {})
    except Exception:
        pass
    return merged


# ── Lockdown state ────────────────────────────────────────────────────────────

def is_active(chat_id) -> bool:
    """True while a raid lockdown is in effect. Lazily expires past entries so no
    background timer is needed."""
    cid = str(chat_id)
    exp = _active.get(cid)
    if not exp:
        return False
    if datetime.utcnow() >= exp:
        _active.pop(cid, None)
        return False
    return True


def seconds_remaining(chat_id) -> int:
    exp = _active.get(str(chat_id))
    if not exp:
        return 0
    return max(0, int((exp - datetime.utcnow()).total_seconds()))


def activate(chat_id, minutes) -> None:
    _active[str(chat_id)] = datetime.utcnow() + timedelta(minutes=max(1, int(minutes)))


def deactivate(chat_id) -> None:
    _active.pop(str(chat_id), None)


# ── Behavioral detectors ──────────────────────────────────────────────────────

def _prune(dq: deque, cutoff: datetime) -> None:
    while dq and dq[0][-1] < cutoff:
        dq.popleft()


def note_violation(chat_id, user_id, settings: dict) -> bool:
    """Record an automod violation. Returns True only on the call that newly
    activates raid mode (so the caller alerts exactly once)."""
    cfg = get_config(settings)
    if not cfg.get("enabled") or user_id is None:
        return False
    cid = str(chat_id)
    if is_active(cid):
        return False  # already locked down — don't re-alert on every violation
    now = datetime.utcnow()
    dq = _violations.setdefault(cid, deque())
    dq.append((user_id, now))
    _prune(dq, now - timedelta(seconds=cfg.get("window_seconds", 60)))
    distinct = {item[0] for item in dq}
    if len(distinct) >= max(2, int(cfg.get("trigger_violators", 5))):
        activate(cid, cfg.get("lockdown_minutes", 10))
        dq.clear()
        return True
    return False


def note_message(chat_id, user_id, text, settings: dict) -> bool:
    """Record a message for duplicate-flood detection (many distinct accounts
    posting the same text). Returns True only on the call that newly activates
    raid mode."""
    cfg = get_config(settings)
    if not cfg.get("enabled") or user_id is None or not text:
        return False
    t = text.strip()
    if len(t) < int(cfg.get("min_text_len", 8)):
        return False
    cid = str(chat_id)
    if is_active(cid):
        return False
    now = datetime.utcnow()
    h = hashlib.sha1(t.lower().encode("utf-8", "ignore")).hexdigest()
    dq = _dupes.setdefault(cid, deque())
    dq.append((user_id, h, now))
    _prune(dq, now - timedelta(seconds=cfg.get("window_seconds", 60)))
    distinct_for_text = {u for (u, hh, _ts) in dq if hh == h}
    if len(distinct_for_text) >= max(2, int(cfg.get("duplicate_threshold", 5))):
        activate(cid, cfg.get("lockdown_minutes", 10))
        dq.clear()
        return True
    return False


# ── Lockdown actions (Telegram side) ──────────────────────────────────────────

async def _restrict_member(bot, chat_id, user_id) -> bool:
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id, user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
        )
        return True
    except Exception as exc:
        logger.debug("raid restrict failed (chat=%s user=%s): %s", chat_id, user_id, exc)
        return False


async def _kick_member(bot, chat_id, user_id) -> bool:
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
        return True
    except Exception as exc:
        logger.debug("raid kick failed (chat=%s user=%s): %s", chat_id, user_id, exc)
        return False


async def lockdown_joiner(bot, chat_id, user_id, settings: dict) -> str:
    """Apply the configured lockdown action to a member who joined during an
    active raid. Returns the action actually taken: mute | kick | none."""
    cfg = get_config(settings)
    if cfg.get("lockdown_action") == "kick":
        return "kick" if await _kick_member(bot, chat_id, user_id) else "none"
    return "mute" if await _restrict_member(bot, chat_id, user_id) else "none"


def activation_notice(seconds_left: int = 0) -> str:
    """Linkless in-group alert posted once when raid mode activates."""
    mins = max(1, round(seconds_left / 60)) if seconds_left else None
    tail = f" for ~{mins} min" if mins else ""
    return (
        "🛡️ *Raid mode activated* — I detected coordinated spam from multiple "
        f"accounts. New members are being automatically restricted{tail} until "
        "things settle. Admins can lift this anytime by disabling Raid Mode."
    )
