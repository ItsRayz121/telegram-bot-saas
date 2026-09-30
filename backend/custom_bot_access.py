"""Who may CREATE a custom (bring-your-own-token) bot.

Every signup gets a 14-day Pro trial, and Pro allows 3 custom bots, so any
new account could spin up dedicated bot pollers at our cost. Trials now get all
Pro features EXCEPT creating custom bots. Access needs one of:
  * a paid Pro / Enterprise plan, or
  * an admin-granted custom-bot trial (User.custom_bot_trial_ends_at), 1 bot.

Only creation is gated. Bots that already exist keep running until their own
tier-expiry lifecycle pauses them.

Kill switch: CUSTOM_BOT_TRIAL_GATE_ENABLED=0 restores the old tier-only rule.
"""
import os
from datetime import datetime

from .config import Config

TRIAL_DAYS = 14
GRANTED_TRIAL_MAX_BOTS = 1


def gate_enabled() -> bool:
    return os.environ.get("CUSTOM_BOT_TRIAL_GATE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def is_on_free_trial(user, now=None) -> bool:
    """Pro via the signup trial, i.e. nothing has been paid."""
    now = now or datetime.utcnow()
    return bool(
        user.subscription_tier == "pro"
        and user.subscription_expires is None
        and user.trial_ends_at is not None
        and user.trial_ends_at > now
    )


def has_granted_trial(user, now=None) -> bool:
    now = now or datetime.utcnow()
    end = getattr(user, "custom_bot_trial_ends_at", None)
    return bool(end and end > now)


def custom_bot_allowance(user, now=None):
    """Return (max_bots, reason). reason: paid | granted_trial | free_trial | free | gate_off."""
    now = now or datetime.utcnow()
    tier_max = Config.MAX_CUSTOM_BOTS.get(user.subscription_tier, 0)
    if not gate_enabled():
        return tier_max, "gate_off"
    if is_on_free_trial(user, now):
        if has_granted_trial(user, now):
            return GRANTED_TRIAL_MAX_BOTS, "granted_trial"
        return 0, "free_trial"
    if tier_max > 0:
        return tier_max, "paid"
    if has_granted_trial(user, now):
        return GRANTED_TRIAL_MAX_BOTS, "granted_trial"
    return 0, "free"


def denial_message(reason: str) -> str:
    if reason == "free_trial":
        return ("Custom bots aren't included in the free trial. Upgrade to Pro to connect your own "
                "bot token, or contact support to request a custom-bot trial for your community.")
    return "Custom bots are available on Pro/Enterprise plans. Upgrade to connect your own bot token."
