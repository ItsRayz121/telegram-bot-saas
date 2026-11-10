"""Per-command cleanup of command messages and the bot's replies (Telegram).

One shared hook for the official bot and every custom bot. Each group has a command table
(group settings -> command_table) with one independent row per command:

    {"xp": {"delete_command": true, "delete_reply": true, "seconds": 30, "enabled": true}, ...}

Execution (see also CommandCleanupJob):
  * The timer starts when the bot's reply has been SENT (a command with no reply: when the handler
    finished). The command message and the reply(ies) are put in ONE persisted job with ONE deadline.
  * Only the enabled toggles are deleted; both off = no job at all.
  * Jobs live in the database (command_cleanup_jobs). A fast in-process timer fires them on time and
    a sweeper in every bot runner recovers anything overdue after a restart or crash. Jobs are claimed
    with an atomic UPDATE, so concurrent workers never delete the same job twice.
  * The bot that sent the reply (bot_ref = numeric Telegram bot id) is the one that deletes it, so
    custom bots clean up with their own token.

Groups that never saved the table keep their old behaviour: the legacy auto_clean settings are mapped
onto a row (0 = keep). Moderation commands and /start /linkgroup are only touched when a row exists.

Kill switch: env COMMAND_AUTODELETE_ENABLED=0 stops every deletion at once, no deploy.
"""
import asyncio
import contextvars
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

RANK_COMMANDS = {"rank", "xp", "me", "leaderboard", "top"}
# Never cleaned from the legacy settings (moderation evidence, setup flows). An explicit table row wins.
SKIP_COMMANDS = {"start", "linkgroup", "warn", "ban", "kick", "mute", "unmute", "tempban",
                 "tempmute", "purge", "removewarning", "unwarn"}
NEVER_COMMANDS = {"start", "linkgroup"}      # setup flows: not even with a table row
ALIASES = {"role": "roles"}                  # the dashboard has always called /roles "/role"
MAX_SECONDS = 86400
MIN_SECONDS = 1
DEFAULT_SECONDS = 30
MAX_ATTEMPTS = 5
SWEEP_INTERVAL = 15
LEASE_SECONDS = 120
LEGACY_COMMAND_ONLY_DELAY = 10

_REPLY_METHODS = ("reply_text", "reply_html", "reply_markdown", "reply_photo", "reply_animation",
                  "reply_document", "reply_video", "reply_sticker", "reply_audio", "reply_voice",
                  "reply_poll", "reply_dice", "reply_location", "reply_contact", "reply_media_group")
# Bot.send_* calls made while a command handler runs (bots that answer with bot.send_message).
_SEND_METHODS = ("send_message", "send_photo", "send_animation", "send_document", "send_video",
                 "send_sticker", "send_audio", "send_voice", "send_poll", "send_dice",
                 "send_location", "send_contact", "send_media_group")

_state = {"app": None, "installed": False, "store": None, "sweepers": {}, "identity": {}}
# The command currently being handled. Set only INSIDE CommandHandler.handle_update and reset right
# after, so it can never leak into another update (welcome messages, warnings, ...).
_current = contextvars.ContextVar("command_cleanup_current", default=None)


def enabled() -> bool:
    return os.environ.get("COMMAND_AUTODELETE_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


# ── configuration ───────────────────────────────────────────────────────────────

def command_name(text):
    """'/rank@MyBot extra' -> 'rank'; None when the text is not a command."""
    if not text or not text.startswith("/"):
        return None
    parts = text[1:].split()
    return parts[0].split("@")[0].lower() or None if parts else None


def canon(command):
    c = (command or "").lstrip("/").lower()
    return ALIASES.get(c, c)


def _seconds(value, default=0, lo=0):
    try:
        return max(lo, min(int(value), MAX_SECONDS))
    except (TypeError, ValueError):
        return default


def normalize_row(raw):
    """Validated row from user input. Raises ValueError on a malformed row."""
    if not isinstance(raw, dict):
        raise ValueError("row must be an object")
    try:
        seconds = int(raw.get("seconds", DEFAULT_SECONDS))
    except (TypeError, ValueError):
        raise ValueError("seconds must be a whole number")
    if seconds < MIN_SECONDS or seconds > MAX_SECONDS:
        raise ValueError(f"seconds must be between {MIN_SECONDS} and {MAX_SECONDS}")
    return {"delete_command": bool(raw.get("delete_command", True)),
            "delete_reply": bool(raw.get("delete_reply", True)),
            "seconds": seconds,
            "enabled": bool(raw.get("enabled", True))}


def delays_from_settings(auto_clean, command):
    """Legacy: (reply_seconds, delete_command_too) from a group's auto_clean settings."""
    if command is None or command in SKIP_COMMANDS or not isinstance(auto_clean, dict):
        return 0, False
    generic = _seconds(auto_clean.get("command_reply_delete_seconds"))
    seconds = generic
    if command in RANK_COMMANDS:
        seconds = _seconds(auto_clean.get("rank_reply_delete_seconds")) or generic
    return seconds, bool(auto_clean.get("delete_commands"))


def legacy_row(settings, command):
    """The row a group effectively has before it ever saved the command table."""
    seconds, delete_cmd = delays_from_settings((settings or {}).get("auto_clean"), command)
    if seconds > 0:
        return {"delete_command": delete_cmd, "delete_reply": True, "seconds": seconds, "enabled": True}
    if delete_cmd:
        return {"delete_command": True, "delete_reply": False,
                "seconds": LEGACY_COMMAND_ONLY_DELAY, "enabled": True}
    return {"delete_command": False, "delete_reply": False, "seconds": DEFAULT_SECONDS, "enabled": True}


def resolve_row(settings, command):
    """The effective row for `command` in a group: saved table row, else the legacy mapping."""
    cmd = canon(command)
    table = (settings or {}).get("command_table")
    raw = table.get(cmd) if isinstance(table, dict) else None
    if isinstance(raw, dict):
        try:
            return normalize_row(raw)
        except ValueError:
            pass
    return legacy_row(settings, cmd)


def is_command_enabled(settings, command):
    """Status toggle: False only when the group switched this command off in the table."""
    table = (settings or {}).get("command_table")
    raw = table.get(canon(command)) if isinstance(table, dict) else None
    return not (isinstance(raw, dict) and raw.get("enabled") is False)


def _settings_for_chat(chat_id, bot=None):
    """Settings of this chat AS SEEN BY this bot: a custom bot reads its own Group row, the official
    bot its TelegramGroup row, so the same chat with two bots never shares (or overwrites) a table."""
    app = _state["app"]
    if app is None:
        return {}
    gid = str(chat_id)
    custom_id = _state["identity"].get(_bot_ref(bot)) if bot is not None else None
    with app.app_context():
        from .models import TelegramGroup, Group
        if custom_id is not None:
            row = Group.query.filter_by(telegram_group_id=gid, bot_id=custom_id).first()
        else:
            row = TelegramGroup.query.filter_by(telegram_group_id=gid).first()
            if row is None:
                row = Group.query.filter_by(telegram_group_id=gid).first()
        return dict(getattr(row, "settings", None) or {})


def _row_for(chat_id, command, bot=None):
    """(row, command) to clean for this command in this chat, or None."""
    cmd = canon(command)
    if not cmd or cmd in NEVER_COMMANDS:
        return None
    settings = _settings_for_chat(chat_id, bot)
    table = settings.get("command_table")
    explicit = isinstance(table, dict) and isinstance(table.get(cmd), dict)
    if not explicit and cmd in SKIP_COMMANDS:
        return None
    row = resolve_row(settings, cmd)
    if not (row["delete_command"] or row["delete_reply"]):
        return None
    return row


# ── job store (database) ────────────────────────────────────────────────────────

class DbStore:
    """Persistent job store on CommandCleanupJob. All methods are synchronous (run in a thread)."""

    def _ctx(self):
        return _state["app"].app_context()

    def create(self, bot_ref, scope_id, command, ids, deliver_at):
        from .models import db, CommandCleanupJob
        with self._ctx():
            job = CommandCleanupJob(platform="telegram", bot_ref=str(bot_ref), scope_id=str(scope_id),
                                    command=command or "", message_ids=list(ids), deliver_at=deliver_at)
            db.session.add(job)
            db.session.commit()
            return job.id

    def append(self, job_id, ids):
        """Add ids to a job that is still pending. False when it already ran / is running."""
        from .models import db, CommandCleanupJob
        with self._ctx():
            job = CommandCleanupJob.query.filter_by(id=job_id, status="pending").with_for_update().first()
            if job is None or job.deliver_at <= datetime.utcnow():
                db.session.rollback()
                return False
            job.message_ids = list(job.message_ids or []) + [i for i in ids if i not in (job.message_ids or [])]
            db.session.commit()
            return True

    def claim(self, job_id):
        """Atomically take a due job. Returns {'scope_id','ids','attempts'} or None."""
        from .models import db, CommandCleanupJob
        now = datetime.utcnow()
        with self._ctx():
            n = CommandCleanupJob.query.filter(
                CommandCleanupJob.id == job_id,
                CommandCleanupJob.deliver_at <= now,
                db.or_(CommandCleanupJob.status == "pending",
                       db.and_(CommandCleanupJob.status == "claimed", CommandCleanupJob.claimed_until < now)),
            ).update({"status": "claimed", "claimed_until": now + timedelta(seconds=LEASE_SECONDS),
                      "attempts": CommandCleanupJob.attempts + 1}, synchronize_session=False)
            db.session.commit()
            if not n:
                return None
            job = db.session.get(CommandCleanupJob, job_id)
            return {"scope_id": job.scope_id, "ids": list(job.message_ids or []), "attempts": job.attempts}

    def settle(self, job_id, remaining, error, retry_in):
        from .models import db, CommandCleanupJob
        with self._ctx():
            job = db.session.get(CommandCleanupJob, job_id)
            if job is None:
                return
            job.message_ids = list(remaining)
            job.last_error = (error or "")[:255] or None
            job.claimed_until = None
            if retry_in is not None:
                job.status = "pending"
                job.deliver_at = datetime.utcnow() + timedelta(seconds=retry_in)
            else:
                job.status = "failed" if error == PERM_ERROR else "done"
            db.session.commit()

    def due(self, bot_ref):
        from .models import db, CommandCleanupJob
        now = datetime.utcnow()
        with self._ctx():
            rows = CommandCleanupJob.query.filter(
                CommandCleanupJob.bot_ref == str(bot_ref), CommandCleanupJob.deliver_at <= now,
                db.or_(CommandCleanupJob.status == "pending",
                       db.and_(CommandCleanupJob.status == "claimed", CommandCleanupJob.claimed_until < now)),
            ).order_by(CommandCleanupJob.deliver_at).limit(200).all()
            return [r.id for r in rows]


PERM_ERROR = "the bot is missing the 'Delete messages' admin right"


def _store():
    if _state["store"] is None:
        _state["store"] = DbStore()
    return _state["store"]


# ── executing jobs ──────────────────────────────────────────────────────────────

def _bot_ref(bot):
    try:
        return str(bot.token).split(":")[0]
    except Exception:
        return "0"


def _classify(exc):
    """'gone' (already deleted / not deletable), 'perm' (no right) or 'retry'."""
    try:
        from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut, NetworkError
    except Exception:  # pragma: no cover
        return "retry"
    text = str(exc).lower()
    if isinstance(exc, Forbidden):
        return "perm"
    if isinstance(exc, BadRequest):
        if "not enough rights" in text or "rights to delete" in text or "administrator" in text:
            return "perm"
        return "gone"   # message to delete not found / can't be deleted (older than 48h)
    if isinstance(exc, (RetryAfter, TimedOut, NetworkError)):
        return "retry"
    return "retry"


async def _execute(bot, job_id):
    """Run one due job. Never raises."""
    try:
        if not enabled():
            return
        store = _store()
        job = await asyncio.to_thread(store.claim, job_id)
        if not job:
            return
        remaining, error = [], None
        for mid in job["ids"]:
            try:
                await bot.delete_message(chat_id=int(job["scope_id"]), message_id=int(mid))
            except Exception as exc:
                kind = _classify(exc)
                if kind == "perm":
                    error = PERM_ERROR
                    logger.warning("command cleanup: cannot delete %s in %s (%s)", mid, job["scope_id"], exc)
                elif kind == "retry":
                    remaining.append(mid)
                    error = f"retrying: {type(exc).__name__}"
        retry = None
        if remaining and job["attempts"] < MAX_ATTEMPTS:
            retry = min(30 * (2 ** (job["attempts"] - 1)), 900)
        await asyncio.to_thread(store.settle, job_id, remaining if retry is not None else [], error, retry)
    except Exception:
        logger.debug("command cleanup job %s failed", job_id, exc_info=True)


async def _run_at(bot, job_id, deliver_at):
    wait = (deliver_at - datetime.utcnow()).total_seconds()
    if wait > 0:
        await asyncio.sleep(wait)
    await _execute(bot, job_id)


async def sweep_once(bot):
    """Run every overdue job that belongs to this bot (restart recovery). Returns jobs attempted."""
    ids = await asyncio.to_thread(_store().due, _bot_ref(bot))
    for jid in ids:
        await _execute(bot, jid)
    return len(ids)


async def _sweep_loop(bot):
    while True:
        try:
            await sweep_once(bot)
        except Exception:
            logger.debug("command cleanup sweep failed", exc_info=True)
        await asyncio.sleep(SWEEP_INTERVAL)


def start_sweeper(bot, flask_app=None, custom_bot_id=None):
    """Start (once per bot per event loop) the loop that recovers and runs this bot's overdue jobs.
    Call from inside the bot's running event loop."""
    if flask_app is not None and _state["app"] is None:
        _state["app"] = flask_app
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    ref = _bot_ref(bot)
    if custom_bot_id is not None:
        _state["identity"][ref] = custom_bot_id
    existing = _state["sweepers"].get(ref)
    if existing is not None and existing[0] is loop and not existing[1].done():
        return existing[1]
    task = loop.create_task(_sweep_loop(bot))
    _state["sweepers"][ref] = (loop, task)
    return task


# ── scheduling a command's cleanup ──────────────────────────────────────────────

def _ids_of(sent):
    items = sent if isinstance(sent, (list, tuple)) else [sent]
    return [m.message_id for m in items if getattr(m, "message_id", None) is not None]


def _new_state(bot, chat_id, command, row, cmd_msg_id):
    return {"bot": bot, "chat_id": chat_id, "command": command, "row": row, "cmd_id": cmd_msg_id,
            "job_id": None, "deadline": None, "lock": asyncio.Lock(), "seen": set()}


async def _register(state, reply_ids):
    """Record a sent reply (or, with reply_ids=None, the command finishing without one)."""
    async with state["lock"]:
        row = state["row"]
        new = [i for i in (reply_ids or []) if i not in state["seen"]]
        state["seen"].update(new)
        ids = list(new) if row["delete_reply"] else []
        first = state["job_id"] is None
        if first:
            if state["deadline"] is None:
                state["deadline"] = datetime.utcnow() + timedelta(seconds=row["seconds"])
            if row["delete_command"] and state["cmd_id"] is not None:
                ids.insert(0, state["cmd_id"])
        if not ids:
            return
        store = _store()
        if not first:
            if await asyncio.to_thread(store.append, state["job_id"], ids):
                return
            state["deadline"] = datetime.utcnow() + timedelta(seconds=2)  # late reply: its own short job
        bot = state["bot"]
        job_id = await asyncio.to_thread(store.create, _bot_ref(bot), state["chat_id"],
                                         state["command"], ids, state["deadline"])
        state["job_id"] = job_id
        asyncio.ensure_future(_run_at(bot, job_id, state["deadline"]))


async def after_reply(command_message, sent):
    """Called after a Message.reply_* returned (commands not handled by a CommandHandler). Never raises."""
    try:
        if not enabled() or sent is None:
            return
        cur = _current.get()
        if cur is not None and cur["chat_id"] == command_message.chat.id:
            return  # the Bot.send_* hook inside the running command handler takes care of it
        chat = getattr(command_message, "chat", None)
        if getattr(chat, "type", None) not in ("group", "supergroup"):
            return
        command = command_name(getattr(command_message, "text", None))
        if command is None:
            return
        row = await asyncio.to_thread(_row_for, chat.id, command, command_message.get_bot())
        if row is None:
            return
        state = _new_state(command_message.get_bot(), chat.id, canon(command), row, command_message.message_id)
        await _register(state, _ids_of(sent))
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
    row = await asyncio.to_thread(_row_for, chat.id, command, msg.get_bot())
    if row is None:
        return None
    return _new_state(msg.get_bot(), chat.id, canon(command), row, msg.message_id)


# Commands whose own handler already applies Status + topic access (and the configurable
# "restricted reply"), so the generic gate below must not pre-empt them.
SELF_GATED = {"xp", "rank", "leaderboard"}


def gate_enabled() -> bool:
    return os.environ.get("COMMAND_GATE_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


def blocked_by_table(settings, command, thread_id) -> bool:
    """True when the Command Management table switches `command` off here: Status off, or access
    limited to topics the message is not in. Pure function of the group's settings."""
    cmd = canon(command)
    if not cmd or cmd in NEVER_COMMANDS or cmd in SELF_GATED:
        return False
    if not is_command_enabled(settings, cmd):
        return True
    cmds = ((settings or {}).get("command_routing") or {}).get("commands") or {}
    rule = None
    for key in [f"/{cmd}", cmd] + [f"/{k}" for k, v in ALIASES.items() if v == cmd]:
        if isinstance(cmds.get(key), dict):
            rule = cmds[key]
            break
    if not rule:
        return False
    scope = rule.get("scope", "all_group")
    if scope == "disabled":
        return True
    if scope == "specific_topics":
        ids = [str(t) for t in (rule.get("topic_ids") or [])]
        return not ids or thread_id is None or str(thread_id) not in ids
    return False


def _gate_blocked(chat_id, command, bot, thread_id):
    return blocked_by_table(_settings_for_chat(chat_id, bot), command, thread_id)


async def _gated(update) -> bool:
    """True when this group command must be ignored per the Command Management table. Never raises."""
    try:
        if not gate_enabled():
            return False
        msg = getattr(update, "effective_message", None)
        chat = getattr(msg, "chat", None)
        if msg is None or getattr(chat, "type", None) not in ("group", "supergroup"):
            return False
        command = command_name(getattr(msg, "text", None))
        if command is None or canon(command) in SELF_GATED or canon(command) in NEVER_COMMANDS:
            return False
        thread_id = getattr(msg, "message_thread_id", None) if getattr(msg, "is_topic_message", False) else None
        return await asyncio.to_thread(_gate_blocked, chat.id, command, msg.get_bot(), thread_id)
    except Exception:
        logger.debug("command gate skipped", exc_info=True)
        return False


def _install_command_scope(handler_cls):
    original = handler_cls.handle_update

    async def handle_update(self, update, *args, **kwargs):
        token = None
        state = None
        if await _gated(update):
            return None
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
            if state is not None and state["job_id"] is None:
                try:   # no reply was sent: the completion time is the reference
                    await _register(state, None)
                except Exception:
                    logger.debug("command cleanup skipped", exc_info=True)

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
                    if state is not None and sent is not None:
                        chat_id = kwargs.get("chat_id", args[0] if args else None)
                        if str(chat_id) == str(state["chat_id"]):
                            state["bot"] = self
                            await _register(state, _ids_of(sent))
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
