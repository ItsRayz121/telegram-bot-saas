"""General AI response, hybrid chat, expand analysis, and resource attachment."""
from __future__ import annotations

import logging
import re

from ._ai import call_ai, call_ai_text, parse_json
from ._prompts import HYBRID_AI_SYSTEM, EXPAND_ANALYSIS_SYSTEM, PROACTIVE_SUGGEST_SYSTEM
from ._state import clear_state, save_state

_log = logging.getLogger(__name__)

# Intents that indicate a workspace-specific question (not pure general chat)
_WORKSPACE_SIGNALS = re.compile(
    r"\b(my group|my task|my meeting|my reminder|my note|my schedule|my channel"
    r"|our group|the group|this group|telegizer|any issue|what.?s happening"
    r"|how.?s my|group activity|my workspace|my plan|my bot|automod"
    r"|what do i have|anything today|my digest|my automation)\b",
    re.IGNORECASE,
)

# Signals that the user wants general AI chat, not workspace ops
_GENERAL_CHAT_SIGNALS = re.compile(
    r"\b(explain|what is|how does|write|generate|create a post|draft|suggest|give me ideas"
    r"|best practices|help me|how to|what are|why is|strategy|compare|summarize this"
    r"|translate|improve|edit|rewrite|make it|can you write|can you explain"
    r"|tell me about|what do you think|your opinion|recommend)\b",
    re.IGNORECASE,
)

# Signals that a real-time/live data answer is expected
_REALTIME_SIGNALS = re.compile(
    r"\b(latest|current|right now|live|today.?s price|trending now|breaking|just happened"
    r"|recent news|market today|crypto today|stock price|weather today)\b",
    re.IGNORECASE,
)


def _classify_query(message: str) -> str:
    """
    Classify message into one of: workspace | productivity | general | realtime
    Used to tune the AI prompt and context injection.
    """
    msg = message.lower()
    if _REALTIME_SIGNALS.search(msg):
        return "realtime"
    if _WORKSPACE_SIGNALS.search(msg):
        return "workspace"
    if _GENERAL_CHAT_SIGNALS.search(msg):
        return "general"
    return "productivity"


def _build_rich_context(message: str, ctx, query_type: str) -> str:
    """Build context string tuned to the query type."""
    if ctx is None:
        return "Workspace data unavailable."

    if query_type == "general":
        # For pure general questions, only inject minimal user identity
        return (
            f"User: {ctx.full_name} | Plan: {ctx.plan} | "
            f"Telegram groups connected: {len(ctx.groups)}\n"
            f"(This is a general question — workspace data not needed)"
        )

    if query_type == "realtime":
        return f"User: {ctx.full_name} | Plan: {ctx.plan} | Telegram groups connected: {len(ctx.groups)}"

    # workspace / productivity — full context
    lines = [ctx.to_prompt_text()]

    # Inject knowledge docs content (not just preview) for richer context
    if ctx.knowledge_docs:
        lines.append("\n--- Knowledge Base Content ---")
        for doc in ctx.knowledge_docs[:3]:
            if doc.get("content"):
                lines.append(f"[{doc['title']}]: {doc['content'][:300]}")

    return "\n".join(lines)


def _build_followup_suggestions(query_type: str, message: str, ctx) -> list[dict]:
    """Generate contextual follow-up action suggestions based on response type."""
    suggestions = []
    msg_lower = message.lower()

    # Content/writing requests → save it
    if re.search(r"\b(write|draft|generate|create a post|announcement)\b", msg_lower):
        suggestions.append({"label": "📝 Save as Note", "value": "Note this: (paste text above)"})
        suggestions.append({"label": "📢 Post to Group", "value": "Post announcement to my groups"})

    # Planning/analysis → create tasks
    elif re.search(r"\b(plan|strategy|steps|todo|action|implement|campaign)\b", msg_lower):
        suggestions.append({"label": "✅ Create Task", "value": "Create task"})
        suggestions.append({"label": "🔍 Expand Analysis", "value": f"Expand analysis: {message[:60]}"})

    # Group/community questions → deeper analysis
    elif re.search(r"\b(group|community|member|engagement|growth|channel)\b", msg_lower):
        suggestions.append({"label": "📊 Group Health", "value": "Any issues in my groups?"})
        suggestions.append({"label": "🔍 Expand Analysis", "value": f"Expand analysis: {message[:60]}"})

    # Workspace state questions → navigate to data
    elif query_type == "workspace":
        suggestions.append({"label": "📅 Full Schedule", "value": "What's on my schedule?"})
        suggestions.append({"label": "🧠 Analyze My Day", "value": "Analyze my day"})

    # Always offer expand as last suggestion if not already there
    has_expand = any("Expand" in s["label"] for s in suggestions)
    if not has_expand and len(suggestions) < 3:
        suggestions.append({"label": "🔍 Expand Analysis", "value": f"Expand analysis: {message[:60]}"})

    # Remind/task options for productivity queries
    if query_type == "productivity" and len(suggestions) < 3:
        suggestions.append({"label": "⏰ Set Reminder", "value": "Remind me"})

    return suggestions[:3]


_GREETING_WORD = re.compile(
    r"^(hi|hey|hello|hiya|howdy|yo|sup|helo|hii|hiii|hy|hw|hye|hye)[!?.]*$",
    re.IGNORECASE,
)
_GREETING_PATTERNS = re.compile(
    r"^\s*(hi|hey|hello|hiya|howdy|yo|sup|helo|hii|hiii|hy|hw|hye"
    r"|how are you|how r you|how are u|how was your|hows it going"
    r"|good morning|good afternoon|good evening|good night"
    r"|what'?s up|wazzup|wsp|hru|how u doing"
    # combined forms: "hy how are you", "hey how are you", "hi how are u"
    r"|(hi|hey|hello|hiya|hy|hw)\s+(how are you|how r you|how are u|hru|how u doing|how.?s it going)"
    r")\s*[?!.]*\s*$",
    re.IGNORECASE,
)


def handle_general(user_id: int, message: str, key_info: dict, ai_reply: str | None, ctx=None) -> dict:
    """
    Hybrid AI handler — routes between workspace assistant and general AI chat.
    Falls back gracefully when no AI key is configured.
    """
    # Handle greetings naturally even without an AI key
    if _GREETING_PATTERNS.match(message):
        msg_lower = message.lower().strip()
        if any(w in msg_lower for w in ("how are you", "how r you", "how are u", "how was your", "hru", "how u")):
            reply = "I'm doing great, thanks for asking! 😊 Ready to help you manage your Telegram workspace. What can I do for you today?"
        else:
            reply = "Hey! 👋 I'm your Telegizer AI assistant. Ask me anything — schedule meetings, set reminders, check your groups, or just chat. What's on your mind?"
        return {"reply": reply, "intent": "general", "data": None, "suggestions": []}

    if not key_info.get("api_key"):
        return _no_key_response()

    query_type = _classify_query(message)

    # Only use the INTENT_SYSTEM's pre-parsed reply for workspace action confirmations
    # (very short workspace replies like "Reminder set!"). For general/factual questions
    # always call Gemini directly so it gives a real answer, not a canned response.
    _is_canned = (
        ai_reply and
        query_type in ("workspace",) and
        len(ai_reply.strip()) < 80 and
        not any(w in (ai_reply or "").lower() for w in ("i'm here", "i can help", "ask me", "ready to help"))
    )
    if _is_canned:
        suggestions = _build_followup_suggestions(query_type, message, ctx)
        return {"reply": ai_reply, "intent": "general", "data": None, "suggestions": suggestions}
    context = _build_rich_context(message, ctx, query_type)

    # Build conversation history for multi-turn coherence
    history_block = ""
    if ctx and ctx.recent_conversation:
        recent = ctx.recent_conversation[-6:]
        history_lines = []
        for turn in recent:
            role = "User" if turn["direction"] == "in" else "Assistant"
            history_lines.append(f"{role}: {turn['content'][:150]}")
        if history_lines:
            history_block = "\n\n[Recent conversation]\n" + "\n".join(history_lines)

    prompt = (
        f"[Workspace context]\n{context}"
        f"{history_block}\n\n"
        f"[User message]\n{message}\n\n"
        "Respond as Telegizer Assistant. Be helpful, specific, and action-oriented."
    )

    try:
        reply = call_ai_text(key_info, HYBRID_AI_SYSTEM, prompt)
        suggestions = _generate_proactive_suggestions(key_info, message, reply) or _build_followup_suggestions(query_type, message, ctx)
        return {"reply": reply, "intent": "general", "data": None, "suggestions": suggestions}
    except Exception as exc:
        _log.warning("hybrid AI failed: %s", exc)
        return _fallback_response(message)


def handle_expand_analysis(user_id: int, message: str, key_info: dict, ctx=None) -> dict:
    """
    Deep-dive expansion of a previous topic or query.
    Triggered by "Expand analysis: <topic>" or explicit expand request.
    """
    if not key_info.get("api_key"):
        return {
            "reply": "Deep analysis requires an AI key. Add one in AI Settings.",
            "intent": "expand_analysis",
            "data": None,
            "suggestions": [],
        }

    # Extract the topic from "Expand analysis: <topic>"
    topic_match = re.match(r"expand\s+analysis\s*[:\-]?\s*(.+)", message, re.IGNORECASE)
    topic = topic_match.group(1).strip() if topic_match else message

    context = ctx.to_prompt_text() if ctx else "Workspace data unavailable."

    prompt = (
        f"[Workspace context]\n{context}\n\n"
        f"[Topic to expand]\n{topic}\n\n"
        "Provide a comprehensive deep-dive analysis on this topic. "
        "Reference the user's actual workspace data where relevant."
    )

    try:
        reply = call_ai_text(key_info, EXPAND_ANALYSIS_SYSTEM, prompt)
        return {
            "reply": reply,
            "intent": "expand_analysis",
            "data": {"topic": topic},
            "suggestions": [
                {"label": "✅ Create Task from This", "value": "Create task"},
                {"label": "📝 Save as Note", "value": "Note this: (key points from above)"},
                {"label": "⏰ Set Follow-up Reminder", "value": "Remind me to follow up on this tomorrow"},
            ],
        }
    except Exception as exc:
        _log.warning("expand_analysis AI failed: %s", exc)
        return {"reply": "Couldn't generate deep analysis right now.", "intent": "expand_analysis", "data": None, "suggestions": []}


def _no_key_response() -> dict:
    return {
        "reply": (
            "I can help with your workspace — schedule meetings, set reminders, manage tasks, and check your groups.\n\n"
            "For full AI chat responses, add an AI key in **Settings → AI Settings**.\n\n"
            "What would you like to do?"
        ),
        "intent": "general",
        "data": None,
        "suggestions": [
            {"label": "📅 My Schedule", "value": "What's on my schedule?"},
            {"label": "👥 Group Health", "value": "Any issues in my groups?"},
        ],
    }


def _fallback_response(message: str) -> dict:
    return {
        "reply": "I had a moment of trouble there — could you rephrase that? I'm here and ready to help.",
        "intent": "general",
        "data": None,
        "suggestions": [],
    }


def _generate_proactive_suggestions(key_info: dict, user_msg: str, ai_reply: str) -> list[dict]:
    """Use AI to generate contextual proactive suggestions based on the conversation."""
    if not key_info.get("api_key"):
        return []
    try:
        prompt = f"User: {user_msg[:200]}\nAssistant: {ai_reply[:400]}"
        raw = call_ai(key_info, PROACTIVE_SUGGEST_SYSTEM, prompt)
        suggestions = parse_json(raw)
        if isinstance(suggestions, list):
            return [s for s in suggestions if isinstance(s, dict) and s.get("label")][:3]
    except Exception:
        pass
    return []


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
