"""Knowledge base retrieval grounding /ask (Phase 16). Plain keyword-overlap
scoring — no embeddings dependency; good enough for FAQ-sized doc sets.
"""
from __future__ import annotations

import re

from database import SessionLocal
from models import KnowledgeDocument

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_MAX_CONTEXT = 4000


def _terms(text: str) -> set[str]:
    return set(_WORD_RE.findall((text or "").lower()))


def grounded_system(guild_id: int, question: str) -> str | None:
    """System prompt grounded on this guild's best-matching docs, or None when
    the guild has no usable knowledge base."""
    db = SessionLocal()
    try:
        docs = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.guild_id == guild_id,
                    KnowledgeDocument.enabled.is_(True))
            .limit(50)
            .all()
        )
        if not docs:
            return None
        q_terms = _terms(question)
        scored = []
        for d in docs:
            doc_terms = _terms(f"{d.title} {d.content}")
            overlap = 0
            for t in q_terms:
                if t in doc_terms:
                    overlap += 1
                elif len(t) >= 4 and any(
                    dt.startswith(t) or t.startswith(dt)
                    for dt in doc_terms if len(dt) >= 4
                ):
                    overlap += 1   # prefix match: refund ~ refunds, launch ~ launches
            scored.append((overlap, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [d for score, d in scored[:3] if score > 0] or [scored[0][1]]
        context = ""
        for d in top:
            chunk = f"## {d.title}\n{d.content}\n\n"
            if len(context) + len(chunk) > _MAX_CONTEXT:
                break
            context += chunk
        return (
            "You are this Discord server's helpful assistant. Answer the member's "
            "question using ONLY the server knowledge below when relevant; if the "
            "answer isn't covered, say so briefly. Be concise.\n\n"
            f"SERVER KNOWLEDGE:\n{context.strip()}"
        )
    finally:
        db.close()
        SessionLocal.remove()
