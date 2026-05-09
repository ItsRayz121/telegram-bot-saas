"""
Assistant Hub API — Sprint 1–4 routes.

All routes use /api/hub prefix.
"""
import logging
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User
from ..assistant.hub_models import (
    AssistantHubGlobal, HubBotIdentity, HubBotSettings,
    HubConnectedGroup, HubTask, HubReminder, HubDecision,
    HubMeeting, HubNote, HubSystemAutomation, HubBotAutomationSetting,
    HubInboxItem, HubMemoryPerson, HubMemoryProject, HubMemoryGroupContext,
    HubMemoryGlobal, HubKnowledgeCard,
)
from ..assistant.hub_settings_resolver import get_effective_settings
from ..assistant.hub_plan_limits import get_limits_for_plan, PlanLimitError
from ..config import Config

_log = logging.getLogger(__name__)

hub_bp = Blueprint("hub", __name__, url_prefix="/api/hub")

# Pre-built automation seed codes (Sprint 1 scaffold)
_SEED_AUTOMATIONS = [
    {
        "code": "meeting_reminder",
        "name": "Meeting Reminder",
        "description": "Remind me 1 hour before any extracted meeting",
        "trigger_event": "meeting_extracted",
        "action": "create_reminder",
        "default_params": {"offset_minutes": 60},
    },
    {
        "code": "deadline_alert",
        "name": "Deadline Alert",
        "description": "Send me a DM immediately when a task with a deadline is extracted",
        "trigger_event": "task_with_deadline_extracted",
        "action": "send_immediate_dm",
        "default_params": {},
    },
    {
        "code": "follow_up_reminder",
        "name": "Follow-up Reminder",
        "description": "Remind me 2 days after a follow-up is detected",
        "trigger_event": "follow_up_detected",
        "action": "create_reminder",
        "default_params": {"offset_days": 2},
    },
]


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


def _ensure_seed_automations():
    """Idempotently seed system_automations if empty."""
    if HubSystemAutomation.query.count() == 0:
        for a in _SEED_AUTOMATIONS:
            db.session.add(HubSystemAutomation(
                id=str(uuid.uuid4()),
                code=a["code"],
                name=a["name"],
                description=a["description"],
                trigger_event=a["trigger_event"],
                action=a["action"],
                default_params=a["default_params"],
                is_active=True,
            ))
        db.session.commit()


def _get_or_create_global(user_id: int) -> AssistantHubGlobal:
    """Lazy-create the assistant_hub_global record on first Hub access."""
    record = AssistantHubGlobal.query.filter_by(user_id=user_id).first()
    if record is None:
        record = AssistantHubGlobal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            is_enabled=False,
        )
        db.session.add(record)
        db.session.commit()
    return record


def _get_or_create_official_bot(user_id: int) -> HubBotIdentity:
    """Return (or lazy-create) the official bot identity for the user."""
    bot = HubBotIdentity.query.filter_by(user_id=user_id, bot_type="official").first()
    if bot is not None:
        return bot

    bot = HubBotIdentity(
        id=str(uuid.uuid4()),
        user_id=user_id,
        bot_type="official",
        display_name="Telegizer Official Assistant",
        telegram_bot_token=None,   # uses shared @telegizer_bot token
        telegram_bot_username=Config.TELEGRAM_BOT_USERNAME or "telegizer_bot",
        is_active=True,
    )
    db.session.add(bot)
    db.session.flush()

    settings = HubBotSettings(
        id=str(uuid.uuid4()),
        bot_id=bot.id,
        user_id=user_id,
    )
    db.session.add(settings)

    # Update global to point default_bot_id here
    global_rec = AssistantHubGlobal.query.filter_by(user_id=user_id).first()
    if global_rec:
        global_rec.default_bot_id = bot.id
        global_rec.is_enabled = True

    db.session.commit()
    _ensure_seed_automations()
    return bot


def _bot_card_data(bot: HubBotIdentity, user_id: int) -> dict:
    """Assemble JSON for a bot card."""
    group_count = HubConnectedGroup.query.filter_by(
        bot_id=bot.id, user_id=user_id, is_active=True
    ).count()

    pending_tasks = HubTask.query.filter_by(
        bot_id=bot.id, user_id=user_id, status="pending"
    ).count()

    today = datetime.utcnow().date()
    meetings_today = HubMeeting.query.filter(
        HubMeeting.bot_id == bot.id,
        HubMeeting.user_id == user_id,
        db.func.date(HubMeeting.scheduled_at) == today,
        HubMeeting.dismissed_at.is_(None),
    ).count()

    last_batch = HubConnectedGroup.query.filter_by(
        bot_id=bot.id, user_id=user_id
    ).order_by(HubConnectedGroup.last_batch_at.desc().nullslast()).first()

    last_summary = None
    if last_batch and last_batch.last_batch_at:
        last_summary = last_batch.last_batch_at.isoformat()

    return {
        "id": bot.id,
        "bot_type": bot.bot_type,
        "display_name": bot.display_name,
        "telegram_bot_username": bot.telegram_bot_username,
        "is_active": bot.is_active,
        "group_count": group_count,
        "pending_tasks": pending_tasks,
        "meetings_today": meetings_today,
        "last_summary": last_summary,
        "created_at": bot.created_at.isoformat() if bot.created_at else None,
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@hub_bp.route("/status", methods=["GET"])
@jwt_required()
def hub_status():
    """
    Lazy-create global + official bot on first Hub page visit.
    Returns hub enabled state and official bot summary.
    """
    user = _current_user()
    global_rec = _get_or_create_global(user.id)

    # Auto-create the official bot record on first visit
    official_bot = _get_or_create_official_bot(user.id)

    return jsonify({
        "is_enabled": global_rec.is_enabled,
        "official_bot": _bot_card_data(official_bot, user.id),
        "plan": user.subscription_tier or "free",
        "limits": get_limits_for_plan(user.subscription_tier or "free"),
    })


@hub_bp.route("/bots", methods=["GET"])
@jwt_required()
def list_bots():
    """Return all bot identities for the current user."""
    user = _current_user()
    _get_or_create_global(user.id)

    bots = HubBotIdentity.query.filter_by(user_id=user.id, is_active=True).all()
    return jsonify({
        "bots": [_bot_card_data(b, user.id) for b in bots],
        "plan": user.subscription_tier or "free",
        "limits": get_limits_for_plan(user.subscription_tier or "free"),
    })


@hub_bp.route("/bots/official", methods=["GET"])
@jwt_required()
def get_official_bot():
    """Return official bot card data."""
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    return jsonify(_bot_card_data(bot, user.id))


@hub_bp.route("/bots/official/settings", methods=["GET"])
@jwt_required()
def get_official_settings():
    """Return effective settings for the official bot via the resolver."""
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    effective = get_effective_settings(bot.id)
    return jsonify({"bot_id": bot.id, "settings": effective})


@hub_bp.route("/bots/official/settings", methods=["PATCH"])
@jwt_required()
def update_official_settings():
    """Update official bot settings."""
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    settings = HubBotSettings.query.filter_by(bot_id=bot.id).first()
    if settings is None:
        settings = HubBotSettings(id=str(uuid.uuid4()), bot_id=bot.id, user_id=user.id)
        db.session.add(settings)

    data = request.get_json(silent=True) or {}
    allowed = [
        "ai_personality_note", "response_language", "extraction_sensitivity",
        "digest_enabled", "digest_format", "notification_prefs",
    ]
    for field in allowed:
        if field in data:
            setattr(settings, field, data[field])

    if "digest_time" in data:
        from datetime import time as dtime
        raw = data["digest_time"]
        if raw and isinstance(raw, str):
            parts = raw.split(":")
            settings.digest_time = dtime(int(parts[0]), int(parts[1]))
        else:
            settings.digest_time = None

    settings.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "settings": get_effective_settings(bot.id)})


@hub_bp.route("/bots/official/groups", methods=["GET"])
@jwt_required()
def list_official_groups():
    """Return connected groups for the official bot."""
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    groups = HubConnectedGroup.query.filter_by(
        bot_id=bot.id, user_id=user.id
    ).order_by(HubConnectedGroup.joined_at.desc()).all()

    return jsonify({
        "groups": [_group_dict(g) for g in groups],
        "total": len(groups),
    })


@hub_bp.route("/bots/official/groups/<group_id>", methods=["PATCH"])
@jwt_required()
def update_group_settings(group_id):
    """Update per-group overrides."""
    user = _current_user()
    group = HubConnectedGroup.query.filter_by(id=group_id, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}

    # display_name is the frontend alias for group_name (override label)
    if "display_name" in data:
        group.group_name = data["display_name"] or group.group_name

    allowed = [
        "group_name", "category", "is_active", "active_mode_enabled",
        "extract_tasks", "extract_reminders", "extract_decisions", "extract_meetings",
    ]
    for field in allowed:
        if field in data:
            setattr(group, field, data[field])

    if "silence_start" in data:
        group.silence_start = _parse_time(data["silence_start"])
    if "silence_end" in data:
        group.silence_end = _parse_time(data["silence_end"])
    if "silence_window_start" in data:
        group.silence_start = _parse_time(data["silence_window_start"])
    if "silence_window_end" in data:
        group.silence_end = _parse_time(data["silence_window_end"])

    if "is_active" in data and not data["is_active"]:
        group.pause_reason = "user_paused"
    elif "is_active" in data and data["is_active"]:
        group.pause_reason = None

    db.session.commit()
    return jsonify({"ok": True, "group": _group_dict(group)})


@hub_bp.route("/bots/official/groups/<group_id>/data", methods=["DELETE"])
@jwt_required()
def delete_group_data(group_id):
    """Delete all extracted data from a specific group (not the group record itself)."""
    user = _current_user()
    group = HubConnectedGroup.query.filter_by(id=group_id, user_id=user.id).first_or_404()

    HubTask.query.filter_by(source_group_id=group.id, user_id=user.id).delete()
    HubReminder.query.filter_by(source_group_id=group.id, user_id=user.id).delete()
    HubDecision.query.filter_by(source_group_id=group.id, user_id=user.id).delete()
    HubMeeting.query.filter_by(source_group_id=group.id, user_id=user.id).delete()
    HubNote.query.filter_by(source_group_id=group.id, user_id=user.id).delete()
    db.session.commit()
    return jsonify({"ok": True})


@hub_bp.route("/bots/official/stats", methods=["GET"])
@jwt_required()
def official_bot_stats():
    """Return Overview tab statistics."""
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)

    # Tasks
    pending_tasks = HubTask.query.filter_by(
        bot_id=bot.id, user_id=user.id, status="pending"
    ).count()
    overdue_tasks = HubTask.query.filter(
        HubTask.bot_id == bot.id,
        HubTask.user_id == user.id,
        HubTask.status == "pending",
        HubTask.due_date < datetime.utcnow().date(),
    ).count()

    # Inbox new items
    new_items = HubInboxItem.query.filter_by(
        user_id=user.id, bot_id=bot.id, is_new=True
    ).filter(HubInboxItem.dismissed_at.is_(None)).count()

    return jsonify({
        "pending_tasks": pending_tasks,
        "overdue_tasks": overdue_tasks,
        "new_inbox_items": new_items,
    })


@hub_bp.route("/limits", methods=["GET"])
@jwt_required()
def plan_limits():
    """Return plan limits and current usage for the user."""
    user = _current_user()
    plan = user.subscription_tier or "free"
    bot = HubBotIdentity.query.filter_by(user_id=user.id, bot_type="official").first()

    limits = get_limits_for_plan(plan)
    usage = {}
    if bot:
        usage["connected_groups"] = HubConnectedGroup.query.filter_by(
            bot_id=bot.id, user_id=user.id, is_active=True
        ).count()

    from ..assistant.hub_models import HubMemoryPerson, HubMemoryProject
    usage["memory_people"] = HubMemoryPerson.query.filter_by(user_id=user.id).count()
    usage["memory_projects"] = HubMemoryProject.query.filter_by(user_id=user.id).count()

    return jsonify({"plan": plan, "limits": limits, "usage": usage})


@hub_bp.route("/bots/official/groups/<group_id>/pause", methods=["POST"])
@jwt_required()
def pause_group(group_id):
    """Pause observation for a connected group."""
    user = _current_user()
    group = HubConnectedGroup.query.filter_by(id=group_id, user_id=user.id).first_or_404()
    group.is_active = False
    group.pause_reason = "user_paused"
    db.session.commit()
    return jsonify({"ok": True, "group": _group_dict(group)})


@hub_bp.route("/bots/official/groups/<group_id>/resume", methods=["POST"])
@jwt_required()
def resume_group(group_id):
    """Resume observation for a paused group (respects plan limits)."""
    user = _current_user()
    group = HubConnectedGroup.query.filter_by(id=group_id, user_id=user.id).first_or_404()

    # Plan limit check before resuming
    from ..assistant.hub_plan_limits import check_connected_groups, PlanLimitError
    try:
        check_connected_groups(
            user_id=user.id,
            bot_id=group.bot_id,
            bot_type="official",
            plan=user.subscription_tier or "free",
        )
    except PlanLimitError as e:
        return jsonify({"error": "plan_limit", **e.to_dict()}), 402

    group.is_active = True
    group.pause_reason = None
    db.session.commit()
    return jsonify({"ok": True, "group": _group_dict(group)})


@hub_bp.route("/bots/official/groups/<group_id>/disconnect", methods=["DELETE"])
@jwt_required()
def disconnect_group(group_id):
    """
    Disconnect a group. Optionally delete all extracted data.
    Query param: delete_data=true
    Bot must leave the group (done via Telegram API if bot instance available).
    """
    user = _current_user()
    group = HubConnectedGroup.query.filter_by(id=group_id, user_id=user.id).first_or_404()
    delete_data = request.args.get("delete_data", "false").lower() == "true"

    if delete_data:
        HubTask.query.filter_by(source_group_id=group.id, user_id=user.id).delete()
        HubReminder.query.filter_by(source_group_id=group.id, user_id=user.id).delete()
        HubDecision.query.filter_by(source_group_id=group.id, user_id=user.id).delete()
        HubMeeting.query.filter_by(source_group_id=group.id, user_id=user.id).delete()
        HubNote.query.filter_by(source_group_id=group.id, user_id=user.id).delete()

    telegram_group_id = group.telegram_group_id
    db.session.delete(group)
    db.session.commit()

    # Best-effort: leave Telegram group
    _try_leave_group(telegram_group_id)

    return jsonify({"ok": True, "deleted_data": delete_data})


@hub_bp.route("/export", methods=["GET"])
@jwt_required()
def export_data():
    """
    Export all Assistant Hub data for the user as JSON.
    Includes tasks, reminders, decisions, meetings, notes, templates,
    memory entries, connected group metadata, digests.
    Raw message content is never included (not stored permanently).
    """
    user = _current_user()

    from ..assistant.hub_models import (
        HubTemplate, HubDigest, HubMemoryGlobal, HubMemoryPerson,
        HubMemoryProject, HubMemoryGroupContext,
    )

    bots = HubBotIdentity.query.filter_by(user_id=user.id).all()

    export = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user_id": user.id,
        "bots": [],
        "memory": {
            "global": None,
            "people": [],
            "projects": [],
            "group_contexts": [],
        },
    }

    for bot in bots:
        groups = HubConnectedGroup.query.filter_by(bot_id=bot.id, user_id=user.id).all()
        bot_export = {
            "bot_id": bot.id,
            "bot_type": bot.bot_type,
            "display_name": bot.display_name,
            "templates": [
                {"name": t.name, "content": t.content, "use_count": t.use_count}
                for t in HubTemplate.query.filter_by(bot_id=bot.id).all()
            ],
            "connected_groups": [],
        }
        for g in groups:
            group_export = {
                "group_id": g.id,
                "group_name": g.group_name,
                "category": g.category,
                "tasks": [_task_dict(t) for t in HubTask.query.filter_by(source_group_id=g.id).all()],
                "reminders": [_reminder_dict(r) for r in HubReminder.query.filter_by(source_group_id=g.id).all()],
                "decisions": [_decision_dict(d) for d in HubDecision.query.filter_by(source_group_id=g.id).all()],
                "meetings": [_meeting_dict(m) for m in HubMeeting.query.filter_by(source_group_id=g.id).all()],
                "notes": [_note_dict(n) for n in HubNote.query.filter_by(source_group_id=g.id).all()],
            }
            bot_export["connected_groups"].append(group_export)
        export["bots"].append(bot_export)

    # Memory
    mem_global = HubMemoryGlobal.query.filter_by(user_id=user.id).first()
    if mem_global:
        export["memory"]["global"] = {
            "preferred_name": mem_global.preferred_name,
            "company_name": mem_global.company_name,
            "role": mem_global.role,
            "timezone": mem_global.timezone,
            "current_priorities": mem_global.current_priorities,
            "free_notes": mem_global.free_notes,
        }
    export["memory"]["people"] = [
        {"name": p.name, "role": p.role, "notes": p.notes}
        for p in HubMemoryPerson.query.filter_by(user_id=user.id).all()
    ]
    export["memory"]["projects"] = [
        {"name": p.name, "status": p.status, "context_notes": p.context_notes, "deadline": p.deadline.isoformat() if p.deadline else None}
        for p in HubMemoryProject.query.filter_by(user_id=user.id).all()
    ]
    export["memory"]["group_contexts"] = [
        {"group_id": gc.group_id, "context_notes": gc.context_notes, "key_members": gc.key_members, "active_projects": gc.active_projects}
        for gc in HubMemoryGroupContext.query.filter_by(user_id=user.id).all()
    ]

    return jsonify(export)


@hub_bp.route("/delete-all", methods=["DELETE"])
@jwt_required()
def delete_all_data():
    """
    Delete ALL Assistant Hub data for the user.
    Requires confirmation header: X-Hub-Confirm: DELETE
    Does NOT delete the main Telegizer account.
    """
    confirm = request.headers.get("X-Hub-Confirm", "")
    if confirm != "DELETE":
        return jsonify({"error": "Confirmation required. Send header X-Hub-Confirm: DELETE"}), 400

    user = _current_user()

    from ..assistant.hub_models import (
        AssistantHubGlobal, HubTemplate, HubDigest,
        HubMemoryGlobal, HubMemoryPerson, HubMemoryProject,
        HubMemoryGroupContext, HubMemorySuggestion, HubKnowledgeCard,
        HubExtractionBatch, HubInboxItem, HubBotAutomationSetting,
    )

    # Get all bots before deletion
    bots = HubBotIdentity.query.filter_by(user_id=user.id).all()
    telegram_group_ids = []

    for bot in bots:
        groups = HubConnectedGroup.query.filter_by(bot_id=bot.id, user_id=user.id).all()
        for g in groups:
            telegram_group_ids.append(g.telegram_group_id)
            # Delete extracted data
            HubTask.query.filter_by(source_group_id=g.id).delete()
            HubReminder.query.filter_by(source_group_id=g.id).delete()
            HubDecision.query.filter_by(source_group_id=g.id).delete()
            HubMeeting.query.filter_by(source_group_id=g.id).delete()
            HubNote.query.filter_by(source_group_id=g.id).delete()
            HubMemoryGroupContext.query.filter_by(group_id=g.id).delete()

        # Delete bot-scoped data
        HubConnectedGroup.query.filter_by(bot_id=bot.id).delete()
        HubTemplate.query.filter_by(bot_id=bot.id).delete()
        HubKnowledgeCard.query.filter_by(bot_id=bot.id).delete()
        HubBotAutomationSetting.query.filter_by(bot_id=bot.id).delete()
        HubBotSettings.query.filter_by(bot_id=bot.id).delete()
        HubDigest.query.filter_by(bot_id=bot.id).delete()
        HubInboxItem.query.filter_by(bot_id=bot.id).delete()
        HubExtractionBatch.query.filter_by(bot_id=bot.id).delete()

    # Delete user-scoped data
    HubMemoryGlobal.query.filter_by(user_id=user.id).delete()
    HubMemoryPerson.query.filter_by(user_id=user.id).delete()
    HubMemoryProject.query.filter_by(user_id=user.id).delete()
    HubMemorySuggestion.query.filter_by(user_id=user.id).delete()
    HubBotIdentity.query.filter_by(user_id=user.id).delete()
    AssistantHubGlobal.query.filter_by(user_id=user.id).delete()

    db.session.commit()

    # Best-effort: leave all Telegram groups
    for tg_id in telegram_group_ids:
        _try_leave_group(tg_id)

    return jsonify({"ok": True, "message": "All Assistant Hub data deleted."})


@hub_bp.route("/bots/official/settings/retention", methods=["PATCH"])
@jwt_required()
def update_retention():
    """Update raw buffer retention window (24 / 48 / 72 hours)."""
    user = _current_user()
    data = request.get_json(silent=True) or {}
    hours = int(data.get("hours", 72))
    if hours not in (24, 48, 72):
        return jsonify({"error": "hours must be 24, 48, or 72"}), 400

    # Store in global settings (we reuse notification_prefs JSON for now as a simple store)
    bot = HubBotIdentity.query.filter_by(user_id=user.id, bot_type="official").first()
    if bot:
        settings = HubBotSettings.query.filter_by(bot_id=bot.id).first()
        if settings:
            prefs = settings.notification_prefs or {}
            prefs["buffer_retention_hours"] = hours
            settings.notification_prefs = prefs
            db.session.commit()

    return jsonify({"ok": True, "hours": hours})


def _try_leave_group(telegram_group_id: int):
    """Best-effort: instruct the official bot to leave a Telegram group."""
    try:
        from flask import current_app
        bot_instance = getattr(current_app, "official_bot_instance", None)
        if bot_instance and bot_instance._loop and bot_instance._loop.is_running():
            import asyncio
            future = asyncio.run_coroutine_threadsafe(
                bot_instance.application.bot.leave_chat(telegram_group_id),
                bot_instance._loop,
            )
            future.result(timeout=5)
    except Exception as e:
        _log.debug("leave_chat failed for %s: %s", telegram_group_id, e)


# ── Export helpers ─────────────────────────────────────────────────────────────

def _task_dict(t):
    return {"id": t.id, "title": t.title, "assignee_name": t.assignee_name,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "priority": t.priority, "status": t.status, "source": t.source,
            "created_at": t.created_at.isoformat()}

def _reminder_dict(r):
    return {"id": r.id, "content": r.content,
            "remind_at": r.remind_at.isoformat() if r.remind_at else None,
            "source": r.source, "created_at": r.created_at.isoformat()}

def _decision_dict(d):
    return {"id": d.id, "content": d.content, "made_by": d.made_by,
            "created_at": d.created_at.isoformat()}

def _meeting_dict(m):
    return {"id": m.id, "title": m.title,
            "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
            "participants": m.participants, "created_at": m.created_at.isoformat()}

def _note_dict(n):
    return {"id": n.id, "content": n.content, "tags": n.tags,
            "source": n.source, "created_at": n.created_at.isoformat()}


# ── Sprint 5: Templates CRUD ──────────────────────────────────────────────────

@hub_bp.route("/templates", methods=["GET"])
@jwt_required()
def list_templates():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    from ..assistant.hub_models import HubTemplate
    templates = HubTemplate.query.filter_by(
        bot_id=bot.id, user_id=user.id
    ).order_by(HubTemplate.name.asc()).all()
    return jsonify({"templates": [_template_dict(t) for t in templates]})


@hub_bp.route("/templates", methods=["POST"])
@jwt_required()
def create_template():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    from ..assistant.hub_models import HubTemplate
    from ..assistant.hub_plan_limits import check_templates, PlanLimitError

    try:
        check_templates(user_id=user.id, bot_id=bot.id, plan=user.subscription_tier or "free")
    except PlanLimitError as e:
        return jsonify({"error": "plan_limit", **e.to_dict()}), 402

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    content = (data.get("content") or "").strip()
    if not name or not content:
        return jsonify({"error": "name and content required"}), 400
    if len(content) > 4096:
        return jsonify({"error": "content exceeds 4096 characters"}), 400

    # Unique name per bot
    existing = HubTemplate.query.filter_by(bot_id=bot.id, name=name).first()
    if existing:
        return jsonify({"error": f"A template named '{name}' already exists"}), 409

    template = HubTemplate(
        bot_id=bot.id,
        user_id=user.id,
        name=name[:100],
        content=content,
    )
    db.session.add(template)
    db.session.commit()
    return jsonify({"template": _template_dict(template)}), 201


@hub_bp.route("/templates/<template_id>", methods=["PATCH"])
@jwt_required()
def update_template(template_id):
    user = _current_user()
    from ..assistant.hub_models import HubTemplate
    template = HubTemplate.query.filter_by(id=template_id, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}

    if "name" in data:
        new_name = (data["name"] or "").strip()
        if new_name and new_name != template.name:
            existing = HubTemplate.query.filter_by(bot_id=template.bot_id, name=new_name).first()
            if existing and existing.id != template_id:
                return jsonify({"error": f"A template named '{new_name}' already exists"}), 409
            template.name = new_name[:100]
    if "content" in data:
        content = (data["content"] or "").strip()
        if len(content) > 4096:
            return jsonify({"error": "content exceeds 4096 characters"}), 400
        template.content = content
    template.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"template": _template_dict(template)})


@hub_bp.route("/templates/<template_id>", methods=["DELETE"])
@jwt_required()
def delete_template(template_id):
    user = _current_user()
    from ..assistant.hub_models import HubTemplate
    template = HubTemplate.query.filter_by(id=template_id, user_id=user.id).first_or_404()
    db.session.delete(template)
    db.session.commit()
    return jsonify({"ok": True})


def _template_dict(t) -> dict:
    return {
        "id": t.id,
        "bot_id": t.bot_id,
        "name": t.name,
        "content": t.content,
        "use_count": t.use_count,
        "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ── Sprint 4: Overview aggregation ───────────────────────────────────────────

@hub_bp.route("/overview", methods=["GET"])
@jwt_required()
def hub_overview():
    """
    Aggregated data for the Overview tab.
    Returns: tasks (pending, sorted by due_date), upcoming meetings,
    recent decisions, upcoming reminders, new inbox count.
    """
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    group_id = request.args.get("group_id")

    now = datetime.utcnow()
    today = now.date()

    def _gfilter(q, model):
        if group_id:
            return q.filter(model.source_group_id == group_id)
        return q

    # Tasks — pending, sort overdue first then by due_date
    tasks_q = HubTask.query.filter_by(
        user_id=user.id, bot_id=bot.id, status="pending"
    ).filter(HubTask.dismissed_at.is_(None) if hasattr(HubTask, "dismissed_at") else db.true())
    tasks_q = _gfilter(tasks_q, HubTask)
    tasks = tasks_q.order_by(
        db.case((HubTask.due_date.isnot(None), HubTask.due_date), else_=db.literal(None)).asc().nullslast()
    ).limit(20).all()

    # Meetings — upcoming (not dismissed)
    meetings_q = HubMeeting.query.filter(
        HubMeeting.user_id == user.id,
        HubMeeting.bot_id == bot.id,
        HubMeeting.dismissed_at.is_(None),
        HubMeeting.scheduled_at >= now - timedelta(hours=1),
    )
    meetings_q = _gfilter(meetings_q, HubMeeting)
    meetings = meetings_q.order_by(HubMeeting.scheduled_at.asc().nullslast()).limit(10).all()

    # Decisions — last 7 days
    decisions_q = HubDecision.query.filter(
        HubDecision.user_id == user.id,
        HubDecision.bot_id == bot.id,
        HubDecision.dismissed_at.is_(None),
        HubDecision.created_at >= now - timedelta(days=7),
    )
    decisions_q = _gfilter(decisions_q, HubDecision)
    decisions = decisions_q.order_by(HubDecision.created_at.desc()).limit(10).all()

    # Reminders — upcoming (not delivered, not dismissed)
    reminders_q = HubReminder.query.filter(
        HubReminder.user_id == user.id,
        HubReminder.bot_id == bot.id,
        HubReminder.delivered_at.is_(None),
        HubReminder.dismissed_at.is_(None),
        HubReminder.remind_at >= now - timedelta(minutes=5),
    )
    reminders_q = _gfilter(reminders_q, HubReminder)
    reminders = reminders_q.order_by(HubReminder.remind_at.asc()).limit(10).all()

    new_inbox = HubInboxItem.query.filter_by(
        user_id=user.id, bot_id=bot.id, is_new=True
    ).filter(HubInboxItem.dismissed_at.is_(None)).count()

    group_count = HubConnectedGroup.query.filter_by(
        bot_id=bot.id, user_id=user.id, is_active=True
    ).count()

    return jsonify({
        "group_count": group_count,
        "new_inbox_items": new_inbox,
        "tasks": [_task_dict(t) for t in tasks],
        "meetings": [_meeting_dict(m) for m in meetings],
        "decisions": [_decision_dict(d) for d in decisions],
        "reminders": [_reminder_dict(r) for r in reminders],
    })


# ── Sprint 4: Inbox ───────────────────────────────────────────────────────────

@hub_bp.route("/inbox", methods=["GET"])
@jwt_required()
def list_inbox():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    item_type = request.args.get("type")
    show_dismissed = request.args.get("dismissed", "false").lower() == "true"

    q = HubInboxItem.query.filter_by(user_id=user.id, bot_id=bot.id)
    if item_type:
        q = q.filter_by(item_type=item_type)
    if not show_dismissed:
        q = q.filter(HubInboxItem.dismissed_at.is_(None))
    items = q.order_by(HubInboxItem.created_at.desc()).limit(50).all()

    return jsonify({"items": [_inbox_dict(i) for i in items]})


@hub_bp.route("/inbox/<item_id>/confirm", methods=["PATCH"])
@jwt_required()
def confirm_inbox_item(item_id):
    user = _current_user()
    item = HubInboxItem.query.filter_by(id=item_id, user_id=user.id).first_or_404()
    item.is_new = False
    item.confirmed_at = datetime.utcnow()
    # Also update source item status to 'confirmed'
    if item.item_type == "task":
        t = HubTask.query.filter_by(id=item.item_id, user_id=user.id).first()
        if t:
            t.status = "confirmed"
    db.session.commit()
    return jsonify({"ok": True})


@hub_bp.route("/inbox/<item_id>/dismiss", methods=["PATCH"])
@jwt_required()
def dismiss_inbox_item(item_id):
    user = _current_user()
    item = HubInboxItem.query.filter_by(id=item_id, user_id=user.id).first_or_404()
    item.is_new = False
    item.dismissed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


# ── Sprint 4: Tasks CRUD ──────────────────────────────────────────────────────

@hub_bp.route("/tasks", methods=["GET"])
@jwt_required()
def list_tasks():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    status = request.args.get("status")
    group_id = request.args.get("group_id")

    q = HubTask.query.filter_by(user_id=user.id, bot_id=bot.id)
    if status:
        q = q.filter_by(status=status)
    if group_id:
        q = q.filter_by(source_group_id=group_id)

    tasks = q.order_by(
        db.case((HubTask.due_date.isnot(None), HubTask.due_date), else_=db.literal(None)).asc().nullslast(),
        HubTask.created_at.desc(),
    ).all()

    return jsonify({"tasks": [_task_dict(t) for t in tasks]})


@hub_bp.route("/tasks", methods=["POST"])
@jwt_required()
def create_task():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400

    task = HubTask(
        user_id=user.id,
        bot_id=bot.id,
        source_group_id=data.get("source_group_id"),
        title=title[:500],
        description=data.get("description"),
        assignee_name=data.get("assignee_name"),
        due_date=_parse_date_str(data.get("due_date")),
        priority=data.get("priority", "normal"),
        status="pending",
        source="manual",
    )
    db.session.add(task)
    db.session.flush()

    # Add to inbox
    inbox = HubInboxItem(
        user_id=user.id, bot_id=bot.id,
        item_type="task", item_id=task.id, is_new=True,
    )
    db.session.add(inbox)
    db.session.commit()
    return jsonify({"task": _task_dict(task)}), 201


@hub_bp.route("/tasks/<task_id>", methods=["PATCH"])
@jwt_required()
def update_task(task_id):
    user = _current_user()
    task = HubTask.query.filter_by(id=task_id, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}

    for field in ("title", "description", "assignee_name", "priority", "status"):
        if field in data:
            setattr(task, field, data[field])
    if "due_date" in data:
        task.due_date = _parse_date_str(data["due_date"])
    task.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"task": _task_dict(task)})


@hub_bp.route("/tasks/<task_id>", methods=["DELETE"])
@jwt_required()
def delete_task(task_id):
    user = _current_user()
    task = HubTask.query.filter_by(id=task_id, user_id=user.id).first_or_404()
    HubInboxItem.query.filter_by(item_type="task", item_id=task_id, user_id=user.id).delete()
    db.session.delete(task)
    db.session.commit()
    return jsonify({"ok": True})


# ── Sprint 4: Reminders CRUD ──────────────────────────────────────────────────

@hub_bp.route("/reminders", methods=["GET"])
@jwt_required()
def list_reminders():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    group_id = request.args.get("group_id")
    filter_by = request.args.get("filter")  # upcoming | overdue | all

    now = datetime.utcnow()
    q = HubReminder.query.filter_by(user_id=user.id, bot_id=bot.id).filter(
        HubReminder.dismissed_at.is_(None)
    )
    if group_id:
        q = q.filter_by(source_group_id=group_id)
    if filter_by == "upcoming":
        q = q.filter(HubReminder.remind_at >= now)
    elif filter_by == "overdue":
        q = q.filter(HubReminder.remind_at < now, HubReminder.delivered_at.is_(None))

    reminders = q.order_by(HubReminder.remind_at.asc()).all()
    return jsonify({"reminders": [_reminder_dict(r) for r in reminders]})


@hub_bp.route("/reminders", methods=["POST"])
@jwt_required()
def create_reminder():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    data = request.get_json(silent=True) or {}

    content = (data.get("content") or "").strip()
    remind_at_raw = data.get("remind_at")
    if not content or not remind_at_raw:
        return jsonify({"error": "content and remind_at required"}), 400

    remind_at = _parse_datetime_str(remind_at_raw)
    if not remind_at:
        return jsonify({"error": "invalid remind_at datetime"}), 400

    reminder = HubReminder(
        user_id=user.id, bot_id=bot.id,
        source_group_id=data.get("source_group_id"),
        content=content[:500],
        remind_at=remind_at,
        recurrence=data.get("recurrence"),
        source="manual",
    )
    db.session.add(reminder)
    db.session.flush()

    inbox = HubInboxItem(
        user_id=user.id, bot_id=bot.id,
        item_type="reminder", item_id=reminder.id, is_new=True,
    )
    db.session.add(inbox)
    db.session.commit()
    return jsonify({"reminder": _reminder_dict(reminder)}), 201


@hub_bp.route("/reminders/<reminder_id>", methods=["PATCH"])
@jwt_required()
def update_reminder(reminder_id):
    user = _current_user()
    reminder = HubReminder.query.filter_by(id=reminder_id, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}

    if "content" in data:
        reminder.content = data["content"][:500]
    if "remind_at" in data:
        reminder.remind_at = _parse_datetime_str(data["remind_at"]) or reminder.remind_at
    if "recurrence" in data:
        reminder.recurrence = data["recurrence"]
    db.session.commit()
    return jsonify({"reminder": _reminder_dict(reminder)})


@hub_bp.route("/reminders/<reminder_id>", methods=["DELETE"])
@jwt_required()
def delete_reminder(reminder_id):
    user = _current_user()
    reminder = HubReminder.query.filter_by(id=reminder_id, user_id=user.id).first_or_404()
    HubInboxItem.query.filter_by(item_type="reminder", item_id=reminder_id, user_id=user.id).delete()
    db.session.delete(reminder)
    db.session.commit()
    return jsonify({"ok": True})


# ── Sprint 4: Notes CRUD ──────────────────────────────────────────────────────

@hub_bp.route("/notes", methods=["GET"])
@jwt_required()
def list_notes():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    group_id = request.args.get("group_id")
    source = request.args.get("source")

    q = HubNote.query.filter_by(user_id=user.id, bot_id=bot.id)
    if group_id:
        q = q.filter_by(source_group_id=group_id)
    if source:
        q = q.filter_by(source=source)

    notes = q.order_by(HubNote.created_at.desc()).all()
    return jsonify({"notes": [_note_dict(n) for n in notes]})


@hub_bp.route("/notes", methods=["POST"])
@jwt_required()
def create_note():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    data = request.get_json(silent=True) or {}

    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400

    note = HubNote(
        user_id=user.id, bot_id=bot.id,
        source_group_id=data.get("source_group_id"),
        content=content[:2000],
        tags=data.get("tags", []),
        source="manual",
    )
    db.session.add(note)
    db.session.commit()
    return jsonify({"note": _note_dict(note)}), 201


@hub_bp.route("/notes/<note_id>", methods=["PATCH"])
@jwt_required()
def update_note(note_id):
    user = _current_user()
    note = HubNote.query.filter_by(id=note_id, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}

    if "content" in data:
        note.content = data["content"][:2000]
    if "tags" in data and isinstance(data["tags"], list):
        note.tags = data["tags"]
    note.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"note": _note_dict(note)})


@hub_bp.route("/notes/<note_id>", methods=["DELETE"])
@jwt_required()
def delete_note(note_id):
    user = _current_user()
    note = HubNote.query.filter_by(id=note_id, user_id=user.id).first_or_404()
    db.session.delete(note)
    db.session.commit()
    return jsonify({"ok": True})


# ── Sprint 4: Decisions & Meetings (read + dismiss) ──────────────────────────

@hub_bp.route("/decisions", methods=["GET"])
@jwt_required()
def list_decisions():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    group_id = request.args.get("group_id")

    q = HubDecision.query.filter(
        HubDecision.user_id == user.id,
        HubDecision.bot_id == bot.id,
        HubDecision.dismissed_at.is_(None),
    )
    if group_id:
        q = q.filter_by(source_group_id=group_id)
    decisions = q.order_by(HubDecision.created_at.desc()).limit(50).all()
    return jsonify({"decisions": [_decision_dict(d) for d in decisions]})


@hub_bp.route("/decisions/<decision_id>/dismiss", methods=["PATCH"])
@jwt_required()
def dismiss_decision(decision_id):
    user = _current_user()
    d = HubDecision.query.filter_by(id=decision_id, user_id=user.id).first_or_404()
    d.dismissed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@hub_bp.route("/meetings", methods=["GET"])
@jwt_required()
def list_meetings():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    group_id = request.args.get("group_id")

    q = HubMeeting.query.filter(
        HubMeeting.user_id == user.id,
        HubMeeting.bot_id == bot.id,
        HubMeeting.dismissed_at.is_(None),
    )
    if group_id:
        q = q.filter_by(source_group_id=group_id)
    meetings = q.order_by(HubMeeting.scheduled_at.asc().nullslast()).all()
    return jsonify({"meetings": [_meeting_dict(m) for m in meetings]})


@hub_bp.route("/meetings/<meeting_id>/dismiss", methods=["PATCH"])
@jwt_required()
def dismiss_meeting(meeting_id):
    user = _current_user()
    m = HubMeeting.query.filter_by(id=meeting_id, user_id=user.id).first_or_404()
    m.dismissed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


# ── Sprint 4: Automation settings ────────────────────────────────────────────

@hub_bp.route("/bots/official/automations", methods=["GET"])
@jwt_required()
def get_automations():
    """Return automation toggle states for the official bot."""
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    _ensure_seed_automations()

    automations = HubSystemAutomation.query.filter_by(is_active=True).all()
    result = []
    for auto in automations:
        setting = HubBotAutomationSetting.query.filter_by(
            bot_id=bot.id, automation_id=auto.id
        ).first()
        is_enabled = setting.is_enabled if (setting and setting.is_enabled is not None) else True
        result.append({
            "code": auto.code,
            "name": auto.name,
            "description": auto.description,
            "is_enabled": is_enabled,
            "custom_params": setting.custom_params if setting else None,
        })

    # Also return digest settings from bot_settings
    settings = HubBotSettings.query.filter_by(bot_id=bot.id).first()
    digest = {
        "enabled": bool(settings.digest_enabled) if settings else False,
        "time": settings.digest_time.strftime("%H:%M") if (settings and settings.digest_time) else "21:00",
        "format": settings.digest_format or "compact",
    }

    return jsonify({"automations": result, "digest": digest})


@hub_bp.route("/bots/official/automations", methods=["PATCH"])
@jwt_required()
def update_automations():
    """Save automation toggle states."""
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    _ensure_seed_automations()
    data = request.get_json(silent=True) or {}

    # Update individual automation toggles
    toggles = data.get("automations", {})  # {"meeting_reminder": true, "deadline_alert": false}
    for code, enabled in toggles.items():
        auto = HubSystemAutomation.query.filter_by(code=code).first()
        if not auto:
            continue
        setting = HubBotAutomationSetting.query.filter_by(
            bot_id=bot.id, automation_id=auto.id
        ).first()
        if not setting:
            setting = HubBotAutomationSetting(
                id=str(uuid.uuid4()), bot_id=bot.id, automation_id=auto.id
            )
            db.session.add(setting)
        setting.is_enabled = bool(enabled)

    # Update digest settings
    if "digest" in data:
        digest_data = data["digest"]
        settings = HubBotSettings.query.filter_by(bot_id=bot.id).first()
        if settings:
            if "enabled" in digest_data:
                settings.digest_enabled = bool(digest_data["enabled"])
            if "time" in digest_data and isinstance(digest_data["time"], str):
                parts = digest_data["time"].split(":")
                from datetime import time as dtime
                settings.digest_time = dtime(int(parts[0]), int(parts[1]))
            if "format" in digest_data:
                settings.digest_format = digest_data["format"]
            settings.updated_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"ok": True})


@hub_bp.route("/webhook", methods=["POST"])
def hub_webhook():
    """
    Telegram webhook receiver for the shared @telegizer_bot in Hub context.

    Sprint 1: receive messages, buffer to Redis, discard if group not connected.
    Full pipeline (extraction) is Sprint 3.
    """
    import json
    import hashlib

    # Validate secret token from Telegram webhook header
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected = Config.SECRET_KEY[:32] if Config.SECRET_KEY else ""
    if secret_token and expected and not _safe_compare(secret_token, expected):
        return jsonify({"ok": False}), 403

    payload = request.get_json(force=True, silent=True) or {}
    message = payload.get("message") or payload.get("edited_message")
    if not message:
        return jsonify({"ok": True}), 200

    chat = message.get("chat", {})
    telegram_group_id = chat.get("id")
    if not telegram_group_id or chat.get("type") not in ("group", "supergroup"):
        return jsonify({"ok": True}), 200

    # Find the connected group record
    group = HubConnectedGroup.query.filter_by(
        telegram_group_id=telegram_group_id,
        is_active=True,
    ).first()

    if not group or not group.consent_confirmed_at:
        return jsonify({"ok": True}), 200

    # Buffer message to Redis
    _buffer_message(group, message)

    return jsonify({"ok": True}), 200


def _buffer_message(group: HubConnectedGroup, message: dict):
    """Write message to Redis buffer with 72-hour TTL."""
    try:
        import redis as redis_lib
        import json

        r = redis_lib.from_url(Config.REDIS_URL, decode_responses=True)
        key = f"assistant:buffer:{group.bot_id}:{group.id}"
        ttl_seconds = 72 * 3600

        sender = message.get("from", {})
        sender_name = sender.get("first_name", "Unknown")
        if sender.get("last_name"):
            sender_name += f" {sender['last_name']}"

        entry = {
            "telegram_message_id": message.get("message_id"),
            "sender_name": sender_name,
            "content": message.get("text", ""),
            "timestamp": datetime.utcfromtimestamp(message.get("date", 0)).isoformat() + "Z",
            "has_trigger": False,
        }

        r.rpush(key, json.dumps(entry))
        r.ltrim(key, -500, -1)   # keep latest 500 only
        r.expire(key, ttl_seconds)

    except Exception as exc:
        _log.warning("Hub buffer write failed for group %s: %s", group.id, exc)


def _group_dict(group: HubConnectedGroup) -> dict:
    return {
        "id": group.id,
        "bot_id": group.bot_id,
        "telegram_group_id": group.telegram_group_id,
        "group_name": group.group_name,
        "display_name": group.group_name,  # frontend alias
        "category": group.category,
        "is_active": group.is_active,
        "pause_reason": group.pause_reason,
        "consent_confirmed_at": group.consent_confirmed_at.isoformat() if group.consent_confirmed_at else None,
        "intro_sent": group.intro_sent,
        "is_public_group": group.is_public_group,
        "silence_start": group.silence_start.strftime("%H:%M") if group.silence_start else None,
        "silence_end": group.silence_end.strftime("%H:%M") if group.silence_end else None,
        "silence_window_start": group.silence_start.strftime("%H:%M") if group.silence_start else None,
        "silence_window_end": group.silence_end.strftime("%H:%M") if group.silence_end else None,
        "extract_tasks": group.extract_tasks,
        "extract_reminders": group.extract_reminders,
        "extract_decisions": group.extract_decisions,
        "extract_meetings": group.extract_meetings,
        "last_batch_at": group.last_batch_at.isoformat() if group.last_batch_at else None,
        "joined_at": group.joined_at.isoformat() if group.joined_at else None,
    }


def _parse_time(raw):
    if not raw or not isinstance(raw, str):
        return None
    try:
        from datetime import time as dtime
        parts = raw.split(":")
        return dtime(int(parts[0]), int(parts[1]))
    except Exception:
        return None


def _safe_compare(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a.encode(), b.encode())


def _inbox_dict(item: HubInboxItem) -> dict:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "item_id": item.item_id,
        "is_new": item.is_new,
        "dismissed_at": item.dismissed_at.isoformat() if item.dismissed_at else None,
        "confirmed_at": item.confirmed_at.isoformat() if item.confirmed_at else None,
        "created_at": item.created_at.isoformat(),
    }


def _parse_date_str(value):
    if not value:
        return None
    try:
        from datetime import date
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _parse_datetime_str(value):
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


# ── Sprint 6: Memory CRUD ─────────────────────────────────────────────────────

@hub_bp.route("/memory/global", methods=["GET"])
@jwt_required()
def get_memory_global():
    user = _current_user()
    mg = HubMemoryGlobal.query.filter_by(user_id=user.id).first()
    if not mg:
        return jsonify({"global": None})
    return jsonify({"global": {
        "preferred_name": mg.preferred_name,
        "company_name": mg.company_name,
        "role": mg.role,
        "timezone": mg.timezone,
        "current_priorities": mg.current_priorities or [],
        "free_notes": mg.free_notes,
        "updated_at": mg.updated_at.isoformat() if mg.updated_at else None,
    }})


@hub_bp.route("/memory/global", methods=["PATCH"])
@jwt_required()
def update_memory_global():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    mg = HubMemoryGlobal.query.filter_by(user_id=user.id).first()
    if not mg:
        mg = HubMemoryGlobal(id=str(uuid.uuid4()), user_id=user.id)
        db.session.add(mg)
    allowed = ["preferred_name", "company_name", "role", "timezone", "current_priorities", "free_notes"]
    for k in allowed:
        if k in data:
            setattr(mg, k, data[k])
    mg.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@hub_bp.route("/memory/people", methods=["GET"])
@jwt_required()
def list_memory_people():
    user = _current_user()
    people = HubMemoryPerson.query.filter_by(user_id=user.id).order_by(HubMemoryPerson.name.asc()).all()
    return jsonify({"people": [_person_dict(p) for p in people]})


@hub_bp.route("/memory/people", methods=["POST"])
@jwt_required()
def create_memory_person():
    user = _current_user()
    from ..assistant.hub_plan_limits import check_memory_people, PlanLimitError
    try:
        check_memory_people(user.id, plan=user.subscription_tier or "free")
    except PlanLimitError as e:
        return jsonify({"error": "plan_limit", **e.to_dict()}), 402
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    p = HubMemoryPerson(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name=name,
        role=data.get("role") or None,
        notes=data.get("notes") or None,
        group_associations=data.get("group_associations") or [],
        source="manual",
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({"person": _person_dict(p)}), 201


@hub_bp.route("/memory/people/<person_id>", methods=["PATCH"])
@jwt_required()
def update_memory_person(person_id):
    user = _current_user()
    p = HubMemoryPerson.query.filter_by(id=person_id, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    for k in ["name", "role", "notes", "group_associations"]:
        if k in data:
            setattr(p, k, data[k] if data[k] != "" else None)
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"person": _person_dict(p)})


@hub_bp.route("/memory/people/<person_id>", methods=["DELETE"])
@jwt_required()
def delete_memory_person(person_id):
    user = _current_user()
    p = HubMemoryPerson.query.filter_by(id=person_id, user_id=user.id).first_or_404()
    db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True})


@hub_bp.route("/memory/projects", methods=["GET"])
@jwt_required()
def list_memory_projects():
    user = _current_user()
    projects = HubMemoryProject.query.filter_by(user_id=user.id).order_by(HubMemoryProject.name.asc()).all()
    return jsonify({"projects": [_project_dict(pj) for pj in projects]})


@hub_bp.route("/memory/projects", methods=["POST"])
@jwt_required()
def create_memory_project():
    user = _current_user()
    from ..assistant.hub_plan_limits import check_memory_projects, PlanLimitError
    try:
        check_memory_projects(user.id, plan=user.subscription_tier or "free")
    except PlanLimitError as e:
        return jsonify({"error": "plan_limit", **e.to_dict()}), 402
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    pj = HubMemoryProject(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name=name,
        status=data.get("status") or None,
        context_notes=data.get("context_notes") or None,
        group_associations=data.get("group_associations") or [],
        deadline=_parse_date_str(data.get("deadline")),
        source="manual",
    )
    db.session.add(pj)
    db.session.commit()
    return jsonify({"project": _project_dict(pj)}), 201


@hub_bp.route("/memory/projects/<project_id>", methods=["PATCH"])
@jwt_required()
def update_memory_project(project_id):
    user = _current_user()
    pj = HubMemoryProject.query.filter_by(id=project_id, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    for k in ["name", "status", "context_notes", "group_associations"]:
        if k in data:
            setattr(pj, k, data[k] if data[k] != "" else None)
    if "deadline" in data:
        pj.deadline = _parse_date_str(data["deadline"])
    pj.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"project": _project_dict(pj)})


@hub_bp.route("/memory/projects/<project_id>", methods=["DELETE"])
@jwt_required()
def delete_memory_project(project_id):
    user = _current_user()
    pj = HubMemoryProject.query.filter_by(id=project_id, user_id=user.id).first_or_404()
    db.session.delete(pj)
    db.session.commit()
    return jsonify({"ok": True})


def _person_dict(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "role": p.role,
        "notes": p.notes,
        "group_associations": p.group_associations or [],
        "source": p.source,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _project_dict(pj) -> dict:
    return {
        "id": pj.id,
        "name": pj.name,
        "status": pj.status,
        "context_notes": pj.context_notes,
        "group_associations": pj.group_associations or [],
        "deadline": pj.deadline.isoformat() if pj.deadline else None,
        "source": pj.source,
        "created_at": pj.created_at.isoformat() if pj.created_at else None,
        "updated_at": pj.updated_at.isoformat() if pj.updated_at else None,
    }


def _parse_date_str(value):
    if not value:
        return None
    try:
        from datetime import date
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None
