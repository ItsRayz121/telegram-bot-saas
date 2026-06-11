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
import re
import time
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import tasks

import ai
import assistant
import automation_runtime
import bot_policy
import campaign_runtime
import campaign_views
import command_registrar
import digest_runtime
import knowledge
import content_runtime
import governor
import guild_sync
import invite_tracking
import leveling
import mod_commands
import moderation
import moderation_runtime
import protection
import raid_guard
import self_roles
import settings as settings_mod
import stats_runtime
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
    """Sync DB read — call off-loop via to_thread.

    Only links to RUNNING custom bots count: if a custom bot is disabled or in
    error (dead token), its guilds fall back to the official bot so the server
    keeps working. Both lineages run in one process and share this map, so the
    hand-off flips atomically for both identities — no double-handling window.
    """
    global _routing_map, _routing_loaded_at
    db = SessionLocal()
    try:
        rows = (
            db.query(Guild.id, Guild.custom_bot_id)
            .join(CustomBot, CustomBot.id == Guild.custom_bot_id)
            .filter(Guild.custom_bot_id.isnot(None), CustomBot.status == "active")
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


# ── AI-layer rate limits (Phase 16) ─────────────────────────────────────────────
_smartmod_last: dict[tuple[int, int], float] = {}   # (gid, uid) -> monotonic ts
_imageai_last: dict[int, float] = {}                # gid -> monotonic ts
_escalation_last: dict[tuple, float] = {}           # (gid, uid) / (gid, uid, type)
_dm_last: dict[tuple[int, int], float] = {}
_emoji_react_last: dict[tuple[int, int], float] = {}     # sentiment reactions
_reaction_xp_last: dict[tuple[int, int], float] = {}     # reaction XP per author
_kb_reply_last: dict[tuple[int, int], float] = {}        # KB auto-replies

_RATE_MAP_MAX_AGE = 3600  # entries older than this are dead weight


def _sweep_rate_maps() -> None:
    """Drop stale per-user rate-limit entries so the maps stay bounded."""
    cutoff = time.monotonic() - _RATE_MAP_MAX_AGE
    for m in (_smartmod_last, _imageai_last, _escalation_last, _dm_last,
              _emoji_react_last, _reaction_xp_last, _kb_reply_last):
        for key in [k for k, ts in m.items() if ts < cutoff]:
            m.pop(key, None)


# ── Emoji-reaction sentiment + text-command heuristics (dashboard parity) ───────
# Cheap keyword buckets — no AI cost; ordering = first matching bucket wins.
_SENTIMENT_BUCKETS = (
    ("😂", ("lol", "lmao", "rofl", "haha", "😂", "🤣")),
    ("🔥", ("fire", "hype", "let's go", "lets go", "lfg", "🔥", "insane", "crazy good")),
    ("🎉", ("congrat", "shipped", "released", "launched", "we won", "milestone", "🎉", "finally")),
    ("❤️", ("thank", "love", "appreciate", "awesome", "amazing", "great", "nice",
            "well done", "good job", "welcome", "glad")),
)

# Text-style command invocation: "!ban", "?rank", "$tip", ".kick", "/warn" as the
# first whitespace token. Slash commands sent through Discord's picker are
# interactions, not messages, so they never hit this.
_TEXT_CMD_RE = re.compile(r"^[!?$./][A-Za-z][\w-]{0,31}$")

_ESCALATION_LABELS = {
    "ai_kb": "AI knowledge base",
    "ai_image": "AI image review",
    "automation": "Automation error",
    "command": "Unknown command",
}


def _sentiment_emoji(text: str) -> str | None:
    low = (text or "").lower()
    if len(low) < 3:
        return None
    for emoji, needles in _SENTIMENT_BUCKETS:
        if any(n in low for n in needles):
            return emoji
    return None

# ── Activity buffers (Phase 15) — flushed every ~60s by process_mod_actions ────
_activity_buffer: dict[tuple[int, int], list] = {}   # (gid, uid) -> [add_msgs, username]
_daily_msg_buffer: dict[int, int] = {}                # gid -> messages


def _note_activity(guild_id: int, user_id: int, username: str, counted_by_leveling: bool) -> None:
    _daily_msg_buffer[guild_id] = _daily_msg_buffer.get(guild_id, 0) + 1
    entry = _activity_buffer.setdefault((guild_id, user_id), [0, username])
    if not counted_by_leveling:
        entry[0] += 1
    entry[1] = username


# ── Data retention (append-only tables would otherwise grow forever) ───────────
_RETENTION = (
    ("feature_usage_events", 180),
    ("bot_health_events", 90),
    ("automation_executions", 90),
)
_last_prune_day: str | None = None


def prune_old_rows() -> None:
    """Sync — call off-loop. Runs the deletes at most once per UTC day."""
    global _last_prune_day
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if _last_prune_day == today:
        return
    _last_prune_day = today
    from sqlalchemy import text as _text

    db = SessionLocal()
    try:
        for table, days in _RETENTION:
            cutoff = datetime.utcnow() - timedelta(days=days)
            db.execute(_text(f"DELETE FROM {table} WHERE created_at < :cutoff"),
                       {"cutoff": cutoff})
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("retention prune failed")
    finally:
        db.close()
        SessionLocal.remove()


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
        for gd in guilds:
            if serves(self, gd.id):
                await invite_tracking.refresh_guild(gd)

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
            if not message.author.bot:
                await self._handle_dm(message)
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
        counted = await self._maybe_award_xp(message)
        _note_activity(message.guild.id, message.author.id, str(message.author), counted)

        # Staff skip moderation + AI layers, but content features (auto-responses,
        # mirrors, workflows) still run for them.
        perms = getattr(message.author, "guild_permissions", None)
        is_staff = bool(perms and (perms.administrator or perms.manage_guild
                                   or perms.manage_messages))

        cfg = await asyncio.to_thread(self._load_moderation, message.guild.id)
        if is_staff or not cfg:
            if cfg:
                await self._maybe_emoji_react(message, cfg, is_staff=True)
            await self._maybe_auto_respond(message)
            await self._maybe_mirror(message)
            await self._run_workflows(
                "message_contains", message.guild,
                member=message.author, channel=message.channel,
                text=message.content or "",
            )
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
            action_taken = await self._execute_action(message, decision, cfg)
            await asyncio.to_thread(
                self._log, message.guild.id, decision["category"], action_taken,
                message.author.id, str(message.author), message.channel.id, decision["detail"],
            )
            await asyncio.to_thread(
                automation_runtime.dispatch_event, message.guild.id, "moderation_action",
                {"action": action_taken, "category": decision["category"],
                 "user_id": str(message.author.id), "username": str(message.author),
                 "detail": decision["detail"]},
            )
            if raid_guard.note_violation(message.guild.id, message.author.id, cfg):
                await self._raid_activated(message.guild, cfg)
        else:
            if raid_guard.note_message(message.guild.id, message.author.id, text, cfg):
                await self._raid_activated(message.guild, cfg)
            else:
                if await self._command_permissions_check(message, cfg):
                    return  # unauthorized command invocation deleted
                if await self._smart_mod_check(message, cfg):
                    return  # message acted on by the AI layer
                await self._image_ai_check(message, cfg)
                await self._escalation_check(message, cfg)
                await self._maybe_emoji_react(message, cfg, is_staff=False)
                responded = await self._maybe_auto_respond(message)
                if not responded:
                    await self._maybe_kb_reply(message, cfg)
                await self._maybe_mirror(message)
                await self._run_workflows(
                    "message_contains", message.guild,
                    member=message.author, channel=message.channel,
                    text=message.content or "",
                )

    async def _handle_dm(self, message: discord.Message) -> None:
        """DM assistant (Phase 17): AI replies grounded on the member's own
        tasks/reminders/notes. White-label bots answer as themselves — the
        custom-assistant lineage rides the same fleet."""
        if not ai.is_configured():
            await governor.safe(message.channel.send(
                "Hi! I can track things for you in servers — try /remind, /note or /task "
                "there. DM chat needs the AI assistant, which isn't configured yet."
            ), what="dm fallback")
            return
        key = (self.custom_bot_id or 0, message.author.id)
        if time.monotonic() - _dm_last.get(key, 0.0) < 5:
            return
        _dm_last[key] = time.monotonic()
        context = await asyncio.to_thread(self._personal_context, message.author.id)
        name = self.user.name if self.user else "Assistant"
        system = (
            f"You are {name}, a personal Discord assistant. Be brief, warm and useful. "
            "You can see the member's saved items below. You cannot take actions in DMs - "
            "tell them to use /task, /remind or /note in a server to add items.\n\n"
            + (f"MEMBER'S ITEMS:\n{context}" if context else "The member has no saved items yet.")
        )
        async with message.channel.typing():
            result = await asyncio.to_thread(ai.complete, system, message.content or "hi")
        if result is None or not result.text:
            await governor.safe(message.channel.send(
                "Sorry, I couldn't think of a reply just now - try again in a moment."
            ), what="dm error")
            return
        await asyncio.to_thread(self._log_ai, None, message.author.id, result)
        await governor.safe(message.channel.send(result.text[:1950]), what="dm reply")

    @staticmethod
    def _personal_context(user_id):
        db = SessionLocal()
        try:
            return assistant.personal_context(db, user_id)
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _add_task(user_id, guild_id, text):
        db = SessionLocal()
        try:
            t = assistant.add_task(db, user_id, guild_id, text)
            db.commit()
            return t.id
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _list_tasks(user_id):
        db = SessionLocal()
        try:
            return [(t.id, t.text) for t in assistant.list_tasks(db, user_id)]
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _complete_task(user_id, task_id):
        db = SessionLocal()
        try:
            ok = assistant.complete_task(db, user_id, task_id)
            db.commit()
            return ok
        finally:
            db.close()
            SessionLocal.remove()

    async def _smart_mod_check(self, message: discord.Message, cfg: dict) -> bool:
        """AI promo/spam layer. Returns True when the message was acted on."""
        sm = (cfg.get("automod") or {}).get("smart_mod") or {}
        if not sm.get("enabled") or not ai.is_configured():
            return False
        if str(message.author.id) in [str(t) for t in (sm.get("trusted_user_ids") or [])]:
            return False
        text = message.content or ""
        if len(text) < 20:   # too short to be meaningful promo
            return False
        key = (message.guild.id, message.author.id)
        limit = max(5, int(sm.get("ai_rate_limit_seconds", 30)))
        if time.monotonic() - _smartmod_last.get(key, 0.0) < limit:
            return False
        _smartmod_last[key] = time.monotonic()
        outcome = await asyncio.to_thread(ai.classify_promo, text, sm.get("group_topic") or "")
        if outcome is None:
            return False
        verdict, usage = outcome
        await asyncio.to_thread(self._log_ai, message.guild.id, message.author.id, usage)
        if verdict != "promo":
            return False
        decision = {"category": "smart_mod", "action": sm.get("action", "delete"),
                    "matched": "ai", "detail": "AI flagged as unsolicited promotion"}
        action_taken = await self._execute_action(message, decision, cfg)
        await asyncio.to_thread(
            self._log, message.guild.id, "smart_mod", action_taken,
            message.author.id, str(message.author), message.channel.id, decision["detail"],
        )
        return True

    async def _image_ai_check(self, message: discord.Message, cfg: dict) -> None:
        ia = (cfg.get("automod") or {}).get("image_ai") or {}
        if not ia.get("enabled") or not ai.is_configured() or not message.attachments:
            return
        limit = max(10, int(ia.get("rate_limit_seconds", 30)))
        if time.monotonic() - _imageai_last.get(message.guild.id, 0.0) < limit:
            return
        image = next((a for a in message.attachments
                      if (a.content_type or "").startswith("image/")), None)
        if image is None:
            return
        _imageai_last[message.guild.id] = time.monotonic()
        outcome = await asyncio.to_thread(ai.check_image, image.url)
        if outcome is None:
            return
        verdict, usage = outcome
        await asyncio.to_thread(self._log_ai, message.guild.id, message.author.id, usage)
        if verdict != "nsfw":
            # neither NSFW nor a clean OK = inconclusive — surface it if asked to
            first_word = (usage.text or "").strip().upper().strip(".,!\"'").split()[:1]
            if first_word != ["OK"]:
                await self._escalate_type(
                    message.guild, "ai_image",
                    f"Image review was inconclusive for a post by {message.author.mention} "
                    f"in {message.channel.mention} — {message.jump_url}",
                    user_id=message.author.id,
                )
            return
        decision = {"category": "image_nsfw", "action": ia.get("action", "delete"),
                    "matched": "image", "detail": "AI flagged image as NSFW"}
        action_taken = await self._execute_action(message, decision, cfg)
        await asyncio.to_thread(
            self._log, message.guild.id, "image_ai", action_taken,
            message.author.id, str(message.author), message.channel.id, decision["detail"],
        )

    async def _escalation_check(self, message: discord.Message, cfg: dict) -> None:
        """Frustration keywords -> alert admins (heuristic, no AI cost)."""
        esc = cfg.get("escalation") or {}
        keywords = esc.get("keywords") or []
        if not esc.get("enabled") or not keywords:
            return
        low = (message.content or "").lower()
        hit = next((k for k in keywords if k and k in low), None)
        if hit is None:
            return
        key = (message.guild.id, message.author.id)
        if time.monotonic() - _escalation_last.get(key, 0.0) < 600:   # 10 min per member
            return
        _escalation_last[key] = time.monotonic()
        await asyncio.to_thread(
            self._log, message.guild.id, "escalation", "alerted",
            message.author.id, str(message.author), message.channel.id, f"keyword: {hit}",
        )
        ch_id = esc.get("alert_channel_id")
        channel = message.guild.get_channel(int(ch_id)) if ch_id else None
        if channel is not None and hasattr(channel, "send"):
            await governor.safe(channel.send(
                f"🚨 **Attention needed**: {message.author.mention} in {message.channel.mention} "
                f"mentioned \"{hit}\" — {message.jump_url}"
            ), what="escalation alert")

    async def _escalate_type(self, guild: discord.Guild, type_key: str, text: str,
                             *, user_id: int | None = None) -> None:
        """Per-type escalation (escalation.types): alert the configured channel.
        Independent of the keyword toggle — the checkbox itself is the opt-in.
        One alert per (member, type) per 10 minutes."""
        cfg = await asyncio.to_thread(self._load_moderation, guild.id)
        esc = (cfg or {}).get("escalation") or {}
        if type_key not in (esc.get("types") or []):
            return
        key = (guild.id, user_id or 0, type_key)
        if time.monotonic() - _escalation_last.get(key, 0.0) < 600:
            return
        _escalation_last[key] = time.monotonic()
        await asyncio.to_thread(
            self._log, guild.id, "escalation", type_key, user_id, None, None, text[:200],
        )
        ch_id = esc.get("alert_channel_id")
        channel = guild.get_channel(int(ch_id)) if ch_id else None
        if channel is not None and hasattr(channel, "send"):
            label = _ESCALATION_LABELS.get(type_key, type_key)
            await governor.safe(channel.send(f"🚨 **{label}**: {text}"[:1900]),
                                what="type escalation alert")

    async def _maybe_emoji_react(self, message: discord.Message, cfg: dict,
                                 *, is_staff: bool) -> None:
        """Dashboard-parity emoji reactions: 👍 on admin messages, sentiment
        reactions (with a per-member cooldown) on member messages."""
        er = cfg.get("emoji_reactions") or {}
        if not er.get("enabled"):
            return
        if is_staff:
            if er.get("admin_thumbs_up"):
                await governor.safe(message.add_reaction("👍"), what="admin thumbs-up")
            return
        if not er.get("sentiment_reactions"):
            return
        emoji = _sentiment_emoji(message.content or "")
        if emoji is None:
            return
        cooldown = max(1, int(er.get("cooldown_minutes") or 10)) * 60
        key = (message.guild.id, message.author.id)
        if time.monotonic() - _emoji_react_last.get(key, 0.0) < cooldown:
            return
        _emoji_react_last[key] = time.monotonic()
        await governor.safe(message.add_reaction(emoji), what="sentiment reaction")

    async def _command_permissions_check(self, message: discord.Message, cfg: dict) -> bool:
        """Text-style command misuse ("!ban", ".kick" … from non-staff). Deletes
        the message when command_permissions.delete_unauthorized is on; also
        feeds the 'command' escalation type. Returns True when deleted."""
        text = (message.content or "").strip()
        first = text.split()[0] if text else ""
        if not _TEXT_CMD_RE.match(first):
            return False
        deleted = False
        if (cfg.get("command_permissions") or {}).get("delete_unauthorized"):
            deleted = bool(await governor.safe(message.delete(),
                                               what="delete unauthorized command"))
            if deleted:
                await asyncio.to_thread(
                    self._log, message.guild.id, "command_permissions", "deleted",
                    message.author.id, str(message.author), message.channel.id,
                    f"unauthorized command {first}",
                )
        await self._escalate_type(
            message.guild, "command",
            f"{message.author.mention} used unrecognised command `{first}` "
            f"in {message.channel.mention}",
            user_id=message.author.id,
        )
        return deleted

    async def _maybe_kb_reply(self, message: discord.Message, cfg: dict) -> bool:
        """KB auto-replies (kb_replies): answer member questions from the
        knowledge base with the configured tone. Returns True when replied."""
        kb = cfg.get("kb_replies") or {}
        if not kb.get("enabled") or not ai.is_configured():
            return False
        text = (message.content or "").strip()
        mentioned = bool(self.user and self.user in message.mentions)
        ref = message.reference.resolved if message.reference else None
        replied_to_me = bool(
            self.user and getattr(getattr(ref, "author", None), "id", None) == self.user.id
        )
        addressed = mentioned or replied_to_me
        if kb.get("mention_only", True):
            if not addressed:
                return False
        elif not addressed and "?" not in text:
            return False   # unaddressed statements aren't questions to answer
        question = re.sub(r"<@!?\d+>", "", text).strip()
        if len(question.split()) < max(1, int(kb.get("min_words") or 3)):
            return False
        key = (message.guild.id, message.author.id)
        if time.monotonic() - _kb_reply_last.get(key, 0.0) < 30:
            return False
        _kb_reply_last[key] = time.monotonic()

        system, confident = await asyncio.to_thread(
            knowledge.grounded_with_confidence, message.guild.id, question
        )
        if system is None:
            return False   # no knowledge base yet
        if not confident:
            await self._escalate_type(
                message.guild, "ai_kb",
                f"KB couldn't answer {message.author.mention} in "
                f"{message.channel.mention}: “{question[:120]}” — {message.jump_url}",
                user_id=message.author.id,
            )
            if kb.get("low_confidence_fallback"):
                await governor.safe(message.reply(
                    "I'm not sure about that one — a moderator can help. 🙏",
                    mention_author=False,
                ), what="kb fallback reply")
                return True
            return False

        length = {"short": "Answer in one or two sentences.",
                  "medium": "Answer in a short paragraph.",
                  "long": "Answer thoroughly, but stay on topic."}
        emoji_use = {"none": "Do not use emojis.",
                     "some": "An emoji or two is fine.",
                     "lots": "Use plenty of fitting emojis."}
        formality = {"casual": "Keep the tone casual and friendly.",
                     "neutral": "Keep the tone neutral.",
                     "formal": "Keep the tone professional and polite."}
        tone = " ".join((
            length.get(kb.get("reply_length") or "medium", length["medium"]),
            emoji_use.get(kb.get("emoji_usage") or "some", emoji_use["some"]),
            formality.get(kb.get("formality") or "casual", formality["casual"]),
        ))
        result = await asyncio.to_thread(ai.complete, f"{system}\n\n{tone}", question)
        if result is None or not result.text:
            return False
        await asyncio.to_thread(self._log_ai, message.guild.id, message.author.id, result)
        await governor.safe(message.reply(result.text[:1950], mention_author=False),
                            what="kb auto-reply")
        return True

    async def _maybe_auto_respond(self, message: discord.Message) -> bool:
        responses = await asyncio.to_thread(content_runtime.load_responses, message.guild.id)
        if not responses:
            return False
        hit = content_runtime.match_response(message.content or "", responses)
        if hit is None or not content_runtime.cooldown_ok(message.guild.id, hit):
            return False
        await governor.safe(message.reply(hit["response"], mention_author=False),
                            what="auto-response")
        return True

    async def _execute_action(self, message: discord.Message, decision: dict,
                              cfg: dict | None = None) -> str:
        action = decision["action"]
        member = message.author
        guild_id = message.guild.id
        reason = f"Guildizer: {decision['detail']}"
        # auto_clean: how long the bot's own warning text stays up (0 = keep)
        warn_secs = int(((cfg or {}).get("auto_clean") or {}).get("warn_messages_seconds") or 0)
        await governor.safe(message.delete(), what="delete flagged message")
        if action == "warn":
            await governor.safe(
                message.channel.send(moderation.warning_text(decision["category"]),
                                     delete_after=warn_secs or None),
                what="post warning",
            )
            await self._apply_xp_penalty(guild_id, member.id, str(member), "warn")
            escalation = await asyncio.to_thread(
                self._record_automod_warning, guild_id, member.id,
                str(member), decision["detail"],
            )
            if not escalation:
                return "warned"
            esc_action = escalation["action"]
            if esc_action == "timeout":
                await governor.safe(
                    member.timeout(timedelta(minutes=escalation["minutes"]), reason=reason),
                    what="ladder timeout",
                )
            elif esc_action == "kick":
                await governor.safe(member.kick(reason=reason), what="ladder kick")
            elif esc_action == "ban":
                await governor.safe(member.ban(reason=reason, delete_message_days=0), what="ladder ban")
            await self._apply_xp_penalty(guild_id, member.id, str(member), esc_action)
            return f"warned+{esc_action}"
        if action == "timeout":
            await governor.safe(member.timeout(timedelta(minutes=10), reason=reason), what="timeout")
            await self._apply_xp_penalty(guild_id, member.id, str(member), "timeout")
            return "timeout"
        if action == "kick":
            await governor.safe(member.kick(reason=reason), what="kick")
            await self._apply_xp_penalty(guild_id, member.id, str(member), "kick")
            return "kick"
        if action == "ban":
            await governor.safe(member.ban(reason=reason, delete_message_days=1), what="ban")
            await self._apply_xp_penalty(guild_id, member.id, str(member), "ban")
            return "ban"
        return "deleted"

    async def _apply_xp_penalty(self, guild_id: int, user_id: int, username: str,
                                kind: str) -> None:
        """Moderation XP penalty (leveling2.penalty_*). No-op when disabled."""
        if kind in ("warn", "timeout", "kick", "ban"):
            await asyncio.to_thread(self._do_apply_penalty, guild_id, user_id, username, kind)

    async def _raid_activated(self, guild: discord.Guild, cfg: dict) -> None:
        secs = raid_guard.seconds_remaining(guild.id)
        log.warning("Raid mode activated for guild %s (%ds)", guild.id, secs)
        await asyncio.to_thread(
            self._log, guild.id, "raid", "restricted", None, None, None, "Raid mode activated"
        )
        await asyncio.to_thread(
            automation_runtime.dispatch_event, guild.id, "raid_activated",
            {"seconds_remaining": secs},
        )
        if not cfg.get("rg_notify"):
            return
        ch_id = cfg.get("rg_notify_channel_id")
        channel = guild.get_channel(int(ch_id)) if ch_id else guild.system_channel
        if channel and hasattr(channel, "send"):
            await governor.safe(channel.send(raid_guard.activation_notice(secs)), what="raid notice")

    # --- leveling / XP ----------------------------------------------------------
    async def _maybe_award_xp(self, message: discord.Message) -> bool:
        """Returns True when leveling counted this message (levels enabled)."""
        cfg = await asyncio.to_thread(self._load_leveling, message.guild.id)
        if not cfg or not cfg.get("levels_enabled"):
            return False
        result = await asyncio.to_thread(
            self._do_award_xp, message.guild.id, message.author.id, str(message.author), cfg
        )
        if result is None:
            return True
        leveled_up, new_level = result
        if leveled_up:
            await self._announce_level_up(message.guild, message.author, new_level,
                                          cfg, message.channel)
        return True

    async def _announce_level_up(self, guild: discord.Guild, member, new_level: int,
                                 cfg: dict, fallback_channel) -> None:
        """Level-up announce (template + auto-delete) and level→role rewards."""
        l2 = cfg.get("leveling2") or {}
        if cfg.get("announce_level_up", True):
            text = leveling.render_levelup(
                cfg.get("levelup_message"),
                mention=member.mention, username=str(member), level=new_level,
            )
            delete_after = int(l2.get("levelup_delete_after_seconds") or 0) or None
            ch_id = cfg.get("levelup_channel_id")
            channel = guild.get_channel(int(ch_id)) if ch_id else fallback_channel
            if channel and hasattr(channel, "send"):
                await governor.safe(channel.send(text, delete_after=delete_after),
                                    what="level-up announce")
        rewards = l2.get("role_rewards") or []
        due = []
        for r in rewards:
            if int(r.get("level") or 0) <= new_level and r.get("role_id"):
                role = guild.get_role(int(r["role_id"]))
                if role is not None and role not in member.roles:
                    due.append(role)
        if due:
            await governor.safe(
                member.add_roles(*due, reason=f"Guildizer level {new_level} reward"),
                what="level role reward",
            )

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

        # optional private welcome DM (independent of the channel welcome)
        w2 = cfg.get("welcome2") or {}
        if w2.get("dm_enabled") and w2.get("dm_message"):
            await governor.safe(
                member.send(settings_mod.render_message(
                    w2["dm_message"], member=member, guild=member.guild)[:2000]),
                what="welcome DM",
            )

        await asyncio.to_thread(stats_runtime.bump_daily, member.guild.id, joins=1)
        attribution = await invite_tracking.attribute_join(member.guild)
        if attribution is not None:
            code, inviter_id, inviter_name = attribution
            if inviter_id != member.id:
                xp = await asyncio.to_thread(
                    invite_tracking.record_join, member.guild.id, code,
                    inviter_id, inviter_name, member.id, str(member),
                )
                await asyncio.to_thread(
                    self._log, member.guild.id, "referral", "join", member.id,
                    str(member), None,
                    f"invited by {inviter_name or inviter_id} via {code}"
                    + (f" (+{xp} XP)" if xp else ""),
                )

        await self._run_workflows("member_join", member.guild, member=member)
        await asyncio.to_thread(
            automation_runtime.dispatch_event, member.guild.id, "member_join",
            {"user_id": str(member.id), "username": str(member)},
        )

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
        if w2.get("ai_welcome") and ai.is_configured():
            result = await asyncio.to_thread(
                ai.complete,
                "Write ONE short, warm, original welcome sentence for a new Discord "
                "member. No emojis spam, no quotes around it.",
                f"Member name: {member.display_name}. Server: {guild.name}.",
                60,
            )
            if result is not None and result.text:
                await asyncio.to_thread(self._log_ai, guild.id, member.id, result)
                text = f"{text}\n{result.text}" if text else result.text
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
        if not member.bot:
            await asyncio.to_thread(stats_runtime.bump_daily, member.guild.id, leaves=1)
            await self._run_workflows("member_leave", member.guild, member=member)
            await asyncio.to_thread(
                automation_runtime.dispatch_event, member.guild.id, "member_leave",
                {"user_id": str(member.id), "username": str(member)},
            )
        cfg = await asyncio.to_thread(self._load_member_settings, member.guild.id)
        if not cfg or not (cfg["leave_enabled"] and cfg["leave_channel_id"]):
            return
        await self._send_to_channel(
            member.guild, cfg["leave_channel_id"],
            settings_mod.render_message(cfg["leave_message"], member=member, guild=member.guild),
        )

    # --- automation engine (Phase 13) -------------------------------------------
    async def _run_workflows(self, trigger_type: str, guild: discord.Guild, *,
                             member=None, channel=None, text: str | None = None,
                             emoji: str | None = None) -> None:
        flows = await asyncio.to_thread(
            automation_runtime.load_workflows, guild.id, trigger_type
        )
        for wf in flows:
            if not automation_runtime.matches(
                wf, text=text, channel_id=channel.id if channel else None, emoji=emoji,
            ):
                continue
            if not automation_runtime.cooldown_ok(wf):
                continue
            status, detail = "ok", None
            try:
                await self._run_workflow_actions(wf, guild, member=member, channel=channel)
            except Exception as exc:  # noqa: BLE001
                status, detail = "error", str(exc)[:300]
                log.exception("workflow %s failed", wf["id"])
            await asyncio.to_thread(
                automation_runtime.record_execution, wf["id"], guild.id, status, detail
            )
            if status == "error":
                await self._escalate_type(
                    guild, "automation", f"Workflow “{wf['name']}” failed: {detail}"
                )

    async def _run_workflow_actions(self, wf: dict, guild: discord.Guild, *,
                                    member=None, channel=None) -> None:
        username = str(member) if member is not None else ""
        for action in (wf.get("actions") or [])[:5]:
            atype = action.get("type")
            if atype == "send_message":
                target = None
                if action.get("channel_id"):
                    target = guild.get_channel(int(action["channel_id"]))
                if target is None:
                    target = channel
                text = automation_runtime.render(
                    action.get("text") or "", username=username,
                    server=guild.name or "", channel=getattr(channel, "name", "") or "",
                )
                if target is not None and hasattr(target, "send") and text:
                    await governor.safe(target.send(text), what="workflow send")
            elif atype in ("add_role", "remove_role") and member is not None:
                role = guild.get_role(int(action.get("role_id") or 0))
                if role is not None:
                    coro = (member.add_roles if atype == "add_role" else member.remove_roles)(
                        role, reason=f"Guildizer workflow: {wf['name']}"
                    )
                    await governor.safe(coro, what=f"workflow {atype}")
            elif atype == "timeout" and member is not None:
                mins = max(1, min(40320, int(action.get("minutes") or 10)))
                await governor.safe(
                    member.timeout(timedelta(minutes=mins),
                                   reason=f"Guildizer workflow: {wf['name']}"),
                    what="workflow timeout",
                )
            elif atype == "webhook" and action.get("url"):
                await asyncio.to_thread(
                    automation_runtime.post_workflow_webhook, action["url"],
                    {"event": "workflow_fired", "workflow": wf["name"],
                     "guild_id": str(guild.id), "user": username},
                )

    async def _maybe_mirror(self, message: discord.Message) -> None:
        rules = await asyncio.to_thread(
            automation_runtime.mirrors_for_channel, message.guild.id, message.channel.id
        )
        if not rules:
            return
        content = message.content or ""
        for att in message.attachments:
            content = content + ("\n" if content else "") + att.url
        if not content:
            return
        for rule in rules:
            url = rule["webhook_url"]
            if not url:
                dest = self.get_channel(int(rule["dest_channel_id"]))
                if dest is None or not hasattr(dest, "create_webhook"):
                    await asyncio.to_thread(
                        automation_runtime.save_mirror_webhook, rule["id"], None,
                        "Destination channel not reachable by this bot.",
                    )
                    continue
                try:
                    hook = await dest.create_webhook(name="Guildizer Mirror")
                    url = hook.url
                    await asyncio.to_thread(
                        automation_runtime.save_mirror_webhook, rule["id"], url
                    )
                except (discord.Forbidden, discord.HTTPException) as exc:
                    await asyncio.to_thread(
                        automation_runtime.save_mirror_webhook, rule["id"], None, str(exc)[:200]
                    )
                    continue
            try:
                webhook = discord.Webhook.from_url(url, client=self)
                await webhook.send(
                    content[:2000],
                    username=message.author.display_name[:80],
                    avatar_url=message.author.display_avatar.url,
                )
                await asyncio.to_thread(automation_runtime.bump_mirror, rule["id"])
            except (discord.NotFound, discord.Forbidden):
                # webhook was deleted on the destination side; recreate next time
                await asyncio.to_thread(
                    automation_runtime.save_mirror_webhook, rule["id"], None,
                    "Webhook missing - will recreate.",
                )
            except discord.HTTPException as exc:
                log.warning("mirror send failed for rule %s: %s", rule["id"], exc)

    async def on_app_command_completion(self, interaction: discord.Interaction, command) -> None:
        await asyncio.to_thread(
            stats_runtime.record_feature, interaction.guild_id,
            interaction.user.id if interaction.user else None,
            getattr(command, "qualified_name", None) or getattr(command, "name", "unknown"),
        )

    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is not None and serves(self, invite.guild.id):
            guild = self.get_guild(invite.guild.id)
            if guild is not None:
                await invite_tracking.refresh_guild(guild)

    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is not None and serves(self, invite.guild.id):
            guild = self.get_guild(invite.guild.id)
            if guild is not None:
                await invite_tracking.refresh_guild(guild)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or not serves(self, payload.guild_id):
            return
        guild = self.get_guild(payload.guild_id)
        if guild is None:
            return
        member = payload.member or guild.get_member(payload.user_id)
        if member is None or member.bot:
            return
        channel = guild.get_channel(payload.channel_id)
        await self_roles.handle_reaction(self, payload, member, add=True)
        await self._maybe_award_reaction_xp(guild, payload, channel)
        await self._run_workflows("reaction_add", guild, member=member, channel=channel,
                                  emoji=str(payload.emoji))

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or not serves(self, payload.guild_id):
            return
        guild = self.get_guild(payload.guild_id)
        if guild is None:
            return
        # raw remove events never carry .member; resolve from the cache instead
        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return
        await self_roles.handle_reaction(self, payload, member, add=False)

    async def _maybe_award_reaction_xp(self, guild: discord.Guild,
                                       payload: discord.RawReactionActionEvent,
                                       channel) -> None:
        """leveling2: XP for the author of a message that received a reaction,
        with its own per-author cooldown. Self-reactions never count."""
        author_id = getattr(payload, "message_author_id", None)
        if not author_id or author_id == payload.user_id:
            return
        cfg = await asyncio.to_thread(self._load_leveling, guild.id)
        if not cfg or not cfg.get("levels_enabled"):
            return
        l2 = cfg.get("leveling2") or {}
        amount = int(l2.get("xp_per_reaction") or 0)
        if amount <= 0:
            return
        author = guild.get_member(author_id)
        if author is None or author.bot:
            return
        cooldown = max(0, int(l2.get("reaction_cooldown_seconds") or 0))
        key = (guild.id, author_id)
        if time.monotonic() - _reaction_xp_last.get(key, 0.0) < cooldown:
            return
        _reaction_xp_last[key] = time.monotonic()
        result = await asyncio.to_thread(
            self._do_add_xp, guild.id, author_id, str(author), amount, "reaction"
        )
        if result and result[0]:
            await self._announce_level_up(guild, author, result[1], cfg, channel)

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

    # --- post campaigns + self-role menus the dashboard flagged -----------------
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
        try:
            await self_roles.process_pending(self)
        except Exception:  # noqa: BLE001
            log.exception("self-role post processing failed")

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

        # housekeeping: bounded rate maps + daily retention prune
        _sweep_rate_maps()
        if self.custom_bot_id is None:   # one identity owns the prune
            await asyncio.to_thread(prune_old_rows)

        # flush activity buffers (Phase 15)
        if _activity_buffer:
            items = [(gid, uid, entry[1], entry[0])
                     for (gid, uid), entry in _activity_buffer.items()]
            _activity_buffer.clear()
            await asyncio.to_thread(stats_runtime.flush_activity, items)
        if _daily_msg_buffer:
            pending = dict(_daily_msg_buffer)
            _daily_msg_buffer.clear()
            for gid, n in pending.items():
                await asyncio.to_thread(stats_runtime.bump_daily, gid, messages=n)

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
                                            row["user_id"], row["username"], None,
                                            "verification timed out")
            else:
                await asyncio.to_thread(self._log, guild.id, "verification", "expired",
                                        row["user_id"], row["username"], None,
                                        "challenge expired (kept)")

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
            if not sent and guild is not None:
                await self._escalate_type(
                    guild, "automation",
                    f"Scheduled message could not be sent (channel missing or no "
                    f"permission): “{(item['content'] or '')[:80]}”",
                )

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

        for item in await asyncio.to_thread(digest_runtime.due_guilds, served):
            guild = self.get_guild(item["guild_id"])
            channel = guild.get_channel(item["channel_id"]) if guild else None
            if guild is None or channel is None or not hasattr(channel, "send"):
                await asyncio.to_thread(digest_runtime.mark_posted, item["guild_id"])
                continue
            body = await asyncio.to_thread(
                digest_runtime.build_stats_text, guild.id, guild.name or "this server"
            )
            if ai.is_configured():
                result = await asyncio.to_thread(
                    ai.complete,
                    "Rewrite this Discord server daily digest as a short, upbeat "
                    "community update. Keep ALL the numbers. Max 5 lines.",
                    body, 250,
                )
                if result is not None and result.text:
                    await asyncio.to_thread(self._log_ai, guild.id, None, result)
                    body = result.text
            await governor.safe(channel.send(body[:1900]), what="daily digest")
            await asyncio.to_thread(digest_runtime.mark_posted, guild.id)

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
            if row is None:
                return None
            cfg = row.levels_to_dict()
            cfg["leveling2"] = {**settings_mod.LEVELING2_DEFAULTS,
                                **((row.extra or {}).get("leveling2") or {})}
            return cfg
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
        """Automod warning (moderator NULL). Returns the escalation dict
        ({"action", "minutes", "at", "reset"}) when a threshold/ladder step
        fires, else None. Legacy single-threshold escalations reset the count."""
        db = SessionLocal()
        try:
            snap = protection.load_snapshot(db, guild_id) or {}
            count, escalation = moderation_runtime.add_warning(
                db, guild_id, user_id, username, None, "automod", detail,
                snap.get("warnings") or {}, snap.get("warn_ladder") or {},
            )
            if escalation and escalation.get("reset"):
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
    def _do_apply_penalty(guild_id, user_id, username, kind):
        db = SessionLocal()
        try:
            removed = leveling.apply_penalty(db, guild_id, user_id, username, kind)
            db.commit()
            return removed
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("xp penalty failed for guild %s", guild_id)
            return 0
        finally:
            db.close()
            SessionLocal.remove()

    @staticmethod
    def _do_add_xp(guild_id, user_id, username, amount, reason):
        """Returns (leveled_up, new_level) or None on failure."""
        db = SessionLocal()
        try:
            _, leveled_up, new_level = leveling.add_xp(
                db, guild_id, user_id, amount, username, reason=reason)
            db.commit()
            return leveled_up, new_level
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("add_xp failed for guild %s", guild_id)
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
    invite_tracking.attach_invite_command(client)
    stats_runtime.attach_wallet_commands(client)

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
        when_str = f"<t:{assistant.utc_ts(due)}:R>" if hasattr(due, "timestamp") else "soon"
        await interaction.response.send_message(f"⏰ Okay! I'll remind you {when_str}: {text}", ephemeral=True)

    @client.tree.command(name="reminders", description="List your pending reminders.")
    async def reminders(interaction: discord.Interaction) -> None:
        rows = await asyncio.to_thread(CoreMixin._list_reminders, interaction.user.id)
        if not rows:
            await interaction.response.send_message("You have no pending reminders.", ephemeral=True)
            return
        lines = [f"• {text} — <t:{assistant.utc_ts(due)}:R>" for text, due in rows]
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

    @client.tree.command(name="task", description="Add a personal task. e.g. /task ship the update")
    @app_commands.describe(text="The task")
    async def task(interaction: discord.Interaction, text: str) -> None:
        task_id = await asyncio.to_thread(
            CoreMixin._add_task, interaction.user.id, interaction.guild_id, text
        )
        await interaction.response.send_message(f"✅ Task [{task_id}] added: {text}", ephemeral=True)

    @client.tree.command(name="tasks", description="List your open tasks.")
    async def tasks_cmd(interaction: discord.Interaction) -> None:
        rows = await asyncio.to_thread(CoreMixin._list_tasks, interaction.user.id)
        if not rows:
            await interaction.response.send_message("No open tasks. 🎉", ephemeral=True)
            return
        lines = [f"• [{tid}] {text}" for tid, text in rows]
        await interaction.response.send_message(
            "🗒️ **Your open tasks**\n" + "\n".join(lines)[:1900]
            + "\nFinish one with /done <id>.", ephemeral=True,
        )

    @client.tree.command(name="done", description="Mark one of your tasks as done. e.g. /done 3")
    @app_commands.describe(task_id="The task number from /tasks")
    async def done(interaction: discord.Interaction, task_id: int) -> None:
        ok = await asyncio.to_thread(CoreMixin._complete_task, interaction.user.id, task_id)
        if ok:
            await interaction.response.send_message(f"✅ Task [{task_id}] done — nice.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "I couldn't find that open task of yours — check /tasks.", ephemeral=True
            )

    @client.tree.command(name="ask", description="Ask the AI assistant a question.")
    @app_commands.describe(question="Your question")
    async def ask(interaction: discord.Interaction, question: str) -> None:
        if not ai.is_configured():
            await interaction.response.send_message(
                "🤖 The AI assistant isn't configured on this server yet.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        system, confident = None, True
        if interaction.guild_id:
            system, confident = await asyncio.to_thread(
                knowledge.grounded_with_confidence, interaction.guild_id, question)
        if system and not confident and interaction.guild is not None:
            await client._escalate_type(
                interaction.guild, "ai_kb",
                f"/ask had low KB confidence for {interaction.user.mention}: "
                f"“{question[:120]}”",
                user_id=interaction.user.id,
            )
        if system:
            result = await asyncio.to_thread(ai.complete, system, question)
        else:
            result = await asyncio.to_thread(ai.ask, question)
        if result is None:
            await interaction.followup.send("Sorry, I couldn't answer that right now.", ephemeral=True)
            return
        await asyncio.to_thread(CoreMixin._log_ai, interaction.guild_id, interaction.user.id, result)
        await interaction.followup.send(result.text[:1950], ephemeral=True)
