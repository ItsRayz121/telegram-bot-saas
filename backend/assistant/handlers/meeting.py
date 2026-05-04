"""Meeting creation — professional 6-step multi-turn flow."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ._ai import resolve_datetime
from ._state import clear_state, save_state
from ._suggestions import (
    time_suggestions, meeting_title_suggestions,
    reminder_suggestions, skip_suggestions, yes_no_suggestions,
    reminder_label,
)

_log = logging.getLogger(__name__)


def handle_schedule_meeting(user_id: int, parsed: dict, key_info: dict, user_tz: str | None) -> dict:
    from ...models import db, Meeting

    data = {
        "title":            parsed.get("title"),
        "datetime_hint":    parsed.get("datetime_hint"),
        "timezone":         parsed.get("timezone") or user_tz or "UTC",
        "_resolved_iso":    parsed.get("_resolved_iso"),
        "_resolved_human":  parsed.get("_resolved_human"),
        "reminder_minutes": parsed.get("reminder_minutes"),
        "notes":            parsed.get("notes"),
        "resource_url":     parsed.get("resource_url"),
        "_reminder_asked":  parsed.get("_reminder_asked", False),
        "_notes_asked":     parsed.get("_notes_asked", False),
        "_resources_asked": parsed.get("_resources_asked", False),
    }

    # Step 1 — need title
    if not data["title"]:
        save_state(user_id, "schedule_meeting", data, "title")
        return {"reply": "Sure — what should I call this meeting?", "intent": "schedule_meeting",
                "data": None, "suggestions": meeting_title_suggestions()}

    # Step 2 — need time
    if not data["_resolved_iso"] and not data["datetime_hint"]:
        save_state(user_id, "schedule_meeting", data, "datetime_hint")
        return {"reply": f'When should I schedule "{data["title"]}"?', "intent": "schedule_meeting",
                "data": None, "suggestions": time_suggestions()}

    # Resolve datetime hint → ISO
    if not data["_resolved_iso"] and data["datetime_hint"]:
        dt = resolve_datetime(key_info, data["datetime_hint"], data["timezone"])
        if not dt.get("iso"):
            save_state(user_id, "schedule_meeting", data, "datetime_hint")
            return {"reply": f'I couldn\'t parse "{data["datetime_hint"]}". When should I schedule it?',
                    "intent": "schedule_meeting", "data": None, "suggestions": time_suggestions()}
        data["_resolved_iso"] = dt["iso"]
        data["_resolved_human"] = dt["human"]

    # Step 3 — reminder preference
    if not data["_reminder_asked"] and data["reminder_minutes"] is None:
        data["_reminder_asked"] = True
        save_state(user_id, "schedule_meeting", data, "reminder")
        return {
            "reply": f'Got it — "{data["title"]}" on {data["_resolved_human"]}.\n\nDo you want a reminder before the meeting?',
            "intent": "schedule_meeting", "data": None, "suggestions": reminder_suggestions(),
        }

    # Step 4 — notes/agenda
    if not data["_notes_asked"] and data["notes"] is None:
        data["_notes_asked"] = True
        save_state(user_id, "schedule_meeting", data, "notes")
        return {"reply": "Any agenda or notes to attach? (topics, goals, context)",
                "intent": "schedule_meeting", "data": None, "suggestions": skip_suggestions()}

    # Step 5 — resources/links
    if not data["_resources_asked"] and data["resource_url"] is None:
        data["_resources_asked"] = True
        save_state(user_id, "schedule_meeting", data, "resource_url")
        return {"reply": "Do you want to attach any links or resources? (doc, agenda, Zoom link)",
                "intent": "schedule_meeting", "data": None, "suggestions": skip_suggestions()}

    # Step 6 — confirmation
    if not parsed.get("_confirmed"):
        summary = (
            f"Here's your meeting summary:\n\n"
            f"📌 Title: {data['title']}\n"
            f"🕒 Time: {data['_resolved_human']}\n"
            f"🔔 Reminder: {reminder_label(data.get('reminder_minutes'))}\n"
            f"📝 Notes: {data.get('notes') or 'None'}\n"
            f"🔗 Resource: {data.get('resource_url') or 'None'}\n\n"
            f"Should I save it?"
        )
        data["_confirmed"] = False
        save_state(user_id, "schedule_meeting", data, "confirm")
        return {"reply": summary, "intent": "schedule_meeting", "data": None, "suggestions": yes_no_suggestions()}

    # Step 7 — save
    scheduled_at = datetime.fromisoformat(data["_resolved_iso"])
    existing = Meeting.query.filter(
        Meeting.owner_user_id == user_id,
        Meeting.title.ilike(data["title"]),
        Meeting.scheduled_at.between(scheduled_at - timedelta(minutes=30), scheduled_at + timedelta(minutes=30)),
        Meeting.is_complete == False,
    ).first()
    if existing:
        clear_state(user_id)
        return {"reply": f'You already have "{existing.title}" scheduled around that time. No duplicate created.',
                "intent": "schedule_meeting", "data": existing.to_dict()}

    resources = []
    if data.get("resource_url"):
        rtype = "link" if data["resource_url"].startswith("http") else "note"
        resources = [{"type": rtype, "value": data["resource_url"], "label": ""}]

    meeting = Meeting(
        owner_user_id=user_id,
        title=data["title"],
        scheduled_at=scheduled_at,
        timezone=data["timezone"],
        priority="medium",
        remind_before_minutes=data.get("reminder_minutes") or 15,
        notes=data.get("notes"),
        resources=resources or None,
    )
    db.session.add(meeting)
    db.session.commit()
    clear_state(user_id)

    try:
        from ...assistant.context_service import AssistantContextService
        AssistantContextService.invalidate(user_id)
    except Exception:
        pass
    try:
        from ...integrations.dispatcher import fire_event
        fire_event(user_id, "meeting.created", meeting.to_dict())
    except Exception:
        pass
    try:
        from ...assistant.profile_service import record_action
        record_action(user_id, "schedule_meeting", {**data, **meeting.to_dict()})
        from ...models import db as _db
        _db.session.commit()
    except Exception:
        pass

    suggestions = []
    if not data.get("notes"):
        suggestions.append({"label": "Add agenda", "value": f"Add notes to my {data['title']} meeting"})
    suggestions.append({"label": "Schedule another", "value": "Book a meeting"})

    reply = f"✅ Meeting saved!\n\n📅 {meeting.title}\n🕒 {data['_resolved_human']}"
    if meeting.remind_before_minutes:
        reply += f"\n🔔 Reminder: {reminder_label(meeting.remind_before_minutes)}"

    return {"reply": reply, "intent": "schedule_meeting", "data": meeting.to_dict(), "suggestions": suggestions}
