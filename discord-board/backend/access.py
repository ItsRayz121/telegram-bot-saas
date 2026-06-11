"""Shared dashboard-access + notification helpers (Phase 18).

can_manage_guild() is THE access check for guild-scoped endpoints: Discord
Manage Server (UserGuild.can_manage, from OAuth) OR a team seat granted via a
redeemed TeamInvite (GuildTeamMember). Every *_api module uses this so team
members get full dashboard access without Discord-side permissions.
"""
from __future__ import annotations

from flask import jsonify

from models import Guild, GuildTeamMember, UserGuild, UserNotification


def can_manage_guild(db, user_id: int, guild_id: int) -> bool:
    membership = db.get(UserGuild, {"user_id": user_id, "guild_id": guild_id})
    if membership is not None and membership.can_manage:
        return True
    seat = db.get(GuildTeamMember, {"guild_id": guild_id, "user_id": user_id})
    return seat is not None


def manage_or_403(db, user_id: int, guild_id: int):
    """(ok, error_response) helper matching the *_api convention."""
    if not can_manage_guild(db, user_id, guild_id):
        return False, (jsonify(error="forbidden"), 403)
    if db.get(Guild, guild_id) is None:
        return False, (jsonify(error="not_found"), 404)
    return True, None


def team_guild_ids(db, user_id: int) -> list[int]:
    rows = db.query(GuildTeamMember.guild_id).filter(GuildTeamMember.user_id == user_id).all()
    return [gid for (gid,) in rows]


def notify(db, user_id: int, title: str, body: str = "", kind: str = "info") -> None:
    """Queue a dashboard notification. Caller commits."""
    db.add(UserNotification(
        user_id=user_id, kind=kind if kind in ("info", "warning", "error") else "info",
        title=(title or "")[:120], body=(body or "")[:500] or None,
    ))
