"""
Tasks API — CRUD for user tasks (manual, AI-extracted, or bot-captured).

GET    /api/tasks                  list (filter: status, priority, group_id)
POST   /api/tasks                  create
PUT    /api/tasks/<id>             update
DELETE /api/tasks/<id>             delete
POST   /api/tasks/extract/<group_id>  AI-extract tasks from group message buffer
"""
from datetime import datetime
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, Task, TelegramGroup, MessageBuffer
from ..middleware.rate_limit import rate_limit

_log = logging.getLogger(__name__)

tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


def _me() -> User:
    return User.query.get(int(get_jwt_identity()))


@tasks_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_tasks():
    user = _me()
    q = Task.query.filter_by(user_id=user.id)
    status = request.args.get("status")
    priority = request.args.get("priority")
    group_id = request.args.get("group_id")
    if status:
        q = q.filter_by(status=status)
    if priority:
        q = q.filter_by(priority=priority)
    if group_id:
        q = q.filter_by(group_id=group_id)
    tasks = q.order_by(Task.created_at.desc()).limit(200).all()
    return jsonify({"tasks": [t.to_dict() for t in tasks]})


@tasks_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def create_task():
    user = _me()
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()[:500]
    if not title:
        return jsonify({"error": "title required"}), 400
    due_at = None
    if body.get("due_at"):
        try:
            due_at = datetime.fromisoformat(body["due_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, AttributeError):
            pass
    t = Task(
        user_id=user.id,
        title=title,
        description=(body.get("description") or "")[:5000] or None,
        status=body.get("status", "todo"),
        priority=body.get("priority", "medium"),
        source=body.get("source", "manual"),
        due_at=due_at,
        group_id=body.get("group_id"),
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({"task": t.to_dict()}), 201


@tasks_bp.route("/<int:task_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def update_task(task_id):
    user = _me()
    t = Task.query.filter_by(id=task_id, user_id=user.id).first_or_404()
    body = request.get_json(silent=True) or {}
    for field in ("title", "description", "status", "priority", "group_id"):
        if field in body:
            val = body[field]
            if isinstance(val, str):
                val = val.strip() or None if field == "description" else val.strip()
            setattr(t, field, val)
    if "due_at" in body:
        if body["due_at"]:
            try:
                t.due_at = datetime.fromisoformat(body["due_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, AttributeError):
                pass
        else:
            t.due_at = None
    t.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"task": t.to_dict()})


@tasks_bp.route("/<int:task_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def delete_task(task_id):
    user = _me()
    t = Task.query.filter_by(id=task_id, user_id=user.id).first_or_404()
    db.session.delete(t)
    db.session.commit()
    return jsonify({"success": True})


@tasks_bp.route("/extract/<group_id>", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def extract_tasks(group_id):
    """Use workspace AI key to extract tasks from recent group messages."""
    user = _me()
    # Verify the group belongs to the user
    from ..models import TelegramGroup
    group = TelegramGroup.query.filter_by(
        telegram_group_id=str(group_id), owner_user_id=user.id
    ).first()
    if not group:
        return jsonify({"error": "Group not found"}), 404

    # Grab last 48h of messages
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=48)
    msgs = (
        MessageBuffer.query
        .filter_by(telegram_group_id=str(group_id))
        .filter(MessageBuffer.created_at >= cutoff)
        .order_by(MessageBuffer.created_at.asc())
        .limit(200)
        .all()
    )
    if not msgs:
        return jsonify({"error": "No recent messages to analyze"}), 400

    text_blob = "\n".join(
        f"[{m.sender_name or 'User'}]: {m.content}" for m in msgs if m.content
    )[:12000]

    from ..assistant.ai_key_resolver import get_workspace_ai_key
    key_info = get_workspace_ai_key(user)
    if not key_info.get("api_key"):
        return jsonify({"error": "No AI key configured"}), 400

    prompt = (
        "Extract all action items and tasks from this conversation. "
        "Return a JSON array of objects with keys: title (string, max 100 chars), "
        "priority (low|medium|high). Only return the JSON array, nothing else.\n\n"
        + text_blob
    )

    try:
        items = _call_ai(key_info, prompt)
    except Exception as exc:
        _log.warning("Task extraction failed: %s", exc)
        return jsonify({"error": "AI extraction failed"}), 502

    created = []
    for item in items[:20]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        t = Task(
            user_id=user.id,
            title=str(item["title"])[:500],
            priority=item.get("priority", "medium") if item.get("priority") in ("low", "medium", "high") else "medium",
            source="ai",
            group_id=str(group_id),
        )
        db.session.add(t)
        created.append(t)

    db.session.commit()
    return jsonify({"created": len(created), "tasks": [t.to_dict() for t in created]}), 201


def _call_ai(key_info, prompt):
    import json, requests as _r
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
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    elif provider == "anthropic":
        resp = _r.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={"model": model or "claude-haiku-4-5-20251001", "max_tokens": 1024,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"].strip()
    else:
        base = key_info.get("base_url", "https://api.openai.com/v1")
        resp = _r.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model or "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(raw)
