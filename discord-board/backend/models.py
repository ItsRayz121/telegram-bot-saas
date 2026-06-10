"""Guildizer data models. Grows per phase; never references Telegram models.

Phase 1 adds Discord OAuth + server-onboarding shape:
  User (with OAuth tokens) ─< UserGuild >─ Guild ─< Channel
                                              └────< Role
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
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
