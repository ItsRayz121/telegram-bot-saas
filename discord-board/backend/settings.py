"""Per-guild settings: defaults, self-heal, and placeholder rendering.

Mirrors the Telegizer pattern of deep-merged defaults + startup self-heal, so
new settings keys appear for existing guilds without a manual migration. No
Telegram imports — pure Guildizer.
"""
from __future__ import annotations

from datetime import datetime

from models import Guild, GuildSettings

# Default copy for new servers. {user}, {server}, {member_count} are rendered.
DEFAULT_WELCOME = "👋 Welcome to **{server}**, {user}! You're member #{member_count}."
DEFAULT_LEAVE = "👋 {user} has left **{server}**."

# Column-level defaults used to backfill nulls on self-heal.
_COLUMN_DEFAULTS = {
    "welcome_enabled": False,
    "welcome_message": DEFAULT_WELCOME,
    "leave_enabled": False,
    "leave_message": DEFAULT_LEAVE,
    "autorole_enabled": False,
    "autorole_ids": list,
    "levels_enabled": False,
    "xp_per_message": 10,
    "xp_cooldown_seconds": 60,
    "announce_level_up": True,
    "commands_dirty": False,
    "extra": dict,
}


# Phase 11 welcome extensions, stored in GuildSettings.extra["welcome2"]
# (deep-merged on read - self-heals without a migration).
WELCOME2_DEFAULTS = {
    "ai_welcome": False,
    "use_embed": False,
    "rules_text": "",
    "image_url": "",
    "delete_after_seconds": 0,
    # Dashboard-parity: optional DM to new members (bot enforcement separate)
    "dm_enabled": False,
    "dm_message": "",
}

# Dashboard-parity leveling extensions, stored in GuildSettings.extra["leveling2"]
# (deep-merged on read — same self-heal pattern as welcome2).
LEVELING2_DEFAULTS = {
    "xp_per_reaction": 0,
    "reaction_cooldown_seconds": 60,
    "levelup_delete_after_seconds": 0,
    "penalty_warn": 0,      # XP removed when the member is warned
    "penalty_timeout": 0,   # … timed out
    "penalty_kick": 0,      # … kicked
    "penalty_ban": 0,       # … banned
    "role_rewards": [],     # [{"level": int, "role_id": str}]
}


# Voice features, stored in GuildSettings.extra["voice"] (deep-merged on read).
# Voice XP rides the leveling system: levels_enabled must be on too.
VOICE_DEFAULTS = {
    "xp_per_minute": 0,             # 0 = voice XP off
    "min_humans": 2,                # no XP for idling alone in a channel
    "j2c_enabled": False,           # join-to-create temp voice rooms
    "j2c_lobby_channel_id": None,
    "j2c_name_template": "{user}'s room",
    "j2c_user_limit": 0,            # 0 = unlimited
}


# Ticket system, stored in GuildSettings.extra["tickets"] (deep-merged on read).
# panel_message_id / needs_post / needs_delete / post_error / counter / open are
# bot-owned — the dashboard PUT must preserve them.
TICKETS_DEFAULTS = {
    "enabled": False,
    "panel_channel_id": None,        # where the "open a ticket" panel lives
    "panel_title": "Need help?",
    "panel_message": "Click the button below to open a private support ticket.",
    "button_label": "🎫 Open a ticket",
    "support_role_id": None,         # pinged into each ticket thread
    "transcript_channel_id": None,   # closing posts the transcript here
    "welcome_message": "",           # extra first message inside a new ticket
    "max_open_per_member": 1,
    # bot-owned
    "panel_message_id": None,
    "needs_post": False,
    "needs_delete": False,
    "post_error": None,
    "counter": 0,                    # lifetime ticket number
    "open": {},                      # thread_id -> {user_id, username, number, opened_at}
}


# Starboard, stored in GuildSettings.extra["starboard"] (deep-merged on read).
# "posted" is bot-owned: source message id -> {star_message_id, count}, pruned.
STARBOARD_DEFAULTS = {
    "enabled": False,
    "channel_id": None,
    "emoji": "⭐",
    "threshold": 3,
    "allow_self_star": False,
    "posted": {},
}


# Auto-publish announcement-channel posts to follower servers (Phase 4 native).
# Stored in GuildSettings.extra["auto_publish"]; empty channel_ids = every
# announcement channel in the guild.
AUTO_PUBLISH_DEFAULTS = {
    "enabled": False,
    "channel_ids": [],
}


def get_or_create(db, guild_id: int) -> GuildSettings:
    """Return the guild's settings row, creating a defaulted one if missing."""
    row = db.get(GuildSettings, guild_id)
    if row is None:
        row = GuildSettings(
            guild_id=guild_id,
            welcome_message=DEFAULT_WELCOME,
            leave_message=DEFAULT_LEAVE,
            autorole_ids=[],
            extra={},
        )
        db.add(row)
    else:
        _backfill(row)
    return row


def _backfill(row: GuildSettings) -> None:
    """Fill any null columns with their default (self-heal for new keys)."""
    for attr, default in _COLUMN_DEFAULTS.items():
        if getattr(row, attr, None) is None:
            setattr(row, attr, default() if callable(default) else default)


def self_heal_all(db, guild_ids: list[int]) -> int:
    """Ensure every given guild has a (backfilled) settings row. Returns count
    of rows created. Caller commits."""
    created = 0
    for gid in guild_ids:
        if db.get(Guild, gid) is None:
            continue  # only guilds we actually know about
        if db.get(GuildSettings, gid) is None:
            get_or_create(db, gid)
            created += 1
        else:
            _backfill(db.get(GuildSettings, gid))
    return created


def render_message(template: str, *, member, guild) -> str:
    """Render welcome/leave placeholders from discord.py member/guild objects."""
    if not template:
        return ""
    name = getattr(member, "mention", None) or getattr(member, "display_name", "")
    return (
        template.replace("{user}", str(name))
        .replace("{server}", getattr(guild, "name", ""))
        .replace("{member_count}", str(getattr(guild, "member_count", "") or ""))
    )


def touch(row: GuildSettings) -> None:
    row.updated_at = datetime.utcnow()
