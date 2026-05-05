"""Task, meeting list, and reminder list handlers."""
from __future__ import annotations

import re
from datetime import datetime

from ._ai import resolve_datetime
from ._state import save_state


def handle_create_task(user_id: int, parsed: dict | str, key_info: dict = None) -> dict:
    from ...models import db, Task

    # Accept both legacy string title and new parsed dict
    if isinstance(parsed, str):
        title = parsed
        priority = "medium"
        description = None
        due_at = None
        datetime_hint = None
        user_tz = "UTC"
    else:
        title = parsed.get("title", "")
        priority = _normalize_priority(parsed.get("priority") or "medium")
        description = parsed.get("notes") or parsed.get("description")
        datetime_hint = parsed.get("datetime_hint")
        user_tz = parsed.get("timezone") or "UTC"
        due_at = None

    if not title or not title.strip():
        save_state(user_id, "create_task", {}, "title")
        return {"reply": "What task should I add?", "intent": "create_task", "data": None}

    # Resolve due date if provided
    if datetime_hint and key_info:
        try:
            dt = resolve_datetime(key_info, datetime_hint, user_tz)
            if dt.get("iso"):
                due_at = datetime.fromisoformat(dt["iso"])
        except Exception:
            pass

    task = Task(
        user_id=user_id,
        title=title.strip()[:500],
        status="todo",
        priority=priority,
        source="bot",
        description=description,
        due_at=due_at,
    )
    db.session.add(task)
    db.session.commit()

    reply = f'✅ Task added: **"{task.title}"**'
    if priority == "high":
        reply += " 🔴 High priority"
    elif priority == "low":
        reply += " 🔵 Low priority"
    if due_at:
        reply += f"\n📅 Due: {due_at.strftime('%b %d, %I:%M %p UTC')}"
    if description:
        reply += f"\n📝 {description[:100]}"

    return {
        "reply": reply,
        "intent": "create_task",
        "data": task.to_dict(),
        "suggestions": [
            {"label": "➕ Another Task", "value": "Create task"},
            {"label": "📋 All Tasks", "value": "Show my tasks"},
            {"label": "⏰ Set Reminder", "value": "Remind me"},
        ],
    }


def _normalize_priority(p: str) -> str:
    p = (p or "").lower()
    if p in ("high", "urgent", "critical", "asap"):
        return "high"
    if p in ("low", "whenever", "optional"):
        return "low"
    return "medium"


def handle_list_tasks(user_id: int) -> dict:
    from ...models import Task
    tasks = (
        Task.query.filter_by(user_id=user_id, status="todo")
        .order_by(Task.created_at.desc()).limit(10).all()
    )
    if not tasks:
        return {
            "reply": "No pending tasks right now.",
            "intent": "list_tasks",
            "data": {"tasks": []},
            "suggestions": [{"label": "➕ Create Task", "value": "Create task"}],
        }

    high = [t for t in tasks if t.priority == "high"]
    normal = [t for t in tasks if t.priority != "high"]

    lines = []
    if high:
        lines.append("**High Priority:**")
        lines.extend(f"🔴 {t.title}" + (f" (due {t.due_at.strftime('%b %d')})" if t.due_at else "") for t in high)
    if normal:
        if high:
            lines.append("")
        lines.extend(f"• {t.title}" + (f" (due {t.due_at.strftime('%b %d')})" if t.due_at else "") for t in normal)

    reply = f"You have {len(tasks)} pending task{'s' if len(tasks) != 1 else ''}:\n\n" + "\n".join(lines)
    return {"reply": reply, "intent": "list_tasks", "data": {"tasks": [t.to_dict() for t in tasks]}}


def handle_list_meetings(user_id: int) -> dict:
    from ...models import Meeting
    now = datetime.utcnow()
    meetings = (
        Meeting.query
        .filter(Meeting.owner_user_id == user_id, Meeting.scheduled_at >= now, Meeting.is_complete == False)
        .order_by(Meeting.scheduled_at.asc()).limit(10).all()
    )
    if not meetings:
        return {
            "reply": "No upcoming meetings. Want to schedule one?",
            "intent": "list_meetings",
            "data": {"meetings": []},
            "suggestions": [{"label": "📅 Schedule Meeting", "value": "Schedule a meeting"}],
        }

    lines = []
    for m in meetings:
        line = f"• **{m.title}** — {m.scheduled_at.strftime('%b %d, %I:%M %p UTC')}"
        if m.participants:
            line += f" (with {', '.join(m.participants[:2])})"
        lines.append(line)

    return {
        "reply": "Your upcoming meetings:\n\n" + "\n".join(lines),
        "intent": "list_meetings",
        "data": {"meetings": [m.to_dict() for m in meetings]},
    }


def handle_list_reminders(user_id: int) -> dict:
    from ...models import WorkspaceReminder
    now = datetime.utcnow()
    reminders = (
        WorkspaceReminder.query
        .filter(WorkspaceReminder.owner_user_id == user_id,
                WorkspaceReminder.remind_at >= now,
                WorkspaceReminder.is_delivered == False)
        .order_by(WorkspaceReminder.remind_at.asc()).limit(10).all()
    )
    if not reminders:
        return {
            "reply": "No upcoming reminders.",
            "intent": "list_reminders",
            "data": {"reminders": []},
            "suggestions": [{"label": "⏰ Set Reminder", "value": "Remind me"}],
        }
    lines = [f"• {r.reminder_text} — {r.remind_at.strftime('%b %d, %I:%M %p UTC')}" for r in reminders]
    return {
        "reply": "Your upcoming reminders:\n\n" + "\n".join(lines),
        "intent": "list_reminders",
        "data": {"reminders": [r.to_dict() for r in reminders]},
    }
