"""
Integration Webhooks API — outbound event webhooks for n8n / Zapier / custom.

GET    /api/integrations/webhooks              list
POST   /api/integrations/webhooks              create
PUT    /api/integrations/webhooks/<id>         update
DELETE /api/integrations/webhooks/<id>         delete
POST   /api/integrations/webhooks/<id>/test    send a test event
"""

import logging
import re
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..models import IntegrationWebhook, User, db
from ..middleware.rate_limit import rate_limit
from ..integrations.dispatcher import SUPPORTED_EVENTS, EVENT_CATALOG

_log = logging.getLogger(__name__)

integration_webhooks_bp = Blueprint(
    "integration_webhooks", __name__, url_prefix="/api/integrations/webhooks"
)

_PRIVATE_IP_RE = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)",
    re.IGNORECASE,
)


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


def _validate_url(url: str) -> str | None:
    """Return error string or None if valid."""
    if not url:
        return "url is required"
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL"
    if parsed.scheme not in ("http", "https"):
        return "URL must start with http:// or https://"
    host = parsed.hostname or ""
    if _PRIVATE_IP_RE.match(host):
        return "Private / localhost URLs are not allowed"
    return None


@integration_webhooks_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_webhooks():
    user = _current_user()
    hooks = IntegrationWebhook.query.filter_by(user_id=user.id).order_by(IntegrationWebhook.created_at.desc()).all()
    return jsonify({"webhooks": [h.to_dict() for h in hooks], "supported_events": sorted(SUPPORTED_EVENTS)})


@integration_webhooks_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_webhook():
    user = _current_user()
    body = request.get_json(silent=True) or {}

    name = (body.get("name") or "").strip()[:200]
    if not name:
        return jsonify({"error": "name is required"}), 400

    url = (body.get("url") or "").strip()
    url_err = _validate_url(url)
    if url_err:
        return jsonify({"error": url_err}), 400

    events = [e for e in (body.get("events") or []) if e in SUPPORTED_EVENTS]
    if not events:
        return jsonify({"error": f"Select at least one event. Supported: {sorted(SUPPORTED_EVENTS)}"}), 400

    secret = (body.get("secret") or "").strip()[:255] or None

    hook = IntegrationWebhook(
        user_id=user.id,
        name=name,
        url=url,
        secret=secret,
        events=events,
        is_active=True,
    )
    db.session.add(hook)
    db.session.commit()
    return jsonify({"webhook": hook.to_dict()}), 201


@integration_webhooks_bp.route("/<int:hook_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_webhook(hook_id: int):
    user = _current_user()
    hook = IntegrationWebhook.query.filter_by(id=hook_id, user_id=user.id).first_or_404()
    body = request.get_json(silent=True) or {}

    if "name" in body:
        hook.name = (body["name"] or "").strip()[:200] or hook.name
    if "url" in body:
        url_err = _validate_url(body["url"])
        if url_err:
            return jsonify({"error": url_err}), 400
        hook.url = body["url"].strip()
    if "events" in body:
        events = [e for e in (body["events"] or []) if e in SUPPORTED_EVENTS]
        if not events:
            return jsonify({"error": "Select at least one valid event"}), 400
        hook.events = events
    if "secret" in body:
        hook.secret = (body["secret"] or "").strip()[:255] or None
    if "is_active" in body:
        hook.is_active = bool(body["is_active"])
        if hook.is_active:
            hook.failure_count = 0   # reset on manual re-enable

    db.session.commit()
    return jsonify({"webhook": hook.to_dict()})


@integration_webhooks_bp.route("/<int:hook_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def delete_webhook(hook_id: int):
    user = _current_user()
    hook = IntegrationWebhook.query.filter_by(id=hook_id, user_id=user.id).first_or_404()
    db.session.delete(hook)
    db.session.commit()
    return jsonify({"ok": True})


@integration_webhooks_bp.route("/<int:hook_id>/test", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def test_webhook(hook_id: int):
    """Send a test payload to the webhook URL synchronously and return the result."""
    user = _current_user()
    hook = IntegrationWebhook.query.filter_by(id=hook_id, user_id=user.id).first_or_404()

    import hashlib
    import hmac
    import json
    import uuid
    from datetime import datetime

    import requests as _r

    first_event = (hook.events or ["meeting.created"])[0]
    delivery_id = str(uuid.uuid4())
    envelope = {
        "event": first_event,
        "delivery_id": delivery_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": user.id,
        "data": {
            "test": True,
            "message": "This is a test event from Telegizer",
            "event_type": first_event,
        },
    }
    body = json.dumps(envelope, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Telegizer-Event": first_event,
        "X-Telegizer-Delivery": delivery_id,
    }
    if hook.secret:
        sig = hmac.new(hook.secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Telegizer-Signature"] = f"sha256={sig}"

    try:
        resp = _r.post(hook.url, data=body, headers=headers, timeout=10)
        success = resp.status_code < 400
        return jsonify({
            "ok": success,
            "status_code": resp.status_code,
            "response_preview": resp.text[:500],
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 200


@integration_webhooks_bp.route("/event-types", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_event_types():
    """Return the full event catalog with sample payloads."""
    return jsonify({"events": EVENT_CATALOG})
