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
    AutoReplyLog, MessageBuffer,
)
from ..middleware.rate_limit import rate_limit
from ..config import Config
from flask import Blueprint

_log = logging.getLogger(__name__)

assistant_bp = Blueprint("assistant", __name__, url_prefix="/api/assistant")


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


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
        "bot_username": Config.TELEGRAM_BOT_USERNAME,
        "reminders_today": [r.to_dict() for r in all_reminders],
        "recent_notes": [n.to_dict() for n in recent_notes],
        "digest_status": digest_status,
        "automation_activity": {
            "auto_replies_today": 0,   # AutoReplyLog is Phase 2
            "workflows_today": workflows_today,
        },
        "onboarding": {
            "has_active_group": len(active_groups) > 0,
            "has_auto_reply": False,   # resolved client-side for simplicity
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
    try:
        # Send via bot using requests (sync-friendly)
        import requests as _r
        bot_token = Config.TELEGRAM_BOT_TOKEN
        resp = _r.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": user.telegram_user_id, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        _log.warning("send_dm telegram error: %s", exc)
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

    from ..assistant.ai_key_resolver import get_workspace_ai_key
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

    # Store inbound message
    inbound = BotDMMessage(user_id=user.id, direction="in", content=message, intent="web_chat")
    db.session.add(inbound)
    db.session.commit()

    from ..assistant.personal_assistant import process_message
    result = process_message(user_id=user.id, message=message, user_tz=user_tz)

    # Store assistant reply
    reply_msg = BotDMMessage(user_id=user.id, direction="out", content=result["reply"], intent=result["intent"])
    db.session.add(reply_msg)
    db.session.commit()

    return jsonify({
        "reply": result["reply"],
        "intent": result["intent"],
        "data": result.get("data"),
        "message_id": reply_msg.id,
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


def _call_ai_text(key_info: dict, prompt: str) -> str:
    import requests as _r
    provider = key_info.get("provider", "gemini")
    api_key = key_info["api_key"]
    model = key_info.get("model", "gemini-2.0-flash")
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
    base = key_info.get("base_url", "https://api.openai.com/v1")
    resp = _r.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model or "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
