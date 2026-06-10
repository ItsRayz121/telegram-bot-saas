"""Register dashboard-defined custom commands as per-guild Discord slash commands.

The bot calls these from its event loop. DB reads run off-loop via to_thread;
the discord.py tree ops (add/clear/sync) run on the loop. Coordination with the
Flask API is via GuildSettings.commands_dirty.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

from database import SessionLocal
from models import CustomCommand, GuildSettings

log = logging.getLogger("guildizer.commands")


# --- sync DB helpers (run via asyncio.to_thread) ------------------------------
def _load_specs(guild_id: int) -> list[tuple[str, str, str]]:
    db = SessionLocal()
    try:
        cmds = (
            db.query(CustomCommand)
            .filter(CustomCommand.guild_id == guild_id, CustomCommand.enabled.is_(True))
            .all()
        )
        return [(c.name, (c.description or "Custom command")[:100], c.response or "") for c in cmds]
    finally:
        db.close()
        SessionLocal.remove()


def _dirty_guild_ids() -> list[int]:
    db = SessionLocal()
    try:
        rows = db.query(GuildSettings).filter(GuildSettings.commands_dirty.is_(True)).all()
        return [r.guild_id for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def _clear_dirty(guild_id: int) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is not None:
            row.commands_dirty = False
            db.commit()
    finally:
        db.close()
        SessionLocal.remove()


# --- command building ---------------------------------------------------------
def _make_callback(response_text: str):
    """Closure that captures the response without exposing it as a slash option."""

    async def _cb(interaction: discord.Interaction):
        await interaction.response.send_message(response_text or "…")

    return _cb


async def register_guild_commands(bot, guild_id: int) -> int:
    """(Re)register one guild's custom commands and push them to Discord."""
    specs = await asyncio.to_thread(_load_specs, guild_id)
    gobj = discord.Object(id=guild_id)
    bot.tree.clear_commands(guild=gobj)
    for name, description, response in specs:
        bot.tree.add_command(
            app_commands.Command(
                name=name,
                description=description or "Custom command",
                callback=_make_callback(response),
            ),
            guild=gobj,
        )
    await bot.tree.sync(guild=gobj)
    return len(specs)


async def register_all(bot, guild_ids: list[int]) -> None:
    for gid in guild_ids:
        try:
            n = await register_guild_commands(bot, gid)
            if n:
                log.info("Registered %d custom command(s) for guild %s", n, gid)
        except Exception:  # noqa: BLE001
            log.exception("Failed to register commands for guild %s", gid)


async def resync_dirty(bot) -> None:
    """Re-register any guilds the API flagged as dirty, then clear the flag."""
    ids = await asyncio.to_thread(_dirty_guild_ids)
    for gid in ids:
        try:
            n = await register_guild_commands(bot, gid)
            await asyncio.to_thread(_clear_dirty, gid)
            log.info("Resynced %d custom command(s) for guild %s", n, gid)
        except Exception:  # noqa: BLE001
            log.exception("Failed to resync commands for guild %s", gid)
