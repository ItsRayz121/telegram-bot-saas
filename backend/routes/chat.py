"""Live chat support — in-house widget ⇄ admin inbox.

Data model (one pair + a child table):
  • SupportConversation — ONE permanent thread per user. A returning user never
    spawns a second conversation; their whole history lives here.
  • SupportSession — an activity episode inside that thread. A new session opens
    when the user starts chatting after the thread went idle, and closes (with a
    reason + ended_at) when the team/user closes it or after IDLE_CLOSE minutes
    of inactivity. Sessions render as dated dividers so past issues stay visible.
  • SupportMessage — a message, tagged with its conversation + session.

Two surfaces:
  • USER side (``/api/support/*``, JWT): the floating dashboard chat widget,
    short-polling ``/api/support/chat/poll?since=<id>`` for new replies.
  • ADMIN side (``/api/admin/support/*``, ``support.manage`` permission): the
    Support inbox — list threads (unread first), read, reply live, open/close.

"Live" is short-polling (no WebSockets) — simplest thing that works on Railway +
Vercel. Idle auto-close is done LAZILY on access (no scheduler dependency): any
read/list sweeps stale open sessions shut. Notifications reuse the existing
in-app + web-push helper, NOT the billing/security bot-DM tier.

Message bodies are stored + returned as PLAIN TEXT — render as text, never HTML.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from ..models import db, User, SupportConversation, SupportSession, SupportMessage
from ..middleware.rate_limit import rate_limit
from .admin import require_permission
from .notifications import create_notification
from .. import admin_rbac as rbac
from ..config import Config

logger = logging.getLogger(__name__)
support_bp = Blueprint("support", __name__)

MAX_MESSAGE_LEN = 4000
PREVIEW_LEN = 180
VALID_PRODUCTS = ("telegizer", "echo", "guildizer")
DEFAULT_PRODUCT = "telegizer"
# A thread with no activity for this long auto-closes its current episode. The
# next message the user sends opens a fresh, separately-dated session.
IDLE_CLOSE_SECONDS = 600  # 10 minutes


def _get_user():
    return User.query.get(int(get_jwt_identity()))


def _clean_body(raw) -> str:
    if not isinstance(raw, str):
        return ""
    body = raw.strip()
    if len(body) > MAX_MESSAGE_LEN:
        body = body[:MAX_MESSAGE_LEN]
    return body


def _clean_product(raw) -> str:
    return raw if raw in VALID_PRODUCTS else DEFAULT_PRODUCT


def _latest_session_product(conv: SupportConversation):
    """Product of the most recent prior episode, so an admin-reopened session
    inherits the topic instead of showing blank."""
    prev = (
        SupportSession.query
        .filter_by(conversation_id=conv.id)
        .order_by(SupportSession.id.desc())
        .first()
    )
    return prev.product if prev else None


def _conversation_for(user_id: int):
    """The user's single permanent conversation, or None if they've never chatted."""
    return SupportConversation.query.filter_by(user_id=user_id).first()


def _open_session(conv: SupportConversation):
    return (
        SupportSession.query
        .filter_by(conversation_id=conv.id, status="open")
        .order_by(SupportSession.id.desc())
        .first()
    )


def _sweep_idle(conv: SupportConversation) -> bool:
    """Lazily close the open session if it's been idle >= IDLE_CLOSE_SECONDS.

    IMPORTANT: an UNANSWERED question never auto-closes. If the most recent
    message in the thread is from the user, the ticket is still awaiting the
    team, so we leave it open indefinitely (it only closes when an admin replies
    and the user then goes quiet, or when an admin closes it manually). This
    guarantees a user's unanswered question is never quietly buried.

    ``ended_at`` is set to the last activity (when the chat really went quiet),
    not "now". Never touches unread flags. Returns True if it closed a session.
    """
    if not conv or conv.status != "open":
        return False
    sess = _open_session(conv)
    if not sess:
        conv.status = "closed"   # normalise drift
        db.session.commit()
        return False
    last = (
        SupportMessage.query
        .filter_by(conversation_id=conv.id)
        .order_by(SupportMessage.id.desc())
        .first()
    )
    # Unanswered → keep open. (last is None only for a reopened-but-unused
    # session, which is safe to let idle-close.)
    if last and last.author == "user":
        return False
    ref = conv.last_message_at or sess.started_at
    if ref and (datetime.utcnow() - ref).total_seconds() >= IDLE_CLOSE_SECONDS:
        sess.status = "closed"
        sess.ended_at = ref
        sess.close_reason = "auto_idle"
        conv.status = "closed"
        db.session.commit()
        return True
    return False


def _ensure_open_session(conv: SupportConversation) -> SupportSession:
    """Return the conversation's open session, starting a new episode if the last
    one has closed/gone idle."""
    _sweep_idle(conv)
    sess = _open_session(conv)
    if sess is None:
        sess = SupportSession(conversation_id=conv.id, status="open")
        db.session.add(sess)
        conv.status = "open"
        db.session.flush()  # populate sess.id for the message FK
    return sess


def _sessions_for(conv: SupportConversation):
    return (
        SupportSession.query
        .filter_by(conversation_id=conv.id)
        .order_by(SupportSession.started_at.asc(), SupportSession.id.asc())
        .all()
    )


def _messages_for(conv: SupportConversation, since: int = 0):
    q = SupportMessage.query.filter_by(conversation_id=conv.id)
    if since:
        q = q.filter(SupportMessage.id > since)
    return q.order_by(SupportMessage.id.asc()).all()


def _support_admin_user_ids() -> list[int]:
    """User ids to alert on a new support message: anyone whose role grants
    ``support.manage`` plus bootstrap super-admins. Best-effort; never raises."""
    ids: set[int] = set()
    try:
        for u in User.query.filter(User.admin_role.isnot(None)).all():
            if rbac.has_permission(u, rbac.P_SUPPORT_MANAGE):
                ids.add(u.id)
        emails = {e.lower() for e in (Config.ADMIN_EMAILS or set())}
        if emails:
            for u in User.query.filter(db.func.lower(User.email).in_(emails)).all():
                ids.add(u.id)
    except Exception as exc:
        logger.debug("support admin lookup failed: %s", exc)
    return list(ids)


def _notify_support_admins(conv: SupportConversation, user: User, preview: str):
    try:
        name = getattr(user, "full_name", None) or getattr(user, "telegram_username", None) or "A user"
        url = f"/admin/compliance/support?c={conv.id}"
        for aid in _support_admin_user_ids():
            if aid == user.id:
                continue
            create_notification(
                aid, "support_message", "New support message",
                f"{name}: {preview}", {"url": url, "conversation_id": conv.id},
            )
    except Exception as exc:
        logger.debug("notify support admins skipped: %s", exc)


def _thread_payload(conv: SupportConversation, *, since: int = 0, with_user: bool = False) -> dict:
    return {
        "conversation": conv.to_dict(with_user=with_user),
        "messages": [m.to_dict() for m in _messages_for(conv, since)],
        "sessions": [s.to_dict() for s in _sessions_for(conv)],
    }


# ── USER (widget) ────────────────────────────────────────────────────────────

@support_bp.route("/api/support/chat", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def get_my_chat():
    """The user's full permanent thread + its sessions. Opening it clears the
    user's unread flag."""
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    conv = _conversation_for(user.id)
    if conv is None:
        return jsonify({"conversation": None, "messages": [], "sessions": []})
    _sweep_idle(conv)
    if conv.unread_user:
        conv.unread_user = False
        db.session.commit()
    return jsonify(_thread_payload(conv))


@support_bp.route("/api/support/chat/poll", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=120)
def poll_my_chat():
    """Messages newer than ``since`` (+ session metadata so the client can draw
    dividers for freshly-started/closed episodes)."""
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    conv = _conversation_for(user.id)
    if conv is None:
        return jsonify({"conversation": None, "messages": [], "sessions": []})
    _sweep_idle(conv)
    if conv.unread_user:
        conv.unread_user = False
        db.session.commit()
    since = request.args.get("since", 0, type=int)
    return jsonify(_thread_payload(conv, since=since))


@support_bp.route("/api/support/chat", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def post_my_message():
    """Append a user message, opening a fresh episode if the thread was idle, and
    alert the team."""
    user = _get_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    payload = request.get_json(silent=True) or {}
    body = _clean_body(payload.get("message"))
    if not body:
        return jsonify({"error": "Message is empty"}), 400
    product = _clean_product(payload.get("product"))

    now = datetime.utcnow()
    conv = _conversation_for(user.id)
    if conv is None:
        conv = SupportConversation(user_id=user.id, status="open")
        db.session.add(conv)
        try:
            db.session.flush()
        except IntegrityError:
            # Rare double-submit / two-tab race: another request just created the
            # user's (unique) conversation. Roll back and reuse the existing one.
            db.session.rollback()
            conv = _conversation_for(user.id)
            if conv is None:  # extremely unlikely — recreate best-effort
                conv = SupportConversation(user_id=user.id, status="open")
                db.session.add(conv)
                db.session.flush()
    sess = _ensure_open_session(conv)
    # Tag the episode with the chosen product on its first message; leave an
    # already-tagged (mid-conversation) session untouched.
    if sess.product is None:
        sess.product = product
    conv.last_product = sess.product

    # created_at is set here explicitly: the column's default only materialises at
    # flush, so reading msg.created_at before flush would yield None and write NULL
    # into conv.last_message_at (a NOT NULL column).
    msg = SupportMessage(conversation_id=conv.id, session_id=sess.id, author="user", body=body, created_at=now)
    db.session.add(msg)
    conv.last_message_at = now
    conv.last_message_preview = body[:PREVIEW_LEN]
    conv.unread_admin = True
    db.session.commit()

    _notify_support_admins(conv, user, body[:PREVIEW_LEN])
    return jsonify({
        "message": msg.to_dict(),
        "conversation": conv.to_dict(),
        "session": sess.to_dict(),
    }), 201


# ── ADMIN (inbox) ────────────────────────────────────────────────────────────

@support_bp.route("/api/admin/support/unread-count", methods=["GET"])
@require_permission(rbac.P_SUPPORT_MANAGE)
@rate_limit(requests_per_minute=120)
def admin_unread_count():
    """Threads awaiting a reply — drives the nav badge. Counts unread regardless
    of whether the episode auto-closed, so nothing unanswered is missed."""
    n = SupportConversation.query.filter_by(unread_admin=True).count()
    return jsonify({"unread": n})


@support_bp.route("/api/admin/support/conversations", methods=["GET"])
@require_permission(rbac.P_SUPPORT_MANAGE)
@rate_limit(requests_per_minute=60)
def admin_list_conversations():
    """List threads, unread first then most-recent.

    Filters:
      • open   → an episode is live OR there's an unanswered message (so a
                 question that auto-closed while idle still shows here)
      • closed → idle AND already seen by the team
      • all    → everything
    """
    status = (request.args.get("status", "open") or "open").lower()
    search = (request.args.get("search", "") or "").strip()
    product = (request.args.get("product", "") or "").lower()

    # Sweep only episodes actually idle past the threshold (active/recent ones
    # can't close yet), so a busy inbox poll stays cheap.
    cutoff = datetime.utcnow() - timedelta(seconds=IDLE_CLOSE_SECONDS)
    for c in (SupportConversation.query
              .filter(SupportConversation.status == "open",
                      SupportConversation.last_message_at < cutoff)
              .all()):
        _sweep_idle(c)

    q = SupportConversation.query
    if status == "open":
        q = q.filter(or_(SupportConversation.status == "open",
                         SupportConversation.unread_admin == True))  # noqa: E712
    elif status == "closed":
        q = q.filter(SupportConversation.status == "closed",
                     SupportConversation.unread_admin == False)  # noqa: E712
    if product in VALID_PRODUCTS:
        q = q.filter(SupportConversation.last_product == product)
    if search:
        like = f"%{search}%"
        q = q.join(User, User.id == SupportConversation.user_id).filter(
            or_(User.email.ilike(like), User.full_name.ilike(like),
                User.telegram_username.ilike(like))
        )
    q = q.order_by(
        SupportConversation.unread_admin.desc(),
        SupportConversation.last_message_at.desc(),
    )
    convs = q.limit(200).all()
    return jsonify({"conversations": [c.to_dict(with_user=True) for c in convs]})


@support_bp.route("/api/admin/support/conversations/<int:cid>", methods=["GET"])
@require_permission(rbac.P_SUPPORT_MANAGE)
@rate_limit(requests_per_minute=120)
def admin_get_thread(cid):
    """Full thread (all sessions). Opening it marks the thread as seen."""
    conv = SupportConversation.query.get(cid)
    if not conv:
        return jsonify({"error": "Not found"}), 404
    _sweep_idle(conv)
    if conv.unread_admin:
        conv.unread_admin = False
        db.session.commit()
    return jsonify(_thread_payload(conv, with_user=True))


@support_bp.route("/api/admin/support/conversations/<int:cid>/reply", methods=["POST"])
@require_permission(rbac.P_SUPPORT_MANAGE)
@rate_limit(requests_per_minute=60)
def admin_reply(cid):
    """Post an admin reply (reopening a fresh episode if the thread was idle) and
    notify the user."""
    admin = _get_user()
    conv = SupportConversation.query.get(cid)
    if not conv:
        return jsonify({"error": "Not found"}), 404
    body = _clean_body((request.get_json(silent=True) or {}).get("message"))
    if not body:
        return jsonify({"error": "Message is empty"}), 400

    now = datetime.utcnow()
    inherited = _latest_session_product(conv)
    sess = _ensure_open_session(conv)
    # A reopened (fresh) episode inherits the previous topic so it isn't blank.
    if sess.product is None:
        sess.product = inherited or conv.last_product
    if sess.product:
        conv.last_product = sess.product
    admin_name = (getattr(admin, "full_name", None) or "Support") if admin else "Support"
    msg = SupportMessage(
        conversation_id=conv.id, session_id=sess.id, author="admin",
        admin_id=getattr(admin, "id", None), admin_name=admin_name, body=body, created_at=now,
    )
    db.session.add(msg)
    conv.last_message_at = now
    conv.last_message_preview = body[:PREVIEW_LEN]
    conv.unread_user = True
    db.session.commit()

    try:
        create_notification(
            conv.user_id, "support_reply", "Support replied", body[:PREVIEW_LEN],
            {"url": "/dashboard", "open_support": True, "conversation_id": conv.id},
        )
    except Exception as exc:
        logger.debug("support reply notify skipped: %s", exc)

    return jsonify({
        "message": msg.to_dict(),
        "conversation": conv.to_dict(with_user=True),
        "session": sess.to_dict(),
    }), 201


@support_bp.route("/api/admin/support/conversations/<int:cid>/status", methods=["POST"])
@require_permission(rbac.P_SUPPORT_MANAGE)
@rate_limit(requests_per_minute=60)
def admin_set_status(cid):
    """Close the current episode, or reopen a fresh one."""
    conv = SupportConversation.query.get(cid)
    if not conv:
        return jsonify({"error": "Not found"}), 404
    status = ((request.get_json(silent=True) or {}).get("status") or "").lower()
    if status not in ("open", "closed"):
        return jsonify({"error": "Invalid status"}), 400

    if status == "closed":
        sess = _open_session(conv)
        if sess:
            sess.status = "closed"
            sess.ended_at = conv.last_message_at or datetime.utcnow()
            sess.close_reason = "admin"
        conv.status = "closed"
        conv.unread_admin = False
    else:
        _ensure_open_session(conv)
        conv.status = "open"
    db.session.commit()
    return jsonify({"conversation": conv.to_dict(with_user=True), "sessions": [s.to_dict() for s in _sessions_for(conv)]})
