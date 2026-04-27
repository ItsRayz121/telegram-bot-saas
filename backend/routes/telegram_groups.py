"""
API routes for the official Telegizer bot group ecosystem.

Endpoints:
  GET  /api/telegram-groups              — list user's linked groups
  POST /api/telegram-groups/link         — link a group using a code
  GET  /api/telegram-groups/<id>         — get single group
  PUT  /api/telegram-groups/<id>         — update group settings
  DELETE /api/telegram-groups/<id>       — unlink group
  POST /api/telegram-groups/link-code    — admin: generate code manually (fallback)
  GET  /api/telegram-groups/<id>/events  — event log for a group
  GET  /api/telegram-groups/<id>/commands — list custom commands (proxy)
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, TelegramGroup, TelegramGroupLinkCode, BotEvent
from ..middleware.rate_limit import rate_limit
from ..config import Config

tg_groups_bp = Blueprint("telegram_groups", __name__, url_prefix="/api/telegram-groups")


def _current_user():
    return User.query.get(int(get_jwt_identity()))


def _owns_group(user_id: int, group_id: str) -> "TelegramGroup | None":
    """Return group only if the user owns it."""
    return TelegramGroup.query.filter_by(
        telegram_group_id=group_id,
        owner_user_id=user_id,
        is_disabled=False,
    ).first()


# ── List user's linked groups ──────────────────────────────────────────────────

@tg_groups_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_groups():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    groups = TelegramGroup.query.filter_by(
        owner_user_id=user.id,
        is_disabled=False,
    ).order_by(TelegramGroup.linked_at.desc()).all()

    return jsonify({"groups": [g.to_dict() for g in groups]})


# ── Link a group via code ──────────────────────────────────────────────────────

@tg_groups_bp.route("/link", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def link_group():
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "Verification code is required"}), 400

    link_code = TelegramGroupLinkCode.query.filter_by(code=code).first()
    if not link_code:
        return jsonify({"error": "Invalid verification code"}), 400

    if not link_code.is_valid:
        return jsonify({"error": "Code has expired or already been used"}), 400

    # Check not already claimed by another user
    tg = TelegramGroup.query.filter_by(
        telegram_group_id=link_code.telegram_group_id
    ).first()

    if not tg:
        return jsonify({"error": "Group not found. Make sure the bot is in the group."}), 404

    if tg.owner_user_id and tg.owner_user_id != user.id:
        return jsonify({"error": "This group is already linked to another account"}), 409

    # Enforce per-tier official group limit
    max_groups = Config.MAX_OFFICIAL_GROUPS.get(user.subscription_tier, 3)
    if max_groups != -1:
        current_count = TelegramGroup.query.filter_by(
            owner_user_id=user.id, is_disabled=False
        ).count()
        if tg.owner_user_id != user.id and current_count >= max_groups:
            return jsonify({
                "error": (
                    f"Your {user.subscription_tier.capitalize()} plan allows {max_groups} "
                    f"linked group(s). Upgrade to Pro to link unlimited groups."
                ),
                "code": "GROUP_LIMIT_REACHED",
                "limit": max_groups,
            }), 403

    # Mark code used and link the group
    link_code.used_at = datetime.utcnow()
    tg.owner_user_id = user.id
    tg.bot_status = "active"
    tg.linked_at = datetime.utcnow()
    tg.linked_via_bot_type = "official"
    db.session.commit()

    # Log event
    ev = BotEvent(
        telegram_group_id=tg.telegram_group_id,
        event_type="group_linked",
        message=f"Group linked by user {user.id}",
        metadata_={"user_id": user.id, "user_email": user.email},
    )
    db.session.add(ev)
    db.session.commit()

    return jsonify({"group": tg.to_dict(), "message": "Group linked successfully"})


# ── Get single group ───────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_group(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    return jsonify({"group": tg.to_dict()})


# ── Update group settings (title, invite link, etc.) ──────────────────────────

@tg_groups_bp.route("/<group_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_group(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    if "title" in data and data["title"]:
        tg.title = data["title"][:255]
    if "invite_link" in data:
        tg.invite_link = data["invite_link"]

    db.session.commit()
    return jsonify({"group": tg.to_dict()})


# ── Unlink / remove group ──────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def unlink_group(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    tg.owner_user_id = None
    tg.bot_status = "pending"
    tg.linked_at = None
    db.session.commit()

    ev = BotEvent(
        telegram_group_id=tg.telegram_group_id,
        event_type="group_unlinked",
        message=f"Group unlinked by user {user.id}",
        metadata_={"user_id": user.id},
    )
    db.session.add(ev)
    db.session.commit()

    return jsonify({"message": "Group unlinked successfully"})


# ── Group event log ────────────────────────────────────────────────────────────

@tg_groups_bp.route("/<group_id>/events", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_group_events(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)

    paginated = BotEvent.query.filter_by(
        telegram_group_id=group_id
    ).order_by(BotEvent.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "events": [e.to_dict() for e in paginated.items],
        "total": paginated.total,
        "page": page,
        "pages": paginated.pages,
    })


# ── Pending groups (bot added but not linked) ──────────────────────────────────

@tg_groups_bp.route("/pending", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def get_pending_groups():
    """Groups where bot is present but not yet linked to any user."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Return unlinked groups — user must supply link code to claim
    pending = TelegramGroup.query.filter_by(
        owner_user_id=None,
        bot_status="pending",
    ).order_by(TelegramGroup.created_at.desc()).limit(50).all()

    return jsonify({"groups": [g.to_dict() for g in pending]})
