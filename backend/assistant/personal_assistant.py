"""
personal_assistant.py — conversational-first orchestration layer.

Architecture:
  Layer 1 — Conversational AI (general chat, Q&A, advice, analysis)
  Layer 2 — Intent Detection / Orchestration (classifies + routes)
  Layer 3 — Workflow Engine (reminders, tasks, meetings, notes)

Layer 3 activates ONLY when actionable intent is detected with confidence.
Hybrid intents get a conversational reply FIRST, then offer the workflow action.
"""
from __future__ import annotations

import logging
import re

_log = logging.getLogger(__name__)

# ── Per-intent rate limits ────────────────────────────────────────────────────
_INTENT_RATE_LIMITS: dict[str, int] = {
    "schedule_meeting":  5,
    "create_reminder":   5,
    "group_query":       3,
    "trigger_digest":    2,
    "post_announcement": 3,
    "get_group_stats":   5,
    "analyze_day":       10,
    "expand_analysis":   10,
    "general":          30,
    "_default":         15,
}


def _check_intent_rate_limit(user_id: int, intent: str) -> bool:
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

    from .handlers import (
        handle_schedule_meeting, handle_create_reminder, handle_upcoming_schedule,
        handle_save_note, handle_list_notes, handle_search_notes, handle_summarize_notes,
        handle_save_link, handle_create_task, handle_list_tasks,
        handle_list_meetings, handle_list_reminders,
        handle_group_query, handle_general, handle_add_resource, handle_continue_state,
        handle_analyze_day, handle_expand_analysis,
    )
    from .handlers._parsers import (
        keyword_intent, keyword_parse, keyword_parse_note, keyword_parse_task,
        keyword_parse_reminder, extract_datetime_hint, normalize_typos,
        low_confidence_suggestions,
    )
    from .handlers._state import get_state, clear_state
    from .handlers._patterns import SCHEDULE_PATTERNS, MEETING_NOUN
    from .handlers._ai import call_ai, parse_json
    from .handlers._prompts import ORCHESTRATION_SYSTEM, INTENT_SYSTEM

    _log.info("process_message user_id=%s message=%r", user_id, message[:120])

    normalized = normalize_typos(message)
    if normalized != message:
        _log.info("Typo normalization: %r → %r", message, normalized)
    message = normalized

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
            "create_reminder", "save_note", "create_task", "save_link",
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
                return _ensure_suggestions(result, user_id, message, ctx)
            except Exception as exc:
                _log.warning("continue_state failed: %s", exc)
                clear_state(user_id)

    # ── Intent detection — new orchestration layer ────────────────────────────
    parsed = None
    intent = None
    orch_layer = None     # conversational | actionable | hybrid
    conv_reply = None     # pre-generated conversational reply for hybrid intents

    # Step 1: high-confidence keyword pre-filter (no AI needed)
    if re.match(r"expand\s+analysis", message, re.IGNORECASE):
        intent = "expand_analysis"
        parsed = {"intent": "expand_analysis"}
        orch_layer = "actionable"

    kw_intent = keyword_intent(message)
    _log.debug("keyword_intent=%s", kw_intent)
    high_confidence_keywords = (
        "group_query", "list_meetings", "list_reminders",
        "list_notes", "list_tasks", "upcoming_schedule", "analyze_day",
    )
    if intent is None and kw_intent in high_confidence_keywords:
        intent = kw_intent
        parsed = {"intent": intent}
        orch_layer = "actionable"

    # Step 2: AI orchestration — detects layer + extracts all fields in one pass
    enriched_message = _enrich_with_history(message, ctx)

    if intent is None and ai_available:
        try:
            raw = call_ai(key_info, ORCHESTRATION_SYSTEM, enriched_message)
            _log.debug("Orchestration raw: %s", raw[:400])
            orch = parse_json(raw)
            orch_layer = orch.get("layer", "conversational")
            orch_intent = orch.get("intent", "general")
            confidence = float(orch.get("confidence", 0.8))
            conv_reply = orch.get("conversational_reply", "") or ""
            extracted = orch.get("extracted") or {}

            # Safety: don't let low-confidence actionable override obvious conversation
            if orch_layer == "actionable" and confidence < 0.6:
                orch_layer = "conversational"
                orch_intent = "general"

            # Safety: keyword overrides AI if keyword is high-confidence
            if kw_intent in high_confidence_keywords and orch_intent == "schedule_meeting":
                orch_intent = kw_intent
                orch_layer = "actionable"

            intent = orch_intent
            # Merge extracted fields into parsed so handlers can use them
            parsed = {
                "intent": intent,
                "title": extracted.get("title"),
                "datetime_hint": extracted.get("datetime_hint"),
                "participants": extracted.get("participants") or [],
                "priority": extracted.get("priority") or "medium",
                "timezone": extracted.get("timezone"),
                "duration_minutes": extracted.get("duration_minutes"),
                "location": extracted.get("location"),
                "recurrence": extracted.get("recurrence"),
                "related_person": extracted.get("related_person"),
                "project": extracted.get("project"),
                "notes": extracted.get("notes"),
                "resource_url": extracted.get("resource_url"),
                "resource_note": extracted.get("notes"),
                "followup_required": extracted.get("followup_required"),
                "reply": conv_reply if orch_layer != "actionable" else "",
            }

        except Exception as exc:
            _log.warning("AI orchestration failed (%s) — keyword fallback", exc)
            parsed = None
            intent = None
            orch_layer = None

    # Step 3: pure keyword fallback
    if intent is None:
        intent = kw_intent or "general"
        orch_layer = "actionable" if intent != "general" else "conversational"
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

    # ── Handle CONVERSATIONAL layer directly ──────────────────────────────────
    # For pure conversation, skip all workflow routing entirely
    if orch_layer == "conversational" and intent == "general":
        if not _check_intent_rate_limit(user_id, "general"):
            return {"reply": "You're sending messages too quickly — give me a moment.", "intent": "general", "data": None, "suggestions": []}
        result = handle_general(user_id, message, key_info, conv_reply or None, ctx)
        return _ensure_suggestions(result, user_id, message, ctx)

    # ── Handle HYBRID layer — conversational reply + optional workflow offer ──
    if orch_layer == "hybrid" and conv_reply and intent != "general":
        # Return conversational reply with a workflow suggestion appended
        action_label = _intent_to_label(intent)
        suggestions = [{"label": f"✅ {action_label}", "value": message}]
        # Add other contextual suggestions
        suggestions.extend(_contextual_suggestions(message, ctx)[:2])
        return {
            "reply": conv_reply,
            "intent": "hybrid",
            "data": {"action_intent": intent, "extracted": parsed},
            "suggestions": suggestions[:3],
        }

    # ── Per-intent rate limiting ──────────────────────────────────────────────
    if not _check_intent_rate_limit(user_id, intent):
        _log.info("Rate limited user=%s intent=%s", user_id, intent)
        return {
            "reply": "You're doing that too quickly — please wait a moment and try again.",
            "intent": intent,
            "data": None,
            "suggestions": [],
        }

    # ── Route to workflow handler ─────────────────────────────────────────────
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
            content = p.get("resource_note") or p.get("notes") or ""
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
            result = handle_create_task(user_id, p, key_info)
        elif intent == "list_tasks":
            result = handle_list_tasks(user_id)
        elif intent == "analyze_day":
            result = handle_analyze_day(user_id, key_info)
        elif intent == "expand_analysis":
            result = handle_expand_analysis(user_id, message, key_info, ctx)
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
            if not ai_available and not result.get("suggestions"):
                did_you_mean = low_confidence_suggestions(message)
                if did_you_mean:
                    result["suggestions"] = did_you_mean

        return _ensure_suggestions(result, user_id, message, ctx)

    except Exception as exc:
        _log.error("intent handler %s failed: %s", intent, exc, exc_info=True)
        return {"reply": "Something went wrong. Please try again.", "intent": "error",
                "data": None, "suggestions": []}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _enrich_with_history(message: str, ctx) -> str:
    """Add recent conversation turns to message for better AI context."""
    if not ctx or not ctx.recent_conversation:
        return message
    history_lines = []
    for turn in ctx.recent_conversation[-4:]:
        role = "User" if turn["direction"] == "in" else "Assistant"
        history_lines.append(f"{role}: {turn['content'][:120]}")
    if not history_lines:
        return message
    return (
        "[Recent conversation for context]\n"
        + "\n".join(history_lines)
        + f"\n[Current message]\n{message}"
    )


def _intent_to_label(intent: str) -> str:
    labels = {
        "schedule_meeting": "Schedule This",
        "create_reminder": "Set Reminder",
        "create_task": "Create Task",
        "save_note": "Save as Note",
        "save_link": "Save Link",
    }
    return labels.get(intent, "Do This")


def _contextual_suggestions(message: str, ctx) -> list[dict]:
    """Quick contextual suggestions based on message content."""
    suggestions = []
    msg = message.lower()
    if re.search(r"\b(meeting|call|sync|review)\b", msg):
        suggestions.append({"label": "📅 My Schedule", "value": "What's on my schedule?"})
    if re.search(r"\b(group|community|member)\b", msg):
        suggestions.append({"label": "👥 Group Health", "value": "Any issues in my groups?"})
    suggestions.append({"label": "🧠 Analyze My Day", "value": "Analyze my day"})
    return suggestions


def _is_self_contained_schedule_request(message: str) -> bool:
    from .handlers._patterns import SCHEDULE_PATTERNS, MEETING_NOUN
    from .handlers._parsers import extract_datetime_hint
    has_schedule = bool(SCHEDULE_PATTERNS.search(message) or MEETING_NOUN.search(message))
    return has_schedule and bool(extract_datetime_hint(message))


def _ensure_suggestions(result: dict, user_id: int | None, message: str = "", ctx=None) -> dict:
    result.setdefault("suggestions", [])

    # Never force suggestions onto plain conversational replies — only add them
    # for workspace/productivity intents where they genuinely help.
    intent = result.get("intent", "general")
    is_pure_chat = intent == "general" and not result.get("suggestions")
    if is_pure_chat:
        return result

    if not result["suggestions"] and user_id is not None:
        try:
            from .suggestion_engine import get_smart_suggestions
            result["suggestions"] = get_smart_suggestions(
                user_id, last_intent=intent, limit=3
            )
        except Exception:
            pass
    return result
