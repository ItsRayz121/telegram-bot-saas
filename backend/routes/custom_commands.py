"""
API routes for per-group custom slash commands.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, TelegramGroup, CustomCommand
from ..middleware.rate_limit import rate_limit

custom_commands_bp = Blueprint("custom_commands", __name__, url_prefix="/api/telegram-groups")

_SUGGESTED_TEMPLATES = [
    {"command": "rules", "response_text": "📋 *Group Rules*\n\n1. Be respectful\n2. No spam\n3. Stay on topic"},
    {"command": "support", "response_text": "💬 *Need support?*\nContact us at support@example.com"},
    {"command": "website", "response_text": "🌐 Visit our website: https://example.com"},
    {"command": "buy", "response_text": "💳 *Purchase here:* https://example.com/buy"},
    {"command": "officiallinks", "response_text": "🔗 *Official Links*\nWebsite: https://example.com"},
    {"command": "verify", "response_text": "✅ To verify, click the button below."},
    {"command": "help", "response_text": "❓ *Need help?* Use /rules or /support for assistance."},
    {"command": "announcement", "response_text": "📢 *Latest Announcement*\nCheck pinned message above."},
]


def _current_user():
    return User.query.get(int(get_jwt_identity()))


def _owns_group(user_id: int, group_id: str):
    return TelegramGroup.query.filter_by(
        telegram_group_id=group_id,
        owner_user_id=user_id,
        is_disabled=False,
    ).first()


# ── List commands for a group ──────────────────────────────────────────────────

@custom_commands_bp.route("/<group_id>/commands", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_commands(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    commands = CustomCommand.query.filter_by(
        telegram_group_id=group_id
    ).order_by(CustomCommand.command).all()

    return jsonify({
        "commands": [c.to_dict() for c in commands],
        "suggested_templates": _SUGGESTED_TEMPLATES,
    })


# ── Create a command ───────────────────────────────────────────────────────────

@custom_commands_bp.route("/<group_id>/commands", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_command(group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    command = (data.get("command") or "").strip().lstrip("/").lower()
    response_text = (data.get("response_text") or "").strip()

    if not command:
        return jsonify({"error": "command is required"}), 400
    if not response_text:
        return jsonify({"error": "response_text is required"}), 400
    if len(command) > 32 or not command.isalnum():
        return jsonify({"error": "command must be alphanumeric and max 32 chars"}), 400

    # Check for duplicates
    existing = CustomCommand.query.filter_by(
        telegram_group_id=group_id, command=command
    ).first()
    if existing:
        return jsonify({"error": f"Command /{command} already exists in this group"}), 409

    cmd = CustomCommand(
        telegram_group_id=group_id,
        command=command,
        response_type=data.get("response_type", "text"),
        response_text=response_text,
        action_type=data.get("action_type"),
        buttons=data.get("buttons"),
        enabled=data.get("enabled", True),
    )
    db.session.add(cmd)
    db.session.commit()

    return jsonify({"command": cmd.to_dict()}), 201


# ── Update a command ───────────────────────────────────────────────────────────

@custom_commands_bp.route("/<group_id>/commands/<int:cmd_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_command(group_id, cmd_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    cmd = CustomCommand.query.filter_by(
        id=cmd_id, telegram_group_id=group_id
    ).first()
    if not cmd:
        return jsonify({"error": "Command not found"}), 404

    data = request.get_json() or {}
    if "response_text" in data:
        cmd.response_text = data["response_text"]
    if "response_type" in data:
        cmd.response_type = data["response_type"]
    if "buttons" in data:
        cmd.buttons = data["buttons"]
    if "action_type" in data:
        cmd.action_type = data["action_type"]
    if "enabled" in data:
        cmd.enabled = bool(data["enabled"])

    db.session.commit()
    return jsonify({"command": cmd.to_dict()})


# ── Delete a command ───────────────────────────────────────────────────────────

@custom_commands_bp.route("/<group_id>/commands/<int:cmd_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def delete_command(group_id, cmd_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    tg = _owns_group(user.id, group_id)
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    cmd = CustomCommand.query.filter_by(
        id=cmd_id, telegram_group_id=group_id
    ).first()
    if not cmd:
        return jsonify({"error": "Command not found"}), 404

    db.session.delete(cmd)
    db.session.commit()
    return jsonify({"message": "Command deleted"})
