"""
Assistant Hub API — Sprint 1 routes.

All routes use /api/hub prefix.

Endpoints:
  GET  /api/hub/status               — lazy-create global record, return hub state
  GET  /api/hub/bots                 — list bot identities for user
  POST /api/hub/bots/official/init   — create official bot identity (first Hub enable)
  GET  /api/hub/bots/official        — official bot card data
  GET  /api/hub/bots/official/settings — effective settings (via resolver)
  PATCH /api/hub/bots/official/settings — save settings
  GET  /api/hub/bots/official/groups — connected groups list
  GET  /api/hub/bots/official/stats  — card stats (task count, last summary)
  GET  /api/hub/limits               — plan limits for current user
  POST /api/hub/webhook              — Telegram webhook receiver (official bot, Hub context)
"""
import logging
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User
from ..assistant.hub_models import (
    AssistantHubGlobal, HubBotIdentity, HubBotSettings,
    HubConnectedGroup, HubTask, HubReminder, HubDecision,
    HubMeeting, HubNote, HubSystemAutomation, HubBotAutomationSetting,
    HubInboxItem,
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
        "category": group.category,
        "is_active": group.is_active,
        "pause_reason": group.pause_reason,
        "consent_confirmed_at": group.consent_confirmed_at.isoformat() if group.consent_confirmed_at else None,
        "intro_sent": group.intro_sent,
        "is_public_group": group.is_public_group,
        "silence_start": group.silence_start.strftime("%H:%M") if group.silence_start else None,
        "silence_end": group.silence_end.strftime("%H:%M") if group.silence_end else None,
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
