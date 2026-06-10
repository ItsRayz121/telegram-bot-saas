"""Guildizer Discord bot.

Phase 1: gateway sync of guilds/channels/roles into the shared DB.
Phase 2: per-guild custom slash commands (registered from the dashboard),
welcome/leave messages, and auto-roles.

Runs as its own process/worker, separate from the Flask API. No Telegizer
coupling. The bot and API coordinate only through the shared database.
"""
import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import tasks

import command_registrar
import guild_sync
import settings as settings_mod
from config import Config
from database import SessionLocal, init_db
from models import GuildSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("guildizer.bot")


# Phase 2 needs the Server Members privileged intent for member join/leave events
# (welcome/leave/auto-roles). Enable "Server Members Intent" in the Developer
# Portal too, or the gateway connection will fail with PrivilegedIntentsRequired.
# Message Content stays off until Phase 3 moderation.
intents = discord.Intents.default()
intents.members = True


class GuildizerBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await asyncio.to_thread(init_db)
        # Global commands (e.g. /ping). Per-guild custom commands sync in on_ready.
        await self.tree.sync()
        log.info("Global slash commands synced.")
        self.resync_commands.start()

    async def on_ready(self) -> None:
        log.info("Guildizer is online as %s (id=%s)", self.user, self.user.id)
        log.info("Connected to %d server(s).", len(self.guilds))
        guilds = list(self.guilds)
        await asyncio.to_thread(self._sync_all_guilds, guilds)
        await asyncio.to_thread(self._self_heal_settings, [gd.id for gd in guilds])
        await command_registrar.register_all(self, [gd.id for gd in guilds])

    async def on_guild_join(self, dguild: discord.Guild) -> None:
        log.info("Joined guild %s (id=%s)", dguild.name, dguild.id)
        await asyncio.to_thread(self._sync_one_guild, dguild)
        await asyncio.to_thread(self._self_heal_settings, [dguild.id])
        await command_registrar.register_guild_commands(self, dguild.id)

    async def on_guild_remove(self, dguild: discord.Guild) -> None:
        log.info("Removed from guild %s (id=%s)", dguild.name, dguild.id)
        await asyncio.to_thread(self._mark_left, dguild.id)

    # --- member events (welcome / leave / auto-roles) -------------------------
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await asyncio.to_thread(self._load_member_settings, member.guild.id)
        if not cfg:
            return

        if cfg["autorole_enabled"] and cfg["autorole_ids"]:
            roles = [member.guild.get_role(int(rid)) for rid in cfg["autorole_ids"]]
            roles = [r for r in roles if r is not None]
            if roles:
                try:
                    await member.add_roles(*roles, reason="Guildizer auto-role")
                except discord.Forbidden:
                    log.warning("Missing permission to auto-role in guild %s", member.guild.id)
                except discord.HTTPException:
                    log.exception("Auto-role failed in guild %s", member.guild.id)

        if cfg["welcome_enabled"] and cfg["welcome_channel_id"]:
            await self._send_to_channel(
                member.guild,
                cfg["welcome_channel_id"],
                settings_mod.render_message(cfg["welcome_message"], member=member, guild=member.guild),
            )

    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = await asyncio.to_thread(self._load_member_settings, member.guild.id)
        if not cfg or not (cfg["leave_enabled"] and cfg["leave_channel_id"]):
            return
        await self._send_to_channel(
            member.guild,
            cfg["leave_channel_id"],
            settings_mod.render_message(cfg["leave_message"], member=member, guild=member.guild),
        )

    async def _send_to_channel(self, guild: discord.Guild, channel_id: int, content: str) -> None:
        if not content:
            return
        channel = guild.get_channel(int(channel_id))
        if channel is None or not hasattr(channel, "send"):
            return
        try:
            await channel.send(content)
        except discord.Forbidden:
            log.warning("Missing permission to post in channel %s", channel_id)
        except discord.HTTPException:
            log.exception("Failed to post in channel %s", channel_id)

    # --- periodic resync of dashboard command changes -------------------------
    @tasks.loop(seconds=30)
    async def resync_commands(self) -> None:
        await command_registrar.resync_dirty(self)

    @resync_commands.before_loop
    async def _before_resync(self) -> None:
        await self.wait_until_ready()

    # --- sync DB writes/reads (run off the event loop via to_thread) ----------
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

    @staticmethod
    def _self_heal_settings(guild_ids) -> None:
        db = SessionLocal()
        try:
            created = settings_mod.self_heal_all(db, guild_ids)
            db.commit()
            if created:
                log.info("Self-healed settings for %d guild(s).", created)
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("Settings self-heal failed")
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _load_member_settings(guild_id):
        db = SessionLocal()
        try:
            row = db.get(GuildSettings, guild_id)
            if row is None:
                return None
            return {
                "welcome_enabled": bool(row.welcome_enabled),
                "welcome_channel_id": row.welcome_channel_id,
                "welcome_message": row.welcome_message or "",
                "leave_enabled": bool(row.leave_enabled),
                "leave_channel_id": row.leave_channel_id,
                "leave_message": row.leave_message or "",
                "autorole_enabled": bool(row.autorole_enabled),
                "autorole_ids": list(row.autorole_ids or []),
            }
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
