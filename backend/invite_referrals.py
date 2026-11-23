"""Member referral links on Telegram: a personal invite link per member, and XP for the inviter.

How it works
  * Any member can run /myinvite. The bot creates (once) a personal Telegram invite link for them in that
    group and stores it as an InviteLink row named "Invite by <name>" with created_by_telegram_id = the member.
  * When someone joins through a stored link, the join is recorded (InviteLinkJoin, uses_count) as before.
  * If the group has set `settings.invites.xp_per_invite` > 0 and the link is a member's personal link, that
    member (the inviter) earns the XP.

Rules that stop it being farmed (all covered by tests):
  * Only PERSONAL links pay. An admin's campaign link ("Twitter raid") never pays XP to its creator.
  * One reward per person per group: someone who was already counted through any link of the group
    (leaving and re-joining, or using a second link) pays nothing the second time.
  * No XP for inviting yourself, and none for a bot account.
  * The amount is clamped to 0..MAX_XP, and 0 (the default) means the feature is off.

Nothing is stored in a new column: the amount lives in the group's settings JSON and the "personal link"
marker is the link name prefix, so there is no migration.

Kill switch: set INVITE_XP_ENABLED=0 on the backend service. Joins are still recorded and links still work;
only the XP is skipped. See REVERT.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

REF_PREFIX = "Invite by "
MAX_XP = 1000


def enabled() -> bool:
    return os.environ.get("INVITE_XP_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def xp_per_invite(settings) -> int:
    """The group's configured XP per invite, clamped to 0..MAX_XP (0 = off, also for junk values)."""
    inv = (settings or {}).get("invites") or {}
    if not isinstance(inv, dict):
        return 0
    try:
        value = int(inv.get("xp_per_invite", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_XP, value))


def personal_link_name(display_name) -> str:
    """Telegram caps an invite link name at 32 characters; the prefix always survives the cut."""
    clean = " ".join(str(display_name or "").split()) or "member"
    return (REF_PREFIX + clean)[:32]


def is_personal_link(name, created_by_telegram_id) -> bool:
    return bool(created_by_telegram_id) and str(name or "").startswith(REF_PREFIX)


def decide_xp(*, xp: int, link_name, link_creator_id, joiner_id, joiner_is_bot: bool, already_counted: bool) -> int:
    """XP to award the inviter for this join (0 = none). Pure: no database, no Telegram."""
    if xp <= 0 or not enabled():
        return 0
    if not is_personal_link(link_name, link_creator_id):
        return 0
    if joiner_is_bot or already_counted:
        return 0
    if str(link_creator_id) == str(joiner_id):
        return 0
    return int(xp)


@dataclass
class JoinResult:
    link_id: int
    inviter_id: Optional[str]
    inviter_username: Optional[str]
    xp: int            # 0 when nothing is owed


# ── database helpers (call inside an app context) ─────────────────────────────────────────────

def _group_links(group_filter: dict):
    from .models import InviteLink
    return InviteLink.query.filter_by(**group_filter)


def get_personal_link(group_filter: dict, user_id):
    """The member's existing personal link in this group, if any."""
    from .models import InviteLink
    return (
        _group_links(group_filter)
        .filter(InviteLink.created_by_telegram_id == str(user_id), InviteLink.is_active.is_(True),
                InviteLink.name.like(REF_PREFIX + "%"))
        .order_by(InviteLink.id.asc())
        .first()
    )


def save_personal_link(group_filter: dict, user_id, username, name: str, url: str):
    from .models import InviteLink, db
    link = InviteLink(name=name, telegram_invite_link=url, created_by_telegram_id=str(user_id),
                      created_by_username=username, **group_filter)
    db.session.add(link)
    db.session.commit()
    return link


def joined_before(group_filter: dict, user_id) -> bool:
    """Has this person already been counted through any invite link of this group?"""
    from .models import InviteLink, InviteLinkJoin
    return (
        InviteLinkJoin.query.join(InviteLink, InviteLink.id == InviteLinkJoin.invite_link_id)
        .filter(InviteLinkJoin.joined_user_id == str(user_id))
        .filter(*[getattr(InviteLink, k) == v for k, v in group_filter.items()])
        .first()
        is not None
    )


def record_join(group_filter: dict, url: str, joiner_id, joiner_username, joiner_is_bot: bool, settings) -> Optional[JoinResult]:
    """Record a join made through a stored invite link and work out the inviter's XP.

    Returns None when the URL is not one of this group's active stored links. The join row and the link's
    use counter are written exactly as before; the XP decision is made BEFORE the new row is added so the
    "already counted" check sees only earlier joins.
    """
    from .models import InviteLink, InviteLinkJoin, db
    link = _group_links(group_filter).filter_by(telegram_invite_link=url, is_active=True).first()
    if not link:
        return None
    already = joined_before(group_filter, joiner_id)
    xp = decide_xp(
        xp=xp_per_invite(settings), link_name=link.name, link_creator_id=link.created_by_telegram_id,
        joiner_id=joiner_id, joiner_is_bot=joiner_is_bot, already_counted=already,
    )
    db.session.add(InviteLinkJoin(
        invite_link_id=link.id, joined_user_id=str(joiner_id), joined_username=joiner_username,
    ))
    link.uses_count = (link.uses_count or 0) + 1
    db.session.commit()
    return JoinResult(link_id=link.id, inviter_id=link.created_by_telegram_id,
                      inviter_username=link.created_by_username, xp=xp)
