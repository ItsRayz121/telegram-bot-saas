from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    subscription_tier = db.Column(db.String(50), default="free", nullable=False)
    subscription_expires = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(255), nullable=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    bots = db.relationship("Bot", backref="owner", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "subscription_tier": self.subscription_tier,
            "subscription_expires": self.subscription_expires.isoformat() if self.subscription_expires else None,
            "is_banned": self.is_banned,
            "created_at": self.created_at.isoformat(),
        }


class Bot(db.Model):
    __tablename__ = "bots"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    bot_token = db.Column(db.String(255), unique=True, nullable=False)
    bot_username = db.Column(db.String(255), nullable=True)
    bot_name = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_active = db.Column(db.DateTime, nullable=True)

    groups = db.relationship("Group", backref="bot", lazy=True, cascade="all, delete-orphan")

    def to_dict(self, include_token=False):
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "bot_username": self.bot_username,
            "bot_name": self.bot_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "group_count": len(self.groups),
        }
        if include_token:
            data["bot_token"] = self.bot_token
        return data


class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey("bots.id"), nullable=False)
    telegram_group_id = db.Column(db.String(255), nullable=False)
    group_name = db.Column(db.String(255), nullable=True)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    telegram_member_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    members = db.relationship("Member", backref="group", lazy=True, cascade="all, delete-orphan")
    audit_logs = db.relationship("AuditLog", backref="group", lazy=True, cascade="all, delete-orphan")
    scheduled_messages = db.relationship("ScheduledMessage", backref="group", lazy=True, cascade="all, delete-orphan")
    raids = db.relationship("Raid", backref="group", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "telegram_group_id": self.telegram_group_id,
            "group_name": self.group_name,
            "settings": self.settings,
            "created_at": self.created_at.isoformat(),
            "member_count": self.telegram_member_count if self.telegram_member_count else len(self.members),
        }


class Member(db.Model):
    __tablename__ = "members"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    telegram_user_id = db.Column(db.String(255), nullable=False)
    username = db.Column(db.String(255), nullable=True)
    first_name = db.Column(db.String(255), nullable=True)
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    warnings = db.Column(db.Integer, default=0)
    role = db.Column(db.String(50), default="member")
    is_verified = db.Column(db.Boolean, default=False)
    is_muted = db.Column(db.Boolean, default=False)
    mute_until = db.Column(db.DateTime, nullable=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_message_at = db.Column(db.DateTime, nullable=True)
    last_xp_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (db.UniqueConstraint("group_id", "telegram_user_id", name="unique_group_member"),)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "telegram_user_id": self.telegram_user_id,
            "username": self.username,
            "first_name": self.first_name,
            "xp": self.xp,
            "level": self.level,
            "warnings": self.warnings,
            "role": self.role,
            "is_verified": self.is_verified,
            "is_muted": self.is_muted,
            "mute_until": self.mute_until.isoformat() if self.mute_until else None,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    target_user_id = db.Column(db.String(255), nullable=True)
    target_username = db.Column(db.String(255), nullable=True)
    moderator_id = db.Column(db.String(255), nullable=True)
    moderator_username = db.Column(db.String(255), nullable=True)
    reason = db.Column(db.Text, nullable=True)
    extra_data = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "action_type": self.action_type,
            "target_user_id": self.target_user_id,
            "target_username": self.target_username,
            "moderator_id": self.moderator_id,
            "moderator_username": self.moderator_username,
            "reason": self.reason,
            "extra_data": self.extra_data,
            "timestamp": self.timestamp.isoformat(),
        }


class ScheduledMessage(db.Model):
    __tablename__ = "scheduled_messages"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    media_url = db.Column(db.String(500), nullable=True)
    buttons = db.Column(db.JSON, nullable=True)
    send_at = db.Column(db.DateTime, nullable=False)
    repeat_interval = db.Column(db.Integer, nullable=True)
    stop_date = db.Column(db.DateTime, nullable=True)
    pin_message = db.Column(db.Boolean, default=False)
    auto_delete_after = db.Column(db.Integer, nullable=True)
    is_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "title": self.title,
            "message_text": self.message_text,
            "media_url": self.media_url,
            "buttons": self.buttons,
            "send_at": self.send_at.isoformat(),
            "repeat_interval": self.repeat_interval,
            "stop_date": self.stop_date.isoformat() if self.stop_date else None,
            "pin_message": self.pin_message,
            "auto_delete_after": self.auto_delete_after,
            "is_sent": self.is_sent,
            "created_at": self.created_at.isoformat(),
        }


class Raid(db.Model):
    __tablename__ = "raids"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    tweet_url = db.Column(db.String(500), nullable=False)
    goals = db.Column(db.JSON, nullable=False, default=dict)
    duration_hours = db.Column(db.Integer, default=24)
    xp_reward = db.Column(db.Integer, default=100)
    pin_message = db.Column(db.Boolean, default=True)
    reminders_enabled = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    participants = db.Column(db.JSON, nullable=False, default=list)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "tweet_url": self.tweet_url,
            "goals": self.goals,
            "duration_hours": self.duration_hours,
            "xp_reward": self.xp_reward,
            "pin_message": self.pin_message,
            "reminders_enabled": self.reminders_enabled,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "participants": self.participants,
        }
