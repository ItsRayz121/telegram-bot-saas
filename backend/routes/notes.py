"""
Notes API — workspace-level note capture and AI extraction.

GET    /api/notes                      — list notes (filter: group_id, source, tag)
POST   /api/notes                      — create manual note
PUT    /api/notes/<id>                 — update note
DELETE /api/notes/<id>                 — delete note
POST   /api/notes/generate/<group_id>  — AI-generate structured notes from group messages
"""
from datetime import datetime, timedelta
import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, Note, MessageBuffer, TelegramGroup
from ..middleware.rate_limit import rate_limit

_log = logging.getLogger(__name__)

notes_bp = Blueprint("notes", __name__, url_prefix="/api/notes")

_VALID_SOURCES = {"manual", "ai", "bot"}
_VALID_TAGS = {"decision", "task", "link", "question"}


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


# ── List ──────────────────────────────────────────────────────────────────────

@notes_bp.route("", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=60)
def list_notes():
    user = _current_user()
    q = Note.query.filter_by(user_id=user.id)

    group_id = request.args.get("group_id")
    if group_id:
        q = q.filter_by(group_id=group_id)

    source = request.args.get("source")
    if source in _VALID_SOURCES:
        q = q.filter_by(source=source)

    tag = request.args.get("tag")
    if tag in _VALID_TAGS:
        q = q.filter(Note.tags.contains([tag]))

    since = request.args.get("since")
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            q = q.filter(Note.created_at >= since_dt)
        except ValueError:
            pass

    notes = q.order_by(Note.created_at.desc()).limit(200).all()
    return jsonify({"notes": [n.to_dict() for n in notes]})


# ── Create ────────────────────────────────────────────────────────────────────

@notes_bp.route("", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def create_note():
    user = _current_user()
    data = request.get_json() or {}

    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400

    tags = [t for t in (data.get("tags") or []) if t in _VALID_TAGS]

    note = Note(
        user_id=user.id,
        group_id=data.get("group_id") or None,
        group_title=data.get("group_title") or None,
        content=content[:10000],
        source="manual",
        tags=tags,
    )
    db.session.add(note)
    db.session.commit()
    return jsonify({"note": note.to_dict()}), 201


# ── Update ────────────────────────────────────────────────────────────────────

@notes_bp.route("/<int:note_id>", methods=["PUT"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def update_note(note_id):
    user = _current_user()
    note = Note.query.get_or_404(note_id)
    if note.user_id != user.id:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    if "content" in data:
        note.content = (data["content"] or "").strip()[:10000]
    if "tags" in data:
        note.tags = [t for t in (data["tags"] or []) if t in _VALID_TAGS]
    if "group_id" in data:
        note.group_id = data["group_id"] or None
    if "group_title" in data:
        note.group_title = data["group_title"] or None

    db.session.commit()
    return jsonify({"note": note.to_dict()})


# ── Delete ────────────────────────────────────────────────────────────────────

@notes_bp.route("/<int:note_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(requests_per_minute=30)
def delete_note(note_id):
    user = _current_user()
    note = Note.query.get_or_404(note_id)
    if note.user_id != user.id:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(note)
    db.session.commit()
    return jsonify({"deleted": True})


# ── AI Generation ─────────────────────────────────────────────────────────────

_GENERATE_PROMPT = """\
You are a smart meeting assistant. Extract structured notes from these Telegram group messages.
Return JSON only, no explanation or markdown fences:
{
  "decisions": ["..."],
  "tasks": ["person: action by date"],
  "links": ["url — description"],
  "questions": ["unanswered question..."]
}
If a category is empty return an empty array. Be concise. Max 5 items per category.
Messages:
"""


def _call_ai_generate(key_info: dict, messages_text: str) -> dict | None:
    import urllib.request
    import json as _json

    provider = key_info["provider"]
    api_key = key_info["api_key"]
    model = key_info.get("model") or ""
    base_url = key_info.get("base_url")
    prompt = _GENERATE_PROMPT + messages_text

    try:
        if provider == "gemini":
            model_id = model or "gemini-2.0-flash"
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_id}:generateContent?key={api_key}"
            )
            payload = _json.dumps(
                {"contents": [{"parts": [{"text": prompt}]}]}
            ).encode()
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = _json.loads(resp.read())
            text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()

        elif provider == "anthropic":
            payload = _json.dumps({
                "model": model or "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = _json.loads(resp.read())
            text = raw["content"][0]["text"].strip()

        else:
            # openai | openrouter | custom
            base = (base_url or "https://api.openai.com/v1").rstrip("/")
            payload = _json.dumps({
                "model": model or "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1024,
                "temperature": 0.2,
            }).encode()
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = _json.loads(resp.read())
            text = raw["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if the model wrapped the JSON
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return _json.loads(text)

    except Exception as exc:
        _log.warning("AI note generation failed (provider=%s): %s", provider, exc)
        return None


_CATEGORY_TAG = {
    "decisions": "decision",
    "tasks": "task",
    "links": "link",
    "questions": "question",
}


@notes_bp.route("/generate/<group_id>", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=5)
def generate_notes(group_id):
    from ..assistant.ai_key_resolver import get_workspace_ai_key

    user = _current_user()

    tg = TelegramGroup.query.filter_by(
        telegram_group_id=group_id,
        owner_user_id=user.id,
        is_disabled=False,
    ).first()
    if not tg:
        return jsonify({"error": "Group not found"}), 404

    key_info = get_workspace_ai_key(user)
    if not key_info.get("api_key"):
        return jsonify({"error": "No AI key configured. Add one in AI Settings."}), 422

    cutoff = datetime.utcnow() - timedelta(hours=48)
    rows = (
        MessageBuffer.query
        .filter(
            MessageBuffer.telegram_group_id == group_id,
            MessageBuffer.created_at >= cutoff,
        )
        .order_by(MessageBuffer.created_at.asc())
        .limit(300)
        .all()
    )
    if not rows:
        return jsonify({"error": "No recent messages found for this group."}), 422

    messages_text = "\n".join(
        f"[{r.sender_name or 'User'}]: {r.message_text}" for r in rows
    )

    result = _call_ai_generate(key_info, messages_text)
    if not result:
        return jsonify({"error": "AI generation failed. Check your AI key in Settings."}), 500

    created = []
    for category, tag in _CATEGORY_TAG.items():
        for item in (result.get(category) or [])[:5]:
            if not item:
                continue
            note = Note(
                user_id=user.id,
                group_id=group_id,
                group_title=tg.title,
                content=str(item)[:2000],
                source="ai",
                tags=[tag],
            )
            db.session.add(note)
            created.append(note)

    db.session.commit()
    return jsonify({
        "notes": [n.to_dict() for n in created],
        "counts": {k: len(result.get(k) or []) for k in _CATEGORY_TAG},
    }), 201
