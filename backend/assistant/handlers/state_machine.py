"""Multi-turn conversation continuation — resumes pending workflow state naturally."""
from __future__ import annotations

import re

from ._patterns import CANCEL_PATTERNS, CONFIRM_YES_PATTERNS, SKIP_VALUE
from ._parsers import extract_datetime_hint, parse_reminder_minutes
from ._state import clear_state

from .meeting import handle_schedule_meeting
from .reminder import handle_create_reminder
from .notes import handle_save_note
from .tasks import handle_create_task
from .general import attach_resource


def handle_continue_state(user_id: int, state, message: str, key_info: dict, user_tz: str | None) -> dict:
    data = dict(state.collected_data or {})
    awaiting = state.awaiting_field
    intent = state.pending_intent
    msg = message.strip()

    # Universal cancellation — natural language cancel detection
    if CANCEL_PATTERNS.match(msg) or re.search(r"\b(forget it|never mind|cancel|stop|abort|scrap that)\b", msg, re.I):
        clear_state(user_id)
        return {
            "reply": "No problem — cancelled. What else can I help you with?",
            "intent": "general",
            "data": None,
            "suggestions": [
                {"label": "📅 Schedule Meeting", "value": "Schedule a meeting"},
                {"label": "⏰ Set Reminder", "value": "Remind me"},
                {"label": "✅ Create Task", "value": "Create task"},
            ],
        }

    # ── Meeting multi-turn ────────────────────────────────────────────────────
    if intent == "schedule_meeting":
        if awaiting == "title":
            data["title"] = msg[:200]

        elif awaiting == "datetime_hint":
            data["datetime_hint"] = extract_datetime_hint(msg) or msg
            data["_resolved_iso"] = None
            data["_resolved_human"] = None

        elif awaiting == "reminder":
            skip_reminder = (
                msg == SKIP_VALUE
                or re.search(r"\b(no\s+reminder|no\s+thanks|skip|none|no)\b", msg, re.I)
            )
            if skip_reminder:
                data["reminder_minutes"] = 0
            else:
                data["reminder_minutes"] = parse_reminder_minutes(msg)
            data["_reminder_asked"] = True

        elif awaiting == "notes":
            skip_notes = (
                msg == SKIP_VALUE
                or re.search(r"\b(skip|no|none|no notes|not now)\b", msg, re.I)
                or re.search(r"\b(remind|reminder|schedule|create task|save note)\b", msg, re.I)
            )
            data["notes"] = None if skip_notes else msg[:2000]
            data["_notes_asked"] = True

        elif awaiting == "resource_url":
            skip_resource = (
                msg == SKIP_VALUE
                or re.search(r"\b(skip|no|none|not now|no link)\b", msg, re.I)
                or (not re.search(r"https?://", msg) and re.search(r"\b(skip|remind|schedule)\b", msg, re.I))
            )
            if skip_resource:
                data["resource_url"] = None
            else:
                url_m = re.search(r"https?://\S+", msg)
                data["resource_url"] = url_m.group(0) if url_m else msg
            data["_resources_asked"] = True

        elif awaiting == "confirm":
            if CONFIRM_YES_PATTERNS.match(msg) or re.search(r"\b(yes|yeah|yep|sure|go ahead|save|confirm|ok|looks good)\b", msg, re.I):
                data["_confirmed"] = True
                clear_state(user_id)
                return handle_schedule_meeting(user_id, data, key_info, user_tz)
            else:
                clear_state(user_id)
                return {
                    "reply": "Meeting cancelled. Let me know if you'd like to schedule it differently.",
                    "intent": "general",
                    "data": None,
                    "suggestions": [{"label": "📅 Try Again", "value": "Schedule a meeting"}],
                }

        clear_state(user_id)
        return handle_schedule_meeting(user_id, data, key_info, user_tz)

    # ── Reminder multi-turn ───────────────────────────────────────────────────
    if intent == "create_reminder":
        if awaiting == "text":
            data["text"] = msg[:500]
        elif awaiting == "datetime_hint":
            data["datetime_hint"] = extract_datetime_hint(msg) or msg
            data["_resolved_iso"] = None
        clear_state(user_id)
        return handle_create_reminder(user_id, data, key_info, user_tz)

    # ── Save note ─────────────────────────────────────────────────────────────
    if intent == "save_note" and awaiting == "content":
        clear_state(user_id)
        return handle_save_note(user_id, msg)

    # ── Create task ───────────────────────────────────────────────────────────
    if intent == "create_task" and awaiting == "title":
        clear_state(user_id)
        return handle_create_task(user_id, {"title": msg})

    # ── Add resource ──────────────────────────────────────────────────────────
    if intent == "add_resource" and awaiting == "resource_value":
        meeting_id = data.get("meeting_id")
        if meeting_id:
            return attach_resource(user_id, meeting_id, msg, state)

    clear_state(user_id)
    return {
        "reply": "Got it! Is there anything else I can help you with?",
        "intent": "general",
        "data": None,
        "suggestions": [
            {"label": "📅 My Schedule", "value": "What's on my schedule?"},
            {"label": "🧠 Analyze My Day", "value": "Analyze my day"},
        ],
    }
