"""General AI response and resource attachment handlers."""
from __future__ import annotations

import logging

from ._ai import call_ai_text
from ._prompts import GENERAL_AI_SYSTEM
from ._state import clear_state, save_state


_log = logging.getLogger(__name__)


def handle_general(user_id: int, message: str, key_info: dict, ai_reply: str | None, ctx=None) -> dict:
    if not key_info.get("api_key"):
        return {
            "reply": (
                "I can help you:\n"
                "• Schedule meetings — \"Book a call Friday 3 PM\"\n"
                "• Set reminders — \"Remind me about X tomorrow\"\n"
                "• Save notes — \"Note this: ...\"\n"
                "• Create tasks — \"Task: write spec\"\n"
                "• Save links — \"Save https://...\"\n"
                "• Check schedule — \"What's on my schedule?\"\n"
                "• Group insights — \"Any issues in my groups?\"\n\n"
                "What can I help you with?"
            ),
            "intent": "general",
            "data": None,
        }

    if ai_reply:
        return {"reply": ai_reply, "intent": "general", "data": None}

    context = ctx.to_prompt_text() if ctx else "Workspace data unavailable."
    prompt = (
        f"User's workspace context:\n{context}\n\n"
        f"User message: {message}\n\n"
        "Give a helpful, professional, concise reply (2-4 sentences max)."
    )
    try:
        reply = call_ai_text(key_info, GENERAL_AI_SYSTEM, prompt)
        return {"reply": reply, "intent": "general", "data": None}
    except Exception as exc:
        _log.warning("general AI failed: %s", exc)
        return {
            "reply": "I'm here to help! Try: \"Book a meeting\", \"Remind me about X\", \"What's on my schedule?\", or \"Any issues in my groups?\"",
            "intent": "general",
            "data": None,
        }


def handle_add_resource(user_id: int, parsed: dict) -> dict:
    from ...models import Meeting
    from datetime import datetime
    now = datetime.utcnow()
    meeting = (
        Meeting.query
        .filter(Meeting.owner_user_id == user_id, Meeting.scheduled_at >= now, Meeting.is_complete == False)
        .order_by(Meeting.scheduled_at.asc()).first()
    )
    if not meeting:
        return {"reply": "No upcoming meetings to attach resources to. Schedule one first.", "intent": "add_resource", "data": None}

    resource_value = parsed.get("resource_url") or parsed.get("resource_note") or ""
    if not resource_value:
        save_state(user_id, "add_resource", {"meeting_id": meeting.id}, "resource_value")
        return {"reply": f'What would you like to attach to "{meeting.title}"? Paste a link or type a note.',
                "intent": "add_resource", "data": None}

    return attach_resource(user_id, meeting.id, resource_value)


def attach_resource(user_id: int, meeting_id: int, value: str, state=None) -> dict:
    from ...models import db, Meeting
    meeting = Meeting.query.filter_by(id=meeting_id, owner_user_id=user_id).first()
    if not meeting:
        if state:
            from ...models import AssistantConversationState
            AssistantConversationState.query.filter_by(user_id=user_id).delete()
            db.session.commit()
        return {"reply": "Couldn't find that meeting to attach the resource to.", "intent": "add_resource", "data": None}

    rtype = "link" if value.strip().startswith("http") else "note"
    resources = list(meeting.resources or [])
    resources.append({"type": rtype, "value": value.strip(), "label": ""})
    meeting.resources = resources
    db.session.commit()

    if state:
        clear_state(user_id)

    try:
        from ...integrations.dispatcher import fire_event
        fire_event(user_id, "resource.attached",
                   {"meeting": meeting.to_dict(), "resource": {"type": rtype, "value": value.strip()}})
    except Exception:
        pass

    return {"reply": f'Resource added to "{meeting.title}".', "intent": "add_resource", "data": meeting.to_dict()}
