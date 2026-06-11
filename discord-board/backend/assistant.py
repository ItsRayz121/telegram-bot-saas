"""Assistant helpers: reminder duration parsing + DB ops for reminders, notes,
and the AI-usage ledger. No discord.py; the bot owns delivery.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from models import AITokenUsage, Note, Reminder

_DUR_RE = re.compile(r"(\d+)\s*([smhdw])", re.I)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def utc_ts(dt) -> int:
    """Epoch seconds for a naive-UTC DB datetime. Naive .timestamp() would
    interpret it in the server's local zone — wrong anywhere but UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


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


# --- Phase 17: tasks + DM assistant context ------------------------------------
def add_task(db, user_id, guild_id, text: str):
    from models import Task
    task = Task(user_id=user_id, guild_id=guild_id, text=(text or "").strip()[:500])
    db.add(task)
    return task


def list_tasks(db, user_id, include_done: bool = False, limit: int = 15):
    from models import Task
    q = db.query(Task).filter(Task.user_id == user_id)
    if not include_done:
        q = q.filter(Task.done.is_(False))
    return q.order_by(Task.created_at).limit(limit).all()


def complete_task(db, user_id, task_id: int) -> bool:
    from datetime import datetime as _dt

    from models import Task
    task = db.get(Task, task_id)
    if task is None or task.user_id != user_id or task.done:
        return False
    task.done = True
    task.done_at = _dt.utcnow()
    return True


def personal_context(db, user_id) -> str:
    """Compact summary of the user's open items, grounding the DM assistant."""
    from models import Reminder, Task

    parts = []
    tasks = list_tasks(db, user_id, limit=10)
    if tasks:
        parts.append("Open tasks:\n" + "\n".join(f"- [{t.id}] {t.text}" for t in tasks))
    reminders = (
        db.query(Reminder)
        .filter(Reminder.user_id == user_id, Reminder.delivered.is_(False))
        .order_by(Reminder.due_at)
        .limit(10)
        .all()
    )
    if reminders:
        parts.append("Pending reminders:\n" + "\n".join(
            f"- {r.text} (due {r.due_at:%Y-%m-%d %H:%M} UTC)" for r in reminders))
    notes = list_notes(db, user_id, limit=8)
    if notes:
        parts.append("Recent notes:\n" + "\n".join(f"- {n.content[:120]}" for n in notes))
    return "\n\n".join(parts)
