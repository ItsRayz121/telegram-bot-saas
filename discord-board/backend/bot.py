"""Guildizer Discord bot — the OFFICIAL bot identity.

All behavior lives in bot_core.py, shared with the white-label custom bots
(custom_bot_manager.py). This file is the thin official client: auto-sharded
gateway connection, built-in command tree, and the fleet runner for any
customer-connected custom bots — one worker process for both lineages.

Runs as its own process/worker, separate from the Flask API. No Telegizer
coupling. Bot and API coordinate only through the shared database.
"""
import asyncio
import logging
import signal

import discord
from discord import app_commands

import bot_core
import campaign_views
import custom_bot_manager
from config import Config
from database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("guildizer.bot")


# AutoShardedClient so the official bot scales past ~2,500 guilds without code
# changes (custom bots serve a handful of guilds each — plain Clients).
class GuildizerBot(bot_core.CoreMixin, discord.AutoShardedClient):
    custom_bot_id = None   # None = the official bot identity

    def __init__(self) -> None:
        super().__init__(intents=bot_core.build_intents())
        self.tree = app_commands.CommandTree(self)
        self._booted = False   # guard one-time startup work across (re)connects/shards

    async def setup_hook(self) -> None:
        await asyncio.to_thread(init_db)
        await self.tree.sync()
        log.info("Global slash commands synced.")
        # Persistent campaign proof buttons survive restarts via DynamicItem.
        self.add_dynamic_items(campaign_views.ProofButton)
        self.resync_commands.start()
        self.post_campaigns.start()
        self.deliver_reminders.start()

    async def on_ready(self) -> None:
        log.info("Guildizer is online as %s (id=%s)", self.user, self.user.id)
        log.info("Connected to %d server(s) across %d shard(s).",
                 len(self.guilds), self.shard_count or 1)
        # on_ready can fire again on reconnects / per shard — only boot once.
        if self._booted:
            return
        self._booted = True
        await asyncio.to_thread(bot_core.record_health, None, "connect")
        await self.core_boot()


client = GuildizerBot()
bot_core.attach_builtin_commands(client)


def main() -> None:
    token = Config.require_bot_token()

    async def runner() -> None:
        loop = asyncio.get_running_loop()
        fleet = custom_bot_manager.FleetManager()

        def _shutdown() -> None:
            log.info("Shutdown signal received — closing gateway gracefully…")
            loop.create_task(fleet.shutdown())
            loop.create_task(client.close())

        # Railway/containers send SIGTERM on deploy; close cleanly so the
        # interpreter doesn't tear down mid-request (avoids shutdown errors).
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _shutdown)
            except (NotImplementedError, AttributeError):
                pass  # not supported on Windows; KeyboardInterrupt still works

        async with client:
            # White-label fleet reconciles in the background on the same loop.
            fleet_task = asyncio.create_task(fleet.run(), name="custom-bot-fleet")
            try:
                await client.start(token)
            finally:
                fleet_task.cancel()
                await fleet.shutdown()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
