"""
Workspace API — user-scoped features that span all groups.

Smart Links  POST/GET/PUT/DELETE /api/workspace/smart-links
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, AutoResponse, TelegramGroup
from ..middleware.rate_limit import rate_limit

workspace_bp = Blueprint("workspace", __name__, url_prefix="/api/workspace")

_VALID_SCOPES = {"group", "user"}
_VALID_MATCH = {"contains", "exact", "starts_with"}


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


def _owns_link(user: User, ar: AutoResponse) -> bool:
    """Return True when the user is authorised to manage this smart link."""
    if ar.owner_user_id == user.id:
        return True
    # Also allow if the link is group-scoped and user owns that group
    if ar.telegram_group_id:
        g = TelegramGroup.query.filter_by(
            telegram_group_id=ar.telegram_group_id,
            owner_user_id=user.id,
            is_disabled=False,
        ).first()
        return g is not None
    return False


# ── List ─────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_smart_links():
    user = _current_user()

    # All smart links owned by this user (global scope)
    owned = AutoResponse.query.filter_by(
        owner_user_id=user.id,
        response_type="smart_link",
    ).order_by(AutoResponse.created_at.desc()).all()

    # Smart links scoped to groups the user owns (in case they were created per-group)
    group_ids = [g.telegram_group_id for g in
                 TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()]
    group_links = []
    if group_ids:
        group_links = AutoResponse.query.filter(
            AutoResponse.telegram_group_id.in_(group_ids),
            AutoResponse.response_type == "smart_link",
            AutoResponse.owner_user_id.is_(None),  # legacy rows without owner set
        ).order_by(AutoResponse.created_at.desc()).all()

    seen = {ar.id for ar in owned}
    combined = list(owned) + [ar for ar in group_links if ar.id not in seen]

    return jsonify({"smart_links": [ar.to_dict() for ar in combined]})


# ── Create ────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def create_smart_link():
    user = _current_user()
    data = request.get_json() or {}

    label = (data.get("link_label") or "").strip()
    triggers_raw = (data.get("trigger_text") or "").strip()
    url = (data.get("link_url") or "").strip()
    response_text = (data.get("response_text") or url or "").strip()
    match_type = data.get("match_type", "contains")
    scope = data.get("scope", "user")
    telegram_group_id = data.get("telegram_group_id") or None
    is_case_sensitive = bool(data.get("is_case_sensitive", False))

    if not label:
        return jsonify({"error": "link_label is required"}), 400
    if not triggers_raw:
        return jsonify({"error": "trigger_text is required"}), 400
    if not response_text:
        return jsonify({"error": "link_url or response_text is required"}), 400
    if match_type not in _VALID_MATCH:
        return jsonify({"error": f"match_type must be one of {sorted(_VALID_MATCH)}"}), 400
    if scope not in _VALID_SCOPES:
        return jsonify({"error": f"scope must be one of {sorted(_VALID_SCOPES)}"}), 400

    # Validate group ownership when group-scoped
    if scope == "group" and telegram_group_id:
        g = TelegramGroup.query.filter_by(
            telegram_group_id=telegram_group_id,
            owner_user_id=user.id,
            is_disabled=False,
        ).first()
        if not g:
            return jsonify({"error": "Group not found or not owned by you"}), 404
    else:
        telegram_group_id = None  # user-scoped links are not tied to a group

    ar = AutoResponse(
        owner_user_id=user.id,
        response_type="smart_link",
        link_label=label[:100],
        link_url=url[:2000] if url else None,
        trigger_text=triggers_raw[:500],
        response_text=response_text,
        match_type=match_type,
        is_case_sensitive=is_case_sensitive,
        is_enabled=True,
        scope=scope,
        telegram_group_id=telegram_group_id,
    )
    db.session.add(ar)
    db.session.commit()
    return jsonify({"smart_link": ar.to_dict()}), 201


# ── Update ────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links/<int:link_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_smart_link(link_id):
    user = _current_user()
    ar = AutoResponse.query.get_or_404(link_id)
    if not _owns_link(user, ar) or ar.response_type != "smart_link":
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    if "link_label" in data:
        ar.link_label = (data["link_label"] or "").strip()[:100]
    if "trigger_text" in data:
        ar.trigger_text = (data["trigger_text"] or "").strip()[:500]
    if "link_url" in data:
        ar.link_url = (data["link_url"] or "").strip()[:2000] or None
    if "response_text" in data:
        ar.response_text = (data["response_text"] or ar.link_url or "").strip()
    if "match_type" in data and data["match_type"] in _VALID_MATCH:
        ar.match_type = data["match_type"]
    if "is_case_sensitive" in data:
        ar.is_case_sensitive = bool(data["is_case_sensitive"])
    if "is_enabled" in data:
        ar.is_enabled = bool(data["is_enabled"])
    if "scope" in data and data["scope"] in _VALID_SCOPES:
        ar.scope = data["scope"]

    db.session.commit()
    return jsonify({"smart_link": ar.to_dict()})


# ── Delete ────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links/<int:link_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_smart_link(link_id):
    user = _current_user()
    ar = AutoResponse.query.get_or_404(link_id)
    if not _owns_link(user, ar) or ar.response_type != "smart_link":
        return jsonify({"error": "Not found"}), 404
    db.session.delete(ar)
    db.session.commit()
    return jsonify({"deleted": True})


# ── Toggle ────────────────────────────────────────────────────────────────────

@workspace_bp.route("/smart-links/<int:link_id>/toggle", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def toggle_smart_link(link_id):
    user = _current_user()
    ar = AutoResponse.query.get_or_404(link_id)
    if not _owns_link(user, ar) or ar.response_type != "smart_link":
        return jsonify({"error": "Not found"}), 404
    ar.is_enabled = not ar.is_enabled
    db.session.commit()
    return jsonify({"smart_link": ar.to_dict()})
