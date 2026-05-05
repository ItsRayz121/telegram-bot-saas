"""Reminder creation — smart extraction + natural 1-2 step flow."""
from __future__ import annotations

from datetime import datetime

from ._ai import resolve_datetime
from ._state import clear_state, save_state
from ._suggestions import time_suggestions


def handle_create_reminder(user_id: int, parsed: dict, key_info: dict, user_tz: str | None) -> dict:
    from ...models import db, WorkspaceReminder

    data = {
        "text":            parsed.get("title") or parsed.get("text"),
        "datetime_hint":   parsed.get("datetime_hint"),
        "timezone":        parsed.get("timezone") or user_tz or "UTC",
        "_resolved_iso":   parsed.get("_resolved_iso"),
        "_resolved_human": parsed.get("_resolved_human"),
        "priority":        parsed.get("priority") or "medium",
        "recurrence":      parsed.get("recurrence"),
        "related_person":  parsed.get("related_person"),
        "notes":           parsed.get("notes"),
    }

    # Step 1 — need reminder text
    if not data["text"]:
        save_state(user_id, "create_reminder", data, "text")
        return {
            "reply": "Sure — what should I remind you about?",
            "intent": "create_reminder",
            "data": None,
            "suggestions": [
                {"label": "Follow up on email", "value": "Follow up on email"},
                {"label": "Review document", "value": "Review document"},
                {"label": "Team check-in", "value": "Team check-in"},
            ],
        }

    # Step 2 — need time
    if not data["_resolved_iso"] and not data["datetime_hint"]:
        save_state(user_id, "create_reminder", data, "datetime_hint")
        return {
            "reply": f'When should I remind you about "{data["text"]}"?',
            "intent": "create_reminder",
            "data": None,
            "suggestions": time_suggestions(),
        }

    # Resolve datetime
    if not data["_resolved_iso"] and data["datetime_hint"]:
        dt = resolve_datetime(key_info, data["datetime_hint"], data["timezone"])
        if not dt.get("iso"):
            save_state(user_id, "create_reminder", data, "datetime_hint")
            return {
                "reply": "I couldn't parse that time. When exactly should I remind you?",
                "intent": "create_reminder",
                "data": None,
                "suggestions": time_suggestions(),
            }
        data["_resolved_iso"] = dt["iso"]
        data["_resolved_human"] = dt["human"]

    # Save directly — no confirmation step for reminders (quick and natural)
    reminder = WorkspaceReminder(
        owner_user_id=user_id,
        reminder_text=data["text"][:500],
        remind_at=datetime.fromisoformat(data["_resolved_iso"]),
    )

    # Set extended fields if they exist on the model
    for field in ("priority", "recurrence", "related_person", "notes"):
        if data.get(field) is not None and hasattr(reminder, field):
            setattr(reminder, field, data[field])

    db.session.add(reminder)
    db.session.commit()
    clear_state(user_id)

    try:
        from ...assistant.context_service import AssistantContextService
        AssistantContextService.invalidate(user_id)
    except Exception:
        pass
    try:
        from ...assistant.profile_service import record_action
        record_action(user_id, "create_reminder", reminder.to_dict())
        from ...models import db as _db
        _db.session.commit()
    except Exception:
        pass

    reply = f"🔔 Got it — I'll remind you to **{data['text']}** on {data['_resolved_human']}."
    if data.get("related_person"):
        reply += f" (re: {data['related_person']})"
    if data.get("recurrence"):
        reply += f"\n🔁 Repeating: {data['recurrence']}"

    return {
        "reply": reply,
        "intent": "create_reminder",
        "data": reminder.to_dict(),
        "suggestions": [
            {"label": "⏰ Another Reminder", "value": "Remind me"},
            {"label": "📋 My Reminders", "value": "Show my reminders"},
            {"label": "✅ Add Task", "value": "Create task"},
        ],
    }
