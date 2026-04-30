from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
import secrets
import string

db = SQLAlchemy()

# Referral milestones: (required_count, reward_days)
REFERRAL_MILESTONES = [(3, 7), (10, 30)]


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    subscription_tier = db.Column(db.String(50), default="free", nullable=False)
    subscription_expires = db.Column(db.DateTime, nullable=True)
    # Legacy Stripe columns — kept to avoid dropping data; Stripe is not active.
    stripe_customer_id = db.Column(db.String(255), nullable=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # Unique referral code assigned at registration
    referral_code = db.Column(db.String(16), unique=True, nullable=True, index=True)
    # Email verification
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verification_token = db.Column(db.String(64), nullable=True, index=True)
    email_verification_expires = db.Column(db.DateTime, nullable=True)
    # Brute-force login protection
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    # 2FA / TOTP (secret stored encrypted)
    totp_secret = db.Column(db.String(255), nullable=True)
    totp_enabled = db.Column(db.Boolean, default=False, nullable=False)
    totp_backup_codes = db.Column(db.JSON, nullable=True)  # list of bcrypt-hashed backup codes
    # Anti-abuse: hashed signup identifiers (SHA-256; never raw IP or fingerprint)
    signup_ip_hash = db.Column(db.String(64), nullable=True, index=True)
    device_fingerprint_hash = db.Column(db.String(64), nullable=True, index=True)
    is_suspicious = db.Column(db.Boolean, default=False, nullable=False)
    # Telegram account linkage
    telegram_user_id = db.Column(db.String(255), nullable=True, unique=True, index=True)
    telegram_username = db.Column(db.String(255), nullable=True)
    telegram_first_name = db.Column(db.String(255), nullable=True)
    telegram_connected_at = db.Column(db.DateTime, nullable=True)
    # Workspace AI token usage tracking (reset daily)
    workspace_ai_tokens_today = db.Column(db.Integer, default=0, nullable=False)
    workspace_ai_tokens_reset_at = db.Column(db.DateTime, nullable=True)

    bots = db.relationship("Bot", backref="owner", lazy=True, cascade="all, delete-orphan")

    def get_or_create_referral_code(self):
        if not self.referral_code:
            self.referral_code = secrets.token_urlsafe(16)
        return self.referral_code

    _GRACE_DAYS = 3  # paid features remain accessible this many days after expiry

    @property
    def subscription_active(self) -> bool:
        """True if the user has a paid plan that is current OR within the 3-day grace window."""
        if self.subscription_tier == "free":
            return False
        if self.subscription_expires is None:
            return True  # admin-granted, no expiry
        grace_deadline = self.subscription_expires + timedelta(days=self._GRACE_DAYS)
        return datetime.utcnow() <= grace_deadline

    @property
    def is_locked(self):
        return self.locked_until is not None and datetime.utcnow() < self.locked_until

    def generate_verification_token(self):
        token = secrets.token_urlsafe(32)
        self.email_verification_token = token
        self.email_verification_expires = datetime.utcnow() + timedelta(hours=24)
        return token

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "subscription_tier": self.subscription_tier,
            "subscription_expires": self.subscription_expires.isoformat() if self.subscription_expires else None,
            "is_banned": self.is_banned,
            "created_at": self.created_at.isoformat(),
            "referral_code": self.referral_code,
            "email_verified": self.email_verified,
            "totp_enabled": self.totp_enabled,
            "telegram_connected": bool(self.telegram_user_id),
            "telegram_username": self.telegram_username,
            "telegram_first_name": self.telegram_first_name,
            "telegram_connected_at": self.telegram_connected_at.isoformat() if self.telegram_connected_at else None,
        }


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

    @staticmethod
    def create_for_user(user_id):
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        return PasswordResetToken(user_id=user_id, token=token, expires_at=expires_at)

    @property
    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at


class RevokedToken(db.Model):
    """DB-backed JWT blocklist used as Redis fallback for logout/revocation."""
    __tablename__ = "revoked_tokens"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Bot(db.Model):
    __tablename__ = "bots"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # Stores the Fernet-encrypted token; use get_token()/set_token() helpers.
    bot_token = db.Column(db.Text, nullable=False)
    # SHA-256 hash of the plain token used for fast uniqueness checks.
    bot_token_hash = db.Column(db.String(64), unique=True, nullable=True, index=True)
    bot_username = db.Column(db.String(255), nullable=True)
    bot_name = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_active = db.Column(db.DateTime, nullable=True)

    groups = db.relationship("Group", backref="bot", lazy=True, cascade="all, delete-orphan")

    def get_token(self) -> str:
        """Return the decrypted plain-text bot token."""
        from .utils.encryption import decrypt_value
        return decrypt_value(self.bot_token)

    def set_token(self, plain_token: str):
        """Encrypt and store the bot token; update the hash column."""
        from .utils.encryption import encrypt_value, hash_token
        self.bot_token = encrypt_value(plain_token) or plain_token
        self.bot_token_hash = hash_token(plain_token)

    def get_health_status(self):
        """Derive health from is_active + last_active age. No extra DB column needed."""
        if not self.is_active:
            return "stopped"
        if self.last_active is None:
            return "unknown"
        age = datetime.utcnow() - self.last_active
        if age < timedelta(hours=1):
            return "active"
        if age < timedelta(hours=24):
            return "warning"
        return "error"

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
            "health_status": self.get_health_status(),
        }
        if include_token:
            data["bot_token"] = self.get_token()
        return data


class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey("bots.id"), nullable=False)
    telegram_group_id = db.Column(db.String(255), nullable=False)
    group_name = db.Column(db.String(255), nullable=True)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    telegram_member_count = db.Column(db.Integer, default=0)
    # Dedicated column so timezone is queryable and not buried in the JSON blob.
    # Authoritative source; groups.settings["timezone"] is kept in sync.
    timezone = db.Column(db.String(50), default="UTC", nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("bot_id", "telegram_group_id", name="uq_bot_telegram_group"),
    )

    members = db.relationship("Member", backref="group", lazy=True, cascade="all, delete-orphan")
    audit_logs = db.relationship("AuditLog", backref="group", lazy=True, cascade="all, delete-orphan")
    scheduled_messages = db.relationship("ScheduledMessage", backref="group", lazy=True, cascade="all, delete-orphan")
    raids = db.relationship("Raid", backref="group", lazy=True, cascade="all, delete-orphan")
    knowledge_documents = db.relationship("KnowledgeDocument", backref="group", lazy=True, cascade="all, delete-orphan")
    polls = db.relationship("Poll", backref="group", lazy=True, cascade="all, delete-orphan")
    webhook_integrations = db.relationship("WebhookIntegration", backref="group", lazy=True, cascade="all, delete-orphan")
    invite_links = db.relationship("InviteLink", backref="group", lazy=True, cascade="all, delete-orphan")
    api_keys = db.relationship("UserApiKey", backref="group", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "telegram_group_id": self.telegram_group_id,
            "group_name": self.group_name,
            "settings": self.settings,
            "timezone": self.timezone or "UTC",
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
    wallet_address = db.Column(db.String(500), nullable=True)
    wallet_submitted_at = db.Column(db.DateTime, nullable=True)

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
            "wallet_address": self.wallet_address,
            "wallet_submitted_at": self.wallet_submitted_at.isoformat() if self.wallet_submitted_at else None,
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
    link_preview_enabled = db.Column(db.Boolean, default=True)
    topic_id = db.Column(db.BigInteger, nullable=True)
    timezone = db.Column(db.String(50), nullable=False, default='UTC', server_default='UTC')
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
            "send_at": self.send_at.isoformat() + "Z",
            "repeat_interval": self.repeat_interval,
            "stop_date": (self.stop_date.isoformat() + "Z") if self.stop_date else None,
            "pin_message": self.pin_message,
            "auto_delete_after": self.auto_delete_after,
            "link_preview_enabled": self.link_preview_enabled,
            "topic_id": self.topic_id,
            "timezone": self.timezone or "UTC",
            "is_sent": self.is_sent,
            "created_at": self.created_at.isoformat() + "Z",
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


class AutoResponse(db.Model):
    __tablename__ = "auto_responses"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    telegram_group_id = db.Column(db.String(255), nullable=True, index=True)
    trigger_text = db.Column(db.String(500), nullable=False)
    response_text = db.Column(db.Text, nullable=False)
    match_type = db.Column(db.String(20), default="contains")  # exact|contains|starts_with
    is_case_sensitive = db.Column(db.Boolean, default=False)
    is_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Smart Links extension (Workspace feature)
    # response_type: 'auto_response' (default) | 'smart_link'
    response_type = db.Column(db.String(20), default="auto_response", nullable=False)
    link_label = db.Column(db.String(100), nullable=True)   # human name: "Calendly Link"
    link_url = db.Column(db.String(2000), nullable=True)    # the URL (optional; else response_text used)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    # scope: 'group' = this group only | 'user' = all groups this user owns
    scope = db.Column(db.String(20), default="group", nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "telegram_group_id": self.telegram_group_id,
            "trigger_text": self.trigger_text,
            "response_text": self.response_text,
            "match_type": self.match_type,
            "is_case_sensitive": self.is_case_sensitive,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at.isoformat(),
            "response_type": self.response_type,
            "link_label": self.link_label,
            "link_url": self.link_url,
            "owner_user_id": self.owner_user_id,
            "scope": self.scope,
        }


class KnowledgeDocument(db.Model):
    __tablename__ = "knowledge_documents"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    telegram_group_id = db.Column(db.String(255), nullable=True, index=True)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    content_text = db.Column(db.Text, nullable=False)
    chunks = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "telegram_group_id": self.telegram_group_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "chunk_count": len(self.chunks) if self.chunks else 0,
            "created_at": self.created_at.isoformat(),
        }


class Poll(db.Model):
    __tablename__ = "polls"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question = db.Column(db.String(500), nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_option_index = db.Column(db.Integer, nullable=True)
    is_quiz = db.Column(db.Boolean, default=False)
    is_anonymous = db.Column(db.Boolean, default=True)
    allows_multiple = db.Column(db.Boolean, default=False)
    explanation = db.Column(db.String(200), nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    timezone = db.Column(db.String(50), nullable=True, default='UTC', server_default='UTC')
    is_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "question": self.question,
            "options": self.options,
            "correct_option_index": self.correct_option_index,
            "is_quiz": self.is_quiz,
            "is_anonymous": self.is_anonymous,
            "allows_multiple": self.allows_multiple,
            "explanation": self.explanation,
            "scheduled_at": (self.scheduled_at.isoformat() + "Z") if self.scheduled_at else None,
            "timezone": self.timezone or "UTC",
            "is_sent": self.is_sent,
            "created_at": self.created_at.isoformat() + "Z",
        }


class WebhookIntegration(db.Model):
    __tablename__ = "webhook_integrations"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    webhook_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    message_template = db.Column(db.Text, nullable=False, default="{payload}")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "name": self.name,
            "webhook_token": self.webhook_token,
            "description": self.description,
            "message_template": self.message_template,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


class InviteLink(db.Model):
    __tablename__ = "invite_links"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    telegram_group_id = db.Column(db.String(255), nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    telegram_invite_link = db.Column(db.String(255), nullable=True)
    uses_count = db.Column(db.Integer, default=0)
    max_uses = db.Column(db.Integer, nullable=True)
    expire_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Who created this link
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by_telegram_id = db.Column(db.String(255), nullable=True)
    created_by_username = db.Column(db.String(255), nullable=True)

    joins = db.relationship("InviteLinkJoin", backref="invite_link", lazy=True, cascade="all, delete-orphan")

    def to_dict(self, include_analytics=False):
        data = {
            "id": self.id,
            "group_id": self.group_id,
            "telegram_group_id": self.telegram_group_id,
            "name": self.name,
            "telegram_invite_link": self.telegram_invite_link,
            "uses_count": self.uses_count,
            "max_uses": self.max_uses,
            "expire_date": self.expire_date.isoformat() if self.expire_date else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "created_by_telegram_id": self.created_by_telegram_id,
            "created_by_username": self.created_by_username,
        }
        if include_analytics:
            from datetime import timedelta
            now = datetime.utcnow()
            joins_all = len(self.joins)
            joins_1d = sum(1 for j in self.joins if j.joined_at >= now - timedelta(days=1))
            joins_7d = sum(1 for j in self.joins if j.joined_at >= now - timedelta(days=7))
            joins_30d = sum(1 for j in self.joins if j.joined_at >= now - timedelta(days=30))
            data.update({
                "joins_total": joins_all,
                "joins_1d": joins_1d,
                "joins_7d": joins_7d,
                "joins_30d": joins_30d,
            })
        return data


class UserApiKey(db.Model):
    __tablename__ = "user_api_keys"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    telegram_group_id = db.Column(db.String(255), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    provider = db.Column(db.String(50), nullable=False)  # openai|openrouter|anthropic|gemini|custom
    scope = db.Column(db.String(20), nullable=False, default="group")  # group | workspace
    api_key_encrypted = db.Column(db.Text, nullable=False)
    base_url = db.Column(db.String(500), nullable=True)
    model_name = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        from .utils.encryption import mask_key, decrypt_value
        raw = decrypt_value(self.api_key_encrypted) if self.api_key_encrypted else ""
        updated = self.updated_at or self.created_at
        return {
            "id": self.id,
            "group_id": self.group_id,
            "telegram_group_id": self.telegram_group_id,
            "user_id": self.user_id,
            "provider": self.provider,
            "base_url": self.base_url,
            "model_name": self.model_name,
            "is_active": self.is_active,
            "api_key_masked": mask_key(raw),
            "created_at": self.created_at.isoformat(),
            "updated_at": updated.isoformat() if updated else None,
        }


class InviteLinkJoin(db.Model):
    __tablename__ = "invite_link_joins"

    id = db.Column(db.Integer, primary_key=True)
    invite_link_id = db.Column(db.Integer, db.ForeignKey("invite_links.id"), nullable=False)
    joined_user_id = db.Column(db.String(255), nullable=False)
    joined_username = db.Column(db.String(255), nullable=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "invite_link_id": self.invite_link_id,
            "joined_user_id": self.joined_user_id,
            "joined_username": self.joined_username,
            "joined_at": self.joined_at.isoformat(),
        }


class Referral(db.Model):
    """Tracks Telegizer platform referrals (one user inviting another to register)."""
    __tablename__ = "referrals"

    id = db.Column(db.Integer, primary_key=True)
    referrer_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    referred_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    referral_code = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # Track which milestones have been awarded to the referrer (JSON list of counts)
    rewards_given = db.Column(db.JSON, nullable=False, default=list)
    # Anti-abuse: status lifecycle and overlap flags
    # pending → approved (email verified) or → suspicious/rejected (abuse detected)
    status = db.Column(db.String(20), nullable=False, default="pending")
    ip_match = db.Column(db.Boolean, default=False, nullable=False)      # referrer/referred share IP
    device_match = db.Column(db.Boolean, default=False, nullable=False)  # referrer/referred share device

    __table_args__ = (
        db.UniqueConstraint("referrer_user_id", "referred_user_id", name="unique_referral_pair"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "referrer_user_id": self.referrer_user_id,
            "referred_user_id": self.referred_user_id,
            "referral_code": self.referral_code,
            "created_at": self.created_at.isoformat(),
            "rewards_given": self.rewards_given,
            "status": self.status,
            "ip_match": self.ip_match,
            "device_match": self.device_match,
        }


class ProcessedPayment(db.Model):
    """Tracks processed payment webhook IDs to prevent duplicate subscription upgrades."""
    __tablename__ = "processed_payments"

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class PaymentHistory(db.Model):
    """Full billing history record created on every successful payment webhook."""
    __tablename__ = "payment_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    provider = db.Column(db.String(50), nullable=False)           # nowpayments | lemonsqueezy
    payment_id = db.Column(db.String(255), nullable=True)
    plan = db.Column(db.String(50), nullable=False)               # pro | enterprise
    billing_period = db.Column(db.String(10), nullable=True, default="monthly")  # monthly | annual
    amount_usd = db.Column(db.Integer, nullable=True)             # cents
    currency = db.Column(db.String(10), nullable=True)            # USD / USDT / BTC / …
    status = db.Column(db.String(30), nullable=False, default="confirmed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    metadata_ = db.Column("metadata", db.JSON, nullable=True)

    def to_dict(self):
        pid = self.payment_id or ""
        masked_id = (pid[:6] + "…" + pid[-4:]) if len(pid) > 12 else pid
        return {
            "id": self.id,
            "provider": self.provider,
            "payment_id_masked": masked_id,
            "plan": self.plan,
            "billing_period": self.billing_period or "monthly",
            "amount_usd": self.amount_usd,
            "currency": self.currency,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
        }


class SuspiciousActivity(db.Model):
    """Records suspicious signup and referral events for admin review.
    All identifiers are SHA-256 hashes — no raw IPs or fingerprints stored."""
    __tablename__ = "suspicious_activities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    event_type = db.Column(db.String(50), nullable=False)   # ip_limit|device_limit|referral_ip|referral_device
    ip_hash = db.Column(db.String(64), nullable=True)
    device_hash = db.Column(db.String(64), nullable=True)
    reason = db.Column(db.String(255), nullable=False)
    event_metadata = db.Column(db.JSON, nullable=True)
    reviewed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            # Partial hash shown to admin — enough to correlate, not enough to reverse
            "ip_hash_prefix": self.ip_hash[:12] if self.ip_hash else None,
            "device_hash_prefix": self.device_hash[:12] if self.device_hash else None,
            "reason": self.reason,
            "event_metadata": self.event_metadata,
            "reviewed": self.reviewed,
            "created_at": self.created_at.isoformat(),
        }


class UserNotification(db.Model):
    """In-app notifications delivered to the dashboard notification center."""
    __tablename__ = "user_notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)   # payment_confirmed|plan_expiring|bot_error|referral|etc
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    metadata_ = db.Column("metadata", db.JSON, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "read": self.read,
            "created_at": self.created_at.isoformat(),
        }


class ReportedMessage(db.Model):
    __tablename__ = "reported_messages"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    reporter_user_id = db.Column(db.BigInteger, nullable=False)
    reporter_username = db.Column(db.String(100), nullable=True)
    reported_message_id = db.Column(db.BigInteger, nullable=True)
    reported_user_id = db.Column(db.BigInteger, nullable=True)
    reported_username = db.Column(db.String(100), nullable=True)
    reason = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default="open")  # open|resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "reporter_user_id": self.reporter_user_id,
            "reporter_username": self.reporter_username,
            "reported_message_id": self.reported_message_id,
            "reported_user_id": self.reported_user_id,
            "reported_username": self.reported_username,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


# ─── Telegram Account Connect Codes ──────────────────────────────────────────


class TelegramConnectCode(db.Model):
    """One-time codes that link a website user's account to their Telegram identity.
    Generated on the website, consumed by the bot via /start connect_<code>."""
    __tablename__ = "telegram_connect_codes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    telegram_user_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @staticmethod
    def generate():
        import secrets as _s
        return _s.token_urlsafe(24)

    @property
    def is_valid(self):
        return self.used_at is None and datetime.utcnow() < self.expires_at


# ─── Official Bot Ecosystem Models ────────────────────────────────────────────


class TelegramBotStarted(db.Model):
    """Tracks Telegram users who have started @telegizer_bot at least once.
    Used to verify whether a private DM can be sent to an admin."""
    __tablename__ = "telegram_bot_started"

    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    first_started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_active_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @staticmethod
    def record(user_id: str):
        """Insert or update the started record for a Telegram user ID."""
        existing = TelegramBotStarted.query.filter_by(telegram_user_id=str(user_id)).first()
        if existing:
            existing.last_active_at = datetime.utcnow()
        else:
            db.session.add(TelegramBotStarted(telegram_user_id=str(user_id)))

    @staticmethod
    def has_started(user_id: str) -> bool:
        return TelegramBotStarted.query.filter_by(telegram_user_id=str(user_id)).first() is not None


class TelegramGroup(db.Model):
    """Groups linked to Telegizer via the official shared bot."""
    __tablename__ = "telegram_groups"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    username = db.Column(db.String(255), nullable=True)
    invite_link = db.Column(db.String(500), nullable=True)
    # Website user who linked this group (NULL = added but not yet linked)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    # 'official' = Telegizer shared bot, 'custom' = user's own bot token
    linked_via_bot_type = db.Column(db.String(20), default="official", nullable=False)
    # FK to custom_bots if linked_via_bot_type='custom'
    linked_bot_id = db.Column(db.Integer, db.ForeignKey("custom_bots.id"), nullable=True)
    # active | pending | removed | disabled
    bot_status = db.Column(db.String(20), default="pending", nullable=False)
    # {delete_messages, ban_users, pin_messages, manage_topics}
    bot_permissions = db.Column(db.JSON, nullable=True)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    timezone = db.Column(db.String(50), default="UTC", nullable=True)
    linked_at = db.Column(db.DateTime, nullable=True)
    last_activity = db.Column(db.DateTime, nullable=True)
    is_disabled = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Cached counts — kept up to date by the bot on member join/leave events
    member_count = db.Column(db.Integer, default=0, nullable=False)
    description = db.Column(db.Text, nullable=True)

    link_codes = db.relationship("TelegramGroupLinkCode", backref="telegram_group", lazy=True, cascade="all, delete-orphan")
    custom_commands = db.relationship("CustomCommand", backref="telegram_group", lazy=True, cascade="all, delete-orphan")
    bot_events = db.relationship("BotEvent", backref="telegram_group", lazy=True, cascade="all, delete-orphan")
    official_warnings = db.relationship("OfficialWarning", backref="telegram_group", lazy=True, cascade="all, delete-orphan")
    official_members = db.relationship("OfficialMember", backref="telegram_group", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "title": self.title,
            "username": self.username,
            "invite_link": self.invite_link,
            "owner_user_id": self.owner_user_id,
            "linked_via_bot_type": self.linked_via_bot_type,
            "linked_bot_id": self.linked_bot_id,
            "bot_status": self.bot_status,
            "bot_permissions": self.bot_permissions,
            "linked_at": self.linked_at.isoformat() if self.linked_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "is_disabled": self.is_disabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "member_count": self.member_count,
            "description": self.description,
        }


class OfficialMember(db.Model):
    """Tracks members of official bot groups for XP/levels."""
    __tablename__ = "official_members"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(
        db.String(255),
        db.ForeignKey("telegram_groups.telegram_group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    telegram_user_id = db.Column(db.String(255), nullable=False, index=True)
    username = db.Column(db.String(255), nullable=True)
    first_name = db.Column(db.String(255), nullable=True)
    xp = db.Column(db.Integer, default=0, nullable=False)
    level = db.Column(db.Integer, default=1, nullable=False)
    message_count = db.Column(db.Integer, default=0, nullable=False)
    last_message_at = db.Column(db.DateTime, nullable=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # Phase 3 additions — mirrors Member model fields
    last_xp_at = db.Column(db.DateTime, nullable=True)
    role = db.Column(db.String(100), default="member", nullable=False)
    warnings = db.Column(db.Integer, default=0, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_muted = db.Column(db.Boolean, default=False, nullable=False)
    mute_until = db.Column(db.DateTime, nullable=True)
    wallet_address = db.Column(db.String(500), nullable=True)
    wallet_submitted_at = db.Column(db.DateTime, nullable=True)
    # Phase 3 item 21 — cached admin status to avoid per-message Telegram API calls
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_admin_cached_at = db.Column(db.DateTime, nullable=True)
    # CRM fields
    crm_tags = db.Column(db.JSON, nullable=True)          # list of tag strings
    crm_notes = db.Column(db.Text, nullable=True)         # admin freetext notes
    engagement_score = db.Column(db.Integer, nullable=True)  # 0–100, computed

    __table_args__ = (
        db.UniqueConstraint("telegram_group_id", "telegram_user_id", name="uq_official_member"),
    )

    def compute_engagement_score(self):
        """Compute 0–100 engagement score from existing member data."""
        from datetime import datetime, timedelta
        score = 0

        # XP / level component (0–35 pts)
        xp = self.xp or 0
        # Normalize: level 10+ = full score
        level = self.level or 1
        score += min(35, int((level / 10) * 35))

        # Message frequency (0–25 pts)
        msgs = self.message_count or 0
        days_since_join = max(1, (datetime.utcnow() - (self.joined_at or datetime.utcnow())).days)
        daily_rate = msgs / days_since_join
        score += min(25, int(daily_rate * 5))  # 5 msgs/day = full score

        # Recency (0–20 pts) — last message within past 7 days
        if self.last_message_at:
            days_ago = (datetime.utcnow() - self.last_message_at).days
            if days_ago <= 1:   score += 20
            elif days_ago <= 3: score += 15
            elif days_ago <= 7: score += 10
            elif days_ago <= 14: score += 5

        # Verification bonus (0–10 pts)
        if self.is_verified:
            score += 10

        # Warning penalty (−10 per warning, min 0)
        score -= min(score, (self.warnings or 0) * 10)

        # Mute penalty
        if self.is_muted:
            score = max(0, score - 15)

        return max(0, min(100, score))

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "telegram_user_id": self.telegram_user_id,
            "username": self.username,
            "first_name": self.first_name,
            "xp": self.xp,
            "level": self.level,
            "message_count": self.message_count,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "joined_at": self.joined_at.isoformat(),
            "last_xp_at": self.last_xp_at.isoformat() if self.last_xp_at else None,
            "role": self.role,
            "warnings": self.warnings,
            "is_verified": self.is_verified,
            "is_muted": self.is_muted,
            "mute_until": self.mute_until.isoformat() if self.mute_until else None,
            "wallet_address": self.wallet_address,
            "wallet_submitted_at": self.wallet_submitted_at.isoformat() if self.wallet_submitted_at else None,
            "is_admin": self.is_admin,
            "is_admin_cached_at": self.is_admin_cached_at.isoformat() if self.is_admin_cached_at else None,
            "crm_tags": self.crm_tags or [],
            "crm_notes": self.crm_notes or "",
            "engagement_score": self.engagement_score,
        }


class PendingVerification(db.Model):
    """In-flight member verifications — persisted so restarts don't lose state."""
    __tablename__ = "pending_verifications"

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.BigInteger, nullable=False)
    user_id = db.Column(db.BigInteger, nullable=False)
    method = db.Column(db.String(20), nullable=False)
    msg_id = db.Column(db.Integer, nullable=True)
    answer = db.Column(db.String(500), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    kick_on_fail = db.Column(db.Boolean, default=True)
    max_attempts = db.Column(db.Integer, default=3)
    attempts = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("chat_id", "user_id", name="uq_pending_verification"),
    )


class OfficialWarning(db.Model):
    """Per-user warnings issued by admins in official bot groups."""
    __tablename__ = "official_warnings"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(
        db.String(255),
        db.ForeignKey("telegram_groups.telegram_group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_user_id = db.Column(db.String(255), nullable=False, index=True)
    target_username = db.Column(db.String(255), nullable=True)
    moderator_user_id = db.Column(db.String(255), nullable=False)
    moderator_username = db.Column(db.String(255), nullable=True)
    reason = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "target_user_id": self.target_user_id,
            "target_username": self.target_username,
            "moderator_user_id": self.moderator_user_id,
            "moderator_username": self.moderator_username,
            "reason": self.reason,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
        }


class OfficialScheduledMessage(db.Model):
    """Scheduled messages for official-bot groups (mirrors ScheduledMessage for custom bots)."""
    __tablename__ = "official_scheduled_messages"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(
        db.String(255),
        db.ForeignKey("telegram_groups.telegram_group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(255), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    media_url = db.Column(db.String(500), nullable=True)
    buttons = db.Column(db.JSON, nullable=True)
    send_at = db.Column(db.DateTime, nullable=False)
    repeat_interval = db.Column(db.Integer, nullable=True)
    stop_date = db.Column(db.DateTime, nullable=True)
    pin_message = db.Column(db.Boolean, default=False)
    auto_delete_after = db.Column(db.Integer, nullable=True)
    link_preview_enabled = db.Column(db.Boolean, default=True)
    topic_id = db.Column(db.BigInteger, nullable=True)
    timezone = db.Column(db.String(50), nullable=False, default="UTC", server_default="UTC")
    is_sent = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "title": self.title,
            "message_text": self.message_text,
            "media_url": self.media_url,
            "buttons": self.buttons,
            "send_at": self.send_at.isoformat() + "Z",
            "repeat_interval": self.repeat_interval,
            "stop_date": (self.stop_date.isoformat() + "Z") if self.stop_date else None,
            "pin_message": self.pin_message,
            "auto_delete_after": self.auto_delete_after,
            "link_preview_enabled": self.link_preview_enabled,
            "topic_id": self.topic_id,
            "timezone": self.timezone or "UTC",
            "is_sent": self.is_sent,
            "created_at": self.created_at.isoformat() + "Z",
        }


class OfficialPoll(db.Model):
    """Scheduled polls for official-bot groups (mirrors Poll for custom bots)."""
    __tablename__ = "official_polls"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(
        db.String(255),
        db.ForeignKey("telegram_groups.telegram_group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question = db.Column(db.String(500), nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_option_index = db.Column(db.Integer, nullable=True)
    is_quiz = db.Column(db.Boolean, default=False)
    is_anonymous = db.Column(db.Boolean, default=True)
    allows_multiple = db.Column(db.Boolean, default=False)
    explanation = db.Column(db.String(200), nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    timezone = db.Column(db.String(50), nullable=True, default="UTC", server_default="UTC")
    is_sent = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "question": self.question,
            "options": self.options,
            "correct_option_index": self.correct_option_index,
            "is_quiz": self.is_quiz,
            "is_anonymous": self.is_anonymous,
            "allows_multiple": self.allows_multiple,
            "explanation": self.explanation,
            "scheduled_at": self.scheduled_at.isoformat() + "Z" if self.scheduled_at else None,
            "timezone": self.timezone or "UTC",
            "is_sent": self.is_sent,
            "created_at": self.created_at.isoformat() + "Z",
        }


class TelegramGroupLinkCode(db.Model):
    """One-time secure codes used to link a Telegram group to a dashboard account."""
    __tablename__ = "telegram_group_link_codes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), unique=True, nullable=False, index=True)
    telegram_group_id = db.Column(db.String(255), db.ForeignKey("telegram_groups.telegram_group_id"), nullable=False)
    telegram_group_title = db.Column(db.String(255), nullable=True)
    created_by_telegram_user_id = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @staticmethod
    def generate_code():
        alphabet = string.ascii_uppercase + string.digits
        return "TLG-" + "".join(secrets.choice(alphabet) for _ in range(8))

    @property
    def is_valid(self):
        return self.used_at is None and datetime.utcnow() < self.expires_at

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "telegram_group_id": self.telegram_group_id,
            "telegram_group_title": self.telegram_group_title,
            "expires_at": self.expires_at.isoformat(),
            "used_at": self.used_at.isoformat() if self.used_at else None,
            "created_at": self.created_at.isoformat(),
            "is_valid": self.is_valid,
        }


class CustomBot(db.Model):
    """Bring-your-own-bot tokens for premium/agency users."""
    __tablename__ = "custom_bots"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    bot_name = db.Column(db.String(255), nullable=True)
    bot_username = db.Column(db.String(255), nullable=False)
    bot_token_encrypted = db.Column(db.Text, nullable=False)
    # active | inactive | error
    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    linked_groups = db.relationship("TelegramGroup", backref="custom_bot", lazy=True)

    def get_token(self) -> str:
        from .utils.encryption import decrypt_value
        return decrypt_value(self.bot_token_encrypted)

    def set_token(self, plain_token: str):
        from .utils.encryption import encrypt_value
        self.bot_token_encrypted = encrypt_value(plain_token) or plain_token

    @property
    def health_status(self) -> str:
        """Derive health from status field. active/inactive/error map directly."""
        if self.status in ("active", "inactive", "error"):
            return self.status
        return "unknown"

    def to_dict(self, include_token=False):
        data = {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "bot_name": self.bot_name,
            "bot_username": self.bot_username,
            "status": self.status,
            "health_status": self.health_status,
            "linked_groups_count": len(self.linked_groups),
            "last_active": self.updated_at.isoformat() if self.updated_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_token:
            data["bot_token"] = self.get_token()
        return data


class CustomCommand(db.Model):
    """Per-group slash commands managed via dashboard."""
    __tablename__ = "custom_commands"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(db.String(255), db.ForeignKey("telegram_groups.telegram_group_id"), nullable=False, index=True)
    command = db.Column(db.String(64), nullable=False)  # e.g. "rules", "support"
    response_type = db.Column(db.String(20), default="text", nullable=False)  # text|markdown
    response_text = db.Column(db.Text, nullable=False)
    action_type = db.Column(db.String(50), nullable=True)  # delete_trigger|reply_only
    buttons = db.Column(db.JSON, nullable=True)  # [[{text, url}]]
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("telegram_group_id", "command", name="unique_group_command"),)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "command": self.command,
            "response_type": self.response_type,
            "response_text": self.response_text,
            "action_type": self.action_type,
            "buttons": self.buttons,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BotGroupCommand(db.Model):
    """Per-group slash commands for custom (user-supplied) bots."""
    __tablename__ = "bot_group_commands"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    command = db.Column(db.String(64), nullable=False)
    response_type = db.Column(db.String(20), default="text", nullable=False)
    response_text = db.Column(db.Text, nullable=False)
    buttons = db.Column(db.JSON, nullable=True)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("group_id", "command", name="uq_bot_group_command"),)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "command": self.command,
            "response_type": self.response_type,
            "response_text": self.response_text,
            "buttons": self.buttons,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BotEvent(db.Model):
    """Audit log for all official bot activity."""
    __tablename__ = "bot_events"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(db.String(255), db.ForeignKey("telegram_groups.telegram_group_id"), nullable=True, index=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    message = db.Column(db.Text, nullable=True)
    metadata_ = db.Column("metadata", db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "event_type": self.event_type,
            "message": self.message,
            "metadata": self.metadata_,
            "created_at": self.created_at.isoformat(),
        }


# ── Official-group feature models (Phase 2 — full parity with custom bots) ──────

class OfficialRaid(db.Model):
    """Twitter/X raids for official-bot groups. Mirrors the custom-bot Raid model."""
    __tablename__ = "official_raids"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(
        db.String(255),
        db.ForeignKey("telegram_groups.telegram_group_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tweet_url = db.Column(db.String(500), nullable=False)
    goals = db.Column(db.JSON, default=dict, nullable=False)
    duration_hours = db.Column(db.Integer, default=24, nullable=False)
    xp_reward = db.Column(db.Integer, default=100, nullable=False)
    pin_message = db.Column(db.Boolean, default=True, nullable=False)
    reminders_enabled = db.Column(db.Boolean, default=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    participants = db.Column(db.JSON, default=list, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "tweet_url": self.tweet_url,
            "goals": self.goals or {},
            "duration_hours": self.duration_hours,
            "xp_reward": self.xp_reward,
            "pin_message": self.pin_message,
            "reminders_enabled": self.reminders_enabled,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() + "Z",
            "ends_at": self.ends_at.isoformat() + "Z",
            "participants": self.participants or [],
        }


class OfficialWebhookIntegration(db.Model):
    """Incoming webhook integrations for official-bot groups."""
    __tablename__ = "official_webhook_integrations"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(
        db.String(255),
        db.ForeignKey("telegram_groups.telegram_group_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    webhook_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    message_template = db.Column(db.Text, default="📡 *{name}*\n\n{payload}", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "name": self.name,
            "webhook_token": self.webhook_token,
            "description": self.description,
            "message_template": self.message_template,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() + "Z",
        }


class WorkspaceReminder(db.Model):
    """Follow-up reminders created manually or auto-detected by the bot."""
    __tablename__ = "workspace_reminders"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    telegram_group_id = db.Column(db.String(255), nullable=True)  # source group; None for manual
    original_message = db.Column(db.Text, nullable=True)          # text that triggered detection
    reminder_text = db.Column(db.String(500), nullable=False)
    remind_at = db.Column(db.DateTime, nullable=False, index=True)
    is_delivered = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "telegram_group_id": self.telegram_group_id,
            "original_message": self.original_message,
            "reminder_text": self.reminder_text,
            "remind_at": self.remind_at.isoformat(),
            "is_delivered": self.is_delivered,
            "created_at": self.created_at.isoformat(),
        }


class MessageBuffer(db.Model):
    """Stores recent group messages for AI Daily Digest summarization.
    Auto-expired after 48 hours via scheduler cleanup."""
    __tablename__ = "message_buffers"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(db.String(255), nullable=False, index=True)
    sender_user_id = db.Column(db.String(255), nullable=False)
    sender_name = db.Column(db.String(255), nullable=True)
    message_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "sender_name": self.sender_name,
            "message_text": self.message_text,
            "created_at": self.created_at.isoformat(),
        }


class AutomationWorkflow(db.Model):
    """User-defined trigger → condition → action automation workflows."""
    __tablename__ = "automation_workflows"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    source_group_id = db.Column(db.String(255), nullable=True, index=True)
    # JSON: {"type": "message_received"|"member_joined"|"member_banned"|"scheduled", "params":{}}
    trigger = db.Column(db.JSON, nullable=False)
    # JSON: [{"type": "message_contains", "params": {"keyword": "..."}}]
    conditions = db.Column(db.JSON, nullable=False, default=list)
    # JSON: [{"type": "send_dm"|"notify_admin_dm"|"forward_message"|..., "params":{}}]
    actions = db.Column(db.JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    run_count = db.Column(db.Integer, default=0, nullable=False)
    last_run_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    executions = db.relationship("AutomationExecution", backref="workflow", lazy="dynamic",
                                 cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "name": self.name,
            "source_group_id": self.source_group_id,
            "trigger": self.trigger,
            "conditions": self.conditions,
            "actions": self.actions,
            "is_active": self.is_active,
            "run_count": self.run_count,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "created_at": self.created_at.isoformat(),
        }


class AutomationExecution(db.Model):
    """Per-run execution log for automation workflows."""
    __tablename__ = "automation_executions"

    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey("automation_workflows.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    trigger_type = db.Column(db.String(50), nullable=False)
    source_group_id = db.Column(db.String(255), nullable=True)
    trigger_data = db.Column(db.JSON, nullable=True)   # snapshot of the event that fired
    # success / failed / skipped (conditions not met)
    status = db.Column(db.String(20), default="success", nullable=False)
    error_msg = db.Column(db.String(500), nullable=True)
    executed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "trigger_type": self.trigger_type,
            "source_group_id": self.source_group_id,
            "trigger_data": self.trigger_data,
            "status": self.status,
            "error_msg": self.error_msg,
            "executed_at": self.executed_at.isoformat(),
        }


class ForwardRule(db.Model):
    """Message forwarding rules — cross-post from one group/channel to another."""
    __tablename__ = "forward_rules"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    rule_name = db.Column(db.String(200), nullable=False)
    source_group_id = db.Column(db.String(255), nullable=False, index=True)
    destination_id = db.Column(db.String(255), nullable=False)  # chat_id or @username
    keyword_filter = db.Column(db.String(1000), nullable=True)  # comma-separated; None = all
    match_type = db.Column(db.String(20), default="contains")   # contains / starts_with
    prefix_text = db.Column(db.String(500), nullable=True)
    suffix_text = db.Column(db.String(500), nullable=True)
    require_approval = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    forward_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    logs = db.relationship("ForwardLog", backref="rule", lazy="dynamic",
                           cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "rule_name": self.rule_name,
            "source_group_id": self.source_group_id,
            "destination_id": self.destination_id,
            "keyword_filter": self.keyword_filter,
            "match_type": self.match_type,
            "prefix_text": self.prefix_text,
            "suffix_text": self.suffix_text,
            "require_approval": self.require_approval,
            "is_active": self.is_active,
            "forward_count": self.forward_count,
            "created_at": self.created_at.isoformat(),
        }


class ForwardLog(db.Model):
    """Per-message forwarding audit log."""
    __tablename__ = "forward_logs"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("forward_rules.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    source_chat_id = db.Column(db.String(255), nullable=False)
    source_message_id = db.Column(db.Integer, nullable=True)
    source_text = db.Column(db.String(500), nullable=True)
    destination_id = db.Column(db.String(255), nullable=False)
    # forwarded / pending_approval / approved / rejected / failed
    status = db.Column(db.String(30), default="forwarded", nullable=False, index=True)
    error_msg = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "source_chat_id": self.source_chat_id,
            "source_message_id": self.source_message_id,
            "source_text": self.source_text,
            "destination_id": self.destination_id,
            "status": self.status,
            "error_msg": self.error_msg,
            "created_at": self.created_at.isoformat(),
        }


class OfficialReportedMessage(db.Model):
    """User reports (/report command) for official-bot groups."""
    __tablename__ = "official_reported_messages"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(
        db.String(255),
        db.ForeignKey("telegram_groups.telegram_group_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    reporter_user_id = db.Column(db.String(255), nullable=False)
    reporter_username = db.Column(db.String(100), nullable=True)
    reported_user_id = db.Column(db.String(255), nullable=True)
    reported_username = db.Column(db.String(100), nullable=True)
    reason = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default="open", nullable=False)  # open | resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "reporter_user_id": self.reporter_user_id,
            "reporter_username": self.reporter_username,
            "reported_user_id": self.reported_user_id,
            "reported_username": self.reported_username,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


# ── Channels ──────────────────────────────────────────────────────────────────

class Channel(db.Model):
    """A Telegram channel managed by a user."""
    __tablename__ = "channels"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    telegram_channel_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    username = db.Column(db.String(128), nullable=True)   # @handle (without @)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)
    member_count = db.Column(db.Integer, default=0)
    # Rolling 30-day averages (updated on refresh)
    avg_views = db.Column(db.Float, default=0.0)
    avg_reactions = db.Column(db.Float, default=0.0)
    avg_forwards = db.Column(db.Float, default=0.0)
    engagement_rate = db.Column(db.Float, default=0.0)   # reactions/views %
    # pending | active | error | no_admin
    bot_status = db.Column(db.String(32), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_refreshed_at = db.Column(db.DateTime, nullable=True)
    # TCS — Telegizer Community Score
    tcs_score = db.Column(db.Integer, nullable=True)         # 0–100
    tcs_grade = db.Column(db.String(2), nullable=True)       # A/B/C/D/F
    tcs_breakdown = db.Column(db.JSON, nullable=True)        # per-signal detail
    tcs_computed_at = db.Column(db.DateTime, nullable=True)

    posts = db.relationship("ChannelPost", backref="channel", lazy="dynamic",
                            cascade="all, delete-orphan")
    daily_stats = db.relationship("ChannelDailyStat", backref="channel", lazy="dynamic",
                                  cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_channel_id": self.telegram_channel_id,
            "username": self.username,
            "title": self.title,
            "description": self.description,
            "member_count": self.member_count,
            "avg_views": round(self.avg_views or 0, 1),
            "avg_reactions": round(self.avg_reactions or 0, 1),
            "avg_forwards": round(self.avg_forwards or 0, 1),
            "engagement_rate": round(self.engagement_rate or 0, 2),
            "bot_status": self.bot_status,
            "post_count": self.posts.count(),
            "created_at": self.created_at.isoformat(),
            "tracking_started_at": self.created_at.isoformat(),
            "last_refreshed_at": self.last_refreshed_at.isoformat() if self.last_refreshed_at else None,
            "tcs_score": self.tcs_score,
            "tcs_grade": self.tcs_grade,
            "tcs_breakdown": self.tcs_breakdown,
            "tcs_computed_at": self.tcs_computed_at.isoformat() if self.tcs_computed_at else None,
        }


class ChannelPost(db.Model):
    """Analytics snapshot for a single channel post."""
    __tablename__ = "channel_posts"

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    message_id = db.Column(db.Integer, nullable=False)
    text_preview = db.Column(db.String(300), nullable=True)
    views = db.Column(db.Integer, default=0)
    reactions = db.Column(db.Integer, default=0)
    forwards = db.Column(db.Integer, default=0)
    has_media = db.Column(db.Boolean, default=False)
    media_type = db.Column(db.String(32), nullable=True)  # photo/video/document/poll/sticker
    posted_at = db.Column(db.DateTime, nullable=False, index=True)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("channel_id", "message_id", name="uq_channel_message"),)

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "text_preview": self.text_preview,
            "views": self.views,
            "reactions": self.reactions,
            "forwards": self.forwards,
            "has_media": self.has_media,
            "media_type": self.media_type,
            "engagement_rate": round((self.reactions / self.views * 100) if self.views else 0, 2),
            "posted_at": self.posted_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }


class ChannelDailyStat(db.Model):
    """Daily snapshot of channel-level metrics."""
    __tablename__ = "channel_daily_stats"

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    member_count = db.Column(db.Integer, default=0)
    posts_count = db.Column(db.Integer, default=0)
    total_views = db.Column(db.Integer, default=0)
    total_reactions = db.Column(db.Integer, default=0)
    total_forwards = db.Column(db.Integer, default=0)
    avg_views_per_post = db.Column(db.Float, default=0.0)

    __table_args__ = (db.UniqueConstraint("channel_id", "date", name="uq_channel_date"),)

    def to_dict(self):
        return {
            "date": self.date.isoformat(),
            "member_count": self.member_count,
            "posts_count": self.posts_count,
            "total_views": self.total_views,
            "total_reactions": self.total_reactions,
            "total_forwards": self.total_forwards,
            "avg_views_per_post": round(self.avg_views_per_post, 1),
        }


# ── Community Directory ───────────────────────────────────────────────────────

DIRECTORY_CATEGORIES = [
    "Technology & Dev", "Crypto & Web3", "News & Politics",
    "Business & Finance", "Education & Learning", "Entertainment",
    "Gaming", "Health & Wellness", "Sports", "Art & Design", "Other",
]

DIRECTORY_LANGUAGES = [
    "English", "Arabic", "Spanish", "Portuguese", "Russian",
    "Hindi", "Indonesian", "Turkish", "French", "German", "Other",
]


class DirectoryListing(db.Model):
    """Public community directory — opt-in listing for channels and groups."""
    __tablename__ = "directory_listings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    # Exactly one of these is set
    channel_id = db.Column(db.Integer, db.ForeignKey("channels.id", ondelete="CASCADE"),
                           nullable=True, unique=True)
    telegram_group_id = db.Column(
        db.String(255),
        db.ForeignKey("telegram_groups.telegram_group_id", ondelete="CASCADE"),
        nullable=True, unique=True,
    )

    listing_type = db.Column(db.String(16), nullable=False)   # channel | group
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(64), nullable=False, index=True)
    language = db.Column(db.String(32), default="English")
    country = db.Column(db.String(64), default="Global", index=True)
    telegram_link = db.Column(db.String(256), nullable=False)  # t.me/... join link

    # Denormalized stats (refreshed periodically)
    member_count = db.Column(db.Integer, default=0)
    tcs_score = db.Column(db.Integer, nullable=True)
    tcs_grade = db.Column(db.String(2), nullable=True)

    # Status
    is_public = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)

    # Partnership / marketplace pricing
    accepts_partnerships = db.Column(db.Boolean, default=False, nullable=False, index=True)
    price_per_post  = db.Column(db.Float, nullable=True)   # USD
    price_per_week  = db.Column(db.Float, nullable=True)   # USD
    pricing_notes   = db.Column(db.String(512), nullable=True)

    # Engagement metrics
    view_count = db.Column(db.Integer, default=0)
    contact_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, include_contact=False):
        d = {
            "id": self.id,
            "listing_type": self.listing_type,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "language": self.language,
            "country": self.country,
            "telegram_link": self.telegram_link,
            "member_count": self.member_count,
            "tcs_score": self.tcs_score,
            "tcs_grade": self.tcs_grade,
            "is_featured": self.is_featured,
            "is_verified": self.is_verified,
            "view_count": self.view_count,
            "contact_count": self.contact_count,
            "accepts_partnerships": self.accepts_partnerships,
            "price_per_post": self.price_per_post,
            "price_per_week": self.price_per_week,
            "pricing_notes": self.pricing_notes,
            "created_at": self.created_at.isoformat(),
        }
        if include_contact:
            d["user_id"] = self.user_id
            d["channel_id"] = self.channel_id
            d["telegram_group_id"] = self.telegram_group_id
        return d


# ── B2B Partnership Marketplace ───────────────────────────────────────────────

class PartnershipDeal(db.Model):
    """A sponsored-post / partnership deal between a brand and a community owner."""
    __tablename__ = "partnership_deals"

    id = db.Column(db.Integer, primary_key=True)
    buyer_user_id  = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    seller_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("directory_listings.id", ondelete="SET NULL"),
                           nullable=True, index=True)

    title        = db.Column(db.String(256), nullable=False)
    requirements = db.Column(db.Text, nullable=True)   # buyer's brief
    deliverable  = db.Column(db.Text, nullable=True)   # seller fills on delivery

    budget_usd = db.Column(db.Float, nullable=False)   # agreed price in USD
    platform_fee_pct = db.Column(db.Float, default=10.0)  # 10% platform fee

    # pending | accepted | declined | in_progress | delivered | completed | disputed | cancelled
    status = db.Column(db.String(32), default="pending", nullable=False, index=True)
    # unpaid | awaiting | paid | released | refunded
    payment_status = db.Column(db.String(32), default="unpaid", nullable=False)
    payment_id = db.Column(db.String(128), nullable=True)   # NOWPayments payment id
    payment_address = db.Column(db.String(256), nullable=True)
    payment_currency = db.Column(db.String(16), default="USDT")

    created_at   = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    accepted_at  = db.Column(db.DateTime, nullable=True)
    paid_at      = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    deadline_at  = db.Column(db.DateTime, nullable=True)

    messages = db.relationship("DealMessage", backref="deal", lazy="dynamic",
                               cascade="all, delete-orphan", order_by="DealMessage.created_at")

    def net_seller_amount(self):
        return round(self.budget_usd * (1 - self.platform_fee_pct / 100), 2)

    def to_dict(self):
        return {
            "id": self.id,
            "buyer_user_id": self.buyer_user_id,
            "seller_user_id": self.seller_user_id,
            "listing_id": self.listing_id,
            "title": self.title,
            "requirements": self.requirements,
            "deliverable": self.deliverable,
            "budget_usd": self.budget_usd,
            "platform_fee_pct": self.platform_fee_pct,
            "net_seller_amount": self.net_seller_amount(),
            "status": self.status,
            "payment_status": self.payment_status,
            "payment_currency": self.payment_currency,
            "created_at": self.created_at.isoformat(),
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
        }


class DealMessage(db.Model):
    """Chat message within a deal thread."""
    __tablename__ = "deal_messages"

    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey("partnership_deals.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    sender_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                               nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "deal_id": self.deal_id,
            "sender_user_id": self.sender_user_id,
            "body": self.body,
            "created_at": self.created_at.isoformat(),
        }


class Note(db.Model):
    """User-created or AI-extracted notes from group messages."""
    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    group_id = db.Column(db.String(255), nullable=True, index=True)   # telegram_group_id; null = personal
    group_title = db.Column(db.String(200), nullable=True)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(20), default="manual", nullable=False)  # manual | ai | bot
    tags = db.Column(db.JSON, default=list, nullable=False)              # ['decision','task','link','question']
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "group_title": self.group_title,
            "content": self.content,
            "source": self.source,
            "tags": self.tags or [],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DigestLog(db.Model):
    """Record of each AI digest that was generated and sent."""
    __tablename__ = "digest_logs"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.String(255), nullable=False, index=True)  # telegram_group_id
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content_preview = db.Column(db.String(300), nullable=True)
    provider = db.Column(db.String(50), nullable=True)
    tokens_used = db.Column(db.Integer, nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "user_id": self.user_id,
            "content_preview": self.content_preview,
            "provider": self.provider,
            "tokens_used": self.tokens_used,
            "sent_at": self.sent_at.isoformat(),
        }
