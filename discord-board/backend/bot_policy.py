"""Foreign-bot join policy (Phase 11). Both lineages.

When another bot is added to a served guild: trusted bots pass; otherwise the
policy kicks it (kick_untrusted) or just alerts (alert_only). Either way an
alert lands in the configured channel with admin Trust/Kick buttons so the
decision is one click. Trusting stores the bot id, so a re-invite sails through.
"""
from __future__ import annotations

import asyncio
import logging

import discord

import governor
import protection
from database import SessionLocal

log = logging.getLogger("guildizer.botpolicy")


def _cfg(guild_id) -> dict:
    db = SessionLocal()
    try:
        snap = protection.load_snapshot(db, guild_id) or {}
        return snap.get("bot_policy") or {}
    finally:
        db.close()
        SessionLocal.remove()


def _trust(guild_id, bot_user_id) -> None:
    db = SessionLocal()
    try:
        snap = protection.load_snapshot(db, guild_id) or {}
        trusted = list((snap.get("bot_policy") or {}).get("trusted_bot_ids") or [])
        if str(bot_user_id) not in [str(t) for t in trusted]:
            trusted.append(str(bot_user_id))
        protection.update_extra_section(db, guild_id, "bot_policy", {"trusted_bot_ids": trusted})
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def _log(guild_id, action, user_id=None, username=None, detail=None):
    db = SessionLocal()
    try:
        protection.log_event(db, guild_id, "bot_policy", action,
                             user_id=user_id, username=username, detail=detail)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
        SessionLocal.remove()


async def handle_bot_join(client, member: discord.Member) -> None:
    """Called from on_member_join when member.bot is True (and we serve the guild)."""
    if member.id == client.user.id:
        return
    cfg = await asyncio.to_thread(_cfg, member.guild.id)
    if not cfg.get("enabled"):
        return
    trusted = [str(t) for t in (cfg.get("trusted_bot_ids") or [])]
    if str(member.id) in trusted:
        await asyncio.to_thread(_log, member.guild.id, "allowed_trusted",
                                member.id, str(member), "trusted bot joined")
        return

    kicked = False
    if cfg.get("policy", "kick_untrusted") == "kick_untrusted":
        kicked = await governor.safe(
            member.kick(reason="Guildizer bot policy: untrusted bot"), what="bot-policy kick"
        )
    await asyncio.to_thread(_log, member.guild.id, "kicked" if kicked else "alerted",
                            member.id, str(member),
                            "untrusted bot " + ("kicked" if kicked else "joined"))

    ch_id = cfg.get("alert_channel_id")
    channel = member.guild.get_channel(int(ch_id)) if ch_id else member.guild.system_channel
    if channel is None or not hasattr(channel, "send"):
        return
    verb = "was kicked (untrusted)" if kicked else "joined"
    view = discord.ui.View(timeout=None)
    view.add_item(TrustBotButton(member.guild.id, member.id))
    if not kicked:
        view.add_item(KickBotButton(member.guild.id, member.id))
    await governor.safe(
        channel.send(
            f"🤖 Bot **{member}** (`{member.id}`) {verb}. "
            + ("Trust it to allow re-inviting it." if kicked else "Trust or kick it below."),
            view=view,
        ),
        what="bot-policy alert",
    )


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild))


class TrustBotButton(discord.ui.DynamicItem[discord.ui.Button],
                     template=r"gz:bottrust:(?P<gid>\d+):(?P<bid>\d+)"):
    def __init__(self, gid: int, bid: int) -> None:
        super().__init__(discord.ui.Button(
            label="Trust this bot", style=discord.ButtonStyle.success,
            custom_id=f"gz:bottrust:{gid}:{bid}",
        ))
        self.gid = gid
        self.bid = bid

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["gid"]), int(match["bid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return
        await asyncio.to_thread(_trust, self.gid, self.bid)
        await asyncio.to_thread(_log, self.gid, "trusted", self.bid, None,
                                f"trusted by {interaction.user}")
        await interaction.response.edit_message(
            content=f"✅ Bot `{self.bid}` is now trusted — re-invite it if it was kicked.",
            view=None,
        )


class KickBotButton(discord.ui.DynamicItem[discord.ui.Button],
                    template=r"gz:botkick:(?P<gid>\d+):(?P<bid>\d+)"):
    def __init__(self, gid: int, bid: int) -> None:
        super().__init__(discord.ui.Button(
            label="Kick it", style=discord.ButtonStyle.danger,
            custom_id=f"gz:botkick:{gid}:{bid}",
        ))
        self.gid = gid
        self.bid = bid

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["gid"]), int(match["bid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return
        member = interaction.guild.get_member(self.bid)
        if member is None:
            await interaction.response.edit_message(content="That bot already left.", view=None)
            return
        ok = await governor.safe(member.kick(reason=f"Guildizer bot policy ({interaction.user})"),
                                 what="bot-policy manual kick")
        await asyncio.to_thread(_log, self.gid, "kicked" if ok else "kick_failed",
                                self.bid, str(member), f"by {interaction.user}")
        await interaction.response.edit_message(
            content=f"👢 Kicked bot **{member}**." if ok else "Kick failed — check my permissions.",
            view=None,
        )
