"""Leveling/XP dashboard endpoints.

  GET /api/guilds/<id>/leveling      -> level settings
  PUT /api/guilds/<id>/leveling      -> update level settings
  GET /api/guilds/<id>/leaderboard   -> top members by XP (free; XP leaderboard)
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, g, jsonify, request

import leveling
import settings as settings_mod
from auth import login_required
from models import Guild, UserGuild

leveling_bp = Blueprint("leveling", __name__)


def _manage_or_403(guild_id: int):
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})
    if membership is None or not membership.can_manage:
        return False, (jsonify(error="forbidden"), 403)
    if g.db.get(Guild, guild_id) is None:
        return False, (jsonify(error="not_found"), 404)
    return True, None


def _as_int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


@leveling_bp.get("/api/guilds/<int:guild_id>/leveling")
@login_required
def get_leveling(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify(row.levels_to_dict())


@leveling_bp.put("/api/guilds/<int:guild_id>/leveling")
@login_required
def update_leveling(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    row = settings_mod.get_or_create(g.db, guild_id)

    if "levels_enabled" in body:
        row.levels_enabled = bool(body["levels_enabled"])
    if "xp_per_message" in body:
        row.xp_per_message = _as_int(body["xp_per_message"], 10, 0, 1000)
    if "xp_cooldown_seconds" in body:
        row.xp_cooldown_seconds = _as_int(body["xp_cooldown_seconds"], 60, 0, 3600)
    if "announce_level_up" in body:
        row.announce_level_up = bool(body["announce_level_up"])
    if "levelup_channel_id" in body:
        v = body["levelup_channel_id"]
        row.levelup_channel_id = int(v) if v and str(v).isdigit() else None
    if "levelup_message" in body:
        row.levelup_message = str(body["levelup_message"] or "")[:1000]

    row.updated_at = datetime.utcnow()
    g.db.commit()
    return jsonify(row.levels_to_dict())


@leveling_bp.get("/api/guilds/<int:guild_id>/leaderboard")
@login_required
def leaderboard(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    limit = _as_int(request.args.get("limit", 10), 10, 1, 100)
    members = leveling.top_members(g.db, guild_id, limit)
    rows = []
    for i, m in enumerate(members, start=1):
        d = m.to_dict()
        d["rank"] = i
        rows.append(d)
    return jsonify(leaderboard=rows)
