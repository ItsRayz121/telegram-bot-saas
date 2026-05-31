"""
Outbound webhook event dispatcher — with exponential backoff retry.

Usage:
    from ..integrations.dispatcher import fire_event
    fire_event(user_id=42, event_type="meeting.created", payload={"id": 7, "title": "..."})

Guarantees:
- Never raises — all errors are caught and logged.
- Signs each request with HMAC-SHA256 if the webhook has a secret configured.
- Retries failed deliveries: 30s → 2min → 10min → 1hr, then marks permanent failure.
- Disables webhook after MAX_FAILURES consecutive fully-failed deliveries.
- Resets failure_count to 0 on any successful delivery.
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

# ── Retry schedule ─────────────────────────────────────────────────────────────
RETRY_DELAYS = [30, 120, 600, 3600]   # seconds: 30s, 2min, 10min, 1hr

# Signal set on process shutdown so retry sleeps wake up immediately.
_shutdown = threading.Event()

# ── Supported event types ──────────────────────────────────────────────────────
SUPPORTED_EVENTS = frozenset({
    # Assistant / Echo features
    "meeting.created",
    "reminder.created",
    "reminder.triggered",
    "note.created",
    "task.created",
    "digest.sent",
    # Group activity
    "member.joined",
    "member.left",
    "group.issue.detected",
    "resource.attached",
})

# Human-readable catalog for the frontend event picker
EVENT_CATALOG = [
    {
        "event": "meeting.created",
        "label": "Meeting Created",
        "description": "A new meeting is scheduled via the assistant.",
        "sample": {"id": 1, "title": "Q3 Review", "scheduled_at": "2026-06-01T14:00:00Z", "priority": "high"},
    },
    {
        "event": "reminder.created",
        "label": "Reminder Created",
        "description": "A workspace reminder is set.",
        "sample": {"id": 5, "title": "Send report", "remind_at": "2026-06-02T09:00:00Z"},
    },
    {
        "event": "reminder.triggered",
        "label": "Reminder Triggered",
        "description": "A reminder fires (deliver time reached).",
        "sample": {"id": 5, "title": "Send report", "triggered_at": "2026-06-02T09:00:00Z"},
    },
    {
        "event": "note.created",
        "label": "Note Created",
        "description": "A note is saved (manual, AI-extracted, or bot capture).",
        "sample": {"id": 12, "content": "Decision: use blue for branding", "source": "ai", "tags": ["decision"]},
    },
    {
        "event": "task.created",
        "label": "Task Created",
        "description": "A task is extracted or created in a group.",
        "sample": {"id": 8, "title": "Fix login bug", "status": "todo", "group_name": "Dev Team"},
    },
    {
        "event": "digest.sent",
        "label": "Digest Sent",
        "description": "A daily digest is generated and delivered.",
        "sample": {"group_id": "-100123456789", "group_title": "Dev Team", "summary_preview": "3 decisions captured today"},
    },
    {
        "event": "member.joined",
        "label": "Member Joined",
        "description": "A new member joins one of your connected groups.",
        "sample": {"group_id": "-100123456789", "group_title": "My Community", "user_id": 99887766, "username": "newuser"},
    },
    {
        "event": "member.left",
        "label": "Member Left",
        "description": "A member leaves or is removed from a connected group.",
        "sample": {"group_id": "-100123456789", "group_title": "My Community", "user_id": 99887766, "username": "olduser"},
    },
    {
        "event": "group.issue.detected",
        "label": "Group Issue Detected",
        "description": "AutoMod or AI detects a problem in a group.",
        "sample": {"group_id": "-100123456789", "issue_type": "spam_burst", "severity": "high"},
    },
    {
        "event": "resource.attached",
        "label": "Resource Attached",
        "description": "A meeting link or shared resource is captured from a group.",
        "sample": {"group_id": "-100123456789", "resource_type": "zoom_link", "url": "https://zoom.us/j/12345"},
    },
]

_PRIVATE_IP_RE = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)",
    re.IGNORECASE,
)

MAX_FAILURES = 5
TIMEOUT_SECONDS = 10


def signal_shutdown():
    """Call on process exit so retry sleeps unblock immediately."""
    _shutdown.set()


def _is_safe_url(url: str) -> bool:
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
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── Low-level HTTP attempt ─────────────────────────────────────────────────────

def _attempt_delivery(url: str, secret: str | None, event_type: str, envelope: dict):
    """Make one HTTP POST. Returns (success: bool, error_msg: str | None)."""
    body = json.dumps(envelope, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Telegizer-Event": event_type,
        "X-Telegizer-Delivery": envelope.get("delivery_id", ""),
    }
    if secret:
        headers["X-Telegizer-Signature"] = f"sha256={_sign_payload(secret, body)}"
    try:
        resp = _requests.post(url, data=body, headers=headers, timeout=TIMEOUT_SECONDS)
        if resp.status_code < 400:
            return True, None
        return False, f"HTTP {resp.status_code}"
    except Exception as exc:
        _log.debug("webhook delivery network error: %s", exc)
        return False, str(exc)[:500]


# ── DB state update ────────────────────────────────────────────────────────────

def _update_webhook_state(hook_id: int, success: bool, error_msg, flask_app, is_final: bool = True):
    """Persist delivery outcome to the IntegrationWebhook row."""
    with flask_app.app_context():
        from ..models import db, IntegrationWebhook
        wh = IntegrationWebhook.query.get(hook_id)
        if not wh:
            return
        wh.last_triggered_at = datetime.utcnow()
        if success:
            wh.last_status = "ok"
            wh.last_error = None
            wh.failure_count = 0
        elif is_final:
            wh.last_status = "error"
            wh.last_error = error_msg
            wh.failure_count = (wh.failure_count or 0) + 1
            if wh.failure_count >= MAX_FAILURES:
                wh.is_active = False
                _log.warning(
                    "webhook %s disabled after %d consecutive delivery failures", wh.id, MAX_FAILURES
                )
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


# ── Retry loop ─────────────────────────────────────────────────────────────────

def _dispatch_with_retry(hook_id: int, event_type: str, envelope: dict, flask_app):
    """Deliver one webhook with exponential backoff. Runs in a daemon thread."""
    url = secret = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        # Wait before retry (not on first attempt)
        if attempt > 0:
            delay = RETRY_DELAYS[attempt - 1]
            _log.info(
                "webhook %s: attempt %d/%d failed, retrying in %ds",
                hook_id, attempt, len(RETRY_DELAYS) + 1, delay,
            )
            if _shutdown.wait(timeout=delay):
                return   # process shutting down — give up

        # Reload URL + secret from DB each attempt (webhook might be disabled/deleted)
        with flask_app.app_context():
            from ..models import IntegrationWebhook
            wh = IntegrationWebhook.query.get(hook_id)
            if not wh or not wh.is_active:
                return
            url, secret = wh.url, wh.secret

        if not _is_safe_url(url):
            return

        success, error_msg = _attempt_delivery(url, secret, event_type, envelope)

        if success:
            _update_webhook_state(hook_id, True, None, flask_app, is_final=True)
            return

        # 4xx client error — permanent failure, don't retry
        if error_msg and error_msg.startswith("HTTP 4"):
            _log.warning("webhook %s returned client error %s — not retrying", hook_id, error_msg)
            _update_webhook_state(hook_id, False, error_msg, flask_app, is_final=True)
            return

    # All retries exhausted
    _update_webhook_state(hook_id, False, error_msg, flask_app, is_final=True)


# ── Public entry point ─────────────────────────────────────────────────────────

def fire_event(user_id: int, event_type: str, payload: dict, flask_app=None) -> None:
    """
    Fire an outbound event to all active webhooks subscribed to event_type.

    Must be called inside a Flask app context (or pass flask_app explicitly).
    Never raises — all errors are caught and logged.
    Delivery is retried up to 4 times with exponential backoff.
    """
    if event_type not in SUPPORTED_EVENTS:
        _log.debug("fire_event: unsupported event type %s — skipped", event_type)
        return

    try:
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
            t = threading.Thread(
                target=_dispatch_with_retry,
                args=(hook.id, event_type, envelope, flask_app),
                daemon=True,
                name=f"wh-{hook.id}-{delivery_id[:8]}",
            )
            t.start()

    except Exception as exc:
        _log.error("fire_event(%s, %s) failed: %s", user_id, event_type, exc)
