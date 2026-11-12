"""Record when a member leaves / is removed from a Discord server (and when they return).

Display-only: feeds the "Left / Removed / Banned" badge in the Guildizer dashboard and
never changes enforcement. Kill switch: MEMBER_LEAVE_TRACKING=0 stops all writes.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from database import SessionLocal
from models import Member

log = logging.getLogger(__name__)

# A leave event arriving within this window of a dashboard/ban action keeps that
# action's more specific reason instead of being overwritten with a plain "left".
_RECENT = timedelta(seconds=90)


def enabled() -> bool:
    return os.environ.get("MEMBER_LEAVE_TRACKING", "1").strip().lower() not in ("0", "false", "off", "no")


def mark(db, guild_id: int, user_id: int, reason: str, *, keep_recent: bool = False) -> None:
    """Flag an existing member row (caller commits). Never creates rows."""
    if not enabled():
        return
    row = db.get(Member, {"guild_id": guild_id, "user_id": user_id})
    if row is None:
        return
    if keep_recent and row.removed_at and datetime.utcnow() - row.removed_at < _RECENT:
        return
    row.removed_at = datetime.utcnow()
    row.removed_reason = reason


def clear(db, guild_id: int, user_id: int) -> None:
    row = db.get(Member, {"guild_id": guild_id, "user_id": user_id})
    if row is not None and row.removed_at is not None:
        row.removed_at = None
        row.removed_reason = None


def _run(fn, guild_id: int, user_id: int, *args, **kw) -> None:
    db = SessionLocal()
    try:
        fn(db, guild_id, user_id, *args, **kw)
        db.commit()
    except Exception:  # noqa: BLE001 - must never affect the bot
        db.rollback()
        log.exception("member presence update failed (guild %s)", guild_id)
    finally:
        db.close()
        SessionLocal.remove()


def record_left(guild_id: int, user_id: int) -> None:
    _run(mark, guild_id, user_id, "left", keep_recent=True)


def record_banned(guild_id: int, user_id: int) -> None:
    _run(mark, guild_id, user_id, "banned")


def record_joined(guild_id: int, user_id: int) -> None:
    _run(clear, guild_id, user_id)
