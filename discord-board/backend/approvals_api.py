"""Staff approval queue for held severe actions (see mod_approvals.py).

  GET   /api/guilds/<id>/approvals?status=pending&kind=
  POST  /api/guilds/<id>/approvals/<n>/review   {decision: approve|reject}
  PUT   /api/guilds/<id>/approvals/settings     {require_approval: [...], rank_approval: bool}

Approving executes the held action through Discord. A failed execution leaves the item
pending with `result_error` so it can be retried; a review is otherwise final and
two reviewers racing cannot both execute it.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

import access
import discord_api
import protection
import role_policy
import settings as settings_mod
import team_direct
from auth import login_required
from models import Guild, ModApproval, ProtectionEvent

approvals_bp = Blueprint("approvals", __name__)
_KINDS = ("kick", "ban", "timeout")


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _code(exc) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return "missing_permission"      # hierarchy or permission: bot role too low
    if status == 404:
        return "member_gone"
    return "discord_error"


@approvals_bp.get("/api/guilds/<int:guild_id>/approvals")
@login_required
def list_approvals(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    status = request.args.get("status", "pending")
    q = g.db.query(ModApproval).filter(ModApproval.guild_id == guild_id)
    if status == "pending":
        q = q.filter(ModApproval.status.in_(("pending", "reviewing")))
    elif status in ("done", "rejected"):
        q = q.filter(ModApproval.status == status)
    kind = request.args.get("kind")
    if kind in _KINDS + ("rank",):
        q = q.filter(ModApproval.kind == kind)
    rows = q.order_by(ModApproval.created_at.desc()).limit(100).all()
    row = protection.get_or_create(g.db, guild_id)
    wl = (protection._merged_extra(row).get("warn_ladder") or {})
    l2 = ((settings_mod.get_or_create(g.db, guild_id).extra or {}).get("leveling2") or {})
    g.db.commit()
    return jsonify(approvals=[a.to_dict() for a in rows],
                   settings={"require_approval": wl.get("require_approval") or [],
                             "rank_approval": bool(l2.get("role_reward_approval"))})


@approvals_bp.put("/api/guilds/<int:guild_id>/approvals/settings")
@login_required
def save_settings(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    if "require_approval" in body:
        req = [k for k in dict.fromkeys(body.get("require_approval") or []) if k in _KINDS]
        row = protection.get_or_create(g.db, guild_id)
        protection.update_extra_section(g.db, guild_id, "warn_ladder", {"require_approval": req})
        row.updated_at = datetime.utcnow()
    if "rank_approval" in body:
        srow = settings_mod.get_or_create(g.db, guild_id)
        extra = dict(srow.extra or {})
        l2 = dict(extra.get("leveling2") or {})
        l2["role_reward_approval"] = bool(body["rank_approval"])
        extra["leveling2"] = l2
        srow.extra = extra
        settings_mod.touch(srow)
    g.db.commit()
    return jsonify(ok=True)


def _execute(a: ModApproval, guild: Guild):
    token = team_direct.bot_token_for(g.db, guild)
    reason = "Guildizer: approved by staff - " + (a.reason or a.kind)
    if a.kind == "kick":
        discord_api.kick_member(guild.id, a.user_id, reason)
    elif a.kind == "ban":
        discord_api.ban_member(guild.id, a.user_id, reason)
    elif a.kind == "timeout":
        until = (datetime.utcnow() + timedelta(minutes=min(40320, max(1, a.minutes or 30)))).isoformat() + "Z"
        discord_api.timeout_member(guild.id, a.user_id, until, reason)
    elif a.kind == "rank":
        if role_policy.check_roles(g.db, guild.id, [a.role_id]):
            raise PermissionError("role_not_assignable")
        discord_api.set_member_role(guild.id, a.user_id, a.role_id, True, token, reason)


@approvals_bp.post("/api/guilds/<int:guild_id>/approvals/<int:approval_id>/review")
@login_required
def review(guild_id: int, approval_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    decision = (request.get_json(silent=True) or {}).get("decision")
    if decision not in ("approve", "reject"):
        return jsonify(error="bad_decision"), 400
    a = g.db.get(ModApproval, approval_id)
    if a is None or a.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    guild = g.db.get(Guild, guild_id)
    now = datetime.utcnow()
    claimed = (g.db.query(ModApproval)
               .filter(ModApproval.id == approval_id, ModApproval.status == "pending")
               .update({"status": "reviewing", "reviewed_at": now}, synchronize_session=False))
    if not claimed:                      # take over a claim abandoned by a crashed request
        claimed = (g.db.query(ModApproval)
                   .filter(ModApproval.id == approval_id, ModApproval.status == "reviewing",
                           ModApproval.reviewed_at < now - timedelta(minutes=2))
                   .update({"reviewed_at": now}, synchronize_session=False))
    g.db.commit()
    if not claimed:
        return jsonify(error="already_reviewed"), 409
    g.db.refresh(a)

    def release(code, http):
        g.db.rollback()
        a.status, a.result_error, a.reviewed_at = "pending", code, None
        g.db.commit()
        return jsonify(error=code), http

    try:
        if decision == "approve":
            if not guild.is_served:
                return release("bot_not_in_server", 409)
            try:
                _execute(a, guild)
            except PermissionError:
                return release("role_not_assignable", 400)
            except Exception as exc:  # noqa: BLE001
                return release(_code(exc), 502)
            a.status = "done"
        else:
            a.status = "rejected"
        a.result_error, a.reviewer_id, a.reviewed_at = None, g.user_id, datetime.utcnow()
        g.db.add(ProtectionEvent(guild_id=guild_id, category="approval", action=a.status,
                                 user_id=a.user_id, username=a.username,
                                 detail=("%s %s by %s" % (a.kind, a.status, g.user_id))[:255]))
        g.db.commit()
    except Exception:  # noqa: BLE001
        return release("discord_error", 500)
    return jsonify(approval=a.to_dict())
