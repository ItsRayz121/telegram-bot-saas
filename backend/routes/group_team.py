"""Per-group team access for Telegram groups (owner invites friends to ONE group).

  GET    /api/telegram-groups/<gid>/team                 members + open invites
  POST   /api/telegram-groups/<gid>/team/invites         {role}  one-use code
  DELETE /api/telegram-groups/<gid>/team/invites/<id>
  PUT    /api/telegram-groups/<gid>/team/members/<uid>   {role}
  DELETE /api/telegram-groups/<gid>/team/members/<uid>
  DELETE /api/telegram-groups/<gid>/team/leave           member leaves
  GET    /api/group-team/invite/<code>                   preview a pasted access code
  POST   /api/group-team/redeem                          {code}

Only the group owner manages the team.
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, TelegramGroupAccess, TelegramGroupInvite, BotEvent
from ..middleware.rate_limit import rate_limit
from ..group_access import team_access_enabled, owned_group_record, resolve_group_record

logger = logging.getLogger(__name__)
group_team_bp = Blueprint("group_team", __name__, url_prefix="/api")

MAX_PER_GROUP = 10
ROLES = ("manager", "viewer")


def _me():
    return User.query.get(int(get_jwt_identity()))


def _owner_group(user, gid):
    """Group the user OWNS (not merely manages), or (None, error response)."""
    if not team_access_enabled():
        return None, (jsonify({"error": "Team access is temporarily disabled"}), 503)
    group = owned_group_record(user.id, gid)  # works for official AND custom-bot groups
    if not group:
        return None, (jsonify({"error": "Group not found"}), 404)
    return group, None


def _log(group, event, msg, **meta):
    db.session.add(BotEvent(telegram_group_id=group.telegram_group_id, event_type=event,
                            message=msg, metadata_=meta))


def _open_invites(gtid):
    return TelegramGroupInvite.query.filter(
        TelegramGroupInvite.telegram_group_id == gtid,
        TelegramGroupInvite.used_by.is_(None),
        TelegramGroupInvite.expires_at > datetime.utcnow(),
    )


@group_team_bp.route("/telegram-groups/<gid>/team", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_team(gid):
    user = _me()
    group, err = _owner_group(user, gid)
    if err:
        return err
    members = TelegramGroupAccess.query.filter_by(telegram_group_id=group.telegram_group_id).all()
    return jsonify({"members": [m.to_dict() for m in members],
                    "invites": [i.to_dict() for i in _open_invites(group.telegram_group_id).all()],
                    "max_members": MAX_PER_GROUP})


@group_team_bp.route("/telegram-groups/<gid>/team/invites", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_invite(gid):
    user = _me()
    group, err = _owner_group(user, gid)
    if err:
        return err
    role = (request.get_json(silent=True) or {}).get("role", "manager")
    if role not in ROLES:
        return jsonify({"error": "role must be manager or viewer"}), 400
    gtid = group.telegram_group_id
    taken = TelegramGroupAccess.query.filter_by(telegram_group_id=gtid).count()
    if taken + _open_invites(gtid).count() >= MAX_PER_GROUP:
        return jsonify({"error": f"Limit of {MAX_PER_GROUP} team members per group reached"}), 403
    inv = TelegramGroupInvite(telegram_group_id=gtid, role=role, created_by=user.id)
    db.session.add(inv)
    db.session.commit()
    return jsonify({"invite": inv.to_dict()}), 201


@group_team_bp.route("/telegram-groups/<gid>/team/invites/<int:invite_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def cancel_invite(gid, invite_id):
    user = _me()
    group, err = _owner_group(user, gid)
    if err:
        return err
    inv = TelegramGroupInvite.query.filter_by(id=invite_id, telegram_group_id=group.telegram_group_id).first()
    if not inv:
        return jsonify({"error": "Invite not found"}), 404
    db.session.delete(inv)
    db.session.commit()
    return jsonify({"ok": True})


@group_team_bp.route("/telegram-groups/<gid>/team/members/<int:member_user_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_member(gid, member_user_id):
    user = _me()
    group, err = _owner_group(user, gid)
    if err:
        return err
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in ROLES:
        return jsonify({"error": "role must be manager or viewer"}), 400
    row = TelegramGroupAccess.query.filter_by(
        telegram_group_id=group.telegram_group_id, user_id=member_user_id).first()
    if not row:
        return jsonify({"error": "Member not found"}), 404
    row.role = role
    _log(group, "group_team_role_changed", f"User {member_user_id} set to {role}",
         by=user.id, user_id=member_user_id, role=role)
    db.session.commit()
    return jsonify({"member": row.to_dict()})


@group_team_bp.route("/telegram-groups/<gid>/team/members/<int:member_user_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def remove_member(gid, member_user_id):
    user = _me()
    group, err = _owner_group(user, gid)
    if err:
        return err
    row = TelegramGroupAccess.query.filter_by(
        telegram_group_id=group.telegram_group_id, user_id=member_user_id).first()
    if not row:
        return jsonify({"error": "Member not found"}), 404
    db.session.delete(row)
    _log(group, "group_team_removed", f"User {member_user_id} removed", by=user.id, user_id=member_user_id)
    db.session.commit()
    return jsonify({"ok": True})


@group_team_bp.route("/telegram-groups/<gid>/team/leave", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def leave_group(gid):
    user = _me()
    row = TelegramGroupAccess.query.filter_by(telegram_group_id=str(gid), user_id=user.id).first()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


def _clean_code(raw):
    return "".join(ch for ch in (raw or "") if ch.isalnum())


def _valid_invite(code):
    code = _clean_code(code)
    if not code:
        return None, None
    inv = TelegramGroupInvite.query.filter_by(code=code).first()
    if not inv or inv.used_by is not None or inv.expires_at <= datetime.utcnow():
        return None, None
    group = resolve_group_record(inv.telegram_group_id)
    # The code only works while the person who made it still owns the group.
    if not group or group.owner_user_id != inv.created_by:
        return None, None
    return inv, group


@group_team_bp.route("/group-team/invite/<code>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def preview_invite(code):
    if not team_access_enabled():
        return jsonify({"error": "Team access is temporarily disabled"}), 503
    inv, group = _valid_invite(code)
    if not inv:
        return jsonify({"error": "Invalid or expired access code"}), 404
    return jsonify({"invite": {"group_title": group.title, "role": inv.role}})


@group_team_bp.route("/group-team/redeem", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def redeem():
    user = _me()
    if not team_access_enabled():
        return jsonify({"error": "Team access is temporarily disabled"}), 503
    code = (request.get_json(silent=True) or {}).get("code")
    inv, group = _valid_invite(code)
    if not inv:
        return jsonify({"error": "Invalid or expired access code"}), 404
    if group.owner_user_id == user.id:
        return jsonify({"error": "You already own this group"}), 400
    existing = TelegramGroupAccess.query.filter_by(
        telegram_group_id=group.telegram_group_id, user_id=user.id).first()
    if existing:
        existing.role = inv.role
        existing.invited_by = inv.created_by
    else:
        db.session.add(TelegramGroupAccess(
            telegram_group_id=group.telegram_group_id, user_id=user.id,
            role=inv.role, invited_by=inv.created_by))
        _log(group, "group_team_joined", f"User {user.id} joined as {inv.role}",
             user_id=user.id, role=inv.role, invited_by=inv.created_by)
    inv.used_by = user.id
    inv.used_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "group": {"telegram_group_id": group.telegram_group_id,
                                          "title": group.title}, "role": inv.role})
