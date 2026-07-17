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


# When the knowledge below doesn't cover the question, the model must output
# exactly this token — callers turn it into a moderator escalation instead of
# posting "I don't know" into the channel. (Same pattern as Telegizer's
# NO_ANSWER sentinel; logic copied, never imported.)
NO_ANSWER_SENTINEL = "NO_ANSWER"

_PROMPT_HEADER = (
    "You are this Discord server's helpful assistant. Answer the member's "
    "question using ONLY the server knowledge below. If the server knowledge "
    "does not contain the information needed to answer, reply with exactly "
    "NO_ANSWER and nothing else — no apology, no explanation; the system "
    "forwards unanswered questions to the moderators. Never tell the member "
    "you don't know. Be concise.\n\n"
    "SERVER KNOWLEDGE:\n"
)


def is_no_answer(text: str | None) -> bool:
    """True when the model signalled it has no answer (or produced nothing)."""
    if not text or not text.strip():
        return True
    stripped = text.strip()
    head = stripped.strip("\"'`*_ .!").upper()
    if head in (NO_ANSWER_SENTINEL, "NO ANSWER"):
        return True
    # Sentinel token followed by extra prose — underscore form only, so a real
    # answer like "No answers are given for…" is never misclassified.
    return stripped.upper().startswith(NO_ANSWER_SENTINEL)


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
        from models import AutoResponse
        docs = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.guild_id == guild_id,
                    KnowledgeDocument.enabled.is_(True))
            .limit(50)
            .all()
        )
        # (title, text) candidates: KB docs (uploaded files expose content_text)
        # plus enabled auto-responses opted into AI knowledge (trigger -> reply).
        candidates: list[tuple[str, str]] = [
            (d.title, d.content_text or d.content or "") for d in docs
        ]
        ai_responses = (
            db.query(AutoResponse)
            .filter(AutoResponse.guild_id == guild_id,
                    AutoResponse.enabled.is_(True),
                    AutoResponse.use_as_ai_knowledge.is_(True))
            .limit(100)
            .all()
        )
        candidates += [(r.trigger, r.response or "") for r in ai_responses]
        if not candidates:
            return None, False
        q_terms = _terms(question)
        scored = []
        for title, text in candidates:
            doc_terms = _terms(f"{title} {text}")
            overlap = 0
            for t in q_terms:
                if t in doc_terms:
                    overlap += 1
                elif len(t) >= 4 and any(
                    dt.startswith(t) or t.startswith(dt)
                    for dt in doc_terms if len(dt) >= 4
                ):
                    overlap += 1   # prefix match: refund ~ refunds, launch ~ launches
            scored.append((overlap, title, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        confident = scored[0][0] > 0
        top = [(t, x) for score, t, x in scored[:3] if score > 0] or [(scored[0][1], scored[0][2])]
        context = ""
        for title, text in top:
            chunk = f"## {title}\n{text}\n\n"
            if len(context) + len(chunk) > _MAX_CONTEXT:
                break
            context += chunk
        return _PROMPT_HEADER + context.strip(), confident
    finally:
        db.close()
        SessionLocal.remove()
