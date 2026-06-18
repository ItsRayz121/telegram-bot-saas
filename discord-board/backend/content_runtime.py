"""Scheduled messages, polls, and auto-responses — DB helpers for the bot
(Phase 12). No discord.py here; pure functions over the session, same pattern
as campaign_runtime.py. All "due" queries are scoped to the guilds the calling
bot identity serves, so the fleet never double-posts.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from sqlalchemy import or_

from database import SessionLocal
from models import AutoResponse, GuildEvent, Poll, ScheduledMessage

RECURRENCE_DELTAS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}


# --- scheduled messages -----------------------------------------------------------
def due_messages(served_guild_ids: list[int]) -> list[dict]:
    if not served_guild_ids:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(ScheduledMessage)
            .filter(ScheduledMessage.enabled.is_(True),
                    ScheduledMessage.next_run_at <= datetime.utcnow(),
                    ScheduledMessage.guild_id.in_(served_guild_ids))
            .limit(25)
            .all()
        )
        return [{"id": r.id, "guild_id": r.guild_id, "channel_id": r.channel_id,
                 "content": r.content or "", "embed": dict(r.embed) if r.embed else None}
                for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def advance_schedule(message_id: int, sent: bool) -> None:
    """After a send attempt: recurring -> roll next_run_at forward (skipping any
    missed slots); one-shot -> disable."""
    db = SessionLocal()
    try:
        row = db.get(ScheduledMessage, message_id)
        if row is None:
            return
        if sent:
            row.last_sent_at = datetime.utcnow()
        delta = RECURRENCE_DELTAS.get(row.recurrence or "none")
        if delta is None:
            row.enabled = False
        else:
            nxt = row.next_run_at or datetime.utcnow()
            while nxt <= datetime.utcnow():
                nxt += delta
            row.next_run_at = nxt
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


# --- polls -------------------------------------------------------------------------
def polls_to_post(served_guild_ids: list[int]) -> list[dict]:
    if not served_guild_ids:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(Poll)
            .filter(Poll.needs_post.is_(True),
                    Poll.status.in_(("pending", "scheduled")),
                    Poll.guild_id.in_(served_guild_ids),
                    or_(Poll.scheduled_at.is_(None), Poll.scheduled_at <= datetime.utcnow()))
            .limit(10)
            .all()
        )
        return [{"id": r.id, "guild_id": r.guild_id, "channel_id": r.channel_id,
                 "question": r.question, "answers": list(r.answers or []),
                 "duration_hours": r.duration_hours or 24,
                 "multiselect": bool(r.multiselect)} for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def mark_poll_posted(poll_id: int, message_id: int | None) -> None:
    db = SessionLocal()
    try:
        row = db.get(Poll, poll_id)
        if row is None:
            return
        row.needs_post = False
        if message_id is None:
            row.status = "failed"
        else:
            row.message_id = message_id
            row.status = "open"
            row.ends_at = datetime.utcnow() + timedelta(hours=row.duration_hours or 24)
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def polls_to_finalize(served_guild_ids: list[int]) -> list[dict]:
    if not served_guild_ids:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(Poll)
            .filter(Poll.status == "open", Poll.ends_at <= datetime.utcnow(),
                    Poll.guild_id.in_(served_guild_ids))
            .limit(10)
            .all()
        )
        return [{"id": r.id, "guild_id": r.guild_id, "channel_id": r.channel_id,
                 "message_id": r.message_id} for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def record_poll_results(poll_id: int, results: dict | None) -> None:
    db = SessionLocal()
    try:
        row = db.get(Poll, poll_id)
        if row is None:
            return
        row.status = "ended"
        row.results = results or {}
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


# --- Discord scheduled events (Phase 4 native) ---------------------------------------
def _event_dict(r: GuildEvent) -> dict:
    return {"id": r.id, "guild_id": r.guild_id, "name": r.name or "",
            "description": r.description or "", "entity_type": r.entity_type or "external",
            "channel_id": r.channel_id, "location": r.location,
            "start_at": r.start_at, "end_at": r.end_at,
            "remind_minutes": r.remind_minutes or 0,
            "reminder_channel_id": r.reminder_channel_id,
            "discord_event_id": r.discord_event_id}


def events_to_create(served_guild_ids: list[int]) -> list[dict]:
    if not served_guild_ids:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(GuildEvent)
            .filter(GuildEvent.needs_create.is_(True), GuildEvent.status == "pending",
                    GuildEvent.start_at > datetime.utcnow(),
                    GuildEvent.guild_id.in_(served_guild_ids))
            .limit(10)
            .all()
        )
        return [_event_dict(r) for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def events_to_delete(served_guild_ids: list[int]) -> list[dict]:
    if not served_guild_ids:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(GuildEvent)
            .filter(GuildEvent.needs_delete.is_(True),
                    GuildEvent.discord_event_id.isnot(None),
                    GuildEvent.guild_id.in_(served_guild_ids))
            .limit(10)
            .all()
        )
        return [_event_dict(r) for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def events_to_remind(served_guild_ids: list[int]) -> list[dict]:
    """Created events whose reminder window just opened (start still ahead)."""
    if not served_guild_ids:
        return []
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        rows = (
            db.query(GuildEvent)
            .filter(GuildEvent.status == "created", GuildEvent.reminded.is_(False),
                    GuildEvent.remind_minutes > 0,
                    GuildEvent.reminder_channel_id.isnot(None),
                    GuildEvent.start_at > now,
                    GuildEvent.guild_id.in_(served_guild_ids))
            .limit(25)
            .all()
        )
        due = [r for r in rows
               if (r.start_at - now) <= timedelta(minutes=r.remind_minutes or 0)]
        return [_event_dict(r) for r in due]
    finally:
        db.close()
        SessionLocal.remove()


def mark_event_created(event_id: int, discord_event_id, error: str | None = None) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildEvent, event_id)
        if row is None:
            return
        row.needs_create = False
        if discord_event_id is None:
            row.status = "failed"
            row.error = (error or "could not create the event")[:200]
        else:
            row.discord_event_id = int(discord_event_id)
            row.status = "created"
            row.error = None
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def mark_event_reminded(event_id: int) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildEvent, event_id)
        if row is not None:
            row.reminded = True
            db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def mark_event_deleted(event_id: int) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildEvent, event_id)
        if row is not None:
            row.needs_delete = False
            row.status = "cancelled"
            db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def finish_past_events(served_guild_ids: list[int]) -> None:
    """Flip created events whose start time passed to done (no Discord calls)."""
    if not served_guild_ids:
        return
    db = SessionLocal()
    try:
        (db.query(GuildEvent)
         .filter(GuildEvent.status == "created",
                 GuildEvent.start_at <= datetime.utcnow(),
                 GuildEvent.guild_id.in_(served_guild_ids))
         .update({GuildEvent.status: "done"}, synchronize_session=False))
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


# --- auto-responses -----------------------------------------------------------------
def load_responses(guild_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(AutoResponse)
            .filter(AutoResponse.guild_id == guild_id, AutoResponse.enabled.is_(True))
            .all()
        )
        return [{"id": r.id, "trigger": r.trigger or "", "match_type": r.match_type or "contains",
                 "response": r.response or "", "cooldown_seconds": r.cooldown_seconds or 30}
                for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def match_response(text: str, responses: list[dict]) -> dict | None:
    """First matching enabled trigger, case-insensitive. Pure."""
    low = (text or "").lower()
    if not low:
        return None
    for r in responses:
        trig = (r["trigger"] or "").lower().strip()
        if not trig:
            continue
        if r["match_type"] == "exact":
            if low.strip() == trig:
                return r
        elif trig in low:
            return r
    return None


# in-memory cooldown: (guild_id, response_id) -> monotonic timestamp
_last_fired: dict[tuple[int, int], float] = {}


def cooldown_ok(guild_id: int, response: dict) -> bool:
    key = (guild_id, response["id"])
    now = time.monotonic()
    if now - _last_fired.get(key, 0.0) < max(1, int(response["cooldown_seconds"])):
        return False
    _last_fired[key] = now
    return True
