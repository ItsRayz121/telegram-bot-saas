"""Role applications + staff grant/revoke (dashboard side).

  GET/PUT /api/guilds/<id>/roles/applications/config   which roles members may apply for
  GET     /api/guilds/<id>/roles/applications          the queue (status filter)
  POST    /api/guilds/<id>/roles/applications/<n>/review   approve (grants the real role) / reject
  PUT/DELETE /api/guilds/<id>/roles/<rid>/members/<uid>    staff manual grant / revoke

Every path refuses a role carrying moderation/management permissions (role_policy), so
none of them can be used to hand out staff powers. Reviews are final and race-safe.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

import access
import discord_api
import role_apps
import role_policy
import settings as settings_mod
import team_direct
from auth import login_required
from models import Guild, ProtectionEvent, Role, RoleApplication

role_apps_bp = Blueprint("role_apps", __name__)


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _grant_error_code(exc) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return "missing_permission"      # bot lacks Manage Roles or sits below the role
    if status == 404:
        return "member_or_role_gone"
    return "discord_error"


def _audit(guild_id: int, action: str, user_id, detail: str):
    g.db.add(ProtectionEvent(guild_id=guild_id, category="role_policy", action=action,
                             user_id=user_id, detail=detail[:255]))


@role_apps_bp.get("/api/guilds/<int:guild_id>/roles/applications/config")
@login_required
def apps_config(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    return jsonify(roles=role_apps.configured_roles(row.extra))


@role_apps_bp.put("/api/guilds/<int:guild_id>/roles/applications/config")
@login_required
def apps_config_save(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    roles, seen = [], set()
    for r in (body.get("roles") or [])[:role_apps.MAX_ROLES]:
        rid = str((r or {}).get("role_id") or "")
        if rid.isdigit() and rid not in seen:
            seen.add(rid)
            roles.append({"role_id": rid, "label": str(r.get("label") or "").strip()[:60]})
    bad = role_policy.check_roles(g.db, guild_id, [r["role_id"] for r in roles])
    if bad:
        return jsonify(error="role_not_assignable", roles=bad), 400
    row = settings_mod.get_or_create(g.db, guild_id)
    extra = dict(row.extra or {})
    extra["role_apps"] = {"roles": roles}
    row.extra = extra
    settings_mod.touch(row)
    g.db.commit()
    return jsonify(roles=roles)


@role_apps_bp.get("/api/guilds/<int:guild_id>/roles/applications")
@login_required
def apps_list(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    status = request.args.get("status", "pending")
    q = g.db.query(RoleApplication).filter(RoleApplication.guild_id == guild_id)
    if status in ("pending", "approved", "rejected"):
        q = q.filter(RoleApplication.status == status)
    rows = q.order_by(RoleApplication.created_at.desc()).limit(100).all()
    names = {r.id: r.name for r in g.db.query(Role).filter(Role.guild_id == guild_id).all()}
    return jsonify(applications=[{**a.to_dict(), "role_name": names.get(a.role_id, str(a.role_id))} for a in rows])


@role_apps_bp.post("/api/guilds/<int:guild_id>/roles/applications/<int:app_id>/review")
@login_required
def apps_review(guild_id: int, app_id: int):
    """Approve (grants the real Discord role) or reject. Final: a second review of the
    same application is refused, and two reviewers racing cannot both grant."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild = g.db.get(Guild, guild_id)
    body = request.get_json(silent=True) or {}
    decision = body.get("decision")
    if decision not in ("approve", "reject"):
        return jsonify(error="bad_decision"), 400
    note = str(body.get("note") or "").strip()[:300] or None
    app = g.db.get(RoleApplication, app_id)
    if app is None or app.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    # Claim it atomically so only one reviewer proceeds. A claim older than 2 minutes is a
    # crashed request and may be taken over; reviewed_at doubles as the claim time.
    now = datetime.utcnow()
    claimed = (g.db.query(RoleApplication)
               .filter(RoleApplication.id == app_id, RoleApplication.status == "pending")
               .update({"status": "reviewing", "reviewed_at": now}, synchronize_session=False))
    if not claimed:
        claimed = (g.db.query(RoleApplication)
                   .filter(RoleApplication.id == app_id, RoleApplication.status == "reviewing",
                           RoleApplication.reviewed_at < now - timedelta(minutes=2))
                   .update({"reviewed_at": now}, synchronize_session=False))
    g.db.commit()
    if not claimed:
        return jsonify(error="already_reviewed"), 409
    g.db.refresh(app)

    def release(code=None, http=502):
        g.db.rollback()
        app.status, app.grant_error, app.reviewed_at = "pending", code, None
        g.db.commit()
        return jsonify(error=code or "discord_error"), http

    try:
        if decision == "approve":
            if role_policy.check_roles(g.db, guild_id, [app.role_id]):
                return release("role_not_assignable", 400)
            if not guild.is_served:
                return release("bot_not_in_server", 409)
            try:
                discord_api.set_member_role(guild_id, app.user_id, app.role_id, True,
                                            team_direct.bot_token_for(g.db, guild),
                                            "Guildizer: role application approved")
            except Exception as exc:  # noqa: BLE001
                return release(_grant_error_code(exc))
            app.status, app.grant_error = "approved", None
        else:
            app.status = "rejected"
        app.reviewer_id, app.review_note, app.reviewed_at = g.user_id, note, datetime.utcnow()
        _audit(guild_id, "app_" + app.status, app.user_id,
               "Role application #%d %s (role %d)" % (app.id, app.status, app.role_id))
        g.db.commit()
    except Exception:  # noqa: BLE001 - any failure after the claim puts it back in the queue
        return release("discord_error", 500)
    return jsonify(application=app.to_dict())


def _staff_set(guild_id: int, role_id: int, user_id: int, add: bool):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild = g.db.get(Guild, guild_id)
    if not guild.is_served:
        return jsonify(error="bot_not_in_server"), 409
    role = g.db.get(Role, role_id)
    if role is None or role.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    if role_policy.role_problem(role, guild_id):
        return jsonify(error="role_not_assignable"), 400
    try:
        discord_api.set_member_role(guild_id, user_id, role_id, add, team_direct.bot_token_for(g.db, guild),
                                    "Guildizer dashboard: staff " + ("grant" if add else "revoke"))
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=_grant_error_code(exc)), 502
    _audit(guild_id, "staff_grant" if add else "staff_revoke", user_id,
           "%s %s (by %s)" % ("Granted" if add else "Removed", role.name, g.user_id))
    g.db.commit()
    return jsonify(ok=True)


@role_apps_bp.put("/api/guilds/<int:guild_id>/roles/<int:role_id>/members/<int:user_id>")
@login_required
def staff_grant(guild_id: int, role_id: int, user_id: int):
    return _staff_set(guild_id, role_id, user_id, True)


@role_apps_bp.delete("/api/guilds/<int:guild_id>/roles/<int:role_id>/members/<int:user_id>")
@login_required
def staff_revoke(guild_id: int, role_id: int, user_id: int):
    return _staff_set(guild_id, role_id, user_id, False)
