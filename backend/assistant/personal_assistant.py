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
  save_note         – save a note
  list_notes        – show recent notes
  save_link         – save a URL/resource for later
  create_task       – create a task
  list_tasks        – show pending tasks
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
  "intent": <one of: "schedule_meeting" | "list_meetings" | "list_reminders" | "save_note" | "list_notes" | "save_link" | "create_task" | "list_tasks" | "group_query" | "add_resource" | "general">,
  "title": <meeting/task title string, or null>,
  "datetime_hint": <natural language date/time phrase, or null>,
  "participants": <list of name strings, [] if none>,
  "priority": <"low" | "medium" | "high">,
  "timezone": <IANA timezone string if mentioned, or null>,
  "resource_url": <URL string if user wants to attach a link, or null>,
  "resource_note": <text content for note/task/resource if provided, or null>,
  "reply": <short friendly assistant reply, plain text, 1-3 sentences>
}

Rules:
- ALWAYS return valid JSON only. No text before or after the JSON object.
- schedule_meeting: set title and datetime_hint when available.
- save_note: put note content in resource_note field.
- save_link: put URL in resource_url field.
- create_task: put task title in title field.
- list_* intents: set intent only, brief reply.
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

Input: "Save a meeting for next Monday"
{"intent":"schedule_meeting","title":"Meeting","datetime_hint":"next Monday","participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Scheduling a meeting for next Monday."}

Input: "Any meetings coming up?"
{"intent":"list_meetings","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Let me check your upcoming meetings."}

Input: "What meetings do I have today?"
{"intent":"list_meetings","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Checking your schedule for today."}

Input: "Show my reminders"
{"intent":"list_reminders","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Here are your reminders."}

Input: "Note this: project deadline is Friday"
{"intent":"save_note","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":"project deadline is Friday","reply":"Got it, saving that note."}

Input: "Save this as a note: need to call Alice tomorrow"
{"intent":"save_note","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":"need to call Alice tomorrow","reply":"Saved to your notes."}

Input: "Show my notes"
{"intent":"list_notes","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Here are your recent notes."}

Input: "What notes do I have?"
{"intent":"list_notes","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Let me pull up your notes."}

Input: "Save this link for later: https://example.com/docs"
{"intent":"save_link","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":"https://example.com/docs","resource_note":null,"reply":"Link saved to your notes."}

Input: "Remember this: https://notion.so/my-plan"
{"intent":"save_link","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":"https://notion.so/my-plan","resource_note":null,"reply":"Saved that link for you."}

Input: "Create task: write product spec by Friday"
{"intent":"create_task","title":"Write product spec by Friday","datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Task created."}

Input: "Add to my task list: review the PR"
{"intent":"create_task","title":"Review the PR","datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Added to your tasks."}

Input: "What tasks do I have?"
{"intent":"list_tasks","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Here are your pending tasks."}

Input: "Show pending tasks"
{"intent":"list_tasks","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Let me check your tasks."}

Input: "What's going on in my groups?"
{"intent":"group_query","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Analyzing your group activity now."}

Input: "Any issues in my group today?"
{"intent":"group_query","title":null,"datetime_hint":null,"participants":[],"priority":"medium","timezone":null,"resource_url":null,"resource_note":null,"reply":"Let me check your groups for any issues."}
---
"""

_RESOLVE_DATETIME_SYSTEM = """\
You are a date/time parser. Given a natural-language phrase and today's date/time in UTC,
return ONLY a JSON object (no extra text):
{
  "iso": "YYYY-MM-DDTHH:MM:SS" (in UTC, null only if the phrase is completely unparseable),
  "human": "human-readable string like Monday 12 May at 3:00 PM UTC"
}

Important rules:
- If a day is given but no time, default to 12:00 PM (noon) in the user's timezone (or UTC if unknown).
- "tomorrow" = tomorrow at 12:00 PM UTC.
- "today" = today at 12:00 PM UTC.
- Day names like "Monday", "Friday" = the next occurrence of that day at 12:00 PM UTC.
- Only return null iso if the phrase contains no date/time information at all.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Keyword-based pre-filter / fallback intent detection
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
    r"|meetings tomorrow|show meetings|list meetings|next meeting|check schedule|what.?s next|check my calendar)\b",
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
_GROUP_ISSUE_SIGNALS = re.compile(
    r"\b(issue|problem|spam|going on|activity|summary|happening|trouble|concern|report)\b",
    re.IGNORECASE,
)
_SAVE_NOTE_PATTERNS = re.compile(
    r"\b(note this|note:|save this as|save as note|remember this|jot this|write this down|log this"
    r"|save this note|quick note|add note|make a note)\b",
    re.IGNORECASE,
)
_LIST_NOTES_PATTERNS = re.compile(
    r"\b(my notes|show notes|list notes|what notes|see notes|view notes|recent notes|saved notes|get my notes)\b",
    re.IGNORECASE,
)
_SAVE_LINK_PATTERNS = re.compile(
    r"\b(save.*link|save.*url|save.*http|remember.*link|bookmark|save for later|keep this link|save this link)\b",
    re.IGNORECASE,
)
_CREATE_TASK_PATTERNS = re.compile(
    r"\b(create task|add task|new task|task:|to do:|todo:|add to.{0,10}task|add.{0,10}to my list"
    r"|remind me to|i need to|don.t forget to)\b",
    re.IGNORECASE,
)
_LIST_TASKS_PATTERNS = re.compile(
    r"\b(my tasks|show tasks|list tasks|pending tasks|what tasks|see tasks|open tasks|to.do list)\b",
    re.IGNORECASE,
)


def _keyword_intent(message: str) -> str | None:
    """Return a best-guess intent from keyword matching, or None if uncertain."""
    msg = message.lower()

    # High-confidence exact-match intents first
    if _LIST_MEETINGS_PATTERNS.search(msg):
        return "list_meetings"
    if _LIST_REMINDERS_PATTERNS.search(msg):
        return "list_reminders"
    if _LIST_NOTES_PATTERNS.search(msg):
        return "list_notes"
    if _LIST_TASKS_PATTERNS.search(msg):
        return "list_tasks"

    # Group query: requires group-noun + issue-signal
    if _GROUP_PATTERNS.search(msg) and _GROUP_ISSUE_SIGNALS.search(msg):
        return "group_query"

    # Save note
    if _SAVE_NOTE_PATTERNS.search(msg):
        return "save_note"

    # Save link — message contains http/https URL and save/remember verb
    if re.search(r"https?://", msg) and re.search(r"\b(save|remember|bookmark|keep|note)\b", msg):
        return "save_link"

    # Create task
    if _CREATE_TASK_PATTERNS.search(msg):
        return "create_task"

    # Schedule: needs schedule-verb OR meeting-noun
    if _SCHEDULE_PATTERNS.search(msg) or _MEETING_NOUN.search(msg):
        return "schedule_meeting"

    return None


def _extract_datetime_hint(message: str) -> str | None:
    """
    Extract a compound datetime hint from the message.
    Collects both day-name and time-of-day components so that
    "tomorrow at 3 PM" is returned whole, not just "tomorrow".
    """
    day_pat = re.compile(
        r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
        r"|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)"
        r"|this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"|in\s+\d+\s+days?)\b",
        re.IGNORECASE,
    )
    time_pat = re.compile(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)\b",
        re.IGNORECASE,
    )
    in_pat = re.compile(
        r"\b(in\s+\d+\s*(?:minutes?|hours?|days?|weeks?))\b",
        re.IGNORECASE,
    )

    day_m = day_pat.search(message)
    time_m = time_pat.search(message)
    in_m = in_pat.search(message)

    parts = []
    if day_m:
        parts.append(day_m.group(0).strip())
    if time_m:
        t = time_m.group(0).strip()
        if t not in parts:
            parts.append(t)

    if parts:
        return " ".join(parts)

    if in_m:
        return in_m.group(0).strip()

    return None


def _keyword_parse(message: str) -> dict:
    """Build a minimal parsed dict from keyword matching for schedule/create fallback."""
    datetime_hint = _extract_datetime_hint(message)

    # Extract title by stripping scheduling verbs and time phrases
    title = re.sub(
        r"^(schedule|book|create|add|save|plan|set up|arrange|can you schedule|"
        r"set a meeting for|set meeting for|make a meeting for|"
        r"new meeting|a meeting|one meeting|my meeting)\s*",
        "", message.strip(), flags=re.IGNORECASE
    ).strip()
    if datetime_hint:
        title = re.sub(re.escape(datetime_hint), "", title, flags=re.IGNORECASE).strip().strip("-–—,").strip()
    # Strip time-only leftovers
    title = re.sub(
        r"\b(at|on|for|tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
        r"|next\s+\w+|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", "", title, flags=re.IGNORECASE
    ).strip().strip("-–—,").strip()
    if not title or len(title) < 2:
        title = None

    return {
        "intent": "schedule_meeting",
        "title": title,
        "datetime_hint": datetime_hint,
        "participants": [],
        "priority": "medium",
        "timezone": None,
        "resource_url": None,
        "resource_note": None,
        "reply": "Sure! Let me get that scheduled for you.",
    }


def _keyword_parse_note(message: str) -> str | None:
    """Extract note content from message, stripping the save/note trigger phrase."""
    clean = re.sub(
        r"^(note this[:\s]*|note[:\s]+|save this as a? note[:\s]*|save this[:\s]+|"
        r"remember this[:\s]*|jot this down[:\s]*|write this down[:\s]*|"
        r"log this[:\s]*|save this note[:\s]*|quick note[:\s]*|add note[:\s]*|make a note[:\s]*)",
        "", message.strip(), flags=re.IGNORECASE
    ).strip()
    if message.reply_to_message_text:
        return message.reply_to_message_text  # handled by caller
    return clean or None


def _keyword_parse_task(message: str) -> str | None:
    """Extract task title from message."""
    clean = re.sub(
        r"^(create task[:\s]*|add task[:\s]*|new task[:\s]*|task[:\s]+|to do[:\s]*|todo[:\s]+|"
        r"add to.{0,10}task list[:\s]*|remind me to\s*|i need to\s*|don.t forget to\s*)",
        "", message.strip(), flags=re.IGNORECASE
    ).strip()
    return clean or None


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
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON in AI response: {text[:200]!r}")


def _resolve_datetime(key_info: dict, hint: str, user_tz: str | None) -> dict:
    """Ask the AI to parse a natural language datetime hint to ISO UTC."""
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    tz_note = f" User timezone: {user_tz}." if user_tz else ""
    prompt = f"Today is {now_str}.{tz_note}\nParse this date/time phrase: \"{hint}\""
    try:
        raw = _call_ai(key_info, _RESOLVE_DATETIME_SYSTEM, prompt)
        result = _parse_json(raw)
        _log.debug("datetime resolve hint=%r → %s", hint, result)
        # If AI returned null iso for a recognisable day word, default to noon today/tomorrow
        if not result.get("iso"):
            result = _fallback_datetime(hint)
        return result
    except Exception as exc:
        _log.warning("datetime resolve failed: %s — using fallback", exc)
        return _fallback_datetime(hint)


def _fallback_datetime(hint: str) -> dict:
    """
    Last-resort datetime: if the hint contains a recognisable day word,
    resolve to noon on that day in UTC rather than failing completely.
    """
    now = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    h = hint.lower()

    day_offsets = {
        "today": 0, "tomorrow": 1,
        "monday": None, "tuesday": None, "wednesday": None,
        "thursday": None, "friday": None, "saturday": None, "sunday": None,
    }
    weekday_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    for word, offset in day_offsets.items():
        if word in h:
            if offset is not None:
                target = now + timedelta(days=offset)
            else:
                # Next occurrence of weekday
                target_wd = weekday_map[word]
                days_ahead = (target_wd - now.weekday()) % 7 or 7
                target = now + timedelta(days=days_ahead)

            # Try to extract a time from the hint
            time_m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", h, re.IGNORECASE)
            if time_m:
                hour = int(time_m.group(1))
                minute = int(time_m.group(2) or 0)
                meridiem = time_m.group(3).lower()
                if meridiem == "pm" and hour != 12:
                    hour += 12
                elif meridiem == "am" and hour == 12:
                    hour = 0
                target = target.replace(hour=hour, minute=minute)

            iso = target.strftime("%Y-%m-%dT%H:%M:%S")
            human = target.strftime("%A %d %B at %I:%M %p UTC")
            return {"iso": iso, "human": human}

    # "in N hours/minutes/days"
    in_m = re.search(r"in\s+(\d+)\s*(minute|hour|day)s?", h, re.IGNORECASE)
    if in_m:
        n, unit = int(in_m.group(1)), in_m.group(2).lower()
        delta = timedelta(minutes=n) if unit == "minute" else timedelta(hours=n) if unit == "hour" else timedelta(days=n)
        target = datetime.utcnow() + delta
        iso = target.strftime("%Y-%m-%dT%H:%M:%S")
        human = target.strftime("%A %d %B at %I:%M %p UTC")
        return {"iso": iso, "human": human}

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


def _time_suggestions() -> list:
    """Return quick-pick time options relative to now (UTC)."""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    # Today at 3 PM, 5 PM; tomorrow at 9 AM, 12 PM, 3 PM; this Friday
    suggestions = []
    today_3pm = now.replace(hour=15, minute=0, second=0, microsecond=0)
    today_5pm = now.replace(hour=17, minute=0, second=0, microsecond=0)
    tomorrow = now + timedelta(days=1)
    tmr_9am = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
    tmr_12pm = tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)
    tmr_3pm = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
    # Next Friday
    days_to_friday = (4 - now.weekday()) % 7 or 7
    friday_3pm = (now + timedelta(days=days_to_friday)).replace(hour=15, minute=0, second=0, microsecond=0)

    if today_3pm > now:
        suggestions.append({"label": "Today 3 PM", "value": "today at 3 PM"})
    if today_5pm > now:
        suggestions.append({"label": "Today 5 PM", "value": "today at 5 PM"})
    suggestions.append({"label": "Tomorrow 9 AM", "value": "tomorrow at 9 AM"})
    suggestions.append({"label": "Tomorrow 3 PM", "value": "tomorrow at 3 PM"})
    suggestions.append({"label": friday_3pm.strftime("Fri %d %b 3 PM"), "value": friday_3pm.strftime("%A at 3 PM")})
    suggestions.append({"label": "Pick a time…", "value": None})  # sentinel for custom input
    return suggestions


def _meeting_title_suggestions() -> list:
    return [
        {"label": "Quick Call", "value": "Quick Call"},
        {"label": "Team Sync", "value": "Team Sync"},
        {"label": "1:1 Meeting", "value": "1:1 Meeting"},
        {"label": "Project Review", "value": "Project Review"},
        {"label": "Investor Call", "value": "Investor Call"},
        {"label": "Custom…", "value": None},
    ]


def _is_self_contained_schedule_request(message: str) -> bool:
    """
    Return True if the message looks like a complete, self-contained scheduling
    request (has both a scheduling verb/noun AND a time reference).
    Used to escape a stale conversation state.
    """
    has_schedule = bool(_SCHEDULE_PATTERNS.search(message) or _MEETING_NOUN.search(message))
    has_time = bool(_extract_datetime_hint(message))
    return has_schedule and has_time


# ─────────────────────────────────────────────────────────────────────────────
# Intent handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_schedule_meeting(user_id: int, parsed: dict, key_info: dict, user_tz: str | None) -> dict:
    from ..models import db, Meeting

    data = {
        "title": parsed.get("title"),
        "datetime_hint": parsed.get("datetime_hint"),
        "participants": parsed.get("participants") or [],
        "priority": parsed.get("priority") or "medium",
        "timezone": parsed.get("timezone") or user_tz or "UTC",
    }
    _log.debug("schedule_meeting data=%s", data)

    if not data["title"]:
        _save_state(user_id, "schedule_meeting", data, "title")
        return {
            "reply": "What's the title or topic of the meeting?",
            "intent": "schedule_meeting",
            "data": None,
            "suggestions": _meeting_title_suggestions(),
        }

    if not data["datetime_hint"]:
        _save_state(user_id, "schedule_meeting", data, "datetime_hint")
        return {
            "reply": f"When should I schedule \"{data['title']}\"?",
            "intent": "schedule_meeting",
            "data": None,
            "suggestions": _time_suggestions(),
        }

    dt_result = _resolve_datetime(key_info, data["datetime_hint"], data["timezone"])
    if not dt_result.get("iso"):
        _save_state(user_id, "schedule_meeting", data, "datetime_hint")
        return {
            "reply": (
                f"I couldn't parse \"{data['datetime_hint']}\" as a time. "
                "Pick one below or type your own:"
            ),
            "intent": "schedule_meeting",
            "data": None,
            "suggestions": _time_suggestions(),
        }

    scheduled_at = datetime.fromisoformat(dt_result["iso"])

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

    participant_str = f" with {', '.join(data['participants'])}" if data["participants"] else ""
    return {
        "reply": (
            f"✅ Meeting scheduled!\n\n"
            f"📅 {meeting.title}{participant_str}\n"
            f"🕒 {dt_result['human']}\n"
            f"⚡ Priority: {meeting.priority}\n\n"
            f"Want to attach any resources (links, agenda, notes)?"
        ),
        "intent": "schedule_meeting",
        "data": meeting.to_dict(),
    }


def _handle_save_note(user_id: int, content: str) -> dict:
    from ..models import db, Note
    if not content or not content.strip():
        return {"reply": "What would you like me to note down?", "intent": "save_note", "data": None}
    note = Note(user_id=user_id, content=content.strip()[:5000], source="bot", tags=[])
    db.session.add(note)
    db.session.commit()
    _log.info("save_note user=%s len=%d", user_id, len(content))
    return {
        "reply": f"📝 Note saved: \"{content.strip()[:80]}{'…' if len(content) > 80 else ''}\"",
        "intent": "save_note",
        "data": note.to_dict(),
    }


def _handle_list_notes(user_id: int) -> dict:
    from ..models import Note
    notes = (
        Note.query
        .filter_by(user_id=user_id)
        .order_by(Note.created_at.desc())
        .limit(8)
        .all()
    )
    if not notes:
        return {"reply": "You have no notes yet. Try saying \"Note this: your message\".", "intent": "list_notes", "data": {"notes": []}}
    lines = [f"• {n.content[:100]}{'…' if len(n.content) > 100 else ''}" for n in notes]
    reply = f"Here are your {len(notes)} most recent notes:\n\n" + "\n".join(lines)
    return {"reply": reply, "intent": "list_notes", "data": {"notes": [n.to_dict() for n in notes]}}


def _handle_save_link(user_id: int, url: str, label: str | None = None) -> dict:
    from ..models import db, Note
    content = f"{label or 'Saved link'}: {url}"
    note = Note(user_id=user_id, content=content[:5000], source="bot", tags=["link"])
    db.session.add(note)
    db.session.commit()
    _log.info("save_link user=%s url=%s", user_id, url[:80])
    return {
        "reply": f"🔗 Link saved: {url[:80]}",
        "intent": "save_link",
        "data": note.to_dict(),
    }


def _handle_create_task(user_id: int, title: str) -> dict:
    from ..models import db, Task
    if not title or not title.strip():
        return {"reply": "What task should I create?", "intent": "create_task", "data": None}
    task = Task(user_id=user_id, title=title.strip()[:500], status="todo", source="bot")
    db.session.add(task)
    db.session.commit()
    _log.info("create_task user=%s title=%r", user_id, title[:60])
    return {
        "reply": f"✅ Task created: \"{task.title}\"",
        "intent": "create_task",
        "data": task.to_dict(),
    }


def _handle_list_tasks(user_id: int) -> dict:
    from ..models import Task
    tasks = (
        Task.query
        .filter_by(user_id=user_id, status="todo")
        .order_by(Task.created_at.desc())
        .limit(10)
        .all()
    )
    if not tasks:
        return {"reply": "You have no pending tasks. Try saying \"Create task: your task\".", "intent": "list_tasks", "data": {"tasks": []}}
    lines = [f"• {t.title}" for t in tasks]
    reply = f"You have {len(tasks)} pending task{'s' if len(tasks) != 1 else ''}:\n\n" + "\n".join(lines)
    return {"reply": reply, "intent": "list_tasks", "data": {"tasks": [t.to_dict() for t in tasks]}}


def _handle_continue_state(user_id: int, state, message: str, key_info: dict, user_tz: str | None) -> dict:
    data = dict(state.collected_data or {})
    awaiting = state.awaiting_field
    intent = state.pending_intent

    if intent == "schedule_meeting":
        if awaiting == "title":
            data["title"] = message.strip()[:200]
        elif awaiting == "datetime_hint":
            # Try to extract a proper datetime hint from the answer
            hint = _extract_datetime_hint(message) or message.strip()
            data["datetime_hint"] = hint
        elif awaiting == "resources":
            meeting_id = data.get("meeting_id")
            if meeting_id:
                return _attach_resource(user_id, meeting_id, message, state)
        _clear_state(user_id)
        return _handle_schedule_meeting(user_id, data, key_info, user_tz)

    if intent == "save_note" and awaiting == "content":
        _clear_state(user_id)
        return _handle_save_note(user_id, message.strip())

    if intent == "create_task" and awaiting == "title":
        _clear_state(user_id)
        return _handle_create_task(user_id, message.strip())

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

    return {"reply": f"Resource added to \"{meeting.title}\".", "intent": "add_resource", "data": meeting.to_dict()}


def _handle_list_meetings(user_id: int) -> dict:
    from ..models import Meeting
    now = datetime.utcnow()
    meetings = (
        Meeting.query
        .filter(Meeting.owner_user_id == user_id, Meeting.scheduled_at >= now, Meeting.is_complete == False)
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
        .filter(WorkspaceReminder.owner_user_id == user_id, WorkspaceReminder.remind_at >= now, WorkspaceReminder.is_delivered == False)
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

    try:
        key_info = get_workspace_ai_key(user)
    except QuotaExceededError as exc:
        _log.info("QuotaExceededError for user %s: %s", user_id, exc)
        return {"reply": str(exc), "intent": "error", "data": None}
    except Exception as exc:
        _log.warning("get_workspace_ai_key failed: %s", exc)
        key_info = {}

    ai_available = bool(key_info.get("api_key"))

    # ── Conversation state resume ─────────────────────────────────────────────
    state = _get_state(user_id)
    if state:
        _log.debug("Pending state intent=%s awaiting=%s", state.pending_intent, state.awaiting_field)

        # Escape 1: high-confidence different intent from keyword pre-filter
        escape_intent = _keyword_intent(message)
        if escape_intent and escape_intent != state.pending_intent and escape_intent in (
            "group_query", "list_meetings", "list_reminders", "list_notes", "list_tasks"
        ):
            _log.info("State escape via different intent: %s → %s", state.pending_intent, escape_intent)
            _clear_state(user_id)
            state = None

        # Escape 2: complete self-contained new scheduling request while waiting for title/datetime
        elif (
            state.pending_intent == "schedule_meeting"
            and state.awaiting_field in ("title", "datetime_hint")
            and _is_self_contained_schedule_request(message)
        ):
            _log.info("State escape: complete new scheduling request, clearing stale state")
            _clear_state(user_id)
            state = None

        if state:
            try:
                return _handle_continue_state(user_id, state, message, key_info, user_tz)
            except Exception as exc:
                _log.warning("continue_state failed: %s", exc)
                _clear_state(user_id)

    parsed = None
    intent = None

    # ── Step 1: Keyword pre-filter for high-confidence entity-free intents ────
    # Runs BEFORE AI to prevent AI from misclassifying query/list intents
    # as schedule_meeting when time words appear in the message.
    keyword_intent = _keyword_intent(message)
    _log.debug("keyword_intent=%s", keyword_intent)
    if keyword_intent in ("group_query", "list_meetings", "list_reminders", "list_notes", "list_tasks"):
        intent = keyword_intent
        parsed = {"intent": intent}
        _log.info("High-confidence keyword intent=%s — skipping AI for routing", intent)

    # ── Step 2: AI parsing for everything else ────────────────────────────────
    if intent is None and ai_available:
        try:
            raw = _call_ai(key_info, _INTENT_SYSTEM, message)
            _log.debug("AI raw response: %s", raw[:300])
            parsed = _parse_json(raw)
            intent = parsed.get("intent", "general")
            _log.info("AI intent=%s title=%r datetime_hint=%r resource_note=%r",
                      intent, parsed.get("title"), parsed.get("datetime_hint"), str(parsed.get("resource_note") or "")[:40])

            # Sanity-check: AI said schedule_meeting but keyword says query — trust keyword
            if intent == "schedule_meeting" and keyword_intent in (
                "group_query", "list_meetings", "list_reminders", "list_notes", "list_tasks"
            ):
                _log.warning("AI intent overridden %s → %s (keyword signal)", intent, keyword_intent)
                intent = keyword_intent
                parsed = {"intent": intent}
        except Exception as exc:
            _log.warning("AI intent parse failed (%s) — falling back to keyword", exc)
            parsed = None
            intent = None

    # ── Step 3: Pure keyword fallback ────────────────────────────────────────
    if intent is None:
        intent = keyword_intent or "general"
        _log.info("Keyword fallback intent=%s", intent)
        if intent == "schedule_meeting":
            parsed = _keyword_parse(message)
        elif intent == "save_note":
            parsed = {"intent": "save_note", "resource_note": _keyword_parse_note(message) or message.strip()}
        elif intent == "create_task":
            parsed = {"intent": "create_task", "title": _keyword_parse_task(message) or message.strip()}
        elif intent == "save_link":
            url_m = re.search(r"https?://\S+", message)
            parsed = {"intent": "save_link", "resource_url": url_m.group(0) if url_m else None}
        else:
            parsed = {"intent": intent}

    # ── Step 4: Route to handler ──────────────────────────────────────────────
    try:
        if intent == "schedule_meeting":
            return _handle_schedule_meeting(user_id, parsed or {}, key_info, user_tz)

        if intent == "list_meetings":
            return _handle_list_meetings(user_id)

        if intent == "list_reminders":
            return _handle_list_reminders(user_id)

        if intent == "save_note":
            content = (parsed or {}).get("resource_note") or ""
            if not content.strip():
                # Ask for content in multi-turn
                _save_state(user_id, "save_note", {}, "content")
                return {"reply": "What would you like me to note down?", "intent": "save_note", "data": None}
            return _handle_save_note(user_id, content)

        if intent == "list_notes":
            return _handle_list_notes(user_id)

        if intent == "save_link":
            url = (parsed or {}).get("resource_url")
            if not url:
                url_m = re.search(r"https?://\S+", message)
                url = url_m.group(0) if url_m else None
            if not url:
                return {"reply": "Please include the URL you'd like me to save.", "intent": "save_link", "data": None}
            return _handle_save_link(user_id, url)

        if intent == "create_task":
            title = (parsed or {}).get("title") or ""
            if not title.strip():
                _save_state(user_id, "create_task", {}, "title")
                return {"reply": "What task should I create?", "intent": "create_task", "data": None}
            return _handle_create_task(user_id, title)

        if intent == "list_tasks":
            return _handle_list_tasks(user_id)

        if intent == "group_query":
            return _handle_group_query(user_id, key_info)

        if intent == "add_resource":
            return _handle_add_resource(user_id, parsed or {})

        # general
        ai_reply = (parsed or {}).get("reply") if ai_available else None
        return {
            "reply": ai_reply or (
                "I can help you:\n"
                "• Schedule meetings — \"Book call Friday 3 PM\"\n"
                "• Set reminders — \"Remind me about X\"\n"
                "• Save notes — \"Note this: ...\"\n"
                "• Create tasks — \"Task: write spec\"\n"
                "• Save links — \"Save https://...\"\n"
                "• Check your schedule — \"Any meetings today?\"\n"
                "• Group insights — \"Any issues in my group?\"\n\n"
                "What can I help you with?"
            ),
            "intent": "general",
            "data": None,
        }
    except Exception as exc:
        _log.error("intent handler %s failed: %s", intent, exc, exc_info=True)
        return {"reply": "Something went wrong processing your request. Please try again.", "intent": "error", "data": None}
