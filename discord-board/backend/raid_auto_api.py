"""Continuous raids API (Guildizer): one automation per server.

  GET    /api/guilds/<id>/raid-auto          current setup + limits
  PUT    /api/guilds/<id>/raid-auto          save {x_handle, channel_id, enabled, template}
  DELETE /api/guilds/<id>/raid-auto          remove it
  POST   /api/guilds/<id>/raid-auto/check    check now (at most once an hour)
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

import access
import raid_auto as ra
import twitter_verify
from auth import login_required
from models import Guild, RaidAutomation

raid_auto_bp = Blueprint("raid_auto", __name__)


def _guild(guild_id: int):
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
        return None, (jsonify(error="forbidden"), 403)
    guild = g.db.get(Guild, guild_id)
    if guild is None:
        return None, (jsonify(error="not_found"), 404)
    return guild, None


def _payload(guild, row, result=None):
    try:
        x_status = twitter_verify.autoverify_status(guild.owner_id)
    except Exception:  # noqa: BLE001
        x_status = "disabled"
    out = {
        "automation": ra.to_dict(row) if row else None, "x_status": x_status, "is_paid": bool(guild.is_pro),
        "can_edit": True,
        "limits": {"interval_hours": ra.INTERVAL_HOURS, "max_per_day": ra.MAX_PER_DAY_LIMIT,
                   "max_per_check": ra.MAX_PER_POLL, "manual_check_minutes": ra.MANUAL_CHECK_COOLDOWN_MIN},
    }
    if result is not None:
        out["result"] = result
    return out


def _row(guild_id):
    return g.db.query(RaidAutomation).filter(RaidAutomation.guild_id == guild_id).first()


@raid_auto_bp.route("/api/guilds/<int:guild_id>/raid-auto", methods=["GET", "PUT", "DELETE"])
@login_required
def raid_auto_root(guild_id: int):
    guild, err = _guild(guild_id)
    if err:
        return err
    row = _row(guild_id)
    if request.method == "GET":
        return jsonify(_payload(guild, row))
    try:
        if request.method == "PUT":
            body = request.get_json(silent=True) or {}
            row = ra.upsert(g.db, guild, g.user_id, channel_id=body.get("channel_id"), x_handle=body.get("x_handle"),
                            template=body.get("template"), enabled_flag=bool(body.get("enabled", True)))
            return jsonify(_payload(guild, row))
        if row is not None:
            g.db.delete(row)
            g.db.commit()
        return jsonify(_payload(guild, None))
    except ra.AutoError as e:
        g.db.rollback()
        return jsonify(error=e.message, code=e.code), e.status


@raid_auto_bp.post("/api/guilds/<int:guild_id>/raid-auto/check")
@login_required
def raid_auto_check(guild_id: int):
    guild, err = _guild(guild_id)
    if err:
        return err
    row = _row(guild_id)
    if row is None:
        return jsonify(error="Set up continuous raids first."), 404
    try:
        result = ra.check_now(g.db, row)
        return jsonify(_payload(guild, row, result))
    except ra.AutoError as e:
        g.db.rollback()
        return jsonify(error=e.message, code=e.code), e.status
