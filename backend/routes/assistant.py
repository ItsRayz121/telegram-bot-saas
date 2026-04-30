"""
Assistant Hub API — aggregated summary for the Hub dashboard.

GET /api/assistant/hub-summary
"""
from datetime import datetime, timedelta
import logging

from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, TelegramGroup, WorkspaceReminder, Note, DigestLog, AutomationExecution, AutomationWorkflow
from ..middleware.rate_limit import rate_limit
from ..config import Config
from flask import Blueprint

_log = logging.getLogger(__name__)

assistant_bp = Blueprint("assistant", __name__, url_prefix="/api/assistant")


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


@assistant_bp.route("/hub-summary", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def hub_summary():
    user = _current_user()
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    # ── Connected groups ──────────────────────────────────────────────────────
    groups = TelegramGroup.query.filter_by(
        owner_user_id=user.id, is_disabled=False
    ).all()
    active_groups = [g for g in groups if g.bot_status == "active"]

    # ── Reminders due today (delivered or not) ────────────────────────────────
    reminders_today = (
        WorkspaceReminder.query
        .filter(
            WorkspaceReminder.owner_user_id == user.id,
            WorkspaceReminder.remind_at >= today_start,
            WorkspaceReminder.remind_at < tomorrow_start,
        )
        .order_by(WorkspaceReminder.remind_at.asc())
        .limit(5)
        .all()
    )
    # Also include overdue undelivered reminders
    overdue = (
        WorkspaceReminder.query
        .filter(
            WorkspaceReminder.owner_user_id == user.id,
            WorkspaceReminder.remind_at < today_start,
            WorkspaceReminder.is_delivered == False,  # noqa: E712
        )
        .order_by(WorkspaceReminder.remind_at.desc())
        .limit(3)
        .all()
    )
    all_reminders = overdue + reminders_today

    # ── Recent notes ──────────────────────────────────────────────────────────
    recent_notes = (
        Note.query
        .filter_by(user_id=user.id)
        .order_by(Note.created_at.desc())
        .limit(3)
        .all()
    )

    # ── Digest status per group ───────────────────────────────────────────────
    digest_status = []
    for g in groups:
        last_log = (
            DigestLog.query
            .filter_by(group_id=g.telegram_group_id)
            .order_by(DigestLog.sent_at.desc())
            .first()
        )
        digest_cfg = (g.settings or {}).get("digest", {})
        enabled = digest_cfg.get("enabled", digest_cfg.get("daily", False))

        if last_log and last_log.sent_at >= today_start:
            status = "sent"
        elif enabled:
            status = "pending"
        else:
            status = "disabled"

        digest_status.append({
            "group_id": g.telegram_group_id,
            "group_title": g.title,
            "bot_status": g.bot_status,
            "last_sent": last_log.sent_at.isoformat() if last_log else None,
            "status": status,
        })

    # ── Automation activity today ─────────────────────────────────────────────
    workflows_today = (
        db.session.query(AutomationExecution)
        .join(AutomationWorkflow, AutomationExecution.workflow_id == AutomationWorkflow.id)
        .filter(
            AutomationWorkflow.owner_user_id == user.id,
            AutomationExecution.executed_at >= today_start,
        )
        .count()
    )

    return jsonify({
        "bot_connected": bool(user.telegram_user_id),
        "telegram_username": user.telegram_username,
        "connected_groups": len(groups),
        "active_groups": len(active_groups),
        "bot_username": Config.TELEGRAM_BOT_USERNAME,
        "reminders_today": [r.to_dict() for r in all_reminders],
        "recent_notes": [n.to_dict() for n in recent_notes],
        "digest_status": digest_status,
        "automation_activity": {
            "auto_replies_today": 0,   # AutoReplyLog is Phase 2
            "workflows_today": workflows_today,
        },
        "onboarding": {
            "has_active_group": len(active_groups) > 0,
            "has_auto_reply": False,   # resolved client-side for simplicity
            "has_digest": any(
                (g.settings or {}).get("digest", {}).get("enabled") for g in groups
            ),
            "has_note": Note.query.filter_by(user_id=user.id).count() > 0,
        },
    })
