"""Guild/server endpoints for the dashboard (Phase 1).

  GET /api/guilds                 -> the user's manageable servers (+ bot status)
  GET /api/guilds/<id>            -> one server's detail (channels + roles)
  GET /api/guilds/<id>/invite     -> the bot-invite OAuth2 URL for that server

All endpoints require a logged-in session (login_required sets g.user_id/g.db).
"""
from __future__ import annotations

from urllib.parse import urlencode

from flask import Blueprint, g, jsonify

import discord_api
import access
import guild_sync
from auth import login_required
from config import Config
from models import Channel, Guild, Role, UserGuild

guilds_bp = Blueprint("guilds", __name__)


def _build_invite_url(guild_id: int | None = None) -> str:
    params = {
        "client_id": Config.DISCORD_CLIENT_ID,
        "scope": "bot applications.commands",
        "permissions": str(discord_api.bot_invite_permissions()),
    }
    if guild_id is not None:
        params["guild_id"] = str(guild_id)
        params["disable_guild_select"] = "true"
    return f"{discord_api.AUTHORIZE_URL}?{urlencode(params)}"


@guilds_bp.get("/api/guilds")
@login_required
def list_guilds():
    """Servers the user can manage, each annotated with whether the bot is in it."""
    rows = (
        g.db.query(UserGuild, Guild)
        .join(Guild, UserGuild.guild_id == Guild.id)
        .filter(UserGuild.user_id == g.user_id, UserGuild.can_manage.is_(True))
        .all()
    )
    out = []
    seen = set()
    for membership, guild in rows:
        data = guild.to_dict()
        data["is_owner"] = bool(membership.is_owner)
        if not guild.bot_present:
            data["invite_url"] = _build_invite_url(guild.id)
        out.append(data)
        seen.add(guild.id)
    # guilds granted via a team seat (Phase 18)
    for gid in access.team_guild_ids(g.db, g.user_id):
        if gid in seen:
            continue
        guild = g.db.get(Guild, gid)
        if guild is None:
            continue
        data = guild.to_dict()
        data["is_owner"] = False
        data["via_team"] = True
        out.append(data)
    # bot-present servers first, then alphabetical
    out.sort(key=lambda d: (not d["bot_present"], (d["name"] or "").lower()))
    return jsonify(guilds=out, invite_url=_build_invite_url())


@guilds_bp.get("/api/guilds/<int:guild_id>")
@login_required
def guild_detail(guild_id: int):
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
        return jsonify(error="forbidden"), 403

    guild = g.db.get(Guild, guild_id)
    if guild is None:
        return jsonify(error="not_found"), 404

    # Team-seat users have no UserGuild row — they're never the owner.
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})

    channels = (
        g.db.query(Channel)
        .filter(Channel.guild_id == guild_id)
        .order_by(Channel.position)
        .all()
    )
    roles = (
        g.db.query(Role)
        .filter(Role.guild_id == guild_id)
        .order_by(Role.position.desc())
        .all()
    )

    data = guild.to_dict()
    data["is_owner"] = bool(membership.is_owner) if membership is not None else False
    data["channels"] = [c.to_dict() for c in channels]
    data["roles"] = [r.to_dict() for r in roles]
    if not guild.bot_present:
        data["invite_url"] = _build_invite_url(guild_id)
    return jsonify(data)


@guilds_bp.post("/api/guilds/<int:guild_id>/resync")
@login_required
def resync_guild(guild_id: int):
    """Pull the live channel + role list from Discord (REST) and refresh the DB,
    so roles/channels created in Discord after the last gateway sync appear in
    the dashboard without waiting for the bot to re-sync."""
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
        return jsonify(error="forbidden"), 403
    guild = g.db.get(Guild, guild_id)
    if guild is None:
        return jsonify(error="not_found"), 404
    if not guild.bot_present:
        return jsonify(error="bot_not_in_server"), 409
    try:
        channels_json = discord_api.get_guild_channels(guild_id)
        roles_json = discord_api.get_guild_roles(guild_id)
    except Exception:
        return jsonify(error="discord_unavailable"), 502
    guild_sync.sync_channels_rest(g.db, guild_id, channels_json)
    guild_sync.sync_roles_rest(g.db, guild_id, roles_json)
    g.db.commit()

    channels = (
        g.db.query(Channel).filter(Channel.guild_id == guild_id).order_by(Channel.position).all()
    )
    roles = (
        g.db.query(Role).filter(Role.guild_id == guild_id).order_by(Role.position.desc()).all()
    )
    return jsonify(
        channels=[c.to_dict() for c in channels],
        roles=[r.to_dict() for r in roles],
    )


@guilds_bp.get("/api/guilds/<int:guild_id>/invite")
@login_required
def guild_invite(guild_id: int):
    if not access.can_manage_guild(g.db, g.user_id, guild_id):
        return jsonify(error="forbidden"), 403
    return jsonify(invite_url=_build_invite_url(guild_id))
