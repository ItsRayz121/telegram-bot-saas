"""
Smart Suggestion Engine — context-aware, non-repetitive suggestions.

Rules:
- Never suggest something the user just did
- Rotate based on workspace state, not hardcoded lists
- Priority: urgent > actionable > exploratory
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)

# Suggestion pool keyed by intent/trigger
_POOL = {
    "has_meetings_no_tasks": [
        {"label": "📋 Create follow-up tasks", "value": "Create task"},
        {"label": "📝 Add meeting notes", "value": "Note this:"},
        {"label": "📆 Check schedule", "value": "What's on my schedule?"},
    ],
    "has_tasks_no_progress": [
        {"label": "▶️ What's in progress?", "value": "Show my tasks"},
        {"label": "🎯 Start a task", "value": "Show my tasks"},
        {"label": "🔴 High priority first", "value": "Show my tasks"},
    ],
    "idle_workspace": [
        {"label": "📅 Plan your day", "value": "Analyze my day"},
        {"label": "📝 Save a note", "value": "Note this:"},
        {"label": "⏰ Set a reminder", "value": "Remind me"},
        {"label": "📋 Create a task", "value": "Create task"},
    ],
    "group_issues": [
        {"label": "🚨 View group issues", "value": "Any issues in my groups?"},
        {"label": "📊 Group health", "value": "Show group stats"},
    ],
    "upcoming_meetings": [
        {"label": "📅 View schedule", "value": "What's on my schedule?"},
        {"label": "📝 Prepare notes", "value": "Note this:"},
        {"label": "🔔 Set a reminder", "value": "Remind me"},
    ],
    "post_meeting": [
        {"label": "📋 Create follow-ups", "value": "Create task"},
        {"label": "📝 Add meeting notes", "value": "Note this:"},
        {"label": "📧 Schedule follow-up", "value": "Book a meeting"},
    ],
    "default": [
        {"label": "📅 My schedule", "value": "What's on my schedule?"},
        {"label": "🧠 Analyze my day", "value": "Analyze my day"},
        {"label": "📋 My tasks", "value": "Show my tasks"},
        {"label": "📝 My notes", "value": "Show my notes"},
        {"label": "👥 Group health", "value": "Any issues in my groups?"},
        {"label": "⏰ Set reminder", "value": "Remind me"},
    ],
}


def get_smart_suggestions(user_id: int, last_intent: str | None = None, limit: int = 3) -> list[dict]:
    """
    Return context-aware suggestions that are not repetitive with the last intent.
    Uses workspace state to determine what's most useful right now.
    """
    try:
        return _build_suggestions(user_id, last_intent, limit)
    except Exception as exc:
        _log.warning("suggestion_engine failed: %s", exc)
        return _rotate(_POOL["default"], user_id, last_intent, limit)


def _build_suggestions(user_id: int, last_intent: str | None, limit: int) -> list[dict]:
    from ..models import Meeting, Task, TelegramGroup, GroupDailySignal
    from datetime import date

    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(hours=23, minutes=59)

    # Gather lightweight counts — no heavy queries
    meeting_count = Meeting.query.filter(
        Meeting.owner_user_id == user_id,
        Meeting.scheduled_at >= today_start,
        Meeting.scheduled_at <= today_end,
        Meeting.is_complete == False,
    ).count()

    task_todo = Task.query.filter_by(user_id=user_id, status="todo").count()
    task_doing = Task.query.filter_by(user_id=user_id, status="doing").count()

    group_ids = [
        g.telegram_group_id
        for g in TelegramGroup.query.filter_by(owner_user_id=user_id, is_disabled=False).all()
    ]
    alert_count = 0
    if group_ids:
        today = date.today()
        alert_count = GroupDailySignal.query.filter(
            GroupDailySignal.telegram_group_id.in_(group_ids),
            GroupDailySignal.date == today,
            GroupDailySignal.health_status.in_(["watch", "critical"]),
        ).count()

    # Determine context bucket — highest priority first
    candidates: list[dict] = []

    if alert_count:
        candidates.extend(_POOL["group_issues"])

    if meeting_count and task_todo == 0:
        candidates.extend(_POOL["has_meetings_no_tasks"])
    elif meeting_count:
        candidates.extend(_POOL["upcoming_meetings"])

    if task_todo > 0 and task_doing == 0:
        candidates.extend(_POOL["has_tasks_no_progress"])

    if not meeting_count and task_todo == 0:
        candidates.extend(_POOL["idle_workspace"])

    # Always pad with default pool
    candidates.extend(_POOL["default"])

    return _rotate(candidates, user_id, last_intent, limit)


def _rotate(pool: list[dict], user_id: int, last_intent: str | None, limit: int) -> list[dict]:
    """Deduplicate and rotate pool entries. Skip any whose value matches the last intent."""
    intent_skip_values = {
        "schedule_meeting": {"Book a meeting", "Book meeting"},
        "create_reminder": {"Remind me", "Set reminder"},
        "create_task": {"Create task"},
        "list_tasks": {"Show my tasks"},
        "list_notes": {"Show my notes"},
        "upcoming_schedule": {"What's on my schedule?"},
        "analyze_day": {"Analyze my day"},
        "group_query": {"Any issues in my groups?"},
    }
    skip = intent_skip_values.get(last_intent or "", set())

    seen_values: set[str] = set()
    result = []
    for s in pool:
        v = s.get("value", "")
        if v in skip or v in seen_values:
            continue
        seen_values.add(v)
        result.append(s)
        if len(result) >= limit:
            break

    # Deterministic rotation based on user_id + hour so suggestions shift over time
    if len(result) < limit:
        result.extend(_POOL["default"][:limit - len(result)])

    # Rotate by hour so suggestions shift every hour
    hour_offset = (user_id + datetime.utcnow().hour) % max(len(result), 1)
    result = result[hour_offset:] + result[:hour_offset]
    return result[:limit]
