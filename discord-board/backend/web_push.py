"""Web Push (VAPID) helper for Guildizer — mirrors Telegizer's push layer.

The Guildizer dashboard is served from the telegizer.com origin and therefore
shares ONE service worker / push subscription with Telegizer. For both backends
to push to the same browser subscription, they MUST use the SAME VAPID keypair:
set identical VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY on both Railway services.

Everything degrades gracefully: if VAPID is unset or pywebpush is missing, push
silently no-ops and only the in-app notification bell is used.
"""
from __future__ import annotations

import json
import logging
import os

from models import PushSubscription, User

logger = logging.getLogger(__name__)

# Notification categories (parity with Telegizer). Guildizer notifications are
# created via access.notify() with a kind; we map kind/title → category loosely.
NOTIF_CATEGORIES = ["moderation", "campaigns", "ai", "members", "billing", "system"]

NOTIF_PREF_DEFAULTS = {
    "sound": True,
    "push": False,
    "categories": {c: True for c in NOTIF_CATEGORIES},
}


def get_prefs(user: User) -> dict:
    prefs = dict(NOTIF_PREF_DEFAULTS)
    prefs["categories"] = dict(NOTIF_PREF_DEFAULTS["categories"])
    stored = getattr(user, "notification_prefs", None) or {}
    if isinstance(stored, dict):
        if "sound" in stored:
            prefs["sound"] = bool(stored["sound"])
        if "push" in stored:
            prefs["push"] = bool(stored["push"])
        cats = stored.get("categories")
        if isinstance(cats, dict):
            for c in NOTIF_CATEGORIES:
                if c in cats:
                    prefs["categories"][c] = bool(cats[c])
    return prefs


def vapid_public_key() -> str:
    return os.environ.get("VAPID_PUBLIC_KEY", "").strip()


def _vapid_config():
    priv = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not priv:
        return None
    email = os.environ.get("VAPID_CLAIM_EMAIL", "admin@telegizer.com").strip()
    return priv, {"sub": f"mailto:{email}"}


def push_to_user(db, user_id: int, payload: dict) -> None:
    """Best-effort Web Push fan-out to all of a user's subscriptions.

    No-ops if VAPID is unconfigured or pywebpush is unavailable. Prunes
    subscriptions the push service reports as gone (404/410). Caller need not
    commit — pruning is committed here only when something was removed."""
    cfg = _vapid_config()
    if not cfg:
        return
    try:
        from pywebpush import webpush, WebPushException
    except Exception:
        logger.debug("pywebpush not installed; skipping web push")
        return

    priv, claims = cfg
    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    if not subs:
        return
    data = json.dumps(payload)
    dead = []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub.to_subscription_info(),
                data=data,
                vapid_private_key=priv,
                vapid_claims=dict(claims),
                timeout=10,
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                dead.append(sub.id)
            else:
                logger.warning("guildizer web push failed (uid=%s): %s", user_id, exc)
        except Exception as exc:
            logger.warning("guildizer web push error (uid=%s): %s", user_id, exc)
    if dead:
        try:
            db.query(PushSubscription).filter(PushSubscription.id.in_(dead)).delete(
                synchronize_session=False
            )
            db.commit()
        except Exception:
            db.rollback()


def maybe_push_notification(db, user_id: int, title: str, body: str, kind: str = "info") -> None:
    """Called from access.notify() — fan out a push if the user opted in.

    kind ('info'|'warning'|'error') maps to category 'system'/'moderation' so
    muting moderation alerts stops warning/error pushes. Never raises."""
    try:
        user = db.get(User, user_id)
        if not user:
            return
        prefs = get_prefs(user)
        if not prefs.get("push"):
            return
        category = "moderation" if kind in ("warning", "error") else "system"
        if not prefs["categories"].get(category, True):
            return
        push_to_user(db, user_id, {
            "title": title or "Guildizer",
            "body": body or "",
            "category": category,
            "url": "/guildizer/notifications",
        })
    except Exception as exc:
        logger.debug("guildizer push fan-out skipped: %s", exc)
