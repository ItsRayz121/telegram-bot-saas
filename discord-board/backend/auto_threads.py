"""Thread auto-management: auto-create a discussion thread on new posts in
chosen channels, with a configurable auto-archive policy. Both lineages.

Config lives in GuildSettings.extra["auto_threads"] (self-heals, no migration):
enabled, channel_ids (explicit — never "all channels"), archive_minutes
(Discord allows 60/1440/4320/10080) and include_bots (thread bot/webhook posts
too, e.g. the bot's own scheduled announcements).

Called from on_message for every guild message, so the config is read through
a short TTL cache (starboard pattern) instead of hitting the DB per message.
"""
from __future__ import annotations

import asyncio
import logging
import time

import discord

import governor
import settings as settings_mod
from database import SessionLocal
from models import GuildSettings

log = logging.getLogger("guildizer.auto_threads")

_GATE_TTL = 60
_gate_cache: dict[int, tuple[float, dict | None]] = {}   # guild id -> (expiry, cfg)

ARCHIVE_CHOICES = {60, 1440, 4320, 10080}


def snapshot(guild_id: int) -> dict | None:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return None
        return {**settings_mod.AUTO_THREADS_DEFAULTS,
                **((row.extra or {}).get("auto_threads") or {})}
    finally:
        db.close()
        SessionLocal.remove()


async def _gate(guild_id: int) -> dict | None:
    now = time.monotonic()
    hit = _gate_cache.get(guild_id)
    if hit and hit[0] > now:
        return hit[1]
    if len(_gate_cache) > 1000:
        _gate_cache.clear()
    cfg = await asyncio.to_thread(snapshot, guild_id)
    _gate_cache[guild_id] = (now + _GATE_TTL, cfg)
    return cfg


def _thread_name(message: discord.Message) -> str:
    snippet = " ".join((message.content or "").split())[:60]
    if not snippet and message.attachments:
        snippet = message.attachments[0].filename[:60]
    base = f"💬 {message.author.display_name}: {snippet}" if snippet \
        else f"💬 {message.author.display_name}'s post"
    return base[:100]


async def handle_message(client, message: discord.Message) -> None:
    """Open a thread on a qualifying message. Never raises."""
    try:
        cfg = await _gate(message.guild.id)
        if not cfg or not cfg.get("enabled"):
            return
        if str(message.channel.id) not in [str(c) for c in (cfg.get("channel_ids") or [])]:
            return
        if message.author.bot and not cfg.get("include_bots"):
            return
        if message.flags.suppress_notifications and message.author.bot:
            return   # silent bot housekeeping posts don't deserve threads
        archive = int(cfg.get("archive_minutes") or 1440)
        if archive not in ARCHIVE_CHOICES:
            archive = 1440
        await governor.safe(
            message.create_thread(name=_thread_name(message),
                                  auto_archive_duration=archive,
                                  reason="Guildizer: auto-thread"),
            what="auto-thread create",
        )
    except Exception:  # noqa: BLE001
        log.exception("auto-thread failed for guild %s",
                      message.guild.id if message.guild else "?")
