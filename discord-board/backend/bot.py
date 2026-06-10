"""Guildizer Discord bot (Phase 0).

Connects to the Discord Gateway and registers a single /ping slash command,
proving the end-to-end bot pipeline works. Runs as its own process/worker,
separate from the Flask API. No Telegizer coupling.
"""
import logging

import discord
from discord import app_commands

from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("guildizer.bot")


# Phase 0 needs no privileged intents to run /ping. We'll enable members/message
# content in later phases (and in the Developer Portal) when moderation/welcome land.
intents = discord.Intents.default()


class GuildizerBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Sync slash commands globally. (Per-guild instant sync comes in Phase 2.)
        await self.tree.sync()
        log.info("Slash commands synced.")

    async def on_ready(self) -> None:
        log.info("Guildizer is online as %s (id=%s)", self.user, self.user.id)
        log.info("Connected to %d server(s).", len(self.guilds))


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
