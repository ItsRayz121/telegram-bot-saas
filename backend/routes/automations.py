"""
Workspace Automations — simple trigger → condition → action workflows.

Workflow   GET/POST/PUT/DELETE  /api/automations/workflows
           POST                 /api/automations/workflows/:id/toggle
Executions GET                  /api/automations/workflows/:id/executions
Templates  GET                  /api/automations/templates
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, User, TelegramGroup, AutomationWorkflow, AutomationExecution
from ..middleware.rate_limit import rate_limit

automations_bp = Blueprint("automations", __name__, url_prefix="/api/automations")
_log = logging.getLogger(__name__)

_MAX_WORKFLOWS_FREE = 3
_MAX_WORKFLOWS_PRO = 25

BUILT_IN_TEMPLATES = [
    {
        "id": "welcome_dm",
        "name": "Welcome DM",
        "description": "Send a private DM to every new member who joins.",
        "trigger": {"type": "member_joined"},
        "conditions": [],
        "actions": [{"type": "send_dm", "params": {"message": "👋 Welcome to our community!"}}],
    },
    {
        "id": "keyword_notify",
        "name": "Keyword → Admin DM",
        "description": "Get a DM when a message contains a specific keyword.",
        "trigger": {"type": "message_received"},
        "conditions": [{"type": "message_contains", "params": {"keyword": "urgent"}}],
        "actions": [{"type": "notify_admin_dm", "params": {"message": "🚨 Keyword 'urgent' detected in your group."}}],
    },
    {
        "id": "auto_forward_keyword",
        "name": "Keyword → Forward",
        "description": "Forward messages matching a keyword to another chat.",
        "trigger": {"type": "message_received"},
        "conditions": [{"type": "message_contains", "params": {"keyword": ""}}],
        "actions": [{"type": "forward_message", "params": {"destination_id": ""}}],
    },
    {
        "id": "new_member_reminder",
        "name": "New member → Reminder",
        "description": "Create a reminder to follow up with every new member after 24 hours.",
        "trigger": {"type": "member_joined"},
        "conditions": [],
        "actions": [{"type": "create_reminder", "params": {"text": "Follow up with new member", "delay_minutes": 1440}}],
    },
    {
        "id": "scheduled_announcement",
        "name": "Scheduled Announcement",
        "description": "Send a message to a group at a fixed time every day.",
        "trigger": {"type": "scheduled", "params": {"cron": "0 9 * * *"}},
        "conditions": [],
        "actions": [{"type": "send_group_message", "params": {"message": "Good morning! 🌅"}}],
    },
    {
        "id": "spam_notify",
        "name": "Spam Detected → Admin DM",
        "description": "Get a DM when AutoMod bans a user.",
        "trigger": {"type": "member_banned"},
        "conditions": [],
        "actions": [{"type": "notify_admin_dm", "params": {"message": "🚫 A user was banned by AutoMod."}}],
    },
]


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


def _owns_workflow(user: User, wf: AutomationWorkflow) -> bool:
    return wf.owner_user_id == user.id


# ── Templates ─────────────────────────────────────────────────────────────────

@automations_bp.route("/templates", methods=["GET"])
@jwt_required()
def list_templates():
    return jsonify({"templates": BUILT_IN_TEMPLATES})


# ── List workflows ────────────────────────────────────────────────────────────

@automations_bp.route("/workflows", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_workflows():
    user = _current_user()
    workflows = AutomationWorkflow.query.filter_by(owner_user_id=user.id)\
        .order_by(AutomationWorkflow.created_at.desc()).all()
    return jsonify({"workflows": [w.to_dict() for w in workflows]})


# ── Create workflow ───────────────────────────────────────────────────────────

@automations_bp.route("/workflows", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def create_workflow():
    user = _current_user()
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    trigger = data.get("trigger") or {}
    conditions = data.get("conditions") or []
    actions = data.get("actions") or []
    source_group_id = data.get("source_group_id") or None

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not trigger.get("type"):
        return jsonify({"error": "trigger.type is required"}), 400
    if not actions:
        return jsonify({"error": "At least one action is required"}), 400

    # Validate source group ownership if provided
    if source_group_id:
        g = TelegramGroup.query.filter_by(
            telegram_group_id=source_group_id, owner_user_id=user.id, is_disabled=False
        ).first()
        if not g:
            return jsonify({"error": "Source group not found or not owned by you"}), 404

    # Tier limits
    existing = AutomationWorkflow.query.filter_by(owner_user_id=user.id).count()
    limit = _MAX_WORKFLOWS_PRO if user.subscription_tier in ("pro", "enterprise") else _MAX_WORKFLOWS_FREE
    if existing >= limit:
        return jsonify({
            "error": f"Workflow limit reached ({limit} workflows). Upgrade to create more.",
            "code": "LIMIT_REACHED",
        }), 403

    wf = AutomationWorkflow(
        owner_user_id=user.id,
        name=name[:200],
        source_group_id=source_group_id,
        trigger=trigger,
        conditions=conditions,
        actions=actions,
        is_active=True,
    )
    db.session.add(wf)
    db.session.commit()
    return jsonify({"workflow": wf.to_dict()}), 201


# ── Update workflow ───────────────────────────────────────────────────────────

@automations_bp.route("/workflows/<int:wf_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_workflow(wf_id):
    user = _current_user()
    wf = AutomationWorkflow.query.get_or_404(wf_id)
    if not _owns_workflow(user, wf):
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    if "name" in data:
        wf.name = (data["name"] or "").strip()[:200]
    if "trigger" in data:
        wf.trigger = data["trigger"]
    if "conditions" in data:
        wf.conditions = data["conditions"]
    if "actions" in data:
        wf.actions = data["actions"]
    if "is_active" in data:
        wf.is_active = bool(data["is_active"])
    if "source_group_id" in data:
        wf.source_group_id = data["source_group_id"] or None

    db.session.commit()
    return jsonify({"workflow": wf.to_dict()})


# ── Delete workflow ───────────────────────────────────────────────────────────

@automations_bp.route("/workflows/<int:wf_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_workflow(wf_id):
    user = _current_user()
    wf = AutomationWorkflow.query.get_or_404(wf_id)
    if not _owns_workflow(user, wf):
        return jsonify({"error": "Not found"}), 404
    db.session.delete(wf)
    db.session.commit()
    return jsonify({"ok": True})


# ── Toggle active ─────────────────────────────────────────────────────────────

@automations_bp.route("/workflows/<int:wf_id>/toggle", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def toggle_workflow(wf_id):
    user = _current_user()
    wf = AutomationWorkflow.query.get_or_404(wf_id)
    if not _owns_workflow(user, wf):
        return jsonify({"error": "Not found"}), 404
    wf.is_active = not wf.is_active
    db.session.commit()
    return jsonify({"workflow": wf.to_dict()})


# ── Execution log ─────────────────────────────────────────────────────────────

@automations_bp.route("/workflows/<int:wf_id>/executions", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def workflow_executions(wf_id):
    user = _current_user()
    wf = AutomationWorkflow.query.get_or_404(wf_id)
    if not _owns_workflow(user, wf):
        return jsonify({"error": "Not found"}), 404

    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 20)), 50)
    execs = AutomationExecution.query.filter_by(workflow_id=wf_id)\
        .order_by(AutomationExecution.executed_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "executions": [e.to_dict() for e in execs.items],
        "total": execs.total,
        "page": page,
    })
