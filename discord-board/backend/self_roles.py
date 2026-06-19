"""Self-assignable roles: reaction-role and button-role menus. Both lineages.

Admins build menus in the dashboard (stored in GuildSettings.extra["self_roles"],
no migration needed) and queue a post; the bot's 20s post loop publishes the
menu into its channel — buttons (persistent via DynamicItem) or reactions.
Members click/react to toggle the role; "max one" menus swap roles instead.

Role grants always go through governor.safe, and roles carrying moderation or
management permissions are never self-assignable, no matter what the stored
config says — a menu must not become a privilege-escalation path.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

import discord

import governor
from database import SessionLocal
from models import GuildSettings

log = logging.getLogger("guildizer.selfroles")

MAX_MENUS = 10
MAX_ENTRIES = 20   # Discord caps a view at 25 buttons; 20 keeps headroom

ACCENT = 0x5865F2

# Permissions a self-assignable role may never carry.
_DANGEROUS_PERMS = (
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "manage_messages", "manage_webhooks", "ban_members", "kick_members",
    "moderate_members", "mention_everyone",
)


def _role_is_safe(role: discord.Role) -> bool:
    if role.is_default() or role.managed:
        return False
    return not any(getattr(role.permissions, p, False) for p in _DANGEROUS_PERMS)


# ── storage helpers (sync — call via to_thread) ────────────────────────────────
def _menus_of(row: GuildSettings) -> list[dict]:
    return [dict(m) for m in ((row.extra or {}).get("self_roles") or [])]


def _write_menus(row: GuildSettings, menus: list[dict]) -> None:
    extra = dict(row.extra or {})
    extra["self_roles"] = menus
    row.extra = extra


def menu_snapshot(guild_id: int, menu_id: int) -> dict | None:
    """One menu's config, for the button callback / reaction handler."""
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return None
        for m in _menus_of(row):
            if int(m.get("id") or 0) == int(menu_id):
                return m
        return None
    finally:
        db.close()
        SessionLocal.remove()


def _post_due(post_at) -> bool:
    """True when a scheduled menu post is due (or has no schedule = post now)."""
    if not post_at:
        return True
    try:
        dt = datetime.fromisoformat(str(post_at).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return True   # unparseable → don't strand the post
    return dt <= datetime.utcnow()


def pending_actions() -> list[tuple[int, int, str]]:
    """(guild_id, menu_id, "post"|"delete") for every queued menu, all guilds.
    Cheap at current fleet size; rows without self_roles are skipped fast."""
    out: list[tuple[int, int, str]] = []
    db = SessionLocal()
    try:
        rows = (
            db.query(GuildSettings.guild_id, GuildSettings.extra)
            .filter(GuildSettings.extra.isnot(None))
            .all()
        )
        for gid, extra in rows:
            for m in (extra or {}).get("self_roles") or []:
                if not str(m.get("id", "")).isdigit():
                    continue
                if m.get("needs_delete"):
                    out.append((gid, int(m["id"]), "delete"))
                elif m.get("needs_post") and _post_due(m.get("post_at")):
                    out.append((gid, int(m["id"]), "post"))
        return out
    finally:
        db.close()
        SessionLocal.remove()


def _update_menu(guild_id: int, menu_id: int, patch: dict) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return
        menus = _menus_of(row)
        for m in menus:
            if int(m.get("id") or 0) == int(menu_id):
                m.update(patch)
        _write_menus(row, menus)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("self-role menu update failed for guild %s", guild_id)
    finally:
        db.close()
        SessionLocal.remove()


def mark_posted(guild_id: int, menu_id: int, message_id: int) -> None:
    _update_menu(guild_id, menu_id, {
        "message_id": str(message_id), "needs_post": False, "post_error": None,
        "post_at": None,
    })
    _cache_clear()


def mark_post_failed(guild_id: int, menu_id: int, error: str) -> None:
    _update_menu(guild_id, menu_id, {"needs_post": False, "post_error": error[:200]})


def mark_deleted(guild_id: int, menu_id: int) -> None:
    _update_menu(guild_id, menu_id, {
        "message_id": None, "needs_delete": False, "needs_post": False,
    })
    _cache_clear()


# ── message-id -> menu cache (reaction events fire often) ─────────────────────
_CACHE_TTL = 60
_menu_cache: dict[int, tuple[float, dict | None]] = {}   # message_id -> (expiry, menu)


def _cache_clear() -> None:
    _menu_cache.clear()


def _reaction_menu_for_message(guild_id: int, message_id: int) -> dict | None:
    """Sync lookup: the reaction-style menu posted as this message, if any."""
    db = SessionLocal()
    try:
        row = db.get(GuildSettings, guild_id)
        if row is None:
            return None
        for m in _menus_of(row):
            if str(m.get("message_id") or "") == str(message_id) \
                    and m.get("style") == "reactions":
                return m
        return None
    finally:
        db.close()
        SessionLocal.remove()


async def menu_for_message(guild_id: int, message_id: int) -> dict | None:
    now = time.monotonic()
    hit = _menu_cache.get(message_id)
    if hit and hit[0] > now:
        return hit[1]
    if len(_menu_cache) > 2000:   # bounded; negative entries dominate
        _cache_clear()
    menu = await asyncio.to_thread(_reaction_menu_for_message, guild_id, message_id)
    _menu_cache[message_id] = (now + _CACHE_TTL, menu)
    return menu


# ── role toggle core ──────────────────────────────────────────────────────────
async def _grant(member: discord.Member, role: discord.Role, menu: dict) -> bool:
    """Add `role`; on a max-one menu, swap out the member's other menu roles."""
    if menu.get("max_one"):
        other_ids = {int(e["role_id"]) for e in (menu.get("entries") or [])
                     if str(e.get("role_id", "")).isdigit() and int(e["role_id"]) != role.id}
        held = [r for r in member.roles if r.id in other_ids]
        if held:
            await governor.safe(
                member.remove_roles(*held, reason="Guildizer self-role (max one)"),
                what="self-role swap",
            )
    return bool(await governor.safe(
        member.add_roles(role, reason="Guildizer self-role"), what="self-role add"
    ))


async def _revoke(member: discord.Member, role: discord.Role) -> bool:
    return bool(await governor.safe(
        member.remove_roles(role, reason="Guildizer self-role"), what="self-role remove"
    ))


# ── persistent button (style: buttons) ────────────────────────────────────────
class SelfRoleButton(discord.ui.DynamicItem[discord.ui.Button],
                     template=r"gz:srole:(?P<gid>\d+):(?P<mid>\d+):(?P<rid>\d+)"):
    def __init__(self, gid: int, mid: int, rid: int,
                 label: str = "Role", emoji: str | None = None) -> None:
        self.gid = gid
        self.mid = mid
        self.rid = rid
        super().__init__(discord.ui.Button(
            label=label[:80], style=discord.ButtonStyle.secondary,
            emoji=emoji or None,
            custom_id=f"gz:srole:{gid}:{mid}:{rid}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["gid"]), int(match["mid"]), int(match["rid"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        role = guild.get_role(self.rid)
        if role is None:
            await interaction.response.send_message(
                "That role no longer exists — ask an admin to update the menu.", ephemeral=True)
            return
        if not _role_is_safe(role):
            await interaction.response.send_message(
                "That role can't be self-assigned.", ephemeral=True)
            return
        if role in member.roles:
            ok = await _revoke(member, role)
            text = f"➖ Removed **{role.name}**." if ok else \
                "I couldn't remove that role — my role may sit below it."
        else:
            menu = await asyncio.to_thread(menu_snapshot, self.gid, self.mid) or {}
            ok = await _grant(member, role, menu)
            text = f"✅ You now have **{role.name}**." if ok else \
                "I couldn't assign that role — my role may sit below it."
        await interaction.response.send_message(text, ephemeral=True)


# ── reaction handling (style: reactions) ──────────────────────────────────────
async def handle_reaction(client, payload: discord.RawReactionActionEvent,
                          member: discord.Member, *, add: bool) -> bool:
    """Toggle a role for a reaction on a posted reaction-role menu.
    Returns True when the reaction belonged to a menu (handled)."""
    menu = await menu_for_message(payload.guild_id, payload.message_id)
    if menu is None:
        return False
    wanted = str(payload.emoji)
    entry = next((e for e in (menu.get("entries") or [])
                  if str(e.get("emoji") or "") == wanted), None)
    if entry is None or not str(entry.get("role_id", "")).isdigit():
        return True   # a menu message, but not one of its mapped emojis
    role = member.guild.get_role(int(entry["role_id"]))
    if role is None or not _role_is_safe(role):
        return True
    if add:
        if role not in member.roles:
            await _grant(member, role, menu)
    elif role in member.roles:
        await _revoke(member, role)
    return True


# ── posting (called from the bot's 20s post loop) ─────────────────────────────
def _menu_text(menu: dict) -> str:
    lines = [f"**{(menu.get('title') or 'Pick your roles')[:100]}**"]
    if menu.get("description"):
        lines.append(str(menu["description"])[:1000])
    if menu.get("style") == "reactions":
        lines.append("")
        for e in (menu.get("entries") or [])[:MAX_ENTRIES]:
            if e.get("emoji"):
                lines.append(f"{e['emoji']} — {e.get('label') or 'role'}")
        lines.append("\nReact to get a role; remove your reaction to drop it.")
    return "\n".join(lines)[:1900]


def _build_view(guild_id: int, menu: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for e in (menu.get("entries") or [])[:MAX_ENTRIES]:
        if not str(e.get("role_id", "")).isdigit():
            continue
        emoji = str(e.get("emoji") or "").strip() or None
        if emoji and emoji.isascii() and not emoji.startswith("<"):
            emoji = None   # plain text isn't an emoji; a bad one 400s the post
        view.add_item(SelfRoleButton(
            guild_id, int(menu["id"]), int(e["role_id"]),
            label=str(e.get("label") or "Role"), emoji=emoji,
        ))
    return view


async def _delete_posted(bot, guild: discord.Guild, menu: dict) -> None:
    ch_id, msg_id = menu.get("channel_id"), menu.get("message_id")
    if ch_id and msg_id:
        channel = guild.get_channel(int(ch_id))
        if channel is not None:
            try:
                old = await channel.fetch_message(int(msg_id))
                await old.delete()
            except Exception:  # noqa: BLE001 — already gone is fine
                pass


async def process_pending(bot) -> None:
    """Publish/remove queued self-role menus for every guild this bot serves."""
    from bot_core import serves   # local import — bot_core imports this module

    for gid, mid, action in await asyncio.to_thread(pending_actions):
        if not serves(bot, gid):
            continue
        guild = bot.get_guild(gid)
        menu = await asyncio.to_thread(menu_snapshot, gid, mid)
        if guild is None or menu is None:
            continue
        if action == "delete":
            await _delete_posted(bot, guild, menu)
            await asyncio.to_thread(mark_deleted, gid, mid)
            continue

        channel = guild.get_channel(int(menu["channel_id"])) if menu.get("channel_id") else None
        if channel is None or not hasattr(channel, "send"):
            await asyncio.to_thread(mark_post_failed, gid, mid, "channel not found")
            continue
        entries = [e for e in (menu.get("entries") or [])
                   if str(e.get("role_id", "")).isdigit()]
        if not entries:
            await asyncio.to_thread(mark_post_failed, gid, mid, "menu has no roles")
            continue

        await _delete_posted(bot, guild, menu)   # re-post replaces the old message
        try:
            if menu.get("style") == "reactions":
                msg = await channel.send(_menu_text(menu))
                for e in entries[:MAX_ENTRIES]:
                    if e.get("emoji"):
                        await governor.safe(msg.add_reaction(str(e["emoji"])),
                                            what="self-role seed reaction")
            else:
                msg = await channel.send(_menu_text(menu), view=_build_view(gid, menu))
            await asyncio.to_thread(mark_posted, gid, mid, msg.id)
            log.info("Posted self-role menu %s/%s", gid, mid)
        except discord.Forbidden:
            await asyncio.to_thread(mark_post_failed, gid, mid, "missing permission to post")
        except discord.HTTPException as exc:
            await asyncio.to_thread(mark_post_failed, gid, mid, str(exc))
