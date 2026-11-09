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
import contextvars
import logging
import os

logger = logging.getLogger(__name__)

RANK_COMMANDS = {"rank", "xp", "me", "leaderboard", "top"}
SKIP_COMMANDS = {"start", "linkgroup", "warn", "ban", "kick", "mute", "unmute", "tempban",
                 "tempmute", "purge", "removewarning", "unwarn"}
MAX_SECONDS = 3600
_REPLY_METHODS = ("reply_text", "reply_html", "reply_markdown", "reply_photo", "reply_animation",
                  "reply_document", "reply_video", "reply_sticker", "reply_audio", "reply_voice",
                  "reply_poll", "reply_dice", "reply_location", "reply_contact", "reply_media_group")
# Bot.send_* calls made while a command handler runs (bots that answer with bot.send_message).
_SEND_METHODS = ("send_message", "send_photo", "send_animation", "send_document", "send_video",
                 "send_sticker", "send_audio", "send_voice", "send_poll", "send_dice",
                 "send_location", "send_contact", "send_media_group")
COMMAND_ONLY_DELAY = 10   # the member's /command is removed after this long when no reply delay is set

_state = {"app": None, "installed": False}
# The command currently being handled. Set only INSIDE CommandHandler.handle_update and reset right
# after, so it can never leak into another update (welcome messages, warnings, ...).
_current = contextvars.ContextVar("command_cleanup_current", default=None)


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


def _ids_of(sent):
    items = sent if isinstance(sent, (list, tuple)) else [sent]
    return [m.message_id for m in items if getattr(m, "message_id", None) is not None]


def _schedule(bot, chat_id, ids, seconds, state=None):
    """Delete `ids` after `seconds`, once each (ids already scheduled for this command are skipped)."""
    if state is not None:
        ids = [i for i in ids if i not in state["scheduled"]]
        state["scheduled"].update(ids)
    if ids and seconds > 0:
        asyncio.ensure_future(_delete_later(bot, chat_id, ids, seconds))


async def after_reply(command_message, sent):
    """Called after a Message.reply_* returned. Never raises."""
    try:
        if not enabled() or sent is None:
            return
        state = _current.get()
        if state is not None and state["chat_id"] == command_message.chat.id:
            return  # the Bot.send_* hook inside the running command handler already took care of it
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
        ids = _ids_of(sent)
        if delete_command:
            ids.append(command_message.message_id)
        _schedule(command_message.get_bot(), chat.id, ids, seconds)
    except Exception:
        logger.debug("command cleanup skipped", exc_info=True)


async def _begin(update):
    """State for the command this update carries, or None when nothing should be cleaned."""
    if not enabled():
        return None
    msg = getattr(update, "effective_message", None)
    chat = getattr(msg, "chat", None)
    if msg is None or getattr(chat, "type", None) not in ("group", "supergroup"):
        return None
    command = command_name(getattr(msg, "text", None))
    if command is None:
        return None
    seconds, delete_command = delays_from_settings(
        await asyncio.to_thread(_auto_clean_for_chat, chat.id), command)
    if seconds <= 0 and not delete_command:
        return None
    state = {"chat_id": chat.id, "seconds": seconds, "scheduled": set()}
    if delete_command:  # works even when the command produces no reply of its own
        _schedule(msg.get_bot(), chat.id, [msg.message_id], seconds or COMMAND_ONLY_DELAY, state)
    return state


def _install_command_scope(handler_cls):
    original = handler_cls.handle_update

    async def handle_update(self, update, *args, **kwargs):
        token = None
        try:
            state = await _begin(update)
            if state is not None:
                token = _current.set(state)
        except Exception:
            logger.debug("command cleanup skipped", exc_info=True)
        try:
            return await original(self, update, *args, **kwargs)
        finally:
            if token is not None:
                _current.reset(token)

    handler_cls.handle_update = handle_update


def _install_send_hooks(bot_cls):
    for name in _SEND_METHODS:
        original = getattr(bot_cls, name, None)
        if original is None:
            continue

        def make(orig):
            async def wrapper(self, *args, **kwargs):
                sent = await orig(self, *args, **kwargs)
                try:
                    state = _current.get()
                    if state is not None and state["seconds"] > 0 and sent is not None:
                        chat_id = kwargs.get("chat_id", args[0] if args else None)
                        if str(chat_id) == str(state["chat_id"]):
                            _schedule(self, state["chat_id"], _ids_of(sent), state["seconds"], state)
                except Exception:
                    logger.debug("command cleanup skipped", exc_info=True)
                return sent
            wrapper.__name__ = getattr(orig, "__name__", name)
            return wrapper

        setattr(bot_cls, name, make(original))


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
    if message_cls.__module__.startswith("telegram"):  # real PTB only; tests pass a fake Message
        try:
            from telegram import Bot
            from telegram.ext import CommandHandler
            _install_command_scope(CommandHandler)
            _install_send_hooks(Bot)
        except Exception:
            logger.exception("command cleanup: could not install the command scope")
    _state["installed"] = True
