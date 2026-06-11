"""Starboard: ⭐-threshold reposts to a best-of channel. Both lineages.

Config lives in GuildSettings.extra["starboard"] (self-heals, no migration).
When a message collects `threshold` reactions of the configured emoji, the bot
reposts it as an embed in the starboard channel; later stars/unstars edit the
count on the existing repost. The source->repost mapping is kept in
extra["starboard"]["posted"], pruned to the newest entries so the row stays
bounded.

Throttling (anti-spam): the deciding repost is immediate, but count edits on a
viral message are coalesced — at most one edit per message per EDIT_COOLDOWN
seconds. Self-stars never trigger anything when allow_self_star is off.
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

log = logging.getLogger("guildizer.starboard")

STAR_COLOR = 0xFEE75C
MAX_POSTED = 400          # mapping entries kept per guild (newest win)
EDIT_COOLDOWN = 15        # seconds between count edits per source message
_GATE_TTL = 60            # config cache — reaction events fire constantly

_edit_last: dict[int, float] = {}   # source message id -> monotonic ts
_gate_cache: dict[int, tuple[float, dict | None]] = {}   # guild id -> (expiry, cfg)
_in_flight: set[int] = set()        # source message ids being reposted right now


def merged(extra: dict | None) -> dict:
    return {**settings_mod.STARBOARD_DEFAULTS, **((extra or {}).get("starboard") or {})}


# ── storage helpers (sync — call via to_thread) ────────────────────────────────
def snapshot(guild_id: int) -> dict | None:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return None
        return merged(row.extra)
    finally:
        db.close()
        SessionLocal.remove()


async def _gate(guild_id: int) -> dict | None:
    """Cached config WITHOUT the posted map — the cheap per-reaction check.
    The posted map is always re-read fresh so a stale cache can't double-post."""
    now = time.monotonic()
    hit = _gate_cache.get(guild_id)
    if hit and hit[0] > now:
        return hit[1]
    if len(_gate_cache) > 1000:
        _gate_cache.clear()
    cfg = await asyncio.to_thread(snapshot, guild_id)
    if cfg is not None:
        cfg = {k: v for k, v in cfg.items() if k != "posted"}
    _gate_cache[guild_id] = (now + _GATE_TTL, cfg)
    return cfg


def posted_entry(guild_id: int, source_id: int) -> dict | None:
    """Fresh read of one posted-map entry (sync — call via to_thread)."""
    cfg = snapshot(guild_id)
    if cfg is None:
        return None
    return (cfg.get("posted") or {}).get(str(source_id))


def record_post(guild_id: int, source_id: int, star_message_id: int, count: int) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return
        cfg = merged(row.extra)
        posted = dict(cfg.get("posted") or {})
        posted[str(source_id)] = {"star_message_id": str(star_message_id), "count": count}
        if len(posted) > MAX_POSTED:   # dicts keep insertion order — drop oldest
            for key in list(posted)[: len(posted) - MAX_POSTED]:
                posted.pop(key, None)
        extra = dict(row.extra or {})
        extra["starboard"] = {**cfg, "posted": posted}
        row.extra = extra
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("starboard record_post failed for guild %s", guild_id)
    finally:
        db.close()
        SessionLocal.remove()


# ── reaction handling (called from bot_core raw reaction events) ───────────────
def _emoji_matches(payload_emoji, wanted: str) -> bool:
    return str(payload_emoji) == (wanted or "⭐")


def _build_embed(message: discord.Message) -> discord.Embed:
    embed = discord.Embed(
        description=(message.content or "")[:2000] or None,
        color=STAR_COLOR,
        timestamp=message.created_at,
    )
    embed.set_author(name=message.author.display_name,
                     icon_url=message.author.display_avatar.url)
    embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})",
                    inline=False)
    image = next((a for a in message.attachments
                  if (a.content_type or "").startswith("image/")), None)
    if image is not None:
        embed.set_image(url=image.url)
    elif message.attachments:
        embed.add_field(name="Attachment", value=message.attachments[0].url, inline=False)
    embed.set_footer(text=f"#{getattr(message.channel, 'name', '?')}")
    return embed


async def handle_reaction(client, payload: discord.RawReactionActionEvent,
                          guild: discord.Guild, *, add: bool) -> None:
    """Repost / update a starboard entry for this reaction event. Never raises."""
    try:
        await _handle(client, payload, guild, add=add)
    except Exception:  # noqa: BLE001
        log.exception("starboard handling failed for guild %s", payload.guild_id)


async def _handle(client, payload, guild: discord.Guild, *, add: bool) -> None:
    cfg = await _gate(guild.id)
    if not cfg or not cfg.get("enabled") or not cfg.get("channel_id"):
        return
    if not _emoji_matches(payload.emoji, cfg.get("emoji")):
        return
    if add and payload.member is not None and payload.member.bot:
        return   # bot reactions never count
    board = guild.get_channel(int(cfg["channel_id"])) if str(cfg["channel_id"]).isdigit() else None
    if board is None or not hasattr(board, "send"):
        return
    if payload.channel_id == board.id:
        return   # stars on starboard reposts don't recurse

    already = await asyncio.to_thread(posted_entry, guild.id, payload.message_id)
    if already is None and not add:
        return   # an unstar on something we never reposted

    # Edits are throttled; the deciding repost always goes through.
    now = time.monotonic()
    if already is not None and now - _edit_last.get(payload.message_id, 0.0) < EDIT_COOLDOWN:
        return
    if len(_edit_last) > 2000:
        _edit_last.clear()

    channel = guild.get_channel(payload.channel_id)
    if channel is None or getattr(channel, "nsfw", False):
        return
    try:
        message = await channel.fetch_message(payload.message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return
    if client.user and message.author.id == client.user.id:
        return   # the bot's own posts never ride the starboard

    if add and not cfg.get("allow_self_star") and payload.user_id == message.author.id:
        return   # a self-star never triggers (count shown may still include it)

    reaction = next((r for r in message.reactions
                     if _emoji_matches(r.emoji, cfg.get("emoji"))), None)
    count = reaction.count if reaction is not None else 0
    emoji = cfg.get("emoji") or "⭐"
    header = f"{emoji} **{count}** · {channel.mention}"

    if already is not None:
        _edit_last[payload.message_id] = now
        try:
            star_msg = await board.fetch_message(int(already["star_message_id"]))
            await star_msg.edit(content=header)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return   # repost was deleted by an admin — respect that
        await asyncio.to_thread(record_post, guild.id, payload.message_id,
                                int(already["star_message_id"]), count)
        return

    if count < max(1, int(cfg.get("threshold") or 3)):
        return
    if payload.message_id in _in_flight:
        return   # a racing event is already reposting this message
    _in_flight.add(payload.message_id)
    try:
        star_msg = await governor.safe(
            board.send(header, embed=_build_embed(message)), what="starboard repost"
        )
        if star_msg and hasattr(star_msg, "id"):
            _edit_last[payload.message_id] = now
            await asyncio.to_thread(record_post, guild.id, payload.message_id,
                                    star_msg.id, count)
    finally:
        _in_flight.discard(payload.message_id)
