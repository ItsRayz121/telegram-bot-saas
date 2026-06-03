"""Pending-group reconciliation (P5).

A TelegramGroup is created with bot_status="pending" when the bot first joins,
and flips to "active" when an owner is attached (link code redeemed or website
user matched). Some groups get stuck "pending" even though the bot is present,
an owner exists, and messages are flowing — that is the bug this module fixes.

`evaluate_pending()` is a pure decision function (DB facts only, no Telegram
calls) shared by the scheduled reconcile job, the admin "why pending" view, and
the manual force-activate action, so all three always agree.
"""
from __future__ import annotations

from datetime import datetime, timedelta

ACTIVITY_WINDOW = timedelta(days=7)


def evaluate_pending(tg, has_recent_activity: bool):
    """Return (should_promote: bool, reason: str) for a pending group.

    Promote only when there is an owner AND recent activity — recent messages
    prove the bot is present and able to read the chat, and an owner proves the
    group was genuinely claimed. Everything else is left pending with a reason.
    """
    has_owner = tg.owner_user_id is not None
    perms = (getattr(tg, "bot_permissions", None) or {})
    # "Permissions valid": either we have a recorded permission score, or we are
    # currently receiving messages (which is only possible if the bot is in the
    # group and can read it).
    perms_ok = bool(perms.get("permission_score", 0)) or has_recent_activity

    if has_owner and has_recent_activity and perms_ok:
        return True, "active_but_marked_pending — owner set, messages flowing, bot present; auto-promoted"
    if not has_owner and not tg.linked_at:
        return False, "never_linked — bot is in the group but no one has run /linkgroup + pasted the code"
    if has_owner and not has_recent_activity:
        return False, "linked_no_recent_activity — owner set but no messages in 7d (bot may have been removed)"
    if has_owner:
        return False, "permissions_unconfirmed — owner set but bot permissions not validated"
    return False, "unlinked — was linked before, owner cleared"


def _has_recent_activity(tg, now=None) -> bool:
    """True if the group received a buffered message within ACTIVITY_WINDOW."""
    from .models import MessageBuffer
    now = now or datetime.utcnow()
    last = (
        MessageBuffer.query
        .filter_by(telegram_group_id=tg.telegram_group_id)
        .order_by(MessageBuffer.created_at.desc())
        .first()
    )
    return bool(last and last.created_at >= now - ACTIVITY_WINDOW)


def reconcile_group(tg, now=None) -> str | None:
    """Promote a single pending group to active when eligible.

    Returns the reason string if promoted, else None. Caller commits the session.
    """
    if tg.bot_status != "pending" or tg.is_disabled:
        return None
    now = now or datetime.utcnow()
    should_promote, reason = evaluate_pending(tg, _has_recent_activity(tg, now))
    if not should_promote:
        return None
    tg.bot_status = "active"
    if not tg.linked_at:
        tg.linked_at = now
    return reason


def reconcile_pending_groups(db) -> int:
    """Promote all eligible pending groups. Returns the number promoted."""
    from .models import TelegramGroup, BotEvent
    now = datetime.utcnow()
    promoted = 0
    for tg in TelegramGroup.query.filter_by(bot_status="pending", is_disabled=False).all():
        reason = reconcile_group(tg, now)
        if reason:
            db.session.add(BotEvent(
                telegram_group_id=tg.telegram_group_id,
                event_type="group_auto_activated",
                message=f"Auto-promoted pending→active: {reason}",
            ))
            promoted += 1
    if promoted:
        db.session.commit()
    return promoted
