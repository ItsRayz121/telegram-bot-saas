import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Team, TeamMember, TeamInvite
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

team_bp = Blueprint("team", __name__, url_prefix="/api/team")

FRONTEND_URL = "https://telegizer.com"  # overridden per-env via config if needed


def _me():
    return User.query.get(int(get_jwt_identity()))


def _my_team(user):
    """Return the team the user belongs to (as owner or member), or None."""
    membership = TeamMember.query.filter_by(user_id=user.id).first()
    if membership:
        return Team.query.get(membership.team_id)
    return None


def _my_role(user, team):
    m = TeamMember.query.filter_by(team_id=team.id, user_id=user.id).first()
    return m.role if m else None


# ── GET /api/team ─────────────────────────────────────────────────────────────

@team_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_team():
    user = _me()
    if not user:
        return jsonify({"error": "Not found"}), 404
    team = _my_team(user)
    if not team:
        return jsonify({"team": None}), 200
    return jsonify({"team": team.to_dict(include_members=True, include_invites=True)}), 200


# ── POST /api/team — create team ─────────────────────────────────────────────

@team_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_team():
    user = _me()
    if not user:
        return jsonify({"error": "Not found"}), 404

    existing = _my_team(user)
    if existing:
        return jsonify({"error": "You already belong to a team"}), 400

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Team name is required"}), 400
    if len(name) > 100:
        return jsonify({"error": "Team name too long (max 100 chars)"}), 400

    team = Team(name=name, owner_id=user.id)
    db.session.add(team)
    db.session.flush()

    owner_membership = TeamMember(team_id=team.id, user_id=user.id, role="owner")
    db.session.add(owner_membership)
    db.session.commit()

    return jsonify({"team": team.to_dict(include_members=True, include_invites=True)}), 201


# ── POST /api/team/invite ─────────────────────────────────────────────────────

@team_bp.route("/invite", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def invite_member():
    user = _me()
    if not user:
        return jsonify({"error": "Not found"}), 404

    team = _my_team(user)
    if not team:
        return jsonify({"error": "You don't have a team yet"}), 400

    role = _my_role(user, team)
    if role not in ("owner", "admin"):
        return jsonify({"error": "Only owners and admins can invite members"}), 403

    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    invite_role = data.get("role", "member")
    if invite_role not in ("admin", "member"):
        invite_role = "member"

    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Check if already a member
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        existing_membership = TeamMember.query.filter_by(team_id=team.id, user_id=existing_user.id).first()
        if existing_membership:
            return jsonify({"error": "This user is already a team member"}), 400

    # Check for existing pending invite
    pending = TeamInvite.query.filter_by(
        team_id=team.id, invited_email=email, accepted_at=None
    ).filter(TeamInvite.expires_at > datetime.utcnow()).first()
    if pending:
        invite_url = f"{FRONTEND_URL}/team/join/{pending.token}"
        return jsonify({"invite_url": invite_url, "reused": True}), 200

    invite = TeamInvite(
        team_id=team.id,
        invited_by_id=user.id,
        invited_email=email,
        role=invite_role,
    )
    db.session.add(invite)
    db.session.commit()

    invite_url = f"{FRONTEND_URL}/team/join/{invite.token}"
    return jsonify({"invite_url": invite_url, "invite_id": invite.id}), 201


# ── GET /api/team/invite/:token — public, no auth ────────────────────────────

@team_bp.route("/invite/<string:token>", methods=["GET"])
@rate_limit(requests_per_minute=30)
def get_invite(token):
    invite = TeamInvite.query.filter_by(token=token).first()
    if not invite:
        return jsonify({"error": "Invite not found"}), 404
    if invite.accepted_at:
        return jsonify({"error": "Invite already accepted"}), 410
    if invite.expires_at < datetime.utcnow():
        return jsonify({"error": "Invite has expired"}), 410

    team = Team.query.get(invite.team_id)
    return jsonify({
        "invite": {
            "id": invite.id,
            "team_name": team.name if team else "Unknown",
            "invited_email": invite.invited_email,
            "role": invite.role,
            "expires_at": invite.expires_at.isoformat(),
        }
    }), 200


# ── POST /api/team/invite/:token/accept ──────────────────────────────────────

@team_bp.route("/invite/<string:token>/accept", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def accept_invite(token):
    user = _me()
    if not user:
        return jsonify({"error": "Not found"}), 404

    invite = TeamInvite.query.filter_by(token=token).first()
    if not invite:
        return jsonify({"error": "Invite not found"}), 404
    if invite.accepted_at:
        return jsonify({"error": "Invite already accepted"}), 410
    if invite.expires_at < datetime.utcnow():
        return jsonify({"error": "Invite has expired"}), 410

    # Check user isn't already in a team
    existing = _my_team(user)
    if existing:
        return jsonify({"error": "You already belong to a team"}), 400

    membership = TeamMember(team_id=invite.team_id, user_id=user.id, role=invite.role)
    invite.accepted_at = datetime.utcnow()
    db.session.add(membership)
    db.session.commit()

    team = Team.query.get(invite.team_id)
    return jsonify({"team": team.to_dict(include_members=True)}), 200


# ── DELETE /api/team/members/:userId ─────────────────────────────────────────

@team_bp.route("/members/<int:target_user_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def remove_member(target_user_id):
    user = _me()
    if not user:
        return jsonify({"error": "Not found"}), 404

    team = _my_team(user)
    if not team:
        return jsonify({"error": "No team found"}), 404

    my_role = _my_role(user, team)
    if my_role not in ("owner", "admin"):
        return jsonify({"error": "Only owners and admins can remove members"}), 403

    target = TeamMember.query.filter_by(team_id=team.id, user_id=target_user_id).first()
    if not target:
        return jsonify({"error": "Member not found"}), 404
    if target.role == "owner":
        return jsonify({"error": "Cannot remove the team owner"}), 403

    db.session.delete(target)
    db.session.commit()
    return jsonify({"ok": True}), 200


# ── DELETE /api/team/invites/:inviteId ────────────────────────────────────────

@team_bp.route("/invites/<int:invite_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def cancel_invite(invite_id):
    user = _me()
    if not user:
        return jsonify({"error": "Not found"}), 404

    team = _my_team(user)
    if not team:
        return jsonify({"error": "No team found"}), 404

    my_role = _my_role(user, team)
    if my_role not in ("owner", "admin"):
        return jsonify({"error": "Only owners and admins can cancel invites"}), 403

    invite = TeamInvite.query.filter_by(id=invite_id, team_id=team.id).first()
    if not invite:
        return jsonify({"error": "Invite not found"}), 404

    db.session.delete(invite)
    db.session.commit()
    return jsonify({"ok": True}), 200
