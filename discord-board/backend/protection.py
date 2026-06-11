"""Moderation/protection persistence helpers (no Flask, no discord.py).

Owns ModerationSettings self-heal, a plain-dict snapshot the bot consumes, and
ProtectionEvent logging. Mirrors the settings.py pattern so new moderation keys
self-heal on startup without a migration.
"""
from __future__ import annotations

from datetime import datetime

from models import Guild, ModerationSettings, ProtectionEvent

_COLUMN_DEFAULTS = {
    "cf_enabled": False,
    "cf_action": "delete",
    "cf_nsfw": True,
    "cf_invites": True,
    "cf_links": False,
    "cf_custom_words": list,
    "rg_enabled": False,
    "rg_window_seconds": 60,
    "rg_trigger_violators": 5,
    "rg_duplicate_threshold": 5,
    "rg_lockdown_minutes": 10,
    "rg_lockdown_action": "timeout",
    "rg_notify": True,
    "jg_min_account_age_days": 0,
    "extra": dict,
}


# Phase 10 automod matrix + warning ladder + auto-clean. Stored in the `extra`
# JSON column (deep-merged per section, so new keys self-heal without ALTERs).
EXTRA_DEFAULTS = {
    "automod": {
        "external_links": {"enabled": False, "whitelist": [], "action": "delete"},
        "excessive_emojis": {"enabled": False, "max_emojis": 15, "action": "delete"},
        "caps_lock": {"enabled": False, "threshold_percent": 80, "min_length": 15, "action": "delete"},
        "language_filter": {"enabled": False, "scripts": [], "action": "delete"},
        "media": {"block_attachments": False, "block_stickers": False,
                  "block_voice": False, "action": "delete"},
    },
    "warnings": {"max_warnings": 3, "action": "timeout", "timeout_minutes": 30},
    "auto_clean": {"join_messages": False},
    # Phase 11 — join captcha (quarantine-role pattern) + foreign-bot policy
    "verification": {
        "enabled": False, "method": "button",        # button | math | word
        "timeout_seconds": 300, "max_attempts": 3,
        "on_timeout": "kick",                         # kick | keep
        "role_id": None, "channel_id": None,          # filled by the bot at setup
    },
    "bot_policy": {
        "enabled": False, "policy": "kick_untrusted",  # kick_untrusted | alert_only
        "trusted_bot_ids": [], "alert_channel_id": None,
    },
}


def update_extra_section(db, guild_id: int, section: str, patch: dict) -> None:
    """Bot-side helper: persist keys into one extra section (e.g. the verification
    role/channel ids created at setup, or a newly trusted bot id)."""
    row = db.get(ModerationSettings, guild_id)
    if row is None:
        return
    extra = dict(row.extra or {})
    sect = dict(extra.get(section) or {})
    sect.update(patch)
    extra[section] = sect
    row.extra = extra


def _merged_extra(row: ModerationSettings) -> dict:
    """extra deep-merged over EXTRA_DEFAULTS (two levels: section -> sub-section)."""
    stored = row.extra or {}
    out = {}
    for section, sect_default in EXTRA_DEFAULTS.items():
        sect_stored = stored.get(section) or {}
        merged = {}
        for key, val in sect_default.items():
            if isinstance(val, dict):
                merged[key] = {**val, **(sect_stored.get(key) or {})}
            else:
                merged[key] = sect_stored.get(key, val)
        out[section] = merged
    return out


def get_or_create(db, guild_id: int) -> ModerationSettings:
    row = db.get(ModerationSettings, guild_id)
    if row is None:
        row = ModerationSettings(guild_id=guild_id, cf_custom_words=[], extra={})
        db.add(row)
    else:
        _backfill(row)
    return row


def _backfill(row: ModerationSettings) -> None:
    for attr, default in _COLUMN_DEFAULTS.items():
        if getattr(row, attr, None) is None:
            setattr(row, attr, default() if callable(default) else default)


def self_heal(db, guild_ids: list[int]) -> int:
    created = 0
    for gid in guild_ids:
        if db.get(Guild, gid) is None:
            continue
        if db.get(ModerationSettings, gid) is None:
            get_or_create(db, gid)
            created += 1
        else:
            _backfill(db.get(ModerationSettings, gid))
    return created


def load_snapshot(db, guild_id: int) -> dict | None:
    """Plain-dict moderation config for the bot's event handlers."""
    row = db.get(ModerationSettings, guild_id)
    if row is None:
        return None
    return {
        "cf_enabled": bool(row.cf_enabled),
        "cf_action": row.cf_action or "delete",
        "cf_nsfw": bool(row.cf_nsfw),
        "cf_invites": bool(row.cf_invites),
        "cf_links": bool(row.cf_links),
        "cf_custom_words": list(row.cf_custom_words or []),
        "rg_enabled": bool(row.rg_enabled),
        "rg_window_seconds": row.rg_window_seconds or 60,
        "rg_trigger_violators": row.rg_trigger_violators or 5,
        "rg_duplicate_threshold": row.rg_duplicate_threshold or 5,
        "rg_lockdown_minutes": row.rg_lockdown_minutes or 10,
        "rg_lockdown_action": row.rg_lockdown_action or "timeout",
        "rg_notify": bool(row.rg_notify),
        "rg_notify_channel_id": row.rg_notify_channel_id,
        "manual_lockdown_until": row.manual_lockdown_until,
        "jg_min_account_age_days": row.jg_min_account_age_days or 0,
        **_merged_extra(row),
    }


def log_event(db, guild_id: int, category: str, action: str, *,
              user_id=None, username=None, channel_id=None, detail=None) -> None:
    db.add(ProtectionEvent(
        guild_id=guild_id,
        category=category,
        action=action,
        user_id=user_id,
        username=(username or "")[:120] or None,
        channel_id=channel_id,
        detail=(detail or "")[:255] or None,
        created_at=datetime.utcnow(),
    ))
