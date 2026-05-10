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
    HubMemoryGlobal, HubKnowledgeCard, HubFollowUp,
)
from ..assistant.hub_settings_resolver import get_effective_settings
from ..assistant.hub_plan_limits import get_limits_for_plan, PlanLimitError
from ..config import Config

_log = logging.getLogger(__name__)

hub_bp = Blueprint("hub", __name__, url_prefix="/api/hub")

# Pre-built automation seed codes
_SEED_AUTOMATIONS = [
    {
        "code": "meeting_reminder",
        "name": "Meeting Reminder",
        "description": "Remind me 1 hour before any meeting extracted from a group",
        "trigger_event": "meeting_extracted",
        "action": "create_reminder",
        "default_params": {"offset_minutes": 60},
        "default_enabled": True,
        "icon": "CalendarMonth",
    },
    {
        "code": "deadline_alert",
        "name": "Deadline Alert",
        "description": "Send a Telegram DM immediately when a task with a deadline is extracted",
        "trigger_event": "task_with_deadline_extracted",
        "action": "send_immediate_dm",
        "default_params": {},
        "default_enabled": True,
        "icon": "Warning",
    },
    {
        "code": "follow_up_reminder",
        "name": "Follow-up Nudge",
        "description": "Remind me 2 days after an unresolved commitment is detected in a group",
        "trigger_event": "follow_up_detected",
        "action": "create_reminder",
        "default_params": {"offset_days": 2},
        "default_enabled": True,
        "icon": "TrackChanges",
    },
    {
        "code": "decision_digest",
        "name": "Decision Log",
        "description": "Save every extracted decision to your Notes automatically",
        "trigger_event": "decision_extracted",
        "action": "save_note",
        "default_params": {},
        "default_enabled": False,
        "icon": "Gavel",
    },
    {
        "code": "high_priority_alert",
        "name": "High-Priority Task Alert",
        "description": "Send a Telegram DM immediately when a high-priority task is extracted",
        "trigger_event": "high_priority_task_extracted",
        "action": "send_immediate_dm",
        "default_params": {},
        "default_enabled": True,
        "icon": "PriorityHigh",
    },
    {
        "code": "daily_followup_summary",
        "name": "Daily Follow-up Summary",
        "description": "Send a morning DM listing all open follow-ups across your groups",
        "trigger_event": "daily_schedule",
        "action": "send_followup_summary_dm",
        "default_params": {"hour": 9},
        "default_enabled": False,
        "icon": "Summarize",
    },
]


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


def _ensure_seed_automations():
    """Upsert seed automations — adds new ones, updates descriptions. Safe to call repeatedly."""
    existing = {a.code: a for a in HubSystemAutomation.query.all()}
    changed = False
    for a in _SEED_AUTOMATIONS:
        if a["code"] in existing:
            rec = existing[a["code"]]
            # Update name/description/icon if changed
            if rec.description != a["description"]:
                rec.description = a["description"]
                changed = True
            if rec.name != a["name"]:
                rec.name = a["name"]
                changed = True
            # Persist icon in default_params if not there
            if rec.default_params.get("icon") != a.get("icon"):
                rec.default_params = {**rec.default_params, "icon": a.get("icon", ""), "default_enabled": a.get("default_enabled", False)}
                changed = True
        else:
            params = {**a.get("default_params", {}), "icon": a.get("icon", ""), "default_enabled": a.get("default_enabled", False)}
            db.session.add(HubSystemAutomation(
                id=str(uuid.uuid4()),
                code=a["code"],
                name=a["name"],
                description=a["description"],
                trigger_event=a["trigger_event"],
                action=a["action"],
                default_params=params,
                is_active=True,
            ))
            changed = True
    if changed:
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


def _resolve_bot(user: User, bot_id_param: str | None = None) -> HubBotIdentity:
    """Return the requested bot (verified owner) or fall back to the official bot."""
    if bot_id_param:
        bot = HubBotIdentity.query.filter_by(id=bot_id_param, user_id=user.id).first()
        if bot is None:
            from flask import abort
            abort(404)
        return bot
    return _get_or_create_official_bot(user.id)


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
    from ..assistant.hub_crypto import _dec
    return {"id": t.id, "title": _dec(t.title), "assignee_name": t.assignee_name,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "priority": t.priority, "status": t.status, "source": t.source,
            "source_group_id": t.source_group_id,
            "created_at": t.created_at.isoformat()}

def _reminder_dict(r):
    from ..assistant.hub_crypto import _dec
    return {"id": r.id, "content": _dec(r.content),
            "remind_at": r.remind_at.isoformat() if r.remind_at else None,
            "delivered_at": r.delivered_at.isoformat() if r.delivered_at else None,
            "dismissed_at": r.dismissed_at.isoformat() if r.dismissed_at else None,
            "source": r.source, "source_group_id": r.source_group_id,
            "created_at": r.created_at.isoformat()}

def _decision_dict(d):
    from ..assistant.hub_crypto import _dec
    return {"id": d.id, "content": _dec(d.content), "made_by": d.made_by,
            "source_group_id": d.source_group_id,
            "created_at": d.created_at.isoformat()}

def _meeting_dict(m):
    from ..assistant.hub_crypto import _dec
    return {"id": m.id, "title": _dec(m.title),
            "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
            "participants": m.participants, "source_group_id": m.source_group_id,
            "created_at": m.created_at.isoformat()}

def _note_dict(n):
    from ..assistant.hub_crypto import _dec
    return {"id": n.id, "content": _dec(n.content), "tags": n.tags,
            "source": n.source, "source_group_id": n.source_group_id,
            "created_at": n.created_at.isoformat()}


# ── Sprint 5: Templates CRUD ──────────────────────────────────────────────────

@hub_bp.route("/templates", methods=["GET"])
@jwt_required()
def list_templates():
    user = _current_user()
    bot = _resolve_bot(user, request.args.get("bot_id"))
    from ..assistant.hub_models import HubTemplate
    templates = HubTemplate.query.filter_by(
        bot_id=bot.id, user_id=user.id
    ).order_by(HubTemplate.name.asc()).all()
    return jsonify({"templates": [_template_dict(t) for t in templates]})


@hub_bp.route("/templates", methods=["POST"])
@jwt_required()
def create_template():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    bot = _resolve_bot(user, data.get("bot_id"))
    from ..assistant.hub_models import HubTemplate
    from ..assistant.hub_plan_limits import check_templates, PlanLimitError

    try:
        check_templates(user_id=user.id, bot_id=bot.id, plan=user.subscription_tier or "free")
    except PlanLimitError as e:
        return jsonify({"error": "plan_limit", **e.to_dict()}), 402

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
    bot = _resolve_bot(user, request.args.get("bot_id"))
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
    bot = _resolve_bot(user, request.args.get("bot_id"))
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
    data = request.get_json(silent=True) or {}
    bot = _resolve_bot(user, data.get("bot_id"))

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400

    from ..assistant.hub_crypto import _enc
    task = HubTask(
        user_id=user.id,
        bot_id=bot.id,
        source_group_id=data.get("source_group_id"),
        title=_enc(title[:500]),
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

    from ..assistant.hub_crypto import _enc
    for field in ("assignee_name", "priority", "status"):
        if field in data:
            setattr(task, field, data[field])
    for field in ("title", "description"):
        if field in data:
            setattr(task, field, _enc(data[field]) if data[field] else None)
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
    bot = _resolve_bot(user, request.args.get("bot_id"))
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
    data = request.get_json(silent=True) or {}
    bot = _resolve_bot(user, data.get("bot_id"))

    content = (data.get("content") or "").strip()
    remind_at_raw = data.get("remind_at")
    if not content or not remind_at_raw:
        return jsonify({"error": "content and remind_at required"}), 400

    remind_at = _parse_datetime_str(remind_at_raw)
    if not remind_at:
        return jsonify({"error": "invalid remind_at datetime"}), 400

    from ..assistant.hub_crypto import _enc
    reminder = HubReminder(
        user_id=user.id, bot_id=bot.id,
        source_group_id=data.get("source_group_id"),
        content=_enc(content[:500]),
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
        from ..assistant.hub_crypto import _enc
        reminder.content = _enc(data["content"][:500])
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
    bot = _resolve_bot(user, request.args.get("bot_id"))
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
    data = request.get_json(silent=True) or {}
    bot = _resolve_bot(user, data.get("bot_id"))

    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400

    from ..assistant.hub_crypto import _enc
    note = HubNote(
        user_id=user.id, bot_id=bot.id,
        source_group_id=data.get("source_group_id"),
        content=_enc(content[:2000]),
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
        from ..assistant.hub_crypto import _enc
        note.content = _enc(data["content"][:2000])
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
        default_on = bool(auto.default_params.get("default_enabled", True)) if auto.default_params else True
        is_enabled = setting.is_enabled if (setting and setting.is_enabled is not None) else default_on
        result.append({
            "code": auto.code,
            "name": auto.name,
            "description": auto.description,
            "icon": auto.default_params.get("icon", "") if auto.default_params else "",
            "is_enabled": is_enabled,
            "default_enabled": default_on,
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
    from ..assistant.hub_crypto import _dec
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
        "free_notes": _dec(mg.free_notes),
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
    from ..assistant.hub_crypto import _enc
    plain_fields = ["preferred_name", "company_name", "role", "timezone", "current_priorities"]
    encrypted_fields = ["free_notes"]
    for k in plain_fields:
        if k in data:
            setattr(mg, k, data[k])
    for k in encrypted_fields:
        if k in data:
            setattr(mg, k, _enc(data[k]) if data[k] else None)
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
    from ..assistant.hub_crypto import _enc
    p = HubMemoryPerson(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name=name,
        role=data.get("role") or None,
        notes=_enc(data.get("notes")) if data.get("notes") else None,
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
    from ..assistant.hub_crypto import _enc
    for k in ["name", "role", "group_associations"]:
        if k in data:
            setattr(p, k, data[k] if data[k] != "" else None)
    if "notes" in data:
        p.notes = _enc(data["notes"]) if data["notes"] else None
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
    from ..assistant.hub_crypto import _enc
    pj = HubMemoryProject(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name=name,
        status=data.get("status") or None,
        context_notes=_enc(data.get("context_notes")) if data.get("context_notes") else None,
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
    from ..assistant.hub_crypto import _enc
    for k in ["name", "status", "group_associations"]:
        if k in data:
            setattr(pj, k, data[k] if data[k] != "" else None)
    if "context_notes" in data:
        pj.context_notes = _enc(data["context_notes"]) if data["context_notes"] else None
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
    from ..assistant.hub_crypto import _dec
    return {
        "id": p.id,
        "name": p.name,
        "role": p.role,
        "notes": _dec(p.notes),
        "group_associations": p.group_associations or [],
        "source": p.source,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _project_dict(pj) -> dict:
    from ..assistant.hub_crypto import _dec
    return {
        "id": pj.id,
        "name": pj.name,
        "status": pj.status,
        "context_notes": _dec(pj.context_notes),
        "group_associations": pj.group_associations or [],
        "deadline": pj.deadline.isoformat() if pj.deadline else None,
        "source": pj.source,
        "created_at": pj.created_at.isoformat() if pj.created_at else None,
        "updated_at": pj.updated_at.isoformat() if pj.updated_at else None,
    }


# ── Sprint 7: Custom Bot Management ──────────────────────────────────────────

@hub_bp.route("/bots", methods=["POST"])
@jwt_required()
def create_custom_bot():
    """Register a new custom Telegram bot (Pro+ only)."""
    import requests as _req
    from ..assistant.hub_crypto import _enc
    from ..assistant.hub_plan_limits import _limit, _unlimited

    user = _current_user()
    plan = user.subscription_tier or "free"
    if plan == "free":
        return jsonify({"error": "plan_limit", "resource": "custom_bots", "plan": plan}), 402

    data = request.get_json(silent=True) or {}
    display_name = (data.get("display_name") or "").strip()
    token = (data.get("telegram_bot_token") or "").strip()

    if not display_name:
        return jsonify({"error": "display_name required"}), 400
    if not token:
        return jsonify({"error": "telegram_bot_token required"}), 400

    max_bots = _limit(plan, "custom_bots")
    if not _unlimited(plan, "custom_bots"):
        current_count = HubBotIdentity.query.filter_by(
            user_id=user.id, bot_type="custom", is_active=True
        ).count()
        if current_count >= max_bots:
            return jsonify({"error": "plan_limit", "resource": "custom_bots",
                            "current": current_count, "max_allowed": max_bots, "plan": plan}), 402

    # Validate token against Telegram
    try:
        resp = _req.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        resp.raise_for_status()
        tg_data = resp.json().get("result", {})
    except Exception as exc:
        _log.warning("create_custom_bot: getMe failed: %s", exc)
        return jsonify({"error": "invalid_token", "detail": "Telegram rejected the bot token"}), 400

    bot_username = tg_data.get("username")
    bot_tg_id = tg_data.get("id")

    existing = HubBotIdentity.query.filter_by(
        user_id=user.id, telegram_bot_id=bot_tg_id, is_active=True
    ).first()
    if existing:
        return jsonify({"error": "already_registered", "bot_id": existing.id}), 409

    bot = HubBotIdentity(
        id=str(uuid.uuid4()),
        user_id=user.id,
        bot_type="custom",
        display_name=display_name,
        telegram_bot_token=_enc(token),
        telegram_bot_username=bot_username,
        telegram_bot_id=bot_tg_id,
        is_active=True,
    )
    db.session.add(bot)
    db.session.flush()

    settings = HubBotSettings(
        id=str(uuid.uuid4()),
        bot_id=bot.id,
        user_id=user.id,
    )
    db.session.add(settings)
    db.session.commit()
    _log.info("create_custom_bot: user=%s registered @%s", user.id, bot_username)

    # Register Telegram webhook (best-effort — don't fail if BASE_URL not set)
    base_url = Config.BACKEND_URL
    if base_url:
        try:
            from ..assistant.hub_custom_bot_runner import register_webhook
            register_webhook(bot.id, token, base_url)
        except Exception as exc:
            _log.warning("create_custom_bot: webhook registration failed: %s", exc)

    return jsonify({"bot": _bot_card_data(bot, user.id)}), 201


@hub_bp.route("/bots/<bot_id>", methods=["PATCH"])
@jwt_required()
def update_custom_bot(bot_id):
    """Update display_name / personality / language for a custom bot."""
    user = _current_user()
    bot = HubBotIdentity.query.filter_by(
        id=bot_id, user_id=user.id, bot_type="custom"
    ).first_or_404()
    data = request.get_json(silent=True) or {}

    if "display_name" in data:
        bot.display_name = (data["display_name"] or "").strip() or bot.display_name

    settings = HubBotSettings.query.filter_by(bot_id=bot.id).first()
    if settings:
        for field in ("ai_personality_note", "response_language",
                      "extraction_sensitivity", "digest_enabled",
                      "digest_format", "notification_prefs"):
            if field in data:
                setattr(settings, field, data[field])
        settings.updated_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"ok": True, "bot": _bot_card_data(bot, user.id)})


@hub_bp.route("/bots/<bot_id>", methods=["DELETE"])
@jwt_required()
def delete_custom_bot(bot_id):
    """Soft-delete a custom bot (official bot cannot be deleted)."""
    from ..assistant.hub_crypto import _dec
    user = _current_user()
    bot = HubBotIdentity.query.filter_by(
        id=bot_id, user_id=user.id, bot_type="custom"
    ).first_or_404()

    # Unregister webhook before soft-deleting
    if bot.telegram_bot_token:
        try:
            from ..assistant.hub_custom_bot_runner import unregister_webhook
            unregister_webhook(_dec(bot.telegram_bot_token))
        except Exception as exc:
            _log.warning("delete_custom_bot: webhook removal failed bot=%s: %s", bot_id, exc)

    bot.is_active = False
    db.session.commit()
    return jsonify({"ok": True})


# ── Sprint 7: Knowledge Cards ─────────────────────────────────────────────────

def _card_dict(c) -> dict:
    from ..assistant.hub_crypto import _dec
    return {
        "id": c.id,
        "bot_id": c.bot_id,
        "title": _dec(c.title),
        "content": _dec(c.content),
        "tags": c.tags or [],
        "use_count": c.use_count,
        "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@hub_bp.route("/knowledge", methods=["GET"])
@jwt_required()
def list_knowledge_cards():
    user = _current_user()
    bot_id = request.args.get("bot_id")
    if not bot_id:
        bot = _get_or_create_official_bot(user.id)
        bot_id = bot.id
    else:
        HubBotIdentity.query.filter_by(id=bot_id, user_id=user.id).first_or_404()

    cards = HubKnowledgeCard.query.filter_by(
        bot_id=bot_id, user_id=user.id
    ).order_by(HubKnowledgeCard.use_count.desc(), HubKnowledgeCard.created_at.desc()).all()
    return jsonify({"cards": [_card_dict(c) for c in cards]})


@hub_bp.route("/knowledge", methods=["POST"])
@jwt_required()
def create_knowledge_card():
    from ..assistant.hub_crypto import _enc
    from ..assistant.hub_plan_limits import check_knowledge_cards, PlanLimitError

    user = _current_user()
    plan = user.subscription_tier or "free"
    data = request.get_json(silent=True) or {}

    bot_id = data.get("bot_id")
    if not bot_id:
        bot = _get_or_create_official_bot(user.id)
        bot_id = bot.id
    else:
        HubBotIdentity.query.filter_by(id=bot_id, user_id=user.id).first_or_404()

    try:
        check_knowledge_cards(user.id, bot_id, plan)
    except PlanLimitError as e:
        return jsonify(e.to_dict()), 402

    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    if not content:
        return jsonify({"error": "content required"}), 400

    card = HubKnowledgeCard(
        id=str(uuid.uuid4()),
        bot_id=bot_id,
        user_id=user.id,
        title=_enc(title[:100]),
        content=_enc(content[:2000]),
        tags=data.get("tags") or [],
    )
    db.session.add(card)
    db.session.commit()
    return jsonify({"card": _card_dict(card)}), 201


@hub_bp.route("/knowledge/<card_id>", methods=["PATCH"])
@jwt_required()
def update_knowledge_card(card_id):
    from ..assistant.hub_crypto import _enc
    user = _current_user()
    card = HubKnowledgeCard.query.filter_by(id=card_id, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}

    if "title" in data and data["title"]:
        card.title = _enc(data["title"][:100])
    if "content" in data and data["content"]:
        card.content = _enc(data["content"][:2000])
    if "tags" in data:
        card.tags = data["tags"] or []
    card.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"card": _card_dict(card)})


@hub_bp.route("/knowledge/<card_id>", methods=["DELETE"])
@jwt_required()
def delete_knowledge_card(card_id):
    user = _current_user()
    card = HubKnowledgeCard.query.filter_by(id=card_id, user_id=user.id).first_or_404()
    db.session.delete(card)
    db.session.commit()
    return jsonify({"ok": True})


@hub_bp.route("/knowledge/<card_id>/use", methods=["POST"])
@jwt_required()
def use_knowledge_card(card_id):
    user = _current_user()
    card = HubKnowledgeCard.query.filter_by(id=card_id, user_id=user.id).first_or_404()
    card.use_count = (card.use_count or 0) + 1
    card.last_used_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "use_count": card.use_count})


# ── Sprint 7C: Custom bot webhook receiver ────────────────────────────────────

@hub_bp.route("/webhook/<bot_id>", methods=["POST"])
def custom_bot_webhook(bot_id):
    """
    Receive Telegram updates for a custom bot via webhook.
    Dispatches @mention messages to hub_reply.handle_mention.
    No JWT — Telegram calls this directly.
    """
    from ..assistant.hub_crypto import _dec
    from ..assistant.hub_reply import handle_mention
    from ..app import create_app as _create_app

    # Verify the bot exists and is active
    bot = HubBotIdentity.query.filter_by(id=bot_id, bot_type="custom", is_active=True).first()
    if not bot:
        return jsonify({"ok": False}), 404

    payload = request.get_json(force=True, silent=True) or {}
    message = payload.get("message") or payload.get("edited_message")
    if not message:
        return jsonify({"ok": True}), 200

    chat = message.get("chat", {})
    chat_type = chat.get("type", "")
    if chat_type not in ("group", "supergroup"):
        return jsonify({"ok": True}), 200

    text = message.get("text") or ""
    bot_username = bot.telegram_bot_username or ""

    # Only handle messages that @mention this bot
    if f"@{bot_username}" not in text:
        return jsonify({"ok": True}), 200

    chat_id = chat.get("id")
    message_id = message.get("message_id")
    token = _dec(bot.telegram_bot_token) if bot.telegram_bot_token else None
    if not token:
        return jsonify({"ok": True}), 200

    try:
        flask_app = _create_app()
        handle_mention(
            bot_token=token,
            bot_username=bot_username,
            message_text=text,
            chat_id=chat_id,
            message_id=message_id,
            bot_id=bot_id,
            user_id=bot.user_id,
            flask_app=flask_app,
        )
    except Exception as exc:
        _log.warning("custom_bot_webhook: dispatch error bot=%s: %s", bot_id, exc)

    return jsonify({"ok": True}), 200


# ── Follow-ups ───────────────────────────────────────────────────────────────

def _followup_dict(f):
    from ..assistant.hub_crypto import _dec
    from ..assistant.hub_models import HubConnectedGroup
    group = HubConnectedGroup.query.get(f.source_group_id) if f.source_group_id else None
    return {
        "id": f.id,
        "commitment": _dec(f.commitment),
        "committed_by": f.committed_by,
        "due_hint": f.due_hint,
        "status": f.status,
        "group_id": f.source_group_id,
        "group_name": group.group_name if group else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
    }


@hub_bp.route("/follow-ups", methods=["GET"])
@jwt_required()
def list_follow_ups():
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)
    status_filter = request.args.get("status", "open")   # open | resolved | dismissed | all
    group_id = request.args.get("group_id")

    q = HubFollowUp.query.filter_by(user_id=user.id, bot_id=bot.id)
    if status_filter != "all":
        q = q.filter_by(status=status_filter)
    if group_id:
        q = q.filter_by(source_group_id=group_id)
    items = q.order_by(HubFollowUp.created_at.desc()).limit(50).all()
    return jsonify({"follow_ups": [_followup_dict(f) for f in items]})


@hub_bp.route("/follow-ups/<followup_id>/resolve", methods=["PATCH"])
@jwt_required()
def resolve_follow_up(followup_id):
    user = _current_user()
    fu = HubFollowUp.query.filter_by(id=followup_id, user_id=user.id).first_or_404()
    fu.status = "resolved"
    fu.resolved_at = datetime.utcnow()
    HubInboxItem.query.filter_by(item_type="follow_up", item_id=followup_id, user_id=user.id).delete()
    db.session.commit()
    return jsonify({"ok": True})


@hub_bp.route("/follow-ups/<followup_id>/dismiss", methods=["PATCH"])
@jwt_required()
def dismiss_follow_up(followup_id):
    user = _current_user()
    fu = HubFollowUp.query.filter_by(id=followup_id, user_id=user.id).first_or_404()
    fu.status = "dismissed"
    fu.dismissed_at = datetime.utcnow()
    HubInboxItem.query.filter_by(item_type="follow_up", item_id=followup_id, user_id=user.id).delete()
    db.session.commit()
    return jsonify({"ok": True})


# ── Cross-Group AI Summary ────────────────────────────────────────────────────

@hub_bp.route("/cross-group-summary", methods=["POST"])
@jwt_required()
def cross_group_summary():
    """
    Generate an executive AI narrative across all connected groups for a time range.
    Caches result in Redis for 30 minutes per user+range combination.
    """
    user = _current_user()
    bot = _get_or_create_official_bot(user.id)

    body = request.get_json(silent=True) or {}
    range_key = body.get("range", "this_week")
    start_date_str = body.get("start_date")
    end_date_str = body.get("end_date")

    now = datetime.utcnow()

    # Resolve date window
    if range_key == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif range_key == "yesterday":
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)
    elif range_key == "this_week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif range_key == "last_7_days":
        start = now - timedelta(days=7)
        end = now
    elif range_key == "last_30_days":
        start = now - timedelta(days=30)
        end = now
    elif range_key == "custom" and start_date_str and end_date_str:
        try:
            start = datetime.strptime(start_date_str, "%Y-%m-%d")
            end = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    else:
        start = now - timedelta(days=7)
        end = now

    # Redis cache check
    cache_key = f"cross_summary:{user.id}:{range_key}:{start.date()}:{end.date()}"
    try:
        import redis as redis_lib
        r = redis_lib.from_url(Config.REDIS_URL, decode_responses=True)
        cached = r.get(cache_key)
        if cached:
            import json as _json
            return jsonify({**_json.loads(cached), "cached": True})
    except Exception:
        r = None

    # Gather extracted items across all connected groups
    connected_groups = HubConnectedGroup.query.filter_by(
        bot_id=bot.id, user_id=user.id, is_active=True
    ).all()

    if not connected_groups:
        return jsonify({"error": "No connected groups. Add the bot to a group first."}), 400

    group_ids = [g.id for g in connected_groups]
    group_name_map = {g.id: (g.group_name or f"Group {g.telegram_group_id}") for g in connected_groups}

    tasks = HubTask.query.filter(
        HubTask.user_id == user.id,
        HubTask.bot_id == bot.id,
        HubTask.source_group_id.in_(group_ids),
        HubTask.created_at.between(start, end),
    ).all()

    decisions = HubDecision.query.filter(
        HubDecision.user_id == user.id,
        HubDecision.bot_id == bot.id,
        HubDecision.source_group_id.in_(group_ids),
        HubDecision.created_at.between(start, end),
    ).all()

    meetings = HubMeeting.query.filter(
        HubMeeting.user_id == user.id,
        HubMeeting.bot_id == bot.id,
        HubMeeting.source_group_id.in_(group_ids),
        HubMeeting.created_at.between(start, end),
    ).all()

    reminders = HubReminder.query.filter(
        HubReminder.user_id == user.id,
        HubReminder.bot_id == bot.id,
        HubReminder.source_group_id.in_(group_ids),
        HubReminder.created_at.between(start, end),
    ).all()

    total_items = len(tasks) + len(decisions) + len(meetings) + len(reminders)
    if total_items == 0:
        return jsonify({
            "summary": "No activity was captured across your groups in this time range. Make sure the bot is active and observing your groups.",
            "groups": [{"id": g.id, "name": group_name_map[g.id]} for g in connected_groups],
            "counts": {"tasks": 0, "decisions": 0, "meetings": 0, "reminders": 0},
            "generated_at": now.isoformat(),
            "cached": False,
        })

    # Build structured context for GPT
    def _group_label(gid):
        return group_name_map.get(gid, "Unknown Group")

    context_lines = []
    if tasks:
        context_lines.append("TASKS:")
        for t in tasks[:30]:
            line = f"  - [{_group_label(t.source_group_id)}] {t.title}"
            if t.assignee:
                line += f" (assigned to {t.assignee})"
            if t.due_date:
                line += f" — due {t.due_date.strftime('%b %d')}"
            if t.priority and t.priority != "normal":
                line += f" [{t.priority} priority]"
            context_lines.append(line)

    if decisions:
        context_lines.append("DECISIONS:")
        for d in decisions[:20]:
            line = f"  - [{_group_label(d.source_group_id)}] {d.content}"
            if d.made_by:
                line += f" (by {d.made_by})"
            context_lines.append(line)

    if meetings:
        context_lines.append("MEETINGS:")
        for m in meetings[:15]:
            line = f"  - [{_group_label(m.source_group_id)}] {m.title}"
            if m.scheduled_at:
                line += f" — {m.scheduled_at.strftime('%b %d %H:%M UTC')}"
            context_lines.append(line)

    if reminders:
        context_lines.append("REMINDERS:")
        for rem in reminders[:15]:
            line = f"  - [{_group_label(rem.source_group_id)}] {rem.content}"
            if rem.remind_at:
                line += f" — {rem.remind_at.strftime('%b %d %H:%M UTC')}"
            context_lines.append(line)

    context_text = "\n".join(context_lines)
    range_label = {
        "today": "today",
        "yesterday": "yesterday",
        "this_week": "this week",
        "last_7_days": "the last 7 days",
        "last_30_days": "the last 30 days",
        "custom": f"{start.strftime('%b %d')} – {end.strftime('%b %d')}",
    }.get(range_key, "the selected period")

    group_names_list = ", ".join(group_name_map.values())

    system_prompt = (
        "You are an executive AI assistant. Your job is to write a concise, insightful narrative "
        "summary of what happened across a user's Telegram groups. "
        "Write in second person ('Your teams...', 'Across your groups...'). "
        "Be direct and specific — mention group names, key assignees, and important deadlines. "
        "Highlight patterns, risks, and what needs attention. "
        "Format as 2–4 short paragraphs. No bullet points. No headers. No markdown. "
        "Sound like a smart chief of staff briefing an executive."
    )

    user_prompt = (
        f"Here is what was captured across {len(connected_groups)} groups ({group_names_list}) "
        f"during {range_label}:\n\n{context_text}\n\n"
        f"Write an executive narrative summary."
    )

    try:
        from openai import OpenAI
        from ..assistant.ai_key_resolver import get_workspace_ai_key, QuotaExceededError, record_token_usage
        try:
            key_config = get_workspace_ai_key(user)
        except QuotaExceededError:
            return jsonify({"error": "Daily AI quota exceeded. Add your own API key in AI Settings."}), 429
        if not key_config.get("api_key"):
            return jsonify({"error": "AI service not configured."}), 503

        client_kwargs = {"api_key": key_config["api_key"]}
        if key_config.get("base_url"):
            client_kwargs["base_url"] = key_config["base_url"]
        client = OpenAI(**client_kwargs)
        resp = client.chat.completions.create(
            model=key_config.get("model") or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=600,
        )
        summary_text = resp.choices[0].message.content.strip()
        if key_config.get("source") == "platform":
            record_token_usage(user, resp.usage.total_tokens if resp.usage else 0)
    except Exception as exc:
        _log.warning("cross_group_summary: OpenAI call failed: %s", exc)
        return jsonify({"error": "AI generation failed. Please try again."}), 503

    # Build groups metadata
    groups_meta = []
    group_item_counts = {}
    for item_list, label in [(tasks, "tasks"), (decisions, "decisions"), (meetings, "meetings"), (reminders, "reminders")]:
        for item in item_list:
            gid = item.source_group_id
            if gid not in group_item_counts:
                group_item_counts[gid] = 0
            group_item_counts[gid] += 1

    for g in connected_groups:
        groups_meta.append({
            "id": g.id,
            "name": group_name_map[g.id],
            "item_count": group_item_counts.get(g.id, 0),
        })

    result = {
        "summary": summary_text,
        "groups": groups_meta,
        "counts": {
            "tasks": len(tasks),
            "decisions": len(decisions),
            "meetings": len(meetings),
            "reminders": len(reminders),
        },
        "range": range_key,
        "generated_at": now.isoformat(),
        "cached": False,
    }

    # Cache for 30 minutes
    try:
        if r:
            import json as _json
            r.setex(cache_key, 1800, _json.dumps(result))
    except Exception:
        pass

    return jsonify(result)
