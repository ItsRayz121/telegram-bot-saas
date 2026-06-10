"""Guildizer configuration — loads from environment only. No Telegizer coupling."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Discord
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
    DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
    DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
    DISCORD_REDIRECT_URI = os.getenv(
        "DISCORD_REDIRECT_URI", "http://localhost:5000/auth/discord/callback"
    )
    # Permission bitfield requested when inviting the bot to a server.
    # Empty -> a sensible default computed in discord_api.bot_invite_permissions().
    DISCORD_BOT_PERMISSIONS = os.getenv("DISCORD_BOT_PERMISSIONS", "")

    # Database (own DB — never shared with Telegizer)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///instance/guildizer.db")

    # App
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000")
    PORT = int(os.getenv("PORT", "5000"))

    # Session cookie. In production (cross-site frontend/api domains) set
    # SESSION_COOKIE_SECURE=true and SESSION_COOKIE_SAMESITE=None.
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "guildizer_session")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", str(60 * 60 * 24 * 14)))  # 14 days

    @classmethod
    def require_bot_token(cls) -> str:
        if not cls.DISCORD_BOT_TOKEN:
            raise RuntimeError(
                "DISCORD_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
            )
        return cls.DISCORD_BOT_TOKEN
