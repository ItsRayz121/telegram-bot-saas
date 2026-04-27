"""
CRUD routes for custom slash commands on user-supplied (custom) bot groups.
URL prefix: /api/bots/<bot_id>/groups/<group_id>/commands
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, Bot, Group, BotGroupCommand

bot_group_commands_bp = Blueprint(
    "bot_group_commands", __name__,
    url_prefix="/api/bots",
)


def _current_user():
    return User.query.get(int(get_jwt_identity()))


def _get_group(user, bot_id: int, group_id: int):
    """Return (bot, group) if user owns the bot and group belongs to it, else (None, None)."""
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return None, None
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    if not group:
        return None, None
    return bot, group


# ── List + create ─────────────────────────────────────────────────────────────

@bot_group_commands_bp.route(
    "/<int:bot_id>/groups/<int:group_id>/commands",
    methods=["GET"],
)
@jwt_required()
def list_commands(bot_id, group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    cmds = BotGroupCommand.query.filter_by(group_id=group.id).order_by(BotGroupCommand.command).all()
    return jsonify({"commands": [c.to_dict() for c in cmds]}), 200


@bot_group_commands_bp.route(
    "/<int:bot_id>/groups/<int:group_id>/commands",
    methods=["POST"],
)
@jwt_required()
def create_command(bot_id, group_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    command = (data.get("command") or "").strip().lstrip("/").lower()
    response_text = (data.get("response_text") or "").strip()

    if not command:
        return jsonify({"error": "command is required"}), 400
    if not response_text:
        return jsonify({"error": "response_text is required"}), 400
    if len(command) > 64:
        return jsonify({"error": "command too long (max 64 chars)"}), 400

    if BotGroupCommand.query.filter_by(group_id=group.id, command=command).first():
        return jsonify({"error": f"Command /{command} already exists in this group"}), 409

    cmd = BotGroupCommand(
        group_id=group.id,
        command=command,
        response_type=data.get("response_type", "text"),
        response_text=response_text,
        buttons=data.get("buttons"),
        enabled=data.get("enabled", True),
    )
    db.session.add(cmd)
    db.session.commit()
    return jsonify({"command": cmd.to_dict()}), 201


# ── Update + delete ───────────────────────────────────────────────────────────

@bot_group_commands_bp.route(
    "/<int:bot_id>/groups/<int:group_id>/commands/<int:cmd_id>",
    methods=["PUT", "PATCH"],
)
@jwt_required()
def update_command(bot_id, group_id, cmd_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    cmd = BotGroupCommand.query.filter_by(id=cmd_id, group_id=group.id).first()
    if not cmd:
        return jsonify({"error": "Command not found"}), 404

    data = request.get_json() or {}
    if "response_text" in data:
        cmd.response_text = data["response_text"].strip()
    if "response_type" in data:
        cmd.response_type = data["response_type"]
    if "buttons" in data:
        cmd.buttons = data["buttons"]
    if "enabled" in data:
        cmd.enabled = bool(data["enabled"])

    db.session.commit()
    return jsonify({"command": cmd.to_dict()}), 200


@bot_group_commands_bp.route(
    "/<int:bot_id>/groups/<int:group_id>/commands/<int:cmd_id>",
    methods=["DELETE"],
)
@jwt_required()
def delete_command(bot_id, group_id, cmd_id):
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    cmd = BotGroupCommand.query.filter_by(id=cmd_id, group_id=group.id).first()
    if not cmd:
        return jsonify({"error": "Command not found"}), 404

    db.session.delete(cmd)
    db.session.commit()
    return jsonify({"message": "Command deleted"}), 200
