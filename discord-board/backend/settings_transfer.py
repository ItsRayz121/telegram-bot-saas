"""Export / import of a server's bot configuration as a portable JSON file.

Copied in spirit from the Telegizer module of the same name — no Telegram
imports, pure Guildizer. The shape differs because Guildizer settings are not
one JSON blob: they live across GuildSettings columns, GuildSettings.extra,
ModerationSettings columns, and CustomCommand rows. This module is the only
place that knows how to flatten all four into one file and back.

The file is meant to be handed to another person, so it is built from an
explicit ALLOW-LIST, never a blocklist. Anything not named here never leaves
the database. That deliberately excludes:

  • Snowflake IDs   — channel_id, role_id, autorole_ids, command_channel_ids.
                      Valid only inside the source server.
  • Bot-owned state — tickets.open/counter/panel_message_id, starboard.posted,
                      commands_dirty, manual_lockdown_until.
  • Secrets         — none live in these tables today; the allow-list keeps it
                      that way by construction.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from models import GuildSettings, ModerationSettings, CustomCommand
import settings as gsettings
import protection

SCHEMA_VERSION = 1
PRODUCT = "guildizer"

# GuildSettings columns that mean the same thing in any server.
GUILD_FIELDS = (
    "welcome_enabled", "welcome_message",
    "leave_enabled", "leave_message",
    "autorole_enabled",
    "levels_enabled", "xp_per_message", "xp_cooldown_seconds",
    "announce_level_up", "levelup_message",
)

# ModerationSettings columns. Safety config is never plan-gated on Guildizer.
MODERATION_FIELDS = (
    "cf_enabled", "cf_action", "cf_nsfw", "cf_invites", "cf_links", "cf_custom_words",
    "rg_enabled", "rg_window_seconds", "rg_trigger_violators",
    "rg_duplicate_threshold", "rg_lockdown_minutes", "rg_lockdown_action", "rg_notify",
    "jg_min_account_age_days",
)

# GuildSettings.extra sub-sections -> the keys inside each that travel.
EXTRA_FIELDS = {
    "welcome2":     ("ai_welcome", "use_embed", "rules_text", "image_url",
                     "delete_after_seconds", "dm_enabled", "dm_message"),
    "leveling2":    ("xp_per_reaction", "reaction_cooldown_seconds",
                     "levelup_delete_after_seconds", "ai_levelup",
                     "penalty_warn", "penalty_timeout", "penalty_kick", "penalty_ban",
                     "rank_card"),
    "voice":        ("xp_per_minute", "min_humans", "j2c_enabled",
                     "j2c_name_template", "j2c_user_limit"),
    "tickets":      ("enabled", "panel_title", "panel_message", "button_label",
                     "welcome_message", "max_open_per_member"),
    "starboard":    ("enabled", "emoji", "threshold", "allow_self_star"),
    "auto_publish": ("enabled",),
    "auto_threads": ("enabled", "archive_minutes", "include_bots"),
    "boosts":       ("enabled", "message", "xp_bonus"),
}

# Everything an import will not touch, named for the UI. These are read off the
# source server but never written into the file.
BINDING_FIELDS = (
    "welcome_channel_id", "leave_channel_id", "levelup_channel_id", "autorole_ids",
    "moderation.rg_notify_channel_id",
    "leveling2.role_rewards", "leveling2.command_channel_ids",
    "voice.j2c_lobby_channel_id",
    "tickets.panel_channel_id", "tickets.support_role_id",
    "tickets.alert_channel_id", "tickets.transcript_channel_id",
    "starboard.channel_id",
    "auto_publish.channel_ids", "auto_threads.channel_ids",
    "boosts.channel_id", "boosts.role_id",
)

_EXTRA_DEFAULTS = {
    "welcome2":     gsettings.WELCOME2_DEFAULTS,
    "leveling2":    gsettings.LEVELING2_DEFAULTS,
    "voice":        gsettings.VOICE_DEFAULTS,
    "tickets":      gsettings.TICKETS_DEFAULTS,
    "starboard":    gsettings.STARBOARD_DEFAULTS,
    "auto_publish": gsettings.AUTO_PUBLISH_DEFAULTS,
    "auto_threads": gsettings.AUTO_THREADS_DEFAULTS,
    "boosts":       gsettings.BOOSTS_DEFAULTS,
}


def _merged_extra(row: GuildSettings, section: str) -> dict:
    """The section as the app sees it: defaults deep-merged under stored values."""
    stored = (row.extra or {}).get(section) or {}
    return {**copy.deepcopy(_EXTRA_DEFAULTS[section]), **stored}


def _which_bindings_set(gs: GuildSettings, mod: ModerationSettings) -> list:
    """Only report bindings the source server actually had set."""
    found = []
    for col in ("welcome_channel_id", "leave_channel_id", "levelup_channel_id"):
        if getattr(gs, col, None):
            found.append(col)
    if gs.autorole_ids:
        found.append("autorole_ids")
    if mod is not None and mod.rg_notify_channel_id:
        found.append("moderation.rg_notify_channel_id")

    for section, keys in (
        ("leveling2", ("role_rewards", "command_channel_ids")),
        ("voice", ("j2c_lobby_channel_id",)),
        ("tickets", ("panel_channel_id", "support_role_id", "alert_channel_id", "transcript_channel_id")),
        ("starboard", ("channel_id",)),
        ("auto_publish", ("channel_ids",)),
        ("auto_threads", ("channel_ids",)),
        ("boosts", ("channel_id", "role_id")),
    ):
        merged = _merged_extra(gs, section)
        for key in keys:
            if merged.get(key):
                found.append(f"{section}.{key}")
    return found


def build_export(db, guild_id: int, guild_name: str = "") -> dict:
    gs = gsettings.get_or_create(db, guild_id)
    mod = protection.get_or_create(db, guild_id)

    payload = {
        "guild": {f: getattr(gs, f, None) for f in GUILD_FIELDS},
        "extra": {
            section: {k: v for k, v in _merged_extra(gs, section).items() if k in keys}
            for section, keys in EXTRA_FIELDS.items()
        },
        "moderation": (
            {f: getattr(mod, f, None) for f in MODERATION_FIELDS} if mod is not None else {}
        ),
        "commands": [
            {"name": c.name, "description": c.description or "", "response": c.response or "",
             "enabled": bool(c.enabled)}
            for c in db.query(CustomCommand).filter(CustomCommand.guild_id == guild_id).all()
        ],
    }

    return {
        "guildizer_settings_export": {
            "schema_version": SCHEMA_VERSION,
            "product": PRODUCT,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source_server": guild_name or "",
            "bindings_excluded": _which_bindings_set(gs, mod),
        },
        "settings": payload,
    }


def parse_export(raw):
    """Validate an uploaded file. Returns (payload, error_message)."""
    if not isinstance(raw, dict):
        return None, "That file isn't a valid settings export."

    meta = raw.get("guildizer_settings_export")
    if not isinstance(meta, dict):
        if "telegizer_settings_export" in raw:
            return None, "That file was exported from Telegizer, not Guildizer."
        return None, "That file isn't a Guildizer settings export."

    if meta.get("product") != PRODUCT:
        return None, f"That file was exported from {meta.get('product') or 'another product'}, not Guildizer."

    version = meta.get("schema_version")
    if version != SCHEMA_VERSION:
        return None, (
            f"That file uses settings format v{version}, but this version of "
            f"Guildizer reads v{SCHEMA_VERSION}."
        )

    settings_blob = raw.get("settings")
    if not isinstance(settings_blob, dict) or not settings_blob:
        return None, "That export file has no settings in it."

    # Rebuild from the allow-list: a hand-edited file cannot smuggle in a
    # channel id, a bot-owned key, or an unknown column.
    clean = {
        "guild": {k: v for k, v in (settings_blob.get("guild") or {}).items() if k in GUILD_FIELDS},
        "moderation": {k: v for k, v in (settings_blob.get("moderation") or {}).items() if k in MODERATION_FIELDS},
        "extra": {
            section: {k: v for k, v in ((settings_blob.get("extra") or {}).get(section) or {}).items() if k in keys}
            for section, keys in EXTRA_FIELDS.items()
        },
        "commands": [
            {
                "name": str(c.get("name", ""))[:32],
                "description": str(c.get("description", ""))[:100],
                "response": str(c.get("response", "")),
                "enabled": bool(c.get("enabled", True)),
            }
            for c in (settings_blob.get("commands") or [])
            if isinstance(c, dict) and c.get("name")
        ][:100],
    }

    if not any(clean["guild"]) and not any(clean["moderation"]) and not clean["commands"]:
        return None, "That export file has no settings we can import."
    return clean, None


def plan_import(db, guild_id: int, payload: dict, apply: bool = False) -> dict:
    """Compute (and optionally apply) the merge. Preview and apply share this
    function, so what the user confirms is exactly what gets written.

    Guildizer never plan-gates these sections — safety and server config are
    free by design (see plan_limits.py). `skipped` is always empty today; it
    exists so a future gate reports through the same UI as Telegizer's.
    """
    gs = gsettings.get_or_create(db, guild_id)
    mod = protection.get_or_create(db, guild_id)
    changes, skipped = [], []

    def note(path, old, new):
        if old != new:
            changes.append({"path": path, "from": old, "to": new})

    for field, new in (payload.get("guild") or {}).items():
        note(field, getattr(gs, field, None), new)
        if apply:
            setattr(gs, field, new)

    for field, new in (payload.get("moderation") or {}).items():
        note(f"moderation.{field}", getattr(mod, field, None), new)
        if apply:
            setattr(mod, field, new)

    extra = copy.deepcopy(gs.extra or {})
    for section, incoming in (payload.get("extra") or {}).items():
        if not incoming:
            continue
        merged = _merged_extra(gs, section)
        for key, new in incoming.items():
            note(f"{section}.{key}", merged.get(key), new)
        if apply:
            # Merge over STORED values, so bot-owned keys (tickets.open,
            # starboard.posted, panel_message_id) are preserved untouched.
            extra.setdefault(section, {})
            extra[section].update(incoming)

    existing = {c.name: c for c in db.query(CustomCommand).filter(CustomCommand.guild_id == guild_id).all()}
    commands_changed = False
    for cmd in payload.get("commands") or []:
        row = existing.get(cmd["name"])
        if row is None:
            note(f"commands./{cmd['name']}", None, cmd["response"] or "(new command)")
            commands_changed = True
            if apply:
                db.add(CustomCommand(guild_id=guild_id, **cmd))
        else:
            for field in ("description", "response", "enabled"):
                if getattr(row, field) != cmd[field]:
                    note(f"commands./{cmd['name']}.{field}", getattr(row, field), cmd[field])
                    commands_changed = True
                    if apply:
                        setattr(row, field, cmd[field])

    if apply:
        gs.extra = extra
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(gs, "extra")
        gs.updated_at = datetime.utcnow()
        mod.updated_at = datetime.utcnow()
        if commands_changed:
            gs.commands_dirty = True   # bot's resync loop re-registers slash commands
        db.commit()

    return {"changes": changes, "skipped": skipped, "applied": bool(apply)}
