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

    # Legacy OAuth2 token columns — no longer written (tokens are used in-hand
    # during the OAuth callback and never persisted). Kept for schema compat;
    # values are nulled on each login.
    access_token = Column(String(255))
    refresh_token = Column(String(255))
    token_expires_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, default=datetime.utcnow)
    admin_notes = Column(Text, nullable=True)          # platform-admin private notes

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
    # Which bot identity serves this guild. NULL = the official Guildizer bot.
    # Set when a white-label custom bot joins (auto-link) or via the dashboard.
    custom_bot_id = Column(Integer, nullable=True)
    member_count = Column(Integer, default=0)
    plan = Column(String(16), default="free")          # free | pro (set by billing)
    plan_expires_at = Column(DateTime, nullable=True)  # null = no expiry

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
            "custom_bot_id": self.custom_bot_id,
            "member_count": self.member_count or 0,
            "plan": self.plan or "free",
            "is_pro": self.is_pro,
            "plan_expires_at": self.plan_expires_at.isoformat() + "Z" if self.plan_expires_at else None,
        }

    @property
    def is_pro(self) -> bool:
        if (self.plan or "free") != "pro":
            return False
        if self.plan_expires_at and self.plan_expires_at < datetime.utcnow():
            return False
        return True


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
    # Phase 15 CRM fields (healed via database._HEAL_COLUMNS on live DBs)
    last_seen = Column(DateTime, nullable=True)
    wallet = Column(String(120), nullable=True)
    admin_notes = Column(Text, nullable=True)
    # Voice XP (healed): total minutes counted by the voice loop
    voice_minutes = Column(Integer, nullable=True)

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "xp": self.xp or 0,
            "level": self.level or 1,
            "messages": self.messages or 0,
            "last_seen": self.last_seen.isoformat() + "Z" if self.last_seen else None,
            "wallet": self.wallet,
            "admin_notes": self.admin_notes,
            "voice_minutes": self.voice_minutes or 0,
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


class Subscription(Base):
    """A Pro upgrade purchase for a guild, paid via NOWPayments. The IPN webhook
    flips the row to active and sets the guild's plan + expiry."""

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=True)           # who initiated checkout
    plan = Column(String(16), default="pro")
    status = Column(String(16), default="pending")        # pending|active|expired|failed
    provider = Column(String(24), default="nowpayments")
    order_id = Column(String(80), unique=True, index=True)  # our id, sent to provider
    invoice_id = Column(String(80), nullable=True)        # provider invoice id
    payment_id = Column(String(80), nullable=True)        # provider payment id
    amount = Column(Integer, default=0)                   # price in whole USD
    currency = Column(String(8), default="usd")
    period_days = Column(Integer, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "plan": self.plan,
            "status": self.status,
            "order_id": self.order_id,
            "amount": self.amount,
            "currency": self.currency,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "expires_at": self.expires_at.isoformat() + "Z" if self.expires_at else None,
        }


class Reminder(Base):
    """A user reminder set via /remind. The due loop DMs the user when due."""

    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=True)          # where it was set (context)
    user_id = Column(BigInteger, nullable=False, index=True)
    text = Column(String(500))
    due_at = Column(DateTime, nullable=False, index=True)
    delivered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "due_at": self.due_at.isoformat() + "Z" if self.due_at else None,
            "delivered": bool(self.delivered),
        }


class Note(Base):
    """A personal note saved via /note."""

    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    guild_id = Column(BigInteger, nullable=True)
    content = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content or "",
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class AITokenUsage(Base):
    """Append-only ledger of AI token consumption (cost/usage analytics)."""

    __tablename__ = "ai_token_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=True)
    user_id = Column(BigInteger, nullable=True)
    model = Column(String(64))
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class CustomBot(Base):
    """A white-label ("bring your own token") Discord bot powered by the
    Guildizer engine. The token is Fernet-encrypted at rest (crypto.py) and is
    only ever decrypted inside the bot worker; it is never returned to the
    frontend after save and never logged.

    Status: active   — fleet worker should run a gateway client for it
            disabled — owner turned it off (kept for re-enable)
            error    — token rejected (401) or decrypt failed; needs a new token
    """

    __tablename__ = "custom_bots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    application_id = Column(BigInteger, nullable=False)      # Discord app id (client_id for invites)
    bot_user_id = Column(BigInteger, nullable=False, unique=True)
    bot_username = Column(String(120))
    bot_avatar = Column(String(255))
    token_encrypted = Column(Text, nullable=False)
    status = Column(String(16), default="active", nullable=False)
    error_detail = Column(String(300))
    # Privileged-intent toggles read from the app's flags at validation time.
    # Both must be on in the owner's Developer Portal or the gateway login fails.
    intents_members = Column(Boolean, default=False)
    intents_message_content = Column(Boolean, default=False)
    # Dirty flag: API -> worker. Set on token change / re-enable; worker restarts
    # the client and clears it.
    needs_restart = Column(Boolean, default=False)
    last_online_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User")

    def avatar_url(self) -> str | None:
        if not self.bot_avatar:
            return None
        return f"https://cdn.discordapp.com/avatars/{self.bot_user_id}/{self.bot_avatar}.png"

    @property
    def intents_ok(self) -> bool:
        return bool(self.intents_members and self.intents_message_content)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "application_id": str(self.application_id),
            "bot_user_id": str(self.bot_user_id),
            "bot_username": self.bot_username,
            "avatar_url": self.avatar_url(),
            "status": self.status,
            "error_detail": self.error_detail,
            "intents_members": bool(self.intents_members),
            "intents_message_content": bool(self.intents_message_content),
            "intents_ok": self.intents_ok,
            "last_online_at": self.last_online_at.isoformat() + "Z" if self.last_online_at else None,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class BotHealthEvent(Base):
    """Connect/disconnect/error history per bot identity, for the dashboard and
    the admin fleet view. custom_bot_id NULL = the official bot."""

    __tablename__ = "bot_health_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    custom_bot_id = Column(Integer, nullable=True, index=True)
    event = Column(String(20), nullable=False)   # connect | disconnect | error | auth_failed
    detail = Column(String(300))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "custom_bot_id": self.custom_bot_id,
            "event": self.event,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class MemberWarning(Base):
    """A moderator-issued warning. Counted toward the guild's warning ladder
    (max warnings -> escalation action, configured in ModerationSettings.extra)."""

    __tablename__ = "warnings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    username = Column(String(120))
    moderator_id = Column(BigInteger, nullable=True)    # NULL = automod
    moderator_name = Column(String(120))
    reason = Column(String(300))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": str(self.user_id),
            "username": self.username,
            "moderator_id": str(self.moderator_id) if self.moderator_id else None,
            "moderator_name": self.moderator_name,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class ModReport(Base):
    """A member-filed report (/report or right-click message -> Report) feeding
    the dashboard review queue."""

    __tablename__ = "mod_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    reporter_id = Column(BigInteger, nullable=False)
    reporter_name = Column(String(120))
    target_id = Column(BigInteger, nullable=True)
    target_name = Column(String(120))
    channel_id = Column(BigInteger, nullable=True)
    message_id = Column(BigInteger, nullable=True)
    message_excerpt = Column(String(500))
    reason = Column(String(300))
    status = Column(String(16), default="open", nullable=False)  # open|actioned|dismissed
    reviewed_by = Column(BigInteger, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "reporter_id": str(self.reporter_id),
            "reporter_name": self.reporter_name,
            "target_id": str(self.target_id) if self.target_id else None,
            "target_name": self.target_name,
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "message_id": str(self.message_id) if self.message_id else None,
            "message_excerpt": self.message_excerpt,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class ScheduledModAction(Base):
    """Deferred moderation work the bot executes when due — today: tempban
    expiry (unban). Timeouts expire natively on Discord, so they need no row."""

    __tablename__ = "scheduled_mod_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(120))
    action = Column(String(16), nullable=False)          # unban
    reason = Column(String(300))
    due_at = Column(DateTime, nullable=False, index=True)
    done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PendingVerification(Base):
    """A join-captcha challenge awaiting the member's response (Phase 11).
    Expired rows are swept by the bot loop (kick/keep per config)."""

    __tablename__ = "pending_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    username = Column(String(120))
    method = Column(String(10), default="button")     # button | math | word
    answer = Column(String(40))                       # expected modal answer (math/word)
    prompt = Column(String(120))                      # shown in the modal (question/word)
    attempts = Column(Integer, default=0)
    channel_id = Column(BigInteger, nullable=True)    # where the challenge was posted
    message_id = Column(BigInteger, nullable=True)    # the challenge message
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScheduledMessage(Base):
    """A dashboard-scheduled message the bot posts when due, with optional
    recurrence (Phase 12). Bot/API coordinate via next_run_at only."""

    __tablename__ = "scheduled_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    channel_id = Column(BigInteger, nullable=False)
    content = Column(Text, default="")
    # Optional rich embed: {title, description, color, image_url, thumbnail_url,
    # footer} — sanitized by the API, rendered by the bot (Phase 4 native).
    embed = Column(JSON, nullable=True)
    recurrence = Column(String(10), default="none")    # none | hourly | daily | weekly
    next_run_at = Column(DateTime, nullable=False, index=True)
    last_sent_at = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=True)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel_id": str(self.channel_id),
            "content": self.content or "",
            "embed": dict(self.embed) if self.embed else None,
            "recurrence": self.recurrence or "none",
            "next_run_at": self.next_run_at.isoformat() + "Z" if self.next_run_at else None,
            "last_sent_at": self.last_sent_at.isoformat() + "Z" if self.last_sent_at else None,
            "enabled": bool(self.enabled),
        }


class Poll(Base):
    """A native Discord poll created from the dashboard (Phase 12). The bot
    posts it (needs_post), then finalizes the vote counts after it closes."""

    __tablename__ = "polls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    channel_id = Column(BigInteger, nullable=False)
    question = Column(String(300), nullable=False)
    answers = Column(JSON, default=list)               # list[str] (2-10)
    duration_hours = Column(Integer, default=24)       # 1-768 (Discord cap: 32 days)
    multiselect = Column(Boolean, default=False)
    needs_post = Column(Boolean, default=True)
    message_id = Column(BigInteger, nullable=True)
    status = Column(String(12), default="pending")     # pending | open | ended | failed
    ends_at = Column(DateTime, nullable=True)
    results = Column(JSON, default=dict)               # {answer_text: votes}
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel_id": str(self.channel_id),
            "question": self.question,
            "answers": list(self.answers or []),
            "duration_hours": self.duration_hours or 24,
            "multiselect": bool(self.multiselect),
            "status": self.status,
            "ends_at": self.ends_at.isoformat() + "Z" if self.ends_at else None,
            "results": dict(self.results or {}),
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class GuildEvent(Base):
    """A Discord scheduled event created from the dashboard (Phase 4 native).
    The bot creates it on Discord (needs_create), optionally posts a channel
    reminder shortly before start, and deletes it on dashboard cancel
    (needs_delete). Bot/API coordinate only through this row."""

    __tablename__ = "guild_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(1000), default="")
    entity_type = Column(String(10), default="external")  # external | voice | stage
    channel_id = Column(BigInteger, nullable=True)         # voice/stage channel
    location = Column(String(200), nullable=True)          # external events
    start_at = Column(DateTime, nullable=False, index=True)
    end_at = Column(DateTime, nullable=True)               # required for external
    remind_minutes = Column(Integer, default=15)           # 0 = no reminder
    reminder_channel_id = Column(BigInteger, nullable=True)
    needs_create = Column(Boolean, default=True)
    needs_delete = Column(Boolean, default=False)
    reminded = Column(Boolean, default=False)
    discord_event_id = Column(BigInteger, nullable=True)
    status = Column(String(12), default="pending")  # pending | created | done | failed | cancelled
    error = Column(String(200), nullable=True)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "entity_type": self.entity_type or "external",
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "location": self.location,
            "start_at": self.start_at.isoformat() + "Z" if self.start_at else None,
            "end_at": self.end_at.isoformat() + "Z" if self.end_at else None,
            "remind_minutes": self.remind_minutes or 0,
            "reminder_channel_id": str(self.reminder_channel_id) if self.reminder_channel_id else None,
            "discord_event_id": str(self.discord_event_id) if self.discord_event_id else None,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class GuildBackup(Base):
    """A snapshot of the server's roles/channels/permission overwrites (Phase 4
    native). The bot fills `data` from its cache (needs_snapshot) and re-applies
    it on restore (needs_restore) — restore edits drifted items and recreates
    missing ones by stored id/name, but never deletes anything."""

    __tablename__ = "guild_backups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    label = Column(String(100), default="")
    data = Column(JSON, nullable=True)        # {everyone, roles: [...], channels: [...]}
    # pending | done | failed | restoring | restored | restore_failed
    status = Column(String(16), default="pending")
    needs_snapshot = Column(Boolean, default=True)
    needs_restore = Column(Boolean, default=False)
    error = Column(String(200), nullable=True)
    roles_count = Column(Integer, default=0)
    channels_count = Column(Integer, default=0)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    restored_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label or "",
            "status": self.status,
            "error": self.error,
            "roles_count": self.roles_count or 0,
            "channels_count": self.channels_count or 0,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "restored_at": self.restored_at.isoformat() + "Z" if self.restored_at else None,
        }


class AutoResponse(Base):
    """Keyword trigger -> bot reply (Phase 12). Cooldown is enforced in-memory
    by the bot (per guild+trigger)."""

    __tablename__ = "auto_responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    trigger = Column(String(120), nullable=False)
    match_type = Column(String(10), default="contains")  # contains | exact
    response = Column(Text, default="")
    cooldown_seconds = Column(Integer, default=30)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "trigger": self.trigger,
            "match_type": self.match_type or "contains",
            "response": self.response or "",
            "cooldown_seconds": self.cooldown_seconds or 30,
            "enabled": bool(self.enabled),
        }


class AutomationWorkflow(Base):
    """Trigger -> actions automation (Phase 13). Actions is an ordered JSON list
    of {type, ...} steps the bot executes when the trigger fires."""

    __tablename__ = "automation_workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    enabled = Column(Boolean, default=True)
    # message_contains | member_join | member_leave | reaction_add
    trigger_type = Column(String(20), nullable=False)
    trigger_value = Column(String(120))                # keyword / emoji, where applicable
    channel_filter = Column(BigInteger, nullable=True)  # only fire in this channel
    # [{type: send_message, channel_id?, text} | {type: add_role|remove_role, role_id}
    #  | {type: timeout, minutes} | {type: webhook, url}]
    actions = Column(JSON, default=list)
    cooldown_seconds = Column(Integer, default=0)
    runs_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": bool(self.enabled),
            "trigger_type": self.trigger_type,
            "trigger_value": self.trigger_value or "",
            "channel_filter": str(self.channel_filter) if self.channel_filter else None,
            "actions": list(self.actions or []),
            "cooldown_seconds": self.cooldown_seconds or 0,
            "runs_count": self.runs_count or 0,
        }


class AutomationExecution(Base):
    """One workflow run (audit trail for the dashboard)."""

    __tablename__ = "automation_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("automation_workflows.id"), nullable=False, index=True)
    guild_id = Column(BigInteger, nullable=False, index=True)
    status = Column(String(10), default="ok")          # ok | error
    detail = Column(String(300))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class MirrorRule(Base):
    """Mirror messages from a source channel to a destination channel via a
    Discord webhook with author name/avatar impersonation (Phase 13). The
    destination may be in another server; the bot creates the webhook once and
    caches its URL here."""

    __tablename__ = "mirror_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)  # source guild
    source_channel_id = Column(BigInteger, nullable=False, index=True)
    dest_channel_id = Column(BigInteger, nullable=False)
    webhook_url = Column(Text)                          # cached after first creation
    enabled = Column(Boolean, default=True)
    mirrored_count = Column(Integer, default=0)
    last_error = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_channel_id": str(self.source_channel_id),
            "dest_channel_id": str(self.dest_channel_id),
            "enabled": bool(self.enabled),
            "mirrored_count": self.mirrored_count or 0,
            "last_error": self.last_error,
            "has_webhook": bool(self.webhook_url),
        }


class InboundWebhook(Base):
    """A secret URL outsiders can POST to; the bot relays the payload into a
    channel (Phase 13). The token in the URL is the credential."""

    __tablename__ = "inbound_webhooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    channel_id = Column(BigInteger, nullable=False)
    name = Column(String(120))
    token = Column(String(64), unique=True, nullable=False, index=True)
    enabled = Column(Boolean, default=True)
    received_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "channel_id": str(self.channel_id),
            "token": self.token,
            "enabled": bool(self.enabled),
            "received_count": self.received_count or 0,
            "last_used_at": self.last_used_at.isoformat() + "Z" if self.last_used_at else None,
        }


class OutboundWebhook(Base):
    """Server events POSTed to an external URL (Phase 13): member_join,
    member_leave, moderation_action, raid_activated. Optional HMAC secret."""

    __tablename__ = "outbound_webhooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    url = Column(String(500), nullable=False)
    events = Column(JSON, default=list)                 # subset of OUTBOUND_EVENTS
    secret = Column(String(120))
    enabled = Column(Boolean, default=True)
    delivered_count = Column(Integer, default=0)
    last_error = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "events": list(self.events or []),
            "has_secret": bool(self.secret),
            "enabled": bool(self.enabled),
            "delivered_count": self.delivered_count or 0,
            "last_error": self.last_error,
        }


class InviteLink(Base):
    """A tracked server invite (created via /invitelink or synced from the
    guild) used for referral attribution (Phase 14)."""

    __tablename__ = "invite_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    creator_id = Column(BigInteger, nullable=True)
    creator_name = Column(String(120))
    uses = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "url": f"https://discord.gg/{self.code}",
            "creator_id": str(self.creator_id) if self.creator_id else None,
            "creator_name": self.creator_name,
            "uses": self.uses or 0,
        }


class InviteJoin(Base):
    """One attributed join: which invite (and inviter) brought the member in."""

    __tablename__ = "invite_joins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    code = Column(String(20), index=True)
    inviter_id = Column(BigInteger, nullable=True, index=True)
    inviter_name = Column(String(120))
    joiner_id = Column(BigInteger, nullable=False)
    joiner_name = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "inviter_id": str(self.inviter_id) if self.inviter_id else None,
            "inviter_name": self.inviter_name,
            "joiner_id": str(self.joiner_id),
            "joiner_name": self.joiner_name,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class CampaignCustomField(Base):
    """An extra input collected in the proof modal (Phase 14). Up to 4 per
    campaign (Discord modals cap at 5 components incl. the proof field)."""

    __tablename__ = "campaign_custom_fields"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    label = Column(String(45), nullable=False)
    required = Column(Boolean, default=True)
    position = Column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "required": bool(self.required),
            "position": self.position or 0,
        }


class GuildDailyStat(Base):
    """Per-day activity rollup (Phase 15): message/join/leave counts buffered
    in the bot and flushed every minute. day = 'YYYY-MM-DD' (UTC)."""

    __tablename__ = "guild_daily_stats"

    guild_id = Column(BigInteger, ForeignKey("guilds.id"), primary_key=True)
    day = Column(String(10), primary_key=True)
    messages = Column(Integer, default=0)
    joins = Column(Integer, default=0)
    leaves = Column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "day": self.day,
            "messages": self.messages or 0,
            "joins": self.joins or 0,
            "leaves": self.leaves or 0,
        }


class FeatureUsageEvent(Base):
    """One feature interaction (Phase 15 usage spine) — today: every completed
    slash command. Feeds the admin usage analytics later."""

    __tablename__ = "feature_usage_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, nullable=True, index=True)
    user_id = Column(BigInteger, nullable=True)
    feature = Column(String(40), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class KnowledgeDocument(Base):
    """Per-server knowledge base content that grounds /ask answers (Phase 16)."""

    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content or "",
            "enabled": bool(self.enabled),
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }


class Task(Base):
    """A personal task managed via /task /tasks /done or the DM assistant
    (Phase 17). Personal scope like reminders/notes; guild_id is context only."""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    guild_id = Column(BigInteger, nullable=True)
    text = Column(String(500), nullable=False)
    done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    done_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "done": bool(self.done),
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class GuildTeamMember(Base):
    """Dashboard access granted to a user who lacks Manage Server on Discord
    (Phase 18). Redeeming a TeamInvite creates one of these; access checks
    treat it like UserGuild.can_manage."""

    __tablename__ = "guild_team_members"

    guild_id = Column(BigInteger, ForeignKey("guilds.id"), primary_key=True)
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(120))
    role = Column(String(12), default="manager")    # manager (viewer reserved)
    invited_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "role": self.role or "manager",
            "invited_by": str(self.invited_by) if self.invited_by else None,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class TeamInvite(Base):
    """A one-use code that grants dashboard access to a guild (Phase 18)."""

    __tablename__ = "team_invites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), nullable=False, index=True)
    code = Column(String(32), unique=True, nullable=False, index=True)
    role = Column(String(12), default="manager")
    created_by = Column(BigInteger, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_by = Column(BigInteger, nullable=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "role": self.role or "manager",
            "expires_at": self.expires_at.isoformat() + "Z" if self.expires_at else None,
            "used_by": str(self.used_by) if self.used_by else None,
        }


class UserNotification(Base):
    """Dashboard notification for a user (Phase 18): bot health problems,
    team changes, billing events."""

    __tablename__ = "user_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    kind = Column(String(20), default="info")       # info | warning | error
    title = Column(String(120), nullable=False)
    body = Column(String(500))
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind or "info",
            "title": self.title,
            "body": self.body or "",
            "read": bool(self.read),
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class PromoCode(Base):
    """A promo code granting free Pro days to a guild (Phase 18). Created by
    platform admins; redeemed on the Billing tab."""

    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(40), unique=True, nullable=False, index=True)
    days_free = Column(Integer, default=30)
    max_uses = Column(Integer, default=1)
    used_count = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "days_free": self.days_free or 0,
            "max_uses": self.max_uses or 1,
            "used_count": self.used_count or 0,
            "enabled": bool(self.enabled),
            "expires_at": self.expires_at.isoformat() + "Z" if self.expires_at else None,
        }


class PromoCodeUsage(Base):
    """One redemption of a promo code (per guild, prevents re-use)."""

    __tablename__ = "promo_code_usages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False, index=True)
    guild_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AdminRole(Base):
    """A DB-granted platform-admin seat (Phase 19). ADMIN_USER_IDS env stays the
    super-admin bootstrap; rows here add support staff without redeploys."""

    __tablename__ = "admin_roles"

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(120))
    role = Column(String(12), default="support")    # support | super
    granted_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "username": self.username,
            "role": self.role or "support",
            "granted_by": str(self.granted_by) if self.granted_by else None,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class AdminAuditLog(Base):
    """Every mutating platform-admin action (Phase 19)."""

    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(BigInteger, nullable=False, index=True)
    action = Column(String(40), nullable=False)
    target = Column(String(80))
    detail = Column(String(300))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "admin_id": str(self.admin_id),
            "action": self.action,
            "target": self.target,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }


class AdminAnnouncement(Base):
    """A platform notice authored in the admin panel (Compliance & Comms). Stored
    + togglable; consumers (dashboard banner) read the active ones."""

    __tablename__ = "admin_announcements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, default="")
    level = Column(String(16), default="info")   # info | warning | critical
    active = Column(Boolean, default=True, nullable=False)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body or "",
            "level": self.level or "info",
            "active": bool(self.active),
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
