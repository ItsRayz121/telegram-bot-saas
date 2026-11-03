"""Auto-delete the bot's replies to member commands (/rank, /leaderboard, /help ...).

One shared hook for the official bot and every custom bot: the reply methods of
telegram.Message are wrapped once, and after a command in a group is answered the reply
(and optionally the member's command message) is deleted after a delay the group chose.

Settings (group settings -> auto_clean; 0 / missing = keep, i.e. behaviour is unchanged):
  command_reply_delete_seconds   delay for replies to any command
  rank_reply_delete_seconds      delay for /rank /xp /me /leaderboard /top (falls back to the above)
  delete_commands                also remove the member's own command message (existing switch)

Moderation commands already clean up through moderation.auto_delete_action_seconds, and
/start /linkgroup are setup flows, so those are never touched here.

Kill switch: env COMMAND_AUTODELETE_ENABLED=0 stops every deletion at once, no deploy.
"""
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

RANK_COMMANDS = {"rank", "xp", "me", "leaderboard", "top"}
SKIP_COMMANDS = {"start", "linkgroup", "warn", "ban", "kick", "mute", "unmute", "tempban",
                 "tempmute", "purge", "removewarning", "unwarn"}
MAX_SECONDS = 3600
_REPLY_METHODS = ("reply_text", "reply_html", "reply_markdown", "reply_photo")

_state = {"app": None, "installed": False}


def enabled() -> bool:
    return os.environ.get("COMMAND_AUTODELETE_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


def command_name(text):
    """'/rank@MyBot extra' -> 'rank'; None when the text is not a command."""
    if not text or not text.startswith("/"):
        return None
    parts = text[1:].split()
    return parts[0].split("@")[0].lower() or None if parts else None


def delays_from_settings(auto_clean, command):
    """(reply_seconds, delete_command_too) for a command given a group's auto_clean settings."""
    if command is None or command in SKIP_COMMANDS or not isinstance(auto_clean, dict):
        return 0, False
    generic = _seconds(auto_clean.get("command_reply_delete_seconds"))
    seconds = generic
    if command in RANK_COMMANDS:
        seconds = _seconds(auto_clean.get("rank_reply_delete_seconds")) or generic
    return seconds, bool(auto_clean.get("delete_commands"))


def _seconds(value):
    try:
        return max(0, min(int(value or 0), MAX_SECONDS))
    except (TypeError, ValueError):
        return 0


def _auto_clean_for_chat(chat_id):
    app = _state["app"]
    if app is None:
        return {}
    gid = str(chat_id)
    with app.app_context():
        from .models import TelegramGroup, Group
        row = TelegramGroup.query.filter_by(telegram_group_id=gid).first()
        if row is None:
            row = Group.query.filter_by(telegram_group_id=gid).first()
        settings = getattr(row, "settings", None) or {}
        return dict(settings.get("auto_clean") or {})


async def _delete_later(bot, chat_id, message_ids, seconds):
    await asyncio.sleep(seconds)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass  # already gone, or the bot lacks the delete right: nothing to do


async def after_reply(command_message, sent):
    """Called after a Message.reply_* returned. Never raises."""
    try:
        if not enabled() or sent is None:
            return
        chat = getattr(command_message, "chat", None)
        if getattr(chat, "type", None) not in ("group", "supergroup"):
            return
        command = command_name(getattr(command_message, "text", None))
        if command is None:
            return
        seconds, delete_command = delays_from_settings(
            await asyncio.to_thread(_auto_clean_for_chat, chat.id), command)
        if seconds <= 0:
            return
        ids = [sent.message_id]
        if delete_command:
            ids.append(command_message.message_id)
        asyncio.ensure_future(_delete_later(command_message.get_bot(), chat.id, ids, seconds))
    except Exception:
        logger.debug("command cleanup skipped", exc_info=True)


def install(flask_app, message_cls=None):
    """Wrap the reply methods once per process. Safe to call from every bot."""
    if flask_app is not None and _state["app"] is None:
        _state["app"] = flask_app
    if _state["installed"]:
        return
    if message_cls is None:
        from telegram import Message as message_cls
    for name in _REPLY_METHODS:
        original = getattr(message_cls, name, None)
        if original is None:
            continue

        def make(orig):
            async def wrapper(self, *args, **kwargs):
                sent = await orig(self, *args, **kwargs)
                # Background: the settings lookup must never delay the reply itself.
                asyncio.ensure_future(after_reply(self, sent))
                return sent
            wrapper.__name__ = getattr(orig, "__name__", "reply")
            return wrapper

        setattr(message_cls, name, make(original))
    _state["installed"] = True
