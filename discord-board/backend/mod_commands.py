"""Moderation slash-command suite (Phase 10), shared by BOTH bot lineages.

attach_mod_commands(client) registers: /warn /warnings /removewarning /mute
/unmute /kick /ban /unban /tempban /purge /userinfo /auditlog /report and a
right-click "Report Message" context command.

Permission model: commands are hidden from members without the matching Discord
permission (default_permissions) AND re-checked at runtime (defense in depth).
Every action writes a ProtectionEvent so the dashboard activity feed sees it.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import discord
from discord import app_commands

import assistant
import governor
import moderation_runtime as modrt
import protection
from database import SessionLocal
from models import ProtectionEvent

log = logging.getLogger("guildizer.modcmds")

MAX_TIMEOUT_DAYS = 28   # Discord's hard cap on member timeouts


# --- sync DB wrappers (run via asyncio.to_thread) -------------------------------
def _db_call(fn, *args, **kwargs):
    db = SessionLocal()
    try:
        result = fn(db, *args, **kwargs)
        db.commit()
        return result
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("moderation DB call failed: %s", getattr(fn, "__name__", fn))
        return None
    finally:
        db.close()
        SessionLocal.remove()


def _ladder_cfg(guild_id: int) -> dict:
    db = SessionLocal()
    try:
        snap = protection.load_snapshot(db, guild_id) or {}
        return snap.get("warnings") or {"max_warnings": 3, "action": "timeout", "timeout_minutes": 30}
    finally:
        db.close()
        SessionLocal.remove()


def _log_event(guild_id, category, action, user_id=None, username=None, detail=None):
    def _do(db):
        protection.log_event(db, guild_id, category, action,
                             user_id=user_id, username=username, detail=detail)
    _db_call(_do)


def _warning_rows(guild_id: int, user_id: int, limit: int):
    """Plain tuples extracted inside the session (rows detach after close)."""
    db = SessionLocal()
    try:
        rows = modrt.list_warnings(db, guild_id, user_id, limit)
        return [(w.created_at, w.moderator_name, w.reason) for w in rows]
    finally:
        db.close()
        SessionLocal.remove()


def _recent_events(guild_id: int, limit: int):
    db = SessionLocal()
    try:
        rows = (
            db.query(ProtectionEvent)
            .filter(ProtectionEvent.guild_id == guild_id)
            .order_by(ProtectionEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return [(e.created_at, e.category, e.action, e.username, e.detail) for e in rows]
    finally:
        db.close()
        SessionLocal.remove()


# --- shared guards ---------------------------------------------------------------
async def _deny(interaction: discord.Interaction, msg: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


def _has(interaction: discord.Interaction, **perm_flags) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    if perms is None:
        return False
    if perms.administrator:
        return True
    return all(getattr(perms, name, False) for name in perm_flags)


async def _check_target(interaction: discord.Interaction, member: discord.Member) -> str | None:
    """None if the target is actionable, else the reason it isn't."""
    if member.id == interaction.user.id:
        return "You can't moderate yourself."
    if member.id == interaction.client.user.id:
        return "Nice try — I can't moderate myself."
    if member.id == interaction.guild.owner_id:
        return "The server owner can't be moderated."
    me = interaction.guild.me
    if me and member.top_role >= me.top_role:
        return "That member's role is above mine — move my role higher to moderate them."
    return None


async def _apply_ladder(interaction: discord.Interaction, member: discord.Member,
                        action: str, ladder: dict) -> str:
    """Execute the escalation action when a member hits max warnings."""
    reason = f"Guildizer: reached {ladder.get('max_warnings', 3)} warnings"
    if action == "timeout":
        mins = max(1, int(ladder.get("timeout_minutes", 30)))
        ok = await governor.safe(member.timeout(timedelta(minutes=mins), reason=reason),
                                 what="ladder timeout")
        return f"timed out {mins}m" if ok else "timeout failed"
    if action == "kick":
        ok = await governor.safe(member.kick(reason=reason), what="ladder kick")
        return "kicked" if ok else "kick failed"
    if action == "ban":
        ok = await governor.safe(member.ban(reason=reason, delete_message_days=0), what="ladder ban")
        return "banned" if ok else "ban failed"
    return "no action"


# --- registration -----------------------------------------------------------------
def attach_mod_commands(client) -> None:  # noqa: C901  (a flat list of commands)
    tree = client.tree

    @tree.command(name="warn", description="Warn a member (counts toward the warning ladder).")
    @app_commands.describe(member="Who to warn", reason="Why")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if interaction.guild is None or not _has(interaction, moderate_members=True):
            return await _deny(interaction, "You need the Timeout Members permission.")
        problem = await _check_target(interaction, member)
        if problem:
            return await _deny(interaction, problem)
        ladder = await asyncio.to_thread(_ladder_cfg, interaction.guild.id)
        result = await asyncio.to_thread(
            _db_call, modrt.add_warning, interaction.guild.id, member.id, str(member),
            interaction.user.id, str(interaction.user), reason, ladder,
        )
        if result is None:
            return await _deny(interaction, "Couldn't record the warning — try again.")
        count, escalation = result
        msg = f"⚠️ Warned {member.mention} ({count}/{ladder.get('max_warnings', 3)}): {reason}"
        if escalation:
            outcome = await _apply_ladder(interaction, member, escalation, ladder)
            await asyncio.to_thread(_db_call, modrt.clear_warnings, interaction.guild.id, member.id)
            msg += f"\n🚨 Warning limit reached — {outcome}; warnings reset."
        await asyncio.to_thread(_log_event, interaction.guild.id, "warning",
                                escalation or "warned", member.id, str(member), reason)
        await interaction.response.send_message(msg)

    @tree.command(name="warnings", description="List a member's warnings.")
    @app_commands.default_permissions(moderate_members=True)
    async def warnings_cmd(interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None or not _has(interaction, moderate_members=True):
            return await _deny(interaction, "You need the Timeout Members permission.")
        rows = await asyncio.to_thread(_warning_rows, interaction.guild.id, member.id, 10)
        if not rows:
            return await _deny(interaction, f"{member.display_name} has no warnings. ✨")
        lines = [
            f"• <t:{assistant.utc_ts(created)}:R> by {mod_name or 'automod'} — {reason or 'no reason'}"
            for created, mod_name, reason in rows
        ]
        await interaction.response.send_message(
            f"⚠️ **Warnings for {member.display_name}** ({len(rows)} shown)\n" + "\n".join(lines),
            ephemeral=True,
        )

    @tree.command(name="removewarning", description="Remove a member's most recent warning.")
    @app_commands.default_permissions(moderate_members=True)
    async def removewarning(interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None or not _has(interaction, moderate_members=True):
            return await _deny(interaction, "You need the Timeout Members permission.")
        ok = await asyncio.to_thread(
            _db_call, modrt.remove_latest_warning, interaction.guild.id, member.id
        )
        if not ok:
            return await _deny(interaction, f"{member.display_name} has no warnings to remove.")
        await asyncio.to_thread(_log_event, interaction.guild.id, "warning", "removed",
                                member.id, str(member), "warning removed")
        await interaction.response.send_message(f"✅ Removed the latest warning for {member.mention}.")

    @tree.command(name="mute", description="Timeout a member. e.g. /mute @user 2h spam")
    @app_commands.describe(member="Who", duration="10m, 2h, 1d… (max 28d)", reason="Why")
    @app_commands.default_permissions(moderate_members=True)
    async def mute(interaction: discord.Interaction, member: discord.Member,
                   duration: str, reason: str = "No reason given") -> None:
        if interaction.guild is None or not _has(interaction, moderate_members=True):
            return await _deny(interaction, "You need the Timeout Members permission.")
        problem = await _check_target(interaction, member)
        if problem:
            return await _deny(interaction, problem)
        seconds = assistant.parse_duration(duration)
        if not seconds:
            return await _deny(interaction, "I couldn't read that duration. Try `10m`, `2h`, `1d`.")
        seconds = min(seconds, MAX_TIMEOUT_DAYS * 86400)
        ok = await governor.safe(
            member.timeout(timedelta(seconds=seconds), reason=f"Guildizer ({interaction.user}): {reason}"),
            what="mute",
        )
        if not ok:
            return await _deny(interaction, "Timeout failed — check my role position and permissions.")
        await asyncio.to_thread(_log_event, interaction.guild.id, "moderation", "timeout",
                                member.id, str(member), f"{duration} — {reason}")
        await interaction.response.send_message(f"🔇 Muted {member.mention} for {duration}: {reason}")

    @tree.command(name="unmute", description="Remove a member's timeout.")
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None or not _has(interaction, moderate_members=True):
            return await _deny(interaction, "You need the Timeout Members permission.")
        ok = await governor.safe(member.timeout(None, reason=f"Guildizer ({interaction.user}): unmute"),
                                 what="unmute")
        if not ok:
            return await _deny(interaction, "Unmute failed — check my permissions.")
        await asyncio.to_thread(_log_event, interaction.guild.id, "moderation", "untimeout",
                                member.id, str(member), None)
        await interaction.response.send_message(f"🔊 Unmuted {member.mention}.")

    @tree.command(name="kick", description="Kick a member from the server.")
    @app_commands.default_permissions(kick_members=True)
    async def kick(interaction: discord.Interaction, member: discord.Member,
                   reason: str = "No reason given") -> None:
        if interaction.guild is None or not _has(interaction, kick_members=True):
            return await _deny(interaction, "You need the Kick Members permission.")
        problem = await _check_target(interaction, member)
        if problem:
            return await _deny(interaction, problem)
        ok = await governor.safe(member.kick(reason=f"Guildizer ({interaction.user}): {reason}"), what="kick")
        if not ok:
            return await _deny(interaction, "Kick failed — check my role position and permissions.")
        await asyncio.to_thread(_log_event, interaction.guild.id, "moderation", "kick",
                                member.id, str(member), reason)
        await interaction.response.send_message(f"👢 Kicked **{member.display_name}**: {reason}")

    @tree.command(name="ban", description="Ban a member.")
    @app_commands.describe(member="Who", reason="Why", delete_days="Delete their messages from the last N days (0–7)")
    @app_commands.default_permissions(ban_members=True)
    async def ban(interaction: discord.Interaction, member: discord.Member,
                  reason: str = "No reason given",
                  delete_days: app_commands.Range[int, 0, 7] = 1) -> None:
        if interaction.guild is None or not _has(interaction, ban_members=True):
            return await _deny(interaction, "You need the Ban Members permission.")
        problem = await _check_target(interaction, member)
        if problem:
            return await _deny(interaction, problem)
        ok = await governor.safe(
            member.ban(reason=f"Guildizer ({interaction.user}): {reason}", delete_message_days=delete_days),
            what="ban",
        )
        if not ok:
            return await _deny(interaction, "Ban failed — check my role position and permissions.")
        await asyncio.to_thread(_log_event, interaction.guild.id, "moderation", "ban",
                                member.id, str(member), reason)
        await interaction.response.send_message(f"🔨 Banned **{member.display_name}**: {reason}")

    @tree.command(name="unban", description="Unban a user by their Discord user ID.")
    @app_commands.default_permissions(ban_members=True)
    async def unban(interaction: discord.Interaction, user_id: str,
                    reason: str = "No reason given") -> None:
        if interaction.guild is None or not _has(interaction, ban_members=True):
            return await _deny(interaction, "You need the Ban Members permission.")
        if not user_id.isdigit():
            return await _deny(interaction, "That doesn't look like a user ID (numbers only).")
        ok = await governor.safe(
            interaction.guild.unban(discord.Object(id=int(user_id)),
                                    reason=f"Guildizer ({interaction.user}): {reason}"),
            what="unban",
        )
        if not ok:
            return await _deny(interaction, "Unban failed — is that user actually banned?")
        await asyncio.to_thread(_log_event, interaction.guild.id, "moderation", "unban",
                                int(user_id), None, reason)
        await interaction.response.send_message(f"✅ Unbanned `{user_id}`: {reason}")

    @tree.command(name="tempban", description="Ban a member temporarily. e.g. /tempban @user 7d raiding")
    @app_commands.describe(member="Who", duration="1d, 7d, 12h…", reason="Why")
    @app_commands.default_permissions(ban_members=True)
    async def tempban(interaction: discord.Interaction, member: discord.Member,
                      duration: str, reason: str = "No reason given") -> None:
        if interaction.guild is None or not _has(interaction, ban_members=True):
            return await _deny(interaction, "You need the Ban Members permission.")
        problem = await _check_target(interaction, member)
        if problem:
            return await _deny(interaction, problem)
        seconds = assistant.parse_duration(duration)
        if not seconds:
            return await _deny(interaction, "I couldn't read that duration. Try `12h`, `1d`, `7d`.")
        ok = await governor.safe(
            member.ban(reason=f"Guildizer tempban {duration} ({interaction.user}): {reason}",
                       delete_message_days=1),
            what="tempban",
        )
        if not ok:
            return await _deny(interaction, "Ban failed — check my role position and permissions.")
        await asyncio.to_thread(
            _db_call, modrt.schedule_unban, interaction.guild.id, member.id, str(member),
            seconds, reason,
        )
        await asyncio.to_thread(_log_event, interaction.guild.id, "moderation", "tempban",
                                member.id, str(member), f"{duration} — {reason}")
        await interaction.response.send_message(
            f"⏳ Temp-banned **{member.display_name}** for {duration}: {reason}"
        )

    @tree.command(name="purge", description="Bulk-delete recent messages in this channel.")
    @app_commands.describe(count="How many to scan (1–100)", member="Only delete messages from this member")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(interaction: discord.Interaction,
                    count: app_commands.Range[int, 1, 100],
                    member: discord.Member | None = None) -> None:
        if interaction.guild is None or not _has(interaction, manage_messages=True):
            return await _deny(interaction, "You need the Manage Messages permission.")
        if not hasattr(interaction.channel, "purge"):
            return await _deny(interaction, "I can't purge this kind of channel.")
        await interaction.response.defer(ephemeral=True)
        check = (lambda m: m.author.id == member.id) if member else (lambda m: True)
        try:
            deleted = await interaction.channel.purge(limit=count, check=check)
        except (discord.Forbidden, discord.HTTPException):
            return await _deny(interaction, "Purge failed — check my Manage Messages permission here.")
        await asyncio.to_thread(_log_event, interaction.guild.id, "moderation", "purge",
                                member.id if member else None,
                                str(member) if member else None,
                                f"{len(deleted)} message(s) in #{interaction.channel}")
        await interaction.followup.send(f"🧹 Deleted {len(deleted)} message(s).", ephemeral=True)

    @tree.command(name="userinfo", description="Show a member's profile, roles and warning count.")
    async def userinfo(interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return await _deny(interaction, "Use this in a server.")
        count = await asyncio.to_thread(
            _db_call, modrt.warning_count, interaction.guild.id, member.id
        ) or 0
        roles = [r.mention for r in member.roles if r.name != "@everyone"][:10]
        embed = discord.Embed(title=str(member), color=member.color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Account created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        if member.joined_at:
            embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Warnings", value=str(count), inline=True)
        if member.is_timed_out():
            embed.add_field(name="Timed out until", value=f"<t:{int(member.timed_out_until.timestamp())}:R>", inline=True)
        embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) or "—", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="auditlog", description="Show recent moderation/protection activity.")
    @app_commands.default_permissions(moderate_members=True)
    async def auditlog(interaction: discord.Interaction,
                       limit: app_commands.Range[int, 1, 20] = 10) -> None:
        if interaction.guild is None or not _has(interaction, moderate_members=True):
            return await _deny(interaction, "You need the Timeout Members permission.")
        rows = await asyncio.to_thread(_recent_events, interaction.guild.id, limit)
        if not rows:
            return await _deny(interaction, "No moderation activity recorded yet.")
        lines = [
            f"• <t:{assistant.utc_ts(ts)}:R> `{cat}/{act}`"
            + (f" {who}" if who else "") + (f" — {detail}" if detail else "")
            for ts, cat, act, who, detail in rows
        ]
        await interaction.response.send_message(
            "📋 **Recent activity**\n" + "\n".join(lines)[:1900], ephemeral=True
        )

    @tree.command(name="report", description="Report a member to the server's moderators.")
    @app_commands.describe(member="Who you're reporting", reason="What happened")
    async def report(interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if interaction.guild is None:
            return await _deny(interaction, "Use this in a server.")
        await asyncio.to_thread(
            _db_call, modrt.create_report, interaction.guild.id,
            reporter_id=interaction.user.id, reporter_name=str(interaction.user),
            target_id=member.id, target_name=str(member), reason=reason,
        )
        await asyncio.to_thread(_log_event, interaction.guild.id, "report", "filed",
                                member.id, str(member), reason)
        await interaction.response.send_message(
            "✅ Report filed — the moderators will review it. Thank you.", ephemeral=True
        )

    @tree.context_menu(name="Report Message")
    async def report_message(interaction: discord.Interaction, message: discord.Message) -> None:
        if interaction.guild is None:
            return await _deny(interaction, "Use this in a server.")
        await asyncio.to_thread(
            _db_call, modrt.create_report, interaction.guild.id,
            reporter_id=interaction.user.id, reporter_name=str(interaction.user),
            target_id=message.author.id, target_name=str(message.author),
            channel_id=message.channel.id, message_id=message.id,
            message_excerpt=(message.content or "")[:500],
            reason="Reported via right-click",
        )
        await asyncio.to_thread(_log_event, interaction.guild.id, "report", "filed",
                                message.author.id, str(message.author), "message report")
        await interaction.response.send_message(
            "✅ Message reported — the moderators will review it. Thank you.", ephemeral=True
        )
