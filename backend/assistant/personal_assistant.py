"""
Shared personal assistant service.

Both the web LiveChat (/api/assistant/chat) and the Telegram bot DM handler
call process_message() here. Returns a structured dict:
  {
    "reply": str,           # text to send back to the user
    "intent": str,          # detected intent key
    "data": dict | None,    # structured data created (meeting, reminder, etc.)
  }

Intent types:
  schedule_meeting  – create a meeting / appointment
  list_meetings     – show upcoming meetings
  list_reminders    – show upcoming reminders
  group_query       – summarise group issues
  add_resource      – attach resource to the last meeting
  general           – generic assistant reply
"""

import json
import logging
import re
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_INTENT_SYSTEM = """\
You are a Telegram personal assistant. Parse the user's message and return JSON only.

Return exactly one object with these keys:
{
  "intent": one of ["schedule_meeting","list_meetings","list_reminders","group_query","add_resource","general"],
  "title": meeting/reminder title if scheduling (string or null),
  "datetime_hint": natural language date/time phrase if present (string or null),
  "participants": list of name strings if mentioned ([] if none),
  "priority": "low"|"medium"|"high" (default "medium"),
  "timezone": IANA timezone if mentioned (string or null),
  "resource_url": URL if user wants to attach a link (string or null),
  "resource_note": short text note if user wants to attach a note (string or null),
  "reply": a short, friendly assistant reply in plain text (no markdown, 1-3 sentences)
}

Rules:
- Always return valid JSON. No extra text outside the JSON object.
- For schedule_meeting: fill title and datetime_hint at minimum.
- For list_meetings / list_reminders: intent only, reply is a brief acknowledgement.
- For group_query: intent only, reply is a brief acknowledgement.
- For general: fill reply only with a helpful answer.
- If scheduling but date/time is missing, set intent="schedule_meeting" and datetime_hint=null.
"""

_RESOLVE_DATETIME_SYSTEM = """\
You are a date/time parser. Given a natural-language phrase and today's date/time in UTC,
return JSON with these keys:
{
  "iso": "YYYY-MM-DDTHH:MM:SS" in UTC (null if unparseable),
  "human": human-readable string like "Monday 12 May at 3:00 PM UTC"
}
No extra text. Only JSON.
"""


def _call_ai(key_info: dict, system: str, user_msg: str) -> str:
    import requests as _r
    provider = key_info.get("provider", "gemini")
    api_key = key_info["api_key"]
    model = key_info.get("model", "gemini-2.0-flash")

    if provider == "gemini":
        resp = _r.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={"contents": [{"parts": [{"text": f"{system}\n\nUser: {user_msg}"}]}]},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    if provider == "anthropic":
        resp = _r.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": model or "claude-haiku-4-5-20251001",
                "max_tokens": 512,
                "system": system,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()

    base = key_info.get("base_url", "https://api.openai.com/v1")
    resp = _r.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _parse_json(text: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def _resolve_datetime(key_info: dict, hint: str, user_tz: str | None) -> dict:
    """Ask the AI to parse a natural language datetime hint to ISO UTC."""
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    tz_note = f" User timezone: {user_tz}." if user_tz else ""
    prompt = f"Today is {now_str}.{tz_note}\nParse this: \"{hint}\""
    try:
        raw = _call_ai(key_info, _RESOLVE_DATETIME_SYSTEM, prompt)
        return _parse_json(raw)
    except Exception as exc:
        _log.warning("datetime resolve failed: %s", exc)
        return {"iso": None, "human": hint}


# ─────────────────────────────────────────────────────────────────────────────
# Conversation state helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_state(user_id: int):
    from ..models import AssistantConversationState
    state = AssistantConversationState.query.filter_by(user_id=user_id).first()
    if state and state.expires_at < datetime.utcnow():
        from ..models import db
        db.session.delete(state)
        db.session.commit()
        return None
    return state


def _clear_state(user_id: int):
    from ..models import db, AssistantConversationState
    AssistantConversationState.query.filter_by(user_id=user_id).delete()
    db.session.commit()


def _save_state(user_id: int, intent: str, data: dict, awaiting: str):
    from ..models import db, AssistantConversationState
    state = AssistantConversationState.query.filter_by(user_id=user_id).first()
    if not state:
        state = AssistantConversationState(user_id=user_id)
        db.session.add(state)
    state.pending_intent = intent
    state.collected_data = data
    state.awaiting_field = awaiting
    state.expires_at = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Intent handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_schedule_meeting(user_id: int, parsed: dict, key_info: dict, user_tz: str | None) -> dict:
    """Create a meeting or ask follow-up if fields are missing."""
    from ..models import db, Meeting

    data = {
        "title": parsed.get("title"),
        "datetime_hint": parsed.get("datetime_hint"),
        "participants": parsed.get("participants") or [],
        "priority": parsed.get("priority") or "medium",
        "timezone": parsed.get("timezone") or user_tz or "UTC",
    }

    # Missing title?
    if not data["title"]:
        _save_state(user_id, "schedule_meeting", data, "title")
        return {"reply": "What's the title or topic of the meeting?", "intent": "schedule_meeting", "data": None}

    # Missing date/time?
    if not data["datetime_hint"]:
        _save_state(user_id, "schedule_meeting", data, "datetime_hint")
        return {"reply": f"When should I schedule \"{data['title']}\"? (e.g. tomorrow at 3 PM, Friday 10 AM)", "intent": "schedule_meeting", "data": None}

    # Resolve datetime
    dt_result = _resolve_datetime(key_info, data["datetime_hint"], data["timezone"])
    if not dt_result.get("iso"):
        _save_state(user_id, "schedule_meeting", data, "datetime_hint")
        return {"reply": f"I couldn't understand the time \"{data['datetime_hint']}\". Could you say something like \"tomorrow at 3 PM\" or \"Friday 10 AM\"?", "intent": "schedule_meeting", "data": None}

    scheduled_at = datetime.fromisoformat(dt_result["iso"])

    # Duplicate guard — same title within ±30 min
    window_start = scheduled_at - timedelta(minutes=30)
    window_end = scheduled_at + timedelta(minutes=30)
    existing = Meeting.query.filter(
        Meeting.owner_user_id == user_id,
        Meeting.title.ilike(data["title"]),
        Meeting.scheduled_at.between(window_start, window_end),
        Meeting.is_complete == False,
    ).first()
    if existing:
        _clear_state(user_id)
        return {
            "reply": f"You already have \"{existing.title}\" scheduled around {dt_result['human']}. I didn't create a duplicate.",
            "intent": "schedule_meeting",
            "data": existing.to_dict(),
        }

    meeting = Meeting(
        owner_user_id=user_id,
        title=data["title"],
        scheduled_at=scheduled_at,
        timezone=data["timezone"],
        participants=data["participants"] or None,
        priority=data["priority"],
    )
    db.session.add(meeting)
    db.session.commit()
    _clear_state(user_id)

    try:
        from ..integrations.dispatcher import fire_event
        fire_event(user_id, "meeting.created", meeting.to_dict())
    except Exception:
        pass

    participant_str = ""
    if data["participants"]:
        participant_str = f" with {', '.join(data['participants'])}"

    return {
        "reply": (
            f"✅ Meeting scheduled!\n\n"
            f"📅 {meeting.title}{participant_str}\n"
            f"🕒 {dt_result['human']}\n"
            f"⚡ Priority: {meeting.priority}\n\n"
            f"Do you want to attach any resources (links, agenda, notes)?"
        ),
        "intent": "schedule_meeting",
        "data": meeting.to_dict(),
    }


def _handle_continue_state(user_id: int, state, message: str, key_info: dict, user_tz: str | None) -> dict:
    """Continue a multi-turn conversation given the pending state."""
    data = dict(state.collected_data or {})
    awaiting = state.awaiting_field
    intent = state.pending_intent

    if intent == "schedule_meeting":
        if awaiting == "title":
            data["title"] = message.strip()[:200]
        elif awaiting == "datetime_hint":
            data["datetime_hint"] = message.strip()
        elif awaiting == "resources":
            # User may be adding a resource to an existing meeting
            meeting_id = data.get("meeting_id")
            if meeting_id:
                return _attach_resource(user_id, meeting_id, message, state)

        _clear_state(user_id)
        return _handle_schedule_meeting(user_id, data, key_info, user_tz)

    if intent == "add_resource" and awaiting == "resource_value":
        meeting_id = data.get("meeting_id")
        if meeting_id:
            return _attach_resource(user_id, meeting_id, message, state)

    _clear_state(user_id)
    return {"reply": "Got it! Is there anything else I can help you with?", "intent": "general", "data": None}


def _attach_resource(user_id: int, meeting_id: int, value: str, state=None) -> dict:
    from ..models import db, Meeting
    meeting = Meeting.query.filter_by(id=meeting_id, owner_user_id=user_id).first()
    if not meeting:
        if state:
            from ..models import AssistantConversationState
            AssistantConversationState.query.filter_by(user_id=user_id).delete()
            db.session.commit()
        return {"reply": "I couldn't find that meeting to attach the resource to.", "intent": "add_resource", "data": None}

    rtype = "link" if value.strip().startswith("http") else "note"
    resources = list(meeting.resources or [])
    resources.append({"type": rtype, "value": value.strip(), "label": ""})
    meeting.resources = resources
    db.session.commit()
    if state:
        from ..models import AssistantConversationState
        AssistantConversationState.query.filter_by(user_id=user_id).delete()
        db.session.commit()

    try:
        from ..integrations.dispatcher import fire_event
        fire_event(user_id, "resource.attached", {"meeting": meeting.to_dict(), "resource": {"type": rtype, "value": value.strip()}})
    except Exception:
        pass

    return {
        "reply": f"Resource added to \"{meeting.title}\".",
        "intent": "add_resource",
        "data": meeting.to_dict(),
    }


def _handle_list_meetings(user_id: int) -> dict:
    from ..models import Meeting
    now = datetime.utcnow()
    meetings = (
        Meeting.query
        .filter(
            Meeting.owner_user_id == user_id,
            Meeting.scheduled_at >= now,
            Meeting.is_complete == False,
        )
        .order_by(Meeting.scheduled_at.asc())
        .limit(10)
        .all()
    )
    if not meetings:
        return {"reply": "You have no upcoming meetings. Want to schedule one?", "intent": "list_meetings", "data": {"meetings": []}}

    lines = []
    for m in meetings:
        dt = m.scheduled_at.strftime("%b %d, %H:%M UTC")
        participants = f" with {', '.join(m.participants)}" if m.participants else ""
        lines.append(f"• {m.title}{participants} — {dt}")

    reply = "Here are your upcoming meetings:\n\n" + "\n".join(lines)
    return {"reply": reply, "intent": "list_meetings", "data": {"meetings": [m.to_dict() for m in meetings]}}


def _handle_list_reminders(user_id: int) -> dict:
    from ..models import WorkspaceReminder
    now = datetime.utcnow()
    reminders = (
        WorkspaceReminder.query
        .filter(
            WorkspaceReminder.owner_user_id == user_id,
            WorkspaceReminder.remind_at >= now,
            WorkspaceReminder.is_delivered == False,
        )
        .order_by(WorkspaceReminder.remind_at.asc())
        .limit(10)
        .all()
    )
    if not reminders:
        return {"reply": "You have no upcoming reminders.", "intent": "list_reminders", "data": {"reminders": []}}

    lines = [f"• {r.reminder_text} — {r.remind_at.strftime('%b %d, %H:%M UTC')}" for r in reminders]
    reply = "Here are your upcoming reminders:\n\n" + "\n".join(lines)
    return {"reply": reply, "intent": "list_reminders", "data": {"reminders": [r.to_dict() for r in reminders]}}


def _handle_group_query(user_id: int, key_info: dict) -> dict:
    from ..models import TelegramGroup, MessageBuffer
    groups = TelegramGroup.query.filter_by(owner_user_id=user_id, is_disabled=False).all()
    if not groups:
        return {
            "reply": (
                "You don't have any groups connected yet. "
                "Add the Telegizer bot to your Telegram group and link it in the dashboard to enable group insights."
            ),
            "intent": "group_query",
            "data": None,
        }

    cutoff = datetime.utcnow() - timedelta(hours=24)
    group_ids = [g.telegram_group_id for g in groups]
    msgs = (
        MessageBuffer.query
        .filter(MessageBuffer.telegram_group_id.in_(group_ids))
        .filter(MessageBuffer.created_at >= cutoff)
        .order_by(MessageBuffer.created_at.desc())
        .limit(200)
        .all()
    )
    if not msgs:
        return {
            "reply": "No messages found in your groups in the last 24 hours. Make sure the bot is active in your groups.",
            "intent": "group_query",
            "data": None,
        }

    group_title_map = {g.telegram_group_id: g.title for g in groups}
    context = "\n".join(
        f"[{group_title_map.get(m.telegram_group_id, m.telegram_group_id)}] {m.sender_name or 'User'}: {m.message_text}"
        for m in reversed(msgs)
    )[:10000]

    prompt = (
        "Analyse the following Telegram group messages from the last 24 hours.\n"
        "Identify and summarise in bullet points:\n"
        "- Spam or moderation issues\n"
        "- Member complaints or conflicts\n"
        "- Important unanswered questions\n"
        "- High-priority discussions\n"
        "- Unusual activity\n"
        "If nothing notable, say the group looks healthy.\n\n"
        f"Messages:\n{context}"
    )

    try:
        summary = _call_ai(key_info, "You are a group moderation assistant. Be concise and factual.", prompt)
    except Exception as exc:
        _log.warning("group_query AI call failed: %s", exc)
        return {"reply": "I couldn't generate a group summary right now. Please try again.", "intent": "group_query", "data": None}

    try:
        from ..integrations.dispatcher import fire_event
        fire_event(user_id, "group.issue.detected", {
            "groups_checked": len(groups),
            "messages_scanned": len(msgs),
            "summary_preview": summary[:500],
        })
    except Exception:
        pass

    return {
        "reply": f"Group summary (last 24h):\n\n{summary}",
        "intent": "group_query",
        "data": {"groups_checked": len(groups), "messages_scanned": len(msgs)},
    }


def _handle_add_resource(user_id: int, parsed: dict) -> dict:
    """Attach a resource (link or note) to the user's most recent upcoming meeting."""
    from ..models import Meeting
    now = datetime.utcnow()
    meeting = (
        Meeting.query
        .filter(Meeting.owner_user_id == user_id, Meeting.scheduled_at >= now, Meeting.is_complete == False)
        .order_by(Meeting.scheduled_at.asc())
        .first()
    )
    if not meeting:
        return {"reply": "I don't see any upcoming meetings to attach resources to. Schedule a meeting first.", "intent": "add_resource", "data": None}

    resource_value = parsed.get("resource_url") or parsed.get("resource_note") or ""
    if not resource_value:
        _save_state(user_id, "add_resource", {"meeting_id": meeting.id}, "resource_value")
        return {"reply": f"What would you like to attach to \"{meeting.title}\"? Paste a link or type a note.", "intent": "add_resource", "data": None}

    return _attach_resource(user_id, meeting.id, resource_value)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def process_message(user_id: int, message: str, user_tz: str | None = None) -> dict:
    """
    Process a natural language message from the user.
    Must be called inside a Flask app context.
    Returns {"reply": str, "intent": str, "data": dict|None}.
    """
    from ..assistant.ai_key_resolver import get_workspace_ai_key
    from ..models import User

    user = User.query.get(user_id)
    if not user:
        return {"reply": "User not found.", "intent": "error", "data": None}

    key_info = get_workspace_ai_key(user)
    if not key_info.get("api_key"):
        return {
            "reply": "No AI key is configured. Add one in Settings → AI Settings to enable the assistant.",
            "intent": "error",
            "data": None,
        }

    # Check for pending conversation state (multi-turn follow-up)
    state = _get_state(user_id)
    if state:
        try:
            return _handle_continue_state(user_id, state, message, key_info, user_tz)
        except Exception as exc:
            _log.warning("continue_state failed: %s", exc)
            _clear_state(user_id)

    # Parse intent from fresh message
    try:
        raw = _call_ai(key_info, _INTENT_SYSTEM, message)
        parsed = _parse_json(raw)
    except Exception as exc:
        _log.warning("intent parse failed: %s", exc)
        return {"reply": "Sorry, I had trouble understanding that. Could you rephrase?", "intent": "error", "data": None}

    intent = parsed.get("intent", "general")

    try:
        if intent == "schedule_meeting":
            return _handle_schedule_meeting(user_id, parsed, key_info, user_tz)
        if intent == "list_meetings":
            return _handle_list_meetings(user_id)
        if intent == "list_reminders":
            return _handle_list_reminders(user_id)
        if intent == "group_query":
            return _handle_group_query(user_id, key_info)
        if intent == "add_resource":
            return _handle_add_resource(user_id, parsed)
        # general
        return {"reply": parsed.get("reply") or "I'm not sure how to help with that. Try asking me to schedule a meeting or show your reminders.", "intent": "general", "data": None}
    except Exception as exc:
        _log.error("intent handler %s failed: %s", intent, exc, exc_info=True)
        return {"reply": "Something went wrong. Please try again.", "intent": "error", "data": None}
