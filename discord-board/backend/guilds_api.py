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
    for membership, guild in rows:
        data = guild.to_dict()
        data["is_owner"] = bool(membership.is_owner)
        if not guild.bot_present:
            data["invite_url"] = _build_invite_url(guild.id)
        out.append(data)
    # bot-present servers first, then alphabetical
    out.sort(key=lambda d: (not d["bot_present"], (d["name"] or "").lower()))
    return jsonify(guilds=out, invite_url=_build_invite_url())


@guilds_bp.get("/api/guilds/<int:guild_id>")
@login_required
def guild_detail(guild_id: int):
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})
    if membership is None or not membership.can_manage:
        return jsonify(error="forbidden"), 403

    guild = g.db.get(Guild, guild_id)
    if guild is None:
        return jsonify(error="not_found"), 404

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
    data["is_owner"] = bool(membership.is_owner)
    data["channels"] = [c.to_dict() for c in channels]
    data["roles"] = [r.to_dict() for r in roles]
    if not guild.bot_present:
        data["invite_url"] = _build_invite_url(guild_id)
    return jsonify(data)


@guilds_bp.get("/api/guilds/<int:guild_id>/invite")
@login_required
def guild_invite(guild_id: int):
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})
    if membership is None or not membership.can_manage:
        return jsonify(error="forbidden"), 403
    return jsonify(invite_url=_build_invite_url(guild_id))
