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


def custom_bot_labels_for_tgids(tgids) -> dict:
    """Reverse map: ``{telegram_group_id: '@bot_username'}`` for groups managed by
    a custom bot via the **legacy** ``bots``/``groups`` lineage.

    The new lineage (``TelegramGroup.linked_bot_id``) is resolved directly by
    callers, so this fills the gap where a ``telegram_groups`` row was never
    stamped with ``linked_bot_id`` (legacy-only bot, or a group linked through the
    official bot before being switched to a custom bot). Without it, admin
    drill-downs mis-attribute such groups to "Telegizer (official)".

    Targeted + best-effort: only queries the requested tgids and never raises.
    """
    want = {str(t) for t in (tgids or []) if t is not None}
    if not want:
        return {}
    try:
        from .models import Group, Bot, CustomBot

        grp_rows = Group.query.filter(Group.telegram_group_id.in_(want)).all()
        if not grp_rows:
            return {}
        bot_ids = {g.bot_id for g in grp_rows if g.bot_id}
        bots = {b.id: b for b in Bot.query.filter(Bot.id.in_(bot_ids)).all()} if bot_ids else {}
        # Resolve each legacy Bot to its CustomBot twin by username (case-insensitive).
        unames = {(b.bot_username or "").lstrip("@").lower() for b in bots.values() if b.bot_username}
        cb_by_uname = {}
        if unames:
            for cb in CustomBot.query.all():
                u = (cb.bot_username or "").lstrip("@").lower()
                if u in unames:
                    cb_by_uname[u] = cb

        out = {}
        for g in grp_rows:
            b = bots.get(g.bot_id)
            if not b or not b.bot_username:
                continue
            uname = b.bot_username.lstrip("@")
            cb = cb_by_uname.get(uname.lower())
            label = f"@{cb.bot_username.lstrip('@')}" if cb and cb.bot_username else f"@{uname}"
            out.setdefault(str(g.telegram_group_id), label)
        return out
    except Exception:
        return {}


def connected_groups_summary(custom_bot) -> dict:
    """Convenience wrapper: groups list + counts for a custom bot."""
    groups = resolve_connected_groups(custom_bot)
    return {
        "connected_groups": groups,
        "groups_count": len(groups),
        "members_managed": sum(g["member_count"] for g in groups),
    }
