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
# Prompt
# ─────────────────────────────────────────────────────────────────────────────

_INTENT_SYSTEM = """\
You are a Telegram personal assistant. Parse the user's message and return ONLY a JSON object — no explanation, no prose, no markdown fences.

Return exactly this structure:
{
  "intent": <one of: "schedule_meeting" | "list_meetings" | "list_reminders" | "group_query" | "add_resource" | "general">,
  "title": <meeting/reminder title string, or null>,
  "datetime_hint": <natural language date/time phrase, or null>,
  "participants": <list of name strings, [] if none>,
  "priority": <"low" | "medium" | "high">,
  "timezone": <IANA timezone string if mentioned, or null>,
  "resource_url": <URL string if user wants to attach a link, or null>,
  "resource_note": <short text note if user wants to attach a note, or null>,
  "reply": <short friendly assistant reply, plain text, 1-3 sentences>
}

Rules:
- ALWAYS return valid JSON only. No text before or after the JSON object.
- schedule_meeting: set title and datetime_hint when available. If date/time missing, set datetime_hint to null.
- list_meetings / list_reminders: set intent only, brief reply.
- group_query: intent only.
- general: set reply only.
- Default priority is "medium".

Examples (input → output):
---
Input: "Schedule meeting tomorrow at 3 PM"
{"intent":"schedule_meeting","title":"Meeting","datetime_hint":"tomorrow at 3 PM","participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Got it, scheduling a meeting for tomorrow at 3 PM!"}

Input: "Book investor call Friday 5 PM"
{"intent":"schedule_meeting","title":"Investor Call","datetime_hint":"Friday 5 PM","participants":[],"priority":"high","timezone":null,"resource_url":null,"resource_note":null,"reply":"Booking your investor call for Friday at 5 PM."}

Input: "Can you schedule a meeting"
{"intent":"schedule_meeting","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Sure! What's the meeting about and when?"}

Input: "Any meetings coming up?"
{"intent":"list_meetings","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Let me check your upcoming meetings."}

Input: "What meetings do I have today?"
{"intent":"list_meetings","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Checking your schedule for today."}

Input: "Show my reminders"
{"intent":"list_reminders","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Here are your reminders."}

Input: "What's going on in my groups?"
{"intent":"group_query","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Analyzing your group activity now."}

Input: "Remind me about standup daily at 9 AM"
{"intent":"schedule_meeting","title":"Daily Standup","datetime_hint":"daily at 9 AM","participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Setting up a daily standup reminder at 9 AM."}

Input: "Save a meeting for next Monday"
{"intent":"schedule_meeting","title":"Meeting","datetime_hint":"next Monday","participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Scheduling a meeting for next Monday. What should I call it?"}

Input: "Attach https://docs.google.com to last meeting"
{"intent":"add_resource","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":"https://docs.google.com","resource_note":null,"reply":"Attaching that link to your most recent meeting."}
---
"""

_RESOLVE_DATETIME_SYSTEM = """\
You are a date/time parser. Given a natural-language phrase and today's date/time in UTC,
return ONLY a JSON object (no extra text):
{
  "iso": "YYYY-MM-DDTHH:MM:SS" (in UTC, null if unparseable),
  "human": "human-readable string like Monday 12 May at 3:00 PM UTC"
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# Keyword-based fallback intent detection (runs when AI is unavailable/fails)
# ─────────────────────────────────────────────────────────────────────────────

_SCHEDULE_PATTERNS = re.compile(
    r"\b(schedul|book|set up|create|add|save|plan|arrange|organis|organiz|set a meeting|set meeting"
    r"|new meeting|make a meeting|can you schedule|remind me about|remind daily|remind weekly)\b",
    re.IGNORECASE,
)
_MEETING_NOUN = re.compile(
    r"\b(meeting|call|standup|stand.?up|sync|catchup|catch.?up|session|appointment|interview|demo|webinar|event)\b",
    re.IGNORECASE,
)
_LIST_MEETINGS_PATTERNS = re.compile(
    r"\b(upcoming|any meetings|what meetings|my meetings|my schedule|do i have.*meeting|meetings today"
    r"|meetings tomorrow|show meetings|list meetings|next meeting|check schedule|what.?s next)\b",
    re.IGNORECASE,
)
_LIST_REMINDERS_PATTERNS = re.compile(
    r"\b(my reminders|show reminders|list reminders|upcoming reminders|any reminders|what reminders)\b",
    re.IGNORECASE,
)
_GROUP_PATTERNS = re.compile(
    r"\b(group|groups|community|communities|members|moderation|spam|issues in|what.?s going on|group activity|group summary)\b",
    re.IGNORECASE,
)

def _keyword_intent(message: str) -> str | None:
    """Return a best-guess intent from keyword matching, or None if uncertain."""
    msg = message.lower()
    if _LIST_MEETINGS_PATTERNS.search(msg):
        return "list_meetings"
    if _LIST_REMINDERS_PATTERNS.search(msg):
        return "list_reminders"
    if _GROUP_PATTERNS.search(msg) and any(w in msg for w in ("issue", "problem", "spam", "going on", "activity", "summary", "happening")):
        return "group_query"
    # schedule: needs schedule-verb OR meeting-noun with time hint
    has_schedule_verb = bool(_SCHEDULE_PATTERNS.search(msg))
    has_meeting_noun = bool(_MEETING_NOUN.search(msg))
    if has_schedule_verb or has_meeting_noun:
        return "schedule_meeting"
    return None


def _keyword_parse(message: str) -> dict:
    """Build a minimal parsed dict from keyword matching for schedule fallback."""
    # Extract a time hint from the message
    time_patterns = [
        r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(next\s+\w+)\b",
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))\b",
        r"\b(at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
        r"\b(in\s+\d+\s*(?:minutes?|hours?|days?))\b",
    ]
    datetime_hint = None
    for pat in time_patterns:
        m = re.search(pat, message, re.IGNORECASE)
        if m:
            datetime_hint = m.group(0)
            break

    # Try to extract a title (strip common scheduling verbs)
    title = re.sub(
        r"^(schedule|book|create|add|save|plan|set up|arrange|can you schedule|"
        r"set a meeting for|set meeting for|make a meeting for|"
        r"new meeting|a meeting|one meeting)\s*",
        "", message.strip(), flags=re.IGNORECASE
    ).strip()
    # Remove time phrases from title
    if datetime_hint:
        title = title.replace(datetime_hint, "").strip().strip("-–—").strip()
    # Fallback title
    if not title or len(title) < 2:
        title = None

    return {
        "intent": "schedule_meeting",
        "title": title or None,
        "datetime_hint": datetime_hint,
        "participants": [],
        "priority": "medium",
        "timezone": None,
        "resource_url": None,
        "resource_note": None,
        "reply": "Sure! Let me get that scheduled for you.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# AI call helpers
# ─────────────────────────────────────────────────────────────────────────────

def _call_ai(key_info: dict, system: str, user_msg: str) -> str:
    import requests as _r
    provider = key_info.get("provider", "gemini")
    api_key = key_info["api_key"]
    model = key_info.get("model", "gemini-2.0-flash")

    _log.debug("_call_ai provider=%s model=%s msg_len=%d", provider, model, len(user_msg))

    if provider == "gemini":
        # Use systemInstruction for proper role separation — avoids Gemini
        # ignoring JSON-only instructions when mixed into the user turn.
        resp = _r.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "candidateCount": 1,
                    "responseMimeType": "application/json",
                },
            },
            timeout=20,
        )
        resp.raise_for_status()
        result = resp.json()
        _log.debug("gemini raw response: %s", str(result)[:500])
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()

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

    # OpenAI / OpenRouter / custom
    base = key_info.get("base_url", "https://api.openai.com/v1")
    resp = _r.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model or "gpt-4o-mini",
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
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
    """Robustly extract and parse the first JSON object from model output."""
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract first {...} block (handles prose wrapping like "Here is the JSON: {...}")
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # Last resort — raise so caller can fall back to keyword detection
    raise ValueError(f"No valid JSON found in AI response: {text[:200]!r}")


def _resolve_datetime(key_info: dict, hint: str, user_tz: str | None) -> dict:
    """Ask the AI to parse a natural language datetime hint to ISO UTC."""
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    tz_note = f" User timezone: {user_tz}." if user_tz else ""
    prompt = f"Today is {now_str}.{tz_note}\nParse this date/time phrase: \"{hint}\""
    try:
        raw = _call_ai(key_info, _RESOLVE_DATETIME_SYSTEM, prompt)
        result = _parse_json(raw)
        _log.debug("datetime resolve hint=%r → %s", hint, result)
        return result
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

    _log.debug("schedule_meeting data=%s", data)

    # Missing title?
    if not data["title"]:
        _save_state(user_id, "schedule_meeting", data, "title")
        return {"reply": "What's the title or topic of the meeting?", "intent": "schedule_meeting", "data": None}

    # Missing date/time?
    if not data["datetime_hint"]:
        _save_state(user_id, "schedule_meeting", data, "datetime_hint")
        return {
            "reply": f"When should I schedule \"{data['title']}\"? (e.g. tomorrow at 3 PM, Friday 10 AM)",
            "intent": "schedule_meeting",
            "data": None,
        }

    # Resolve datetime
    dt_result = _resolve_datetime(key_info, data["datetime_hint"], data["timezone"])
    if not dt_result.get("iso"):
        _save_state(user_id, "schedule_meeting", data, "datetime_hint")
        return {
            "reply": (
                f"I couldn't understand the time \"{data['datetime_hint']}\". "
                "Could you say something like \"tomorrow at 3 PM\" or \"Friday 10 AM\"?"
            ),
            "intent": "schedule_meeting",
            "data": None,
        }

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
    from ..assistant.ai_key_resolver import get_workspace_ai_key, QuotaExceededError
    from ..models import User

    _log.info("process_message user_id=%s message=%r", user_id, message[:120])

    user = User.query.get(user_id)
    if not user:
        return {"reply": "User not found.", "intent": "error", "data": None}

    # Resolve AI key — quota errors get a friendly message instead of a 500
    try:
        key_info = get_workspace_ai_key(user)
    except QuotaExceededError as exc:
        _log.info("QuotaExceededError for user %s: %s", user_id, exc)
        return {"reply": str(exc), "intent": "error", "data": None}
    except Exception as exc:
        _log.warning("get_workspace_ai_key failed: %s", exc)
        key_info = {}

    ai_available = bool(key_info.get("api_key"))
    if not ai_available:
        _log.info("No AI key for user %s — using keyword-only intent detection", user_id)

    # Check for pending conversation state (multi-turn follow-up)
    state = _get_state(user_id)
    if state:
        _log.debug("Resuming conversation state intent=%s awaiting=%s", state.pending_intent, state.awaiting_field)
        # Escape hatch: if the user is clearly asking for something different
        # (e.g. group_query while stuck in schedule_meeting), clear state and
        # let the new intent win — don't consume their message as a field answer.
        escape_intent = _keyword_intent(message)
        if escape_intent and escape_intent != state.pending_intent and escape_intent in ("group_query", "list_meetings", "list_reminders"):
            _log.info("State escape: clearing %s state, routing to %s", state.pending_intent, escape_intent)
            _clear_state(user_id)
            state = None
        else:
            try:
                return _handle_continue_state(user_id, state, message, key_info, user_tz)
            except Exception as exc:
                _log.warning("continue_state failed: %s", exc)
                _clear_state(user_id)

    parsed = None
    intent = None

    # ── Step 1: Keyword pre-filter for high-confidence, entity-free intents ──
    # group_query / list_meetings / list_reminders never need AI entity
    # extraction. Running keyword detection FIRST prevents AI from
    # misclassifying e.g. "Any issues in my group today?" as schedule_meeting
    # because it sees a time-like phrase ("today") in the message.
    keyword_intent = _keyword_intent(message)
    _log.debug("keyword_intent=%s", keyword_intent)
    if keyword_intent in ("group_query", "list_meetings", "list_reminders"):
        intent = keyword_intent
        parsed = {"intent": intent}
        _log.info("High-confidence keyword intent=%s — skipping AI", intent)

    # ── Step 2: AI parsing for schedule_meeting / general / ambiguous ────────
    if intent is None and ai_available:
        try:
            raw = _call_ai(key_info, _INTENT_SYSTEM, message)
            _log.debug("AI raw response: %s", raw[:300])
            parsed = _parse_json(raw)
            intent = parsed.get("intent", "general")
            _log.info("AI intent=%s title=%r datetime_hint=%r", intent, parsed.get("title"), parsed.get("datetime_hint"))
            # Sanity-check: if AI says schedule_meeting but the message
            # strongly looks like a query/group intent, override it.
            if intent == "schedule_meeting" and keyword_intent in ("group_query", "list_meetings", "list_reminders"):
                _log.warning("AI intent overridden from schedule_meeting → %s by keyword signal", keyword_intent)
                intent = keyword_intent
                parsed = {"intent": intent}
        except Exception as exc:
            _log.warning("AI intent parse failed (%s) — falling back to keyword detection", exc)
            parsed = None
            intent = None

    # ── Step 3: Pure keyword fallback if AI failed or unavailable ────────────
    if intent is None:
        intent = keyword_intent or "general"
        _log.info("Keyword fallback intent=%s for message=%r", intent, message[:80])
        if intent == "schedule_meeting":
            parsed = _keyword_parse(message)
        else:
            parsed = {"intent": intent}

    # ── Step 3: Route to handler ──────────────────────────────────────────────
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
        ai_reply = (parsed or {}).get("reply") if ai_available else None
        return {
            "reply": ai_reply or "I can help you schedule meetings, set reminders, or check your upcoming schedule. What would you like to do?",
            "intent": "general",
            "data": None,
        }
    except Exception as exc:
        _log.error("intent handler %s failed: %s", intent, exc, exc_info=True)
        return {"reply": "Something went wrong processing your request. Please try again.", "intent": "error", "data": None}
