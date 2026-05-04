"""Task, meeting list, and reminder list handlers."""
from __future__ import annotations

from datetime import datetime

from ._state import save_state


def handle_create_task(user_id: int, title: str, priority: str = "medium") -> dict:
    from ...models import db, Task
    if not title or not title.strip():
        save_state(user_id, "create_task", {}, "title")
        return {"reply": "What task should I add?", "intent": "create_task", "data": None}
    task = Task(user_id=user_id, title=title.strip()[:500], status="todo", source="bot")
    db.session.add(task)
    db.session.commit()
    return {
        "reply": f'✅ Task added: "{task.title}"',
        "intent": "create_task",
        "data": task.to_dict(),
        "suggestions": [
            {"label": "Add another task", "value": None},
            {"label": "Show all tasks", "value": "show my tasks"},
        ],
    }


def handle_list_tasks(user_id: int) -> dict:
    from ...models import Task
    tasks = (
        Task.query.filter_by(user_id=user_id, status="todo")
        .order_by(Task.created_at.desc()).limit(10).all()
    )
    if not tasks:
        return {"reply": 'No pending tasks. Try "Create task: your task".', "intent": "list_tasks", "data": {"tasks": []}}
    lines = [f"• {t.title}" for t in tasks]
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
            "reply": "You have no upcoming meetings. Want to schedule one?",
            "intent": "list_meetings", "data": {"meetings": []},
            "suggestions": [{"label": "Book a meeting", "value": "Book a meeting"}],
        }
    lines = [f"• {m.title} — {m.scheduled_at.strftime('%b %d, %I:%M %p UTC')}" for m in meetings]
    return {"reply": "Here are your upcoming meetings:\n\n" + "\n".join(lines),
            "intent": "list_meetings", "data": {"meetings": [m.to_dict() for m in meetings]}}


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
            "reply": "You have no upcoming reminders.",
            "intent": "list_reminders", "data": {"reminders": []},
            "suggestions": [{"label": "Set a reminder", "value": "Remind me"}],
        }
    lines = [f"• {r.reminder_text} — {r.remind_at.strftime('%b %d, %I:%M %p UTC')}" for r in reminders]
    return {"reply": "Here are your upcoming reminders:\n\n" + "\n".join(lines),
            "intent": "list_reminders", "data": {"reminders": [r.to_dict() for r in reminders]}}
