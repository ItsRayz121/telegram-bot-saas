"""Boost tracking: thank-you post + reward role + XP on server boost. Both lineages.

Config lives in GuildSettings.extra["boosts"] (self-heals, no migration). The
bot watches on_member_update premium_since transitions: a new boost posts the
thank-you message ({user}/{server}/{count} placeholders), grants the configured
extra reward role, and awards a one-time XP bonus through the normal leveling
ledger (reason "boost"). When the boost lapses the reward role is removed.

Discord's native booster role is untouched — the reward role here is an extra,
and (like self-roles) it may never carry moderation/management permissions, so
a misconfigured reward can't become a privilege-escalation path.
"""
from __future__ import annotations

import asyncio
import logging

import discord

import governor
import leveling
import self_roles
import settings as settings_mod
from database import SessionLocal
from models import GuildSettings

log = logging.getLogger("guildizer.boosts")


# ── storage helpers (sync — call via to_thread) ────────────────────────────────
def snapshot(guild_id: int) -> dict | None:
    """Boosts config merged over defaults, plus whether leveling is on."""
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return None
        return {**settings_mod.BOOSTS_DEFAULTS,
                **((row.extra or {}).get("boosts") or {}),
                "levels_enabled": bool(row.levels_enabled)}
    finally:
        db.close()
        SessionLocal.remove()


def _award_boost_xp(guild_id: int, user_id: int, username: str, amount: int) -> None:
    db = SessionLocal()
    try:
        leveling.add_xp(db, guild_id, user_id, amount, username, reason="boost")
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("boost XP award failed for guild %s user %s", guild_id, user_id)
    finally:
        db.close()
        SessionLocal.remove()


def _render(template: str, member: discord.Member, count: int) -> str:
    return (template or "")[:1500] \
        .replace("{user}", member.mention) \
        .replace("{server}", member.guild.name) \
        .replace("{count}", str(count))


# ── event handling (called from bot_core.on_member_update) ─────────────────────
async def handle_member_update(client, before: discord.Member,
                               after: discord.Member) -> None:
    """React to boost start/stop. Never raises."""
    try:
        boosted = before.premium_since is None and after.premium_since is not None
        unboosted = before.premium_since is not None and after.premium_since is None
        if not (boosted or unboosted):
            return
        cfg = await asyncio.to_thread(snapshot, after.guild.id)
        if not cfg or not cfg.get("enabled"):
            return
        if boosted:
            await _on_boost(after, cfg)
        else:
            await _on_unboost(after, cfg)
    except Exception:  # noqa: BLE001
        log.exception("boost handling failed for guild %s", after.guild.id)


def _reward_role(guild: discord.Guild, cfg: dict) -> discord.Role | None:
    rid = cfg.get("role_id")
    if not (rid and str(rid).isdigit()):
        return None
    role = guild.get_role(int(rid))
    if role is None:
        return None
    if not self_roles._role_is_safe(role):
        log.warning("boost reward role %s in guild %s carries dangerous "
                    "permissions — skipped", role.id, guild.id)
        return None
    return role


async def _on_boost(member: discord.Member, cfg: dict) -> None:
    guild = member.guild

    # 1. thank-you message
    channel = None
    ch = cfg.get("channel_id")
    if ch and str(ch).isdigit():
        channel = guild.get_channel(int(ch))
    if channel is None:
        channel = guild.system_channel
    if channel is not None and hasattr(channel, "send"):
        text = _render(cfg.get("message") or "", member,
                       guild.premium_subscription_count or 0)
        if text.strip():
            await governor.safe(channel.send(text), what="boost thank-you")

    # 2. extra reward role
    role = _reward_role(guild, cfg)
    if role is not None and role not in member.roles:
        await governor.safe(member.add_roles(role, reason="Guildizer: server boost"),
                            what="boost reward role")

    # 3. XP bonus through the normal ledger
    xp = int(cfg.get("xp_bonus") or 0)
    if xp > 0 and cfg.get("levels_enabled"):
        await asyncio.to_thread(_award_boost_xp, guild.id, member.id,
                                str(member), xp)


async def _on_unboost(member: discord.Member, cfg: dict) -> None:
    role = _reward_role(member.guild, cfg)
    if role is not None and role in member.roles:
        await governor.safe(
            member.remove_roles(role, reason="Guildizer: boost ended"),
            what="boost reward role removal",
        )
