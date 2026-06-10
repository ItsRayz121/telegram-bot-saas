"""Single source of truth for "which groups is a custom bot connected to".

A custom bot can be linked to its groups through TWO historically-separate
storage paths:

  • New lineage — ``TelegramGroup.linked_bot_id`` FK → ``custom_bots.id`` with
    ``linked_via_bot_type='custom'`` (official-bot-style group management run by a
    user-supplied token).
  • Legacy lineage — the ``bots`` + ``groups`` tables, where a ``Bot`` row is
    matched to its ``CustomBot`` twin by ``bot_username`` and owns ``Group`` rows
    via ``Group.bot_id``.

The user dashboard (``routes/custom_bots.list_custom_bots``) already falls back to
the legacy path by username, but the admin custom-bot detail page only ever read
``TelegramGroup.linked_bot_id`` — so a bot whose groups live only in the legacy
tables showed "No connected groups" in admin while the user dashboard showed them.

This module centralises the resolution so admin and user views read the same
source of truth and can never disagree again.
"""
from __future__ import annotations


def resolve_connected_groups(custom_bot) -> list[dict]:
    """Return the de-duplicated set of groups a custom bot manages.

    Each entry: ``{telegram_group_id, title, member_count, bot_status, source}``
    where ``source`` is ``'telegram_groups'`` (new lineage) or ``'legacy'``.
    De-duplicated by ``telegram_group_id`` — the new lineage wins when a group is
    present in both (it carries the live-synced member_count).
    """
    from .models import TelegramGroup, Bot, Group

    by_tgid: dict[str, dict] = {}

    # New lineage — authoritative member_count (member_sync reconciles it live).
    tg_rows = TelegramGroup.query.filter_by(linked_bot_id=custom_bot.id).all()
    for g in tg_rows:
        by_tgid[str(g.telegram_group_id)] = {
            "telegram_group_id": g.telegram_group_id,
            "title": g.title,
            "member_count": g.member_count or 0,
            "bot_status": g.bot_status,
            "member_count_synced_at": (
                g.member_count_synced_at.isoformat() if getattr(g, "member_count_synced_at", None) else None
            ),
            "source": "telegram_groups",
        }

    # Legacy lineage — match the CustomBot to its Bot twin by username, then read
    # its Group rows. Only add groups not already surfaced by the new lineage.
    uname = (custom_bot.bot_username or "").lstrip("@")
    if uname:
        legacy_bots = Bot.query.filter_by(bot_username=uname).all()
        for lb in legacy_bots:
            for grp in Group.query.filter_by(bot_id=lb.id).all():
                tgid = str(grp.telegram_group_id)
                if tgid in by_tgid:
                    continue
                by_tgid[tgid] = {
                    "telegram_group_id": grp.telegram_group_id,
                    "title": grp.group_name,
                    "member_count": grp.telegram_member_count or 0,
                    "bot_status": "active" if lb.is_active else "inactive",
                    "member_count_synced_at": None,
                    "source": "legacy",
                }

    return list(by_tgid.values())


def connected_groups_summary(custom_bot) -> dict:
    """Convenience wrapper: groups list + counts for a custom bot."""
    groups = resolve_connected_groups(custom_bot)
    return {
        "connected_groups": groups,
        "groups_count": len(groups),
        "members_managed": sum(g["member_count"] for g in groups),
    }
