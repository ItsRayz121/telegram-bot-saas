import os
import logging as _logging
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

_log = _logging.getLogger(__name__)


class Config:
    _secret_key = os.environ.get("SECRET_KEY")
    if not _secret_key:
        raise RuntimeError(
            "SECRET_KEY environment variable is required and must not be empty. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    SECRET_KEY = _secret_key

    _jwt_secret_key = os.environ.get("JWT_SECRET_KEY")
    if not _jwt_secret_key:
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is required and must not be empty. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    JWT_SECRET_KEY = _jwt_secret_key

    # Dedicated encryption key for bot tokens and other sensitive field encryption.
    # Must be separate from SECRET_KEY so Flask session security and field encryption
    # can be rotated independently.
    # Migration path: set ENCRYPTION_KEY_OLD to your current SECRET_KEY value,
    # then set ENCRYPTION_KEY to a new dedicated secret.  Existing encrypted records
    # decrypt via the old key and are re-encrypted on next save.
    _enc_key = os.environ.get("ENCRYPTION_KEY")
    if not _enc_key:
        raise RuntimeError(
            "ENCRYPTION_KEY environment variable is required for token encryption. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "Set ENCRYPTION_KEY_OLD to your current SECRET_KEY value to keep existing "
            "encrypted records working during the transition."
        )
    ENCRYPTION_KEY = _enc_key

    # Access tokens expire after 1 day; refresh tokens last 30 days.
    # On 401, the frontend auto-refreshes using the refresh token.
    # Logout revokes both via the Redis jti blocklist.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ["access", "refresh"]

    raw_db_url = os.environ.get("DATABASE_URL", "sqlite:///telegram_saas.db")
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # NOWPayments (crypto — USDT, BTC, ETH, etc.)
    NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "")
    NOWPAYMENTS_IPN_SECRET = os.environ.get("NOWPAYMENTS_IPN_SECRET", "")

    # Lemon Squeezy (card payments — 1-H-01)
    LS_API_KEY                      = os.environ.get("LS_API_KEY", "")
    LS_STORE_ID                     = os.environ.get("LS_STORE_ID", "")
    LS_WEBHOOK_SECRET               = os.environ.get("LS_WEBHOOK_SECRET", "")
    LS_PRO_MONTHLY_VARIANT_ID       = os.environ.get("LS_PRO_MONTHLY_VARIANT_ID", "")
    LS_PRO_YEARLY_VARIANT_ID        = os.environ.get("LS_PRO_YEARLY_VARIANT_ID", "")
    LS_ENTERPRISE_MONTHLY_VARIANT_ID = os.environ.get("LS_ENTERPRISE_MONTHLY_VARIANT_ID", "")
    LS_ENTERPRISE_YEARLY_VARIANT_ID  = os.environ.get("LS_ENTERPRISE_YEARLY_VARIANT_ID", "")
    BACKEND_URL = os.environ.get("BACKEND_URL", "https://api.telegizer.com")

    # Email provider: "resend" (preferred) or "smtp"
    EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "")
    # Resend (https://resend.com) — set EMAIL_PROVIDER=resend
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    FROM_EMAIL = os.environ.get("FROM_EMAIL", "noreply@example.com")
    # SMTP fallback — set EMAIL_PROVIDER=smtp
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

    # In production (PostgreSQL) email must be configured — users cannot verify
    # their email address or reset passwords without it.
    _is_prod = "postgres" in os.environ.get("DATABASE_URL", "")
    if _is_prod and not EMAIL_PROVIDER:
        raise RuntimeError(
            "EMAIL_PROVIDER environment variable is required in production. "
            "Set EMAIL_PROVIDER=resend (or smtp) and the matching credentials "
            "(RESEND_API_KEY / SMTP_* vars) in your Railway environment."
        )

    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    # In production, FRONTEND_URL pointing to localhost breaks all email links.
    if _is_prod and ("localhost" in FRONTEND_URL or "127.0.0.1" in FRONTEND_URL):
        raise RuntimeError(
            f"FRONTEND_URL is set to '{FRONTEND_URL}' but DATABASE_URL points to PostgreSQL. "
            "Set FRONTEND_URL=https://your-domain.com in your Railway environment."
        )
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    # Platform-wide Gemini key (kept for user workspace keys; not used as platform primary).
    PLATFORM_GEMINI_API_KEY = os.environ.get("PLATFORM_GEMINI_API_KEY", "")

    # OpenRouter — primary platform AI key.
    PLATFORM_OPENROUTER_API_KEY = os.environ.get("PLATFORM_OPENROUTER_API_KEY", "")

    # Daily platform AI spend cap in USD. When exceeded, platform-key AI calls are
    # blocked until midnight UTC. Users with their own API key are unaffected.
    MAX_DAILY_AI_SPEND_USD = float(os.environ.get("MAX_DAILY_AI_SPEND_USD", "50"))


    # Official Telegizer shared bot (serves all users/groups)
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "telegizer_bot")
    _admin_env = os.environ.get("ADMIN_EMAILS", "")
    ADMIN_EMAILS = [e.strip().lower() for e in _admin_env.split(",") if e.strip()]

    # Set to "true" to require admin accounts to have TOTP/2FA before accessing /api/admin/*.
    # Defaults to False so sole-admin setups are not locked out.
    ENFORCE_ADMIN_2FA = os.environ.get("ENFORCE_ADMIN_2FA", "false").lower() == "true"
    if _is_prod and not ENFORCE_ADMIN_2FA:
        _log.warning(
            "ENFORCE_ADMIN_2FA is not enabled in production. "
            "Admin accounts can be accessed without 2FA — set ENFORCE_ADMIN_2FA=true "
            "in your Railway environment after ensuring all admin accounts have TOTP enabled."
        )
    if not ADMIN_EMAILS:
        if _is_prod:
            raise RuntimeError(
                "ADMIN_EMAILS environment variable is required in production. "
                "Set ADMIN_EMAILS=you@example.com (comma-separated) in your Railway environment. "
                "Without this, nobody can access the admin panel."
            )
        _log.warning(
            "ADMIN_EMAILS env var is not set — no accounts will have admin access. "
            "Set ADMIN_EMAILS=you@example.com in your Railway environment."
        )

    # Max custom bots per user (Bot model — bring-your-own running bots)
    MAX_BOTS = {
        "free": 1,
        "pro": 3,
        "enterprise": 50,
    }

    # Max bring-your-own-token custom bots (CustomBot model — token stored, not running)
    MAX_CUSTOM_BOTS = {
        "free": 1,
        "pro": 3,
        "enterprise": 50,
    }

    # Max groups per custom bot — -1 = unlimited
    # Free users hit the limit at 3 groups/bot → natural upgrade trigger.
    # Official @telegizer_bot groups are always unlimited (drives brand reach).
    MAX_GROUPS_PER_CUSTOM_BOT = {
        "free": 3,
        "pro": -1,
        "enterprise": -1,
    }

    # Max official-bot linked groups per user (TelegramGroup model) — always unlimited
    MAX_OFFICIAL_GROUPS = {
        "free": -1,
        "pro": -1,
        "enterprise": -1,
    }

    # AI token daily budgets (platform Gemini key)
    AI_TOKEN_LIMITS = {
        "free": 10_000,
        "pro": 500_000,
        "enterprise": 500_000,
    }

    # Version string surfaced by /health — update on each deploy to aid debugging
    VERSION = os.environ.get("APP_VERSION", "2026-05-01-v2")

    PLANS = {
        "free": {
            "name": "Free",
            "price": 0,
            "max_bots": 1,
            "ai_tokens_day": 10_000,
            "features": [
                "1 custom bot",
                "Unlimited groups",
                "Welcome messages",
                "Basic moderation",
                "Verification system",
                "XP & levels",
                "Scheduled messages",
                "10k AI credits / day",
            ],
        },
        "pro": {
            "name": "Pro",
            "price": 900,          # $9/mo in cents
            "price_annual": 8640,  # $86.40/yr (~$7.20/mo, save ~20%)
            "max_bots": 3,
            "ai_tokens_day": 500_000,
            "features": [
                "3 custom bots",
                "Unlimited groups",
                "Everything in Free",
                "AI Auto-Reply (knowledge base Q&A)",
                "AI Group Digests (daily/weekly)",
                "AI Assistant Hub (notes, tasks, queries)",
                "500k AI credits / day",
                "Bring your own AI API key",
                "Advanced analytics (90 days)",
                "Message forwarding & automations",
                "Webhook integrations",
                "Member CRM",
                "Priority support",
            ],
        },
        "enterprise": {
            "name": "Enterprise",
            "price": 4900,         # $49/mo in cents
            "price_annual": 47040, # $392/yr (~$32.67/mo, save ~33%)
            "max_bots": 50,
            "ai_tokens_day": 500_000,
            "features": [
                "50 custom bots",
                "Unlimited groups",
                "Everything in Pro",
                "White-label custom bots",
                "Full REST API access",
                "Bulk group operations",
                "Advanced member CRM",
                "Raid coordinator",
                "Marketplace access",
                "Dedicated support channel",
                "SLA guarantee",
                "Custom integrations",
            ],
        },
    }
