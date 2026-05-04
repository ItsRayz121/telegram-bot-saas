"""Upcoming schedule — unified timeline view."""
from __future__ import annotations

from datetime import datetime, timedelta


def handle_upcoming_schedule(user_id: int) -> dict:
    from ...models import Meeting, WorkspaceReminder, Task

    now = datetime.utcnow()
    today_end = now.replace(hour=23, minute=59, second=59)
    tomorrow_end = today_end + timedelta(days=1)

    meetings = (
        Meeting.query
        .filter(Meeting.owner_user_id == user_id, Meeting.scheduled_at >= now, Meeting.is_complete == False)
        .order_by(Meeting.scheduled_at.asc()).limit(20).all()
    )
    reminders = (
        WorkspaceReminder.query
        .filter(WorkspaceReminder.owner_user_id == user_id,
                WorkspaceReminder.remind_at >= now,
                WorkspaceReminder.is_delivered == False)
        .order_by(WorkspaceReminder.remind_at.asc()).limit(20).all()
    )
    tasks = (
        Task.query
        .filter(Task.user_id == user_id, Task.status == "todo",
                Task.due_at != None, Task.due_at >= now)
        .order_by(Task.due_at.asc()).limit(10).all()
    )

    events = (
        [{"dt": m.scheduled_at, "type": "📅 Meeting",  "text": m.title}         for m in meetings] +
        [{"dt": r.remind_at,    "type": "🔔 Reminder", "text": r.reminder_text} for r in reminders] +
        [{"dt": t.due_at,       "type": "✅ Task",     "text": t.title}         for t in tasks]
    )

    if not events:
        return {"reply": "Your calendar is clear — nothing scheduled coming up! 🎉",
                "intent": "upcoming_schedule",
                "data": {"meetings": [], "reminders": [], "tasks": []}}

    events.sort(key=lambda e: e["dt"])
    today_items    = [e for e in events if e["dt"] <= today_end]
    tomorrow_items = [e for e in events if today_end < e["dt"] <= tomorrow_end]
    later_items    = [e for e in events if e["dt"] > tomorrow_end]

    lines = []
    if today_items:
        lines.append("Today:")
        for e in today_items:
            lines.append(f"  • {e['dt'].strftime('%I:%M %p')} — {e['type']}: {e['text']}")
    if tomorrow_items:
        lines.append("\nTomorrow:")
        for e in tomorrow_items:
            lines.append(f"  • {e['dt'].strftime('%I:%M %p')} — {e['type']}: {e['text']}")
    if later_items:
        lines.append("\nUpcoming:")
        for e in later_items[:8]:
            lines.append(f"  • {e['dt'].strftime('%b %d, %I:%M %p')} — {e['type']}: {e['text']}")

    reply = "Here's your upcoming schedule:\n\n" + "\n".join(lines)
    if not today_items:
        reply += "\n\n✨ Nothing scheduled for today."

    return {
        "reply": reply,
        "intent": "upcoming_schedule",
        "data": {
            "meetings":  [m.to_dict() for m in meetings],
            "reminders": [r.to_dict() for r in reminders],
            "tasks":     [t.to_dict() for t in tasks],
        },
    }
