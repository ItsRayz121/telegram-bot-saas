"""Plans, pricing, and Pro activation for Guildizer.

One paid tier (Pro). The product decision (see project notes): we monetize
engagement — unlimited active campaigns + per-campaign leaderboards — and never
paywall safety/moderation. No discord.py; no Flask. Activation is shared by the
checkout flow and the IPN webhook.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from config import Config


def pricing() -> dict:
    return {
        "pro": {
            "name": "Pro",
            "price_usd": Config.PRO_PRICE_USD,
            "period_days": Config.PRO_PERIOD_DAYS,
            "features": [
                "Unlimited active campaigns",
                "Per-campaign leaderboards",
                "Priority support",
            ],
        }
    }


def activate_pro(db, guild, subscription) -> None:
    """Flip a guild to Pro and stamp the subscription as active. Caller commits."""
    now = datetime.utcnow()
    period = subscription.period_days or Config.PRO_PERIOD_DAYS
    # Extend from the later of now or current expiry (so re-ups stack).
    base = guild.plan_expires_at if (guild.plan_expires_at and guild.plan_expires_at > now) else now
    expires = base + timedelta(days=period)

    guild.plan = "pro"
    guild.plan_expires_at = expires
    subscription.status = "active"
    subscription.activated_at = now
    subscription.expires_at = expires


def expire_if_due(db, guild) -> bool:
    """Downgrade a guild whose Pro period has lapsed. Returns True if changed."""
    if guild.plan == "pro" and guild.plan_expires_at and guild.plan_expires_at < datetime.utcnow():
        guild.plan = "free"
        return True
    return False
