"""Starboard dashboard endpoints.

  GET /api/guilds/<id>/starboard -> settings
  PUT /api/guilds/<id>/starboard -> update settings

Config lives in GuildSettings.extra["starboard"] (self-heals, no migration).
The "posted" source->repost mapping is bot-owned and never exposed or written
by the dashboard.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

import access
import settings as settings_mod
from auth import login_required
from starboard import merged

starboard_bp = Blueprint("starboard", __name__)


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _public(cfg: dict) -> dict:
    return {
        "enabled": bool(cfg.get("enabled")),
        "channel_id": cfg.get("channel_id"),
        "emoji": cfg.get("emoji") or "⭐",
        "threshold": int(cfg.get("threshold") or 3),
        "allow_self_star": bool(cfg.get("allow_self_star")),
        "posted_count": len(cfg.get("posted") or {}),
    }


@starboard_bp.get("/api/guilds/<int:guild_id>/starboard")
@login_required
def get_starboard(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify(_public(merged(row.extra)))


@starboard_bp.put("/api/guilds/<int:guild_id>/starboard")
@login_required
def update_starboard(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    row = settings_mod.get_or_create(g.db, guild_id)
    cfg = merged(row.extra)

    cfg["enabled"] = bool(body.get("enabled", cfg["enabled"]))
    if "channel_id" in body:
        ch = body["channel_id"]
        cfg["channel_id"] = str(ch) if ch and str(ch).isdigit() else None
    if "emoji" in body:
        cfg["emoji"] = str(body["emoji"] or "").strip()[:64] or "⭐"
    if "threshold" in body:
        try:
            cfg["threshold"] = max(1, min(100, int(body["threshold"])))
        except (TypeError, ValueError):
            pass
    if "allow_self_star" in body:
        cfg["allow_self_star"] = bool(body["allow_self_star"])

    extra = dict(row.extra or {})
    extra["starboard"] = cfg
    row.extra = extra
    settings_mod.touch(row)
    g.db.commit()
    return jsonify(_public(cfg))
