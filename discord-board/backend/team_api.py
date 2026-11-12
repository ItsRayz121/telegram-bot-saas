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

import os
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

import access
import team_direct
from auth import login_required
from models import Guild, GuildTeamMember, Member, TeamInvite, User, UserGuild, UserNotification

team_bp = Blueprint("team", __name__)

MAX_SEATS = 10
INVITE_TTL_DAYS = 7


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _owner_or_403(guild_id: int):
    """Seat management (invite / promote / remove) is for people with Discord Manage Server on
    this server, NOT for team seats - otherwise a "manager" seat could mint more managers or
    lock the real admins out. Kill switch GUILD_TEAM_MANAGER_CAN_INVITE=1 restores the old rule."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return ok, err
    if os.environ.get("GUILD_TEAM_MANAGER_CAN_INVITE", "0").strip().lower() in ("1", "true", "on", "yes"):
        return True, None
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})
    if membership is None or not membership.can_manage:
        return False, (jsonify(error="owner_only",
                               message="Only people with Manage Server on Discord can change the team."), 403)
    return True, None


def _disabled():
    return jsonify(error="team_access_disabled", message="Team access is temporarily disabled."), 503


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
    role = access.role_for_ui(g.db, g.user_id, guild_id)
    codes, direct = [], []
    # Open access codes are secrets (anyone holding one can join as its role), so a read-only
    # viewer never sees them.
    if role != "viewer":
        codes = (
            g.db.query(TeamInvite)
            .filter(TeamInvite.guild_id == guild_id,
                    TeamInvite.invitee_discord_id.is_(None),
                    TeamInvite.used_by.is_(None),
                    TeamInvite.expires_at > datetime.utcnow())
            .all()
        )
        direct = team_direct.open_direct(g.db, guild_id)
    since = datetime.utcnow() - timedelta(days=90)
    history = (
        g.db.query(TeamInvite)
        .filter(TeamInvite.guild_id == guild_id, TeamInvite.invitee_discord_id.isnot(None),
                TeamInvite.created_at >= since)
        .order_by(TeamInvite.created_at.desc()).limit(30).all()
    )
    return jsonify(members=[m.to_dict() for m in members],
                   invites=[i.to_dict() for i in codes],
                   direct_invites=[i.to_dict() for i in direct],
                   invitations=[i.to_dict() for i in history],
                   your_role=role,
                   enabled=access.team_access_enabled(),
                   direct_enabled=team_direct.direct_invites_enabled())


@team_bp.get("/api/guilds/<int:guild_id>/team/candidates")
@login_required
def candidates(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    return jsonify(members=team_direct.candidates(
        g.db, guild_id, request.args.get("q", ""), exclude_user_id=g.user_id))


@team_bp.post("/api/guilds/<int:guild_id>/team/invites/direct")
@login_required
def create_direct_invite(guild_id: int):
    ok, err = _owner_or_403(guild_id)
    if not ok:
        return err
    if not team_direct.direct_invites_enabled():
        return jsonify(error="direct_disabled",
                       message="Invitations are temporarily disabled. Use an access code instead."), 503
    body = request.get_json(silent=True) or {}
    role = body.get("role", "manager")
    if role not in team_direct.ROLES:
        return jsonify(error="bad_role"), 400
    raw = str(body.get("discord_user_id") or "").strip()
    if not raw.isdigit():
        return jsonify(error="bad_user"), 400
    invitee = int(raw)
    if invitee == g.user_id:
        return jsonify(error="self_invite", message="You already have access."), 400
    guild = g.db.get(Guild, guild_id)
    row = g.db.get(Member, {"guild_id": guild_id, "user_id": invitee})
    if row is None:
        return jsonify(error="not_a_member", message="That person is not in this server's member list."), 400
    managing = g.db.get(UserGuild, {"user_id": invitee, "guild_id": guild_id})
    if managing is not None and managing.can_manage:
        return jsonify(error="already_manager", message="They already manage this server."), 400
    # A new invitation SUPERSEDES any earlier unanswered one to the same person
    # (pending or expired): the old row goes away, so its Accept / Reject buttons stop
    # working and only the newest invitation can be answered. Accepted / declined
    # history is untouched. (Telegizer parity: re-sending always works.)
    g.db.query(TeamInvite).filter(
        TeamInvite.guild_id == guild_id, TeamInvite.invitee_discord_id == invitee,
        TeamInvite.used_by.is_(None), TeamInvite.declined_at.is_(None),
    ).delete(synchronize_session=False)
    g.db.flush()
    open_now = team_direct.open_direct(g.db, guild_id)
    seats = g.db.query(GuildTeamMember).filter(GuildTeamMember.guild_id == guild_id).count()
    if seats + len(open_now) >= MAX_SEATS:
        return jsonify(error="seat_limit_reached", limit=MAX_SEATS), 403
    me = g.db.get(User, g.user_id)
    owner_name = ((me.global_name or me.username) if me else None) or "A server manager"
    inv = TeamInvite(guild_id=guild_id, code=secrets.token_urlsafe(12), role=role, created_by=g.user_id,
                     invitee_discord_id=invitee, invitee_name=row.username,
                     expires_at=datetime.utcnow() + timedelta(days=INVITE_TTL_DAYS))
    g.db.add(inv)
    # Commit BEFORE messaging: the Accept button must never point at a row that was
    # rolled back, which is what used to make a delivered invitation read "no longer valid".
    g.db.commit()
    result = inv.to_dict()
    sent, derr = team_direct.send_dm(
        team_direct.bot_token_for(g.db, guild), invitee,
        team_direct.invite_message(guild.name, owner_name, role, inv.id))
    if not sent:
        try:
            g.db.query(TeamInvite).filter(TeamInvite.id == result["id"]).delete(synchronize_session=False)
            g.db.commit()
        except Exception:  # noqa: BLE001
            g.db.rollback()
        return jsonify(error="dm_failed", message=derr), 502
    return jsonify(invite=result), 201


@team_bp.patch("/api/guilds/<int:guild_id>/team/members/<int:user_id>")
@login_required
def set_member_role(guild_id: int, user_id: int):
    ok, err = _owner_or_403(guild_id)
    if not ok:
        return err
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in team_direct.ROLES:
        return jsonify(error="bad_role"), 400
    row = g.db.get(GuildTeamMember, {"guild_id": guild_id, "user_id": user_id})
    if row is None:
        return jsonify(error="not_found"), 404
    row.role = role
    g.db.commit()
    return jsonify(member=row.to_dict())


@team_bp.post("/api/guilds/<int:guild_id>/team/invites")
@login_required
def create_invite(guild_id: int):
    ok, err = _owner_or_403(guild_id)
    if not ok:
        return err
    if not access.team_access_enabled():
        return _disabled()
    role = (request.get_json(silent=True) or {}).get("role", "manager")
    if role not in team_direct.ROLES:
        return jsonify(error="bad_role"), 400
    seats = g.db.query(GuildTeamMember).filter(GuildTeamMember.guild_id == guild_id).count()
    if seats >= MAX_SEATS:
        return jsonify(error="seat_limit_reached", limit=MAX_SEATS), 403
    invite = TeamInvite(
        guild_id=guild_id, code=secrets.token_urlsafe(12), role=role,
        created_by=g.user_id,
        expires_at=datetime.utcnow() + timedelta(days=INVITE_TTL_DAYS),
    )
    g.db.add(invite)
    g.db.commit()
    return jsonify(invite=invite.to_dict()), 201


@team_bp.delete("/api/guilds/<int:guild_id>/team/invites/<int:iid>")
@login_required
def delete_invite(guild_id: int, iid: int):
    ok, err = _owner_or_403(guild_id)
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
    ok, err = _owner_or_403(guild_id)
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
    if not access.team_access_enabled():
        return _disabled()
    code = ((request.get_json(silent=True) or {}).get("code") or "").strip()
    if not code:
        return jsonify(error="code_required"), 400
    invite = g.db.query(TeamInvite).filter(TeamInvite.code == code).one_or_none()
    if (invite is None or invite.used_by is not None or invite.declined_at is not None
            or invite.invitee_discord_id is not None          # direct invites are accepted in the DM, never by code
            or invite.expires_at <= datetime.utcnow()):
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
