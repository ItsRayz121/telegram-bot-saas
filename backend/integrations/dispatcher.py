"""
Outbound webhook event dispatcher.

Usage:
    from ..integrations.dispatcher import fire_event
    fire_event(user_id=42, event_type="meeting.created", payload={"id": 7, "title": "..."})

Guarantees:
- Never raises — always logs and swallows errors so caller flow is unaffected.
- Signs each request with HMAC-SHA256 if the webhook has a secret configured.
- Marks the webhook inactive after 5 consecutive failures.
- Stores last_triggered_at, last_status, last_error on each webhook row.
"""

import hashlib
import hmac
import json
import logging
import re
import threading
from datetime import datetime

import requests as _requests

_log = logging.getLogger(__name__)

SUPPORTED_EVENTS = frozenset({
    "meeting.created",
    "reminder.created",
    "resource.attached",
    "group.issue.detected",
})

_PRIVATE_IP_RE = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)",
    re.IGNORECASE,
)

MAX_FAILURES = 5
TIMEOUT_SECONDS = 10


def _is_safe_url(url: str) -> bool:
    """Block localhost / private IP targets in any environment."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if _PRIVATE_IP_RE.match(host):
            return False
        return True
    except Exception:
        return False


def _sign_payload(secret: str, body: bytes) -> str:
    """Return hex HMAC-SHA256 signature for the given body."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _dispatch_one(hook, event_type: str, envelope: dict, flask_app) -> None:
    """POST the envelope to a single webhook. Updates DB state."""
    body = json.dumps(envelope, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Telegizer-Event": event_type,
        "X-Telegizer-Delivery": envelope.get("delivery_id", ""),
    }
    if hook.secret:
        headers["X-Telegizer-Signature"] = f"sha256={_sign_payload(hook.secret, body)}"

    try:
        resp = _requests.post(hook.url, data=body, headers=headers, timeout=TIMEOUT_SECONDS)
        success = resp.status_code < 400
    except Exception as exc:
        success = False
        _log.warning("webhook %s delivery failed: %s", hook.id, exc)
        error_msg = str(exc)[:500]
    else:
        error_msg = None if success else f"HTTP {resp.status_code}"

    with flask_app.app_context():
        from ..models import db, IntegrationWebhook
        wh = IntegrationWebhook.query.get(hook.id)
        if not wh:
            return
        wh.last_triggered_at = datetime.utcnow()
        if success:
            wh.last_status = "ok"
            wh.last_error = None
            wh.failure_count = 0
        else:
            wh.last_status = "error"
            wh.last_error = error_msg
            wh.failure_count = (wh.failure_count or 0) + 1
            if wh.failure_count >= MAX_FAILURES:
                wh.is_active = False
                _log.warning("webhook %s disabled after %d consecutive failures", wh.id, MAX_FAILURES)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def fire_event(user_id: int, event_type: str, payload: dict, flask_app=None) -> None:
    """
    Fire an outbound event to all active webhooks subscribed to event_type.

    Must be called inside a Flask app context (or pass flask_app explicitly).
    Never raises — all errors are caught and logged.
    """
    if event_type not in SUPPORTED_EVENTS:
        _log.debug("fire_event: unsupported event type %s — skipped", event_type)
        return

    try:
        # Resolve app context
        if flask_app is None:
            from flask import current_app
            flask_app = current_app._get_current_object()

        from ..models import IntegrationWebhook
        hooks = IntegrationWebhook.query.filter_by(user_id=user_id, is_active=True).all()
        subscribed = [h for h in hooks if event_type in (h.events or [])]

        if not subscribed:
            return

        import uuid
        delivery_id = str(uuid.uuid4())
        envelope = {
            "event": event_type,
            "delivery_id": delivery_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "data": payload,
        }

        for hook in subscribed:
            if not _is_safe_url(hook.url):
                _log.warning("webhook %s has unsafe URL %s — skipping", hook.id, hook.url)
                continue
            # Fire each webhook in a daemon thread so the main request isn't blocked
            t = threading.Thread(
                target=_dispatch_one,
                args=(hook, event_type, envelope, flask_app),
                daemon=True,
            )
            t.start()

    except Exception as exc:
        _log.error("fire_event(%s, %s) failed: %s", user_id, event_type, exc)
