"""
Meetings CRUD API.

GET    /api/meetings              list upcoming + recent meetings
POST   /api/meetings              create meeting manually
PUT    /api/meetings/<id>         update meeting (title, time, participants, resources, etc.)
DELETE /api/meetings/<id>         delete meeting
POST   /api/meetings/<id>/complete  mark complete
POST   /api/meetings/<id>/resources add a resource
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, Meeting
from ..middleware.rate_limit import rate_limit

_log = logging.getLogger(__name__)

meetings_bp = Blueprint("meetings", __name__, url_prefix="/api/meetings")


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


@meetings_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_meetings():
    user = _current_user()
    now = datetime.utcnow()
    include_past = request.args.get("include_past", "false").lower() == "true"

    q = Meeting.query.filter_by(owner_user_id=user.id)
    if not include_past:
        q = q.filter(Meeting.scheduled_at >= now, Meeting.is_complete == False)

    meetings = q.order_by(Meeting.scheduled_at.asc()).limit(50).all()
    return jsonify({"meetings": [m.to_dict() for m in meetings]})


@meetings_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_meeting():
    user = _current_user()
    body = request.get_json(silent=True) or {}

    title = (body.get("title") or "").strip()[:300]
    if not title:
        return jsonify({"error": "title required"}), 400

    scheduled_at_raw = body.get("scheduled_at")
    if not scheduled_at_raw:
        return jsonify({"error": "scheduled_at required"}), 400
    try:
        scheduled_at = datetime.fromisoformat(str(scheduled_at_raw).replace("Z", ""))
    except ValueError:
        return jsonify({"error": "Invalid scheduled_at format. Use ISO 8601."}), 400

    priority = body.get("priority", "medium")
    if priority not in ("low", "medium", "high"):
        priority = "medium"

    meeting = Meeting(
        owner_user_id=user.id,
        title=title,
        scheduled_at=scheduled_at,
        timezone=body.get("timezone") or "UTC",
        participants=body.get("participants") or None,
        priority=priority,
        resources=body.get("resources") or None,
        remind_before_minutes=int(body.get("remind_before_minutes") or 15),
        notes=body.get("notes") or None,
    )
    db.session.add(meeting)
    db.session.commit()
    return jsonify({"meeting": meeting.to_dict()}), 201


@meetings_bp.route("/<int:meeting_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_meeting(meeting_id: int):
    user = _current_user()
    meeting = Meeting.query.filter_by(id=meeting_id, owner_user_id=user.id).first_or_404()
    body = request.get_json(silent=True) or {}

    if "title" in body:
        meeting.title = (body["title"] or "").strip()[:300] or meeting.title
    if "scheduled_at" in body:
        try:
            meeting.scheduled_at = datetime.fromisoformat(str(body["scheduled_at"]).replace("Z", ""))
        except ValueError:
            return jsonify({"error": "Invalid scheduled_at format"}), 400
    if "timezone" in body:
        meeting.timezone = body["timezone"]
    if "participants" in body:
        meeting.participants = body["participants"] or None
    if "priority" in body and body["priority"] in ("low", "medium", "high"):
        meeting.priority = body["priority"]
    if "resources" in body:
        meeting.resources = body["resources"] or None
    if "remind_before_minutes" in body:
        meeting.remind_before_minutes = int(body["remind_before_minutes"] or 15)
    if "notes" in body:
        meeting.notes = body["notes"] or None
    if "is_complete" in body:
        meeting.is_complete = bool(body["is_complete"])

    db.session.commit()
    return jsonify({"meeting": meeting.to_dict()})


@meetings_bp.route("/<int:meeting_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def delete_meeting(meeting_id: int):
    user = _current_user()
    meeting = Meeting.query.filter_by(id=meeting_id, owner_user_id=user.id).first_or_404()
    db.session.delete(meeting)
    db.session.commit()
    return jsonify({"ok": True})


@meetings_bp.route("/<int:meeting_id>/complete", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def complete_meeting(meeting_id: int):
    user = _current_user()
    meeting = Meeting.query.filter_by(id=meeting_id, owner_user_id=user.id).first_or_404()
    meeting.is_complete = True
    db.session.commit()
    return jsonify({"meeting": meeting.to_dict()})


@meetings_bp.route("/<int:meeting_id>/resources", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def add_resource(meeting_id: int):
    user = _current_user()
    meeting = Meeting.query.filter_by(id=meeting_id, owner_user_id=user.id).first_or_404()
    body = request.get_json(silent=True) or {}

    value = (body.get("value") or "").strip()
    if not value:
        return jsonify({"error": "value required"}), 400

    rtype = body.get("type") or ("link" if value.startswith("http") else "note")
    label = (body.get("label") or "").strip()[:200]

    resources = list(meeting.resources or [])
    resources.append({"type": rtype, "value": value, "label": label})
    meeting.resources = resources
    db.session.commit()
    return jsonify({"meeting": meeting.to_dict()})
