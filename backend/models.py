from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
import secrets
import string

db = SQLAlchemy()

# pgvector support — optional, degrades gracefully when extension not installed
try:
    from pgvector.sqlalchemy import Vector as _PgVector
    _PGVECTOR_AVAILABLE = True
except ImportError:
    _PgVector = None
    _PGVECTOR_AVAILABLE = False

# Referral milestones: (required_count, reward_days)
REFERRAL_MILESTONES = [(3, 7), (10, 30)]


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    full_name = db.Column(db.String(255), nullable=True)
    auth_provider = db.Column(db.String(20), nullable=False, default='email')  # 'email' | 'telegram' | 'both'
    subscription_tier = db.Column(db.String(50), default="free", nullable=False)
    subscription_expires = db.Column(db.DateTime, nullable=True)
    # Extended subscription lifecycle fields (1-A-01)
    subscription_expires_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    subscription_grace_until = db.Column(db.DateTime(timezone=True), nullable=True)
    subscription_interval    = db.Column(db.String(20), nullable=True)  # "monthly" | "annual"
    # Legacy Stripe columns — kept to avoid dropping data; Stripe is not active.
    stripe_customer_id = db.Column(db.String(255), nullable=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.Text, nullable=True)
    # Platform-admin role (RBAC). NULL = not an admin via this column. Bootstrap:
    # emails in Config.ADMIN_EMAILS are treated as super_admin even with NULL here,
    # so a sole admin can never be locked out. See backend/admin_rbac.py.
    # Values: super_admin | admin | support | finance | moderator | analyst
    admin_role = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # Unique referral code assigned at registration
    referral_code = db.Column(db.String(16), unique=True, nullable=True, index=True)
    # Email verification
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verification_token = db.Column(db.String(64), nullable=True, index=True)
    email_verification_expires = db.Column(db.DateTime, nullable=True)
    # Onboarding email sequence (0=none sent, 2=day3 sent, 3=day7 sent)
    onboarding_emails_sent = db.Column(db.Integer, default=0, nullable=False)
    # Brute-force login protection
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    # 2FA / TOTP — always stored Fernet-encrypted; use the totp_secret property.
    # The DB column stays named 'totp_secret'; the Python attribute is _totp_secret_enc
    # so that the property below intercepts all reads and writes.
    _totp_secret_enc = db.Column("totp_secret", db.String(255), nullable=True)
    totp_enabled = db.Column(db.Boolean, default=False, nullable=False)
    totp_backup_codes = db.Column(db.JSON, nullable=True)  # list of bcrypt-hashed backup codes

    @property
    def totp_secret(self):
        """Return the decrypted TOTP secret, or None if not set.

        Automatically re-encrypts under the current key when the old key was used,
        so the old ENCRYPTION_KEY_OLD can be retired after a rotation window.
        """
        if not self._totp_secret_enc:
            return None
        from .utils.encryption import decrypt_value, encrypt_value, DecryptionError

        def _reenc(new_ct):
            self._totp_secret_enc = new_ct

        try:
            return decrypt_value(self._totp_secret_enc, _re_encrypt_callback=_reenc)
        except DecryptionError:
            import logging
            logging.getLogger(__name__).error(
                "User %s totp_secret decryption failed — secret may be corrupt or key rotated incorrectly", self.id
            )
            return None

    @totp_secret.setter
    def totp_secret(self, plaintext):
        """Encrypt and store the TOTP secret. Pass None to clear it."""
        if plaintext is None:
            self._totp_secret_enc = None
            return
        from .utils.encryption import encrypt_value
        self._totp_secret_enc = encrypt_value(plaintext)
    # Anti-abuse: hashed signup identifiers (SHA-256; never raw IP or fingerprint)
    signup_ip_hash = db.Column(db.String(64), nullable=True, index=True)
    device_fingerprint_hash = db.Column(db.String(64), nullable=True, index=True)
    is_suspicious = db.Column(db.Boolean, default=False, nullable=False)
    # Telegram account linkage
    telegram_user_id = db.Column(db.String(255), nullable=True, unique=True, index=True)
    telegram_username = db.Column(db.String(255), nullable=True)
    telegram_first_name = db.Column(db.String(255), nullable=True)
    telegram_connected_at = db.Column(db.DateTime, nullable=True)
    # Email-linking via Mini App OTP flow
    email_link_pending = db.Column(db.String(255), nullable=True)       # email being linked
    email_link_otp_hash = db.Column(db.String(64), nullable=True)       # SHA-256 of 6-digit OTP
    email_link_otp_expires = db.Column(db.DateTime, nullable=True)
    # Workspace AI token usage tracking (reset daily)
    workspace_ai_tokens_today = db.Column(db.Integer, default=0, nullable=False)
    workspace_ai_tokens_reset_at = db.Column(db.DateTime, nullable=True)
    # User's preferred timezone (IANA name, e.g. "America/New_York"). Used for digest scheduling.
    timezone = db.Column(db.String(64), default="UTC", nullable=False)
    # ToS acceptance tracking (1-D-05)
    tos_version_accepted = db.Column(db.String(20), nullable=True)  # e.g. "2.0"
    tos_accepted_at      = db.Column(db.DateTime, nullable=True)
    # AUP acceptance tracking
    aup_accepted_at      = db.Column(db.DateTime, nullable=True)
    # GDPR soft-delete
    deleted_at           = db.Column(db.DateTime, nullable=True)
    is_suspended         = db.Column(db.Boolean, default=False, nullable=False)
    # AI cost tracking (1-G-04)
    ai_cost_usd_today    = db.Column(db.Numeric(10, 6), default=0)
    ai_cost_reset_at     = db.Column(db.DateTime, nullable=True)
    # 14-day Pro trial (2-D-01)
    trial_ends_at        = db.Column(db.DateTime, nullable=True)
    trial_used           = db.Column(db.Boolean, default=False)
    # Onboarding checklist (2-B-01)
    onboarding_completed_steps = db.Column(db.JSON, nullable=True)  # list of completed step keys
    # Product tour: server-side persistence so it never re-appears across
    # refreshes / browsers / Telegram webview sessions (localStorage is wiped in
    # the Telegram in-app webview). Reset via Settings → Retake Onboarding Tour.
    onboarding_tour_completed = db.Column(db.Boolean, default=False, nullable=False)
    # Payment abuse tracking
    chargeback_count = db.Column(db.Integer, default=0, nullable=False)

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
            "auth_provider": self.auth_provider or "email",
            "email_linked": bool(self.email),
            "subscription_tier": self.subscription_tier,
            "subscription_expires": self.subscription_expires.isoformat() if self.subscription_expires else None,
            "is_banned": self.is_banned,
            "admin_role": self.admin_role,
            "created_at": self.created_at.isoformat(),
            "referral_code": self.referral_code,
            "email_verified": self.email_verified,
            "totp_enabled": self.totp_enabled,
            "telegram_connected": bool(self.telegram_user_id),
            "telegram_username": self.telegram_username,
            "telegram_first_name": self.telegram_first_name,
            "telegram_connected_at": self.telegram_connected_at.isoformat() if self.telegram_connected_at else None,
            "timezone": self.timezone or "UTC",
            "trial_ends_at": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
            "trial_used": bool(self.trial_used),
            "onboarding_completed_steps": self.onboarding_completed_steps or [],
            "onboarding_tour_completed": bool(self.onboarding_tour_completed),
        }


class UserTelegramAccount(db.Model):
    """Linked Telegram accounts for a user. Multiple Telegram IDs can be
    associated with one email/user account and managed under the same dashboard."""
    __tablename__ = "user_telegram_accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    telegram_user_id = db.Column(db.String(255), nullable=False, unique=True, index=True)
    telegram_username = db.Column(db.String(255), nullable=True)
    telegram_first_name = db.Column(db.String(255), nullable=True)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    linked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("user_id", "telegram_user_id", name="uq_user_telegram"),)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_user_id": self.telegram_user_id,
            "telegram_username": self.telegram_username,
            "telegram_first_name": self.telegram_first_name,
            "is_primary": self.is_primary,
            "linked_at": self.linked_at.isoformat(),
        }


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # token_hash: SHA-256 of the raw token sent in the reset email URL.
    # The raw token is NEVER stored — only the hash. This prevents DB-dump
    # + email-cache attacks from producing a working reset link.
    token_hash = db.Column(db.String(64), unique=True, nullable=True, index=True)
    # Legacy column — kept to avoid dropping existing rows; no longer written.
    token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

    @staticmethod
    def _hash(raw_token: str) -> str:
        import hashlib
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @staticmethod
    def create_for_user(user_id):
        """Return (raw_token, PasswordResetToken) — caller sends raw_token in email."""
        raw = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        row = PasswordResetToken(
            user_id=user_id,
            token_hash=PasswordResetToken._hash(raw),
            # Production DB has token NOT NULL (migration pending).
            # Populate with the raw token so the constraint is satisfied.
            # find_valid() prefers token_hash; falls back to this for old rows.
            token=raw,
            expires_at=expires_at,
        )
        return raw, row

    @staticmethod
    def find_valid(raw_token: str):
        """Look up a valid (unused, unexpired) token row by the raw token string."""
        token_hash = PasswordResetToken._hash(raw_token)
        row = PasswordResetToken.query.filter_by(token_hash=token_hash, used=False).first()
        if row is None:
            # Fallback: check legacy plaintext column for rows created before this fix
            row = PasswordResetToken.query.filter_by(token=raw_token, used=False).first()
        if row is None or datetime.utcnow() >= row.expires_at:
            return None
        return row

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
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    # Stores the Fernet-encrypted token; use get_token()/set_token() helpers.
    bot_token = db.Column(db.Text, nullable=False)
    # SHA-256 hash of the plain token used for fast uniqueness checks.
    bot_token_hash = db.Column(db.String(64), unique=True, nullable=True, index=True)
    bot_username = db.Column(db.String(255), nullable=True)
    bot_name = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_active = db.Column(db.DateTime, nullable=True)
    # Secret token used to validate incoming Telegram webhook POSTs in webhook mode.
    # Generated on first webhook registration; None means bot uses polling mode.
    webhook_secret = db.Column(db.String(64), nullable=True)

    groups = db.relationship("Group", backref="bot", lazy=True, cascade="all, delete-orphan")

    def get_token(self) -> str:
        """Return the decrypted plain-text bot token, re-encrypting under the current key if needed."""
        from .utils.encryption import decrypt_value, encrypt_value

        def _reenc(new_ct):
            self.bot_token = new_ct

        return decrypt_value(self.bot_token, _re_encrypt_callback=_reenc)

    def set_token(self, plain_token: str):
        """Encrypt and store the bot token; update the hash column."""
        from .utils.encryption import encrypt_value, hash_token
        self.bot_token = encrypt_value(plain_token)
        self.bot_token_hash = hash_token(plain_token)

    def get_health_status(self):
        """Derive public health from is_active + last_active age.

        Infrastructure states (thread alive, watchdog recovery, deploy
        events) are intentionally excluded — they are internal only.
        Thresholds are wide enough to survive Railway rolling deploys
        and heartbeat gaps without showing false negatives.
        """
        if not self.is_active:
            return "offline"
        if self.last_active is None:
            return "active"  # freshly added bot; thread starting up
        age = datetime.utcnow() - self.last_active
        if age <= timedelta(days=7):
            return "active"
        if age <= timedelta(days=30):
            return "idle"
        return "unreachable"

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
    # Telegram chat type: group | supergroup | channel | private
    # Set at creation time; used to exclude private groups from listings.
    chat_type = db.Column(db.String(20), default="group", nullable=False)
    # Public @username of the Telegram group.
    # NULL  = not yet resolved (old records — shown for backwards compat).
    # ""    = confirmed private (no username) — excluded from Group Management.
    # "foo" = public group with @username — shown in Group Management.
    chat_username = db.Column(db.String(255), nullable=True)
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
            "chat_type": self.chat_type or "group",
            "is_private": (self.chat_type or "group") == "private",
            "created_at": self.created_at.isoformat(),
            "member_count": self.telegram_member_count if self.telegram_member_count else len(self.members),
        }


class Member(db.Model):
    __tablename__ = "members"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
    telegram_user_id = db.Column(db.String(255), nullable=False)
    username = db.Column(db.String(255), nullable=True)
    first_name = db.Column(db.String(255), nullable=True)
    last_name = db.Column(db.String(255), nullable=True)
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
    crm_tags = db.Column(db.JSON, nullable=True)
    crm_notes = db.Column(db.Text, nullable=True)
    engagement_score = db.Column(db.Integer, nullable=True)
    xp_1d  = db.Column(db.Integer, default=0, nullable=False)
    xp_7d  = db.Column(db.Integer, default=0, nullable=False)
    xp_30d = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (db.UniqueConstraint("group_id", "telegram_user_id", name="unique_group_member"),)

    def compute_engagement_score(self):
        from datetime import datetime
        score = 0
        score += min(40, int(((self.level or 1) / 10) * 40))
        score += min(15, int(((self.xp or 0) / 1000) * 15))
        if self.last_message_at:
            days = (datetime.utcnow() - self.last_message_at).days
            score += 20 if days <= 1 else 15 if days <= 3 else 10 if days <= 7 else 5 if days <= 14 else 0
        if self.is_verified:
            score += 10
        if self.wallet_address:
            score += 5
        score -= min(score, (self.warnings or 0) * 10)
        if self.is_muted:
            score = max(0, score - 15)
        return max(0, min(100, score))

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
            "crm_tags": self.crm_tags or [],
            "crm_notes": self.crm_notes or "",
            "engagement_score": self.engagement_score,
            "xp_1d": self.xp_1d or 0,
            "xp_7d": self.xp_7d or 0,
            "xp_30d": self.xp_30d or 0,
        }


class XpEvent(db.Model):
    """Timestamped XP ledger — the source of truth for period (today/7d/30d) XP.

    The xp_1d/xp_7d/xp_30d columns on Member/OfficialMember are derived snapshots,
    recomputed from this ledger over true rolling windows by a scheduled job
    (see scheduler.recompute_xp_periods). Each row is a single +/- XP change.
    `member_id` is the PK of Member (scope='custom') or OfficialMember (scope='official');
    `scope` disambiguates the two id spaces.
    """
    __tablename__ = "xp_events"

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(16), nullable=False)          # 'custom' | 'official'
    member_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Integer, nullable=False)             # may be negative (penalties)
    reason = db.Column(db.String(64), nullable=True)           # 'message' | 'reaction' | 'penalty' | ...
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("ix_xp_events_scope_member_created", "scope", "member_id", "created_at"),
        db.Index("ix_xp_events_scope_created", "scope", "created_at"),
    )


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
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
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
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
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
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
    use_as_ai_knowledge = db.Column(db.Boolean, default=False, nullable=False, server_default="false")

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
            "use_as_ai_knowledge": self.use_as_ai_knowledge,
        }


class KnowledgeDocument(db.Model):
    __tablename__ = "knowledge_documents"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True, index=True)
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
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
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
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    # webhook_token: in the trigger URL — proves the caller knows the endpoint.
    webhook_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    # signing_secret: HMAC-SHA256 key — callers sign the raw request body with this
    # and put the hex digest in X-Telegizer-Signature. Null = legacy (token-only auth).
    signing_secret = db.Column(db.String(64), nullable=True)
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
            "signing_secret": self.signing_secret,  # shown once at creation
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
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True, index=True)
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
        from .utils.encryption import mask_key, decrypt_value, DecryptionError
        try:
            raw = decrypt_value(self.api_key_encrypted) if self.api_key_encrypted else ""
        except DecryptionError:
            raw = ""
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


class PendingInvoice(db.Model):
    """Server-side record created when a user initiates a NOWPayments checkout.

    The invoice_id (NOWPayments' invoice ID) is used as order_id so the IPN
    handler looks up user_id from the DB row rather than trusting a user_id
    embedded in the order string — which an attacker could tamper with to credit
    a different account.
    """
    __tablename__ = "pending_invoices"

    id = db.Column(db.Integer, primary_key=True)
    # NOWPayments invoice ID returned from /v1/invoice — used as order_id in IPN
    invoice_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    tier = db.Column(db.String(50), nullable=False)
    billing_period = db.Column(db.String(10), nullable=False)
    amount_usd = db.Column(db.Numeric(10, 2), nullable=False)
    processed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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


class SubscriptionRenewal(db.Model):
    """One record per successful payment that activates or extends a subscription (1-A-02)."""
    __tablename__ = "subscription_renewals"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan        = db.Column(db.String(50))      # "pro" | "enterprise"
    interval    = db.Column(db.String(20))      # "monthly" | "annual"
    amount_usd  = db.Column(db.Numeric(10, 2))
    payment_id  = db.Column(db.String(200))     # NOWPayments / LS payment id
    renewed_at  = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at  = db.Column(db.DateTime)


class PromoCode(db.Model):
    """Admin-created promo / discount codes applied at checkout."""
    __tablename__ = "promo_codes"

    id              = db.Column(db.Integer, primary_key=True)
    code            = db.Column(db.String(50), unique=True, nullable=False, index=True)
    # percent | fixed | trial_days
    discount_type   = db.Column(db.String(20), nullable=False, default="percent")
    discount_value  = db.Column(db.Numeric(10, 2), nullable=False)
    # JSON list of plan tiers it applies to, e.g. ["pro","enterprise"]. None = all.
    applicable_plans = db.Column(db.JSON, nullable=True)
    max_uses        = db.Column(db.Integer, nullable=True)     # None = unlimited
    uses_count      = db.Column(db.Integer, default=0, nullable=False)
    max_uses_per_user = db.Column(db.Integer, default=1, nullable=False)
    valid_from      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    valid_until     = db.Column(db.DateTime, nullable=True)    # None = no expiry
    is_active       = db.Column(db.Boolean, default=True, nullable=False)
    # KOL / influencer tracking
    is_influencer_code = db.Column(db.Boolean, default=False, nullable=False)
    influencer_name = db.Column(db.String(100), nullable=True)
    label           = db.Column(db.String(200), nullable=True) # internal note
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    usages = db.relationship("PromoCodeUsage", backref="promo_code", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "discount_type": self.discount_type,
            "discount_value": float(self.discount_value),
            "applicable_plans": self.applicable_plans,
            "max_uses": self.max_uses,
            "uses_count": self.uses_count,
            "max_uses_per_user": self.max_uses_per_user,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "is_active": self.is_active,
            "is_influencer_code": self.is_influencer_code,
            "influencer_name": self.influencer_name,
            "label": self.label,
            "created_at": self.created_at.isoformat(),
        }

    def is_valid_for(self, user_id: int, plan: str) -> tuple[bool, str]:
        """Return (ok, reason). reason is empty string when ok=True."""
        now = datetime.utcnow()
        if not self.is_active:
            return False, "Code is no longer active."
        if self.valid_from and now < self.valid_from:
            return False, "Code is not yet valid."
        if self.valid_until and now > self.valid_until:
            return False, "Code has expired."
        if self.max_uses is not None and self.uses_count >= self.max_uses:
            return False, "Code has reached its usage limit."
        if self.applicable_plans and plan not in self.applicable_plans:
            return False, f"Code is not valid for the {plan} plan."
        # Per-user limit — only count confirmed (paid) usages so abandoned
        # checkouts don't permanently block the user from retrying.
        user_uses = PromoCodeUsage.query.filter_by(
            promo_code_id=self.id, user_id=user_id, confirmed=True
        ).count()
        if user_uses >= self.max_uses_per_user:
            return False, "You have already used this code."
        return True, ""

    def compute_discount(self, base_amount_usd: float) -> float:
        """Return discount amount in USD (positive value to subtract)."""
        v = float(self.discount_value)
        if self.discount_type == "percent":
            return round(base_amount_usd * v / 100, 2)
        if self.discount_type == "fixed":
            return min(v, base_amount_usd)
        return 0.0  # trial_days handled separately


class PromoCodeUsage(db.Model):
    """One record per successful promo-code redemption."""
    __tablename__ = "promo_code_usages"

    id              = db.Column(db.Integer, primary_key=True)
    promo_code_id   = db.Column(db.Integer, db.ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    used_at         = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    order_id        = db.Column(db.String(255), nullable=True, index=True)  # NOWPayments invoice / payment id
    original_price  = db.Column(db.Numeric(10, 2), nullable=True)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=True)
    final_price     = db.Column(db.Numeric(10, 2), nullable=True)
    # False = checkout initiated but payment not yet confirmed. True = payment confirmed.
    # Per-user limit checks only count confirmed=True rows so abandoned checkouts
    # don't permanently block re-use of the same code.
    confirmed       = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "promo_code_id": self.promo_code_id,
            "user_id": self.user_id,
            "used_at": self.used_at.isoformat(),
            "order_id": self.order_id,
            "original_price": float(self.original_price) if self.original_price else None,
            "discount_amount": float(self.discount_amount) if self.discount_amount else None,
            "final_price": float(self.final_price) if self.final_price else None,
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
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
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
    # Referral code captured from `/start ref_<code>` before the user has an account.
    # Consumed when the Mini App auto-creates the user, then cleared.
    pending_referral_code = db.Column(db.String(16), nullable=True)

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

    @staticmethod
    def set_pending_referral(user_id: str, ref_code: str):
        """Stash a referral code from `/start ref_<code>` until the account is created.
        Only stores if no code is already pending (first referral link wins)."""
        existing = TelegramBotStarted.query.filter_by(telegram_user_id=str(user_id)).first()
        if existing is None:
            existing = TelegramBotStarted(telegram_user_id=str(user_id))
            db.session.add(existing)
        if not existing.pending_referral_code:
            existing.pending_referral_code = ref_code[:16]

    @staticmethod
    def consume_pending_referral(user_id: str) -> str | None:
        """Return and clear the pending referral code for a Telegram user, if any."""
        existing = TelegramBotStarted.query.filter_by(telegram_user_id=str(user_id)).first()
        if existing and existing.pending_referral_code:
            code = existing.pending_referral_code
            existing.pending_referral_code = None
            return code
        return None


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
    # 'group_management' = My Groups / moderation pillar
    # 'assistant_hub'    = Assistant Hub / AI extraction pillar
    group_context = db.Column(db.String(20), default="group_management", nullable=False,
                              server_default="group_management")

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
            "group_context": self.group_context or "group_management",
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
    xp_1d  = db.Column(db.Integer, default=0, nullable=False)
    xp_7d  = db.Column(db.Integer, default=0, nullable=False)
    xp_30d = db.Column(db.Integer, default=0, nullable=False)

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
            "xp_1d": self.xp_1d or 0,
            "xp_7d": self.xp_7d or 0,
            "xp_30d": self.xp_30d or 0,
        }


class PendingVerification(db.Model):
    """In-flight member verifications — persisted so restarts don't lose state."""
    __tablename__ = "pending_verifications"

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.BigInteger, nullable=False)
    user_id = db.Column(db.BigInteger, nullable=False)
    method = db.Column(db.String(20), nullable=False)
    msg_id = db.Column(db.Integer, nullable=True)
    # Forum topic ID — if set, delete/send in this topic thread
    message_thread_id = db.Column(db.Integer, nullable=True)
    answer = db.Column(db.String(500), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    kick_on_fail = db.Column(db.Boolean, default=True)
    auto_delete_on_timeout = db.Column(db.Boolean, default=True)
    max_attempts = db.Column(db.Integer, default=3)
    attempts = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("chat_id", "user_id", name="uq_pending_verification"),
    )


class PendingUnban(db.Model):
    """Tracks temp-banned users who need to be unbanned after a delay (1-C-01)."""
    __tablename__ = "pending_unbans"

    id               = db.Column(db.Integer, primary_key=True)
    telegram_chat_id = db.Column(db.BigInteger, nullable=False)
    telegram_user_id = db.Column(db.BigInteger, nullable=False)
    unban_at         = db.Column(db.DateTime, nullable=False)
    retry_count      = db.Column(db.Integer, default=0)
    last_attempt_at  = db.Column(db.DateTime)
    success          = db.Column(db.Boolean, default=False)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)


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
    message_text = db.Column(db.Text, nullable=True)
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
            "message_text": self.message_text,
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
    # dashboard-generated flow (1-B-01): user_id set, telegram_group_id null initially
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    bot_id  = db.Column(db.Integer, db.ForeignKey("bots.id"), nullable=True)
    # bot-generated flow (legacy): telegram_group_id always set
    telegram_group_id = db.Column(db.String(255), db.ForeignKey("telegram_groups.telegram_group_id"), nullable=True)
    telegram_group_title = db.Column(db.String(255), nullable=True)
    created_by_telegram_user_id = db.Column(db.String(255), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    used = db.Column(db.Boolean, default=False, nullable=False)
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

    # Link to the matching HubBotIdentity — set when the bot is auto-mirrored to Assistant Hub
    hub_bot_id = db.Column(db.String(36), db.ForeignKey("hub_bot_identities.id", ondelete="SET NULL"), nullable=True, index=True)

    linked_groups = db.relationship("TelegramGroup", backref="custom_bot", lazy=True)

    def get_token(self) -> str:
        from .utils.encryption import decrypt_value, encrypt_value

        def _reenc(new_ct):
            self.bot_token_encrypted = new_ct

        return decrypt_value(self.bot_token_encrypted, _re_encrypt_callback=_reenc)

    def set_token(self, plain_token: str):
        from .utils.encryption import encrypt_value
        self.bot_token_encrypted = encrypt_value(plain_token)

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
            "hub_bot_id": self.hub_bot_id,
        }
        if include_token:
            data["bot_token"] = self.get_token()
        return data


class GroupForumTopic(db.Model):
    """Forum topics passively discovered by the bot in a Telegram supergroup.

    Telegram has no API to list all topics, so the bot caches them here as it
    sees activity. The dashboard reads this table to populate topic selectors.
    """
    __tablename__ = "group_forum_topics"

    id = db.Column(db.Integer, primary_key=True)
    # The Telegram chat ID string (e.g. "-100123456789") — works for both
    # TelegramGroup (official) and Group (custom bot) contexts.
    telegram_group_id = db.Column(db.String(255), nullable=False, index=True)
    thread_id = db.Column(db.BigInteger, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    is_closed = db.Column(db.Boolean, default=False, nullable=False)
    discovered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("telegram_group_id", "thread_id", name="uq_forum_topic_group_thread"),
    )

    def to_dict(self):
        return {
            "thread_id": self.thread_id,
            "name": self.name,
            "is_closed": self.is_closed,
            "discovered_at": self.discovered_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
        }


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


class BotHealthEvent(db.Model):
    """Append-only log of bot failures, surfaced in the admin Bot Health tab.

    Only ERRORS are recorded (never successful messages) so write volume stays
    low even with hundreds of custom bots. Liveness is checked on-demand via the
    admin "Ping" button (Telegram getMe), not from this table.
    """
    __tablename__ = "bot_health_events"

    id = db.Column(db.Integer, primary_key=True)
    # official | custom | assistant | ai
    scope = db.Column(db.String(20), nullable=False, index=True)
    # custom bot id, telegram group id, 'official', or 'provider:model'
    ref = db.Column(db.String(64), nullable=True, index=True)
    # handler | ai | command | webhook
    category = db.Column(db.String(20), nullable=False)
    detail = db.Column(db.Text, nullable=True)  # truncated error message (<= 500 chars)
    # Classification (Part 6): severity ∈ info|warning|critical; error_class is a
    # stable machine key (deployment_restart, invalid_token, network_error, …).
    severity = db.Column(db.String(10), nullable=True, index=True)
    error_class = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "scope": self.scope,
            "ref": self.ref,
            "category": self.category,
            "detail": self.detail,
            "severity": self.severity,
            "error_class": self.error_class,
            "created_at": self.created_at.isoformat(),
        }


class BotHealthState(db.Model):
    """Per-bot liveness + escalation state for the Bot Health Center (P1).

    One row per monitored bot across BOTH tables (scope = 'legacy' | 'custom').
    Updated by the scheduled getMe ping job. Distinct from BotHealthEvent, which
    is an append-only error log; this is the current rolled-up state.
    """
    __tablename__ = "bot_health_state"
    __table_args__ = (
        db.UniqueConstraint("scope", "ref", name="uq_bot_health_state_scope_ref"),
    )

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(20), nullable=False, index=True)   # legacy | custom
    ref = db.Column(db.String(64), nullable=False, index=True)     # bot id (as string)
    bot_username = db.Column(db.String(255), nullable=True)
    owner_user_id = db.Column(db.Integer, nullable=True, index=True)
    # healthy | warning | critical | inactive | archived
    health_grade = db.Column(db.String(20), nullable=False, default="healthy", index=True)
    consecutive_failures = db.Column(db.Integer, nullable=False, default=0)
    last_ping_at = db.Column(db.DateTime, nullable=True)
    last_successful_ping = db.Column(db.DateTime, nullable=True)
    last_failed_ping = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    last_alert_grade = db.Column(db.String(20), nullable=True)     # last grade we alerted the owner about
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "scope": self.scope,
            "ref": self.ref,
            "bot_username": self.bot_username,
            "owner_user_id": self.owner_user_id,
            "health_grade": self.health_grade,
            "consecutive_failures": self.consecutive_failures,
            "last_ping_at": self.last_ping_at.isoformat() if self.last_ping_at else None,
            "last_successful_ping": self.last_successful_ping.isoformat() if self.last_successful_ping else None,
            "last_failed_ping": self.last_failed_ping.isoformat() if self.last_failed_ping else None,
            "last_error": self.last_error,
        }


class AIActivity(db.Model):
    """Append-only log of AI-generated actions inside a group (AI Activity tab).

    This is a *reporting layer* only — it records actions already performed by
    the AI systems (moderation, knowledge, engagement, automation, analytics).
    Writing here must never trigger a new AI call or raise into the caller; use
    the best-effort `backend.ai_activity.log_ai_activity()` helper.

    Groups are addressed flexibly so both bot worlds share one table:
      • official-bot groups  → scope='official', group_ref=telegram_group_id (str)
      • custom-bot groups    → scope='custom',   group_ref=str(Group.id)
    """
    __tablename__ = "ai_activity"

    # The five spec categories.
    CATEGORIES = ("moderation", "knowledge", "engagement", "automation", "analytics")

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(20), nullable=False, index=True)        # official | custom
    group_ref = db.Column(db.String(64), nullable=False, index=True)   # telegram_group_id or Group.id
    category = db.Column(db.String(20), nullable=False, index=True)    # one of CATEGORIES
    action = db.Column(db.String(120), nullable=False)                 # e.g. "Spam removed", "FAQ answer generated"
    # Free-form context: reason, query, knowledge source, summary, outcome…
    detail = db.Column(db.Text, nullable=True)
    # Who/what the action was about (display name or @username)
    target = db.Column(db.String(255), nullable=True)
    # ok | failed | skipped — lets the tab show whether the action worked
    status = db.Column(db.String(20), nullable=False, default="ok")
    # Which AI engine produced it (e.g. "knowledge_base", "automod", "welcome")
    source = db.Column(db.String(40), nullable=True)
    meta = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        db.Index("ix_ai_activity_group_created", "scope", "group_ref", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "action": self.action,
            "detail": self.detail,
            "target": self.target,
            "status": self.status,
            "source": self.source,
            "meta": self.meta,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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
    # Legacy single source/destination — kept readable for back-compat. The
    # source(s)/destination(s) of record now live in the child tables below;
    # these columns are backfilled and used as a fallback when no child rows exist.
    source_group_id = db.Column(db.String(255), nullable=False, index=True)
    source_topic_id = db.Column(db.Integer, nullable=True)      # message_thread_id filter
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
    sources = db.relationship("ForwardSource", backref="rule", lazy="select",
                              cascade="all, delete-orphan")
    destinations = db.relationship("ForwardDestination", backref="rule", lazy="select",
                                   cascade="all, delete-orphan")

    def effective_sources(self):
        """List of {chat_id, topic_id}. Falls back to the legacy single source
        column when no ForwardSource rows exist (pre-migration rules)."""
        rows = list(self.sources)
        if rows:
            return [{"chat_id": s.source_chat_id, "topic_id": s.source_topic_id} for s in rows]
        return [{"chat_id": self.source_group_id, "topic_id": self.source_topic_id}]

    def effective_destinations(self):
        """List of {id, destination_id, topic_id, is_paused}. Falls back to the
        legacy single destination column when no ForwardDestination rows exist."""
        rows = list(self.destinations)
        if rows:
            return [
                {"id": d.id, "destination_id": d.destination_id,
                 "topic_id": d.topic_id, "is_paused": d.is_paused}
                for d in rows
            ]
        return [{"id": None, "destination_id": self.destination_id,
                 "topic_id": None, "is_paused": False}]

    def to_dict(self):
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "rule_name": self.rule_name,
            "source_group_id": self.source_group_id,
            "source_topic_id": self.source_topic_id,
            "destination_id": self.destination_id,
            "keyword_filter": self.keyword_filter,
            "match_type": self.match_type,
            "prefix_text": self.prefix_text,
            "suffix_text": self.suffix_text,
            "require_approval": self.require_approval,
            "is_active": self.is_active,
            "forward_count": self.forward_count,
            "created_at": self.created_at.isoformat(),
            "sources": self.effective_sources(),
            "destinations": [
                {**d, "forward_count": None} if d["id"] is None else d
                for d in self.effective_destinations()
            ],
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
    destination_topic_id = db.Column(db.Integer, nullable=True)  # forum thread, if any
    # Which bot captured this message — custom Bot.id, or NULL = official bot.
    # Lets the approval path deliver via the exact owning bot's loop.
    bot_id = db.Column(db.Integer, nullable=True)
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
            "destination_topic_id": self.destination_topic_id,
            "bot_id": self.bot_id,
            "status": self.status,
            "error_msg": self.error_msg,
            "created_at": self.created_at.isoformat(),
        }


class ForwardSource(db.Model):
    """One source chat (+optional forum topic) for a forwarding rule.

    Enables many→one / many→many fan-in within a single rule (O3). A rule with no
    ForwardSource rows falls back to ForwardRule.source_group_id for back-compat.
    """
    __tablename__ = "forward_sources"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("forward_rules.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    source_chat_id = db.Column(db.String(255), nullable=False, index=True)
    source_topic_id = db.Column(db.Integer, nullable=True)  # message_thread_id filter
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "source_chat_id": self.source_chat_id,
            "source_topic_id": self.source_topic_id,
        }


class ForwardDestination(db.Model):
    """One destination chat (+optional forum topic) for a forwarding rule.

    Enables 1→many fan-out (D4). A rule with no ForwardDestination rows falls
    back to ForwardRule.destination_id for back-compat. The anti-ban governor
    (D7) flips `is_paused` when a destination becomes unhealthy.
    """
    __tablename__ = "forward_destinations"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("forward_rules.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    destination_id = db.Column(db.String(255), nullable=False)  # chat_id or @username
    topic_id = db.Column(db.Integer, nullable=True)             # message_thread_id target
    is_paused = db.Column(db.Boolean, default=False, nullable=False)
    pause_reason = db.Column(db.String(255), nullable=True)
    last_error = db.Column(db.String(500), nullable=True)
    fail_count = db.Column(db.Integer, default=0, nullable=False)  # consecutive failures
    forward_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "destination_id": self.destination_id,
            "topic_id": self.topic_id,
            "is_paused": self.is_paused,
            "pause_reason": self.pause_reason,
            "last_error": self.last_error,
            "fail_count": self.fail_count,
            "forward_count": self.forward_count,
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
    # Moderation: pending | approved | rejected. Public browse filtered by approved.
    moderation_status = db.Column(db.String(16), default="pending", nullable=False, index=True)

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
    # Semantic search embedding (pgvector, 1536-dim for OpenAI / 768-dim for Gemini)
    embedding = db.Column(_PgVector(1536), nullable=True) if _PGVECTOR_AVAILABLE else db.Column(db.Text, nullable=True)
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


class BotDMMessage(db.Model):
    """DM conversation between a user and the bot (for Live Chat in the web UI)."""
    __tablename__ = "bot_dm_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    direction = db.Column(db.String(3), nullable=False)  # 'in' (user→bot) | 'out' (bot→user)
    content = db.Column(db.Text, nullable=False)
    intent = db.Column(db.String(50), nullable=True)  # 'reminder', 'note', 'other', etc.
    # Analytics / feedback (Phase 6.3)
    session_id = db.Column(db.String(36), nullable=True, index=True)  # UUID groups a conversation session
    feedback = db.Column(db.SmallInteger, nullable=True)               # 1=thumbs up, -1=thumbs down
    intent_confidence = db.Column(db.Float, nullable=True)             # 0.0–1.0 AI confidence score
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "direction": self.direction,
            "content": self.content,
            "intent": self.intent,
            "session_id": self.session_id,
            "feedback": self.feedback,
            "intent_confidence": self.intent_confidence,
            "created_at": self.created_at.isoformat(),
        }


class EscalationEvent(db.Model):
    """Global escalation event — any AI/Automation issue forwarded to admins for review."""
    __tablename__ = "escalation_events"

    id = db.Column(db.Integer, primary_key=True)
    # Group context (nullable to support both official and custom bots)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True)
    telegram_group_id = db.Column(db.String(255), nullable=True, index=True)
    bot_id = db.Column(db.Integer, nullable=True)  # custom bot int id, null = official
    # Issue details
    issue_type = db.Column(db.String(50), nullable=False)  # ai_kb | ai_image | automation | command | moderation
    user_telegram_id = db.Column(db.String(100), nullable=True)
    user_username = db.Column(db.String(255), nullable=True)
    original_content = db.Column(db.Text, nullable=True)
    context_data = db.Column(db.JSON, nullable=True)   # {confidence, group_name, thread_id, ...}
    # Admin DM tracking: list of {admin_id, summary_msg_id} so replies can be linked
    admin_dm_refs = db.Column(db.JSON, nullable=True)
    # Resolution
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)  # pending | resolved | ignored
    resolved_admin_telegram_id = db.Column(db.String(100), nullable=True)
    admin_answer = db.Column(db.Text, nullable=True)
    learned = db.Column(db.Boolean, default=False, nullable=False)  # stored in KB?
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "group_id": self.group_id,
            "telegram_group_id": self.telegram_group_id,
            "bot_id": self.bot_id,
            "issue_type": self.issue_type,
            "user_telegram_id": self.user_telegram_id,
            "user_username": self.user_username,
            "original_content": self.original_content,
            "context_data": self.context_data,
            "status": self.status,
            "resolved_admin_telegram_id": self.resolved_admin_telegram_id,
            "admin_answer": self.admin_answer,
            "learned": self.learned,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class PendingReminderState(db.Model):
    """Transient state while bot collects reminder time/frequency from the user."""
    __tablename__ = "pending_reminder_states"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True)
    subject = db.Column(db.String(500), nullable=False)
    remind_at = db.Column(db.DateTime, nullable=True)   # filled after user picks time
    expires_at = db.Column(db.DateTime, nullable=False)  # auto-expire stale state

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "subject": self.subject,
            "remind_at": self.remind_at.isoformat() if self.remind_at else None,
            "expires_at": self.expires_at.isoformat(),
        }


class Task(db.Model):
    """User task — created manually, by AI extraction, or via bot DM."""
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="todo", nullable=False)   # todo|doing|done
    priority = db.Column(db.String(10), default="medium", nullable=False)  # low|medium|high
    source = db.Column(db.String(20), default="manual", nullable=False)   # manual|ai|bot
    due_at = db.Column(db.DateTime, nullable=True)
    group_id = db.Column(db.String(255), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "source": self.source,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "group_id": self.group_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AutoReplyLog(db.Model):
    """Log of auto-reply (SmartLink) triggers fired in groups."""
    __tablename__ = "auto_reply_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    auto_response_id = db.Column(db.Integer, db.ForeignKey("auto_responses.id", ondelete="SET NULL"), nullable=True)
    telegram_group_id = db.Column(db.String(255), nullable=True, index=True)
    trigger_text = db.Column(db.String(500), nullable=True)
    message_text = db.Column(db.String(1000), nullable=True)  # incoming message excerpt
    triggered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "auto_response_id": self.auto_response_id,
            "telegram_group_id": self.telegram_group_id,
            "trigger_text": self.trigger_text,
            "message_text": self.message_text,
            "triggered_at": self.triggered_at.isoformat(),
        }


class WorkspaceKnowledgeDocument(db.Model):
    """Workspace-scoped knowledge document (not tied to a specific group/bot)."""
    __tablename__ = "workspace_knowledge_documents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)    # pdf|txt|md|docx
    content_text = db.Column(db.Text, nullable=False)
    chunks = db.Column(db.JSON, nullable=True)               # text chunks for search
    tags = db.Column(db.JSON, nullable=True)                 # user-assigned tags
    description = db.Column(db.String(500), nullable=True)
    # Semantic search embedding
    embedding = db.Column(_PgVector(768), nullable=True) if _PGVECTOR_AVAILABLE else db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "chunk_count": len(self.chunks) if self.chunks else 0,
            "tags": self.tags or [],
            "description": self.description,
            "content_preview": self.content_text[:300] if self.content_text else "",
            "created_at": self.created_at.isoformat(),
        }


class AdminAuditLog(db.Model):
    """Immutable log of every admin action for security review."""
    __tablename__ = "admin_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    action = db.Column(db.String(255), nullable=False)   # Flask endpoint name
    method = db.Column(db.String(10), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    payload_json = db.Column(db.Text, nullable=True)     # sanitised request body
    ip_address = db.Column(db.String(45), nullable=True)
    # Richer audit context (Phase 1 admin-panel overhaul). All nullable so the
    # auto-logger keeps working unchanged; sensitive routes populate them explicitly.
    severity = db.Column(db.String(10), nullable=True)   # info | notice | warning | critical
    target_type = db.Column(db.String(40), nullable=True)  # e.g. "user", "secret", "promo_code"
    target_id = db.Column(db.String(64), nullable=True)
    old_value = db.Column(db.Text, nullable=True)        # safe (never secret) prior value
    new_value = db.Column(db.Text, nullable=True)        # safe (never secret) new value
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "action": self.action,
            "method": self.method,
            "path": self.path,
            "ip_address": self.ip_address,
            "severity": self.severity or "info",
            "target_type": self.target_type,
            "target_id": self.target_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "created_at": self.created_at.isoformat(),
        }


# ── PlatformSetting & FeatureFlag (Phase 2 admin-panel overhaul) ───────────────

class PlatformSetting(db.Model):
    """A single DB-backed platform configuration value, editable from the admin
    panel. Resolved DB-first with hardcoded/env fallback (see backend/platform_config.py).
    ``value_json`` stores any JSON-serialisable value. ``is_public`` marks settings
    safe to expose unauthenticated (branding, URLs, maintenance status)."""
    __tablename__ = "platform_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    value_json = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(40), nullable=True)
    is_public = db.Column(db.Boolean, default=False, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        import json as _json
        try:
            value = _json.loads(self.value_json) if self.value_json is not None else None
        except Exception:
            value = self.value_json
        return {
            "key": self.key,
            "value": value,
            "category": self.category,
            "is_public": self.is_public,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ComplianceRequest(db.Model):
    """Audit trail for GDPR-style requests (data export / account deletion) so
    admins have visibility into who requested what and when, and can mark them
    handled. Created automatically when a user triggers export/delete."""
    __tablename__ = "compliance_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    user_email = db.Column(db.String(255), nullable=True)   # denormalised (survives hard-delete)
    request_type = db.Column(db.String(20), nullable=False)  # export | delete
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending | completed | cancelled
    note = db.Column(db.Text, nullable=True)
    handled_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    handled_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "request_type": self.request_type,
            "status": self.status,
            "note": self.note,
            "handled_by": self.handled_by,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "handled_at": self.handled_at.isoformat() if self.handled_at else None,
        }


class PlatformSecret(db.Model):
    """A platform-level secret/API key, editable from the admin panel and stored
    Fernet-encrypted (reusing utils.encryption). Resolved DB-first with env
    fallback via backend/secret_vault.py. The plaintext is NEVER returned by the
    API — only a masked hint (first4****last4). ``name`` matches the Config attr."""
    __tablename__ = "platform_secrets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value_encrypted = db.Column(db.Text, nullable=True)
    masked_hint = db.Column(db.String(40), nullable=True)   # safe-to-display, e.g. "sk-1****ab2"
    provider = db.Column(db.String(40), nullable=True)
    category = db.Column(db.String(40), nullable=True)
    last_test_ok = db.Column(db.Boolean, nullable=True)
    last_tested_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def get_value(self):
        """Decrypt and return the stored secret, or None."""
        if not self.value_encrypted:
            return None
        from .utils.encryption import decrypt_value, DecryptionError
        try:
            return decrypt_value(self.value_encrypted)
        except DecryptionError:
            import logging
            logging.getLogger(__name__).error("PlatformSecret %s decrypt failed", self.name)
            return None


class FeatureFlag(db.Model):
    """A platform-wide feature toggle / kill-switch, editable from the admin panel.
    Consumed via platform_config.is_feature_enabled(key)."""
    __tablename__ = "feature_flags"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "key": self.key,
            "enabled": self.enabled,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── AdminAnnouncement ─────────────────────────────────────────────────────────

class AdminAnnouncement(db.Model):
    """Platform-wide announcements broadcast by admins to user segments."""
    __tablename__ = "admin_announcements"

    id            = db.Column(db.Integer, primary_key=True)
    admin_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title         = db.Column(db.String(200), nullable=False)
    body          = db.Column(db.Text, nullable=False)
    # Audience: all | free | pro | enterprise | with_bots
    audience      = db.Column(db.String(50), nullable=False, default="all")
    # Channel: inapp | email | both
    channel       = db.Column(db.String(20), nullable=False, default="inapp")
    # Type: info | warning | critical
    announcement_type = db.Column(db.String(20), nullable=False, default="info")
    sent          = db.Column(db.Boolean, default=False, nullable=False)
    sent_at       = db.Column(db.DateTime, nullable=True)
    delivered_count = db.Column(db.Integer, default=0, nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "title": self.title,
            "body": self.body,
            "audience": self.audience,
            "channel": self.channel,
            "announcement_type": self.announcement_type,
            "sent": self.sent,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_count": self.delivered_count,
            "created_at": self.created_at.isoformat(),
        }


# ── AssistantBot ──────────────────────────────────────────────────────────────

class AssistantBot(db.Model):
    """A user-supplied bot token used as their personal Assistant Bot.

    One bot per user (enforced at the route layer via subscription gate).
    The token is stored encrypted via the shared Fernet utility.
    """
    __tablename__ = "assistant_bots"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    _bot_token_enc = db.Column("bot_token", db.String(512), nullable=False)
    bot_username = db.Column(db.String(255), nullable=True)
    bot_name = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def bot_token(self):
        if not self._bot_token_enc:
            return None
        from .utils.encryption import decrypt_value, DecryptionError
        try:
            return decrypt_value(self._bot_token_enc)
        except DecryptionError:
            import logging
            logging.getLogger(__name__).error("AssistantBot %s token decryption failed", self.id)
            return None

    @bot_token.setter
    def bot_token(self, plaintext):
        if plaintext is None:
            self._bot_token_enc = None
            return
        from .utils.encryption import encrypt_value
        self._bot_token_enc = encrypt_value(plaintext)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "bot_username": self.bot_username,
            "bot_name": self.bot_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AssistantSpace(db.Model):
    """A chat (group, supergroup, or private DM) where an AssistantBot has been seen.

    Auto-created on first message — no /link_group command needed.
    """
    __tablename__ = "assistant_spaces"

    id = db.Column(db.Integer, primary_key=True)
    assistant_bot_id = db.Column(db.Integer, db.ForeignKey("assistant_bots.id", ondelete="CASCADE"), nullable=False, index=True)
    telegram_chat_id = db.Column(db.String(255), nullable=False)
    chat_title = db.Column(db.String(255), nullable=True)
    chat_type = db.Column(db.String(30), nullable=False, default="unknown")  # private|group|supergroup|channel
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("assistant_bot_id", "telegram_chat_id", name="uq_assistant_space"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "assistant_bot_id": self.assistant_bot_id,
            "telegram_chat_id": self.telegram_chat_id,
            "chat_title": self.chat_title,
            "chat_type": self.chat_type,
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
        }


# ── Group Daily Signal ────────────────────────────────────────────────────────

class GroupDailySignal(db.Model):
    """Pre-computed daily health signal for a Telegram group.

    Populated by the GroupSignalExtractor pipeline (runs every 2 hours).
    One record per group per calendar date (UTC). Upserted, not duplicated.
    """
    __tablename__ = "group_daily_signals"

    id = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(
        db.String(255),
        db.ForeignKey("telegram_groups.telegram_group_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date = db.Column(db.Date, nullable=False, index=True)

    # Volume & engagement
    message_count = db.Column(db.Integer, default=0, nullable=False)
    active_members = db.Column(db.Integer, default=0, nullable=False)

    # Health scores (0–10, higher = worse for spam/conflict)
    spam_score = db.Column(db.Float, default=0.0, nullable=False)
    conflict_score = db.Column(db.Float, default=0.0, nullable=False)

    # Quality signals
    questions_unanswered = db.Column(db.Integer, default=0, nullable=False)
    top_topics = db.Column(db.JSON, default=list, nullable=False)   # list[str]

    # Computed labels
    sentiment = db.Column(db.String(20), default="neutral", nullable=False)   # positive|neutral|negative
    health_status = db.Column(db.String(20), default="healthy", nullable=False)  # healthy|watch|critical

    # AI-generated one-liner
    ai_summary = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("telegram_group_id", "date", name="uq_group_daily_signal"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "date": self.date.isoformat(),
            "message_count": self.message_count,
            "active_members": self.active_members,
            "spam_score": self.spam_score,
            "conflict_score": self.conflict_score,
            "questions_unanswered": self.questions_unanswered,
            "top_topics": self.top_topics or [],
            "sentiment": self.sentiment,
            "health_status": self.health_status,
            "ai_summary": self.ai_summary,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

class Meeting(db.Model):
    """Meeting/appointment scheduled via natural language through the assistant."""
    __tablename__ = "meetings"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False, index=True)
    timezone = db.Column(db.String(100), nullable=True, default="UTC")
    participants = db.Column(db.JSON, nullable=True)       # list of name strings
    priority = db.Column(db.String(10), default="medium", nullable=False)  # low|medium|high
    resources = db.Column(db.JSON, nullable=True)          # [{type, value, label}]
    remind_before_minutes = db.Column(db.Integer, default=15, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    is_complete = db.Column(db.Boolean, default=False, nullable=False)
    reminder_sent = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "title": self.title,
            "scheduled_at": self.scheduled_at.isoformat(),
            "timezone": self.timezone,
            "participants": self.participants or [],
            "priority": self.priority,
            "resources": self.resources or [],
            "remind_before_minutes": self.remind_before_minutes,
            "notes": self.notes,
            "is_complete": self.is_complete,
            "reminder_sent": self.reminder_sent,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AssistantConversationState(db.Model):
    """Tracks multi-turn assistant conversations (pending intent + partially collected data)."""
    __tablename__ = "assistant_conversation_states"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True)
    pending_intent = db.Column(db.String(50), nullable=True)   # schedule_meeting | add_resource
    collected_data = db.Column(db.JSON, nullable=True)          # partial fields gathered so far
    awaiting_field = db.Column(db.String(50), nullable=True)    # which field we're asking about
    expires_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class IntegrationWebhook(db.Model):
    """Outbound webhook — Telegizer POSTs event payloads to user-configured URLs.

    Supported events: meeting.created, reminder.created, resource.attached,
                      group.issue.detected
    """
    __tablename__ = "integration_webhooks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    secret = db.Column(db.String(255), nullable=True)   # stored plain; used for HMAC signing
    # JSON list of subscribed event types, e.g. ["meeting.created", "reminder.created"]
    events = db.Column(db.JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    failure_count = db.Column(db.Integer, default=0, nullable=False)
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(20), nullable=True)   # "ok" | "error"
    last_error = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self, include_secret=False):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "url": self.url,
            "secret_set": bool(self.secret),
            **({"secret": self.secret} if include_secret else {}),
            "events": self.events or [],
            "is_active": self.is_active,
            "failure_count": self.failure_count,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class UserAssistantProfile(db.Model):
    """Long-term assistant memory — learned preferences and usage patterns per user."""
    __tablename__ = "user_assistant_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Learned scheduling preferences
    preferred_meeting_hour = db.Column(db.Integer, nullable=True)   # 0-23 UTC hour most meetings scheduled
    preferred_reminder_minutes = db.Column(db.Integer, nullable=True)  # most-used lead time
    most_active_groups = db.Column(db.JSON, nullable=True)          # list of telegram_group_ids sorted by attention

    # Usage counters (used to derive preferences)
    meetings_created = db.Column(db.Integer, default=0, nullable=False)
    reminders_created = db.Column(db.Integer, default=0, nullable=False)
    notes_saved = db.Column(db.Integer, default=0, nullable=False)
    tasks_created = db.Column(db.Integer, default=0, nullable=False)

    # Aggregate hour histogram for meetings: JSON list of 24 ints
    meeting_hour_histogram = db.Column(db.JSON, nullable=True)

    # Aggregate reminder lead-time histogram: JSON dict {minutes: count}
    reminder_minutes_histogram = db.Column(db.JSON, nullable=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "preferred_meeting_hour": self.preferred_meeting_hour,
            "preferred_reminder_minutes": self.preferred_reminder_minutes,
            "most_active_groups": self.most_active_groups or [],
            "meetings_created": self.meetings_created,
            "reminders_created": self.reminders_created,
            "notes_saved": self.notes_saved,
            "tasks_created": self.tasks_created,
        }


class GoogleCalendarToken(db.Model):
    """OAuth 2.0 tokens for a user's connected Google Calendar account."""
    __tablename__ = "google_calendar_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    email = db.Column(db.String(255))
    token_json = db.Column(db.Text, nullable=False)  # Fernet-encrypted JSON token blob
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class GroupMeetingLink(db.Model):
    """Meeting/video call links captured automatically from group messages."""
    __tablename__ = "group_meeting_links"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    telegram_group_id = db.Column(db.String(255), nullable=False, index=True)
    group_title = db.Column(db.String(255), nullable=True)
    url = db.Column(db.String(2000), nullable=False)
    # zoom | meet | teams | calendly | webex | other
    platform = db.Column(db.String(30), nullable=False, default="other")
    # message excerpt that contained the link (truncated)
    context_text = db.Column(db.String(500), nullable=True)
    posted_by_username = db.Column(db.String(100), nullable=True)
    captured_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    is_dismissed = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_group_id": self.telegram_group_id,
            "group_title": self.group_title,
            "url": self.url,
            "platform": self.platform,
            "context_text": self.context_text,
            "posted_by_username": self.posted_by_username,
            "captured_at": self.captured_at.isoformat(),
            "is_dismissed": self.is_dismissed,
        }


# ── Team / Multi-user ─────────────────────────────────────────────────────────

class Team(db.Model):
    """A workspace team — one owner, multiple members sharing the same Telegizer account scope."""
    __tablename__ = "teams"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), nullable=False)
    owner_id   = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    members = db.relationship("TeamMember", backref="team", cascade="all, delete-orphan", lazy="dynamic")
    invites = db.relationship("TeamInvite", backref="team", cascade="all, delete-orphan", lazy="dynamic")

    def to_dict(self, include_members=False, include_invites=False):
        d = {
            "id": self.id,
            "name": self.name,
            "owner_id": self.owner_id,
            "created_at": self.created_at.isoformat(),
        }
        if include_members:
            d["members"] = [m.to_dict() for m in self.members.all()]
        if include_invites:
            d["pending_invites"] = [
                i.to_dict() for i in self.invites.filter_by(accepted_at=None).all()
                if i.expires_at > datetime.utcnow()
            ]
        return d


class TeamMember(db.Model):
    """Associates a user with a team and assigns them a role."""
    __tablename__ = "team_members"

    id        = db.Column(db.Integer, primary_key=True)
    team_id   = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id   = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # owner | admin | member
    role      = db.Column(db.String(20), nullable=False, default="member")
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    def to_dict(self):
        user = User.query.get(self.user_id)
        return {
            "id": self.id,
            "team_id": self.team_id,
            "user_id": self.user_id,
            "full_name": user.full_name if user else None,
            "email": user.email if user else None,
            "role": self.role,
            "joined_at": self.joined_at.isoformat(),
        }


class TeamInvite(db.Model):
    """A pending invitation for a user to join a team."""
    __tablename__ = "team_invites"

    id             = db.Column(db.Integer, primary_key=True)
    team_id        = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    invited_by_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    invited_email  = db.Column(db.String(255), nullable=False)
    role           = db.Column(db.String(20), nullable=False, default="member")
    token          = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    expires_at     = db.Column(db.DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(days=7))
    accepted_at    = db.Column(db.DateTime, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "team_id": self.team_id,
            "invited_by_id": self.invited_by_id,
            "invited_email": self.invited_email,
            "role": self.role,
            "token": self.token,
            "expires_at": self.expires_at.isoformat(),
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "created_at": self.created_at.isoformat(),
        }


# ══════════════════════════════════════════════════════════════════════════════
# Engagement Campaigns  (Engagement section → Campaigns subtab)
# ──────────────────────────────────────────────────────────────────────────────
# A single engine with campaign *types* — proof_collection / content_submission /
# social_task / giveaway. Lives ALONGSIDE the existing Raid feature (not a
# replacement). Dual-FK pattern (group_id for custom-bot lineage,
# telegram_group_id for the official-bot lineage) mirrors AutoResponse /
# KnowledgeDocument so both bot lineages share one engine. Rewards are written to
# the existing XpEvent ledger (reason="campaign:<id>"); audit reuses AuditLog.
# See ENGAGEMENT_CAMPAIGNS_PLAN.md for the full design.
# ══════════════════════════════════════════════════════════════════════════════

# Campaign type values
CAMPAIGN_TYPES = ("proof_collection", "content_submission", "social_task", "giveaway", "raid")
# Verification mode values
CAMPAIGN_VERIFICATION_MODES = ("auto", "manual", "honor", "screenshot", "link")
# Lifecycle status values
CAMPAIGN_STATUSES = ("draft", "active", "paused", "closed", "archived")
# Custom-field types
CAMPAIGN_FIELD_TYPES = ("text", "url", "uid", "wallet", "screenshot", "tx_hash", "username")


class EngagementCampaign(db.Model):
    """An engagement campaign created by a group owner/admin from the dashboard or
    Mini App. Belongs to exactly one group (the campaign id is the anchor that
    disambiguates multi-group usage on the shared official bot)."""
    __tablename__ = "engagement_campaigns"

    id = db.Column(db.Integer, primary_key=True)
    # Lineage anchors — exactly one is populated per row.
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True, index=True)            # custom-bot lineage
    telegram_group_id = db.Column(db.String(255), nullable=True, index=True)                            # official-bot lineage
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    type = db.Column(db.String(32), nullable=False, default="proof_collection")  # CAMPAIGN_TYPES
    platform = db.Column(db.String(32), nullable=True)  # x|youtube|telegram|instagram|facebook|other
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    task_url = db.Column(db.String(2000), nullable=True)
    verification_mode = db.Column(db.String(20), nullable=False, default="manual")  # CAMPAIGN_VERIFICATION_MODES

    reward_xp = db.Column(db.Integer, nullable=False, default=0)
    reward_label = db.Column(db.String(200), nullable=True)

    status = db.Column(db.String(20), nullable=False, default="draft", index=True)  # CAMPAIGN_STATUSES
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)

    max_participants = db.Column(db.Integer, nullable=True)
    one_per_user = db.Column(db.Boolean, nullable=False, default=True)

    pin_message = db.Column(db.Boolean, nullable=False, default=True)
    # The group announcement message (so the scheduler can flip its status label).
    telegram_message_id = db.Column(db.BigInteger, nullable=True)
    message_thread_id = db.Column(db.Integer, nullable=True)  # forum topic, if published into one

    # Group-post delivery tracking (so the admin can see Posted / Failed and retry).
    #   none   → never attempted (e.g. still a draft)
    #   posted → successfully sent to the group
    #   failed → last attempt errored (see post_error)
    post_status = db.Column(db.String(16), nullable=False, default="none")
    post_error = db.Column(db.Text, nullable=True)
    posted_at = db.Column(db.DateTime, nullable=True)

    # Flexible bag: verification target (e.g. channel @username for TG-join),
    # winner selections, branding overrides, etc.
    settings = db.Column(db.JSON, nullable=False, default=dict)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    custom_fields = db.relationship(
        "EngagementCustomField",
        primaryjoin="EngagementCustomField.campaign_id == EngagementCampaign.id",
        backref="campaign",
        cascade="all, delete-orphan", lazy="dynamic", order_by="EngagementCustomField.order",
    )
    tasks = db.relationship(
        "EngagementTask", backref="campaign",
        cascade="all, delete-orphan", lazy="dynamic", order_by="EngagementTask.order",
    )
    submissions = db.relationship(
        "EngagementSubmission", backref="campaign",
        cascade="all, delete-orphan", lazy="dynamic",
    )

    @property
    def is_open(self):
        """True if the campaign currently accepts submissions."""
        if self.status != "active":
            return False
        now = datetime.utcnow()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now >= self.ends_at:
            return False
        return True

    def to_dict(self, include_fields=True, include_analytics=False):
        d = {
            "id": self.id,
            "group_id": self.group_id,
            "telegram_group_id": self.telegram_group_id,
            "owner_user_id": self.owner_user_id,
            "type": self.type,
            "platform": self.platform,
            "title": self.title,
            "description": self.description,
            "task_url": self.task_url,
            "verification_mode": self.verification_mode,
            "reward_xp": self.reward_xp,
            "reward_label": self.reward_label,
            "status": self.status,
            "is_open": self.is_open,
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "max_participants": self.max_participants,
            "one_per_user": self.one_per_user,
            "pin_message": self.pin_message,
            "telegram_message_id": self.telegram_message_id,
            "message_thread_id": self.message_thread_id,
            "post_status": self.post_status or "none",
            "post_error": self.post_error,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "settings": self.settings or {},
            "created_at": self.created_at.isoformat(),
        }
        if include_fields:
            d["custom_fields"] = [f.to_dict() for f in self.custom_fields.all()]
            tasks = self.tasks.all()
            if tasks:
                d["tasks"] = [t.to_dict(include_fields=True) for t in tasks]
                d["is_multitask"] = True
        if include_analytics:
            subs = self.submissions
            d["submissions_total"] = subs.count()
            d["submissions_pending"] = subs.filter_by(status="pending").count()
            d["submissions_verified"] = subs.filter_by(status="verified").count()
            d["submissions_rejected"] = subs.filter_by(status="rejected").count()
        return d


class EngagementTask(db.Model):
    """One sub-task of a multi-task campaign. A campaign with zero tasks is a
    legacy single-task campaign (proof fields + reward live on the campaign). When
    tasks exist, each carries its own type/platform/verification/reward and proof
    fields, and submissions are tagged with task_id."""
    __tablename__ = "engagement_tasks"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer, db.ForeignKey("engagement_campaigns.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    order = db.Column(db.Integer, nullable=False, default=0)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    type = db.Column(db.String(32), nullable=False, default="social_task")  # CAMPAIGN_TYPES
    platform = db.Column(db.String(32), nullable=True)
    task_url = db.Column(db.String(2000), nullable=True)
    verification_mode = db.Column(db.String(20), nullable=False, default="manual")  # CAMPAIGN_VERIFICATION_MODES
    reward_xp = db.Column(db.Integer, nullable=False, default=0)
    reward_label = db.Column(db.String(200), nullable=True)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # A task owns its proof fields (campaign_id stays NULL on these rows).
    custom_fields = db.relationship(
        "EngagementCustomField",
        primaryjoin="EngagementCustomField.task_id == EngagementTask.id",
        cascade="all, delete-orphan", lazy="dynamic",
        order_by="EngagementCustomField.order",
    )

    def to_dict(self, include_fields=True):
        d = {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "order": self.order,
            "title": self.title,
            "description": self.description,
            "type": self.type,
            "platform": self.platform,
            "task_url": self.task_url,
            "verification_mode": self.verification_mode,
            "reward_xp": self.reward_xp,
            "reward_label": self.reward_label,
            "settings": self.settings or {},
        }
        if include_fields:
            d["custom_fields"] = [f.to_dict() for f in self.custom_fields.all()]
        return d


class EngagementCustomField(db.Model):
    """A typed proof field on a campaign OR a task (e.g. exchange UID, wallet,
    screenshot). Exactly one of campaign_id / task_id is set: campaign_id for a
    legacy campaign-level field, task_id for a multi-task field."""
    __tablename__ = "engagement_custom_fields"

    id = db.Column(db.Integer, primary_key=True)
    # Nullable since a field may instead belong to a task (task_id set). Legacy
    # campaign-level fields keep campaign_id set and task_id NULL.
    campaign_id = db.Column(
        db.Integer, db.ForeignKey("engagement_campaigns.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    task_id = db.Column(
        db.Integer, db.ForeignKey("engagement_tasks.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    key = db.Column(db.String(64), nullable=False)        # machine key, unique within a campaign
    label = db.Column(db.String(200), nullable=False)     # human prompt shown to the user
    field_type = db.Column(db.String(20), nullable=False, default="text")  # CAMPAIGN_FIELD_TYPES
    required = db.Column(db.Boolean, nullable=False, default=True)
    order = db.Column(db.Integer, nullable=False, default=0)
    # Optional example / format hint shown to the user when asking for this proof
    # (e.g. "Example: 123456789 or ABC123"). Structure already supports making
    # this required-with-pattern later.
    example = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "task_id": self.task_id,
            "key": self.key,
            "label": self.label,
            "field_type": self.field_type,
            "required": self.required,
            "order": self.order,
            "example": self.example,
        }


class EngagementSubmission(db.Model):
    """A user's submission/proof for a campaign. One-per-user is enforced in
    application logic (not a hard DB unique constraint) so that campaigns with
    one_per_user=False can accept multiple submissions; the composite index keeps
    the dedup lookup fast."""
    __tablename__ = "engagement_submissions"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer, db.ForeignKey("engagement_campaigns.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Set when the submission is for a sub-task of a multi-task campaign; NULL for
    # legacy single-task campaigns.
    task_id = db.Column(
        db.Integer, db.ForeignKey("engagement_tasks.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    telegram_user_id = db.Column(db.String(64), nullable=False, index=True)
    telegram_username = db.Column(db.String(255), nullable=True)
    # PK of Member (scope='custom') or OfficialMember (scope='official'); for reward attribution.
    member_id = db.Column(db.Integer, nullable=True)
    scope = db.Column(db.String(16), nullable=False, default="custom")  # custom | official

    status = db.Column(db.String(16), nullable=False, default="pending")  # pending|verified|rejected
    payload = db.Column(db.JSON, nullable=False, default=dict)            # {field_key: value}
    file_id = db.Column(db.String(255), nullable=True)                    # Telegram file_id (screenshot)
    file_hash = db.Column(db.String(64), nullable=True, index=True)       # for screenshot dedup

    reviewed_by = db.Column(db.String(64), nullable=True)
    review_reason = db.Column(db.Text, nullable=True)
    rewarded = db.Column(db.Boolean, nullable=False, default=False)       # idempotency guard for XP

    # Anti-fraud: set when a duplicate value/screenshot is detected (Phase 6).
    flagged = db.Column(db.Boolean, nullable=False, default=False)
    flag_reason = db.Column(db.String(255), nullable=True)

    # Result of the post-review DM we try to send the participant.
    #   none → not attempted, sent → delivered, failed → user blocked / never started.
    notify_status = db.Column(db.String(16), nullable=False, default="none")
    notify_error = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index("ix_engagement_submissions_campaign_user", "campaign_id", "telegram_user_id"),
        db.Index("ix_engagement_submissions_campaign_status", "campaign_id", "status"),
        db.Index("ix_engagement_submissions_campaign_task_user", "campaign_id", "task_id", "telegram_user_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "task_id": self.task_id,
            "telegram_user_id": self.telegram_user_id,
            "telegram_username": self.telegram_username,
            "member_id": self.member_id,
            "scope": self.scope,
            "status": self.status,
            "payload": self.payload or {},
            "file_id": self.file_id,
            "file_hash": self.file_hash,
            "reviewed_by": self.reviewed_by,
            "review_reason": self.review_reason,
            "rewarded": self.rewarded,
            "flagged": self.flagged,
            "flag_reason": self.flag_reason,
            "notify_status": self.notify_status or "none",
            "notify_error": self.notify_error,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }
