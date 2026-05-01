import hashlib
import hmac
import secrets
import asyncio
import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, WebhookIntegration
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api")


def _get_current_user():
    return User.query.get(int(get_jwt_identity()))


def _get_group(user, bot_id, group_id):
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return None, None
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    return bot, group


def _verify_webhook_signature(hook: WebhookIntegration, raw_body: bytes) -> bool:
    """Return True if the request carries a valid HMAC-SHA256 signature.

    Signature header: X-Telegizer-Signature: sha256=<hex>

    If the hook has no signing_secret (legacy rows created before this fix),
    the signature check is skipped and the URL token alone is accepted.
    Callers should be prompted to rotate and enable signing.
    """
    if not hook.signing_secret:
        return True  # legacy hook — no signing configured yet

    provided = request.headers.get("X-Telegizer-Signature", "")
    if not provided.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        hook.signing_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, provided)


@webhooks_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/webhooks", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def list_webhooks(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    hooks = WebhookIntegration.query.filter_by(group_id=group.id).order_by(WebhookIntegration.created_at.desc()).all()
    # Mask signing_secret in list view — shown only at creation
    result = []
    for h in hooks:
        d = h.to_dict()
        d["signing_secret"] = "***" if h.signing_secret else None
        result.append(d)
    return jsonify({"webhooks": result})


@webhooks_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/webhooks", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_webhook(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400

    signing_secret = secrets.token_hex(32)

    hook = WebhookIntegration(
        group_id=group.id,
        name=name,
        webhook_token=secrets.token_urlsafe(32),
        signing_secret=signing_secret,
        description=(data.get("description") or "")[:255] or None,
        message_template=data.get("message_template") or "📡 *{name}*\n\n{payload}",
        is_active=True,
    )
    db.session.add(hook)
    db.session.commit()

    response = hook.to_dict()
    response["signing_secret"] = signing_secret  # returned once — user must save it
    response["signing_note"] = (
        "Sign requests with HMAC-SHA256 using this secret. "
        "Header: X-Telegizer-Signature: sha256=<hex_digest_of_raw_body>. "
        "This secret will not be shown again."
    )
    return jsonify({"webhook": response}), 201


@webhooks_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/webhooks/<int:hook_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_webhook(bot_id, group_id, hook_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    hook = WebhookIntegration.query.filter_by(id=hook_id, group_id=group.id).first()
    if not hook:
        return jsonify({"error": "Webhook not found"}), 404

    data = request.get_json() or {}
    if "name" in data:
        hook.name = data["name"][:100]
    if "description" in data:
        hook.description = (data["description"] or "")[:255] or None
    if "message_template" in data:
        hook.message_template = data["message_template"] or "{payload}"
    if "is_active" in data:
        hook.is_active = bool(data["is_active"])
    db.session.commit()

    result = hook.to_dict()
    result["signing_secret"] = "***" if hook.signing_secret else None
    return jsonify({"webhook": result})


@webhooks_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/webhooks/<int:hook_id>/rotate-secret", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def rotate_webhook_secret(bot_id, group_id, hook_id):
    """Rotate the signing secret for a webhook. Returns the new secret once."""
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    hook = WebhookIntegration.query.filter_by(id=hook_id, group_id=group.id).first()
    if not hook:
        return jsonify({"error": "Webhook not found"}), 404

    new_secret = secrets.token_hex(32)
    hook.signing_secret = new_secret
    db.session.commit()

    return jsonify({
        "signing_secret": new_secret,
        "signing_note": "Update your sender to use this new secret. The old secret is now invalid.",
    })


@webhooks_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/webhooks/<int:hook_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_webhook(bot_id, group_id, hook_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    hook = WebhookIntegration.query.filter_by(id=hook_id, group_id=group.id).first()
    if not hook:
        return jsonify({"error": "Webhook not found"}), 404
    db.session.delete(hook)
    db.session.commit()
    return jsonify({"success": True})


# Public trigger endpoint — authenticated by URL token + optional HMAC signature
@webhooks_bp.route("/webhooks/<string:token>/trigger", methods=["POST"])
@rate_limit(requests_per_minute=60)
def trigger_webhook(token):
    hook = WebhookIntegration.query.filter_by(webhook_token=token, is_active=True).first()
    if not hook:
        return jsonify({"error": "Webhook not found"}), 404

    # Verify HMAC signature before reading body content
    raw_body = request.get_data()
    if not _verify_webhook_signature(hook, raw_body):
        logger.warning("Webhook %s rejected — invalid X-Telegizer-Signature", hook.id)
        return jsonify({"error": "Invalid signature"}), 403

    group = Group.query.get(hook.group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    bot = Bot.query.get(group.bot_id)
    if not bot or not bot.is_active:
        return jsonify({"error": "Bot not active"}), 400

    try:
        import json
        payload_data = json.loads(raw_body) if raw_body else {}
        if not isinstance(payload_data, dict):
            payload_data = {}
    except Exception:
        payload_data = {}

    payload_str = "\n".join(f"*{k}:* {v}" for k, v in payload_data.items()) if payload_data else ""

    message = hook.message_template.replace("{name}", hook.name).replace("{payload}", payload_str)
    for k, v in payload_data.items():
        message = message.replace(f"{{{k}}}", str(v))

    from ..app import bot_manager
    instance = bot_manager.active_bots.get(bot.id)
    if instance and instance.application and instance.loop and instance.loop.is_running():
        async def _send(msg=message, g=group):
            try:
                await instance.application.bot.send_message(
                    chat_id=g.telegram_group_id,
                    text=msg,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error("Webhook trigger send error: %s", e)
        asyncio.run_coroutine_threadsafe(_send(), instance.loop)

    return jsonify({"success": True, "message": "Webhook triggered"})
