import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "fallback-secret-key-change-in-production")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "fallback-jwt-secret-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = False

    raw_db_url = os.environ.get("DATABASE_URL", "sqlite:///telegram_saas.db")
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "")
    STRIPE_ENTERPRISE_PRICE_ID = os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", "")

    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    FROM_EMAIL = os.environ.get("FROM_EMAIL", "noreply@example.com")

    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    _admin_env = os.environ.get("ADMIN_EMAILS", "")
    _default_admins = ["fazalelahi5577@gmail.com"]
    ADMIN_EMAILS = list({e.strip() for e in _admin_env.split(",") if e.strip()} | set(_default_admins))

    MAX_BOTS = {
        "free": 1,
        "pro": 5,
        "enterprise": 50,
    }

    PLANS = {
        "free": {
            "name": "Free",
            "price": 0,
            "max_bots": 1,
            "features": ["1 bot", "1 group per bot", "Basic moderation", "Welcome messages"],
        },
        "pro": {
            "name": "Pro",
            "price": 1900,
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
            "price": 7900,
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
