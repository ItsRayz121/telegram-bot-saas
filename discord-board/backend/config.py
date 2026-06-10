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

    # Database (own DB — never shared with Telegizer)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///instance/guildizer.db")

    # App
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    PORT = int(os.getenv("PORT", "5000"))

    @classmethod
    def require_bot_token(cls) -> str:
        if not cls.DISCORD_BOT_TOKEN:
            raise RuntimeError(
                "DISCORD_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
            )
        return cls.DISCORD_BOT_TOKEN
