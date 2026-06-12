"""Server settings backup/restore: roles, channels, permission overwrites.

The dashboard queues work on GuildBackup rows; the bot's 20s post loop picks it
up here. A snapshot is read straight from the gateway cache (no extra API
calls). Restore is deliberately NON-destructive — the anti-nuke recovery story:

  • @everyone / roles matched by stored id: drifted name/color/permissions/
    hoist/mentionable are re-applied; deleted roles are recreated (new id, old
    member assignments are unrecoverable).
  • channels matched by stored id: drifted name/topic/nsfw/slowmode re-applied;
    deleted channels are recreated under their (possibly recreated) category
    with their stored role overwrites. Member overwrites are never captured.
  • nothing is ever deleted, and role/channel positions are left alone.

Every Discord call goes through governor.safe, so missing permissions degrade
to partial restores instead of crashes; per-row status/error reports back to
the dashboard.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import discord

import governor
from database import SessionLocal
from models import GuildBackup

log = logging.getLogger("guildizer.backups")

_RECREATABLE = {0: "text", 2: "voice", 4: "category", 5: "news", 13: "stage"}


# ── storage helpers (sync — call via to_thread) ────────────────────────────────
def pending_actions() -> list[tuple[int, int, str]]:
    """(guild_id, backup_id, "snapshot"|"restore") for queued backup work."""
    out: list[tuple[int, int, str]] = []
    db = SessionLocal()
    try:
        rows = (
            db.query(GuildBackup)
            .filter((GuildBackup.needs_snapshot.is_(True))
                    | (GuildBackup.needs_restore.is_(True)))
            .limit(10)
            .all()
        )
        for r in rows:
            out.append((r.guild_id, r.id, "restore" if r.needs_restore else "snapshot"))
        return out
    finally:
        db.close()
        SessionLocal.remove()


def load_data(backup_id: int) -> dict | None:
    db = SessionLocal()
    try:
        row = db.get(GuildBackup, backup_id)
        return dict(row.data) if row is not None and row.data else None
    finally:
        db.close()
        SessionLocal.remove()


def update_row(backup_id: int, patch: dict) -> None:
    db = SessionLocal()
    try:
        row = db.get(GuildBackup, backup_id)
        if row is None:
            return
        for k, v in patch.items():
            setattr(row, k, v)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("backup row update failed for %s", backup_id)
    finally:
        db.close()
        SessionLocal.remove()


# ── snapshot (pure reads from the gateway cache) ───────────────────────────────
def snapshot_guild(guild: discord.Guild) -> dict:
    roles = []
    for r in guild.roles:
        if r.is_default() or r.managed:
            continue   # @everyone handled separately; bot/integration roles aren't ours
        roles.append({
            "id": str(r.id), "name": r.name[:100], "color": r.color.value,
            "permissions": str(r.permissions.value),
            "hoist": r.hoist, "mentionable": r.mentionable,
        })
    channels = []
    for c in guild.channels:
        if c.type.value not in _RECREATABLE:
            continue
        overwrites = []
        for target, ow in c.overwrites.items():
            if not isinstance(target, discord.Role):
                continue   # member overwrites are private — never captured
            allow, deny = ow.pair()
            overwrites.append({"role_id": str(target.id),
                               "allow": str(allow.value), "deny": str(deny.value)})
        channels.append({
            "id": str(c.id), "name": c.name[:100], "type": c.type.value,
            "parent_id": str(c.category_id) if c.category_id else None,
            "topic": (getattr(c, "topic", None) or "")[:1024],
            "nsfw": bool(getattr(c, "nsfw", False)),
            "slowmode": int(getattr(c, "slowmode_delay", 0) or 0),
            "overwrites": overwrites,
        })
    return {
        "everyone_permissions": str(guild.default_role.permissions.value),
        "roles": roles,
        "channels": channels,
    }


# ── restore ────────────────────────────────────────────────────────────────────
async def _restore_roles(guild: discord.Guild, data: dict) -> dict[str, discord.Role]:
    """Re-apply role settings; recreate missing roles. Returns old id -> role."""
    mapping: dict[str, discord.Role] = {}

    everyone_perms = discord.Permissions(int(data.get("everyone_permissions") or 0))
    if guild.default_role.permissions.value != everyone_perms.value:
        await governor.safe(
            guild.default_role.edit(permissions=everyone_perms,
                                    reason="Guildizer: backup restore"),
            what="restore @everyone permissions",
        )

    for spec in data.get("roles") or []:
        role = guild.get_role(int(spec["id"])) if str(spec.get("id", "")).isdigit() else None
        perms = discord.Permissions(int(spec.get("permissions") or 0))
        color = discord.Color(int(spec.get("color") or 0))
        if role is None:
            created = await governor.safe(
                guild.create_role(name=spec["name"], permissions=perms, colour=color,
                                  hoist=bool(spec.get("hoist")),
                                  mentionable=bool(spec.get("mentionable")),
                                  reason="Guildizer: backup restore"),
                what="restore role create",
            )
            if created and hasattr(created, "id"):
                mapping[spec["id"]] = created
            continue
        mapping[spec["id"]] = role
        if (role.name != spec["name"] or role.permissions.value != perms.value
                or role.color.value != color.value or role.hoist != bool(spec.get("hoist"))
                or role.mentionable != bool(spec.get("mentionable"))):
            await governor.safe(
                role.edit(name=spec["name"], permissions=perms, colour=color,
                          hoist=bool(spec.get("hoist")),
                          mentionable=bool(spec.get("mentionable")),
                          reason="Guildizer: backup restore"),
                what="restore role edit",
            )
    return mapping


async def _apply_overwrites(channel, spec: dict, roles: dict[str, discord.Role],
                            guild: discord.Guild) -> None:
    # set_permissions per role keeps member overwrites intact (channel.edit
    # with overwrites= would wipe them).
    for ow in spec.get("overwrites") or []:
        role = roles.get(ow["role_id"]) or (
            guild.get_role(int(ow["role_id"])) if str(ow["role_id"]).isdigit() else None
        ) or (guild.default_role if ow["role_id"] == str(guild.id) else None)
        if role is None:
            continue
        overwrite = discord.PermissionOverwrite.from_pair(
            discord.Permissions(int(ow.get("allow") or 0)),
            discord.Permissions(int(ow.get("deny") or 0)),
        )
        await governor.safe(
            channel.set_permissions(role, overwrite=overwrite,
                                    reason="Guildizer: backup restore"),
            what="restore channel overwrite",
        )


async def _restore_channels(guild: discord.Guild, data: dict,
                            roles: dict[str, discord.Role]) -> None:
    specs = data.get("channels") or []
    # categories first so recreated children can be parented correctly
    specs = sorted(specs, key=lambda s: 0 if s["type"] == 4 else 1)
    recreated: dict[str, discord.abc.GuildChannel] = {}

    def _parent_for(spec):
        pid = spec.get("parent_id")
        if not pid:
            return None
        parent = recreated.get(pid) or (guild.get_channel(int(pid)) if str(pid).isdigit() else None)
        return parent if isinstance(parent, discord.CategoryChannel) else None

    for spec in specs:
        channel = guild.get_channel(int(spec["id"])) if str(spec.get("id", "")).isdigit() else None
        if channel is not None:
            kwargs = {}
            if channel.name != spec["name"]:
                kwargs["name"] = spec["name"]
            if hasattr(channel, "topic") and (channel.topic or "") != (spec.get("topic") or ""):
                kwargs["topic"] = spec.get("topic") or None
            if getattr(channel, "nsfw", False) != bool(spec.get("nsfw")):
                kwargs["nsfw"] = bool(spec.get("nsfw"))
            if getattr(channel, "slowmode_delay", 0) != int(spec.get("slowmode") or 0):
                kwargs["slowmode_delay"] = int(spec.get("slowmode") or 0)
            if kwargs:
                await governor.safe(
                    channel.edit(reason="Guildizer: backup restore", **kwargs),
                    what="restore channel edit",
                )
            await _apply_overwrites(channel, spec, roles, guild)
            continue

        # deleted — recreate
        ctype = spec["type"]
        created = None
        if ctype == 4:
            created = await governor.safe(
                guild.create_category(spec["name"], reason="Guildizer: backup restore"),
                what="restore category create",
            )
        elif ctype in (0, 5):
            created = await governor.safe(
                guild.create_text_channel(
                    spec["name"], category=_parent_for(spec),
                    topic=spec.get("topic") or None, nsfw=bool(spec.get("nsfw")),
                    slowmode_delay=int(spec.get("slowmode") or 0), news=(ctype == 5),
                    reason="Guildizer: backup restore",
                ),
                what="restore text channel create",
            )
        elif ctype == 2:
            created = await governor.safe(
                guild.create_voice_channel(spec["name"], category=_parent_for(spec),
                                           reason="Guildizer: backup restore"),
                what="restore voice channel create",
            )
        elif ctype == 13:
            created = await governor.safe(
                guild.create_stage_channel(spec["name"], category=_parent_for(spec),
                                           reason="Guildizer: backup restore"),
                what="restore stage channel create",
            )
        if created and hasattr(created, "id"):
            recreated[spec["id"]] = created
            await _apply_overwrites(created, spec, roles, guild)


# ── queue processor (called from bot_core's 20s post loop) ─────────────────────
async def process_pending(bot) -> None:
    from bot_core import serves   # local import — bot_core imports this module

    for gid, bid, action in await asyncio.to_thread(pending_actions):
        if not serves(bot, gid):
            continue
        guild = bot.get_guild(gid)
        if guild is None:
            continue
        try:
            if action == "snapshot":
                data = snapshot_guild(guild)
                await asyncio.to_thread(update_row, bid, {
                    "data": data, "status": "done", "needs_snapshot": False,
                    "error": None,
                    "roles_count": len(data["roles"]),
                    "channels_count": len(data["channels"]),
                })
            else:
                data = await asyncio.to_thread(load_data, bid)
                if not data:
                    await asyncio.to_thread(update_row, bid, {
                        "needs_restore": False, "status": "restore_failed",
                        "error": "backup has no data",
                    })
                    continue
                await asyncio.to_thread(update_row, bid, {"status": "restoring"})
                roles = await _restore_roles(guild, data)
                await _restore_channels(guild, data, roles)
                await asyncio.to_thread(update_row, bid, {
                    "needs_restore": False, "status": "restored",
                    "restored_at": datetime.utcnow(), "error": None,
                })
        except Exception:  # noqa: BLE001
            log.exception("backup %s (%s) failed for guild %s", bid, action, gid)
            await asyncio.to_thread(update_row, bid, {
                "needs_snapshot": False, "needs_restore": False,
                "status": "failed" if action == "snapshot" else "restore_failed",
                "error": "unexpected error — check the bot logs",
            })
