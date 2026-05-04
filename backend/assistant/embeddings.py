"""
Semantic search service using text embeddings.

Requires pgvector Postgres extension and pgvector Python package.
Gracefully degrades to keyword ILIKE search when pgvector is unavailable.

Usage:
    embed_text(text, api_key, provider) -> list[float]  (1536-dim for OpenAI, 768 for Gemini)
    embed_note(note, api_key, provider) -> None         (updates note.embedding in-place)
    semantic_search(user_id, query, limit) -> list[Note]
"""
from __future__ import annotations

import logging
from typing import Optional

_log = logging.getLogger(__name__)

# Dimension depends on provider/model
_OPENAI_DIM = 1536   # text-embedding-3-small
_GEMINI_DIM = 768    # text-embedding-004

_PGVECTOR_AVAILABLE = False
try:
    from pgvector.sqlalchemy import Vector  # noqa: F401
    _PGVECTOR_AVAILABLE = True
except ImportError:
    pass


def is_available() -> bool:
    return _PGVECTOR_AVAILABLE


def embed_text(text: str, key_info: dict) -> Optional[list[float]]:
    """Return embedding vector for text using the workspace AI key."""
    if not text or not key_info.get("api_key"):
        return None
    provider = key_info.get("provider", "openai")
    api_key = key_info["api_key"]

    try:
        import requests as _r

        if provider in ("openai", "openrouter"):
            base = key_info.get("base_url", "https://api.openai.com/v1")
            resp = _r.post(
                f"{base.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": "text-embedding-3-small", "input": text[:8000]},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]

        if provider == "gemini":
            model = "text-embedding-004"
            resp = _r.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={api_key}",
                json={"model": f"models/{model}", "content": {"parts": [{"text": text[:8000]}]}},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]

        # Anthropic doesn't have embeddings — fall through to None
        return None

    except Exception as exc:
        _log.warning("embed_text failed (provider=%s): %s", provider, exc)
        return None


def embed_note(note, key_info: dict) -> bool:
    """
    Compute and store embedding for a Note object.
    Returns True if embedding was stored, False otherwise.
    """
    if not _PGVECTOR_AVAILABLE:
        return False

    text = f"{note.title or ''}\n{note.content or ''}"[:4000]
    vec = embed_text(text, key_info)
    if vec is None:
        return False

    note.embedding = vec
    return True


def embed_document(doc, key_info: dict) -> bool:
    """Compute and store embedding for a WorkspaceKnowledgeDocument object."""
    if not _PGVECTOR_AVAILABLE:
        return False

    text = f"{doc.title or ''}\n{(doc.content or '')[:3900]}"
    vec = embed_text(text, key_info)
    if vec is None:
        return False

    doc.embedding = vec
    return True


def semantic_search(user_id: int, query: str, key_info: dict, limit: int = 5) -> list:
    """
    Search user's notes semantically. Falls back to ILIKE keyword search.
    Returns list of Note objects.
    """
    from ..models import Note

    # Pgvector path
    if _PGVECTOR_AVAILABLE:
        try:
            query_vec = embed_text(query, key_info)
            if query_vec:
                # L2 distance — closest vectors first
                results = (
                    Note.query
                    .filter_by(user_id=user_id)
                    .filter(Note.embedding.isnot(None))
                    .order_by(Note.embedding.l2_distance(query_vec))
                    .limit(limit)
                    .all()
                )
                if results:
                    return results
        except Exception as exc:
            _log.warning("semantic_search pgvector query failed: %s", exc)

    # Fallback: simple keyword ILIKE search
    keyword = f"%{query[:100]}%"
    return (
        Note.query
        .filter_by(user_id=user_id)
        .filter(
            (Note.title.ilike(keyword)) | (Note.content.ilike(keyword))
        )
        .order_by(Note.created_at.desc())
        .limit(limit)
        .all()
    )
