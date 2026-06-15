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


_PROMPT_HEADER = (
    "You are this Discord server's helpful assistant. Answer the member's "
    "question using ONLY the server knowledge below when relevant; if the "
    "answer isn't covered, say so briefly. Be concise.\n\n"
    "SERVER KNOWLEDGE:\n"
)


def grounded_with_confidence(guild_id: int, question: str) -> tuple[str | None, bool]:
    """(system_prompt_or_None, confident). Confident means the knowledge base
    actually matched the question — when False the prompt still carries the
    best-guess content, but callers may prefer a fallback/escalation.

    Uploaded documents are retrieved semantically (cosine over embedded chunks);
    when no embedded chunks exist we fall back to keyword overlap over the
    manual FAQ-style documents."""
    try:
        import kb_index
        sem = kb_index.semantic_context(guild_id, question)
    except Exception:  # noqa: BLE001 — never let retrieval break /ask
        sem = None
    if sem is not None:
        context, confident = sem
        if context:
            return _PROMPT_HEADER + context, confident

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
            return None, False
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
        confident = scored[0][0] > 0
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
        ), confident
    finally:
        db.close()
        SessionLocal.remove()
