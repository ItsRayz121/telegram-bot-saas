"""Central roles API (Role Hub + Settings -> Role Directory). Read-only except create.

  GET  /api/guilds/<id>/roles/overview             roles + live member counts + usage
  GET  /api/guilds/<id>/roles/<rid>/members        who holds a role (search, paginated)
  POST /api/guilds/<id>/roles/create               make a plain, permission-less role

Member counts come from Discord's own paginated member list (not a gateway cache),
held in a short per-guild cache so a busy dashboard doesn't hammer Discord. When the
list is truncated or unavailable the response says so (`status`) - it never turns
"unknown" into 0. Inspection never edits a role or a member.
"""
from __future__ import annotations

import time

from flask import Blueprint, g, jsonify, request

import access
import discord_api
import role_policy
import settings as settings_mod
import team_direct
from auth import login_required
from models import Guild, ProtectionEvent, Role

roles_bp = Blueprint("roles", __name__)

_CACHE_TTL = 60
_cache: dict = {}     # guild -> (monotonic ts, members, complete)
_MAX_PAGE = 100


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _members(guild: Guild, refresh: bool = False):
    """(members, complete) or raises. Cached _CACHE_TTL seconds per guild."""
    hit = _cache.get(guild.id)
    if hit and not refresh and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1], hit[2]
    token = team_direct.bot_token_for(g.db, guild)
    members, complete = discord_api.list_guild_members(guild.id, token)
    if len(_cache) > 200:                       # bounded
        _cache.clear()
    _cache[guild.id] = (time.monotonic(), members, complete)
    return members, complete


def _user_card(m: dict) -> dict:
    u = m.get("user") or {}
    return {"id": str(u.get("id")), "username": u.get("username"),
            "display": m.get("nick") or u.get("global_name") or u.get("username"),
            "avatar_url": discord_api.avatar_url(u), "bot": bool(u.get("bot"))}


def _category(role: Role, privileged: bool) -> str:
    if role.managed:
        return "integration"
    return "staff" if privileged else "community"


def _usage(db, guild_id: int) -> dict:
    """Where each role is wired in: self-role menus, level rewards, auto-roles."""
    row = settings_mod.get_or_create(db, guild_id)
    use: dict = {}

    def slot(rid):
        return use.setdefault(str(rid), {"self_role_menus": [], "level_rewards": [], "auto_role": False})
    for m in (row.extra or {}).get("self_roles") or []:
        for e in m.get("entries") or []:
            if str(e.get("role_id", "")).isdigit():
                slot(e["role_id"])["self_role_menus"].append(m.get("title") or "Menu")
    for r in ((row.extra or {}).get("leveling2") or {}).get("role_rewards") or []:
        if str(r.get("role_id", "")).isdigit():
            slot(r["role_id"])["level_rewards"].append(int(r.get("level") or 1))
    if row.autorole_enabled:
        for rid in row.autorole_ids or []:
            slot(rid)["auto_role"] = True
    return use


@roles_bp.get("/api/guilds/<int:guild_id>/roles/overview")
@login_required
def roles_overview(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild = g.db.get(Guild, guild_id)
    roles = g.db.query(Role).filter(Role.guild_id == guild_id).all()
    use = _usage(g.db, guild_id)
    include_bots = request.args.get("bots") == "1"

    status, counts, totals, fetched = "unavailable", {}, None, None
    if guild.is_served:
        try:
            members, complete = _members(guild, refresh=request.args.get("refresh") == "1")
            status = "complete" if complete else "partial"
            fetched = _cache[guild_id][0]
            pool = [m for m in members if include_bots or not (m.get("user") or {}).get("bot")]
            for m in pool:
                for rid in m.get("roles") or []:
                    counts[str(rid)] = counts.get(str(rid), 0) + 1
            totals = {"members": len(pool), "bots": sum(1 for m in members if (m.get("user") or {}).get("bot"))}
        except Exception:
            status = "unavailable"          # e.g. Server Members intent off: counts stay unknown

    out = []
    for r in sorted(roles, key=lambda r: -(r.position or 0)):
        everyone = r.id == guild_id or r.name == "@everyone"
        priv = bool(role_policy.dangerous_perms(r.permissions))
        d = r.to_dict()
        if status == "unavailable":
            count = None
        elif everyone:
            count = totals["members"]
        else:
            count = counts.get(str(r.id), 0)
        d.update(
            id=str(r.id), everyone=everyone, privileged=priv, category=_category(r, priv),
            assignable=role_policy.role_problem(r, guild_id) is None,
            member_count=count,
            usage=use.get(str(r.id), {"self_role_menus": [], "level_rewards": [], "auto_role": False}),
        )
        out.append(d)
    return jsonify(roles=out, status=status, totals=totals, bots_included=include_bots,
                   age_seconds=int(time.monotonic() - fetched) if fetched else None)


@roles_bp.get("/api/guilds/<int:guild_id>/roles/<int:role_id>/members")
@login_required
def role_members(guild_id: int, role_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild = g.db.get(Guild, guild_id)
    role = g.db.get(Role, role_id)
    if role is None or role.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    if not guild.is_served:
        return jsonify(error="bot_not_in_server"), 409
    try:
        members, complete = _members(guild)
    except Exception:
        return jsonify(error="members_unavailable"), 502
    include_bots = request.args.get("bots") == "1"
    everyone = role_id == guild_id
    q = (request.args.get("q") or "").strip().lower()[:64]
    rows = [m for m in members
            if (everyone or str(role_id) in [str(x) for x in m.get("roles") or []])
            and (include_bots or not (m.get("user") or {}).get("bot"))]
    cards = [_user_card(m) for m in rows]
    if q:
        cards = [c for c in cards if q in (c["username"] or "").lower()
                 or q in (c["display"] or "").lower() or q in c["id"]]
    cards.sort(key=lambda c: (c["display"] or "").lower())
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = max(1, min(_MAX_PAGE, int(request.args.get("limit", 25))))
    except ValueError:
        page, limit = 1, 25
    start = (page - 1) * limit
    return jsonify(members=cards[start:start + limit], total=len(cards), page=page,
                   status="complete" if complete else "partial",
                   role={"id": str(role.id), "name": role.name, "color": role.color_hex(),
                         "managed": bool(role.managed)})


@roles_bp.post("/api/guilds/<int:guild_id>/roles/create")
@login_required
def create_role(guild_id: int):
    """Create a plain role (no permissions) for a contribution rank / self-role."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild = g.db.get(Guild, guild_id)
    if not guild.is_served:
        return jsonify(error="bot_not_in_server"), 409
    body = request.get_json(silent=True) or {}
    name = " ".join(str(body.get("name") or "").split())[:100]
    if not name:
        return jsonify(error="name_required"), 400
    if name.lower() in ("everyone", "@everyone", "here", "@here"):
        return jsonify(error="bad_name"), 400
    for r in g.db.query(Role).filter(Role.guild_id == guild_id).all():
        if (r.name or "").lower() == name.lower():      # retry / double-click safety: reuse
            return jsonify(error="already_exists", role=r.to_dict()), 409
    color = 0
    raw = str(body.get("color") or "").lstrip("#")
    if len(raw) == 6:
        try:
            color = int(raw, 16)
        except ValueError:
            color = 0
    token = team_direct.bot_token_for(g.db, guild)
    try:
        made = discord_api.create_role(guild_id, name, color, token, "Guildizer dashboard: contribution role")
    except Exception as exc:  # noqa: BLE001
        status = getattr(getattr(exc, "response", None), "status_code", None)
        code = "missing_permission" if status in (401, 403) else ("role_limit" if status == 400 else "discord_error")
        return jsonify(error=code), 502
    role = Role(id=int(made["id"]), guild_id=guild_id, name=made.get("name") or name,
                color=int(made.get("color") or 0), position=int(made.get("position") or 0),
                permissions=str(made.get("permissions") or "0"), managed=False,
                mentionable=bool(made.get("mentionable")))
    g.db.merge(role)
    g.db.add(ProtectionEvent(guild_id=guild_id, category="role_policy", action="role_created",
                             user_id=g.user_id, detail=("Created role " + name)[:255]))
    g.db.commit()
    return jsonify(role=role.to_dict()), 201
