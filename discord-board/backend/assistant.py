"""Assistant helpers: reminder duration parsing + DB ops for reminders, notes,
and the AI-usage ledger. No discord.py; the bot owns delivery.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from models import AITokenUsage, Note, Reminder

_DUR_RE = re.compile(r"(\d+)\s*([smhdw])", re.I)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> int | None:
    """Parse '10m', '2h', '1d30m', '45', etc. into seconds (max 365d). A bare
    number is treated as minutes. Returns None if nothing parses."""
    if not text:
        return None
    text = text.strip().lower()
    if text.isdigit():
        secs = int(text) * 60
        return min(secs, 365 * 86400) if secs > 0 else None
    total = 0
    for amount, unit in _DUR_RE.findall(text):
        total += int(amount) * _UNIT_SECONDS[unit.lower()]
    if total <= 0:
        return None
    return min(total, 365 * 86400)


def add_reminder(db, guild_id, user_id, text: str, seconds: int) -> Reminder:
    r = Reminder(
        guild_id=guild_id, user_id=user_id, text=(text or "")[:500],
        due_at=datetime.utcnow() + timedelta(seconds=seconds), delivered=False,
    )
    db.add(r)
    return r


def list_reminders(db, user_id, limit=10):
    return (
        db.query(Reminder)
        .filter(Reminder.user_id == user_id, Reminder.delivered.is_(False))
        .order_by(Reminder.due_at)
        .limit(limit)
        .all()
    )


def due_reminders(db, limit=50):
    return (
        db.query(Reminder)
        .filter(Reminder.delivered.is_(False), Reminder.due_at <= datetime.utcnow())
        .order_by(Reminder.due_at)
        .limit(limit)
        .all()
    )


def add_note(db, user_id, guild_id, content: str) -> Note:
    n = Note(user_id=user_id, guild_id=guild_id, content=(content or "")[:2000])
    db.add(n)
    return n


def list_notes(db, user_id, limit=15):
    return (
        db.query(Note)
        .filter(Note.user_id == user_id)
        .order_by(Note.created_at.desc())
        .limit(limit)
        .all()
    )


def log_ai_usage(db, guild_id, user_id, model, input_tokens, output_tokens) -> None:
    db.add(AITokenUsage(
        guild_id=guild_id, user_id=user_id, model=model,
        input_tokens=input_tokens or 0, output_tokens=output_tokens or 0,
    ))
