"""Guildizer Discord bot.

Connects to the Discord Gateway, registers slash commands, and — as of Phase 1 —
syncs the servers it's in (guilds, channels, roles) into the shared Guildizer DB
so the dashboard can render them. Runs as its own process/worker, separate from
the Flask API. No Telegizer coupling.
"""
import asyncio
import logging

import discord
from discord import app_commands

import guild_sync
from config import Config
from database import SessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("guildizer.bot")


# Phase 1 syncs guilds/channels/roles — all available under the default intents
# (the privileged Members / Message Content intents arrive with moderation in
# later phases, and must also be toggled on in the Developer Portal then).
intents = discord.Intents.default()


class GuildizerBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Ensure tables exist (bot may boot before the web service has).
        await asyncio.to_thread(init_db)
        # Sync slash commands globally. (Per-guild instant sync comes in Phase 2.)
        await self.tree.sync()
        log.info("Slash commands synced.")

    async def on_ready(self) -> None:
        log.info("Guildizer is online as %s (id=%s)", self.user, self.user.id)
        log.info("Connected to %d server(s).", len(self.guilds))
        await asyncio.to_thread(self._sync_all_guilds, list(self.guilds))

    async def on_guild_join(self, dguild: discord.Guild) -> None:
        log.info("Joined guild %s (id=%s)", dguild.name, dguild.id)
        await asyncio.to_thread(self._sync_one_guild, dguild)

    async def on_guild_remove(self, dguild: discord.Guild) -> None:
        log.info("Removed from guild %s (id=%s)", dguild.name, dguild.id)
        await asyncio.to_thread(self._mark_left, dguild.id)

    # --- DB writes (run off the event loop via to_thread) ---------------------
    @staticmethod
    def _sync_all_guilds(guilds) -> None:
        db = SessionLocal()
        try:
            for dguild in guilds:
                guild_sync.full_sync(db, dguild)
            db.commit()
            log.info("Synced %d guild(s) to DB.", len(guilds))
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("Guild sync failed")
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _sync_one_guild(dguild) -> None:
        db = SessionLocal()
        try:
            guild_sync.full_sync(db, dguild)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("Guild sync failed for %s", dguild.id)
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _mark_left(guild_id) -> None:
        db = SessionLocal()
        try:
            guild_sync.mark_bot_left(db, guild_id)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("mark_bot_left failed for %s", guild_id)
        finally:
            db.close()
            SessionLocal.remove()


client = GuildizerBot()


@client.tree.command(name="ping", description="Check that Guildizer is alive.")
async def ping(interaction: discord.Interaction) -> None:
    latency_ms = round(client.latency * 1000)
    await interaction.response.send_message(
        f"🟢 Guildizer is online — {latency_ms}ms", ephemeral=True
    )


def main() -> None:
    token = Config.require_bot_token()
    client.run(token)


if __name__ == "__main__":
    main()
