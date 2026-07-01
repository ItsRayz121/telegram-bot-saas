import json
import logging
import os
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, UserNotification, PushSubscription, TelegramBotStarted
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)
notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


# ── Preference model ──────────────────────────────────────────────────────────
# Categories used to group notification types so users can mute whole classes.
NOTIF_CATEGORIES = ["billing", "security", "moderation", "campaigns", "ai", "members", "system"]

# Categories important enough to also send a private bot DM (money + security +
# account), and only when the user has opted into bot DMs. Everything else stays
# in-app + web push. See create_notification / _maybe_bot_dm.
IMPORTANT_CATEGORIES = {"billing", "security"}

# Coalesce window: repeated notifications of the same type for the same user
# within this window "buzz once, then update quietly" — the newest one updates
# the existing in-app item in place without re-firing push / bot DM. Prevents a
# busy source (e.g. a chatty group) from flooding a user with alerts.
COALESCE_WINDOW_SECONDS = 90

NOTIF_PREF_DEFAULTS = {
    "sound": True,   # play a bell sound in-app when a new notification arrives
    "push": False,   # web push opt-in (off until the user grants permission)
    # Proactive daily Telegram briefing DM — OPT-IN (off until the user enables it).
    # Anti-ban: never send recurring DMs no one asked for; see [[anti_ban_rule]].
    "daily_briefing": False,
    # Private bot DM for important (billing/security) events — OPT-IN, default OFF.
    # Honors the "never DM users unless they asked" rule: nobody gets a proactive
    # bot message until they turn this on. Only reaches users who /started the bot.
    "bot_dm": False,
    # Admin announcements — OPT-OUT (on by default). Turning this off silences
    # broadcast announcements across every channel, but NEVER affects the user's
    # transactional / security notifications above.
    "announcements": True,
    "categories": {c: True for c in NOTIF_CATEGORIES},
}

# Maps a notification `type` → category. Unknown types fall back to "system".
_TYPE_CATEGORY = {
    "payment_confirmed": "billing",
    "plan_expiring": "billing",
    "plan_expiring_soon": "billing",
    "plan_expired": "billing",
    "security_alert": "security",
    "login_alert": "security",
    "new_device": "security",
    "password_changed": "security",
    "email_changed": "security",
    "twofa_changed": "security",
    "account": "security",
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
    for prefix, cat in (
        ("campaign", "campaigns"), ("ai", "ai"), ("mod", "moderation"),
        ("security", "security"), ("account", "security"),
    ):
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
        if "bot_dm" in stored:
            prefs["bot_dm"] = bool(stored["bot_dm"])
        if "announcements" in stored:
            prefs["announcements"] = bool(stored["announcements"])
        cats = stored.get("categories")
        if isinstance(cats, dict):
            for c in NOTIF_CATEGORIES:
                if c in cats:
                    prefs["categories"][c] = bool(cats[c])
    return prefs


def _maybe_bot_dm(user: User, category: str, title: str, message: str, url: str):
    """Best-effort private bot DM for an important notification.

    Anti-ban contract (BINDING, see [[anti_ban_rule]]): only sends when the user
    opted in (`bot_dm`), has a linked Telegram ID, has actually /started the bot,
    and has not blocked it. Delivery is paced + 429-safe via telegram_safe. If the
    bot is blocked we persist `bot_blocked=True` so we never message them again.
    Never raises.
    """
    try:
        if category not in IMPORTANT_CATEGORIES:
            return
        if getattr(user, "bot_blocked", False):
            return
        tg_id = getattr(user, "telegram_user_id", None)
        if not tg_id:
            return
        prefs = get_prefs(user)
        if not prefs.get("bot_dm"):
            return
        if not prefs["categories"].get(category, True):
            return
        if not TelegramBotStarted.has_started(tg_id):
            return
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return
        from ..telegram_safe import send_status
        base = os.environ.get("FRONTEND_URL", "https://telegizer.com").rstrip("/")
        link = url if str(url).startswith("http") else f"{base}{url}"
        text = f"*{title}*\n{message}\n\n{link}"
        ok, blocked = send_status(bot_token, tg_id, text, parse_mode="Markdown",
                                  disable_web_page_preview=True)
        if blocked:
            user.bot_blocked = True
            db.session.commit()
    except Exception as exc:
        logger.debug("bot DM skipped: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass


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

    Fans out across up to three channels (in-app bell → web push → private bot DM
    for important events), respecting user prefs, and coalesces bursts so a busy
    source buzzes the user once then updates quietly. Never raises."""
    category = _category_for(type_)
    try:
        # ── Coalesce bursts: if an unread notification of the same type landed in
        # the last COALESCE_WINDOW seconds, update it in place and DON'T re-buzz.
        cutoff = datetime.utcnow() - timedelta(seconds=COALESCE_WINDOW_SECONDS)
        recent = (
            UserNotification.query
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.type == type_,
                UserNotification.read == False,  # noqa: E712
                UserNotification.created_at >= cutoff,
            )
            .order_by(UserNotification.created_at.desc())
            .first()
        )
        if recent is not None:
            recent.title = title
            recent.message = message
            recent.metadata_ = metadata
            recent.created_at = datetime.utcnow()  # resurface at top, quietly
            db.session.commit()
            return  # quiet update — no second push / bot DM buzz
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

    url = "/notifications"
    if isinstance(metadata, dict) and metadata.get("url"):
        url = metadata["url"]

    user = User.query.get(user_id)
    if not user:
        return
    prefs = get_prefs(user)
    category_on = prefs["categories"].get(category, True)

    # Web push fan-out (respect prefs). Never let push errors break the request.
    try:
        if prefs.get("push") and category_on:
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

    # Private bot DM — important events only, opt-in, /started users only.
    _maybe_bot_dm(user, category, title, message, url)


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
        # Whether a private bot DM can actually be delivered (Telegram linked).
        "telegram_connected": bool(getattr(user, "telegram_user_id", None)),
        "bot_blocked": bool(getattr(user, "bot_blocked", False)),
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
    if "bot_dm" in body:
        prefs["bot_dm"] = bool(body["bot_dm"])
    if "announcements" in body:
        prefs["announcements"] = bool(body["announcements"])
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


# ── Announcement banner (top-of-app) ──────────────────────────────────────────
@notifications_bp.route("/banner", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=120)
def active_banner():
    """Return the newest live banner announcement this user should still see.

    None when: the user opted out of announcements, there is no active banner,
    or they've already dismissed the latest one. Shows once, stays dismissed."""
    user = _get_user()
    if not user:
        return jsonify({"banner": None})
    if not get_prefs(user).get("announcements", True):
        return jsonify({"banner": None})
    from ..models import AdminAnnouncement
    ann = (
        AdminAnnouncement.query
        .filter(AdminAnnouncement.active == True,  # noqa: E712
                AdminAnnouncement.sent == True)     # noqa: E712
        .order_by(AdminAnnouncement.created_at.desc())
        .limit(10).all()
    )
    dismissed = set((getattr(user, "notification_prefs", None) or {}).get("dismissed_banners", []))
    for a in ann:
        if "banner" in a.channel_list() and a.id not in dismissed:
            return jsonify({"banner": a.to_dict()})
    return jsonify({"banner": None})


@notifications_bp.route("/banner/<int:ann_id>/dismiss", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def dismiss_banner(ann_id):
    """Record that this user dismissed a banner so it never reappears for them."""
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    prefs = dict(getattr(user, "notification_prefs", None) or {})
    dismissed = list(prefs.get("dismissed_banners", []))
    if ann_id not in dismissed:
        dismissed.append(ann_id)
        dismissed = dismissed[-50:]  # cap history
        prefs["dismissed_banners"] = dismissed
        user.notification_prefs = prefs
        db.session.commit()
    return jsonify({"ok": True})
