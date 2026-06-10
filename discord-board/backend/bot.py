"""Guildizer Discord bot.

Phase 1: gateway sync of guilds/channels/roles into the shared DB.
Phase 2: custom slash commands, welcome/leave messages, auto-roles.
Phase 3: moderation — content filter, behavior-based raid guard, join gate, and
a Protection Activity audit log.

Runs as its own process/worker, separate from the Flask API. No Telegizer
coupling. Bot and API coordinate only through the shared database.
"""
import asyncio
import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import tasks

import command_registrar
import content_filter  # noqa: F401  (kept explicit; moderation imports it)
import governor
import guild_sync
import leveling
import moderation
import protection
import raid_guard
import settings as settings_mod
from config import Config
from database import SessionLocal, init_db
from models import GuildSettings, Member

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("guildizer.bot")


# Phase 2 needs Server Members (member join/leave). Phase 3's content filter needs
# Message Content to read message text. BOTH must also be toggled ON in the
# Developer Portal, or the gateway connection fails with PrivilegedIntentsRequired.
intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class GuildizerBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await asyncio.to_thread(init_db)
        await self.tree.sync()
        log.info("Global slash commands synced.")
        self.resync_commands.start()

    async def on_ready(self) -> None:
        log.info("Guildizer is online as %s (id=%s)", self.user, self.user.id)
        log.info("Connected to %d server(s).", len(self.guilds))
        guilds = list(self.guilds)
        ids = [gd.id for gd in guilds]
        await asyncio.to_thread(self._sync_all_guilds, guilds)
        await asyncio.to_thread(self._self_heal_settings, ids)
        await command_registrar.register_all(self, ids)

    async def on_guild_join(self, dguild: discord.Guild) -> None:
        log.info("Joined guild %s (id=%s)", dguild.name, dguild.id)
        await asyncio.to_thread(self._sync_one_guild, dguild)
        await asyncio.to_thread(self._self_heal_settings, [dguild.id])
        await command_registrar.register_guild_commands(self, dguild.id)

    async def on_guild_remove(self, dguild: discord.Guild) -> None:
        log.info("Removed from guild %s (id=%s)", dguild.name, dguild.id)
        await asyncio.to_thread(self._mark_left, dguild.id)

    # --- moderation: message-level content filter + raid signals --------------
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        # XP applies to everyone (including staff); moderation skips staff.
        await self._maybe_award_xp(message)

        perms = getattr(message.author, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild or perms.manage_messages):
            return  # never moderate staff

        cfg = await asyncio.to_thread(self._load_moderation, message.guild.id)
        if not cfg:
            return

        text = message.content or ""
        for emb in message.embeds:
            text += " " + (emb.title or "") + " " + (emb.description or "")

        decision = moderation.evaluate(text, cfg)
        if decision:
            action_taken = await self._execute_action(message, decision)
            await asyncio.to_thread(
                self._log, message.guild.id, decision["category"], action_taken,
                message.author.id, str(message.author), message.channel.id, decision["detail"],
            )
            if raid_guard.note_violation(message.guild.id, message.author.id, cfg):
                await self._raid_activated(message.guild, cfg)
        else:
            if raid_guard.note_message(message.guild.id, message.author.id, text, cfg):
                await self._raid_activated(message.guild, cfg)

    async def _execute_action(self, message: discord.Message, decision: dict) -> str:
        action = decision["action"]
        member = message.author
        reason = f"Guildizer: {decision['detail']}"
        await governor.safe(message.delete(), what="delete flagged message")
        if action == "warn":
            await governor.safe(
                message.channel.send(moderation.warning_text(decision["category"]), delete_after=8),
                what="post warning",
            )
            return "warned"
        if action == "timeout":
            await governor.safe(member.timeout(timedelta(minutes=10), reason=reason), what="timeout")
            return "timeout"
        if action == "kick":
            await governor.safe(member.kick(reason=reason), what="kick")
            return "kick"
        if action == "ban":
            await governor.safe(member.ban(reason=reason, delete_message_days=1), what="ban")
            return "ban"
        return "deleted"

    async def _raid_activated(self, guild: discord.Guild, cfg: dict) -> None:
        secs = raid_guard.seconds_remaining(guild.id)
        log.warning("Raid mode activated for guild %s (%ds)", guild.id, secs)
        await asyncio.to_thread(
            self._log, guild.id, "raid", "restricted", None, None, None, "Raid mode activated"
        )
        if not cfg.get("rg_notify"):
            return
        ch_id = cfg.get("rg_notify_channel_id")
        channel = guild.get_channel(int(ch_id)) if ch_id else guild.system_channel
        if channel and hasattr(channel, "send"):
            await governor.safe(channel.send(raid_guard.activation_notice(secs)), what="raid notice")

    # --- leveling / XP --------------------------------------------------------
    async def _maybe_award_xp(self, message: discord.Message) -> None:
        cfg = await asyncio.to_thread(self._load_leveling, message.guild.id)
        if not cfg or not cfg.get("levels_enabled"):
            return
        result = await asyncio.to_thread(
            self._do_award_xp, message.guild.id, message.author.id, str(message.author), cfg
        )
        if result is None:
            return
        leveled_up, new_level = result
        if leveled_up and cfg.get("announce_level_up", True):
            text = leveling.render_levelup(
                cfg.get("levelup_message"),
                mention=message.author.mention,
                username=str(message.author),
                level=new_level,
            )
            ch_id = cfg.get("levelup_channel_id")
            channel = message.guild.get_channel(int(ch_id)) if ch_id else message.channel
            if channel and hasattr(channel, "send"):
                await governor.safe(channel.send(text), what="level-up announce")

    # --- member events (join gate, lockdown, welcome/leave, auto-roles) -------
    async def on_member_join(self, member: discord.Member) -> None:
        mod = await asyncio.to_thread(self._load_moderation, member.guild.id)
        if mod:
            # account-age join gate
            min_days = mod.get("jg_min_account_age_days", 0)
            if min_days and member.created_at:
                age = discord.utils.utcnow() - member.created_at
                if age.days < min_days:
                    if await governor.safe(
                        member.kick(reason=f"Guildizer join gate: account < {min_days}d"),
                        what="join-gate kick",
                    ):
                        await asyncio.to_thread(
                            self._log, member.guild.id, "join_gate", "kick", member.id,
                            str(member), None, f"Account age {age.days}d < {min_days}d",
                        )
                    return

            # raid lockdown (auto or manual) — restrict newcomers
            if raid_guard.is_locked_down(member.guild.id, mod.get("manual_lockdown_until")):
                taken = await self._lockdown_joiner(member, mod)
                await asyncio.to_thread(
                    self._log, member.guild.id, "lockdown_join", taken, member.id,
                    str(member), None, "Joined during lockdown",
                )
                if taken == "kick":
                    return

        # welcome message + auto-roles
        cfg = await asyncio.to_thread(self._load_member_settings, member.guild.id)
        if not cfg:
            return
        if cfg["autorole_enabled"] and cfg["autorole_ids"]:
            roles = [member.guild.get_role(int(rid)) for rid in cfg["autorole_ids"]]
            roles = [r for r in roles if r is not None]
            if roles:
                await governor.safe(
                    member.add_roles(*roles, reason="Guildizer auto-role"), what="auto-role"
                )
        if cfg["welcome_enabled"] and cfg["welcome_channel_id"]:
            await self._send_to_channel(
                member.guild, cfg["welcome_channel_id"],
                settings_mod.render_message(cfg["welcome_message"], member=member, guild=member.guild),
            )

    async def _lockdown_joiner(self, member: discord.Member, cfg: dict) -> str:
        if cfg.get("rg_lockdown_action") == "kick":
            return "kick" if await governor.safe(
                member.kick(reason="Guildizer raid lockdown"), what="lockdown kick"
            ) else "none"
        mins = cfg.get("rg_lockdown_minutes", 10)
        return "timeout" if await governor.safe(
            member.timeout(timedelta(minutes=mins), reason="Guildizer raid lockdown"),
            what="lockdown timeout",
        ) else "none"

    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = await asyncio.to_thread(self._load_member_settings, member.guild.id)
        if not cfg or not (cfg["leave_enabled"] and cfg["leave_channel_id"]):
            return
        await self._send_to_channel(
            member.guild, cfg["leave_channel_id"],
            settings_mod.render_message(cfg["leave_message"], member=member, guild=member.guild),
        )

    async def _send_to_channel(self, guild: discord.Guild, channel_id: int, content: str) -> None:
        if not content:
            return
        channel = guild.get_channel(int(channel_id))
        if channel is None or not hasattr(channel, "send"):
            return
        await governor.safe(channel.send(content), what="send channel message")

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
            c1 = settings_mod.self_heal_all(db, guild_ids)
            c2 = protection.self_heal(db, guild_ids)
            db.commit()
            if c1 or c2:
                log.info("Self-healed settings for %d / moderation for %d guild(s).", c1, c2)
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

    @staticmethod
    def _load_moderation(guild_id):
        db = SessionLocal()
        try:
            return protection.load_snapshot(db, guild_id)
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _load_leveling(guild_id):
        db = SessionLocal()
        try:
            row = db.get(GuildSettings, guild_id)
            return row.levels_to_dict() if row is not None else None
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _do_award_xp(guild_id, user_id, username, cfg):
        db = SessionLocal()
        try:
            res = leveling.award_message_xp(db, guild_id, user_id, username, cfg)
            db.commit()
            return res
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("award_message_xp failed for guild %s", guild_id)
            return None
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _rank_snapshot(guild_id, user_id):
        db = SessionLocal()
        try:
            m = db.get(Member, {"guild_id": guild_id, "user_id": user_id})
            if m is None:
                return None
            return {"xp": m.xp or 0, "level": m.level or 1, "rank": leveling.rank_of(db, guild_id, user_id)}
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _top_snapshot(guild_id, limit=10):
        db = SessionLocal()
        try:
            return [(m.username or str(m.user_id), m.level or 1, m.xp or 0)
                    for m in leveling.top_members(db, guild_id, limit)]
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _log(guild_id, category, action, user_id=None, username=None, channel_id=None, detail=None):
        db = SessionLocal()
        try:
            protection.log_event(
                db, guild_id, category, action,
                user_id=user_id, username=username, channel_id=channel_id, detail=detail,
            )
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("log_event failed for guild %s", guild_id)
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


@client.tree.command(name="rank", description="Show your XP and level.")
async def rank(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    snap = await asyncio.to_thread(
        GuildizerBot._rank_snapshot, interaction.guild.id, interaction.user.id
    )
    if not snap:
        await interaction.response.send_message("You have no XP yet — start chatting!", ephemeral=True)
        return
    need = leveling.xp_for_level(snap["level"] + 1)
    await interaction.response.send_message(
        f"🏅 **Level {snap['level']}** · {snap['xp']} XP · rank #{snap['rank']}\n"
        f"Next level at {need} XP.",
        ephemeral=True,
    )


@client.tree.command(name="leaderboard", description="Show the top members by XP.")
async def leaderboard(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    rows = await asyncio.to_thread(GuildizerBot._top_snapshot, interaction.guild.id, 10)
    if not rows:
        await interaction.response.send_message("No XP yet — start chatting!", ephemeral=True)
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = [
        f"{medals[i] if i < 3 else f'**{i+1}.**'} {name} — level {lvl} ({xp} XP)"
        for i, (name, lvl, xp) in enumerate(rows)
    ]
    await interaction.response.send_message("🏆 **Leaderboard**\n" + "\n".join(lines))


def main() -> None:
    token = Config.require_bot_token()
    client.run(token)


if __name__ == "__main__":
    main()
