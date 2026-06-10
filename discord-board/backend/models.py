"""Guildizer data models. Grows per phase; never references Telegram models.

Phase 1 adds Discord OAuth + server-onboarding shape:
  User (with OAuth tokens) ─< UserGuild >─ Guild ─< Channel
                                              └────< Role
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    """A dashboard user, identified by their Discord account (snowflake id)."""

    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)          # Discord user id (snowflake)
    username = Column(String(120))
    global_name = Column(String(120))                  # Discord display name
    avatar = Column(String(255))

    # OAuth2 tokens — used to re-fetch the user's guild list later.
    # Lives only in Guildizer's own DB (never shared with Telegizer).
    access_token = Column(String(255))
    refresh_token = Column(String(255))
    token_expires_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, default=datetime.utcnow)

    # Guilds this user personally owns (owner_id on Guild). Distinct from the
    # broader membership/manage relationship captured by UserGuild.
    owned_guilds = relationship("Guild", back_populates="owner")
    memberships = relationship(
        "UserGuild", back_populates="user", cascade="all, delete-orphan"
    )

    def avatar_url(self) -> str | None:
        if not self.avatar:
            return None
        return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.png"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "username": self.username,
            "global_name": self.global_name,
            "avatar_url": self.avatar_url(),
        }


class Guild(Base):
    """A Discord server ('guild'). Created either from a user's OAuth guild list
    or from the bot's gateway sync; bot_present is only ever set true by the bot."""

    __tablename__ = "guilds"

    id = Column(BigInteger, primary_key=True)          # Discord guild id (snowflake)
    name = Column(String(200))
    icon = Column(String(255))
    owner_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    bot_present = Column(Boolean, default=False)
    member_count = Column(Integer, default=0)

    added_at = Column(DateTime, default=datetime.utcnow)
    synced_at = Column(DateTime)                       # last bot gateway sync

    owner = relationship("User", back_populates="owned_guilds")
    memberships = relationship(
        "UserGuild", back_populates="guild", cascade="all, delete-orphan"
    )
    channels = relationship(
        "Channel", back_populates="guild", cascade="all, delete-orphan"
    )
    roles = relationship(
        "Role", back_populates="guild", cascade="all, delete-orphan"
    )
    settings = relationship(
        "GuildSettings",
        back_populates="guild",
        uselist=False,
        cascade="all, delete-orphan",
    )
    commands = relationship(
        "CustomCommand", back_populates="guild", cascade="all, delete-orphan"
    )

    def icon_url(self) -> str | None:
        if not self.icon:
            return None
        return f"https://cdn.discordapp.com/icons/{self.id}/{self.icon}.png"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "icon_url": self.icon_url(),
            "bot_present": bool(self.bot_present),
            "member_count": self.member_count or 0,
        }


class UserGuild(Base):
    """A user's relationship to a guild, derived from their OAuth guild list:
    their permission bits there, whether they own it, and whether they can
    manage it (i.e. are allowed to add/configure the bot)."""

    __tablename__ = "user_guilds"

    user_id = Column(BigInteger, ForeignKey("users.id"), primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), primary_key=True)
    permissions = Column(String(32), default="0")      # bitfield as string (64-bit safe)
    is_owner = Column(Boolean, default=False)
    can_manage = Column(Boolean, default=False)        # has MANAGE_GUILD or owns it
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="memberships")
    guild = relationship("Guild", back_populates="memberships")


class Channel(Base):
    """A channel within a guild, synced from the bot's gateway cache."""

    __tablename__ = "channels"

    id = Column(BigInteger, primary_key=True)          # Discord channel id (snowflake)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False)
    name = Column(String(120))
    type = Column(Integer, default=0)                  # Discord channel type enum
    position = Column(Integer, default=0)
    parent_id = Column(BigInteger, nullable=True)      # category id, if any
    synced_at = Column(DateTime, default=datetime.utcnow)

    guild = relationship("Guild", back_populates="channels")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "type": self.type,
            "position": self.position,
            "parent_id": str(self.parent_id) if self.parent_id else None,
        }


class Role(Base):
    """A role within a guild, synced from the bot's gateway cache."""

    __tablename__ = "roles"

    id = Column(BigInteger, primary_key=True)          # Discord role id (snowflake)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False)
    name = Column(String(120))
    color = Column(Integer, default=0)                 # integer RGB
    position = Column(Integer, default=0)
    permissions = Column(String(32), default="0")      # bitfield as string
    managed = Column(Boolean, default=False)           # managed by an integration
    mentionable = Column(Boolean, default=False)
    synced_at = Column(DateTime, default=datetime.utcnow)

    guild = relationship("Guild", back_populates="roles")

    def color_hex(self) -> str | None:
        if not self.color:
            return None
        return f"#{self.color:06x}"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "color": self.color_hex(),
            "position": self.position,
            "managed": bool(self.managed),
            "mentionable": bool(self.mentionable),
        }


class GuildSettings(Base):
    """Per-server configuration: welcome/leave messages + auto-roles. One row per
    guild, created/self-healed on bot startup (see settings.py)."""

    __tablename__ = "guild_settings"

    guild_id = Column(BigInteger, ForeignKey("guilds.id"), primary_key=True)

    # Welcome
    welcome_enabled = Column(Boolean, default=False)
    welcome_channel_id = Column(BigInteger, nullable=True)
    welcome_message = Column(Text, default="")

    # Leave
    leave_enabled = Column(Boolean, default=False)
    leave_channel_id = Column(BigInteger, nullable=True)
    leave_message = Column(Text, default="")

    # Auto-roles assigned on join (list of role-id strings)
    autorole_enabled = Column(Boolean, default=False)
    autorole_ids = Column(JSON, default=list)

    # Set true by the API when custom commands change; the bot's resync loop
    # re-registers that guild's slash commands and clears the flag.
    commands_dirty = Column(Boolean, default=False)

    # Forward-compat bag so new settings self-heal without a migration.
    extra = Column(JSON, default=dict)

    updated_at = Column(DateTime, default=datetime.utcnow)

    guild = relationship("Guild", back_populates="settings")

    def to_dict(self) -> dict:
        return {
            "welcome_enabled": bool(self.welcome_enabled),
            "welcome_channel_id": str(self.welcome_channel_id) if self.welcome_channel_id else None,
            "welcome_message": self.welcome_message or "",
            "leave_enabled": bool(self.leave_enabled),
            "leave_channel_id": str(self.leave_channel_id) if self.leave_channel_id else None,
            "leave_message": self.leave_message or "",
            "autorole_enabled": bool(self.autorole_enabled),
            "autorole_ids": [str(r) for r in (self.autorole_ids or [])],
        }


class CustomCommand(Base):
    """A dashboard-defined slash command: `/name` -> a stored text response.
    The bot registers these as per-guild slash commands."""

    __tablename__ = "custom_commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False)
    name = Column(String(32), nullable=False)          # slash command name (no slash)
    description = Column(String(100), default="Custom command")
    response = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    guild = relationship("Guild", back_populates="commands")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "response": self.response or "",
            "enabled": bool(self.enabled),
        }
