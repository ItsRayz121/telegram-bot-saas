"""Direct team invites for a Discord server: the owner picks a member, the server's bot DMs them
Accept / Decline buttons, and accepting creates the same GuildTeamMember seat an access code does.
Mirrors Telegizer's group_invite_flow.

Rules:
  * Only people who already appear in the server's member list (they have chatted or been seen
    there) can be invited, never an arbitrary Discord id.
  * The DM is sent by the bot that serves the server (the official bot, or the owner's custom bot),
    so the button press comes back through that same bot's gateway.
  * One pending invitation per person per server; they expire after 7 days.

Kill switches: GUILD_TEAM_DIRECT_INVITES_ENABLED=0 stops new direct invites and makes pending ones
unacceptable; GUILD_TEAM_ACCESS_ENABLED=0 (access.py) stops all team access. Existing seats stay.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import requests

import access
import crypto
from config import Config
from models import CustomBot, Guild, GuildTeamMember, Member, TeamInvite, UserGuild

log = logging.getLogger("guildizer.team_direct")

API_BASE = "https://discord.com/api/v10"
INVITE_TTL_DAYS = 7
MAX_SEATS = 10
ROLES = ("manager", "viewer")
_TIMEOUT = 10


def direct_invites_enabled() -> bool:
    if os.environ.get("GUILD_TEAM_DIRECT_INVITES_ENABLED", "1").strip().lower() in ("0", "false", "off", "no"):
        return False
    return access.team_access_enabled()


def bot_token_for(db, guild: Guild):
    """Token of the bot that serves this server (custom bot if linked, else the official bot)."""
    if guild.custom_bot_id is not None:
        bot = db.get(CustomBot, guild.custom_bot_id)
        return crypto.decrypt_token(bot.token_encrypted) if bot is not None else None
    return Config.DISCORD_BOT_TOKEN or None


def open_direct(db, guild_id: int):
    return (db.query(TeamInvite)
            .filter(TeamInvite.guild_id == guild_id, TeamInvite.invitee_discord_id.isnot(None),
                    TeamInvite.used_by.is_(None), TeamInvite.declined_at.is_(None),
                    TeamInvite.expires_at > datetime.utcnow()).all())


def candidates(db, guild_id: int, query: str, exclude_user_id: int, limit: int = 15) -> list[dict]:
    """Server members matching `query` who can be invited, with their current state."""
    q = (query or "").strip().lstrip("@")
    if len(q) < 2:
        return []
    rows = (db.query(Member)
            .filter(Member.guild_id == guild_id, Member.username.ilike(f"%{q}%"))
            .order_by(Member.username).limit(limit * 3).all())
    managers = {uid for (uid,) in db.query(UserGuild.user_id)
                .filter(UserGuild.guild_id == guild_id, UserGuild.can_manage.is_(True)).all()}
    seats = {s.user_id: s.role for s in db.query(GuildTeamMember).filter(GuildTeamMember.guild_id == guild_id).all()}
    pending = {i.invitee_discord_id for i in open_direct(db, guild_id)}
    out = []
    for m in rows:
        if m.user_id == exclude_user_id or m.user_id in managers:
            continue
        out.append({"user_id": str(m.user_id), "username": m.username,
                    "has_access": m.user_id in seats, "member_role": seats.get(m.user_id),
                    "pending": m.user_id in pending})
        if len(out) >= limit:
            break
    return out


def invite_message(guild_name: str, owner_name: str, role: str, invite_id: int) -> dict:
    what = ("full control of the dashboard: settings, moderation, automations and campaigns"
            if role == "manager" else "view-only access to the dashboard, no changes")
    verb = "manage" if role == "manager" else "view"
    return {
        "content": (f"👥 **Team invitation**\n{owner_name} invites you to {verb} "
                    f"**{guild_name}** on Guildizer as **{role.title()}** ({what}).\n"
                    f"You only get access to this one server. The invitation expires in {INVITE_TTL_DAYS} days."),
        "components": [{"type": 1, "components": [
            {"type": 2, "style": 3, "label": "Accept", "custom_id": f"gti:a:{invite_id}"},
            {"type": 2, "style": 4, "label": "Decline", "custom_id": f"gti:r:{invite_id}"},
        ]}],
        "allowed_mentions": {"parse": []},
    }


def send_dm(token, user_id: int, payload: dict):
    """DM a user through the bot owning `token`. Returns (ok, error)."""
    if not token:
        return False, "The bot for this server is not configured"
    headers = {"Authorization": f"Bot {token}"}
    try:
        ch = requests.post(f"{API_BASE}/users/@me/channels", json={"recipient_id": str(user_id)},
                           headers=headers, timeout=_TIMEOUT)
        if ch.status_code != 200:
            return False, "Discord would not open a DM with this person"
        msg = requests.post(f"{API_BASE}/channels/{ch.json()['id']}/messages", json=payload,
                            headers=headers, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        log.warning("team invite DM failed: %s", exc)
        return False, "Discord is unreachable"
    if msg.status_code in (200, 201):
        return True, None
    if msg.status_code == 403:
        return False, "They have DMs from server members turned off. Send an access code instead."
    return False, "Discord refused the message"


def respond(db, invite_id: int, discord_user_id: int, username, accept: bool):
    """Handle the invitee pressing Accept / Decline.
    Returns (status, info): ok | declined | gone | not_you | disabled; info has guild_name, role,
    created_by and, for 'gone', a reason."""
    inv = db.get(TeamInvite, invite_id)
    if inv is None or inv.invitee_discord_id is None:
        return "gone", {"reason": "unknown"}
    if inv.invitee_discord_id != int(discord_user_id):
        return "not_you", {}
    guild = db.get(Guild, inv.guild_id)
    info = {"guild_name": guild.name if guild else "the server", "role": inv.role or "manager",
            "created_by": inv.created_by}
    state = inv.status()
    if guild is None or state != "pending":
        info["reason"] = "owner_changed" if guild is None else state
        log.warning("team invite %s refused for %s: %s", inv.id, discord_user_id, info["reason"])
        return "gone", info
    if not accept:
        inv.declined_at = datetime.utcnow()
        db.commit()
        return "declined", info
    if not direct_invites_enabled():
        return "disabled", info
    seats = db.query(GuildTeamMember).filter(GuildTeamMember.guild_id == inv.guild_id).count()
    existing = db.get(GuildTeamMember, {"guild_id": inv.guild_id, "user_id": int(discord_user_id)})
    if existing is None and seats >= MAX_SEATS:
        info["reason"] = "seat_limit"
        return "gone", info
    claimed = (db.query(TeamInvite)
               .filter(TeamInvite.id == inv.id, TeamInvite.used_by.is_(None), TeamInvite.declined_at.is_(None))
               .update({"used_by": int(discord_user_id), "used_at": datetime.utcnow()}, synchronize_session=False))
    if claimed != 1:
        db.rollback()
        info["reason"] = "used"
        return "gone", info
    if existing is None:
        db.add(GuildTeamMember(guild_id=inv.guild_id, user_id=int(discord_user_id), username=username,
                               role=inv.role or "manager", invited_by=inv.created_by))
    else:
        existing.role, existing.invited_by = inv.role or "manager", inv.created_by
    access.notify(db, inv.created_by, "Team invite accepted",
                  f"{username or discord_user_id} accepted your invite to {info['guild_name']}.", "info")
    db.commit()
    return "ok", info


REPLIES = {
    "ok": "✅ You now have **{role}** access to **{guild}**. Log in at telegizer.com/guildizer with Discord to open it.",
    "declined": "You declined the invitation to **{guild}**.",
    "disabled": "Team invitations are paused right now. Please try again later.",
    "gone": "This invitation is no longer valid. Ask the server owner to send a new one.",
    "expired": "This invitation expired (they last 7 days). Ask the server owner to send a new one.",
    "used": "This invitation was already accepted.",
    "declined_before": "You already declined this invitation. Ask the server owner to send a new one.",
    "seat_limit": "This server has reached its team limit. Ask the owner to free a seat.",
    "not_you": "This invitation is not for you.",
}


def reply_text(status: str, info: dict) -> str:
    key = status
    if status == "gone":
        key = {"expired": "expired", "used": "used", "accepted": "used", "declined": "declined_before",
               "seat_limit": "seat_limit"}.get(info.get("reason"), "gone")
    return REPLIES[key].format(role=(info.get("role") or "manager").title(),
                               guild=info.get("guild_name") or "the server")
