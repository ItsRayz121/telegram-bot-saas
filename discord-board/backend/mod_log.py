"""Mod-action log channel (Phase 1 parity).

When a guild enables a mod-log channel, every moderation action — automod
removals and the manual mod-command suite — is mirrored there as a compact
embed. Self-guarding: callers pass an already-loaded moderation snapshot and a
discord guild; if the log is off or the channel is gone, post() is a no-op.
"""
from __future__ import annotations

import discord

import governor

# action -> (emoji, embed colour)
_STYLE = {
    "deleted": ("🗑️", 0x95A5A6),
    "warned": ("⚠️", 0xF1C40F),
    "timeout": ("🔇", 0xE67E22),
    "untimeout": ("🔊", 0x2ECC71),
    "kick": ("👢", 0xE74C3C),
    "ban": ("🔨", 0xC0392B),
    "tempban": ("⏳", 0xC0392B),
    "unban": ("✅", 0x2ECC71),
    "purge": ("🧹", 0x3498DB),
    "removed": ("✅", 0x2ECC71),
}
_DEFAULT_STYLE = ("🛡️", 0x5865F2)


def channel_id(cfg: dict):
    """The configured mod-log channel id, or None when logging is off."""
    ml = (cfg or {}).get("mod_log") or {}
    if not ml.get("enabled"):
        return None
    return ml.get("channel_id")


async def post(guild, cfg: dict, *, action: str, category: str = "moderation",
               target_name: str | None = None, target_id=None,
               moderator_name: str | None = None, reason: str | None = None,
               channel_name: str | None = None) -> None:
    """Mirror a moderation action into the guild's mod-log channel (no-op when
    unconfigured or the channel can't be found/posted to)."""
    cid = channel_id(cfg)
    if not cid or guild is None:
        return
    try:
        channel = guild.get_channel(int(cid))
    except (TypeError, ValueError):
        return
    if channel is None or not hasattr(channel, "send"):
        return
    emoji, color = _STYLE.get(action, _DEFAULT_STYLE)
    embed = discord.Embed(
        title=f"{emoji} {action.replace('_', ' ').title()}",
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    if target_name:
        tline = target_name + (f" (`{target_id}`)" if target_id else "")
        embed.add_field(name="Member", value=tline[:256], inline=True)
    embed.add_field(name="Moderator", value=(moderator_name or "Auto-mod")[:256], inline=True)
    if channel_name:
        embed.add_field(name="Channel", value=channel_name[:256], inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason[:1000], inline=False)
    embed.set_footer(text=category)
    await governor.safe(channel.send(embed=embed), what="mod-log post")
