"""Level -> role rewards that follow the member's level in EVERY XP path.

Before this, a reward role was only granted at the moment of a message or voice
level-up. XP that arrives any other way (campaign rewards approved from the web
dashboard, invite and boost bonuses) never produced the role, and neither did a
reward added to the ladder AFTER members had already reached that level.

This module holds the pure/DB parts of a small sweep that the bot runs every few
minutes (bot_core.level_role_loop):

  * incremental: members whose row changed since the last sweep and whose level
    reaches a reward;
  * full resync: when the ladder is edited (leveling2.roles_resync_at is set by the
    API), every member at or above the lowest reward is checked once, in pages.

It only ever GRANTS roles the ladder says the member has reached. It never removes
a role (a level drop from a moderation penalty keeps the roles already earned), so
it cannot take away a role an admin gave by hand.
"""
from __future__ import annotations

from models import Member

PAGE = 100


def valid_rewards(rewards) -> list[tuple[int, int]]:
    """[(level, role_id)] from the saved ladder, ignoring malformed rows."""
    out = []
    for r in rewards or []:
        try:
            lvl, rid = int(r.get("level")), int(r.get("role_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        if lvl >= 1 and rid > 0:
            out.append((lvl, rid))
    return sorted(out)


def due_role_ids(level: int, rewards) -> list[int]:
    """Role ids a member at ``level`` should hold: every reward at or below it."""
    return [rid for lvl, rid in valid_rewards(rewards) if lvl <= int(level or 1)]


def min_reward_level(rewards):
    v = valid_rewards(rewards)
    return v[0][0] if v else None


def candidates(db, guild_id: int, rewards, *, since=None, after_user_id: int = 0, limit: int = PAGE):
    """[(user_id, level)] of members who may be missing a reward role.

    since=None -> everyone at/above the lowest reward (used by a full resync);
    otherwise only rows updated at or after ``since``. Ordered by user id so a
    resync can continue from a cursor (``after_user_id``)."""
    lowest = min_reward_level(rewards)
    if lowest is None:
        return []
    q = (db.query(Member.user_id, Member.level)
         .filter(Member.guild_id == guild_id, Member.level >= lowest, Member.user_id > after_user_id))
    if since is not None:
        q = q.filter(Member.updated_at >= since)
    return [(int(u), int(lv or 1)) for u, lv in q.order_by(Member.user_id).limit(limit).all()]
