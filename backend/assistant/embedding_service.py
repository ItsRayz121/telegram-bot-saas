"""
embedding_service.py — text embedding generation and semantic similarity search.

Uses OpenAI text-embedding-3-small (1536-dim). Embeddings are stored as
JSON-encoded float lists in the `embedding` TEXT column on hub_notes and
hub_knowledge_cards tables, consistent with the existing knowledge-card pattern.
"""
from __future__ import annotations

import json
import logging
import math
import threading
from typing import Optional

_log = logging.getLogger(__name__)

_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIM = 1536


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if not mag_a or not mag_b:
        return 0.0
    return dot / (mag_a * mag_b)


def _get_openai_client(api_key: str):
    from openai import OpenAI
    return OpenAI(api_key=api_key)


def generate_embedding(text: str, api_key: str) -> Optional[list[float]]:
    """Return embedding vector or None on failure."""
    try:
        client = _get_openai_client(api_key)
        resp = client.embeddings.create(model=_EMBEDDING_MODEL, input=text[:8000])
        return resp.data[0].embedding
    except Exception as exc:
        _log.warning("embedding generation failed: %s", exc)
        return None


def _get_platform_openai_key() -> Optional[str]:
    """Return the platform OpenAI key if configured, else None."""
    try:
        from ..config import Config
        return getattr(Config, "OPENAI_API_KEY", None) or None
    except Exception:
        return None


def embed_note_background(note_id: str, content: str) -> None:
    """Trigger embedding generation in a background thread (fire-and-forget)."""
    api_key = _get_platform_openai_key()
    if not api_key:
        return

    def _run():
        try:
            from ..app import create_app
            app = create_app()
            with app.app_context():
                from ..assistant.hub_models import HubNote
                from ..models import db
                vec = generate_embedding(content, api_key)
                if vec is None:
                    return
                note = HubNote.query.get(note_id)
                if note:
                    note.embedding = json.dumps(vec)
                    db.session.commit()
        except Exception as exc:
            _log.warning("embed_note_background failed for note %s: %s", note_id, exc)

    threading.Thread(target=_run, daemon=True).start()


def semantic_search_notes(user_id: int, query: str, api_key: str, limit: int = 10) -> list[dict]:
    """
    Search hub_notes for user by semantic similarity to query.
    Returns list of {id, content_preview, tags, score, created_at}.
    """
    query_vec = generate_embedding(query, api_key)
    if query_vec is None:
        return []

    from ..assistant.hub_models import HubNote
    from ..assistant.hub_crypto import _dec

    notes = HubNote.query.filter(
        HubNote.user_id == user_id,
        HubNote.embedding.isnot(None),
    ).all()

    scored = []
    for n in notes:
        try:
            vec = json.loads(n.embedding)
        except Exception:
            continue
        score = _cosine(query_vec, vec)
        if score > 0.3:
            content = _dec(n.content) or ""
            scored.append({
                "id": n.id,
                "type": "note",
                "content_preview": content[:200],
                "tags": n.tags or [],
                "score": round(score, 4),
                "created_at": n.created_at.isoformat() if n.created_at else None,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def semantic_search_knowledge(user_id: int, query: str, api_key: str, limit: int = 10) -> list[dict]:
    """
    Search hub_knowledge_cards for user by semantic similarity to query.
    Returns list of {id, title, content_preview, score}.
    """
    query_vec = generate_embedding(query, api_key)
    if query_vec is None:
        return []

    from ..assistant.hub_models import HubKnowledgeCard
    from ..assistant.hub_crypto import _dec

    cards = HubKnowledgeCard.query.filter(
        HubKnowledgeCard.user_id == user_id,
        HubKnowledgeCard.embedding.isnot(None),
    ).all()

    scored = []
    for c in cards:
        try:
            vec = json.loads(c.embedding)
        except Exception:
            continue
        score = _cosine(query_vec, vec)
        if score > 0.3:
            scored.append({
                "id": c.id,
                "type": "knowledge_card",
                "title": _dec(c.title) or "",
                "content_preview": (_dec(c.content) or "")[:200],
                "tags": c.tags or [],
                "score": round(score, 4),
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
