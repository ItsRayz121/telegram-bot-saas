"""
Resolve which live bot (+ its asyncio loop) manages a given Telegram chat.

The approval/deferred forwarding path runs in a Flask request thread and must
hand work to the correct bot's event loop — the OFFICIAL bot for official-lineage
groups, or the OWNING custom bot for custom-lineage groups. This mirrors the
lineage resolution already used by engagement_telegram._resolve_target.

Returns (bot, loop) or (None, None) when no live bot is available.
"""
import logging

_log = logging.getLogger(__name__)


def resolve_bot_loop_for_chat(chat_id):
    """Return (bot, loop) for the bot that manages `chat_id`, or (None, None).

    Custom-lineage groups live in the `Group` model (keyed by telegram_group_id)
    and run under bot_manager; everything else falls back to the official bot.
    """
    chat_key = str(chat_id)

    # ── Custom lineage: a Group row whose bot is currently running ──
    try:
        from ..models import Group
        group = Group.query.filter_by(telegram_group_id=chat_key).first()
        if group and group.bot_id:
            from ..app import bot_manager
            with bot_manager._lock:
                instance = bot_manager.active_bots.get(group.bot_id)
            if (instance and instance.application and instance.loop
                    and instance.loop.is_running()):
                return instance.application.bot, instance.loop
    except Exception as exc:  # noqa: BLE001
        _log.debug("resolve_bot_loop_for_chat: custom lookup failed for %s: %s",
                   chat_key, exc)

    # ── Official lineage (default) ──
    try:
        from ..official_bot import get_official_bot_loop
        bot, loop = get_official_bot_loop()
        if bot and loop and loop.is_running():
            return bot, loop
    except Exception as exc:  # noqa: BLE001
        _log.debug("resolve_bot_loop_for_chat: official lookup failed: %s", exc)

    return None, None
