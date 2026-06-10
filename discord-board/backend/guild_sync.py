"""Upsert Discord guild/channel/role state into Guildizer's DB.

The bot (bot.py) owns this sync: it has the gateway cache and fires the calls on
ready / guild join / guild remove. The Flask API just reads the resulting rows.
Functions take a live SQLAlchemy session and discord.py objects; the caller
commits. No Telegizer imports.
"""
from __future__ import annotations

from datetime import datetime

from models import Channel, Guild, Role


def upsert_guild(db, dguild) -> Guild:
    """Create/update the Guild row from a discord.Guild and mark the bot present."""
    guild = db.get(Guild, dguild.id)
    if guild is None:
        guild = Guild(id=dguild.id)
        db.add(guild)
    guild.name = dguild.name
    guild.icon = dguild.icon.key if dguild.icon else None
    guild.bot_present = True
    guild.member_count = getattr(dguild, "member_count", 0) or 0
    if dguild.owner_id and guild.owner_id is None:
        guild.owner_id = dguild.owner_id
    guild.synced_at = datetime.utcnow()
    return guild


def sync_channels(db, dguild) -> None:
    """Replace the guild's channels with its current gateway channel set."""
    current_ids = set()
    for ch in dguild.channels:
        current_ids.add(ch.id)
        row = db.get(Channel, ch.id)
        if row is None:
            row = Channel(id=ch.id, guild_id=dguild.id)
            db.add(row)
        row.guild_id = dguild.id
        row.name = getattr(ch, "name", None)
        row.type = int(ch.type.value) if hasattr(ch.type, "value") else int(ch.type)
        row.position = getattr(ch, "position", 0) or 0
        row.parent_id = ch.category_id if getattr(ch, "category_id", None) else None
        row.synced_at = datetime.utcnow()

    _prune(db, Channel, dguild.id, current_ids)


def sync_roles(db, dguild) -> None:
    """Replace the guild's roles with its current gateway role set."""
    current_ids = set()
    for role in dguild.roles:
        current_ids.add(role.id)
        row = db.get(Role, role.id)
        if row is None:
            row = Role(id=role.id, guild_id=dguild.id)
            db.add(row)
        row.guild_id = dguild.id
        row.name = role.name
        row.color = role.color.value if role.color else 0
        row.position = role.position
        row.permissions = str(role.permissions.value)
        row.managed = role.managed
        row.mentionable = role.mentionable
        row.synced_at = datetime.utcnow()

    _prune(db, Role, dguild.id, current_ids)


def _prune(db, model, guild_id: int, keep_ids: set[int]) -> None:
    for row in db.query(model).filter(model.guild_id == guild_id).all():
        if row.id not in keep_ids:
            db.delete(row)


def full_sync(db, dguild) -> None:
    """Sync the guild row + its channels + its roles in one shot."""
    upsert_guild(db, dguild)
    sync_channels(db, dguild)
    sync_roles(db, dguild)


def mark_bot_left(db, guild_id: int) -> None:
    guild = db.get(Guild, guild_id)
    if guild is not None:
        guild.bot_present = False
        guild.synced_at = datetime.utcnow()
