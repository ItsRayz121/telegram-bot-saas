"""Shared role-safety policy: which Discord roles may be handed out automatically
(self-roles, level rewards, applications) without becoming a privilege path.

A role is *privileged* when it carries any moderation/management permission, or is
@everyone / integration-managed. Judged from the role's real permission bitfield,
never its name. Pure functions + one DB helper, so API and bot share one rule.
"""
from __future__ import annotations

from models import Role

# Same set the bot enforces at click time (self_roles._DANGEROUS_PERMS), as bits.
DANGEROUS_BITS = {
    "kick_members": 1 << 1, "ban_members": 1 << 2, "administrator": 1 << 3,
    "manage_channels": 1 << 4, "manage_guild": 1 << 5, "manage_messages": 1 << 13,
    "mention_everyone": 1 << 17, "manage_roles": 1 << 28, "manage_webhooks": 1 << 29,
    "moderate_members": 1 << 40,
}


def dangerous_perms(permissions) -> list[str]:
    try:
        bits = int(permissions or 0)
    except (TypeError, ValueError):
        return list(DANGEROUS_BITS)       # unreadable → treat as unsafe
    return [n for n, b in DANGEROUS_BITS.items() if bits & b]


def role_problem(role: Role | None, guild_id: int) -> str | None:
    """Why this role can't be auto-assigned, or None when it is safe. Unknown roles
    (not synced / other guild) are rejected too — never assume."""
    if role is None or role.guild_id != guild_id:
        return "unknown_role"
    if role.id == guild_id or (role.name or "") == "@everyone":
        return "everyone_role"
    if role.managed:
        return "managed_role"
    if dangerous_perms(role.permissions):
        return "privileged_role"
    return None


def check_roles(db, guild_id: int, role_ids) -> dict[str, str]:
    """{role_id: problem} for every id that is NOT safely assignable."""
    ids = [int(r) for r in role_ids if str(r).isdigit()]
    found = {r.id: r for r in db.query(Role).filter(Role.guild_id == guild_id, Role.id.in_(ids)).all()} if ids else {}
    out = {}
    for rid in ids:
        p = role_problem(found.get(rid), guild_id)
        # A role not synced yet is not blocked here (the bot re-checks the live role
        # at grant time); only roles KNOWN to be unsafe are refused at save time.
        if p and p != "unknown_role":
            out[str(rid)] = p
    return out


def audit_grant(guild_id: int, user_id: int, username, action: str, detail: str) -> None:
    """Sync, best-effort audit row for an automatic role grant (action: level_grant / self_grant).
    Never raises - an audit hiccup must not undo or block the grant itself."""
    from database import SessionLocal
    import protection
    db = SessionLocal()
    try:
        protection.log_event(db, guild_id, "role_policy", action, user_id=user_id,
                             username=username, detail=detail)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
        SessionLocal.remove()


_ext_budget: dict = {}      # guild_id -> (minute, count): a mass role change can't flood the audit log
EXTERNAL_PER_MINUTE = 60
OWN_WINDOW_SECONDS = 30


def audit_external(guild_id: int, user_id: int, username, added: list[str], removed: list[str]) -> bool:
    """Sync. Record a role change seen on the Discord gateway as 'Changed in Discord', unless
    Guildizer itself (bot or dashboard) recorded a role event for this member in the last 30 s -
    that is the same change, already in the history with its real source. Returns True if logged."""
    import time
    from datetime import datetime, timedelta
    from database import SessionLocal
    import protection
    from models import ProtectionEvent
    minute = int(time.time() // 60)
    seen_minute, count = _ext_budget.get(guild_id, (minute, 0))
    if seen_minute != minute:
        count = 0
    if count >= EXTERNAL_PER_MINUTE:
        return False
    _ext_budget[guild_id] = (minute, count + 1)
    db = SessionLocal()
    try:
        recent = (db.query(ProtectionEvent.id)
                  .filter(ProtectionEvent.guild_id == guild_id, ProtectionEvent.category == "role_policy",
                          ProtectionEvent.user_id == user_id,
                          ProtectionEvent.created_at >= datetime.utcnow() - timedelta(seconds=OWN_WINDOW_SECONDS))
                  .first())
        if recent is not None:
            return False
        parts = []
        if added:
            parts.append("Added " + ", ".join(added))
        if removed:
            parts.append("Removed " + ", ".join(removed))
        protection.log_event(db, guild_id, "role_policy", "discord_change", user_id=user_id,
                             username=username, detail="; ".join(parts) + " (changed in Discord)")
        db.commit()
        return True
    except Exception:  # noqa: BLE001
        db.rollback()
        return False
    finally:
        db.close()
        SessionLocal.remove()
