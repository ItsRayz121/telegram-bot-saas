"""Stop polling bots whose Telegram token is rejected.

A revoked / regenerated / typo'd token makes Telegram answer 401 on every call.
Retrying forever burns a thread, a DB connection and API calls for nothing, and
the watchdog used to restart the dead thread on every tick. After a handful of
consecutive rejections the bot is taken offline (``Bot.is_active = False``) so
neither the poller, the boot-time restart nor the watchdog touches it again
until its owner re-enables it.

Kill switch: BOT_TOKEN_AUTO_OFFLINE=0 keeps the retry cap but leaves the bot
flagged active in the database (the old behaviour).
"""
import logging
import os

logger = logging.getLogger(__name__)

# Consecutive token rejections tolerated before the bot is taken offline.
TOKEN_REJECT_LIMIT = 5
# Seconds to wait after the Nth consecutive rejection (guards against a single
# transient 401 from Telegram without hammering it).
_BACKOFF = (10, 20, 40, 60)


def is_token_rejection(exc: BaseException) -> bool:
    """True when Telegram rejected the bot token itself (not a network error).

    python-telegram-bot >= 20 raises ``InvalidToken``; older releases raised
    ``Unauthorized``. Matching by class name keeps this working on either, and
    never depends on an import that may not exist.
    """
    return any(c.__name__ in ("InvalidToken", "Unauthorized") for c in type(exc).__mro__)


def backoff_seconds(rejections: int) -> int:
    """Wait before retry number ``rejections`` (1-based)."""
    return _BACKOFF[min(max(rejections, 1), len(_BACKOFF)) - 1]


def auto_offline_enabled() -> bool:
    return os.environ.get("BOT_TOKEN_AUTO_OFFLINE", "1").strip() != "0"


def mark_bot_offline(flask_app, bot_id: int, detail: str) -> bool:
    """Flag the bot (and its custom-bot twin) offline. Never raises."""
    if not auto_offline_enabled():
        return False
    try:
        with flask_app.app_context():
            from .models import Bot, CustomBot, db

            bot = Bot.query.get(bot_id)
            if bot is None:
                return False
            bot.is_active = False
            twin = None
            if bot.bot_username:
                twin = CustomBot.query.filter_by(
                    owner_user_id=bot.user_id, bot_username=bot.bot_username
                ).first()
            if twin is not None and twin.status == "active":
                twin.status = "error"
            db.session.commit()
            logger.warning("Bot %s taken offline: %s", bot_id, detail)
            return True
    except Exception:
        logger.exception("Could not mark bot %s offline", bot_id)
        try:
            from .models import db
            db.session.rollback()
        except Exception:
            pass
        return False
