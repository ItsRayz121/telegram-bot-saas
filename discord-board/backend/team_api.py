"""Team seats + notifications endpoints (Phase 18).

  GET    /api/guilds/<id>/team                 members + open invites
  POST   /api/guilds/<id>/team/invites         create a one-use invite code
  DELETE /api/guilds/<id>/team/invites/<iid>
  DELETE /api/guilds/<id>/team/members/<uid>
  POST   /api/team/redeem                      {code} — any logged-in user
  GET    /api/notifications                    latest + unread count
  POST   /api/notifications/read               mark all read
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

import access
from auth import login_required
from models import Guild, GuildTeamMember, TeamInvite, User, UserNotification

team_bp = Blueprint("team", __name__)

MAX_SEATS = 10
INVITE_TTL_DAYS = 7


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


@team_bp.get("/api/guilds/<int:guild_id>/team")
@login_required
def team(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    members = (
        g.db.query(GuildTeamMember)
        .filter(GuildTeamMember.guild_id == guild_id)
        .all()
    )
    invites = (
        g.db.query(TeamInvite)
        .filter(TeamInvite.guild_id == guild_id,
                TeamInvite.used_by.is_(None),
                TeamInvite.expires_at > datetime.utcnow())
        .all()
    )
    return jsonify(members=[m.to_dict() for m in members],
                   invites=[i.to_dict() for i in invites])


@team_bp.post("/api/guilds/<int:guild_id>/team/invites")
@login_required
def create_invite(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    seats = g.db.query(GuildTeamMember).filter(GuildTeamMember.guild_id == guild_id).count()
    if seats >= MAX_SEATS:
        return jsonify(error="seat_limit_reached", limit=MAX_SEATS), 403
    invite = TeamInvite(
        guild_id=guild_id, code=secrets.token_urlsafe(12),
        created_by=g.user_id,
        expires_at=datetime.utcnow() + timedelta(days=INVITE_TTL_DAYS),
    )
    g.db.add(invite)
    g.db.commit()
    return jsonify(invite=invite.to_dict()), 201


@team_bp.delete("/api/guilds/<int:guild_id>/team/invites/<int:iid>")
@login_required
def delete_invite(guild_id: int, iid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(TeamInvite, iid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


@team_bp.delete("/api/guilds/<int:guild_id>/team/members/<int:user_id>")
@login_required
def remove_member(guild_id: int, user_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(GuildTeamMember, {"guild_id": guild_id, "user_id": user_id})
    if row is None:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    access.notify(g.db, user_id, "Team access removed",
                  "Your dashboard access to a server was removed.", "warning")
    g.db.commit()
    return jsonify(ok=True)


@team_bp.post("/api/team/redeem")
@login_required
def redeem():
    code = ((request.get_json(silent=True) or {}).get("code") or "").strip()
    if not code:
        return jsonify(error="code_required"), 400
    invite = g.db.query(TeamInvite).filter(TeamInvite.code == code).one_or_none()
    if invite is None or invite.used_by is not None or invite.expires_at <= datetime.utcnow():
        return jsonify(error="invalid_or_used_code"), 404
    guild = g.db.get(Guild, invite.guild_id)
    if guild is None:
        return jsonify(error="invalid_or_used_code"), 404
    existing = g.db.get(GuildTeamMember, {"guild_id": invite.guild_id, "user_id": g.user_id})
    if existing is None:
        me = g.db.get(User, g.user_id)
        g.db.add(GuildTeamMember(
            guild_id=invite.guild_id, user_id=g.user_id,
            username=(me.username if me else None),
            role=invite.role or "manager", invited_by=invite.created_by,
        ))
    invite.used_by = g.user_id
    invite.used_at = datetime.utcnow()
    access.notify(g.db, invite.created_by, "Team invite redeemed",
                  f"Your invite to {guild.name} was used.", "info")
    g.db.commit()
    return jsonify(ok=True, guild=guild.to_dict())


# --- notifications -------------------------------------------------------------------
@team_bp.get("/api/notifications")
@login_required
def notifications():
    rows = (
        g.db.query(UserNotification)
        .filter(UserNotification.user_id == g.user_id)
        .order_by(UserNotification.created_at.desc())
        .limit(30)
        .all()
    )
    unread = (
        g.db.query(UserNotification)
        .filter(UserNotification.user_id == g.user_id, UserNotification.read.is_(False))
        .count()
    )
    return jsonify(notifications=[n.to_dict() for n in rows], unread=unread)


@team_bp.post("/api/notifications/read")
@login_required
def mark_read():
    (
        g.db.query(UserNotification)
        .filter(UserNotification.user_id == g.user_id, UserNotification.read.is_(False))
        .update({"read": True})
    )
    g.db.commit()
    return jsonify(ok=True)
