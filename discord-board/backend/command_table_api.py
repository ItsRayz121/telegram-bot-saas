"""Command management table for a server (Guildizer).

  GET /api/guilds/<id>/command-table   -> one row per command (+ limits, channel access, failures)
  PUT /api/guilds/<id>/command-table   -> {"commands": [{command, delete_reply, seconds, enabled}, ...]}
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

import access
import command_cleanup as cc
import settings as settings_mod
from auth import login_required
from models import Guild

command_table_bp = Blueprint("command_table", __name__)


def _guard(guild_id: int):
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
        return jsonify(error="forbidden"), 403
    if g.db.get(Guild, guild_id) is None:
        return jsonify(error="not_found"), 404
    return None


def _payload(row, guild_id):
    extra = row.extra or {}
    channels = [str(c) for c in ((extra.get("leveling2") or {}).get("command_channel_ids") or [])]
    return {
        "commands": cc.command_rows(extra, cc.custom_command_names(g.db, guild_id)),
        "limits": {"min_seconds": cc.MIN_SECONDS, "max_seconds": cc.MAX_SECONDS, "can_delete_command": False,
                   "note": "Discord does not let a bot delete a member's slash command, only the bot's reply."},
        # rank/leaderboard are limited to these channels (empty = everywhere); edited in Leveling settings
        "xp_command_channel_ids": channels,
        "delete_failures_24h": cc.recent_failures(guild_id),
    }


@command_table_bp.get("/api/guilds/<int:guild_id>/command-table")
@login_required
def get_command_table(guild_id: int):
    err = _guard(guild_id)
    if err:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify(_payload(row, guild_id))


@command_table_bp.put("/api/guilds/<int:guild_id>/command-table")
@login_required
def put_command_table(guild_id: int):
    err = _guard(guild_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    row = settings_mod.get_or_create(g.db, guild_id)
    try:
        row.extra = cc.apply_table(row.extra, body.get("commands"), cc.custom_command_names(g.db, guild_id))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    g.db.commit()
    return jsonify(_payload(row, guild_id))
