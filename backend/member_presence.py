"""Record when a member leaves / is removed from a Telegram group (and when they return).

Called from the bots' service-message handlers. Display-only data: it feeds the
"Removed / Left" badge on the dashboard and never changes enforcement.

Kill switch: set MEMBER_LEAVE_TRACKING=0 (Railway env var) to stop all writes from
this module. Flags already stored stay in place.
"""
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def enabled():
    return os.environ.get("MEMBER_LEAVE_TRACKING", "1").strip().lower() not in ("0", "false", "off", "no")


def _row(scope, group_key, user_id):
    from .models import Member, OfficialMember
    if scope == "official":
        return OfficialMember.query.filter_by(
            telegram_group_id=str(group_key), telegram_user_id=str(user_id)).first()
    return Member.query.filter_by(group_id=group_key, telegram_user_id=str(user_id)).first()


def record_service_message(scope, group_key, message):
    """Apply a left_chat_member / new_chat_members service message. Must run inside
    an app context. Never raises - a failure here must not affect the bot."""
    if not enabled() or message is None:
        return
    try:
        from .models import db
        changed = False
        left = getattr(message, "left_chat_member", None)
        if left is not None and not getattr(left, "is_bot", False):
            row = _row(scope, group_key, left.id)
            if row is not None:
                sender = getattr(message, "from_user", None)
                row.removed_at = datetime.utcnow()
                row.removed_reason = "left" if sender is not None and sender.id == left.id else "kicked"
                changed = True
        for u in (getattr(message, "new_chat_members", None) or []):
            if getattr(u, "is_bot", False):
                continue
            row = _row(scope, group_key, u.id)
            if row is not None and row.removed_at is not None:
                row.removed_at = None
                row.removed_reason = None
                changed = True
        if changed:
            db.session.commit()
    except Exception as exc:  # defensive: never break the bot
        logger.warning("member presence update failed: %s", exc)
        try:
            from .models import db
            db.session.rollback()
        except Exception:
            pass


def mark_removed(member, reason):
    """Dashboard kick/ban: flag the row (caller commits)."""
    if member is not None and enabled():
        member.removed_at = datetime.utcnow()
        member.removed_reason = reason


def clear_removed(member):
    """Dashboard unban: lift the flag (caller commits)."""
    if member is not None and getattr(member, "removed_at", None) is not None:
        member.removed_at = None
        member.removed_reason = None
