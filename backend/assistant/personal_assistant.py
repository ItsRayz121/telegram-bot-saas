"""
personal_assistant.py — public entry point.

process_message() is called by /api/assistant/chat and the Telegram DM handler.
All logic lives in backend/assistant/handlers/. This file is now a thin orchestrator
with intent routing, per-intent rate limiting (Phase 6.5), and context injection.
"""
from __future__ import annotations

import logging
import re

_log = logging.getLogger(__name__)

# ── Per-intent rate limits (Phase 6.5) ───────────────────────────────────────
# requests_per_minute per user per intent
_INTENT_RATE_LIMITS: dict[str, int] = {
    "schedule_meeting":  5,
    "create_reminder":   5,
    "group_query":       3,
    "trigger_digest":    2,
    "post_announcement": 3,
    "get_group_stats":   5,
    "general":          20,
    "_default":         15,
}


def _check_intent_rate_limit(user_id: int, intent: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    limit = _INTENT_RATE_LIMITS.get(intent, _INTENT_RATE_LIMITS["_default"])
    try:
        import redis as _redis
        from ..config import Config
        r = _redis.from_url(getattr(Config, "REDIS_URL", "redis://localhost:6379/0"))
        key = f"rl:intent:{user_id}:{intent}"
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        count, _ = pipe.execute()
        return count <= limit
    except Exception:
        # Redis unavailable — allow through
        return True


# ── Public entry point ────────────────────────────────────────────────────────

def process_message(user_id: int, message: str, user_tz: str | None = None) -> dict:
    """
    Process a natural language message from the user.
    Must be called inside a Flask app context.
    Returns {"reply": str, "intent": str, "data": dict|None, "suggestions": list}.
    """
    from ..assistant.ai_key_resolver import get_workspace_ai_key, QuotaExceededError
    from ..assistant.context_service import AssistantContextService
    from ..models import User

    # Import handler functions from the package
    from .handlers import (
        handle_schedule_meeting, handle_create_reminder, handle_upcoming_schedule,
        handle_save_note, handle_list_notes, handle_search_notes, handle_summarize_notes,
        handle_save_link, handle_create_task, handle_list_tasks,
        handle_list_meetings, handle_list_reminders,
        handle_group_query, handle_general, handle_add_resource, handle_continue_state,
    )
    from .handlers._parsers import (
        keyword_intent, keyword_parse, keyword_parse_note, keyword_parse_task, keyword_parse_reminder,
        extract_datetime_hint,
    )
    from .handlers._state import get_state, clear_state
    from .handlers._patterns import SCHEDULE_PATTERNS, MEETING_NOUN
    from .handlers._ai import call_ai, parse_json
    from .handlers._prompts import INTENT_SYSTEM

    _log.info("process_message user_id=%s message=%r", user_id, message[:120])

    user = User.query.get(user_id)
    if not user:
        return {"reply": "User not found.", "intent": "error", "data": None, "suggestions": []}

    try:
        key_info = get_workspace_ai_key(user)
    except QuotaExceededError as exc:
        return {"reply": str(exc), "intent": "error", "data": None, "suggestions": []}
    except Exception as exc:
        _log.warning("get_workspace_ai_key failed: %s", exc)
        key_info = {}

    ai_available = bool(key_info.get("api_key"))

    # ── Build workspace context ───────────────────────────────────────────────
    try:
        ctx = AssistantContextService.build(user_id)
        if not user_tz and ctx.timezone and ctx.timezone != "UTC":
            user_tz = ctx.timezone
    except Exception as exc:
        _log.warning("AssistantContextService.build failed: %s", exc)
        ctx = None

    # ── Conversation state resume ─────────────────────────────────────────────
    state = get_state(user_id)
    if state:
        _log.debug("Pending state intent=%s awaiting=%s", state.pending_intent, state.awaiting_field)
        escape_intent = keyword_intent(message)
        high_confidence_escapes = (
            "group_query", "list_meetings", "list_reminders",
            "list_notes", "list_tasks", "upcoming_schedule",
        )
        if escape_intent and escape_intent != state.pending_intent and escape_intent in high_confidence_escapes:
            _log.info("State escape: %s → %s", state.pending_intent, escape_intent)
            clear_state(user_id)
            state = None
        elif (
            state.pending_intent == "schedule_meeting"
            and state.awaiting_field in ("title", "datetime_hint")
            and _is_self_contained_schedule_request(message)
        ):
            _log.info("State escape: complete new scheduling request")
            clear_state(user_id)
            state = None

        if state:
            try:
                result = handle_continue_state(user_id, state, message, key_info, user_tz)
                return _ensure_suggestions(result)
            except Exception as exc:
                _log.warning("continue_state failed: %s", exc)
                clear_state(user_id)

    # ── Intent detection ──────────────────────────────────────────────────────
    parsed = None
    intent = None

    # Step 1: high-confidence keyword pre-filter
    kw_intent = keyword_intent(message)
    _log.debug("keyword_intent=%s", kw_intent)
    high_confidence_keywords = (
        "group_query", "list_meetings", "list_reminders",
        "list_notes", "list_tasks", "upcoming_schedule",
    )
    if kw_intent in high_confidence_keywords:
        intent = kw_intent
        parsed = {"intent": intent}

    # Step 2: AI parsing with conversation history context
    enriched_message = message
    if ctx and ctx.recent_conversation:
        history_lines = []
        for turn in ctx.recent_conversation[-4:]:
            role = "User" if turn["direction"] == "in" else "Assistant"
            history_lines.append(f"{role}: {turn['content'][:100]}")
        if history_lines:
            enriched_message = (
                "[Recent conversation for context]\n"
                + "\n".join(history_lines)
                + f"\n[Current message]\n{message}"
            )

    if intent is None and ai_available:
        try:
            raw = call_ai(key_info, INTENT_SYSTEM, enriched_message)
            _log.debug("AI raw: %s", raw[:300])
            parsed = parse_json(raw)
            intent = parsed.get("intent", "general")
            if intent == "schedule_meeting" and kw_intent in high_confidence_keywords:
                _log.warning("AI intent overridden %s → %s (keyword signal)", intent, kw_intent)
                intent = kw_intent
                parsed = {"intent": intent}
        except Exception as exc:
            _log.warning("AI intent parse failed (%s) — keyword fallback", exc)
            parsed = None
            intent = None

    # Step 3: pure keyword fallback
    if intent is None:
        intent = kw_intent or "general"
        if intent == "schedule_meeting":
            parsed = keyword_parse(message)
        elif intent == "create_reminder":
            text, dt_hint = keyword_parse_reminder(message)
            parsed = {"intent": "create_reminder", "title": text, "datetime_hint": dt_hint}
        elif intent == "save_note":
            parsed = {"intent": "save_note", "resource_note": keyword_parse_note(message) or message.strip()}
        elif intent == "create_task":
            parsed = {"intent": "create_task", "title": keyword_parse_task(message) or message.strip()}
        elif intent == "save_link":
            url_m = re.search(r"https?://\S+", message)
            parsed = {"intent": "save_link", "resource_url": url_m.group(0) if url_m else None}
        else:
            parsed = {"intent": intent}

    # ── Per-intent rate limiting (Phase 6.5) ─────────────────────────────────
    if not _check_intent_rate_limit(user_id, intent):
        _log.info("Rate limited user=%s intent=%s", user_id, intent)
        return {
            "reply": "You're doing that too quickly — please wait a moment and try again.",
            "intent": intent,
            "data": None,
            "suggestions": [],
        }

    # ── Route to handler ──────────────────────────────────────────────────────
    try:
        p = parsed or {}

        if intent == "schedule_meeting":
            result = handle_schedule_meeting(user_id, p, key_info, user_tz)
        elif intent == "list_meetings":
            result = handle_list_meetings(user_id)
        elif intent == "create_reminder":
            result = handle_create_reminder(user_id, p, key_info, user_tz)
        elif intent == "list_reminders":
            result = handle_list_reminders(user_id)
        elif intent == "upcoming_schedule":
            result = handle_upcoming_schedule(user_id)
        elif intent == "save_note":
            content = p.get("resource_note") or ""
            if not content.strip():
                from .handlers._state import save_state
                save_state(user_id, "save_note", {}, "content")
                result = {"reply": "What would you like me to note down?", "intent": "save_note", "data": None}
            else:
                result = handle_save_note(user_id, content)
        elif intent == "list_notes":
            result = handle_list_notes(user_id)
        elif intent == "search_notes":
            query = p.get("query") or message.strip()
            query = re.sub(
                r"^(search|find|look\s+for|look\s+up)\s+(my\s+)?notes?\s*(for|about)?\s*",
                "", query, flags=re.I,
            ).strip() or query
            result = handle_search_notes(user_id, query, key_info)
        elif intent == "summarize_notes":
            result = handle_summarize_notes(user_id, key_info)
        elif intent == "save_link":
            url = p.get("resource_url")
            if not url:
                url_m = re.search(r"https?://\S+", message)
                url = url_m.group(0) if url_m else None
            if not url:
                result = {"reply": "Please include the URL you'd like me to save.", "intent": "save_link", "data": None}
            else:
                result = handle_save_link(user_id, url)
        elif intent == "create_task":
            title = p.get("title") or ""
            result = handle_create_task(user_id, title)
        elif intent == "list_tasks":
            result = handle_list_tasks(user_id)
        elif intent == "group_query":
            result = handle_group_query(user_id, key_info)
        elif intent == "add_resource":
            result = handle_add_resource(user_id, p)
        elif intent in ("trigger_digest", "post_announcement", "get_group_stats",
                        "list_auto_replies", "update_automod"):
            from ..assistant.actions import run_action
            action_args = p.copy()
            if intent == "post_announcement" and not action_args.get("text"):
                text = re.sub(
                    r"^(post|announce|broadcast|send)\s+(an?\s+)?(announcement|message|update)"
                    r"\s*(to\s+\w+\s+group\s*:?)?\s*",
                    "", message, flags=re.I,
                ).strip()
                action_args["text"] = text
            if intent == "update_automod":
                action_args["enable"] = not re.search(r"\b(disable|turn\s+off)\b", message, re.I)
            result = run_action(intent, user, action_args)
        else:
            ai_reply = p.get("reply") if ai_available else None
            result = handle_general(user_id, message, key_info, ai_reply, ctx)

        return _ensure_suggestions(result)

    except Exception as exc:
        _log.error("intent handler %s failed: %s", intent, exc, exc_info=True)
        return {"reply": "Something went wrong. Please try again.", "intent": "error",
                "data": None, "suggestions": []}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_self_contained_schedule_request(message: str) -> bool:
    from .handlers._patterns import SCHEDULE_PATTERNS, MEETING_NOUN
    from .handlers._parsers import extract_datetime_hint
    has_schedule = bool(SCHEDULE_PATTERNS.search(message) or MEETING_NOUN.search(message))
    return has_schedule and bool(extract_datetime_hint(message))


def _ensure_suggestions(result: dict) -> dict:
    result.setdefault("suggestions", [])
    return result
