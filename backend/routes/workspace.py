"""
Workspace API — user-scoped features that span all groups.

Smart Links   POST/GET/PUT/DELETE /api/workspace/smart-links
Reminders     POST/GET/DELETE      /api/workspace/reminders
AI Settings   GET/POST/DELETE      /api/workspace/ai-settings
              POST                 /api/workspace/ai-settings/test
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, AutoResponse, TelegramGroup, WorkspaceReminder, UserApiKey
from ..middleware.rate_limit import rate_limit

workspace_bp = Blueprint("workspace", __name__, url_prefix="/api/workspace")

_VALID_SCOPES = {"group", "user"}
_VALID_MATCH = {"contains", "exact", "starts_with"}


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


def _owns_link(user: User, ar: AutoResponse) -> bool:
    """Return True when the user is authorised to manage this smart link."""
    if ar.owner_user_id == user.id:
        return True
    # Also allow if the link is group-scoped and user owns that group
    if ar.telegram_group_id:
        g = TelegramGroup.query.filter_by(
            telegram_group_id=ar.telegram_group_id,
            owner_user_id=user.id,
            is_disabled=False,
        ).first()
        return g is not None
    return False


# ── List ─────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_smart_links():
    user = _current_user()

    # All smart links owned by this user (global scope)
    owned = AutoResponse.query.filter_by(
        owner_user_id=user.id,
        response_type="smart_link",
    ).order_by(AutoResponse.created_at.desc()).all()

    # Smart links scoped to groups the user owns (in case they were created per-group)
    group_ids = [g.telegram_group_id for g in
                 TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()]
    group_links = []
    if group_ids:
        group_links = AutoResponse.query.filter(
            AutoResponse.telegram_group_id.in_(group_ids),
            AutoResponse.response_type == "smart_link",
            AutoResponse.owner_user_id.is_(None),  # legacy rows without owner set
        ).order_by(AutoResponse.created_at.desc()).all()

    seen = {ar.id for ar in owned}
    combined = list(owned) + [ar for ar in group_links if ar.id not in seen]

    return jsonify({"smart_links": [ar.to_dict() for ar in combined]})


# ── Create ────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def create_smart_link():
    user = _current_user()
    data = request.get_json() or {}

    label = (data.get("link_label") or "").strip()
    triggers_raw = (data.get("trigger_text") or "").strip()
    url = (data.get("link_url") or "").strip()
    response_text = (data.get("response_text") or url or "").strip()
    match_type = data.get("match_type", "contains")
    scope = data.get("scope", "user")
    telegram_group_id = data.get("telegram_group_id") or None
    is_case_sensitive = bool(data.get("is_case_sensitive", False))

    if not label:
        return jsonify({"error": "link_label is required"}), 400
    if not triggers_raw:
        return jsonify({"error": "trigger_text is required"}), 400
    if not response_text:
        return jsonify({"error": "link_url or response_text is required"}), 400
    if match_type not in _VALID_MATCH:
        return jsonify({"error": f"match_type must be one of {sorted(_VALID_MATCH)}"}), 400
    if scope not in _VALID_SCOPES:
        return jsonify({"error": f"scope must be one of {sorted(_VALID_SCOPES)}"}), 400

    # Validate group ownership when group-scoped
    if scope == "group" and telegram_group_id:
        g = TelegramGroup.query.filter_by(
            telegram_group_id=telegram_group_id,
            owner_user_id=user.id,
            is_disabled=False,
        ).first()
        if not g:
            return jsonify({"error": "Group not found or not owned by you"}), 404
    else:
        telegram_group_id = None  # user-scoped links are not tied to a group

    ar = AutoResponse(
        owner_user_id=user.id,
        response_type="smart_link",
        link_label=label[:100],
        link_url=url[:2000] if url else None,
        trigger_text=triggers_raw[:500],
        response_text=response_text,
        match_type=match_type,
        is_case_sensitive=is_case_sensitive,
        is_enabled=True,
        scope=scope,
        telegram_group_id=telegram_group_id,
    )
    db.session.add(ar)
    db.session.commit()
    return jsonify({"smart_link": ar.to_dict()}), 201


# ── Update ────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links/<int:link_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_smart_link(link_id):
    user = _current_user()
    ar = AutoResponse.query.get_or_404(link_id)
    if not _owns_link(user, ar) or ar.response_type != "smart_link":
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    if "link_label" in data:
        ar.link_label = (data["link_label"] or "").strip()[:100]
    if "trigger_text" in data:
        ar.trigger_text = (data["trigger_text"] or "").strip()[:500]
    if "link_url" in data:
        ar.link_url = (data["link_url"] or "").strip()[:2000] or None
    if "response_text" in data:
        ar.response_text = (data["response_text"] or ar.link_url or "").strip()
    if "match_type" in data and data["match_type"] in _VALID_MATCH:
        ar.match_type = data["match_type"]
    if "is_case_sensitive" in data:
        ar.is_case_sensitive = bool(data["is_case_sensitive"])
    if "is_enabled" in data:
        ar.is_enabled = bool(data["is_enabled"])
    if "scope" in data and data["scope"] in _VALID_SCOPES:
        ar.scope = data["scope"]

    db.session.commit()
    return jsonify({"smart_link": ar.to_dict()})


# ── Delete ────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links/<int:link_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_smart_link(link_id):
    user = _current_user()
    ar = AutoResponse.query.get_or_404(link_id)
    if not _owns_link(user, ar) or ar.response_type != "smart_link":
        return jsonify({"error": "Not found"}), 404
    db.session.delete(ar)
    db.session.commit()
    return jsonify({"deleted": True})


# ── Toggle ────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links/<int:link_id>/toggle", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def toggle_smart_link(link_id):
    user = _current_user()
    ar = AutoResponse.query.get_or_404(link_id)
    if not _owns_link(user, ar) or ar.response_type != "smart_link":
        return jsonify({"error": "Not found"}), 404
    ar.is_enabled = not ar.is_enabled
    db.session.commit()
    return jsonify({"smart_link": ar.to_dict()})


# ── Reminders ──────────────────────────────────────────────────────────────────

@workspace_bp.route("/reminders", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_reminders():
    user = _current_user()
    include_delivered = request.args.get("delivered", "false").lower() == "true"
    q = WorkspaceReminder.query.filter_by(owner_user_id=user.id)
    if not include_delivered:
        q = q.filter_by(is_delivered=False)
    reminders = q.order_by(WorkspaceReminder.remind_at.asc()).all()
    return jsonify({"reminders": [r.to_dict() for r in reminders]})


@workspace_bp.route("/reminders", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def create_reminder():
    user = _current_user()
    data = request.get_json() or {}

    reminder_text = (data.get("reminder_text") or "").strip()
    remind_at_raw = data.get("remind_at")
    telegram_group_id = data.get("telegram_group_id") or None

    if not reminder_text:
        return jsonify({"error": "reminder_text is required"}), 400
    if not remind_at_raw:
        return jsonify({"error": "remind_at is required (ISO datetime)"}), 400

    try:
        # Normalise to UTC naive datetime for consistent comparison with utcnow()
        parsed = datetime.fromisoformat(str(remind_at_raw).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            from datetime import timezone as _tz
            remind_at = parsed.astimezone(_tz.utc).replace(tzinfo=None)
        else:
            remind_at = parsed
    except ValueError:
        return jsonify({"error": "remind_at must be a valid ISO datetime"}), 400

    if remind_at <= datetime.utcnow():
        return jsonify({"error": "remind_at must be in the future"}), 400

    reminder = WorkspaceReminder(
        owner_user_id=user.id,
        reminder_text=reminder_text[:500],
        remind_at=remind_at,
        telegram_group_id=telegram_group_id,
    )
    db.session.add(reminder)
    db.session.commit()

    try:
        from ..integrations.dispatcher import fire_event
        fire_event(user.id, "reminder.created", reminder.to_dict())
    except Exception:
        pass

    return jsonify({"reminder": reminder.to_dict()}), 201


@workspace_bp.route("/reminders/<int:reminder_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_reminder(reminder_id):
    user = _current_user()
    reminder = WorkspaceReminder.query.get_or_404(reminder_id)
    if reminder.owner_user_id != user.id:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(reminder)
    db.session.commit()
    return jsonify({"deleted": True})


# ── Workspace AI Settings ──────────────────────────────────────────────────────

def _token_limit(user: User) -> int:
    tier = user.subscription_tier
    if tier == "enterprise":
        return 500000
    if tier == "pro":
        return 200000
    return 10000


def _maybe_reset_tokens(user: User) -> None:
    """Reset daily token counter if 24 hours have elapsed since last reset."""
    now = datetime.utcnow()
    if (
        user.workspace_ai_tokens_reset_at is None
        or (now - user.workspace_ai_tokens_reset_at).total_seconds() >= 86400
    ):
        user.workspace_ai_tokens_today = 0
        user.workspace_ai_tokens_reset_at = now
        db.session.commit()


def _test_provider_key(provider: str, api_key: str, model: str, base_url: str = None) -> tuple:
    """Send a minimal prompt to verify an AI provider key. Returns (ok, message)."""
    import requests as _req
    timeout = 10

    try:
        if provider == "gemini":
            model_id = model or "gemini-2.0-flash"
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_id}:generateContent?key={api_key}"
            )
            r = _req.post(
                url,
                json={"contents": [{"parts": [{"text": "Hi"}]}]},
                timeout=timeout,
            )
            if r.status_code == 200:
                return True, "Key is valid"
            err = (r.json().get("error") or {}).get("message", f"Error {r.status_code}")
            return False, err

        elif provider in ("openai", "custom"):
            base = (base_url or "https://api.openai.com").rstrip("/")
            endpoint = f"{base}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            r = _req.post(
                endpoint,
                json={
                    "model": model or "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                },
                headers=headers,
                timeout=timeout,
            )
            if r.status_code == 200:
                return True, "Key is valid"
            try:
                err = (r.json().get("error") or {}).get("message", f"Error {r.status_code}")
            except Exception:
                err = f"Error {r.status_code}"
            return False, err

        elif provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            r = _req.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": model or "claude-haiku-4-5-20251001",
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers=headers,
                timeout=timeout,
            )
            if r.status_code == 200:
                return True, "Key is valid"
            try:
                err = (r.json().get("error") or {}).get("message", f"Error {r.status_code}")
            except Exception:
                err = f"Error {r.status_code}"
            return False, err

        elif provider == "openrouter":
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://opencalwtest.online",
            }
            r = _req.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": model or "google/gemini-flash-1.5",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                },
                headers=headers,
                timeout=timeout,
            )
            if r.status_code == 200:
                return True, "Key is valid"
            try:
                err = (r.json().get("error") or {}).get("message", f"Error {r.status_code}")
            except Exception:
                err = f"Error {r.status_code}"
            return False, err

        return False, f"Unknown provider: {provider}"

    except Exception as exc:
        return False, f"Connection error: {str(exc)[:120]}"


@workspace_bp.route("/ai-settings", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_ai_settings():
    from ..config import Config

    user = _current_user()
    _maybe_reset_tokens(user)

    user_key = (
        UserApiKey.query
        .filter_by(user_id=user.id, scope="workspace", is_active=True)
        .order_by(UserApiKey.updated_at.desc())
        .first()
    )

    tier = user.subscription_tier
    token_limit = _token_limit(user)

    _PLAN_ENTITLEMENTS = {
        "enterprise": {
            "label": "Enterprise",
            "platform_ai_included": True,
            "description": "Full Telegizer AI access included",
            "models": ["GPT-4o Mini", "GPT-4.1 Mini", "Claude Haiku", "Gemini Flash"],
            "token_limit": 500000,
            "priority": "High priority queue",
        },
        "pro": {
            "label": "Pro",
            "platform_ai_included": True,
            "description": "Telegizer AI included in your Pro plan",
            "models": ["GPT-4o Mini", "Gemini Flash"],
            "token_limit": 200000,
            "priority": "Standard queue",
        },
        "free": {
            "label": "Free",
            "platform_ai_included": bool(Config.PLATFORM_OPENROUTER_API_KEY),
            "description": "Limited platform AI access",
            "models": ["GPT-4o Mini"],
            "token_limit": 10000,
            "priority": None,
        },
    }

    entitlements = _PLAN_ENTITLEMENTS.get(tier, _PLAN_ENTITLEMENTS["free"])

    return jsonify({
        "platform_key_active": bool(Config.PLATFORM_OPENROUTER_API_KEY),
        "user_key": user_key.to_dict() if user_key else None,
        "token_usage": {
            "used": user.workspace_ai_tokens_today or 0,
            "limit": token_limit,
            "reset_at": (
                user.workspace_ai_tokens_reset_at.isoformat()
                if user.workspace_ai_tokens_reset_at else None
            ),
        },
        "plan": {
            "tier": tier,
            "subscription_active": user.subscription_active,
            **entitlements,
        },
        "telegram_connected": bool(user.telegram_user_id),
        "telegram_username": user.telegram_username,
    })


_VALID_PROVIDERS = {"gemini", "openai", "anthropic", "openrouter", "custom"}


@workspace_bp.route("/ai-settings", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def save_ai_settings():
    from ..utils.encryption import encrypt_value

    user = _current_user()
    data = request.get_json() or {}

    provider = (data.get("provider") or "").strip().lower()
    api_key = (data.get("api_key") or "").strip()
    model = (data.get("model") or "").strip() or None
    base_url = (data.get("base_url") or "").strip() or None

    if provider not in _VALID_PROVIDERS:
        return jsonify({"error": f"provider must be one of {sorted(_VALID_PROVIDERS)}"}), 400
    if not api_key:
        return jsonify({"error": "api_key is required"}), 400

    # Deactivate any existing workspace key
    for existing in UserApiKey.query.filter_by(user_id=user.id, scope="workspace", is_active=True).all():
        existing.is_active = False

    new_key = UserApiKey(
        user_id=user.id,
        scope="workspace",
        provider=provider,
        api_key_encrypted=encrypt_value(api_key),
        model_name=model,
        base_url=base_url,
        is_active=True,
    )
    db.session.add(new_key)
    db.session.commit()
    return jsonify({"success": True, "user_key": new_key.to_dict()}), 201


@workspace_bp.route("/ai-settings", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def delete_ai_settings():
    user = _current_user()
    for key in UserApiKey.query.filter_by(user_id=user.id, scope="workspace", is_active=True).all():
        key.is_active = False
    db.session.commit()
    return jsonify({"success": True})


# ── Workspace Digests overview ─────────────────────────────────────────────────

@workspace_bp.route("/digests", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_digests():
    """Return all user's groups with their digest config and last-sent info."""
    from ..models import TelegramGroup, DigestLog

    user = _current_user()
    groups = (
        TelegramGroup.query
        .filter_by(owner_user_id=user.id, is_disabled=False)
        .order_by(TelegramGroup.linked_at.desc())
        .all()
    )

    result = []
    for g in groups:
        digest = (g.settings or {}).get("digest", {})
        last_log = (
            DigestLog.query
            .filter_by(group_id=g.telegram_group_id)
            .order_by(DigestLog.sent_at.desc())
            .first()
        )
        result.append({
            "group_id": g.telegram_group_id,
            "group_title": g.title,
            "bot_status": g.bot_status,
            "digest": digest,
            "last_sent": last_log.to_dict() if last_log else None,
        })

    return jsonify({"groups": result})


@workspace_bp.route("/ai-settings/test", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def test_ai_settings():
    data = request.get_json() or {}
    provider = (data.get("provider") or "").strip().lower()
    api_key = (data.get("api_key") or "").strip()
    model = (data.get("model") or "").strip() or None
    base_url = (data.get("base_url") or "").strip() or None

    if not provider or not api_key:
        return jsonify({"error": "provider and api_key are required"}), 400
    if provider not in _VALID_PROVIDERS:
        return jsonify({"error": f"provider must be one of {sorted(_VALID_PROVIDERS)}"}), 400

    ok, message = _test_provider_key(provider, api_key, model, base_url)
    return jsonify({"success": ok, "message": message})
