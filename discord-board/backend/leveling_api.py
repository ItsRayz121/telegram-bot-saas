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
import access
from auth import login_required
from models import Guild, UserGuild

leveling_bp = Blueprint("leveling", __name__)


def _manage_or_403(guild_id: int):
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
        return False, (jsonify(error="forbidden"), 403)
    if g.db.get(Guild, guild_id) is None:
        return False, (jsonify(error="not_found"), 404)
    return True, None


def _as_int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _leveling2(row) -> dict:
    """leveling2 extras deep-merged over defaults (welcome2 pattern)."""
    return {**settings_mod.LEVELING2_DEFAULTS,
            **((row.extra or {}).get("leveling2") or {})}


def _voice(row) -> dict:
    return {**settings_mod.VOICE_DEFAULTS,
            **((row.extra or {}).get("voice") or {})}


@leveling_bp.get("/api/guilds/<int:guild_id>/leveling")
@login_required
def get_leveling(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify({**row.levels_to_dict(), "leveling2": _leveling2(row),
                    "voice": _voice(row)})


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

    # Dashboard-parity extras (extra JSON, merged over LEVELING2_DEFAULTS on read)
    if isinstance(body.get("leveling2"), dict):
        l_in = body["leveling2"]
        extra = dict(row.extra or {})
        l2 = dict(extra.get("leveling2") or {})
        for key, hi in (("xp_per_reaction", 1000), ("reaction_cooldown_seconds", 3600),
                        ("levelup_delete_after_seconds", 86400),
                        ("penalty_warn", 10000), ("penalty_timeout", 10000),
                        ("penalty_kick", 10000), ("penalty_ban", 10000)):
            if key in l_in:
                l2[key] = _as_int(l_in[key], 0, 0, hi)
        if "ai_levelup" in l_in:
            l2["ai_levelup"] = bool(l_in["ai_levelup"])
        if isinstance(l_in.get("role_rewards"), list):
            rewards = []
            for r in l_in["role_rewards"][:20]:
                if not isinstance(r, dict) or not str(r.get("role_id", "")).isdigit():
                    continue
                rewards.append({"level": _as_int(r.get("level"), 1, 1, 1000),
                                "role_id": str(r["role_id"])})
            l2["role_rewards"] = sorted(rewards, key=lambda r: r["level"])
        extra["leveling2"] = l2
        row.extra = extra

    # Voice features (extra JSON, merged over VOICE_DEFAULTS on read)
    if isinstance(body.get("voice"), dict):
        v_in = body["voice"]
        extra = dict(row.extra or {})
        v = dict(extra.get("voice") or {})
        if "xp_per_minute" in v_in:
            v["xp_per_minute"] = _as_int(v_in["xp_per_minute"], 0, 0, 100)
        if "min_humans" in v_in:
            v["min_humans"] = _as_int(v_in["min_humans"], 2, 1, 20)
        if "j2c_enabled" in v_in:
            v["j2c_enabled"] = bool(v_in["j2c_enabled"])
        if "j2c_lobby_channel_id" in v_in:
            ch = v_in["j2c_lobby_channel_id"]
            v["j2c_lobby_channel_id"] = str(ch) if ch and str(ch).isdigit() else None
        if "j2c_name_template" in v_in:
            v["j2c_name_template"] = str(v_in["j2c_name_template"] or "")[:100]
        if "j2c_user_limit" in v_in:
            v["j2c_user_limit"] = _as_int(v_in["j2c_user_limit"], 0, 0, 99)
        extra["voice"] = v
        row.extra = extra

    row.updated_at = datetime.utcnow()
    g.db.commit()
    return jsonify({**row.levels_to_dict(), "leveling2": _leveling2(row),
                    "voice": _voice(row)})


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
