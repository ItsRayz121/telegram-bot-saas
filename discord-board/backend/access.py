"""Shared dashboard-access + notification helpers (Phase 18).

can_manage_guild() is THE access check for guild-scoped endpoints: Discord
Manage Server (UserGuild.can_manage, from OAuth) OR a team seat granted via a
redeemed TeamInvite (GuildTeamMember). Every *_api module uses this so team
members get full dashboard access without Discord-side permissions.
"""
from __future__ import annotations

import os

from flask import has_request_context, jsonify, request

from models import Guild, GuildTeamMember, UserGuild, UserNotification


def team_access_enabled() -> bool:
    """Kill switch: GUILD_TEAM_ACCESS_ENABLED=0 stops team seats granting any access and
    refuses new invites. People with Manage Server on Discord are unaffected."""
    return os.environ.get("GUILD_TEAM_ACCESS_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def team_role(db, user_id: int, guild_id: int):
    """'manager' | 'viewer' for a team seat, None when the user has no (usable) seat."""
    if not team_access_enabled():
        return None
    seat = db.get(GuildTeamMember, {"guild_id": guild_id, "user_id": user_id})
    if seat is None:
        return None
    return seat.role if seat.role in ("manager", "viewer") else "manager"


def role_for_ui(db, user_id: int, guild_id: int):
    """'owner' | 'manager' | 'viewer' for the dashboard banner, None without access."""
    membership = db.get(UserGuild, {"user_id": user_id, "guild_id": guild_id})
    if membership is not None and membership.can_manage:
        return "owner" if membership.is_owner else "manager"
    return team_role(db, user_id, guild_id)


def can_manage_guild(db, user_id: int, guild_id: int) -> bool:
    membership = db.get(UserGuild, {"user_id": user_id, "guild_id": guild_id})
    if membership is not None and membership.can_manage:
        return True
    role = team_role(db, user_id, guild_id)
    if role is None:
        return False
    if role == "viewer" and has_request_context() and request.method not in _SAFE_METHODS:
        return False        # viewers are read-only: every write endpoint refuses them
    return True


def manage_or_403(db, user_id: int, guild_id: int):
    """(ok, error_response) helper matching the *_api convention."""
    if not can_manage_guild(db, user_id, guild_id):
        return False, (jsonify(error="forbidden"), 403)
    if db.get(Guild, guild_id) is None:
        return False, (jsonify(error="not_found"), 404)
    return True, None


def team_guild_ids(db, user_id: int) -> list[int]:
    if not team_access_enabled():
        return []
    rows = db.query(GuildTeamMember.guild_id).filter(GuildTeamMember.user_id == user_id).all()
    return [gid for (gid,) in rows]


def notify(db, user_id: int, title: str, body: str = "", kind: str = "info") -> None:
    """Queue a dashboard notification (caller commits) + best-effort web push.

    Coalesces bursts: if an unread notification with the same title landed in the
    last 90s, it's updated in place (buzz once, then update quietly) instead of
    stacking up a flood."""
    from datetime import datetime, timedelta
    kind = kind if kind in ("info", "warning", "error") else "info"
    title = (title or "")[:120]
    body = (body or "")[:500] or None
    try:
        cutoff = datetime.utcnow() - timedelta(seconds=90)
        recent = (
            db.query(UserNotification)
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.title == title,
                UserNotification.read.is_(False),
                UserNotification.created_at >= cutoff,
            )
            .order_by(UserNotification.created_at.desc())
            .first()
        )
    except Exception:
        recent = None
    if recent is not None:
        recent.body = body
        recent.kind = kind
        recent.created_at = datetime.utcnow()
        return  # quiet update — no second push buzz
    db.add(UserNotification(user_id=user_id, kind=kind, title=title, body=body))
    # Fan out an OS-level push if the user opted in. Best-effort; never raises.
    try:
        from web_push import maybe_push_notification
        maybe_push_notification(db, user_id, title, body, kind)
    except Exception:
        pass
