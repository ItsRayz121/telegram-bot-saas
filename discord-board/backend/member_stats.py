"""Shared member-stat helpers for the CRM members list and the XP leaderboard.

Keeps the Telegizer-parity columns (period XP, warnings count, rank role) in one
place so /members and /leaderboard agree. Pure functions over a session.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func

from models import MemberWarning, Role, XpEvent

# Dashboard period chips → lookback in days (None = all time).
PERIOD_DAYS = {"1d": 1, "today": 1, "7d": 7, "30d": 30, "all": None}


def period_since(period: str | None):
    days = PERIOD_DAYS.get((period or "all"), None)
    if not days:
        return None
    return datetime.utcnow() - timedelta(days=days)


def xp_by_user(db, guild_id: int, since) -> dict[int, int]:
    """{user_id: summed XP} from the append-only ledger, optionally since a time."""
    q = db.query(XpEvent.user_id, func.coalesce(func.sum(XpEvent.amount), 0)) \
        .filter(XpEvent.guild_id == guild_id)
    if since is not None:
        q = q.filter(XpEvent.created_at >= since)
    return {uid: int(total or 0) for uid, total in q.group_by(XpEvent.user_id).all()}


def warnings_by_user(db, guild_id: int) -> dict[int, int]:
    """{user_id: active warning count}."""
    rows = db.query(MemberWarning.user_id, func.count(MemberWarning.id)) \
        .filter(MemberWarning.guild_id == guild_id) \
        .group_by(MemberWarning.user_id).all()
    return {uid: int(n or 0) for uid, n in rows}


def role_label_map(db, guild_id: int, role_rewards: list[dict]) -> dict[int, str]:
    """Map a member level → the name of the highest level→role reward they qualify
    for, so the table can show a "rank role" column (Telegizer parity). Returns
    {level: role_name}; callers look up by the member's level."""
    if not role_rewards:
        return {}
    # role_id → name (one query)
    role_ids = [int(r["role_id"]) for r in role_rewards if str(r.get("role_id") or "").isdigit()]
    if not role_ids:
        return {}
    names = {r.id: r.name for r in db.query(Role).filter(Role.guild_id == guild_id, Role.id.in_(role_ids)).all()}
    # Sorted ascending so the last match wins (highest qualifying level).
    rewards = sorted(
        [(int(r["level"]), int(r["role_id"])) for r in role_rewards if str(r.get("role_id") or "").isdigit()],
        key=lambda t: t[0],
    )
    # Precompute the qualifying role name for any level by walking thresholds.
    out: dict[int, str] = {}
    max_level = max((lvl for lvl, _ in rewards), default=0)
    for level in range(1, max_level + 1):
        name = None
        for lvl, rid in rewards:
            if lvl <= level and rid in names:
                name = names[rid]
        if name:
            out[level] = name
    return out
