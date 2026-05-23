import requests as http_requests
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, Bot, Group, AdminAuditLog
from ..middleware.rate_limit import rate_limit

bots_bp = Blueprint("bots", __name__, url_prefix="/api/bots")


def _get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


def _enrich_bot(bot) -> dict:
    """Add internal runtime fields and compute public health_status.

    Public health is derived solely from user intent (is_active) and
    last-seen activity. Infrastructure states (thread alive, watchdog
    recovery, Railway rolling deploy) are kept internal and never
    surface as a user-facing badge.

    Token is never included in normal responses. Use POST /reveal-token
    with password re-authentication to access the raw token.
    """
    from ..bot_manager import bot_manager
    from datetime import datetime, timedelta

    d = bot.to_dict()

    # Show a masked token (last 4 chars only) so the UI can display a hint
    # without exposing the full credential.
    raw_token = bot.get_token() or ""
    d["token_masked"] = ("•" * max(0, len(raw_token) - 4) + raw_token[-4:]) if raw_token else ""

    # thread_alive is an internal diagnostic field — kept in payload for
    # admin tooling and the /status endpoint but NOT used for health_status.
    d["thread_alive"] = bot_manager.is_running(bot.id)

    # ── Public health_status ───────────────────────────────────────────
    # Layer 1 (infrastructure) is invisible to users.
    # Layer 2 (public health) is driven only by is_active + last_active.
    if not bot.is_active:
        d["health_status"] = "offline"
    elif bot.last_active is None:
        # Freshly added bot — thread is starting up. Show Active, not a warning.
        d["health_status"] = "active"
    else:
        age = datetime.utcnow() - bot.last_active
        if age <= timedelta(days=7):
            d["health_status"] = "active"
        elif age <= timedelta(days=30):
            d["health_status"] = "idle"
        else:
            d["health_status"] = "unreachable"

    return d


@bots_bp.route("", methods=["GET"])
@jwt_required()
def get_bots():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bots = Bot.query.filter_by(user_id=user.id).all()
    return jsonify({"bots": [_enrich_bot(b) for b in bots]}), 200


@bots_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def create_bot():
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    max_bots = current_app.config["MAX_BOTS"].get(user.subscription_tier, 1)
    current_count = Bot.query.filter_by(user_id=user.id).count()
    if current_count >= max_bots:
        return jsonify({
            "error": f"Bot limit reached ({max_bots} bots for {user.subscription_tier} tier). Upgrade to add more.",
        }), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    token = data.get("bot_token", "").strip()
    if not token:
        return jsonify({"error": "bot_token is required"}), 400

    from ..utils.encryption import hash_token
    token_hash = hash_token(token)
    if Bot.query.filter_by(bot_token_hash=token_hash).first():
        return jsonify({"error": "This bot token is already registered"}), 409

    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
        def _get_me():
            return http_requests.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=8,
            )
        with ThreadPoolExecutor(max_workers=1) as _ex:
            try:
                resp = _ex.submit(_get_me).result(timeout=10)
            except _FutureTimeout:
                return jsonify({"error": "Telegram API timeout. Check your token."}), 400
        resp.raise_for_status()
        bot_info = resp.json()
        if not bot_info.get("ok"):
            return jsonify({"error": "Invalid bot token"}), 400

        result = bot_info["result"]
        bot_username = result.get("username", "")
        bot_name = result.get("first_name", "")
    except http_requests.exceptions.Timeout:
        return jsonify({"error": "Telegram API timeout. Check your token."}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to validate bot token: {str(e)}"}), 400

    from datetime import datetime as _dt
    bot = Bot(
        user_id=user.id,
        bot_username=bot_username,
        bot_name=bot_name,
        is_active=True,
        last_active=_dt.utcnow(),
    )
    bot.set_token(token)
    db.session.add(bot)
    db.session.commit()

    try:
        from ..bot_manager import bot_manager
        bot_manager.start_bot(bot.id, token, current_app._get_current_object())
    except Exception as e:
        current_app.logger.error(f"Failed to start bot {bot.id}: {e}")

    try:
        from ..notifications import send_bot_added_notification
        send_bot_added_notification(user.email, user.full_name, bot_name, bot_username)
    except Exception:
        pass

    return jsonify({"bot": bot.to_dict(), "message": "Bot added successfully"}), 201


@bots_bp.route("/<int:bot_id>", methods=["DELETE"])
@jwt_required()
def delete_bot(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    try:
        from ..bot_manager import bot_manager
        bot_manager.stop_bot(bot_id)
    except Exception as e:
        current_app.logger.error(f"Failed to stop bot {bot_id}: {e}")

    db.session.delete(bot)
    db.session.commit()

    return jsonify({"message": "Bot deleted successfully"}), 200


@bots_bp.route("/<int:bot_id>", methods=["GET"])
@jwt_required()
def get_bot(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    return jsonify({"bot": _enrich_bot(bot)}), 200


@bots_bp.route("/<int:bot_id>/groups", methods=["GET"])
@jwt_required()
def get_bot_groups(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    # Find Hub-connected private groups for this bot so we can exclude them.
    # Private groups (is_public_group=False) belong in Assistant Hub only.
    hub_private_tg_ids: set = set()
    try:
        from ..models import CustomBot
        from ..assistant.hub_models import HubBotIdentity, HubConnectedGroup
        cb = CustomBot.query.filter_by(
            bot_username=bot.bot_username,
            owner_user_id=bot.user_id,
        ).first()
        if cb and cb.hub_bot_id:
            hub_private_tg_ids = {
                str(hg.telegram_group_id)
                for hg in HubConnectedGroup.query.filter_by(
                    bot_id=cb.hub_bot_id, is_active=True
                ).all()
                if not hg.is_public_group
            }
    except Exception:
        pass

    all_groups = Group.query.filter(
        Group.bot_id == bot_id,
        Group.chat_type != "private",
    ).all()

    # Resolve chat_username for any group that hasn't been classified yet (NULL).
    # chat_username == ""  → confirmed private; excluded from Group Management.
    # chat_username is not NULL and non-empty → public group; shown.
    # chat_username is NULL → unknown (old record); shown for backwards compat.
    unresolved = [g for g in all_groups if g.chat_username is None]
    if unresolved:
        try:
            token = bot.get_token()
            for g in unresolved:
                try:
                    resp = http_requests.get(
                        f"https://api.telegram.org/bot{token}/getChat",
                        params={"chat_id": g.telegram_group_id},
                        timeout=3,
                    )
                    data = resp.json()
                    if data.get("ok"):
                        username = data["result"].get("username") or ""
                        g.chat_username = username
                    else:
                        # Telegram returned an error — treat as private to be safe.
                        g.chat_username = ""
                except Exception:
                    # Network / timeout — leave as NULL; show the group.
                    pass
            db.session.commit()
        except Exception:
            pass

    # Exclude confirmed-private groups that are not already handled as Hub groups.
    groups = [
        g for g in all_groups
        if g.telegram_group_id not in hub_private_tg_ids
        and g.chat_username != ""
    ]
    return jsonify({"groups": [g.to_dict() for g in groups]}), 200


@bots_bp.route("/<int:bot_id>/groups/<int:group_id>", methods=["DELETE"])
@jwt_required()
def disconnect_bot_group(bot_id, group_id):
    """
    Disconnect a single group from a custom bot.

    Ownership chain verified: user → Bot → Group.
    Only deletes the Group record (bot-group link in the old system).
    Does NOT touch TelegramGroup, official bot groups, or analytics records
    stored by telegram_group_id.
    """
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    if not group:
        return jsonify({"error": "Group not found or does not belong to this bot"}), 404

    group_name = group.group_name or str(group.telegram_group_id)
    db.session.delete(group)
    db.session.commit()

    return jsonify({"message": f"Group '{group_name}' disconnected from bot"}), 200


@bots_bp.route("/<int:bot_id>/toggle", methods=["POST"])
@jwt_required()
def toggle_bot(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    from ..bot_manager import bot_manager

    if bot.is_active:
        bot_manager.stop_bot(bot_id)
        bot.is_active = False
        msg = "Bot stopped"
    else:
        bot.is_active = True
        bot_manager.start_bot(bot_id, bot.get_token(), current_app._get_current_object())
        msg = "Bot started"

    db.session.commit()
    return jsonify({"message": msg, "is_active": bot.is_active}), 200


@bots_bp.route("/<int:bot_id>/status", methods=["GET"])
@jwt_required()
def bot_status(bot_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    from ..bot_manager import bot_manager
    running = bot_manager.is_running(bot_id)

    auto_restarted = False
    if not running and bot.is_active:
        auto_restarted = bot_manager.start_bot(bot_id, bot.get_token(), current_app._get_current_object())

    return jsonify({
        "bot_id": bot_id,
        "is_active": bot.is_active,
        "thread_alive": running,
        "auto_restarted": auto_restarted,
    }), 200


@bots_bp.route("/<int:bot_id>/reveal-token", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def reveal_token(bot_id):
    """Step-up authentication: requires current account password.

    Returns the raw decrypted bot token once per confirmed request.
    Every successful reveal is recorded in AuditLog for security monitoring.
    """
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return jsonify({"error": "Bot not found"}), 404

    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not password:
        return jsonify({"error": "password is required"}), 400

    if not user.check_password(password):
        return jsonify({"error": "Invalid password"}), 403

    token = bot.get_token()
    if not token:
        return jsonify({"error": "Token unavailable"}), 500

    # Audit log — every token reveal is tracked for security review
    import json
    audit = AdminAuditLog(
        admin_id=user.id,
        action="bot_token_revealed",
        method="POST",
        path=f"/api/bots/{bot_id}/reveal-token",
        payload_json=json.dumps({"bot_id": bot_id, "bot_username": bot.bot_username}),
        ip_address=request.remote_addr,
    )
    db.session.add(audit)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    masked = "•" * max(0, len(token) - 4) + token[-4:]
    return jsonify({"token": token, "masked": masked}), 200
