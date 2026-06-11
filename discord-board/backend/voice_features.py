"""Voice features: join-to-create temp voice rooms + voice-minutes XP. Both lineages.

Join-to-create: members joining the configured lobby voice channel get their own
temporary room (named from a template, same category, optional user limit) and
are moved into it. The creator can manage their room. Rooms are registered in
GuildSettings.extra["voice_temp"] so empty ones are still cleaned up after a
restart; deletion happens when the last member leaves (plus a periodic sweep).

Voice XP: the bot's 5-minute voice loop awards leveling XP to members actively
sitting in voice — skipping the AFK channel, deafened members, and rooms below
the configured minimum of humans (no XP for idling alone). Awards ride the
normal leveling ledger (reason "voice") and bump Member.voice_minutes.
"""
from __future__ import annotations

import asyncio
import logging
import time

import discord

import governor
import leveling
from database import SessionLocal
from models import GuildSettings

log = logging.getLogger("guildizer.voice")

_J2C_COOLDOWN_SECONDS = 15
_j2c_last: dict[tuple[int, int], float] = {}   # (gid, uid) -> monotonic ts


# ── temp-room registry (persisted so restarts don't orphan empty rooms) ───────
def _registry(row: GuildSettings) -> list[str]:
    return [str(c) for c in ((row.extra or {}).get("voice_temp") or [])]


def _write_registry(db, guild_id: int, ids: list[str]) -> None:
    row = db.get(GuildSettings, guild_id)
    if row is None:
        return
    extra = dict(row.extra or {})
    extra["voice_temp"] = ids[:100]
    row.extra = extra


def temp_ids(guild_id: int) -> set[int]:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        return {int(c) for c in _registry(row)} if row else set()
    finally:
        db.close()
        SessionLocal.remove()


def register_temp(guild_id: int, channel_id: int) -> None:
    _mutate_registry(guild_id, add=channel_id)


def unregister_temp(guild_id: int, channel_id: int) -> None:
    _mutate_registry(guild_id, remove=channel_id)


def _mutate_registry(guild_id: int, *, add: int | None = None,
                     remove: int | None = None) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return
        ids = _registry(row)
        if add is not None and str(add) not in ids:
            ids.append(str(add))
        if remove is not None:
            ids = [c for c in ids if c != str(remove)]
        _write_registry(db, guild_id, ids)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("voice temp registry update failed for guild %s", guild_id)
    finally:
        db.close()
        SessionLocal.remove()


# ── join-to-create ────────────────────────────────────────────────────────────
def _room_name(template: str, member: discord.Member) -> str:
    name = (template or "{user}'s room").replace("{user}", member.display_name)
    return name[:100] or "voice room"


async def handle_voice_state(client, member: discord.Member,
                             before: discord.VoiceState, after: discord.VoiceState,
                             cfg: dict) -> None:
    """Called from on_voice_state_update (serves() already checked)."""
    guild = member.guild

    # leaving a temp room: delete it once it's empty
    if before.channel is not None and (after.channel is None
                                       or after.channel.id != before.channel.id):
        registered = await _to_thread(temp_ids, guild.id)
        if before.channel.id in registered and not before.channel.members:
            if await governor.safe(
                before.channel.delete(reason="Guildizer: temp voice room empty"),
                what="temp room delete",
            ):
                await _to_thread(unregister_temp, guild.id, before.channel.id)

    # joining the lobby: spin up a personal room
    if not cfg.get("j2c_enabled") or member.bot or after.channel is None:
        return
    lobby_id = cfg.get("j2c_lobby_channel_id")
    if not lobby_id or after.channel.id != int(lobby_id):
        return
    key = (guild.id, member.id)
    now = time.monotonic()
    if now - _j2c_last.get(key, 0.0) < _J2C_COOLDOWN_SECONDS:
        return
    _j2c_last[key] = now

    limit = max(0, min(99, int(cfg.get("j2c_user_limit") or 0)))
    overwrites = {member: discord.PermissionOverwrite(manage_channels=True,
                                                      move_members=True)}
    kwargs = {"user_limit": limit} if limit else {}
    try:
        room = await guild.create_voice_channel(
            _room_name(cfg.get("j2c_name_template") or "", member),
            category=after.channel.category,
            overwrites=overwrites,
            reason=f"Guildizer join-to-create for {member}",
            **kwargs,
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("join-to-create failed in guild %s: %s", guild.id, exc)
        return
    await _to_thread(register_temp, guild.id, room.id)
    if not await governor.safe(member.move_to(room, reason="Guildizer join-to-create"),
                               what="move into temp room"):
        # member already left the lobby — don't leave an empty room behind
        if not room.members:
            await governor.safe(room.delete(reason="Guildizer: temp room unused"),
                                what="temp room rollback")
            await _to_thread(unregister_temp, guild.id, room.id)


async def sweep_empty_rooms(client, guild: discord.Guild) -> None:
    """Periodic safety net: drop empty/deleted temp rooms (e.g. after a restart)."""
    registered = await _to_thread(temp_ids, guild.id)
    for cid in registered:
        channel = guild.get_channel(cid)
        if channel is None:
            await _to_thread(unregister_temp, guild.id, cid)
        elif not channel.members:
            if await governor.safe(
                channel.delete(reason="Guildizer: temp voice room empty"),
                what="temp room sweep delete",
            ):
                await _to_thread(unregister_temp, guild.id, cid)


# ── voice XP (called from the bot's 5-minute voice loop) ──────────────────────
def eligible_members(guild: discord.Guild, cfg: dict) -> list[tuple[int, str, int]]:
    """(user_id, username, channel_id) for members who count this tick."""
    min_humans = max(1, int(cfg.get("min_humans") or 2))
    out: list[tuple[int, str, int]] = []
    for channel in guild.voice_channels:
        if guild.afk_channel is not None and channel.id == guild.afk_channel.id:
            continue
        humans = [m for m in channel.members if not m.bot]
        if len(humans) < min_humans:
            continue
        for m in humans:
            vs = m.voice
            if vs is None or vs.deaf or vs.self_deaf:
                continue
            out.append((m.id, str(m), channel.id))
    return out


def award_minutes(guild_id: int, members: list[tuple[int, str, int]],
                  amount: int, minutes: int) -> list[tuple[int, int, int]]:
    """Sync — call via to_thread. Grants `amount` XP + `minutes` voice-minutes to
    each member. Returns (user_id, new_level, channel_id) for level-ups."""
    ups: list[tuple[int, int, int]] = []
    db = SessionLocal()
    try:
        for uid, name, ch_id in members:
            m, leveled_up, new_level = leveling.add_xp(
                db, guild_id, uid, amount, name, reason="voice")
            m.voice_minutes = (m.voice_minutes or 0) + minutes
            if leveled_up:
                ups.append((uid, new_level, ch_id))
        db.commit()
        return ups
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("voice XP award failed for guild %s", guild_id)
        return []
    finally:
        db.close()
        SessionLocal.remove()


async def _to_thread(fn, *args):
    return await asyncio.to_thread(fn, *args)
