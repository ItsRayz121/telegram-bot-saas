"""
GroupSignalExtractor — compute daily health signals for each Telegram group.

Called by the Celery beat task `extract_group_signals` every 2 hours.
Reads MessageBuffer records from the last 24 hours, computes structured
signals, and upserts into GroupDailySignal.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Optional

_log = logging.getLogger(__name__)

# Simple spam heuristics — messages matching these are flagged
_SPAM_PATTERNS = [
    re.compile(r"(join|click|earn|free|prize|win|crypto|t\.me/)", re.I),
    re.compile(r"https?://", re.I),
]

# Conflict heuristics
_CONFLICT_PATTERNS = [
    re.compile(r"\b(idiot|stupid|shut up|you suck|hate you|f\*\*k|moron)\b", re.I),
]

# Question detection
_QUESTION_RE = re.compile(r"\?")

# Common stopwords to filter when extracting topics
_STOPWORDS = {
    "the", "a", "an", "is", "it", "in", "on", "at", "to", "and", "or",
    "of", "for", "with", "this", "that", "are", "was", "be", "as", "i",
    "we", "you", "he", "she", "they", "my", "your", "our", "has", "have",
    "had", "not", "but", "so", "do", "did", "will", "can", "just", "up",
    "me", "hi", "hey", "ok", "okay", "yes", "no",
}


def extract_for_group(group, messages: list, ai_key_info: Optional[dict] = None) -> dict:
    """
    Compute signal dict for a single group from a list of MessageBuffer rows.
    Returns a dict matching GroupDailySignal columns (excluding id/dates).
    """
    if not messages:
        return _empty_signal()

    senders = set()
    spam_hits = 0
    conflict_hits = 0
    question_count = 0
    answer_count = 0
    word_freq: Counter = Counter()

    for msg in messages:
        content = (msg.message_text or "").strip()
        sender = msg.sender_name or "unknown"
        senders.add(sender)

        # Spam scoring
        for pat in _SPAM_PATTERNS:
            if pat.search(content):
                spam_hits += 1
                break

        # Conflict scoring
        for pat in _CONFLICT_PATTERNS:
            if pat.search(content):
                conflict_hits += 1
                break

        # Question / answer detection
        if _QUESTION_RE.search(content):
            question_count += 1
        else:
            answer_count += 1

        # Word frequency for topic extraction
        for word in re.findall(r"[a-zA-Z]{4,}", content):
            w = word.lower()
            if w not in _STOPWORDS:
                word_freq[w] += 1

    total = len(messages)
    spam_score = min(10.0, round(spam_hits / total * 10, 2)) if total else 0.0
    conflict_score = min(10.0, round(conflict_hits / total * 10, 2)) if total else 0.0

    # Unanswered questions: if questions >> answers, flag as unanswered
    questions_unanswered = max(0, question_count - answer_count)

    top_topics = [w for w, _ in word_freq.most_common(5)]

    # Sentiment heuristic
    if conflict_score >= 3:
        sentiment = "negative"
    elif spam_score >= 4:
        sentiment = "negative"
    elif conflict_score <= 1 and spam_score <= 1:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    # Health status
    if conflict_score >= 5 or spam_score >= 6:
        health_status = "critical"
    elif conflict_score >= 2 or spam_score >= 3 or questions_unanswered >= 10:
        health_status = "watch"
    else:
        health_status = "healthy"

    # AI summary (optional — only if key provided and group has meaningful activity)
    ai_summary = None
    if ai_key_info and total >= 5:
        try:
            ai_summary = _generate_ai_summary(
                group_title=getattr(group, "title", str(group)),
                messages=messages[:40],
                health_status=health_status,
                key_info=ai_key_info,
            )
        except Exception as exc:
            _log.warning("AI summary for group %s failed: %s", getattr(group, "telegram_group_id", "?"), exc)

    return {
        "message_count": total,
        "active_members": len(senders),
        "spam_score": spam_score,
        "conflict_score": conflict_score,
        "questions_unanswered": questions_unanswered,
        "top_topics": top_topics,
        "sentiment": sentiment,
        "health_status": health_status,
        "ai_summary": ai_summary,
    }


def _empty_signal() -> dict:
    return {
        "message_count": 0,
        "active_members": 0,
        "spam_score": 0.0,
        "conflict_score": 0.0,
        "questions_unanswered": 0,
        "top_topics": [],
        "sentiment": "neutral",
        "health_status": "healthy",
        "ai_summary": None,
    }


def _generate_ai_summary(group_title: str, messages: list, health_status: str, key_info: dict) -> str:
    """Ask AI for a ≤120-char one-liner summary of today's group activity."""
    lines = []
    for m in messages:
        sender = m.sender_name or "User"
        lines.append(f"{sender}: {(m.message_text or '')[:80]}")
    context = "\n".join(lines)[:3000]

    prompt = (
        f"Summarize today's activity in the Telegram group '{group_title}' in ONE sentence (≤120 chars).\n"
        f"Health status: {health_status}.\n"
        f"Recent messages:\n{context}\n\n"
        "Return only the sentence, no quotes."
    )

    import requests as _r
    provider = key_info.get("provider", "gemini")
    api_key = key_info["api_key"]
    model = key_info.get("model", "gemini-2.0-flash")

    if provider == "gemini":
        resp = _r.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=20,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    elif provider == "anthropic":
        resp = _r.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={"model": model or "claude-haiku-4-5-20251001", "max_tokens": 60,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=20,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
    else:
        base = key_info.get("base_url", "https://api.openai.com/v1")
        resp = _r.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model or "gpt-4o-mini", "max_tokens": 60,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=20,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()

    return text[:500]


def run_extraction(app=None):
    """
    Main entry point called by the Celery task.
    Iterates all active groups, computes signals for today, upserts into DB.
    """
    ctx = app.app_context() if app else None
    if ctx:
        ctx.push()

    try:
        from ..models import db, TelegramGroup, MessageBuffer, GroupDailySignal, User
        from ..assistant.ai_key_resolver import get_workspace_ai_key

        today = date.today()
        cutoff = datetime.utcnow() - timedelta(hours=24)

        groups = TelegramGroup.query.filter_by(is_disabled=False).all()
        _log.info("GroupSignalExtractor: processing %d groups", len(groups))

        for group in groups:
            try:
                messages = (
                    MessageBuffer.query
                    .filter_by(telegram_group_id=group.telegram_group_id)
                    .filter(MessageBuffer.created_at >= cutoff)
                    .order_by(MessageBuffer.created_at.asc())
                    .limit(500)
                    .all()
                )

                # Resolve AI key for the group owner
                owner = User.query.get(group.owner_user_id) if group.owner_user_id else None
                ai_key_info = get_workspace_ai_key(owner) if owner else {}

                signal_data = extract_for_group(group, messages, ai_key_info if ai_key_info.get("api_key") else None)

                # Upsert
                existing = GroupDailySignal.query.filter_by(
                    telegram_group_id=group.telegram_group_id,
                    date=today,
                ).first()

                if existing:
                    for k, v in signal_data.items():
                        setattr(existing, k, v)
                    existing.updated_at = datetime.utcnow()
                else:
                    record = GroupDailySignal(
                        telegram_group_id=group.telegram_group_id,
                        date=today,
                        **signal_data,
                    )
                    db.session.add(record)

            except Exception as exc:
                _log.warning("Signal extraction failed for group %s: %s", group.telegram_group_id, exc)
                db.session.rollback()
                continue

        db.session.commit()
        _log.info("GroupSignalExtractor: committed signals for %d groups", len(groups))

    except Exception as exc:
        _log.error("GroupSignalExtractor run failed: %s", exc)
        if ctx:
            try:
                from ..models import db
                db.session.rollback()
            except Exception:
                pass
    finally:
        if ctx:
            ctx.pop()
