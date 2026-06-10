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
    plan = Column(String(16), default="free")          # free | pro (set by billing)

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
    moderation = relationship(
        "ModerationSettings",
        back_populates="guild",
        uselist=False,
        cascade="all, delete-orphan",
    )
    protection_events = relationship(
        "ProtectionEvent", back_populates="guild", cascade="all, delete-orphan"
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
            "plan": self.plan or "free",
        }

    @property
    def is_pro(self) -> bool:
        return (self.plan or "free") == "pro"


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

    # Leveling / XP
    levels_enabled = Column(Boolean, default=False)
    xp_per_message = Column(Integer, default=10)
    xp_cooldown_seconds = Column(Integer, default=60)
    announce_level_up = Column(Boolean, default=True)
    levelup_channel_id = Column(BigInteger, nullable=True)   # null = post in-channel
    levelup_message = Column(Text, default="")

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

    def levels_to_dict(self) -> dict:
        return {
            "levels_enabled": bool(self.levels_enabled),
            "xp_per_message": self.xp_per_message or 10,
            "xp_cooldown_seconds": self.xp_cooldown_seconds or 60,
            "announce_level_up": bool(self.announce_level_up),
            "levelup_channel_id": str(self.levelup_channel_id) if self.levelup_channel_id else None,
            "levelup_message": self.levelup_message or "",
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


class ModerationSettings(Base):
    """Per-server moderation config: content filter + raid guard + join gate.
    One row per guild, created/self-healed on startup (see settings.py)."""

    __tablename__ = "moderation_settings"

    guild_id = Column(BigInteger, ForeignKey("guilds.id"), primary_key=True)

    # Content filter
    cf_enabled = Column(Boolean, default=False)
    cf_action = Column(String(16), default="delete")   # delete|warn|timeout|kick|ban
    cf_nsfw = Column(Boolean, default=True)
    cf_invites = Column(Boolean, default=True)          # block foreign Discord invites
    cf_links = Column(Boolean, default=False)           # block shortener/scam-TLD links
    cf_custom_words = Column(JSON, default=list)        # admin-added terms

    # Raid guard (behavior-based — distinct accounts tripping filters / dup-flooding)
    rg_enabled = Column(Boolean, default=False)
    rg_window_seconds = Column(Integer, default=60)
    rg_trigger_violators = Column(Integer, default=5)
    rg_duplicate_threshold = Column(Integer, default=5)
    rg_lockdown_minutes = Column(Integer, default=10)
    rg_lockdown_action = Column(String(16), default="timeout")  # timeout|kick
    rg_notify = Column(Boolean, default=True)
    rg_notify_channel_id = Column(BigInteger, nullable=True)
    manual_lockdown_until = Column(DateTime, nullable=True)      # admin panic button

    # Join gate
    jg_min_account_age_days = Column(Integer, default=0)         # 0 = off

    extra = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow)

    guild = relationship("Guild", back_populates="moderation")

    def to_dict(self) -> dict:
        from datetime import datetime as _dt

        locked = bool(self.manual_lockdown_until and self.manual_lockdown_until > _dt.utcnow())
        return {
            "cf_enabled": bool(self.cf_enabled),
            "cf_action": self.cf_action or "delete",
            "cf_nsfw": bool(self.cf_nsfw),
            "cf_invites": bool(self.cf_invites),
            "cf_links": bool(self.cf_links),
            "cf_custom_words": list(self.cf_custom_words or []),
            "rg_enabled": bool(self.rg_enabled),
            "rg_window_seconds": self.rg_window_seconds or 60,
            "rg_trigger_violators": self.rg_trigger_violators or 5,
            "rg_duplicate_threshold": self.rg_duplicate_threshold or 5,
            "rg_lockdown_minutes": self.rg_lockdown_minutes or 10,
            "rg_lockdown_action": self.rg_lockdown_action or "timeout",
            "rg_notify": bool(self.rg_notify),
            "rg_notify_channel_id": str(self.rg_notify_channel_id) if self.rg_notify_channel_id else None,
            "jg_min_account_age_days": self.jg_min_account_age_days or 0,
            "manual_lockdown_active": locked,
            "manual_lockdown_until": self.manual_lockdown_until.isoformat() + "Z" if self.manual_lockdown_until else None,
        }


class ProtectionEvent(Base):
    """An audit record of a moderation/protection action, shown in the
    Protection Activity feed."""

    __tablename__ = "protection_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False)
    category = Column(String(24))    # nsfw|csam|invite|link|custom|spam|raid|lockdown_join|join_gate|manual_lockdown
    action = Column(String(16))      # deleted|warned|timeout|kick|ban|restricted|none
    user_id = Column(BigInteger, nullable=True)
    username = Column(String(120), nullable=True)
    channel_id = Column(BigInteger, nullable=True)
    detail = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    guild = relationship("Guild", back_populates="protection_events")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "action": self.action,
            "user_id": str(self.user_id) if self.user_id else None,
            "username": self.username,
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class Member(Base):
    """A guild member's XP/level state. Composite-keyed per (guild, user)."""

    __tablename__ = "members"

    guild_id = Column(BigInteger, ForeignKey("guilds.id"), primary_key=True)
    user_id = Column(BigInteger, primary_key=True)        # Discord user id
    username = Column(String(120))
    xp = Column(Integer, default=0)
    level = Column(Integer, default=1)
    messages = Column(Integer, default=0)
    last_xp_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "xp": self.xp or 0,
            "level": self.level or 1,
            "messages": self.messages or 0,
        }


class XpEvent(Base):
    """Append-only XP ledger: every grant (message, campaign, manual) recorded."""

    __tablename__ = "xp_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False)
    user_id = Column(BigInteger, nullable=False)
    amount = Column(Integer, default=0)
    reason = Column(String(64))                           # message | campaign:<id> | manual
    created_at = Column(DateTime, default=datetime.utcnow)


CAMPAIGN_TYPES = ("proof_collection", "content_submission", "social_task", "raid")
CAMPAIGN_VERIFICATION_MODES = ("manual", "honor", "link")
CAMPAIGN_STATUSES = ("draft", "active", "paused", "closed")
SUBMISSION_STATUSES = ("pending", "verified", "rejected")


class Campaign(Base):
    """An engagement campaign created from the dashboard. Belongs to one guild.
    A campaign with tasks is multi-task; tasks carry their own reward + proof."""

    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    type = Column(String(32), default="proof_collection")
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    task_url = Column(String(2000), nullable=True)
    verification_mode = Column(String(20), default="manual")  # manual|honor|link
    reward_xp = Column(Integer, default=0)
    reward_label = Column(String(200), nullable=True)

    status = Column(String(20), default="draft", index=True)
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    one_per_user = Column(Boolean, default=True)

    # Discord post tracking + coordination flag the bot's post loop watches.
    channel_id = Column(BigInteger, nullable=True)        # where to announce
    message_id = Column(BigInteger, nullable=True)        # posted announcement
    needs_post = Column(Boolean, default=False)           # API asked the bot to (re)post
    post_status = Column(String(16), default="none")      # none|posted|failed
    post_error = Column(String(255), nullable=True)

    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    tasks = relationship(
        "CampaignTask", back_populates="campaign",
        cascade="all, delete-orphan", order_by="CampaignTask.order",
    )
    submissions = relationship(
        "CampaignSubmission", back_populates="campaign", cascade="all, delete-orphan"
    )

    @property
    def is_open(self) -> bool:
        if self.status != "active":
            return False
        now = datetime.utcnow()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now >= self.ends_at:
            return False
        return True

    def to_dict(self, include_tasks=True, include_counts=False) -> dict:
        d = {
            "id": self.id,
            "guild_id": str(self.guild_id),
            "type": self.type,
            "title": self.title,
            "description": self.description or "",
            "task_url": self.task_url,
            "verification_mode": self.verification_mode,
            "reward_xp": self.reward_xp or 0,
            "reward_label": self.reward_label,
            "status": self.status,
            "is_open": self.is_open,
            "starts_at": self.starts_at.isoformat() + "Z" if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() + "Z" if self.ends_at else None,
            "one_per_user": bool(self.one_per_user),
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "message_id": str(self.message_id) if self.message_id else None,
            "post_status": self.post_status or "none",
            "post_error": self.post_error,
            "settings": self.settings or {},
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
        if include_tasks:
            d["tasks"] = [t.to_dict() for t in self.tasks]
        return d


class CampaignTask(Base):
    """One sub-task of a multi-task campaign, with its own reward + proof button."""

    __tablename__ = "campaign_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    order = Column(Integer, default=0)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    type = Column(String(32), default="social_task")
    task_url = Column(String(2000), nullable=True)
    verification_mode = Column(String(20), default="manual")
    reward_xp = Column(Integer, default=0)

    campaign = relationship("Campaign", back_populates="tasks")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "order": self.order,
            "title": self.title,
            "description": self.description or "",
            "type": self.type,
            "task_url": self.task_url,
            "verification_mode": self.verification_mode,
            "reward_xp": self.reward_xp or 0,
        }


class CampaignSubmission(Base):
    """A user's proof submission for a campaign (or one of its tasks)."""

    __tablename__ = "campaign_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("campaign_tasks.id"), nullable=True, index=True)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(120))
    status = Column(String(16), default="pending")        # pending|verified|rejected
    proof = Column(JSON, default=dict)                    # {"value": "...url/text"}
    reward_granted = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewer_id = Column(BigInteger, nullable=True)

    campaign = relationship("Campaign", back_populates="submissions")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "task_id": self.task_id,
            "user_id": str(self.user_id),
            "username": self.username,
            "status": self.status,
            "proof": self.proof or {},
            "reward_granted": self.reward_granted or 0,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "reviewed_at": self.reviewed_at.isoformat() + "Z" if self.reviewed_at else None,
        }
