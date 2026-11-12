"""A Discord member's X handle, saved ONCE and reused by every campaign.

Keyed on the Discord user id (usernames change, the id never does) and shared across
servers. One X handle can belong to only one Discord account, so a single X account
can't farm XP through several Discord accounts. Kill switch: SOCIAL_HANDLE_UNIQUE=0.
Nothing links to Telegram - this is Discord-only.
"""
from __future__ import annotations

import logging
import os

import twitter_verify
from database import SessionLocal
from models import SocialIdentity

log = logging.getLogger(__name__)

TAKEN = "__taken__"   # set_handle() result: the handle belongs to a different account


def _unique_enabled() -> bool:
    return os.environ.get("SOCIAL_HANDLE_UNIQUE", "1").strip().lower() not in ("0", "false", "off", "no")


def taken(db, user_id: int, handle: str, platform: str = "x") -> bool:
    """True if a DIFFERENT Discord account already holds this handle."""
    if not _unique_enabled() or not handle:
        return False
    row = (
        db.query(SocialIdentity)
        .filter(
            SocialIdentity.platform == platform,
            SocialIdentity.handle_lc == handle.lower(),
            SocialIdentity.user_id != user_id,
        )
        .first()
    )
    return row is not None


def get_handle(user_id: int, platform: str = "x") -> str | None:
    db = SessionLocal()
    try:
        row = db.get(SocialIdentity, {"user_id": user_id, "platform": platform})
        return row.handle if row else None
    except Exception:  # noqa: BLE001 - never break a campaign over this
        log.exception("get_handle failed")
        return None
    finally:
        db.close()
        SessionLocal.remove()


def set_handle(user_id: int, raw: str, platform: str = "x") -> str | None:
    """Save (or change) the member's handle. Returns the stored handle, TAKEN if another
    account holds it, or None if the input isn't a usable username."""
    norm = twitter_verify.normalize_handle(raw)
    if not norm or len(norm) > 15 or not all(ch.isalnum() or ch == "_" for ch in norm):
        return None
    db = SessionLocal()
    try:
        if taken(db, user_id, norm, platform):
            return TAKEN
        row = db.get(SocialIdentity, {"user_id": user_id, "platform": platform})
        if row is None:
            db.add(SocialIdentity(user_id=user_id, platform=platform, handle=norm, handle_lc=norm.lower()))
        else:
            row.handle, row.handle_lc = norm, norm.lower()
        db.commit()
        return norm
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("set_handle failed")
        return None
    finally:
        db.close()
        SessionLocal.remove()
