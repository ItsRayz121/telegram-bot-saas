"""Reminder creation — multi-step flow."""
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
                {"label": "Custom…", "value": None},
            ],
        }

    # Step 2 — need time
    if not data["_resolved_iso"] and not data["datetime_hint"]:
        save_state(user_id, "create_reminder", data, "datetime_hint")
        return {"reply": f'When should I remind you about "{data["text"]}"?',
                "intent": "create_reminder", "data": None, "suggestions": time_suggestions()}

    if not data["_resolved_iso"] and data["datetime_hint"]:
        dt = resolve_datetime(key_info, data["datetime_hint"], data["timezone"])
        if not dt.get("iso"):
            save_state(user_id, "create_reminder", data, "datetime_hint")
            return {"reply": "I couldn't parse that time. When exactly should I remind you?",
                    "intent": "create_reminder", "data": None, "suggestions": time_suggestions()}
        data["_resolved_iso"] = dt["iso"]
        data["_resolved_human"] = dt["human"]

    # Step 3 — save
    reminder = WorkspaceReminder(
        owner_user_id=user_id,
        reminder_text=data["text"][:500],
        remind_at=datetime.fromisoformat(data["_resolved_iso"]),
    )
    db.session.add(reminder)
    db.session.commit()
    clear_state(user_id)

    try:
        from ...assistant.context_service import AssistantContextService
        AssistantContextService.invalidate(user_id)
    except Exception:
        pass

    return {
        "reply": f"🔔 Reminder set!\n\n📌 {data['text']}\n🕒 {data['_resolved_human']}",
        "intent": "create_reminder",
        "data": reminder.to_dict(),
        "suggestions": [
            {"label": "Add another reminder", "value": "Remind me"},
            {"label": "Show my reminders", "value": "show my reminders"},
        ],
    }
