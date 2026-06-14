"""Consolidated critical-alerts channel (Phase 2 parity).

One opt-in channel where admins receive the high-signal safety events — bans,
raid activations, anti-nuke containment, member reports — instead of wiring each
feature's own alert channel. Additive: per-feature channels still fire too; this
is the "just tell me the important stuff in one place" layer.

Self-guarding: callers pass an already-loaded moderation snapshot + a discord
guild. If the alert is off for that event, or the channel is gone, post() is a
no-op.
"""
from __future__ import annotations

import governor

# event -> (emoji prefix) for the one-line alert.
_PREFIX = {
    "ban": "🔨",
    "raid": "🚨",
    "nuke": "🛡️",
    "report": "📣",
}


def _channel(guild, cfg: dict, event: str):
    aa = (cfg or {}).get("admin_alerts") or {}
    if not aa.get("enabled") or not aa.get(f"on_{event}"):
        return None
    cid = aa.get("channel_id")
    if not cid or guild is None:
        return None
    try:
        channel = guild.get_channel(int(cid))
    except (TypeError, ValueError):
        return None
    if channel is None or not hasattr(channel, "send"):
        return None
    return channel


async def post(guild, cfg: dict, event: str, text: str) -> None:
    """Send a one-line critical alert when the guild opted in for this event."""
    channel = _channel(guild, cfg, event)
    if channel is None:
        return
    prefix = _PREFIX.get(event, "⚠️")
    await governor.safe(channel.send(f"{prefix} {text}"[:1900]), what=f"admin-alert {event}")
