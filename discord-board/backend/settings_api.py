"""Dashboard config endpoints: per-guild settings + custom slash commands.

  GET  /api/guilds/<id>/settings
  PUT  /api/guilds/<id>/settings
  GET  /api/guilds/<id>/settings/export
  POST /api/guilds/<id>/settings/import
  GET  /api/guilds/<id>/commands
  POST /api/guilds/<id>/commands
  PUT  /api/guilds/<id>/commands/<cmd_id>
  DEL  /api/guilds/<id>/commands/<cmd_id>

All require a session and that the user can_manage the guild. Command mutations
flip GuildSettings.commands_dirty so the bot re-registers slash commands.
"""
from __future__ import annotations

import re

from flask import Blueprint, g, jsonify, request

import settings as settings_mod
import settings_transfer
import access
from auth import login_required
from models import CustomCommand, Guild, UserGuild

settings_bp = Blueprint("settings", __name__)

_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
# Built-in commands every bot identity registers globally. Guild commands
# override globals in Discord, so a custom command with one of these names
# would silently hijack the built-in.
_RESERVED = {
    "ping", "rank", "leaderboard",
    "remind", "reminders", "note", "notes", "task", "tasks", "done", "ask",
    "wallet", "mywallet", "invitelink",
    "warn", "warnings", "removewarning", "mute", "unmute", "kick", "ban",
    "unban", "tempban", "purge", "userinfo", "auditlog", "report",
}


def _manage_or_403(guild_id: int):
    """Return (membership, guild) if the user manages it, else a 403/404 response."""
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
        return None, (jsonify(error="forbidden"), 403)
    guild = g.db.get(Guild, guild_id)
    if guild is None:
        return None, (jsonify(error="not_found"), 404)
    return (None, guild), None


# --- settings -----------------------------------------------------------------
@settings_bp.get("/api/guilds/<int:guild_id>/settings")
@login_required
def get_settings(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if err:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify({**row.to_dict(),
                    "welcome2": {**settings_mod.WELCOME2_DEFAULTS,
                                 **((row.extra or {}).get("welcome2") or {})}})


@settings_bp.put("/api/guilds/<int:guild_id>/settings")
@login_required
def update_settings(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    row = settings_mod.get_or_create(g.db, guild_id)

    if "welcome_enabled" in body:
        row.welcome_enabled = bool(body["welcome_enabled"])
    if "welcome_channel_id" in body:
        row.welcome_channel_id = _as_id(body["welcome_channel_id"])
    if "welcome_message" in body:
        row.welcome_message = str(body["welcome_message"] or "")[:2000]
    if "leave_enabled" in body:
        row.leave_enabled = bool(body["leave_enabled"])
    if "leave_channel_id" in body:
        row.leave_channel_id = _as_id(body["leave_channel_id"])
    if "leave_message" in body:
        row.leave_message = str(body["leave_message"] or "")[:2000]
    if "autorole_enabled" in body:
        row.autorole_enabled = bool(body["autorole_enabled"])
    # Phase 11 welcome extensions (extra JSON, merged over WELCOME2_DEFAULTS on read)
    if isinstance(body.get("welcome2"), dict):
        w_in = body["welcome2"]
        extra = dict(row.extra or {})
        w2 = dict(extra.get("welcome2") or {})
        if "use_embed" in w_in:
            w2["use_embed"] = bool(w_in["use_embed"])
        if "ai_welcome" in w_in:
            w2["ai_welcome"] = bool(w_in["ai_welcome"])
        if "rules_text" in w_in:
            w2["rules_text"] = str(w_in["rules_text"] or "")[:1024]
        if "image_url" in w_in:
            url = str(w_in["image_url"] or "").strip()[:300]
            w2["image_url"] = url if url.startswith(("http://", "https://")) or not url else ""
        if "delete_after_seconds" in w_in:
            try:
                w2["delete_after_seconds"] = max(0, min(3600, int(w_in["delete_after_seconds"])))
            except (TypeError, ValueError):
                pass
        if "dm_enabled" in w_in:
            w2["dm_enabled"] = bool(w_in["dm_enabled"])
        if "dm_message" in w_in:
            w2["dm_message"] = str(w_in["dm_message"] or "")[:2000]
        extra["welcome2"] = w2
        row.extra = extra
    if "autorole_ids" in body:
        ids = body["autorole_ids"] or []
        row.autorole_ids = [str(int(x)) for x in ids if str(x).isdigit()][:10]

    settings_mod.touch(row)
    g.db.commit()
    return jsonify({**row.to_dict(),
                    "welcome2": {**settings_mod.WELCOME2_DEFAULTS,
                                 **((row.extra or {}).get("welcome2") or {})}})


def _as_id(value):
    if value in (None, "", "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --- custom commands ----------------------------------------------------------
@settings_bp.get("/api/guilds/<int:guild_id>/commands")
@login_required
def list_commands(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if err:
        return err
    cmds = (
        g.db.query(CustomCommand)
        .filter(CustomCommand.guild_id == guild_id)
        .order_by(CustomCommand.name)
        .all()
    )
    return jsonify(commands=[c.to_dict() for c in cmds])


@settings_bp.post("/api/guilds/<int:guild_id>/commands")
@login_required
def create_command(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip().lower()
    valid, msg = _validate_name(g.db, guild_id, name)
    if not valid:
        return jsonify(error=msg), 400

    cmd = CustomCommand(
        guild_id=guild_id,
        name=name,
        description=str(body.get("description") or "Custom command")[:100],
        response=str(body.get("response") or "")[:2000],
        enabled=bool(body.get("enabled", True)),
    )
    g.db.add(cmd)
    _mark_dirty(guild_id)
    g.db.commit()
    return jsonify(cmd.to_dict()), 201


@settings_bp.put("/api/guilds/<int:guild_id>/commands/<int:cmd_id>")
@login_required
def update_command(guild_id: int, cmd_id: int):
    ok, err = _manage_or_403(guild_id)
    if err:
        return err
    cmd = g.db.get(CustomCommand, cmd_id)
    if cmd is None or cmd.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}

    if "name" in body:
        name = str(body["name"]).strip().lower()
        valid, msg = _validate_name(g.db, guild_id, name, exclude_id=cmd_id)
        if not valid:
            return jsonify(error=msg), 400
        cmd.name = name
    if "description" in body:
        cmd.description = str(body["description"] or "Custom command")[:100]
    if "response" in body:
        cmd.response = str(body["response"] or "")[:2000]
    if "enabled" in body:
        cmd.enabled = bool(body["enabled"])

    _mark_dirty(guild_id)
    g.db.commit()
    return jsonify(cmd.to_dict())


@settings_bp.delete("/api/guilds/<int:guild_id>/commands/<int:cmd_id>")
@login_required
def delete_command(guild_id: int, cmd_id: int):
    ok, err = _manage_or_403(guild_id)
    if err:
        return err
    cmd = g.db.get(CustomCommand, cmd_id)
    if cmd is None or cmd.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(cmd)
    _mark_dirty(guild_id)
    g.db.commit()
    return jsonify(ok=True)


def _validate_name(db, guild_id: int, name: str, *, exclude_id: int | None = None):
    if not _NAME_RE.match(name):
        return False, "Name must be 1–32 chars: lowercase letters, numbers, - or _"
    if name in _RESERVED:
        return False, f"'{name}' is reserved"
    q = db.query(CustomCommand).filter(
        CustomCommand.guild_id == guild_id, CustomCommand.name == name
    )
    if exclude_id is not None:
        q = q.filter(CustomCommand.id != exclude_id)
    if q.first() is not None:
        return False, f"A command named '{name}' already exists"
    return True, ""


def _mark_dirty(guild_id: int) -> None:
    row = settings_mod.get_or_create(g.db, guild_id)
    row.commands_dirty = True


# --- settings import / export -------------------------------------------------
@settings_bp.get("/api/guilds/<int:guild_id>/settings/export")
@login_required
def export_settings(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if err:
        return err
    _, guild = ok
    envelope = settings_transfer.build_export(g.db, guild_id, guild.name or "")
    g.db.commit()   # build_export may have created the defaulted settings row
    return jsonify(envelope)


@settings_bp.post("/api/guilds/<int:guild_id>/settings/import")
@login_required
def import_settings(guild_id: int):
    """dry_run=true returns the preview; dry_run=false applies the same merge."""
    ok, err = _manage_or_403(guild_id)
    if err:
        return err

    # A settings export is a few dozen KB. Anything larger is not one of ours.
    if (request.content_length or 0) > 512 * 1024:
        return jsonify(error="That file is too large to be a settings export.",
                       code="INVALID_EXPORT_FILE"), 413

    body = request.get_json(silent=True) or {}
    raw_file = body.get("file")
    if not isinstance(raw_file, dict):
        return jsonify(error="No settings file provided."), 400

    payload, parse_err = settings_transfer.parse_export(raw_file)
    if parse_err:
        return jsonify(error=parse_err, code="INVALID_EXPORT_FILE"), 400

    dry_run = bool(body.get("dry_run", True))
    result = settings_transfer.plan_import(g.db, guild_id, payload, apply=not dry_run)
    if dry_run:
        # plan_import wrote nothing, but get_or_create may have added the
        # defaulted settings row. Persist that, same as GET /settings does.
        g.db.commit()

    meta = raw_file.get("guildizer_settings_export") or {}
    result["bindings_excluded"] = meta.get("bindings_excluded", [])
    result["source_group"] = meta.get("source_server", "")
    if not dry_run:
        result["message"] = f"Imported {len(result['changes'])} setting(s)."
    return jsonify(result)
