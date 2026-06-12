"""Boost-tracking dashboard endpoints.

  GET /api/guilds/<id>/boosts -> settings
  PUT /api/guilds/<id>/boosts -> update settings

Config lives in GuildSettings.extra["boosts"] (self-heals, no migration).
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

import access
import settings as settings_mod
from auth import login_required

boosts_bp = Blueprint("boosts", __name__)


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _public(extra: dict | None) -> dict:
    return {**settings_mod.BOOSTS_DEFAULTS, **((extra or {}).get("boosts") or {})}


@boosts_bp.get("/api/guilds/<int:guild_id>/boosts")
@login_required
def get_boosts(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify(_public(row.extra))


@boosts_bp.put("/api/guilds/<int:guild_id>/boosts")
@login_required
def update_boosts(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    row = settings_mod.get_or_create(g.db, guild_id)
    cfg = _public(row.extra)

    if "enabled" in body:
        cfg["enabled"] = bool(body["enabled"])
    if "channel_id" in body:
        ch = body["channel_id"]
        cfg["channel_id"] = str(ch) if ch and str(ch).isdigit() else None
    if "message" in body:
        cfg["message"] = str(body["message"] or "").strip()[:1500] \
            or settings_mod.BOOSTS_DEFAULTS["message"]
    if "role_id" in body:
        rid = body["role_id"]
        cfg["role_id"] = str(rid) if rid and str(rid).isdigit() else None
    if "xp_bonus" in body:
        try:
            cfg["xp_bonus"] = max(0, min(10000, int(body["xp_bonus"])))
        except (TypeError, ValueError):
            pass

    extra = dict(row.extra or {})
    extra["boosts"] = cfg
    row.extra = extra
    settings_mod.touch(row)
    g.db.commit()
    return jsonify(cfg)
