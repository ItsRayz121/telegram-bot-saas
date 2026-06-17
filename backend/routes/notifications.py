import json
import logging
import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, UserNotification, PushSubscription
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)
notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


# ── Preference model ──────────────────────────────────────────────────────────
# Categories used to group notification types so users can mute whole classes.
NOTIF_CATEGORIES = ["billing", "moderation", "campaigns", "ai", "members", "system"]

NOTIF_PREF_DEFAULTS = {
    "sound": True,   # play a bell sound in-app when a new notification arrives
    "push": False,   # web push opt-in (off until the user grants permission)
    # Proactive daily Telegram briefing DM — OPT-IN (off until the user enables it).
    # Anti-ban: never send recurring DMs no one asked for; see [[anti_ban_rule]].
    "daily_briefing": False,
    "categories": {c: True for c in NOTIF_CATEGORIES},
}

# Maps a notification `type` → category. Unknown types fall back to "system".
_TYPE_CATEGORY = {
    "payment_confirmed": "billing",
    "plan_expiring": "billing",
    "plan_expiring_soon": "billing",
    "plan_expired": "billing",
    "raid_alert": "moderation",
    "lockdown": "moderation",
    "mod_action": "moderation",
    "report": "moderation",
    "protection_alert": "moderation",
    "campaign": "campaigns",
    "campaign_milestone": "campaigns",
    "campaign_submission": "campaigns",
    "ai_error": "ai",
    "ai_activity": "ai",
    "referral": "members",
    "new_member": "members",
}


def _category_for(type_: str) -> str:
    if type_ in _TYPE_CATEGORY:
        return _TYPE_CATEGORY[type_]
    # Prefix fallback: "campaign_x" → campaigns, "ai_x" → ai, "mod_x" → moderation
    for prefix, cat in (("campaign", "campaigns"), ("ai", "ai"), ("mod", "moderation")):
        if type_.startswith(prefix):
            return cat
    return "system"


def get_prefs(user: User) -> dict:
    """Return the user's notification prefs merged over defaults (deep)."""
    prefs = dict(NOTIF_PREF_DEFAULTS)
    prefs["categories"] = dict(NOTIF_PREF_DEFAULTS["categories"])
    stored = getattr(user, "notification_prefs", None) or {}
    if isinstance(stored, dict):
        if "sound" in stored:
            prefs["sound"] = bool(stored["sound"])
        if "push" in stored:
            prefs["push"] = bool(stored["push"])
        if "daily_briefing" in stored:
            prefs["daily_briefing"] = bool(stored["daily_briefing"])
        cats = stored.get("categories")
        if isinstance(cats, dict):
            for c in NOTIF_CATEGORIES:
                if c in cats:
                    prefs["categories"][c] = bool(cats[c])
    return prefs


def _get_user():
    return User.query.get(int(get_jwt_identity()))


# ── VAPID / Web Push config ─────────────────────────────────────────────────
def _vapid_config():
    """Return (private_key, claims) or None if Web Push is not configured.

    Set VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY and (optionally) VAPID_CLAIM_EMAIL
    in the environment to enable OS-level push. When unset, push silently
    no-ops and only the in-app notification center is used."""
    priv = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not priv:
        return None
    email = os.environ.get("VAPID_CLAIM_EMAIL", "fazalelahi5577@gmail.com").strip()
    return priv, {"sub": f"mailto:{email}"}


def vapid_public_key() -> str:
    return os.environ.get("VAPID_PUBLIC_KEY", "").strip()


def push_to_user(user_id: int, payload: dict):
    """Best-effort Web Push fan-out to all of a user's subscriptions.

    Silently no-ops if VAPID is unconfigured or pywebpush is unavailable.
    Prunes subscriptions that the push service reports as gone (404/410)."""
    cfg = _vapid_config()
    if not cfg:
        return
    try:
        from pywebpush import webpush, WebPushException
    except Exception:
        logger.debug("pywebpush not installed; skipping web push")
        return

    priv, claims = cfg
    subs = PushSubscription.query.filter_by(user_id=user_id).all()
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
                logger.warning("web push failed (uid=%s): %s", user_id, exc)
        except Exception as exc:
            logger.warning("web push error (uid=%s): %s", user_id, exc)
    if dead:
        try:
            PushSubscription.query.filter(PushSubscription.id.in_(dead)).delete(
                synchronize_session=False
            )
            db.session.commit()
        except Exception:
            db.session.rollback()


def create_notification(user_id: int, type_: str, title: str, message: str, metadata=None):
    """Helper called from other routes to create in-app notifications.

    Also fans out a Web Push (best effort) when the user has opted in and the
    notification's category is not muted."""
    try:
        n = UserNotification(
            user_id=user_id, type=type_, title=title, message=message,
            metadata_=metadata,
        )
        db.session.add(n)
        db.session.commit()
    except Exception as exc:
        logger.warning("create_notification failed: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass
        return

    # Web push fan-out (respect prefs). Never let push errors break the request.
    try:
        user = User.query.get(user_id)
        if not user:
            return
        prefs = get_prefs(user)
        if not prefs.get("push"):
            return
        category = _category_for(type_)
        if not prefs["categories"].get(category, True):
            return
        url = "/notifications"
        if isinstance(metadata, dict) and metadata.get("url"):
            url = metadata["url"]
        push_to_user(user_id, {
            "title": title,
            "body": message,
            "type": type_,
            "category": category,
            "url": url,
            "id": n.id,
        })
    except Exception as exc:
        logger.debug("push fan-out skipped: %s", exc)


@notifications_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_notifications():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(50, int(request.args.get("per_page", 20)))
    q = UserNotification.query.filter_by(user_id=user.id).order_by(
        UserNotification.created_at.desc()
    )
    total = q.count()
    unread = UserNotification.query.filter_by(user_id=user.id, read=False).count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "notifications": [n.to_dict() for n in items],
        "unread": unread,
        "total": total,
        "page": page,
    })


@notifications_bp.route("/unread-count", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=120)
def unread_count():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    count = UserNotification.query.filter_by(user_id=user.id, read=False).count()
    return jsonify({"unread": count})


@notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def mark_read(notif_id):
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    n = UserNotification.query.filter_by(id=notif_id, user_id=user.id).first()
    if not n:
        return jsonify({"error": "Notification not found"}), 404
    n.read = True
    db.session.commit()
    return jsonify({"ok": True})


@notifications_bp.route("/read-all", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def mark_all_read():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    UserNotification.query.filter_by(user_id=user.id, read=False).update({"read": True})
    db.session.commit()
    return jsonify({"ok": True})


# ── Preferences ───────────────────────────────────────────────────────────────
@notifications_bp.route("/preferences", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_preferences():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    has_sub = PushSubscription.query.filter_by(user_id=user.id).count() > 0
    return jsonify({
        "preferences": get_prefs(user),
        "categories": NOTIF_CATEGORIES,
        "push_supported": bool(vapid_public_key()),
        "push_subscribed": has_sub,
    })


@notifications_bp.route("/preferences", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_preferences():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = request.get_json(silent=True) or {}
    prefs = get_prefs(user)
    if "sound" in body:
        prefs["sound"] = bool(body["sound"])
    if "push" in body:
        prefs["push"] = bool(body["push"])
    if "daily_briefing" in body:
        prefs["daily_briefing"] = bool(body["daily_briefing"])
    cats = body.get("categories")
    if isinstance(cats, dict):
        for c in NOTIF_CATEGORIES:
            if c in cats:
                prefs["categories"][c] = bool(cats[c])
    user.notification_prefs = prefs
    db.session.commit()
    return jsonify({"ok": True, "preferences": prefs})


# ── Web Push subscription management ──────────────────────────────────────────
@notifications_bp.route("/vapid-public-key", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_vapid_public_key():
    return jsonify({"public_key": vapid_public_key()})


@notifications_bp.route("/subscribe", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def subscribe_push():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = request.get_json(silent=True) or {}
    endpoint = (body.get("endpoint") or "").strip()
    keys = body.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "Invalid subscription"}), 400

    ua = (request.headers.get("User-Agent") or "")[:300]
    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if sub:
        # Re-subscribe / re-assign to this user (endpoint is globally unique).
        sub.user_id = user.id
        sub.p256dh = p256dh
        sub.auth = auth
        sub.user_agent = ua
    else:
        sub = PushSubscription(
            user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent=ua,
        )
        db.session.add(sub)
    # Opt in to push when a subscription is registered.
    prefs = get_prefs(user)
    prefs["push"] = True
    user.notification_prefs = prefs
    db.session.commit()
    return jsonify({"ok": True})


@notifications_bp.route("/unsubscribe", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def unsubscribe_push():
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = request.get_json(silent=True) or {}
    endpoint = (body.get("endpoint") or "").strip()
    if endpoint:
        PushSubscription.query.filter_by(user_id=user.id, endpoint=endpoint).delete()
    else:
        PushSubscription.query.filter_by(user_id=user.id).delete()
    prefs = get_prefs(user)
    prefs["push"] = False
    user.notification_prefs = prefs
    db.session.commit()
    return jsonify({"ok": True})
