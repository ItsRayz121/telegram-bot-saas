"""Ticket system dashboard endpoints.

  GET    /api/guilds/<id>/tickets        -> settings + open tickets
  PUT    /api/guilds/<id>/tickets        -> update settings (bot-owned fields preserved)
  POST   /api/guilds/<id>/tickets/panel  -> queue (re)post of the ticket panel
  DELETE /api/guilds/<id>/tickets/panel  -> queue removal of the posted panel

Config lives in GuildSettings.extra["tickets"] (self-heals, no migration).
panel_message_id / needs_post / needs_delete / post_error / counter / open are
bot-owned — PUT never touches them.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

import access
import settings as settings_mod
from auth import login_required
from tickets import merged

tickets_bp = Blueprint("tickets", __name__)


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _public(cfg: dict) -> dict:
    open_map = cfg.get("open") or {}
    return {
        "enabled": bool(cfg.get("enabled")),
        "panel_channel_id": cfg.get("panel_channel_id"),
        "panel_title": cfg.get("panel_title") or "",
        "panel_message": cfg.get("panel_message") or "",
        "button_label": cfg.get("button_label") or "",
        "support_role_id": cfg.get("support_role_id"),
        "alert_channel_id": cfg.get("alert_channel_id"),
        "transcript_channel_id": cfg.get("transcript_channel_id"),
        "welcome_message": cfg.get("welcome_message") or "",
        "max_open_per_member": int(cfg.get("max_open_per_member") or 1),
        "panel_message_id": cfg.get("panel_message_id"),
        "needs_post": bool(cfg.get("needs_post")),
        "needs_delete": bool(cfg.get("needs_delete")),
        "post_error": cfg.get("post_error"),
        "counter": int(cfg.get("counter") or 0),
        "open": [
            {"thread_id": tid, **entry}
            for tid, entry in sorted(open_map.items(),
                                     key=lambda kv: kv[1].get("number") or 0)
        ],
    }


def _id_or_none(value) -> str | None:
    return str(value) if value and str(value).isdigit() else None


@tickets_bp.get("/api/guilds/<int:guild_id>/tickets")
@login_required
def get_tickets(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify(_public(merged(row.extra)))


@tickets_bp.put("/api/guilds/<int:guild_id>/tickets")
@login_required
def update_tickets(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    row = settings_mod.get_or_create(g.db, guild_id)
    cfg = merged(row.extra)

    cfg["enabled"] = bool(body.get("enabled", cfg["enabled"]))
    if "panel_channel_id" in body:
        cfg["panel_channel_id"] = _id_or_none(body["panel_channel_id"])
    if "support_role_id" in body:
        cfg["support_role_id"] = _id_or_none(body["support_role_id"])
    if "alert_channel_id" in body:
        cfg["alert_channel_id"] = _id_or_none(body["alert_channel_id"])
    if "transcript_channel_id" in body:
        cfg["transcript_channel_id"] = _id_or_none(body["transcript_channel_id"])
    if "panel_title" in body:
        cfg["panel_title"] = str(body["panel_title"] or "").strip()[:256] or "Need help?"
    if "panel_message" in body:
        cfg["panel_message"] = str(body["panel_message"] or "").strip()[:2000]
    if "button_label" in body:
        cfg["button_label"] = str(body["button_label"] or "").strip()[:80] or "🎫 Open a ticket"
    if "welcome_message" in body:
        cfg["welcome_message"] = str(body["welcome_message"] or "").strip()[:1500]
    if "max_open_per_member" in body:
        try:
            cfg["max_open_per_member"] = max(1, min(10, int(body["max_open_per_member"])))
        except (TypeError, ValueError):
            pass

    extra = dict(row.extra or {})
    extra["tickets"] = cfg
    row.extra = extra
    settings_mod.touch(row)
    g.db.commit()
    return jsonify(_public(cfg))


def _queue_panel(guild_id: int, patch: dict) -> dict:
    row = settings_mod.get_or_create(g.db, guild_id)
    cfg = {**merged(row.extra), **patch}
    extra = dict(row.extra or {})
    extra["tickets"] = cfg
    row.extra = extra
    settings_mod.touch(row)
    g.db.commit()
    return cfg


@tickets_bp.post("/api/guilds/<int:guild_id>/tickets/panel")
@login_required
def queue_panel_post(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    cfg = merged(row.extra)
    if not cfg.get("panel_channel_id"):
        return jsonify(error="no_channel", message="Pick a panel channel first."), 400
    _queue_panel(guild_id, {"needs_post": True, "needs_delete": False, "post_error": None})
    return jsonify(ok=True, post_status="queued")


@tickets_bp.delete("/api/guilds/<int:guild_id>/tickets/panel")
@login_required
def queue_panel_delete(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    _queue_panel(guild_id, {"needs_delete": True, "needs_post": False})
    return jsonify(ok=True)
