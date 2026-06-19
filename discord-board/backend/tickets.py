"""Ticket system: button -> private support thread, transcript on close. Both lineages.

Admins configure a panel in the dashboard (GuildSettings.extra["tickets"], no
migration needed) and queue it; the bot's 20s post loop publishes the panel
with a persistent Open button (DynamicItem — survives restarts). Clicking it
creates a private thread for the member, pings the support role into it, and
drops a Close button. Closing builds a text transcript, posts it to the
configured transcript channel, and locks + archives the thread.

Open tickets are tracked in extra["tickets"]["open"] keyed by thread id —
bounded by what's actually open, so no table is needed. Threads deleted by
hand are forgotten via on_raw_thread_delete.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import datetime

import discord

import governor
import settings as settings_mod
from database import SessionLocal
from models import GuildSettings

log = logging.getLogger("guildizer.tickets")

ACCENT = 0x5865F2
TRANSCRIPT_MESSAGE_LIMIT = 500   # plenty for a support thread; noted when hit


def merged(extra: dict | None) -> dict:
    return {**settings_mod.TICKETS_DEFAULTS, **((extra or {}).get("tickets") or {})}


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


def _update(guild_id: int, patch: dict) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return
        extra = dict(row.extra or {})
        extra["tickets"] = {**merged(row.extra), **patch}
        row.extra = extra
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("ticket settings update failed for guild %s", guild_id)
    finally:
        db.close()
        SessionLocal.remove()


def next_number(guild_id: int) -> int:
    """Reserve the next lifetime ticket number. Returns 0 on failure."""
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return 0
        cfg = merged(row.extra)
        number = int(cfg.get("counter") or 0) + 1
        extra = dict(row.extra or {})
        extra["tickets"] = {**cfg, "counter": number}
        row.extra = extra
        db.commit()
        return number
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("next_number failed for guild %s", guild_id)
        return 0
    finally:
        db.close()
        SessionLocal.remove()


def record_open(guild_id: int, thread_id: int, user_id: int, username: str,
                number: int) -> None:
    """Register a newly created ticket thread under its reserved number."""
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return
        cfg = merged(row.extra)
        open_map = dict(cfg.get("open") or {})
        open_map[str(thread_id)] = {
            "user_id": str(user_id),
            "username": username[:100],
            "number": number,
            "opened_at": datetime.utcnow().isoformat(),
        }
        extra = dict(row.extra or {})
        extra["tickets"] = {**cfg, "open": open_map}
        row.extra = extra
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("record_open failed for guild %s", guild_id)
    finally:
        db.close()
        SessionLocal.remove()


def close_entry(guild_id: int, thread_id: int) -> dict | None:
    """Remove the open-ticket record for this thread; returns it (or None)."""
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return None
        cfg = merged(row.extra)
        open_map = dict(cfg.get("open") or {})
        entry = open_map.pop(str(thread_id), None)
        if entry is None:
            return None
        extra = dict(row.extra or {})
        extra["tickets"] = {**cfg, "open": open_map}
        row.extra = extra
        db.commit()
        return entry
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("close_entry failed for guild %s", guild_id)
        return None
    finally:
        db.close()
        SessionLocal.remove()


def forget_thread(guild_id: int, thread_id: int) -> None:
    """A ticket thread was deleted out from under us — drop its record."""
    close_entry(guild_id, thread_id)


def mark_claimed(guild_id: int, thread_id: int, claimer_id: int, claimer_name: str) -> bool:
    """Record who claimed a ticket. Returns False if already claimed or unknown."""
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return False
        cfg = merged(row.extra)
        open_map = dict(cfg.get("open") or {})
        entry = open_map.get(str(thread_id))
        if entry is None or entry.get("claimed_by"):
            return False
        entry = {**entry, "claimed_by": str(claimer_id), "claimed_by_name": claimer_name[:100]}
        open_map[str(thread_id)] = entry
        extra = dict(row.extra or {})
        extra["tickets"] = {**cfg, "open": open_map}
        row.extra = extra
        db.commit()
        return True
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("mark_claimed failed for guild %s", guild_id)
        return False
    finally:
        db.close()
        SessionLocal.remove()


def count_open_for(cfg: dict, user_id: int) -> int:
    return sum(1 for t in (cfg.get("open") or {}).values()
               if str(t.get("user_id")) == str(user_id))


def pending_panels() -> list[tuple[int, str]]:
    """(guild_id, "post"|"delete") for every queued ticket panel."""
    out: list[tuple[int, str]] = []
    db = SessionLocal()
    try:
        rows = (
            db.query(GuildSettings.guild_id, GuildSettings.extra)
            .filter(GuildSettings.extra.isnot(None))
            .all()
        )
        for gid, extra in rows:
            t = (extra or {}).get("tickets") or {}
            if t.get("needs_delete"):
                out.append((gid, "delete"))
            elif t.get("needs_post"):
                out.append((gid, "post"))
        return out
    finally:
        db.close()
        SessionLocal.remove()


def mark_panel_posted(guild_id: int, message_id: int) -> None:
    _update(guild_id, {"panel_message_id": str(message_id),
                       "needs_post": False, "post_error": None})


def mark_panel_failed(guild_id: int, error: str) -> None:
    _update(guild_id, {"needs_post": False, "post_error": error[:200]})


def mark_panel_deleted(guild_id: int) -> None:
    _update(guild_id, {"panel_message_id": None,
                       "needs_post": False, "needs_delete": False})


# ── permissions ────────────────────────────────────────────────────────────────
def _is_support(member: discord.Member, cfg: dict) -> bool:
    perms = getattr(member, "guild_permissions", None)
    if perms and (perms.administrator or perms.manage_guild or perms.manage_messages):
        return True
    rid = cfg.get("support_role_id")
    return bool(rid and str(rid).isdigit()
                and any(r.id == int(rid) for r in member.roles))


def _thread_name(number: int, member: discord.Member) -> str:
    base = re.sub(r"\s+", "-", member.display_name).strip("-") or "member"
    return f"ticket-{number:04d}-{base}"[:100]


# ── persistent buttons ─────────────────────────────────────────────────────────
class TicketOpenButton(discord.ui.DynamicItem[discord.ui.Button],
                       template=r"gz:ticket:(?P<gid>\d+)"):
    def __init__(self, gid: int, label: str = "🎫 Open a ticket") -> None:
        self.gid = gid
        super().__init__(discord.ui.Button(
            label=label[:80], style=discord.ButtonStyle.primary,
            custom_id=f"gz:ticket:{gid}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["gid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        cfg = await asyncio.to_thread(snapshot, guild.id)
        if not cfg or not cfg.get("enabled"):
            await interaction.response.send_message(
                "Tickets are currently disabled on this server.", ephemeral=True)
            return
        max_open = max(1, int(cfg.get("max_open_per_member") or 1))
        if count_open_for(cfg, member.id) >= max_open:
            await interaction.response.send_message(
                "You already have an open ticket — please use that one.", ephemeral=True)
            return
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Tickets can only be opened from a text channel.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        # Reserve the number first so two quick clicks can't share one.
        number = await asyncio.to_thread(next_number, guild.id)
        if not number:
            await interaction.followup.send("Something went wrong — try again.", ephemeral=True)
            return
        try:
            thread = await channel.create_thread(
                name=_thread_name(number, member),
                type=discord.ChannelType.private_thread,
                invitable=False,
                reason=f"Guildizer ticket #{number} for {member}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I can't create private threads here — an admin should grant me "
                "**Create Private Threads** in this channel.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            log.warning("ticket thread create failed for guild %s: %s", guild.id, exc)
            await interaction.followup.send(
                "Discord wouldn't let me open a thread just now — try again shortly.",
                ephemeral=True)
            return

        await asyncio.to_thread(record_open, guild.id, thread.id, member.id,
                                str(member), number)
        rid = cfg.get("support_role_id")
        support_ping = f" <@&{int(rid)}>" if rid and str(rid).isdigit() else ""
        lines = [f"🎫 **Ticket #{number:04d}** — {member.mention}{support_ping}"]
        if cfg.get("welcome_message"):
            lines.append(str(cfg["welcome_message"])[:1500])
        lines.append("A staff member will be with you shortly. "
                     "Close the ticket when you're done.")
        view = discord.ui.View(timeout=None)
        view.add_item(TicketClaimButton(guild.id))
        view.add_item(TicketCloseButton(guild.id))
        # Mentioning the support role pulls its members into the private thread.
        await governor.safe(thread.send(
            "\n".join(lines)[:1900], view=view,
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        ), what="ticket opening message")

        # Staff alert: a separate "new ticket" notice in the configured channel so
        # admins see it even when they're not watching the thread/role ping.
        alert_id = cfg.get("alert_channel_id")
        alert_ch = guild.get_channel(int(alert_id)) if alert_id and str(alert_id).isdigit() else None
        if alert_ch is not None and hasattr(alert_ch, "send"):
            embed = discord.Embed(
                title=f"🎫 New ticket #{number:04d}",
                description=(f"{member.mention} opened a support ticket.\n"
                            f"Jump in: {thread.mention}"),
                color=ACCENT,
            )
            await governor.safe(alert_ch.send(
                content=support_ping or None, embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True),
            ), what="ticket staff alert")

        await interaction.followup.send(
            f"✅ Your ticket is open: {thread.mention}", ephemeral=True)


class TicketClaimButton(discord.ui.DynamicItem[discord.ui.Button],
                        template=r"gz:tclaim:(?P<gid>\d+)"):
    """Lets support staff claim a ticket so everyone sees who's handling it."""
    def __init__(self, gid: int) -> None:
        self.gid = gid
        super().__init__(discord.ui.Button(
            label="Claim", style=discord.ButtonStyle.success, emoji="🙋",
            custom_id=f"gz:tclaim:{gid}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["gid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        member = interaction.user
        thread = interaction.channel
        if guild is None or not isinstance(member, discord.Member) \
                or not isinstance(thread, discord.Thread):
            await interaction.response.send_message("Use this inside a ticket.", ephemeral=True)
            return
        cfg = await asyncio.to_thread(snapshot, guild.id) or {}
        if not _is_support(member, cfg):
            await interaction.response.send_message(
                "Only support staff can claim tickets.", ephemeral=True)
            return
        entry = (cfg.get("open") or {}).get(str(thread.id))
        if entry and entry.get("claimed_by"):
            await interaction.response.send_message(
                f"Already claimed by {entry.get('claimed_by_name') or 'a staff member'}.",
                ephemeral=True)
            return
        ok = await asyncio.to_thread(mark_claimed, guild.id, thread.id, member.id, str(member))
        if not ok:
            await interaction.response.send_message(
                "Couldn't claim this ticket — it may already be claimed or closed.", ephemeral=True)
            return
        await interaction.response.send_message(f"🙋 {member.mention} has claimed this ticket.")


class TicketCloseButton(discord.ui.DynamicItem[discord.ui.Button],
                        template=r"gz:tclose:(?P<gid>\d+)"):
    def __init__(self, gid: int) -> None:
        self.gid = gid
        super().__init__(discord.ui.Button(
            label="Close ticket", style=discord.ButtonStyle.secondary, emoji="🔒",
            custom_id=f"gz:tclose:{gid}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["gid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        member = interaction.user
        thread = interaction.channel
        if guild is None or not isinstance(member, discord.Member) \
                or not isinstance(thread, discord.Thread):
            await interaction.response.send_message("Use this inside a ticket.", ephemeral=True)
            return
        cfg = await asyncio.to_thread(snapshot, guild.id) or {}
        entry = (cfg.get("open") or {}).get(str(thread.id))
        if entry is None:
            await interaction.response.send_message(
                "This thread isn't an open ticket.", ephemeral=True)
            return
        is_opener = str(entry.get("user_id")) == str(member.id)
        if not is_opener and not _is_support(member, cfg):
            await interaction.response.send_message(
                "Only the ticket opener or support staff can close this.", ephemeral=True)
            return

        await interaction.response.defer()   # transcript can take a moment
        await asyncio.to_thread(close_entry, guild.id, thread.id)
        await self._post_transcript(guild, thread, entry, cfg, closed_by=member)
        try:
            await interaction.followup.send(
                f"🔒 Ticket closed by {member.mention}. This thread is now archived.")
        except discord.HTTPException:
            pass
        await governor.safe(thread.edit(archived=True, locked=True),
                            what="archive ticket thread")

    @staticmethod
    async def _post_transcript(guild: discord.Guild, thread: discord.Thread,
                               entry: dict, cfg: dict, *, closed_by) -> None:
        ch_id = cfg.get("transcript_channel_id")
        channel = guild.get_channel(int(ch_id)) if ch_id and str(ch_id).isdigit() else None
        if channel is None or not hasattr(channel, "send"):
            return
        lines = [
            f"Transcript of {thread.name} ({guild.name})",
            f"Opened by: {entry.get('username') or entry.get('user_id')} "
            f"at {entry.get('opened_at') or 'unknown'}",
            f"Closed by: {closed_by} at {datetime.utcnow().isoformat()}",
            "-" * 60,
        ]
        count = 0
        try:
            async for msg in thread.history(limit=TRANSCRIPT_MESSAGE_LIMIT,
                                            oldest_first=True):
                stamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
                body = msg.content or ""
                for att in msg.attachments:
                    body += ("\n" if body else "") + f"[attachment] {att.url}"
                lines.append(f"[{stamp}] {msg.author}: {body}")
                count += 1
        except discord.HTTPException as exc:
            lines.append(f"[transcript truncated: {exc}]")
        if count >= TRANSCRIPT_MESSAGE_LIMIT:
            lines.append(f"[only the first {TRANSCRIPT_MESSAGE_LIMIT} messages are included]")
        data = io.BytesIO("\n".join(lines).encode("utf-8"))
        number = int(entry.get("number") or 0)
        await governor.safe(channel.send(
            f"📑 Transcript for **ticket #{number:04d}** "
            f"(opened by {entry.get('username') or 'unknown'}, closed by {closed_by})",
            file=discord.File(data, filename=f"{thread.name}.txt"),
        ), what="ticket transcript")


# ── panel posting (called from the bot's 20s post loop) ────────────────────────
async def _delete_panel(guild: discord.Guild, cfg: dict) -> None:
    ch_id, msg_id = cfg.get("panel_channel_id"), cfg.get("panel_message_id")
    if ch_id and msg_id:
        channel = guild.get_channel(int(ch_id))
        if channel is not None:
            try:
                old = await channel.fetch_message(int(msg_id))
                await old.delete()
            except Exception:  # noqa: BLE001 — already gone is fine
                pass


async def process_pending(bot) -> None:
    """Publish/remove queued ticket panels for every guild this bot serves."""
    from bot_core import serves   # local import — bot_core imports this module

    for gid, action in await asyncio.to_thread(pending_panels):
        if not serves(bot, gid):
            continue
        guild = bot.get_guild(gid)
        cfg = await asyncio.to_thread(snapshot, gid)
        if guild is None or cfg is None:
            continue
        if action == "delete":
            await _delete_panel(guild, cfg)
            await asyncio.to_thread(mark_panel_deleted, gid)
            continue

        channel = guild.get_channel(int(cfg["panel_channel_id"])) \
            if cfg.get("panel_channel_id") else None
        if channel is None or not hasattr(channel, "send"):
            await asyncio.to_thread(mark_panel_failed, gid, "channel not found")
            continue

        await _delete_panel(guild, cfg)   # re-post replaces the old panel
        embed = discord.Embed(
            title=(cfg.get("panel_title") or "Need help?")[:256],
            description=(cfg.get("panel_message") or "")[:2000] or None,
            color=ACCENT,
        )
        view = discord.ui.View(timeout=None)
        view.add_item(TicketOpenButton(gid, label=str(cfg.get("button_label") or "🎫 Open a ticket")))
        try:
            msg = await channel.send(embed=embed, view=view)
            await asyncio.to_thread(mark_panel_posted, gid, msg.id)
            log.info("Posted ticket panel for guild %s", gid)
        except discord.Forbidden:
            await asyncio.to_thread(mark_panel_failed, gid, "missing permission to post")
        except discord.HTTPException as exc:
            await asyncio.to_thread(mark_panel_failed, gid, str(exc))
