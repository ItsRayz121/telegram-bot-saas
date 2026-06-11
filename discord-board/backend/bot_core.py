"""Shared bot engine for BOTH bot lineages (Phase 9).

The official Guildizer bot (bot.py) and every white-label custom bot
(custom_bot_manager.py) are thin clients over this module. All behavior lives
here, keyed by guild_id — ship a feature once and every bot has it on the next
deploy. (This is the same lineage rule Telegizer uses.)

Bot resolution: each guild is served by exactly ONE bot identity —
Guild.custom_bot_id NULL = the official bot, otherwise that custom bot. Event
handlers check serves() so two bots sharing a guild never double-moderate or
double-welcome. The routing map is cached in-process and refreshed every ~15s.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import tasks

import ai
import assistant
import bot_policy
import campaign_runtime
import campaign_views
import command_registrar
import content_runtime
import governor
import guild_sync
import leveling
import mod_commands
import moderation
import moderation_runtime
import protection
import raid_guard
import settings as settings_mod
import verification
from database import SessionLocal
from models import BotHealthEvent, CustomBot, Guild, GuildSettings, Member

log = logging.getLogger("guildizer.core")


# Both lineages need Server Members (join/leave) and Message Content (filter).
# Custom bots must have both toggled ON in their owner's Developer Portal —
# the connect wizard verifies this via the application flags before activation.
def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    return intents


# ── Bot resolution (guild -> serving bot identity) ─────────────────────────────
_ROUTING_TTL_SECONDS = 15
_routing_map: dict[int, int] = {}      # guild_id -> custom_bot_id (linked guilds only)
_routing_loaded_at: float = 0.0


def _load_routing() -> None:
    """Sync DB read — call off-loop via to_thread."""
    global _routing_map, _routing_loaded_at
    db = SessionLocal()
    try:
        rows = (
            db.query(Guild.id, Guild.custom_bot_id)
            .filter(Guild.custom_bot_id.isnot(None))
            .all()
        )
        _routing_map = {gid: cbid for gid, cbid in rows}
        _routing_loaded_at = time.monotonic()
    finally:
        db.close()
        SessionLocal.remove()


def refresh_routing_if_stale() -> None:
    """Sync; cheap no-op while fresh. Shared across all clients in the process."""
    if time.monotonic() - _routing_loaded_at > _ROUTING_TTL_SECONDS:
        try:
            _load_routing()
        except Exception:  # noqa: BLE001
            log.exception("Routing refresh failed; keeping previous map")


def serves(client, guild_id: int) -> bool:
    """True if `client` is the bot identity responsible for this guild."""
    linked = _routing_map.get(int(guild_id))
    if getattr(client, "custom_bot_id", None) is None:   # official bot
        return linked is None
    return linked == client.custom_bot_id


# ── Health events (dashboard + admin fleet view) ───────────────────────────────
def record_health(custom_bot_id: int | None, event: str, detail: str | None = None) -> None:
    """Sync — call off-loop. Never raises."""
    db = SessionLocal()
    try:
        db.add(BotHealthEvent(custom_bot_id=custom_bot_id, event=event,
                              detail=(detail or "")[:300] or None))
        if custom_bot_id is not None and event == "connect":
            bot = db.get(CustomBot, custom_bot_id)
            if bot is not None:
                bot.last_online_at = datetime.utcnow()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("record_health failed")
    finally:
        db.close()
        SessionLocal.remove()


class CoreMixin:
    """Event handlers + DB helpers shared by GuildizerBot and CustomBotClient.

    Expects on the concrete class:
      custom_bot_id: int | None   (None = the official bot)
      tree: app_commands.CommandTree
      _booted: bool
    """

    custom_bot_id: int | None = None

    # --- one-time boot work (call from on_ready, guarded by _booted) ----------
    async def core_boot(self) -> None:
        guilds = list(self.guilds)
        ids = [gd.id for gd in guilds]
        await asyncio.to_thread(self._sync_all_guilds, guilds)
        await asyncio.to_thread(self._self_heal_settings, ids)
        if self.custom_bot_id is not None:
            # Auto-link: every guild this custom bot is in that isn't already
            # claimed by another custom bot is now served by it.
            await asyncio.to_thread(self._auto_link_guilds, ids)
        await asyncio.to_thread(_load_routing)
        served = [gid for gid in ids if serves(self, gid)]
        await command_registrar.register_all(self, served)

    def _auto_link_guilds(self, guild_ids) -> None:
        db = SessionLocal()
        try:
            for gid in guild_ids:
                guild = db.get(Guild, gid)
                if guild is not None and guild.custom_bot_id is None:
                    guild.custom_bot_id = self.custom_bot_id
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("auto-link failed")
        finally:
            db.close()
            SessionLocal.remove()

    def _unlink_guild(self, guild_id) -> None:
        db = SessionLocal()
        try:
            guild = db.get(Guild, guild_id)
            if guild is not None and guild.custom_bot_id == self.custom_bot_id:
                guild.custom_bot_id = None
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("unlink failed for guild %s", guild_id)
        finally:
            db.close()
            SessionLocal.remove()

    # --- guild lifecycle -------------------------------------------------------
    async def on_guild_join(self, dguild: discord.Guild) -> None:
        log.info("[bot %s] joined guild %s (id=%s)",
                 self.custom_bot_id or "official", dguild.name, dguild.id)
        await asyncio.to_thread(self._sync_one_guild, dguild)
        await asyncio.to_thread(self._self_heal_settings, [dguild.id])
        if self.custom_bot_id is not None:
            await asyncio.to_thread(self._auto_link_guilds, [dguild.id])
        await asyncio.to_thread(_load_routing)
        if serves(self, dguild.id):
            await command_registrar.register_guild_commands(self, dguild.id)

    async def on_guild_remove(self, dguild: discord.Guild) -> None:
        log.info("[bot %s] removed from guild %s (id=%s)",
                 self.custom_bot_id or "official", dguild.name, dguild.id)
        if self.custom_bot_id is not None:
            # Guild reverts to the official bot; don't flip bot_present (the
            # official bot may still be in it).
            await asyncio.to_thread(self._unlink_guild, dguild.id)
            await asyncio.to_thread(_load_routing)
        else:
            await asyncio.to_thread(self._mark_left, dguild.id)

    # --- moderation: message-level content filter + raid signals ---------------
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        # auto-clean: delete system join messages when configured (Phase 10)
        if message.type == discord.MessageType.new_member:
            if serves(self, message.guild.id):
                cfg = await asyncio.to_thread(self._load_moderation, message.guild.id)
                if cfg and (cfg.get("auto_clean") or {}).get("join_messages"):
                    await governor.safe(message.delete(), what="auto-clean join message")
            return
        if message.author.bot:
            return
        if not serves(self, message.guild.id):
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
        if decision is None:
            decision = moderation.evaluate_automod(text, cfg)
        if decision is None:
            flags = {
                "attachments": bool(message.attachments),
                "stickers": bool(message.stickers),
                "voice": bool(getattr(message.flags, "voice", False)),
            }
            decision = moderation.evaluate_media(flags, cfg)
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
            else:
                await self._maybe_auto_respond(message)

    async def _maybe_auto_respond(self, message: discord.Message) -> None:
        responses = await asyncio.to_thread(content_runtime.load_responses, message.guild.id)
        if not responses:
            return
        hit = content_runtime.match_response(message.content or "", responses)
        if hit is None or not content_runtime.cooldown_ok(message.guild.id, hit):
            return
        await governor.safe(message.reply(hit["response"], mention_author=False),
                            what="auto-response")

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
            escalation = await asyncio.to_thread(
                self._record_automod_warning, message.guild.id, member.id,
                str(member), decision["detail"],
            )
            if escalation == "timeout":
                await governor.safe(member.timeout(timedelta(minutes=30), reason=reason), what="ladder timeout")
            elif escalation == "kick":
                await governor.safe(member.kick(reason=reason), what="ladder kick")
            elif escalation == "ban":
                await governor.safe(member.ban(reason=reason, delete_message_days=0), what="ladder ban")
            return f"warned+{escalation}" if escalation else "warned"
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

    # --- leveling / XP ----------------------------------------------------------
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

    # --- member events (join gate, lockdown, welcome/leave, auto-roles) ---------
    async def on_member_join(self, member: discord.Member) -> None:
        if not serves(self, member.guild.id):
            return
        if member.bot:
            await bot_policy.handle_bot_join(self, member)
            return
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

        # join captcha: quarantine role + challenge in #verify (Phase 11)
        vcfg = (mod or {}).get("verification") or {}
        if vcfg.get("enabled"):
            await self._start_verification(member, vcfg)

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
            await self._send_welcome(member, cfg)

    async def _start_verification(self, member: discord.Member, vcfg: dict) -> None:
        guild = member.guild
        # lazy setup: create role/channel on first use (admin enabled it in the dashboard)
        if not (vcfg.get("role_id") and guild.get_role(int(vcfg["role_id"]))):
            ids = await verification.ensure_setup(guild, vcfg)
            if ids is None:
                return
            await asyncio.to_thread(verification.save_setup_ids, guild.id,
                                    ids["role_id"], ids["channel_id"])
            vcfg = {**vcfg, "role_id": str(ids["role_id"]), "channel_id": str(ids["channel_id"])}
        role = guild.get_role(int(vcfg["role_id"]))
        channel = guild.get_channel(int(vcfg["channel_id"])) if vcfg.get("channel_id") else None
        if role is None or channel is None:
            return
        if not await governor.safe(
            member.add_roles(role, reason="Guildizer: verification pending"), what="verify role"
        ):
            return
        await asyncio.to_thread(verification.create_pending, guild.id, member.id,
                                str(member), vcfg)
        mins = max(1, int(vcfg.get("timeout_seconds", 300)) // 60)
        msg = await governor.safe(
            channel.send(
                f"👋 {member.mention} — verify within {mins} min to unlock the server.",
                view=verification.challenge_view(guild.id, member.id),
            ),
            what="post verification challenge",
        )
        if msg:
            await asyncio.to_thread(verification.set_challenge_message, guild.id,
                                    member.id, channel.id, msg.id)

    async def _send_welcome(self, member: discord.Member, cfg: dict) -> None:
        guild = member.guild
        channel = guild.get_channel(int(cfg["welcome_channel_id"]))
        if channel is None or not hasattr(channel, "send"):
            return
        text = settings_mod.render_message(cfg["welcome_message"], member=member, guild=guild)
        w2 = cfg.get("welcome2") or {}
        delete_after = int(w2.get("delete_after_seconds") or 0) or None
        rules_emoji = "📜"
        if w2.get("use_embed"):
            embed = discord.Embed(description=text or None, color=0x5865F2)
            embed.set_author(name=f"Welcome, {member.display_name}!",
                             icon_url=member.display_avatar.url)
            if w2.get("rules_text"):
                embed.add_field(name=f"{rules_emoji} Rules", value=str(w2["rules_text"])[:1024], inline=False)
            if w2.get("image_url"):
                embed.set_image(url=w2["image_url"])
            await governor.safe(channel.send(embed=embed, delete_after=delete_after),
                                what="welcome embed")
        else:
            if w2.get("rules_text"):
                rules = f"{rules_emoji} {w2['rules_text']}"
                text = f"{text}\n\n{rules}" if text else rules
            if text:
                await governor.safe(channel.send(text, delete_after=delete_after), what="welcome")

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
        if not serves(self, member.guild.id):
            return
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

    # --- periodic resync of dashboard command changes + routing refresh ---------
    @tasks.loop(seconds=30)
    async def resync_commands(self) -> None:
        await asyncio.to_thread(refresh_routing_if_stale)
        await command_registrar.resync_dirty(
            self, allow=lambda gid: self.get_guild(gid) is not None and serves(self, gid)
        )

    @resync_commands.before_loop
    async def _before_resync(self) -> None:
        await self.wait_until_ready()

    # --- post campaigns the dashboard flagged (needs_post) ----------------------
    @tasks.loop(seconds=20)
    async def post_campaigns(self) -> None:
        pairs = await asyncio.to_thread(campaign_runtime.campaigns_to_post)
        for cid, gid in pairs:
            if not serves(self, gid):
                continue
            try:
                await campaign_views.post_campaign(self, cid)
            except Exception:  # noqa: BLE001
                log.exception("post_campaign failed for %s", cid)

    @post_campaigns.before_loop
    async def _before_post(self) -> None:
        await self.wait_until_ready()

    # --- deliver due reminders (DM the user) -------------------------------------
    @tasks.loop(seconds=30)
    async def deliver_reminders(self) -> None:
        due = await asyncio.to_thread(self._fetch_due_reminders)
        for rid, user_id, text, gid in due:
            # Each identity delivers reminders set in guilds it serves; the
            # official bot also takes guild-less (DM-context) reminders.
            if gid is not None:
                if not serves(self, gid):
                    continue
            elif self.custom_bot_id is not None:
                continue
            try:
                user = self.get_user(int(user_id)) or await self.fetch_user(int(user_id))
                if user is not None:
                    await governor.safe(user.send(f"⏰ Reminder: {text}"), what="reminder DM")
            except Exception:  # noqa: BLE001
                log.exception("reminder delivery failed for %s", user_id)
            finally:
                await asyncio.to_thread(self._mark_reminder_delivered, rid)

    @deliver_reminders.before_loop
    async def _before_reminders(self) -> None:
        await self.wait_until_ready()

    # --- execute due scheduled moderation work (tempban expiry) ------------------
    @tasks.loop(seconds=60)
    async def process_mod_actions(self) -> None:
        rows = await asyncio.to_thread(self._fetch_due_mod_actions)
        for aid, gid, uid, action, reason in rows:
            if not serves(self, gid):
                continue
            guild = self.get_guild(gid)
            if guild is not None and action == "unban":
                ok = await governor.safe(
                    guild.unban(discord.Object(id=uid), reason=f"Guildizer: tempban expired ({reason or 'no reason'})"),
                    what="tempban expiry unban",
                )
                await asyncio.to_thread(
                    self._log, gid, "moderation", "unban" if ok else "unban_failed",
                    uid, None, None, "tempban expired",
                )
            await asyncio.to_thread(self._mark_mod_action_done, aid)

        # expired join-captcha challenges (kick/keep per config)
        served = [gd.id for gd in self.guilds if serves(self, gd.id)]
        expired = await asyncio.to_thread(verification.expired_rows, served)
        for row in expired:
            guild = self.get_guild(row["guild_id"])
            if guild is None:
                continue
            vcfg = ((await asyncio.to_thread(self._load_moderation, guild.id)) or {}).get("verification") or {}
            member = guild.get_member(row["user_id"])
            await verification._delete_challenge_message(guild, row)
            if member is not None and vcfg.get("on_timeout", "kick") == "kick":
                if await governor.safe(member.kick(reason="Guildizer: verification timed out"),
                                       what="verification timeout kick"):
                    await asyncio.to_thread(self._log, guild.id, "verification", "kick",
                                            row["user_id"], row["username"], "verification timed out")
            else:
                await asyncio.to_thread(self._log, guild.id, "verification", "expired",
                                        row["user_id"], row["username"], "challenge expired (kept)")

    @process_mod_actions.before_loop
    async def _before_mod_actions(self) -> None:
        await self.wait_until_ready()

    # --- scheduled messages + polls (Phase 12) ---------------------------------
    @tasks.loop(seconds=30)
    async def content_loop(self) -> None:
        served = [gd.id for gd in self.guilds if serves(self, gd.id)]

        for item in await asyncio.to_thread(content_runtime.due_messages, served):
            guild = self.get_guild(item["guild_id"])
            channel = guild.get_channel(int(item["channel_id"])) if guild else None
            sent = False
            if channel is not None and hasattr(channel, "send") and item["content"]:
                sent = bool(await governor.safe(channel.send(item["content"]),
                                                what="scheduled message"))
            await asyncio.to_thread(content_runtime.advance_schedule, item["id"], sent)

        for item in await asyncio.to_thread(content_runtime.polls_to_post, served):
            guild = self.get_guild(item["guild_id"])
            channel = guild.get_channel(int(item["channel_id"])) if guild else None
            message_id = None
            if channel is not None and hasattr(channel, "send"):
                try:
                    poll = discord.Poll(
                        question=item["question"],
                        duration=timedelta(hours=item["duration_hours"]),
                        multiple=item["multiselect"],
                    )
                    for ans in item["answers"]:
                        poll.add_answer(text=ans)
                    msg = await channel.send(poll=poll)
                    message_id = msg.id
                except (discord.HTTPException, AttributeError, TypeError):
                    log.exception("poll post failed for %s", item["id"])
            await asyncio.to_thread(content_runtime.mark_poll_posted, item["id"], message_id)

        for item in await asyncio.to_thread(content_runtime.polls_to_finalize, served):
            results = None
            guild = self.get_guild(item["guild_id"])
            channel = guild.get_channel(int(item["channel_id"])) if guild else None
            if channel is not None and item["message_id"]:
                try:
                    msg = await channel.fetch_message(int(item["message_id"]))
                    if msg.poll is not None:
                        results = {a.text: a.vote_count for a in msg.poll.answers}
                except (discord.HTTPException, AttributeError):
                    pass
            await asyncio.to_thread(content_runtime.record_poll_results, item["id"], results)

    @content_loop.before_loop
    async def _before_content(self) -> None:
        await self.wait_until_ready()

    # --- sync DB writes/reads (run off the event loop via to_thread) ------------
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
                "welcome2": {**settings_mod.WELCOME2_DEFAULTS,
                             **((row.extra or {}).get("welcome2") or {})},
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

    # --- assistant DB helpers -----------------------------------------------------
    @staticmethod
    def _add_reminder(guild_id, user_id, text, seconds):
        db = SessionLocal()
        try:
            r = assistant.add_reminder(db, guild_id, user_id, text, seconds)
            db.commit()
            return r.due_at
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _list_reminders(user_id):
        db = SessionLocal()
        try:
            return [(r.text, r.due_at) for r in assistant.list_reminders(db, user_id)]
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _fetch_due_reminders():
        db = SessionLocal()
        try:
            return [(r.id, r.user_id, r.text, r.guild_id) for r in assistant.due_reminders(db)]
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _mark_reminder_delivered(rid):
        db = SessionLocal()
        try:
            from models import Reminder
            r = db.get(Reminder, rid)
            if r is not None:
                r.delivered = True
                db.commit()
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _add_note(user_id, guild_id, content):
        db = SessionLocal()
        try:
            assistant.add_note(db, user_id, guild_id, content)
            db.commit()
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _list_notes(user_id):
        db = SessionLocal()
        try:
            return [(n.content, n.created_at) for n in assistant.list_notes(db, user_id)]
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _log_ai(guild_id, user_id, result):
        db = SessionLocal()
        try:
            assistant.log_ai_usage(db, guild_id, user_id, result.model,
                                   result.input_tokens, result.output_tokens)
            db.commit()
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _record_automod_warning(guild_id, user_id, username, detail):
        """Automod warning (moderator NULL). Returns the ladder escalation action
        (and resets the count) when the member hits max warnings, else None."""
        db = SessionLocal()
        try:
            snap = protection.load_snapshot(db, guild_id) or {}
            ladder = snap.get("warnings") or {}
            count, escalation = moderation_runtime.add_warning(
                db, guild_id, user_id, username, None, "automod", detail, ladder,
            )
            if escalation:
                moderation_runtime.clear_warnings(db, guild_id, user_id)
            db.commit()
            return escalation
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("automod warning failed for guild %s", guild_id)
            return None
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _fetch_due_mod_actions():
        db = SessionLocal()
        try:
            return [(a.id, a.guild_id, a.user_id, a.action, a.reason)
                    for a in moderation_runtime.due_actions(db)]
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _mark_mod_action_done(action_id):
        db = SessionLocal()
        try:
            moderation_runtime.mark_done(db, action_id)
            db.commit()
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


# ── Built-in slash commands (registered on EVERY bot identity's tree) ──────────
def attach_builtin_commands(client) -> None:
    """Register the built-in command set on a client's tree. White-label bots
    answer under their own name/avatar — same engine underneath."""
    mod_commands.attach_mod_commands(client)

    @client.tree.command(name="ping", description="Check that the bot is alive.")
    async def ping(interaction: discord.Interaction) -> None:
        latency_ms = round(client.latency * 1000)
        name = client.user.name if client.user else "Bot"
        await interaction.response.send_message(
            f"🟢 {name} is online — {latency_ms}ms", ephemeral=True
        )

    @client.tree.command(name="rank", description="Show your XP and level.")
    async def rank(interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        snap = await asyncio.to_thread(
            CoreMixin._rank_snapshot, interaction.guild.id, interaction.user.id
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
        rows = await asyncio.to_thread(CoreMixin._top_snapshot, interaction.guild.id, 10)
        if not rows:
            await interaction.response.send_message("No XP yet — start chatting!", ephemeral=True)
            return
        medals = ["🥇", "🥈", "🥉"]
        lines = [
            f"{medals[i] if i < 3 else f'**{i+1}.**'} {name} — level {lvl} ({xp} XP)"
            for i, (name, lvl, xp) in enumerate(rows)
        ]
        await interaction.response.send_message("🏆 **Leaderboard**\n" + "\n".join(lines))

    @client.tree.command(name="remind", description="Set a reminder. e.g. /remind 2h take a break")
    @app_commands.describe(when="When: 10m, 2h, 1d, 1h30m (a bare number = minutes)", text="What to remind you about")
    async def remind(interaction: discord.Interaction, when: str, text: str) -> None:
        seconds = assistant.parse_duration(when)
        if not seconds:
            await interaction.response.send_message(
                "I couldn't read that time. Try `10m`, `2h`, `1d`, or `1h30m`.", ephemeral=True
            )
            return
        gid = interaction.guild_id
        due = await asyncio.to_thread(
            CoreMixin._add_reminder, gid, interaction.user.id, text, seconds
        )
        ts = int(due.replace(tzinfo=None).timestamp()) if hasattr(due, "timestamp") else None
        when_str = f"<t:{int(due.timestamp())}:R>" if ts else "soon"
        await interaction.response.send_message(f"⏰ Okay! I'll remind you {when_str}: {text}", ephemeral=True)

    @client.tree.command(name="reminders", description="List your pending reminders.")
    async def reminders(interaction: discord.Interaction) -> None:
        rows = await asyncio.to_thread(CoreMixin._list_reminders, interaction.user.id)
        if not rows:
            await interaction.response.send_message("You have no pending reminders.", ephemeral=True)
            return
        lines = [f"• {text} — <t:{int(due.timestamp())}:R>" for text, due in rows]
        await interaction.response.send_message("⏰ **Your reminders**\n" + "\n".join(lines), ephemeral=True)

    @client.tree.command(name="note", description="Save a personal note.")
    @app_commands.describe(text="The note to save")
    async def note(interaction: discord.Interaction, text: str) -> None:
        await asyncio.to_thread(CoreMixin._add_note, interaction.user.id, interaction.guild_id, text)
        await interaction.response.send_message("📝 Saved.", ephemeral=True)

    @client.tree.command(name="notes", description="List your saved notes.")
    async def notes(interaction: discord.Interaction) -> None:
        rows = await asyncio.to_thread(CoreMixin._list_notes, interaction.user.id)
        if not rows:
            await interaction.response.send_message("You have no notes yet.", ephemeral=True)
            return
        lines = [f"• {content}" for content, _ in rows]
        await interaction.response.send_message("📝 **Your notes**\n" + "\n".join(lines)[:1900], ephemeral=True)

    @client.tree.command(name="ask", description="Ask the AI assistant a question.")
    @app_commands.describe(question="Your question")
    async def ask(interaction: discord.Interaction, question: str) -> None:
        if not ai.is_configured():
            await interaction.response.send_message(
                "🤖 The AI assistant isn't configured on this server yet.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await asyncio.to_thread(ai.ask, question)
        if result is None:
            await interaction.followup.send("Sorry, I couldn't answer that right now.", ephemeral=True)
            return
        await asyncio.to_thread(CoreMixin._log_ai, interaction.guild_id, interaction.user.id, result)
        await interaction.followup.send(result.text[:1950], ephemeral=True)
