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

    # Access tokens expire after 7 days. Reduces compromise window vs 30-day default.
    # Logout uses a Redis jti blocklist; see routes/auth.py /logout endpoint.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ["access"]

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

    # Stripe (kept for legacy/future use — not active)
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "")
    STRIPE_ENTERPRISE_PRICE_ID = os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", "")

    # Lemon Squeezy (card / bank payments)
    LS_API_KEY = os.environ.get("LS_API_KEY", "")
    LS_STORE_ID = os.environ.get("LS_STORE_ID", "")
    LS_PRO_VARIANT_ID = os.environ.get("LS_PRO_VARIANT_ID", "")
    LS_ENTERPRISE_VARIANT_ID = os.environ.get("LS_ENTERPRISE_VARIANT_ID", "")
    LS_WEBHOOK_SECRET = os.environ.get("LS_WEBHOOK_SECRET", "")

    # NOWPayments (crypto — USDT, BTC, ETH, etc.)
    NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "")
    NOWPAYMENTS_IPN_SECRET = os.environ.get("NOWPAYMENTS_IPN_SECRET", "")
    BACKEND_URL = os.environ.get("BACKEND_URL", "https://api.telegizer.xyz")

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

    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    # Official Telegizer shared bot (serves all users/groups)
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "telegizer_bot")
    _admin_env = os.environ.get("ADMIN_EMAILS", "")
    ADMIN_EMAILS = [e.strip() for e in _admin_env.split(",") if e.strip()]
    if not ADMIN_EMAILS:
        _log.warning(
            "ADMIN_EMAILS env var is not set — no accounts will have admin access. "
            "Set ADMIN_EMAILS=you@example.com in your Railway environment."
        )

    # Max custom bots per user (Bot model — bring-your-own running bots)
    MAX_BOTS = {
        "free": 1,
        "pro": 5,
        "enterprise": 50,
    }

    # Max bring-your-own-token custom bots (CustomBot model — token stored, not running)
    MAX_CUSTOM_BOTS = {
        "free": 0,
        "pro": 2,
        "enterprise": 10,
    }

    # Max official-bot linked groups per user (TelegramGroup model)
    # -1 = unlimited
    MAX_OFFICIAL_GROUPS = {
        "free": 3,
        "pro": -1,
        "enterprise": -1,
    }

    # Version string surfaced by /health — update on each deploy to aid debugging
    VERSION = os.environ.get("APP_VERSION", "2026-04-27-v1")

    PLANS = {
        "free": {
            "name": "Free",
            "price": 0,
            "max_bots": 1,
            "features": ["1 bot", "1 group per bot", "Basic moderation", "Welcome messages"],
        },
        "pro": {
            "name": "Pro",
            "price": 900,
            "price_annual": 9000,
            "max_bots": 5,
            "features": [
                "5 bots",
                "Unlimited groups",
                "Advanced moderation",
                "Verification system",
                "Scheduled messages",
                "XP & levels",
                "Analytics",
                "Priority support",
            ],
        },
        "enterprise": {
            "name": "Enterprise",
            "price": 4900,
            "price_annual": 47000,
            "max_bots": 50,
            "features": [
                "50 bots",
                "Unlimited groups",
                "All Pro features",
                "Raid coordinator",
                "Custom branding",
                "API access",
                "Dedicated support",
                "SLA guarantee",
            ],
        },
    }
