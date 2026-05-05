"""Meeting creation — smart extraction + progressive natural intake."""
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
        "agenda":           parsed.get("agenda"),
        "duration_minutes": parsed.get("duration_minutes"),
        "location":         parsed.get("location"),
        "participants":     parsed.get("participants") or [],
        "related_person":   parsed.get("related_person"),
        "project":          parsed.get("project"),
        "resource_url":     parsed.get("resource_url"),
        "priority":         parsed.get("priority") or "medium",
        "followup_required": parsed.get("followup_required", False),
        "_reminder_asked":  parsed.get("_reminder_asked", False),
        "_notes_asked":     parsed.get("_notes_asked", False),
        "_resources_asked": parsed.get("_resources_asked", False),
    }

    # Merge participants + related_person for richer context
    if data["related_person"] and data["related_person"] not in data["participants"]:
        data["participants"].append(data["related_person"])

    # Step 1 — need title
    if not data["title"]:
        save_state(user_id, "schedule_meeting", data, "title")
        return {
            "reply": "Sure, I can schedule that. What's the meeting about?",
            "intent": "schedule_meeting",
            "data": None,
            "suggestions": meeting_title_suggestions(),
        }

    # Step 2 — need time
    if not data["_resolved_iso"] and not data["datetime_hint"]:
        save_state(user_id, "schedule_meeting", data, "datetime_hint")
        participants_hint = f" with {data['participants'][0]}" if data["participants"] else ""
        return {
            "reply": f'When should I schedule "{data["title"]}"{participants_hint}?',
            "intent": "schedule_meeting",
            "data": None,
            "suggestions": time_suggestions(),
        }

    # Resolve datetime hint → ISO (max 3 attempts to avoid infinite loop)
    if not data["_resolved_iso"] and data["datetime_hint"]:
        dt = resolve_datetime(key_info, data["datetime_hint"], data["timezone"])
        if not dt.get("iso"):
            attempts = data.get("_datetime_attempts", 0) + 1
            if attempts >= 3:
                clear_state(user_id)
                return {
                    "reply": "I'm having trouble understanding that time. Try something like 'tomorrow 3pm' or 'Friday at 10am'.",
                    "intent": "schedule_meeting",
                    "data": None,
                    "suggestions": time_suggestions(),
                }
            data["_datetime_attempts"] = attempts
            save_state(user_id, "schedule_meeting", data, "datetime_hint")
            return {
                "reply": f'I couldn\'t parse "{data["datetime_hint"]}" — try something like "tomorrow 3pm" or "Friday at 10am".',
                "intent": "schedule_meeting",
                "data": None,
                "suggestions": time_suggestions(),
            }
        data["_resolved_iso"] = dt["iso"]
        data["_resolved_human"] = dt["human"]

    # Step 3 — reminder preference (skip if reminder_minutes already set)
    if not data["_reminder_asked"] and data["reminder_minutes"] is None:
        data["_reminder_asked"] = True
        save_state(user_id, "schedule_meeting", data, "reminder")
        who = f" with {data['participants'][0]}" if data["participants"] else ""
        return {
            "reply": f'Got it — "{data["title"]}"{who} on {data["_resolved_human"]}. Want a reminder before the meeting?',
            "intent": "schedule_meeting",
            "data": None,
            "suggestions": reminder_suggestions(),
        }

    # If we have both title + time + reminder preference (or skipped), go to confirmation
    # Skip notes/resources steps by default (Quick Mode) — offer them in suggestions after save
    if not parsed.get("_confirmed"):
        participants_str = ", ".join(data["participants"]) if data["participants"] else None
        summary_lines = [
            f"Here's a summary before I save it:\n",
            f"📌 **{data['title']}**",
            f"🕒 {data['_resolved_human']}",
        ]
        if participants_str:
            summary_lines.append(f"👤 {participants_str}")
        if data.get("location"):
            summary_lines.append(f"📍 {data['location']}")
        if data.get("duration_minutes"):
            summary_lines.append(f"⏱️ {data['duration_minutes']} min")
        summary_lines.append(f"🔔 Reminder: {reminder_label(data.get('reminder_minutes'))}")
        if data.get("notes") or data.get("agenda"):
            summary_lines.append(f"📝 Notes: {data.get('notes') or data.get('agenda')}")
        if data.get("resource_url"):
            summary_lines.append(f"🔗 {data['resource_url']}")
        summary_lines.append("\nShould I save it?")

        data["_confirmed"] = False
        save_state(user_id, "schedule_meeting", data, "confirm")
        return {
            "reply": "\n".join(summary_lines),
            "intent": "schedule_meeting",
            "data": None,
            "suggestions": yes_no_suggestions(),
        }

    # Save
    scheduled_at = datetime.fromisoformat(data["_resolved_iso"])
    existing = Meeting.query.filter(
        Meeting.owner_user_id == user_id,
        Meeting.title.ilike(data["title"]),
        Meeting.scheduled_at.between(scheduled_at - timedelta(minutes=30), scheduled_at + timedelta(minutes=30)),
        Meeting.is_complete == False,
    ).first()
    if existing:
        clear_state(user_id)
        return {
            "reply": f'You already have "{existing.title}" around that time — no duplicate created.',
            "intent": "schedule_meeting",
            "data": existing.to_dict(),
        }

    resources = []
    if data.get("resource_url"):
        rtype = "link" if data["resource_url"].startswith("http") else "note"
        resources = [{"type": rtype, "value": data["resource_url"], "label": ""}]

    meeting = Meeting(
        owner_user_id=user_id,
        title=data["title"],
        scheduled_at=scheduled_at,
        timezone=data["timezone"],
        priority=data.get("priority") or "medium",
        remind_before_minutes=data.get("reminder_minutes") or 15,
        notes=data.get("notes") or data.get("agenda"),
        resources=resources or None,
        participants=data["participants"] or None,
    )

    # Add extended fields if they exist on the model
    for field in ("duration_minutes", "location", "related_person", "project", "followup_required"):
        if data.get(field) is not None and hasattr(meeting, field):
            setattr(meeting, field, data[field])

    db.session.add(meeting)
    db.session.commit()
    clear_state(user_id)

    _post_create_hooks(user_id, meeting, data)

    suggestions = []
    if not data.get("notes") and not data.get("agenda"):
        suggestions.append({"label": "📝 Add Agenda", "value": f'Add notes to my "{data["title"]}" meeting'})
    if not data.get("resource_url"):
        suggestions.append({"label": "🔗 Attach Link", "value": f'Attach a link to "{data["title"]}"'})
    suggestions.append({"label": "📅 My Schedule", "value": "Show my upcoming meetings"})

    reply = f"✅ Meeting saved!\n\n📅 **{meeting.title}**\n🕒 {data['_resolved_human']}"
    if data["participants"]:
        reply += f"\n👤 {', '.join(data['participants'])}"
    if meeting.remind_before_minutes:
        reply += f"\n🔔 Reminder: {reminder_label(meeting.remind_before_minutes)}"

    return {
        "reply": reply,
        "intent": "schedule_meeting",
        "data": meeting.to_dict(),
        "suggestions": suggestions,
    }


def _post_create_hooks(user_id: int, meeting, data: dict) -> None:
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
