import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, Bot, Group, UserApiKey
from ..utils.encryption import encrypt_value, decrypt_value, mask_key
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

api_keys_bp = Blueprint("api_keys", __name__, url_prefix="/api")

VALID_PROVIDERS = {"openai", "openrouter", "anthropic", "gemini", "custom"}

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
}

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "gemini": "gemini-1.5-flash",
}


def _get_current_user():
    return User.query.get(int(get_jwt_identity()))


def _get_group(user, bot_id, group_id):
    bot = Bot.query.filter_by(id=bot_id, user_id=user.id).first()
    if not bot:
        return None, None
    group = Group.query.filter_by(id=group_id, bot_id=bot.id).first()
    return bot, group


@api_keys_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/api-keys", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_api_key(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    key_record = UserApiKey.query.filter_by(group_id=group.id, is_active=True).order_by(
        UserApiKey.updated_at.desc()
    ).first()

    if not key_record:
        return jsonify({"api_key": None})

    return jsonify({"api_key": key_record.to_dict()})


@api_keys_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/api-keys", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def save_api_key(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    provider = (data.get("provider") or "").strip().lower()
    api_key = (data.get("api_key") or "").strip()
    base_url = (data.get("base_url") or "").strip() or None
    model_name = (data.get("model_name") or "").strip() or None

    if not provider or provider not in VALID_PROVIDERS:
        return jsonify({"error": f"Provider must be one of: {', '.join(VALID_PROVIDERS)}"}), 400

    # Treat absent, empty, or masked api_key as "keep existing key"
    keep_existing_key = not api_key or "****" in api_key

    existing = UserApiKey.query.filter_by(group_id=group.id, is_active=True).first()

    if keep_existing_key:
        if not existing:
            return jsonify({"error": "API key is required"}), 400
        # Update metadata only — preserve the existing encrypted key
        existing.provider = provider
        existing.base_url = base_url
        existing.model_name = model_name
        from datetime import datetime
        existing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"api_key": existing.to_dict(), "message": "API key updated"})

    encrypted_key = encrypt_value(api_key)
    if not encrypted_key:
        return jsonify({"error": "Failed to encrypt API key. Check server configuration."}), 500

    if existing:
        existing.provider = provider
        existing.api_key_encrypted = encrypted_key
        existing.base_url = base_url
        existing.model_name = model_name
        from datetime import datetime
        existing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"api_key": existing.to_dict(), "message": "API key updated"})
    else:
        record = UserApiKey(
            group_id=group.id,
            user_id=user.id,
            provider=provider,
            api_key_encrypted=encrypted_key,
            base_url=base_url,
            model_name=model_name,
            is_active=True,
        )
        db.session.add(record)
        db.session.commit()
        return jsonify({"api_key": record.to_dict(), "message": "API key saved"}), 201


@api_keys_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/api-keys", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def delete_api_key(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    UserApiKey.query.filter_by(group_id=group.id).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "API key removed"})


@api_keys_bp.route("/bots/<int:bot_id>/groups/<int:group_id>/api-keys/test", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def test_api_key(bot_id, group_id):
    user = _get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    _, group = _get_group(user, bot_id, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json() or {}
    provider = (data.get("provider") or "").strip().lower()
    api_key = (data.get("api_key") or "").strip()
    base_url = (data.get("base_url") or "").strip() or None
    model_name = (data.get("model_name") or "").strip() or None

    if not provider or provider not in VALID_PROVIDERS:
        return jsonify({"error": "Invalid provider"}), 400

    # If api_key is masked (user didn't re-enter it), load from DB
    if not api_key or "****" in api_key:
        existing = UserApiKey.query.filter_by(group_id=group.id, is_active=True).first()
        if not existing:
            return jsonify({"error": "No API key saved yet"}), 400
        api_key = decrypt_value(existing.api_key_encrypted)
        if not api_key:
            return jsonify({"error": "Failed to decrypt stored API key"}), 500
        provider = existing.provider
        base_url = base_url or existing.base_url
        model_name = model_name or existing.model_name

    try:
        success, message = _test_connection(provider, api_key, base_url, model_name)
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "error": message}), 400
    except Exception as e:
        logger.error(f"Test connection error: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


def _test_connection(provider, api_key, base_url=None, model_name=None):
    """Returns (success: bool, message: str)."""
    if provider in ("openai", "openrouter", "custom"):
        return _test_openai_compatible(provider, api_key, base_url, model_name)
    elif provider == "anthropic":
        return _test_anthropic(api_key, base_url, model_name)
    elif provider == "gemini":
        return _test_gemini(api_key, model_name)
    return False, f"Unsupported provider: {provider}"


def _test_openai_compatible(provider, api_key, base_url, model_name):
    try:
        from openai import OpenAI
        url = base_url or DEFAULT_BASE_URLS.get(provider)
        model = model_name or DEFAULT_MODELS.get(provider, "gpt-4o-mini")
        client = OpenAI(api_key=api_key, base_url=url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK"}],
            max_tokens=5,
        )
        reply = resp.choices[0].message.content.strip() if resp.choices else ""
        return True, f"Connection successful. Model: {model}. Response: {reply}"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"


def _test_anthropic(api_key, base_url, model_name):
    import requests as req
    model = model_name or DEFAULT_MODELS["anthropic"]
    url = (base_url or "https://api.anthropic.com") + "/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 10,
        "messages": [{"role": "user", "content": "Reply with OK"}],
    }
    try:
        resp = req.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            reply = data.get("content", [{}])[0].get("text", "")
            return True, f"Connection successful. Model: {model}. Response: {reply}"
        else:
            return False, f"API returned {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"


def _test_gemini(api_key, model_name):
    import requests as req
    model = model_name or DEFAULT_MODELS["gemini"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": "Reply with OK"}]}]}
    try:
        resp = req.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            reply = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return True, f"Connection successful. Model: {model}. Response: {reply}"
        else:
            return False, f"API returned {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"
