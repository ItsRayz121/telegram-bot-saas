"""Guildizer notification extras: paginated history, unread count, preferences
and Web Push subscription management.

The base in-app endpoints (GET /api/notifications, POST /api/notifications/read)
live in team_api.py; this module ADDS the push + preference + history routes so
there are no route collisions. See web_push.py for the VAPID/keypair note
(Guildizer shares the telegizer.com service worker, so the VAPID keypair must
match Telegizer's).
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import login_required
from models import PushSubscription, User, UserNotification
import web_push

notifications_extra_bp = Blueprint("notifications_extra", __name__)


@notifications_extra_bp.get("/api/notifications/unread-count")
@login_required
def unread_count():
    n = (
        g.db.query(UserNotification)
        .filter(UserNotification.user_id == g.user_id, UserNotification.read.is_(False))
        .count()
    )
    return jsonify(unread=n)


@notifications_extra_bp.get("/api/notifications/history")
@login_required
def history():
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(50, int(request.args.get("per_page", 20)))
    base = g.db.query(UserNotification).filter(UserNotification.user_id == g.user_id)
    total = base.count()
    unread = base.filter(UserNotification.read.is_(False)).count()
    rows = (
        base.order_by(UserNotification.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return jsonify(
        notifications=[n.to_dict() for n in rows],
        total=total, unread=unread, page=page,
    )


# --- preferences --------------------------------------------------------------
@notifications_extra_bp.get("/api/notifications/preferences")
@login_required
def get_preferences():
    user = g.db.get(User, g.user_id)
    if not user:
        return jsonify(error="not_found"), 404
    has_sub = (
        g.db.query(PushSubscription).filter(PushSubscription.user_id == g.user_id).count() > 0
    )
    return jsonify(
        preferences=web_push.get_prefs(user),
        categories=web_push.NOTIF_CATEGORIES,
        push_supported=bool(web_push.vapid_public_key()),
        push_subscribed=has_sub,
    )


@notifications_extra_bp.put("/api/notifications/preferences")
@login_required
def update_preferences():
    user = g.db.get(User, g.user_id)
    if not user:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    prefs = web_push.get_prefs(user)
    if "sound" in body:
        prefs["sound"] = bool(body["sound"])
    if "push" in body:
        prefs["push"] = bool(body["push"])
    if "announcements" in body:
        prefs["announcements"] = bool(body["announcements"])
    cats = body.get("categories")
    if isinstance(cats, dict):
        for c in web_push.NOTIF_CATEGORIES:
            if c in cats:
                prefs["categories"][c] = bool(cats[c])
    user.notification_prefs = prefs
    g.db.commit()
    return jsonify(ok=True, preferences=prefs)


# --- web push subscription ----------------------------------------------------
@notifications_extra_bp.get("/api/notifications/vapid-public-key")
@login_required
def vapid_public_key():
    return jsonify(public_key=web_push.vapid_public_key())


@notifications_extra_bp.post("/api/notifications/subscribe")
@login_required
def subscribe_push():
    body = request.get_json(silent=True) or {}
    endpoint = (body.get("endpoint") or "").strip()
    keys = body.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return jsonify(error="invalid_subscription"), 400

    ua = (request.headers.get("User-Agent") or "")[:300]
    sub = (
        g.db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    )
    if sub:
        sub.user_id = g.user_id
        sub.p256dh = p256dh
        sub.auth = auth
        sub.user_agent = ua
    else:
        g.db.add(PushSubscription(
            user_id=g.user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent=ua,
        ))
    user = g.db.get(User, g.user_id)
    if user:
        prefs = web_push.get_prefs(user)
        prefs["push"] = True
        user.notification_prefs = prefs
    g.db.commit()
    return jsonify(ok=True)


@notifications_extra_bp.post("/api/notifications/unsubscribe")
@login_required
def unsubscribe_push():
    body = request.get_json(silent=True) or {}
    endpoint = (body.get("endpoint") or "").strip()
    q = g.db.query(PushSubscription).filter(PushSubscription.user_id == g.user_id)
    if endpoint:
        q = q.filter(PushSubscription.endpoint == endpoint)
    q.delete(synchronize_session=False)
    user = g.db.get(User, g.user_id)
    if user:
        prefs = web_push.get_prefs(user)
        prefs["push"] = False
        user.notification_prefs = prefs
    g.db.commit()
    return jsonify(ok=True)


# --- announcement banner (top-of-app) -----------------------------------------
@notifications_extra_bp.get("/api/notifications/banner")
@login_required
def active_banner():
    """Newest live banner this user hasn't dismissed / opted out of (or None)."""
    from models import AdminAnnouncement
    user = g.db.get(User, g.user_id)
    if not user or not web_push.get_prefs(user).get("announcements", True):
        return jsonify(banner=None)
    rows = (
        g.db.query(AdminAnnouncement)
        .filter(AdminAnnouncement.active.is_(True))
        .order_by(AdminAnnouncement.created_at.desc())
        .limit(10).all()
    )
    dismissed = set((getattr(user, "notification_prefs", None) or {}).get("dismissed_banners", []))
    for a in rows:
        if "banner" in a.channel_list() and a.id not in dismissed:
            return jsonify(banner=a.to_dict())
    return jsonify(banner=None)


@notifications_extra_bp.post("/api/notifications/banner/<int:ann_id>/dismiss")
@login_required
def dismiss_banner(ann_id: int):
    user = g.db.get(User, g.user_id)
    if not user:
        return jsonify(error="not_found"), 404
    prefs = dict(getattr(user, "notification_prefs", None) or {})
    dismissed = list(prefs.get("dismissed_banners", []))
    if ann_id not in dismissed:
        dismissed.append(ann_id)
        prefs["dismissed_banners"] = dismissed[-50:]
        user.notification_prefs = prefs
        g.db.commit()
    return jsonify(ok=True)
