"""Tracked invites + referral attribution (Phase 14). Both lineages.

The serving bot caches each guild's invite uses; when a member joins, the
invite whose use-count increased identifies the inviter (the standard Discord
invite-tracker pattern). Attribution rows feed the referral leaderboard, and
inviters can earn XP per join (configurable, default off).

Needs the Manage Guild permission to list invites — degrades silently without.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import discord

import leveling
from database import SessionLocal
from models import GuildSettings, InviteJoin, InviteLink

log = logging.getLogger("guildizer.invites")

# in-memory cache: guild_id -> {code: (uses, inviter_id, inviter_name)}
_cache: dict[int, dict[str, tuple[int, int | None, str | None]]] = {}


async def refresh_guild(guild: discord.Guild) -> None:
    try:
        invites = await guild.invites()
    except (discord.Forbidden, discord.HTTPException):
        _cache.pop(guild.id, None)
        return
    _cache[guild.id] = {
        inv.code: (inv.uses or 0,
                   inv.inviter.id if inv.inviter else None,
                   str(inv.inviter) if inv.inviter else None)
        for inv in invites
    }


async def attribute_join(guild: discord.Guild) -> tuple[str, int | None, str | None] | None:
    """Compare cached vs current invite uses. Returns (code, inviter_id,
    inviter_name) for the invite that gained a use, or None. Refreshes cache."""
    before = _cache.get(guild.id)
    await refresh_guild(guild)
    after = _cache.get(guild.id)
    if before is None or after is None:
        return None
    for code, (uses, inviter_id, inviter_name) in after.items():
        prev = before.get(code, (0, inviter_id, inviter_name))[0]
        if uses > prev:
            return code, inviter_id, inviter_name
    return None


# --- sync DB helpers (call via to_thread) ---------------------------------------
def record_join(guild_id: int, code: str, inviter_id: int | None, inviter_name: str | None,
                joiner_id: int, joiner_name: str | None) -> int:
    """Store the attribution, bump the tracked link, award referral XP.
    Returns the XP awarded (0 if disabled/none)."""
    db = SessionLocal()
    try:
        db.add(InviteJoin(
            guild_id=guild_id, code=code, inviter_id=inviter_id,
            inviter_name=(inviter_name or "")[:120] or None,
            joiner_id=joiner_id, joiner_name=(joiner_name or "")[:120] or None,
        ))
        link = db.query(InviteLink).filter(InviteLink.code == code).one_or_none()
        if link is None:
            link = InviteLink(guild_id=guild_id, code=code, creator_id=inviter_id,
                              creator_name=(inviter_name or "")[:120] or None)
            db.add(link)
        link.uses = (link.uses or 0) + 1

        xp = 0
        if inviter_id:
            settings = db.get(GuildSettings, guild_id)
            ref_cfg = ((settings.extra or {}).get("referrals") or {}) if settings else {}
            xp = max(0, int(ref_cfg.get("xp_per_referral", 0) or 0))
            if xp > 0:
                leveling.add_xp(db, guild_id, inviter_id, xp, inviter_name,
                                reason=f"referral:{joiner_id}")
        db.commit()
        return xp
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("record_join failed for guild %s", guild_id)
        return 0
    finally:
        db.close()
        SessionLocal.remove()


def register_link(guild_id: int, code: str, creator_id: int, creator_name: str | None) -> None:
    db = SessionLocal()
    try:
        link = db.query(InviteLink).filter(InviteLink.code == code).one_or_none()
        if link is None:
            db.add(InviteLink(guild_id=guild_id, code=code, creator_id=creator_id,
                              creator_name=(creator_name or "")[:120] or None))
            db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def referral_counts(guild_id: int, user_id: int) -> int:
    db = SessionLocal()
    try:
        return (
            db.query(InviteJoin)
            .filter(InviteJoin.guild_id == guild_id, InviteJoin.inviter_id == user_id)
            .count()
        )
    finally:
        db.close()
        SessionLocal.remove()


# --- slash command ---------------------------------------------------------------
def attach_invite_command(client) -> None:
    from discord import app_commands  # local import keeps module import-light

    @client.tree.command(name="invitelink",
                         description="Get your personal tracked invite link for this server.")
    async def invitelink(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        channel = interaction.channel
        if not hasattr(channel, "create_invite"):
            await interaction.response.send_message("I can't create invites here.", ephemeral=True)
            return
        try:
            invite = await channel.create_invite(
                max_age=0, max_uses=0, unique=True,
                reason=f"Guildizer /invitelink for {interaction.user}",
            )
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message(
                "I couldn't create an invite — I need the Create Invite permission here.",
                ephemeral=True,
            )
            return
        await asyncio.to_thread(register_link, interaction.guild.id, invite.code,
                                interaction.user.id, str(interaction.user))
        await refresh_guild(interaction.guild)
        count = await asyncio.to_thread(referral_counts, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            f"🔗 Your personal invite: {invite.url}\n"
            f"Joins through your links are tracked — you've brought in **{count}** member(s) so far.",
            ephemeral=True,
        )
