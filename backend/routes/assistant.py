"""
Assistant Hub API — aggregated summary for the Hub dashboard + Live Chat DMs.

GET  /api/assistant/hub-summary
GET  /api/assistant/dm-messages?last_id=X
POST /api/assistant/send-dm
POST /api/assistant/ask                     cross-group intelligence query
GET  /api/assistant/autoreply-logs          auto-reply execution history
"""
from datetime import datetime, timedelta
import logging

from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import (
    db, User, TelegramGroup, WorkspaceReminder, Note, DigestLog,
    AutomationExecution, AutomationWorkflow, BotDMMessage,
    AutoReplyLog, MessageBuffer, GroupMeetingLink,
)
from ..middleware.rate_limit import rate_limit
from ..config import Config
from flask import Blueprint

_log = logging.getLogger(__name__)

assistant_bp = Blueprint("assistant", __name__, url_prefix="/api/assistant")


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


@assistant_bp.route("/briefing", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def briefing():
    """
    Return a pre-built daily briefing for the persistent assistant sidebar.
    Cached per user per session — built from AssistantContextService.
    """
    user = _current_user()
    try:
        from ..assistant.context_service import AssistantContextService
        ctx = AssistantContextService.build(user.id)
    except Exception as exc:
        _log.warning("briefing context build failed: %s", exc)
        return jsonify({"briefing": None, "suggestions": []})

    now = datetime.utcnow()
    hour = now.hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    name = user.full_name.split()[0] if user.full_name else "there"

    lines = [f"{greeting}, {name}! Here's your day:"]
    lines.append("")

    if ctx.upcoming_meetings:
        today_meetings = [
            m for m in ctx.upcoming_meetings
            if m["scheduled_at_human"].startswith(now.strftime("%a %d %b"))
        ]
        if today_meetings:
            lines.append(f"📅 Meetings today: {', '.join(m['title'] for m in today_meetings[:3])}")
        else:
            next_m = ctx.upcoming_meetings[0]
            lines.append(f"📅 Next meeting: {next_m['title']} — {next_m['scheduled_at_human']}")
    else:
        lines.append("📅 No meetings scheduled")

    if ctx.upcoming_reminders:
        lines.append(f"🔔 {len(ctx.upcoming_reminders)} reminder(s) coming up")

    if ctx.pending_tasks:
        lines.append(f"✅ {len(ctx.pending_tasks)} pending task(s)")

    if ctx.group_alerts:
        for alert in ctx.group_alerts[:2]:
            lines.append(f"⚠️ {alert['group_title']}: {alert['health_status']}")
    elif ctx.groups:
        active = sum(1 for g in ctx.groups if g.get("is_active"))
        lines.append(f"👥 {len(ctx.groups)} group(s) connected, {active} active")

    if ctx.platform_today.get("messages_received", 0) > 0:
        lines.append(
            f"💬 {ctx.platform_today['messages_received']} messages today"
            + (f", {ctx.platform_today['automations_fired']} automations fired"
               if ctx.platform_today.get("automations_fired") else "")
        )

    lines.append("")
    lines.append("How can I help you today?")

    suggestions = [
        {"label": "What's on my schedule?", "value": "What's on my schedule today?"},
        {"label": "Any group issues?", "value": "Any issues in my groups?"},
    ]
    if not ctx.upcoming_meetings:
        suggestions.append({"label": "Book a meeting", "value": "Book a meeting"})
    if not ctx.upcoming_reminders:
        suggestions.append({"label": "Set a reminder", "value": "Remind me"})

    return jsonify({
        "briefing": "\n".join(lines),
        "suggestions": suggestions,
    })


@assistant_bp.route("/hub-summary", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def hub_summary():
    user = _current_user()
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    # ── Connected groups ──────────────────────────────────────────────────────
    groups = TelegramGroup.query.filter_by(
        owner_user_id=user.id, is_disabled=False
    ).all()
    active_groups = [g for g in groups if g.bot_status == "active"]

    # ── Reminders due today (delivered or not) ────────────────────────────────
    reminders_today = (
        WorkspaceReminder.query
        .filter(
            WorkspaceReminder.owner_user_id == user.id,
            WorkspaceReminder.remind_at >= today_start,
            WorkspaceReminder.remind_at < tomorrow_start,
        )
        .order_by(WorkspaceReminder.remind_at.asc())
        .limit(5)
        .all()
    )
    # Also include overdue undelivered reminders
    overdue = (
        WorkspaceReminder.query
        .filter(
            WorkspaceReminder.owner_user_id == user.id,
            WorkspaceReminder.remind_at < today_start,
            WorkspaceReminder.is_delivered == False,  # noqa: E712
        )
        .order_by(WorkspaceReminder.remind_at.desc())
        .limit(3)
        .all()
    )
    all_reminders = overdue + reminders_today

    # ── Recent notes ──────────────────────────────────────────────────────────
    recent_notes = (
        Note.query
        .filter_by(user_id=user.id)
        .order_by(Note.created_at.desc())
        .limit(3)
        .all()
    )

    # ── Digest status per group ───────────────────────────────────────────────
    digest_status = []
    for g in groups:
        last_log = (
            DigestLog.query
            .filter_by(group_id=g.telegram_group_id)
            .order_by(DigestLog.sent_at.desc())
            .first()
        )
        digest_cfg = (g.settings or {}).get("digest", {})
        enabled = digest_cfg.get("enabled", digest_cfg.get("daily", False))

        if last_log and last_log.sent_at >= today_start:
            status = "sent"
        elif enabled:
            status = "pending"
        else:
            status = "disabled"

        digest_status.append({
            "group_id": g.telegram_group_id,
            "group_title": g.title,
            "bot_status": g.bot_status,
            "last_sent": last_log.sent_at.isoformat() if last_log else None,
            "status": status,
        })

    # ── Automation activity today ─────────────────────────────────────────────
    workflows_today = (
        db.session.query(AutomationExecution)
        .join(AutomationWorkflow, AutomationExecution.workflow_id == AutomationWorkflow.id)
        .filter(
            AutomationWorkflow.owner_user_id == user.id,
            AutomationExecution.executed_at >= today_start,
        )
        .count()
    )

    return jsonify({
        "bot_connected": bool(user.telegram_user_id),
        "telegram_username": user.telegram_username,
        "connected_groups": len(groups),
        "active_groups": len(active_groups),
        "bot_username": Config.ECHO_BOT_USERNAME or Config.TELEGRAM_BOT_USERNAME,
        "reminders_today": [r.to_dict() for r in all_reminders],
        "recent_notes": [n.to_dict() for n in recent_notes],
        "digest_status": digest_status,
        "automation_activity": {
            "auto_replies_today": AutoReplyLog.query.filter(
                AutoReplyLog.user_id == user.id,
                AutoReplyLog.triggered_at >= today_start,
            ).count(),
            "workflows_today": workflows_today,
        },
        "onboarding": {
            "has_active_group": len(active_groups) > 0,
            "has_auto_reply": AutoReplyLog.query.filter_by(user_id=user.id).count() > 0,
            "has_digest": any(
                (g.settings or {}).get("digest", {}).get("enabled") for g in groups
            ),
            "has_note": Note.query.filter_by(user_id=user.id).count() > 0,
        },
    })


@assistant_bp.route("/dm-messages", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def dm_messages():
    """Return BotDMMessages newer than last_id (0 = last 50)."""
    user = _current_user()
    last_id = int(request.args.get("last_id", 0))
    q = BotDMMessage.query.filter_by(user_id=user.id)
    if last_id:
        q = q.filter(BotDMMessage.id > last_id)
    msgs = q.order_by(BotDMMessage.id.asc()).limit(50).all()
    return jsonify({"messages": [m.to_dict() for m in msgs]})


@assistant_bp.route("/send-dm", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def send_dm():
    """Send a message from the web UI to the user's Telegram DM."""
    user = _current_user()
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()[:4000]
    if not text:
        return jsonify({"error": "text required"}), 400
    if not user.telegram_user_id:
        return jsonify({"error": "Telegram not connected"}), 400

    flask_app = request.environ.get("flask_app")  # set by app factory, optional
    from ..telegram_safe import safe_send_message
    bot_token = Config.TELEGRAM_BOT_TOKEN
    if not safe_send_message(bot_token, user.telegram_user_id, text):
        _log.warning("send_dm telegram error for user=%s", user.id)
        return jsonify({"error": "Failed to send message"}), 502

    # Log outbound DM
    msg = BotDMMessage(user_id=user.id, direction="out", content=text, intent="web")
    db.session.add(msg)
    db.session.commit()
    return jsonify({"message": msg.to_dict()}), 201


@assistant_bp.route("/ask", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def ask_groups():
    """Cross-group intelligence: answer a question using all connected groups' message buffers."""
    user = _current_user()
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()[:500]
    if not question:
        return jsonify({"error": "question required"}), 400

    # Gather recent messages across all user's groups
    groups = TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()
    if not groups:
        return jsonify({"error": "No groups connected"}), 400

    cutoff = datetime.utcnow() - timedelta(hours=72)
    group_ids = [g.telegram_group_id for g in groups]
    msgs = (
        MessageBuffer.query
        .filter(MessageBuffer.telegram_group_id.in_(group_ids))
        .filter(MessageBuffer.created_at >= cutoff)
        .order_by(MessageBuffer.created_at.desc())
        .limit(300)
        .all()
    )
    if not msgs:
        return jsonify({"error": "No recent messages found in your groups"}), 400

    # Build context with group labels
    group_title_map = {g.telegram_group_id: g.title for g in groups}
    context_lines = []
    for m in reversed(msgs):
        grp = group_title_map.get(m.telegram_group_id, m.telegram_group_id)
        context_lines.append(f"[{grp}] {m.sender_name or 'User'}: {m.content}")
    context = "\n".join(context_lines)[:14000]

    from ..assistant.ai_key_resolver import get_workspace_ai_key, record_token_usage
    key_info = get_workspace_ai_key(user)
    if not key_info.get("api_key"):
        return jsonify({"error": "No AI key configured — set one in AI Settings"}), 400

    prompt = (
        "You are an AI assistant that answers questions about a user's Telegram group conversations.\n"
        "Use only the provided conversation context to answer. If the answer is not in the context, say so.\n\n"
        f"Context (last 72h from {len(groups)} group(s)):\n{context}\n\n"
        f"Question: {question}\n\nAnswer:"
    )

    try:
        answer = _call_ai_text(key_info, prompt)
        if key_info.get("source") == "platform":
            record_token_usage(user, (len(prompt) + len(answer)) // 4)
    except Exception as exc:
        _log.warning("Cross-group ask failed: %s", exc)
        return jsonify({"error": "AI request failed"}), 502

    return jsonify({
        "answer": answer,
        "groups_searched": len(groups),
        "messages_scanned": len(msgs),
    })


@assistant_bp.route("/chat", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def chat():
    """
    Unified assistant chat endpoint for the web LiveChat.
    Processes natural language messages and returns a reply + optional structured data.
    """
    user = _current_user()
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()[:1000]
    if not message:
        return jsonify({"error": "message required"}), 400

    user_tz = body.get("timezone") or None

    # Store inbound message — gracefully skip if schema migration is pending
    inbound_id = None
    try:
        inbound = BotDMMessage(user_id=user.id, direction="in", content=message, intent="web_chat")
        db.session.add(inbound)
        db.session.commit()
        inbound_id = inbound.id
    except Exception as _e:
        _log.warning("BotDMMessage inbound insert failed (schema migration pending?): %s", _e)
        db.session.rollback()

    from ..assistant.personal_assistant import process_message
    result = process_message(user_id=user.id, message=message, user_tz=user_tz)

    # Store assistant reply
    reply_msg_id = None
    try:
        reply_msg = BotDMMessage(user_id=user.id, direction="out", content=result["reply"], intent=result["intent"])
        db.session.add(reply_msg)
        db.session.commit()
        reply_msg_id = reply_msg.id
    except Exception as _e:
        _log.warning("BotDMMessage outbound insert failed (schema migration pending?): %s", _e)
        db.session.rollback()

    return jsonify({
        "reply": result["reply"],
        "intent": result["intent"],
        "data": result.get("data"),
        "suggestions": result.get("suggestions", []),
        "message_id": reply_msg_id,
    })


@assistant_bp.route("/autoreply-logs", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def autoreply_logs():
    """Return recent auto-reply execution logs for the user."""
    user = _current_user()
    logs = (
        AutoReplyLog.query
        .filter_by(user_id=user.id)
        .order_by(AutoReplyLog.triggered_at.desc())
        .limit(100)
        .all()
    )
    return jsonify({"logs": [l.to_dict() for l in logs]})


@assistant_bp.route("/meeting-links", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def meeting_links():
    """GET /api/assistant/meeting-links — recent meeting links captured in user's groups."""
    user = _current_user()
    group_id = request.args.get("group_id")
    dismissed = request.args.get("dismissed", "false").lower() == "true"

    q = GroupMeetingLink.query.filter_by(owner_user_id=user.id, is_dismissed=dismissed)
    if group_id:
        q = q.filter_by(telegram_group_id=group_id)
    links = q.order_by(GroupMeetingLink.captured_at.desc()).limit(100).all()
    return jsonify({"links": [l.to_dict() for l in links]})


@assistant_bp.route("/meeting-links/<int:link_id>/dismiss", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def dismiss_meeting_link(link_id):
    """Mark a captured meeting link as dismissed."""
    user = _current_user()
    link = GroupMeetingLink.query.filter_by(id=link_id, owner_user_id=user.id).first_or_404()
    link.is_dismissed = True
    db.session.commit()
    return jsonify({"ok": True})


@assistant_bp.route("/group-trends", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def group_trends():
    """
    GET /api/assistant/group-trends?days=7&group_id=<telegram_group_id>
    Returns daily GroupDailySignal history for chart rendering.
    """
    from ..models import GroupDailySignal
    from datetime import date, timedelta

    user = _current_user()
    days = min(int(request.args.get("days", 7)), 90)
    group_id = request.args.get("group_id")

    groups = TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()
    group_ids = [g.telegram_group_id for g in groups]
    if not group_ids:
        return jsonify({"trends": [], "groups": []})

    if group_id and group_id in group_ids:
        group_ids = [group_id]

    cutoff = date.today() - timedelta(days=days - 1)
    signals = (
        GroupDailySignal.query
        .filter(GroupDailySignal.telegram_group_id.in_(group_ids))
        .filter(GroupDailySignal.date >= cutoff)
        .order_by(GroupDailySignal.telegram_group_id, GroupDailySignal.date)
        .all()
    )

    group_title_map = {g.telegram_group_id: (g.title or g.telegram_group_id) for g in groups}
    trends_by_group: dict = {}
    for sig in signals:
        gid = sig.telegram_group_id
        if gid not in trends_by_group:
            trends_by_group[gid] = {"group_id": gid, "title": group_title_map.get(gid, gid), "days": []}
        trends_by_group[gid]["days"].append({
            "date": sig.date.isoformat(),
            "message_count": sig.message_count,
            "active_members": sig.active_members,
            "spam_score": float(sig.spam_score or 0),
            "conflict_score": float(sig.conflict_score or 0),
            "questions_unanswered": sig.questions_unanswered,
            "sentiment": sig.sentiment,
            "health_status": sig.health_status,
            "ai_summary": sig.ai_summary,
        })

    return jsonify({
        "trends": list(trends_by_group.values()),
        "groups": [{"id": g.telegram_group_id, "title": g.title or g.telegram_group_id} for g in groups],
        "days_requested": days,
    })


@assistant_bp.route("/inline-ai", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def inline_ai():
    """
    POST /api/assistant/inline-ai
    Body: { "action": "summarize"|"suggest_automod"|"write_announcement"|"explain", "context": "..." }
    Returns { "result": "..." }
    """
    user = _current_user()
    body = request.get_json(silent=True) or {}
    action = body.get("action", "summarize")
    context = (body.get("context") or "")[:8000]

    if not context.strip():
        return jsonify({"error": "context is required"}), 400

    prompts = {
        "summarize": (
            f"Summarize the following Telegram group messages in 3-5 bullet points. "
            f"Focus on key topics, decisions, and action items.\n\nMessages:\n{context}"
        ),
        "suggest_automod": (
            f"Based on these Telegram group messages, suggest 3 specific automod rules "
            f"(keyword triggers + auto-reply text) that would improve moderation. "
            f"Format each as: Trigger: <keyword> → Reply: <response text>\n\nMessages:\n{context}"
        ),
        "write_announcement": (
            f"Write a professional, friendly Telegram group announcement based on this context. "
            f"Keep it under 200 words, use emojis sparingly.\n\nContext:\n{context}"
        ),
        "explain": (
            f"Explain the following in simple terms for a non-technical Telegram group admin:\n\n{context}"
        ),
        "improve_message": (
            f"Rewrite the following message to be clearer, more professional, and engaging "
            f"for a Telegram audience. Provide 2 alternatives.\n\nOriginal:\n{context}"
        ),
    }

    prompt = prompts.get(action, prompts["summarize"])

    try:
        from ..assistant.ai_key_resolver import get_workspace_ai_key, QuotaExceededError, record_token_usage
        key_info = get_workspace_ai_key(user)
        result = _call_ai_text(key_info, prompt)
        if key_info.get("source") == "platform":
            record_token_usage(user, (len(prompt) + len(result)) // 4)
        return jsonify({"result": result, "action": action})
    except Exception as exc:
        _log.warning("inline_ai action=%s failed: %s", action, exc)
        return jsonify({"error": str(exc)}), 503


@assistant_bp.route("/search", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def universal_search():
    """
    GET /api/assistant/search?q=<query>&types=meetings,reminders,notes,tasks,groups
    Natural language search across all workspace entities.
    """
    from ..models import Meeting, WorkspaceReminder, Note, Task as WorkspaceTask
    from datetime import datetime

    user = _current_user()
    q = (request.args.get("q") or "").strip()
    types_param = request.args.get("types", "meetings,reminders,notes,tasks,groups")
    types = set(types_param.split(","))

    if not q:
        return jsonify({"error": "q is required"}), 400

    results = []
    q_lower = q.lower()

    if "meetings" in types:
        meetings = Meeting.query.filter_by(owner_user_id=user.id).order_by(Meeting.scheduled_at.desc()).limit(200).all()
        for m in meetings:
            score = 0
            text = f"{m.title or ''} {m.notes or ''} {' '.join(m.participants or [])}".lower()
            for word in q_lower.split():
                if word in text:
                    score += 1
            if score:
                d = m.to_dict()
                d["_type"] = "meeting"
                d["_score"] = score
                d["_label"] = m.title or "Untitled meeting"
                d["_date"] = m.scheduled_at.isoformat() if m.scheduled_at else None
                results.append(d)

    if "reminders" in types:
        reminders = WorkspaceReminder.query.filter_by(user_id=user.id).order_by(WorkspaceReminder.remind_at.desc()).limit(200).all()
        for r in reminders:
            score = sum(1 for word in q_lower.split() if word in (r.reminder_text or "").lower())
            if score:
                d = r.to_dict()
                d["_type"] = "reminder"
                d["_score"] = score
                d["_label"] = r.reminder_text or "Reminder"
                d["_date"] = r.remind_at.isoformat() if r.remind_at else None
                results.append(d)

    if "notes" in types:
        notes = Note.query.filter_by(user_id=user.id).order_by(Note.created_at.desc()).limit(200).all()
        for n in notes:
            text = f"{n.title or ''} {n.content or ''}".lower()
            score = sum(1 for word in q_lower.split() if word in text)
            if score:
                d = n.to_dict()
                d["_type"] = "note"
                d["_score"] = score
                d["_label"] = n.title or (n.content or "")[:60]
                d["_date"] = n.created_at.isoformat() if n.created_at else None
                results.append(d)

    if "tasks" in types:
        try:
            tasks = WorkspaceTask.query.filter_by(user_id=user.id).order_by(WorkspaceTask.created_at.desc()).limit(200).all()
            for t in tasks:
                text = f"{t.title or ''} {t.description or ''}".lower()
                score = sum(1 for word in q_lower.split() if word in text)
                if score:
                    d = t.to_dict()
                    d["_type"] = "task"
                    d["_score"] = score
                    d["_label"] = t.title or "Task"
                    d["_date"] = t.created_at.isoformat() if t.created_at else None
                    results.append(d)
        except Exception:
            pass

    if "groups" in types:
        from ..models import GroupDailySignal
        from datetime import date, timedelta
        groups = TelegramGroup.query.filter_by(owner_user_id=user.id, is_disabled=False).all()
        cutoff = date.today() - timedelta(days=7)
        for g in groups:
            text = f"{g.title or ''} {g.description or ''}".lower()
            score = sum(1 for word in q_lower.split() if word in text)
            if score:
                sig = GroupDailySignal.query.filter(
                    GroupDailySignal.telegram_group_id == g.telegram_group_id,
                    GroupDailySignal.date >= cutoff,
                ).order_by(GroupDailySignal.date.desc()).first()
                results.append({
                    "_type": "group",
                    "_score": score,
                    "_label": g.title or g.telegram_group_id,
                    "_date": None,
                    "id": g.telegram_group_id,
                    "title": g.title,
                    "health_status": sig.health_status if sig else "unknown",
                    "spam_score": float(sig.spam_score or 0) if sig else 0,
                })

    results.sort(key=lambda x: x["_score"], reverse=True)
    return jsonify({"results": results[:30], "query": q, "total": len(results)})


@assistant_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    """Return the user's learned assistant preferences."""
    from ..assistant.profile_service import get_preferences
    user = _current_user()
    return jsonify(get_preferences(user.id))


def _call_ai_text(key_info: dict, prompt: str) -> str:
    """AI helper for cross-group ask and inline AI. Uses OpenRouter (OpenAI-compatible)."""
    import requests as _r
    provider = key_info.get("provider", "openrouter")
    api_key = key_info["api_key"]
    model = key_info.get("model", "openai/gpt-4o-mini")

    if provider == "gemini":
        resp = _r.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    if provider == "anthropic":
        resp = _r.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={"model": model or "claude-haiku-4-5-20251001", "max_tokens": 1024,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()

    # openrouter / openai-compatible
    base = key_info.get("base_url", "https://openrouter.ai/api/v1")
    resp = _r.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
