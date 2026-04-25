import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, UserNotification
from ..middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)
notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


def _get_user():
    return User.query.get(int(get_jwt_identity()))


def create_notification(user_id: int, type_: str, title: str, message: str, metadata=None):
    """Helper called from other routes to create in-app notifications."""
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
