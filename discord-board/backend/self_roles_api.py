"""Self-role menu dashboard endpoints (reaction/button roles).

  GET    /api/guilds/<id>/self-roles                  -> {menus: [...]}
  PUT    /api/guilds/<id>/self-roles                  -> replace menus (sanitized)
  POST   /api/guilds/<id>/self-roles/<mid>/post       -> queue (re)post for the bot
  DELETE /api/guilds/<id>/self-roles/<mid>/post       -> queue removal of the posted message

Menus live in GuildSettings.extra["self_roles"] (self-heals, no migration).
message_id / needs_post / needs_delete / post_error are bot-owned — PUT
preserves them per menu id so a dashboard save never orphans a posted message.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

import access
import settings as settings_mod
from auth import login_required
from models import Guild
import role_policy
from self_roles import MAX_ENTRIES, MAX_MENUS

self_roles_bp = Blueprint("self_roles", __name__)

_STYLES = ("buttons", "reactions")


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _menus(row) -> list[dict]:
    return [dict(m) for m in ((row.extra or {}).get("self_roles") or [])]


def _parse_future_iso(val) -> str | None:
    """Normalize a client datetime to a future UTC ISO string, or None if it's
    missing/invalid/in the past (None = post immediately)."""
    if not val or not isinstance(val, str):
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    if dt <= datetime.utcnow():
        return None
    return dt.isoformat() + "Z"


def menu_status(menu: dict) -> str:
    """draft | scheduled | publishing | published | unpublished | failed - derived from
    the bot-owned fields, so the badge always reflects what the bot actually did."""
    if menu.get("post_error"):
        return "failed"
    if menu.get("needs_delete"):
        return "publishing"
    if menu.get("needs_post"):
        return "scheduled" if menu.get("post_at") else "publishing"
    if menu.get("message_id"):
        return "published"
    return "unpublished" if menu.get("unpublished") else "draft"


def _public(menu: dict) -> dict:
    return {
        "status": menu_status(menu),
        "posted_channel_id": menu.get("posted_channel_id"),
        "published_at": menu.get("published_at"),
        "id": menu.get("id"),
        "title": menu.get("title") or "",
        "description": menu.get("description") or "",
        "channel_id": menu.get("channel_id"),
        "style": menu.get("style") or "buttons",
        "max_one": bool(menu.get("max_one")),
        "entries": menu.get("entries") or [],
        "message_id": menu.get("message_id"),
        "needs_post": bool(menu.get("needs_post")),
        "needs_delete": bool(menu.get("needs_delete")),
        "post_error": menu.get("post_error"),
        "post_at": menu.get("post_at"),
    }


@self_roles_bp.get("/api/guilds/<int:guild_id>/self-roles")
@login_required
def list_menus(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify(menus=[_public(m) for m in _menus(row)])


@self_roles_bp.put("/api/guilds/<int:guild_id>/self-roles")
@login_required
def update_menus(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("menus"), list):
        return jsonify(error="menus_must_be_a_list"), 400
    row = settings_mod.get_or_create(g.db, guild_id)
    current = {int(m["id"]): m for m in _menus(row) if str(m.get("id", "")).isdigit()
               or isinstance(m.get("id"), int)}
    next_id = max(current.keys(), default=0) + 1

    cleaned = []
    for m_in in body["menus"][:MAX_MENUS]:
        if not isinstance(m_in, dict):
            continue
        try:
            mid = int(m_in.get("id"))
        except (TypeError, ValueError):
            mid = 0
        old = current.get(mid)
        if old is None:
            mid, next_id = next_id, next_id + 1

        entries = []
        for e in (m_in.get("entries") or [])[:MAX_ENTRIES]:
            if not isinstance(e, dict) or not str(e.get("role_id", "")).isdigit():
                continue
            entries.append({
                "emoji": str(e.get("emoji") or "").strip()[:64],
                "label": str(e.get("label") or "").strip()[:80] or "Role",
                "role_id": str(e["role_id"]),
            })

        ch = m_in.get("channel_id")
        cleaned.append({
            "id": mid,
            "title": str(m_in.get("title") or "").strip()[:100] or "Pick your roles",
            "description": str(m_in.get("description") or "").strip()[:1000],
            "channel_id": str(ch) if ch and str(ch).isdigit() else None,
            "style": m_in.get("style") if m_in.get("style") in _STYLES else "buttons",
            "max_one": bool(m_in.get("max_one")),
            "entries": entries,
            # bot-owned fields survive the round-trip
            "message_id": (old or {}).get("message_id"),
            "needs_post": bool((old or {}).get("needs_post")),
            "needs_delete": bool((old or {}).get("needs_delete")),
            "post_error": (old or {}).get("post_error"),
            "post_at": (old or {}).get("post_at"),
            "posted_channel_id": (old or {}).get("posted_channel_id"),
            "unpublished": bool((old or {}).get("unpublished")),
            "publishing_since": (old or {}).get("publishing_since"),
            "published_at": (old or {}).get("published_at"),
        })

    # Server-side privilege guard (the UI hides these too): a menu entry may never
    # map to a role with moderation/management permissions, @everyone or an
    # integration role — e.g. an "Ambassador" button pointing at "Admin".
    bad = role_policy.check_roles(g.db, guild_id, {e["role_id"] for m in cleaned for e in m["entries"]})
    # Entries already saved before keep saving (a role that LATER gained a permission must not
    # make the whole list unsaveable); only newly added unsafe mappings are refused.
    already = {str(e.get("role_id")) for m in current.values() for e in (m.get("entries") or [])}
    bad = {k: v for k, v in bad.items() if k not in already}
    if bad:
        return jsonify(error="role_not_assignable", roles=bad), 400

    extra = dict(row.extra or {})
    extra["self_roles"] = cleaned
    row.extra = extra
    settings_mod.touch(row)
    g.db.commit()
    return jsonify(menus=[_public(m) for m in cleaned])


def _queue(guild_id: int, menu_id: int, patch: dict):
    row = settings_mod.get_or_create(g.db, guild_id)
    menus = _menus(row)
    target = next((m for m in menus if int(m.get("id") or 0) == menu_id), None)
    if target is None:
        return None
    target.update(patch)
    extra = dict(row.extra or {})
    extra["self_roles"] = menus
    row.extra = extra
    settings_mod.touch(row)
    g.db.commit()
    return target


@self_roles_bp.post("/api/guilds/<int:guild_id>/self-roles/<int:menu_id>/post")
@login_required
def queue_post(guild_id: int, menu_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    target = next((m for m in _menus(row) if int(m.get("id") or 0) == menu_id), None)
    if target is None:
        return jsonify(error="not_found"), 404
    if not target.get("channel_id"):
        return jsonify(error="no_channel", message="Pick a channel for this menu first."), 400
    if not (target.get("entries") or []):
        return jsonify(error="no_entries", message="Add at least one role first."), 400
    body = request.get_json(silent=True) or {}
    raw_at = body.get("post_at")
    post_at = _parse_future_iso(raw_at)
    if raw_at and post_at is None:
        return jsonify(error="bad_time", message="Pick a date and time in the future."), 400
    _queue(guild_id, menu_id, {"needs_post": True, "needs_delete": False,
                               "post_error": None, "post_at": post_at, "unpublished": False})
    return jsonify(ok=True, post_status="scheduled" if post_at else "queued", post_at=post_at)


@self_roles_bp.delete("/api/guilds/<int:guild_id>/self-roles/<int:menu_id>/post")
@login_required
def queue_unpost(guild_id: int, menu_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    cur = next((m for m in _menus(row) if int(m.get("id") or 0) == menu_id), None)
    if cur is None:
        return jsonify(error="not_found"), 404
    if not cur.get("message_id"):
        # Nothing is live: this just cancels a queued/scheduled post (or clears a failure).
        _queue(guild_id, menu_id, {"needs_post": False, "post_at": None, "post_error": None})
        return jsonify(ok=True, cancelled=True)
    _queue(guild_id, menu_id, {"needs_delete": True, "needs_post": False, "post_at": None})
    return jsonify(ok=True)
