"""Per-group team access for Telegram groups (owner invites friends to ONE group).

  GET    /api/telegram-groups/<gid>/team                 members + open invites
  POST   /api/telegram-groups/<gid>/team/invites         {role}  one-use code
  GET    /api/telegram-groups/<gid>/team/admins          Telegram admins that can be invited directly
  POST   /api/telegram-groups/<gid>/team/invites/direct  {telegram_user_id, role}  DM Accept/Reject
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

from ..models import (
    db, User, TelegramGroupAccess, TelegramGroupInvite, TelegramBotAccess, TelegramBotInvite, BotEvent,
)
from ..middleware.rate_limit import rate_limit
from .. import group_invite_flow as dflow
from ..models import TelegramBotStarted
from ..group_access import (
    team_access_enabled, owned_group_record, resolve_group_record,
    owned_bot_scopes, norm_bot_key, OFFICIAL_KEY, _bot_keys_for_chat,
)

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


def _open_invites(gtid, direct=None):
    """Unused, unexpired, undeclined invites. direct=False -> access codes only, True -> DM invites only."""
    q = TelegramGroupInvite.query.filter(
        TelegramGroupInvite.telegram_group_id == gtid,
        TelegramGroupInvite.used_by.is_(None),
        TelegramGroupInvite.declined_at.is_(None),
        TelegramGroupInvite.expires_at > datetime.utcnow(),
    )
    if direct is True:
        q = q.filter(TelegramGroupInvite.invitee_telegram_id.isnot(None))
    elif direct is False:
        q = q.filter(TelegramGroupInvite.invitee_telegram_id.is_(None))
    return q


@group_team_bp.route("/telegram-groups/<gid>/team", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_team(gid):
    user = _me()
    group, err = _owner_group(user, gid)
    if err:
        return err
    members = TelegramGroupAccess.query.filter_by(telegram_group_id=group.telegram_group_id).all()
    keys = _bot_keys_for_chat(group.telegram_group_id, user.id)
    inherited = [m.to_dict() for m in TelegramBotAccess.query.filter_by(invited_by=user.id).all()
                 if m.bot_key in keys]
    return jsonify({"members": [m.to_dict() for m in members],
                    "inherited": inherited,
                    "invites": [i.to_dict() for i in _open_invites(group.telegram_group_id, direct=False).all()],
                    "direct_invites": [i.to_dict() for i in _open_invites(group.telegram_group_id, direct=True).all()],
                    "direct_enabled": dflow.direct_invites_enabled()
                    and dflow.official_group(group.telegram_group_id) is not None,
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


@group_team_bp.route("/telegram-groups/<gid>/team/admins", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def team_admins(gid):
    """Telegram admins of this group, marked with whether the bot can DM them yet."""
    user = _me()
    group, err = _owner_group(user, gid)
    if err:
        return err
    if not dflow.official_group(group.telegram_group_id):
        return jsonify({"admins": [], "supported": False,
                        "error": "Direct invites work for groups managed by the Telegizer bot."})
    admins, terr = dflow.chat_admins(group.telegram_group_id)
    if terr:
        return jsonify({"admins": [], "supported": True, "error": terr})
    gtid = group.telegram_group_id
    have = {r.user_id for r in TelegramGroupAccess.query.filter_by(telegram_group_id=gtid).all()}
    pending = {i.invitee_telegram_id for i in _open_invites(gtid, direct=True).all()}
    me_tg = {user.telegram_user_id} if user.telegram_user_id else set()
    out = []
    for a in admins:
        if a["user_id"] in me_tg:
            continue
        acct = User.query.filter_by(telegram_user_id=a["user_id"]).first()
        out.append({**a,
                    "can_dm": TelegramBotStarted.has_started(a["user_id"]),
                    "has_access": bool(acct and acct.id in have),
                    "pending": a["user_id"] in pending})
    return jsonify({"admins": out, "supported": True})


@group_team_bp.route("/telegram-groups/<gid>/team/invites/direct", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_direct_invite(gid):
    user = _me()
    group, err = _owner_group(user, gid)
    if err:
        return err
    if not dflow.direct_invites_enabled():
        return jsonify({"error": "Invitations are temporarily disabled. Use an access code instead."}), 503
    if not dflow.official_group(group.telegram_group_id):
        return jsonify({"error": "Direct invites work for groups managed by the Telegizer bot."}), 400
    body = request.get_json(silent=True) or {}
    role = body.get("role", "manager")
    if role not in ROLES:
        return jsonify({"error": "role must be manager or viewer"}), 400
    tg_id = str(body.get("telegram_user_id") or "").strip()
    admins, terr = dflow.chat_admins(group.telegram_group_id)
    if terr:
        return jsonify({"error": f"Could not read the group's admins: {terr}"}), 502
    target = next((a for a in admins if a["user_id"] == tg_id), None)
    if not target:
        return jsonify({"error": "That person is not an admin of this group"}), 400
    if user.telegram_user_id and tg_id == str(user.telegram_user_id):
        return jsonify({"error": "You own this group"}), 400
    if not TelegramBotStarted.has_started(tg_id):
        return jsonify({"error": "They need to start the bot first (open the bot and press Start)."}), 409
    gtid = group.telegram_group_id
    if _open_invites(gtid, direct=True).filter_by(invitee_telegram_id=tg_id).first():
        return jsonify({"error": "An invitation to this person is already pending"}), 409
    taken = TelegramGroupAccess.query.filter_by(telegram_group_id=gtid).count()
    if taken + _open_invites(gtid).count() >= MAX_PER_GROUP:
        return jsonify({"error": f"Limit of {MAX_PER_GROUP} team members per group reached"}), 403
    inv = TelegramGroupInvite(telegram_group_id=gtid, role=role, created_by=user.id,
                              invitee_telegram_id=tg_id, invitee_name=target["name"])
    db.session.add(inv)
    db.session.flush()
    ok, derr = dflow.send_invite_dm(inv, group.title, user.full_name or "The group owner")
    if not ok:
        db.session.rollback()
        return jsonify({"error": f"Could not message them: {derr}"}), 502
    _log(group, "group_team_invited", f"Invited Telegram user {tg_id} as {role}",
         by=user.id, telegram_user_id=tg_id, role=role)
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
    if inv.invitee_telegram_id or inv.declined_at:  # DM invites are accepted in the bot, never by code
        return None, None
    group = resolve_group_record(inv.telegram_group_id)
    # The code only works while the person who made it still owns the group.
    if not group or group.owner_user_id != inv.created_by:
        return None, None
    return inv, group


def _valid_bot_invite(code):
    code = _clean_code(code)
    if not code:
        return None, None
    inv = TelegramBotInvite.query.filter_by(code=code).first()
    if not inv or inv.used_by is not None or inv.expires_at <= datetime.utcnow():
        return None, None
    scope = owned_bot_scopes(inv.created_by).get(inv.bot_key)  # issuer must still own the bot
    if scope is None:
        return None, None
    return inv, scope


@group_team_bp.route("/group-team/invite/<code>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def preview_invite(code):
    if not team_access_enabled():
        return jsonify({"error": "Team access is temporarily disabled"}), 503
    inv, group = _valid_invite(code)
    if inv:
        return jsonify({"invite": {"scope": "group", "group_title": group.title, "role": inv.role}})
    binv, scope = _valid_bot_invite(code)
    if binv:
        n = len(scope["chats"])
        return jsonify({"invite": {"scope": "bot", "group_title": f"All groups of {scope['label']}",
                                   "group_count": n, "role": binv.role}})
    return jsonify({"error": "Invalid or expired access code"}), 404


def _claim_group_invite(inv, user_id):
    """Atomically mark a code used; False if someone else got there first."""
    n = TelegramGroupInvite.query.filter_by(id=inv.id, used_by=None).update(
        {"used_by": user_id, "used_at": datetime.utcnow()}, synchronize_session=False)
    return n == 1


def _claim_bot_invite(inv, user_id):
    n = TelegramBotInvite.query.filter_by(id=inv.id, used_by=None).update(
        {"used_by": user_id, "used_at": datetime.utcnow()}, synchronize_session=False)
    return n == 1


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
        binv, scope = _valid_bot_invite(code)
        if not binv:
            return jsonify({"error": "Invalid or expired access code"}), 404
        if binv.created_by == user.id:
            return jsonify({"error": "You own this bot"}), 400
        if not _claim_bot_invite(binv, user.id):
            db.session.rollback()
            return jsonify({"error": "Invalid or expired access code"}), 404
        existing = TelegramBotAccess.query.filter_by(
            bot_key=binv.bot_key, user_id=user.id, invited_by=binv.created_by).first()
        if existing:
            existing.role = binv.role
        else:
            db.session.add(TelegramBotAccess(
                bot_key=binv.bot_key, user_id=user.id, role=binv.role, invited_by=binv.created_by))
            db.session.add(BotEvent(telegram_group_id="bot:" + binv.bot_key, event_type="bot_team_joined",
                                    message=f"User {user.id} joined {binv.bot_key} as {binv.role}",
                                    metadata_={"user_id": user.id, "role": binv.role,
                                               "invited_by": binv.created_by}))
        db.session.commit()
        return jsonify({"ok": True, "scope": "bot", "group_count": len(scope["chats"]),
                        "group": {"telegram_group_id": None, "title": f"All groups of {scope['label']}"},
                        "role": binv.role})
    if group.owner_user_id == user.id:
        return jsonify({"error": "You already own this group"}), 400
    if not _claim_group_invite(inv, user.id):
        db.session.rollback()
        return jsonify({"error": "Invalid or expired access code"}), 404
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
    db.session.commit()
    return jsonify({"ok": True, "scope": "group",
                    "group": {"telegram_group_id": group.telegram_group_id, "title": group.title},
                    "role": inv.role})


# ── Whole-bot sharing (every group one bot manages, now and later) ────────────

def _owned_scope(user, key):
    if not team_access_enabled():
        return None, (jsonify({"error": "Team access is temporarily disabled"}), 503)
    key = norm_bot_key(key) if key != OFFICIAL_KEY else key
    scope = owned_bot_scopes(user.id).get(key)
    if scope is None:
        return None, (jsonify({"error": "Bot not found"}), 404)
    return (key, scope), None


@group_team_bp.route("/group-team/bots", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def list_bot_scopes():
    user = _me()
    if not team_access_enabled():
        return jsonify({"error": "Team access is temporarily disabled"}), 503
    out = []
    for key, sc in owned_bot_scopes(user.id).items():
        if key == OFFICIAL_KEY and not sc["chats"]:
            continue  # nothing to share yet
        shared = TelegramBotAccess.query.filter_by(bot_key=key, invited_by=user.id).count()
        out.append({"key": key, "label": sc["label"], "kind": sc["kind"],
                    "group_count": len(sc["chats"]), "people": shared})
    out.sort(key=lambda x: (x["kind"] != "official", x["label"]))
    return jsonify({"bots": out})


def _bot_open_invites(key, owner_id):
    return TelegramBotInvite.query.filter(
        TelegramBotInvite.bot_key == key, TelegramBotInvite.created_by == owner_id,
        TelegramBotInvite.used_by.is_(None), TelegramBotInvite.expires_at > datetime.utcnow())


@group_team_bp.route("/group-team/bots/<key>/team", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_bot_team(key):
    user = _me()
    res, err = _owned_scope(user, key)
    if err:
        return err
    key, scope = res
    members = TelegramBotAccess.query.filter_by(bot_key=key, invited_by=user.id).all()
    return jsonify({"members": [m.to_dict() for m in members],
                    "invites": [i.to_dict() for i in _bot_open_invites(key, user.id).all()],
                    "max_members": MAX_PER_GROUP, "group_count": len(scope["chats"]),
                    "label": scope["label"]})


@group_team_bp.route("/group-team/bots/<key>/team/invites", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_bot_invite(key):
    user = _me()
    res, err = _owned_scope(user, key)
    if err:
        return err
    key, _scope = res
    role = (request.get_json(silent=True) or {}).get("role", "manager")
    if role not in ROLES:
        return jsonify({"error": "role must be manager or viewer"}), 400
    taken = TelegramBotAccess.query.filter_by(bot_key=key, invited_by=user.id).count()
    if taken + _bot_open_invites(key, user.id).count() >= MAX_PER_GROUP:
        return jsonify({"error": f"Limit of {MAX_PER_GROUP} team members per bot reached"}), 403
    inv = TelegramBotInvite(bot_key=key, role=role, created_by=user.id)
    db.session.add(inv)
    db.session.commit()
    return jsonify({"invite": inv.to_dict()}), 201


@group_team_bp.route("/group-team/bots/<key>/team/invites/<int:invite_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def cancel_bot_invite(key, invite_id):
    user = _me()
    res, err = _owned_scope(user, key)
    if err:
        return err
    inv = TelegramBotInvite.query.filter_by(id=invite_id, bot_key=res[0], created_by=user.id).first()
    if not inv:
        return jsonify({"error": "Invite not found"}), 404
    db.session.delete(inv)
    db.session.commit()
    return jsonify({"ok": True})


@group_team_bp.route("/group-team/bots/<key>/team/members/<int:member_user_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_bot_member(key, member_user_id):
    user = _me()
    res, err = _owned_scope(user, key)
    if err:
        return err
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in ROLES:
        return jsonify({"error": "role must be manager or viewer"}), 400
    row = TelegramBotAccess.query.filter_by(bot_key=res[0], user_id=member_user_id, invited_by=user.id).first()
    if not row:
        return jsonify({"error": "Member not found"}), 404
    row.role = role
    db.session.commit()
    return jsonify({"member": row.to_dict()})


@group_team_bp.route("/group-team/bots/<key>/team/members/<int:member_user_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def remove_bot_member(key, member_user_id):
    user = _me()
    res, err = _owned_scope(user, key)
    if err:
        return err
    row = TelegramBotAccess.query.filter_by(bot_key=res[0], user_id=member_user_id, invited_by=user.id).first()
    if not row:
        return jsonify({"error": "Member not found"}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


@group_team_bp.route("/group-team/bots/<key>/team/leave", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def leave_bot_team(key):
    user = _me()
    k = key if key == OFFICIAL_KEY else norm_bot_key(key)
    n = TelegramBotAccess.query.filter_by(bot_key=k, user_id=user.id).delete(synchronize_session=False)
    db.session.commit()
    if not n:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"ok": True})


@group_team_bp.route("/group-team/mine", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def my_shared_access():
    """Whole-bot shares this user holds (so they can see and leave them)."""
    user = _me()
    out = []
    for r in TelegramBotAccess.query.filter_by(user_id=user.id).all():
        owner = User.query.get(r.invited_by)
        scope = owned_bot_scopes(r.invited_by).get(r.bot_key)
        out.append({"bot_key": r.bot_key, "role": r.role,
                    "label": scope["label"] if scope else r.bot_key,
                    "group_count": len(scope["chats"]) if scope else 0,
                    "owner_name": (owner.full_name or owner.email) if owner else None})
    return jsonify({"bots": out})
