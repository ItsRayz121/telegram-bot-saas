"""Escalation auto-learn: when a staff member REPLIES to a Guildizer escalation alert, the
original member's message plus that answer is saved as a knowledge-base entry, so the next
person who asks gets the answer from /ask (Telegizer parity: "learn from admin replies").

Opt-in (escalation.learn_from_replies), staff-only (the replier needs Manage Messages), only in
the configured alert channel, and bounded by the plan's knowledge-document cap. Pure helpers +
one sync DB function; the bot supplies the discord.py parts.
"""
from __future__ import annotations

import re

from database import SessionLocal
from models import KnowledgeDocument

_JUMP = re.compile(r"discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")
MIN_LEN = 8
MAX_Q, MAX_A = 300, 1500


def parse_jump(text: str):
    """(guild_id, channel_id, message_id) of the first message link in an alert, else None."""
    m = _JUMP.search(text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def qa_entry(question: str, answer: str):
    """(title, content) for a usable pair, else None (too short, a command, or just a link)."""
    q = " ".join((question or "").split())
    a = (answer or "").strip()
    if len(q) < MIN_LEN or len(a) < MIN_LEN or q.startswith(("/", "!")) or a.startswith("http") and " " not in a:
        return None
    return q[:MAX_Q], f"Q: {q[:MAX_Q]}\nA: {a[:MAX_A]}"


def save(guild_id: int, title: str, content: str) -> str:
    """'saved' | 'duplicate' | 'limit'. Skips an existing entry with the same question."""
    import plan_limits
    db = SessionLocal()
    try:
        docs = (db.query(KnowledgeDocument)
                .filter(KnowledgeDocument.guild_id == guild_id, KnowledgeDocument.source_id.is_(None)).all())
        if any((d.title or "").strip().lower() == title.strip().lower() for d in docs):
            return "duplicate"
        if len(docs) >= plan_limits.limit(db, guild_id, "knowledge_docs"):
            return "limit"
        db.add(KnowledgeDocument(guild_id=guild_id, title=title[:200], content=content[:8000]))
        db.commit()
        return "saved"
    except Exception:  # noqa: BLE001
        db.rollback()
        return "limit"
    finally:
        db.close()
        SessionLocal.remove()
