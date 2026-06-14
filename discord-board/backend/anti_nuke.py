"""Anti-nuke guard: stop a compromised admin (or rogue bot) from wrecking the
server. Both lineages.

Watches destructive admin actions — bans, kicks, channel deletions, role
deletions — attributes each to its executor via the audit log, and counts them
in per-executor sliding windows. When one executor crosses a threshold inside
the window, the guard responds (strip elevated roles / ban / alert only) and
alerts admins. The guild owner, this bot itself, and whitelisted user ids are
exempt.

Detection state is per-process (same trade-off as raid_guard): a restart
resets the windows, which only means a nuke must re-cross the threshold.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

import discord

import admin_alerts
import governor
import protection
from database import SessionLocal

log = logging.getLogger("guildizer.antinuke")

# kind -> (audit log action, threshold key)
KINDS = {
    "ban": (discord.AuditLogAction.ban, "max_bans"),
    "kick": (discord.AuditLogAction.kick, "max_kicks"),
    "channel_delete": (discord.AuditLogAction.channel_delete, "max_channel_deletes"),
    "role_delete": (discord.AuditLogAction.role_delete, "max_role_deletes"),
}

_AUDIT_MAX_AGE_SECONDS = 120   # only attribute to a fresh audit entry
_TRIP_COOLDOWN_SECONDS = 600   # one response per executor per 10 minutes

_events: dict[tuple[int, int, str], deque] = {}   # (gid, uid, kind) -> deque[monotonic ts]
_tripped: dict[tuple[int, int], float] = {}        # (gid, uid) -> monotonic ts


def note(guild_id: int, executor_id: int, kind: str, cfg: dict) -> bool:
    """Record one destructive action. Returns True only on the call that
    crosses the executor's threshold (so the caller responds exactly once)."""
    now = time.monotonic()
    trip_at = _tripped.get((guild_id, executor_id), 0.0)
    if now - trip_at < _TRIP_COOLDOWN_SECONDS:
        return False
    window = max(10, int(cfg.get("window_seconds") or 300))
    limit = max(2, int(cfg.get(KINDS[kind][1]) or 0) or 999)
    dq = _events.setdefault((guild_id, executor_id, kind), deque())
    dq.append(now)
    while dq and dq[0] < now - window:
        dq.popleft()
    if len(dq) >= limit:
        _tripped[(guild_id, executor_id)] = now
        dq.clear()
        return True
    return False


def _exempt(client, guild: discord.Guild, executor_id: int, cfg: dict) -> bool:
    if client.user and executor_id == client.user.id:
        return True
    if executor_id == guild.owner_id:
        return True
    return str(executor_id) in [str(u) for u in (cfg.get("whitelist_user_ids") or [])]


async def find_executor(guild: discord.Guild, kind: str, target_id: int) -> int | None:
    """The user id behind a fresh destructive action, from the audit log.
    None when the entry is stale/missing or we lack View Audit Log."""
    action = KINDS[kind][0]
    try:
        async for entry in guild.audit_logs(limit=8, action=action):
            age = (discord.utils.utcnow() - entry.created_at).total_seconds()
            if age > _AUDIT_MAX_AGE_SECONDS:
                break   # entries come newest-first; everything after is older
            if entry.target is not None and entry.target.id == target_id and entry.user:
                return entry.user.id
    except discord.Forbidden:
        log.warning("No View Audit Log permission in guild %s", guild.id)
    except discord.HTTPException as exc:
        log.warning("Audit log fetch failed for guild %s: %s", guild.id, exc)
    return None


def _log_event(guild_id: int, action: str, user_id: int, username, detail: str) -> None:
    db = SessionLocal()
    try:
        protection.log_event(db, guild_id, "anti_nuke", action,
                             user_id=user_id, username=username, detail=detail)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("anti-nuke event log failed for guild %s", guild_id)
    finally:
        db.close()
        SessionLocal.remove()


_ELEVATED_PERMS = (
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "manage_webhooks", "ban_members", "kick_members", "moderate_members",
)

_KIND_LABEL = {
    "ban": "mass bans", "kick": "mass kicks",
    "channel_delete": "mass channel deletions", "role_delete": "mass role deletions",
}


async def respond(client, guild: discord.Guild, executor_id: int,
                  kind: str, cfg: dict, full_cfg: dict | None = None) -> None:
    """Threshold crossed: contain the executor per the configured action and
    alert admins."""
    member = guild.get_member(executor_id)
    name = str(member) if member else str(executor_id)
    action = cfg.get("action") or "strip_roles"
    taken = "alerted"

    if action == "ban":
        if await governor.safe(
            guild.ban(discord.Object(id=executor_id),
                      reason=f"Guildizer anti-nuke: {_KIND_LABEL[kind]}",
                      delete_message_days=0),
            what="anti-nuke ban",
        ):
            taken = "banned"
    elif action == "strip_roles" and member is not None:
        elevated = [r for r in member.roles
                    if not r.is_default()
                    and any(getattr(r.permissions, p, False) for p in _ELEVATED_PERMS)]
        if elevated and await governor.safe(
            member.remove_roles(*elevated, reason=f"Guildizer anti-nuke: {_KIND_LABEL[kind]}"),
            what="anti-nuke role strip",
        ):
            taken = "stripped_roles"

    detail = f"{_KIND_LABEL[kind]} threshold crossed; response: {taken}"
    await asyncio.to_thread(_log_event, guild.id, taken, executor_id,
                            str(member) if member else None, detail)

    await admin_alerts.post(guild, full_cfg or {}, "nuke",
                            f"Anti-nuke triggered by **{name}** (`{executor_id}`) — "
                            f"{_KIND_LABEL[kind]}; response: {taken}.")

    ch_id = cfg.get("alert_channel_id")
    channel = guild.get_channel(int(ch_id)) if ch_id else guild.system_channel
    if channel is None or not hasattr(channel, "send"):
        return
    verb = {
        "banned": "I **banned** them",
        "stripped_roles": "I **removed their elevated roles**",
        "alerted": "No automatic action is configured — review them now",
    }[taken]
    await governor.safe(channel.send(
        f"🧨 **Anti-nuke triggered** — **{name}** (`{executor_id}`) performed "
        f"{_KIND_LABEL[kind]} within the detection window. {verb}. "
        "Review the audit log and the dashboard's Protection Activity feed."
    ), what="anti-nuke alert")


async def handle(client, guild: discord.Guild, kind: str, target_id: int) -> None:
    """One destructive event happened: attribute it, count it, respond on trip.
    Caller has already checked serves()."""
    cfg_full = await asyncio.to_thread(_load_cfg, guild.id)
    cfg = (cfg_full or {}).get("anti_nuke") or {}
    if not cfg.get("enabled"):
        return
    executor_id = await find_executor(guild, kind, target_id)
    if executor_id is None or _exempt(client, guild, executor_id, cfg):
        return
    if note(guild.id, executor_id, kind, cfg):
        await respond(client, guild, executor_id, kind, cfg, full_cfg=cfg_full)


def _load_cfg(guild_id: int) -> dict | None:
    db = SessionLocal()
    try:
        return protection.load_snapshot(db, guild_id)
    finally:
        db.close()
        SessionLocal.remove()
