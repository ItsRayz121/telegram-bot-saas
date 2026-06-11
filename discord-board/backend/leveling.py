"""XP / leveling engine for Guildizer.

Copied math from the Telegizer LevelSystem: 100 XP per level, message XP with a
per-user cooldown, optional level-up announcement. DB writes take a live session;
no discord.py here, so it unit-tests standalone. The bot performs the announce.
"""
from __future__ import annotations

from datetime import datetime

from models import Member, XpEvent

DEFAULT_LEVELUP = "🎉 {user} reached **level {level}**!"


def level_from_xp(xp: int) -> int:
    """The level corresponding to a total XP value."""
    return max(1, (xp or 0) // 100 + 1)


def xp_for_level(level: int) -> int:
    """XP threshold required to reach `level`."""
    return max(0, (level - 1) * 100)


def get_or_create_member(db, guild_id: int, user_id: int, username: str | None = None) -> Member:
    m = db.get(Member, {"guild_id": guild_id, "user_id": user_id})
    if m is None:
        m = Member(guild_id=guild_id, user_id=user_id, username=username, xp=0, level=1)
        db.add(m)
        # Flush so a follow-up get() in the same (autoflush-off) session finds it
        # rather than creating a duplicate primary key.
        db.flush()
    elif username and m.username != username:
        m.username = username
    return m


def _apply_xp(db, member: Member, amount: int, reason: str):
    """Add XP to an already-resolved member, recompute level, log the ledger row.
    Negative amounts (penalties) floor at 0 XP. Returns (leveled_up, new_level)."""
    old_level = member.level or 1
    member.xp = max(0, (member.xp or 0) + int(amount))
    member.level = level_from_xp(member.xp)
    member.updated_at = datetime.utcnow()
    db.add(XpEvent(
        guild_id=member.guild_id, user_id=member.user_id,
        amount=int(amount), reason=reason[:64],
    ))
    return (member.level > old_level), member.level


def add_xp(db, guild_id: int, user_id: int, amount: int, username=None, reason="manual"):
    """Grant XP to a member (resolved once). Returns (member, leveled_up, new_level)."""
    m = get_or_create_member(db, guild_id, user_id, username)
    leveled_up, new_level = _apply_xp(db, m, amount, reason)
    return m, leveled_up, new_level


def award_message_xp(db, guild_id: int, user_id: int, username, cfg: dict):
    """Award message XP if the per-user cooldown has elapsed.
    Returns (leveled_up, new_level) or None if skipped. Caller commits."""
    amount = int(cfg.get("xp_per_message", 10) or 0)
    if amount <= 0:
        return None
    cooldown = int(cfg.get("xp_cooldown_seconds", 60) or 0)

    m = get_or_create_member(db, guild_id, user_id, username)
    now = datetime.utcnow()
    if m.last_xp_at and (now - m.last_xp_at).total_seconds() < cooldown:
        m.messages = (m.messages or 0) + 1   # still count the message
        return None

    m.last_xp_at = now
    m.messages = (m.messages or 0) + 1
    leveled_up, new_level = _apply_xp(db, m, amount, reason="message")
    return (leveled_up, new_level)


def apply_penalty(db, guild_id: int, user_id: int, username, kind: str) -> int:
    """Deduct the configured moderation XP penalty (leveling2.penalty_<kind>,
    kind in warn/timeout/kick/ban). Returns the amount removed (0 = disabled or
    leveling off). Caller commits."""
    import settings as settings_mod
    from models import GuildSettings

    row = db.get(GuildSettings, guild_id)
    if row is None or not row.levels_enabled:
        return 0
    l2 = {**settings_mod.LEVELING2_DEFAULTS, **((row.extra or {}).get("leveling2") or {})}
    amount = int(l2.get(f"penalty_{kind}") or 0)
    if amount <= 0:
        return 0
    add_xp(db, guild_id, user_id, -amount, username, reason=f"penalty_{kind}")
    return amount


def top_members(db, guild_id: int, limit: int = 10):
    return (
        db.query(Member)
        .filter(Member.guild_id == guild_id)
        .order_by(Member.xp.desc())
        .limit(limit)
        .all()
    )


def rank_of(db, guild_id: int, user_id: int) -> int:
    """1-based rank of a user by XP within the guild (0 if no XP row)."""
    m = db.get(Member, {"guild_id": guild_id, "user_id": user_id})
    if m is None:
        return 0
    higher = (
        db.query(Member)
        .filter(Member.guild_id == guild_id, Member.xp > (m.xp or 0))
        .count()
    )
    return higher + 1


def render_levelup(template: str, *, mention: str, username: str, level: int) -> str:
    tpl = template or DEFAULT_LEVELUP
    return (
        tpl.replace("{user}", mention or username or "")
        .replace("{username}", username or "")
        .replace("{level}", str(level))
    )
