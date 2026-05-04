"""
Handler for user-owned Assistant Bots (Telegram DM interface).

Natural language DMs are routed through process_message() — the same hybrid AI
engine that powers the web assistant. All AI upgrades (general chat, expand
analysis, workspace intelligence) apply automatically here too.

Slash commands are kept as shortcuts for power users.
"""

import logging
import re
from datetime import datetime, timedelta

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

_log = logging.getLogger("assistant_bot_handler")


# ── Formatting helpers ────────────────────────────────────────────────────────

def _md_to_telegram(text: str) -> str:
    """
    Convert AI-generated markdown (**bold**, *italic*, bullet lists)
    to Telegram HTML so it renders properly in bot messages.
    """
    if not text:
        return text
    # **bold** → <b>bold</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    # *italic* → <i>italic</i>  (only single asterisk remaining)
    text = re.sub(r'\*(?!\*)(.+?)(?<!\*)\*', r'<i>\1</i>', text, flags=re.DOTALL)
    # ### Header → <b>Header</b>
    text = re.sub(r'^#{1,3}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    # Escape bare < and > that aren't part of our tags
    # (already escaped because we build the HTML ourselves — no extra escaping needed)
    return text


async def _reply(bot: Bot, chat_id: int, text: str):
    """Send a message with HTML formatting. Falls back to plain text on error."""
    html = _md_to_telegram(text)
    try:
        await bot.send_message(chat_id=chat_id, text=html, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except Exception as exc:
            _log.warning("send_message failed chat_id=%s: %s", chat_id, exc)


async def _reply_with_keyboard(bot: Bot, chat_id: int, text: str, keyboard):
    html = _md_to_telegram(text)
    try:
        await bot.send_message(chat_id=chat_id, text=html, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        try:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
        except Exception as exc:
            _log.warning("send_message_with_keyboard failed chat_id=%s: %s", chat_id, exc)


# ── Suggestion keyboard builder ───────────────────────────────────────────────

def _build_suggestion_keyboard(suggestions):
    if not suggestions:
        return None
    rows = []
    row = []
    for s in suggestions:
        label = s.get("label", "")
        value = s.get("value")
        cb = "assist_custom" if value is None else f"assist_pick:{value[:50]}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows) if rows else None


# ── Space auto-registration ───────────────────────────────────────────────────

def _register_space(flask_app, assistant_bot_id: int, message):
    try:
        chat = message.chat
        chat_id_str = str(chat.id)
        title = getattr(chat, "title", None) or getattr(chat, "first_name", None) or chat_id_str
        chat_type = chat.type or "unknown"

        with flask_app.app_context():
            from ..models import db, AssistantSpace
            from sqlalchemy import text

            now = datetime.utcnow()
            try:
                db.session.execute(text("""
                    INSERT INTO assistant_spaces (assistant_bot_id, telegram_chat_id, chat_title, chat_type, first_seen_at, last_seen_at)
                    VALUES (:bot_id, :chat_id, :title, :ctype, :now, :now)
                    ON CONFLICT (assistant_bot_id, telegram_chat_id)
                    DO UPDATE SET chat_title = EXCLUDED.chat_title, last_seen_at = EXCLUDED.last_seen_at
                """), {"bot_id": assistant_bot_id, "chat_id": chat_id_str, "title": title, "ctype": chat_type, "now": now})
                db.session.commit()
            except Exception:
                db.session.rollback()
                space = AssistantSpace.query.filter_by(
                    assistant_bot_id=assistant_bot_id, telegram_chat_id=chat_id_str
                ).first()
                if space:
                    space.chat_title = title
                    space.last_seen_at = now
                else:
                    space = AssistantSpace(
                        assistant_bot_id=assistant_bot_id,
                        telegram_chat_id=chat_id_str,
                        chat_title=title, chat_type=chat_type,
                        first_seen_at=now, last_seen_at=now,
                    )
                    db.session.add(space)
                db.session.commit()
    except Exception as exc:
        _log.warning("_register_space failed: %s", exc)


# ── Main update handler ───────────────────────────────────────────────────────

async def handle_update(update: Update, bot: Bot, flask_app, assistant_bot_id: int):
    if update.callback_query:
        await _handle_callback(update.callback_query, bot, flask_app, assistant_bot_id)
        return

    message = update.message or update.edited_message
    if not message or not message.text:
        return

    _register_space(flask_app, assistant_bot_id, message)

    text = message.text.strip()
    chat_id = message.chat_id
    tg_user = message.from_user

    cmd = text.split()[0].lower().split("@")[0] if text.startswith("/") else None

    if cmd == "/start":
        await _cmd_start(bot, chat_id, tg_user)
    elif cmd == "/help":
        await _cmd_help(bot, chat_id)
    elif cmd == "/remind":
        await _cmd_remind(bot, chat_id, tg_user, text, flask_app, assistant_bot_id)
    elif cmd == "/note":
        await _cmd_note(bot, chat_id, tg_user, text, flask_app, assistant_bot_id)
    elif cmd == "/task":
        await _cmd_task(bot, chat_id, tg_user, text, flask_app, assistant_bot_id)
    elif cmd == "/analyze" or cmd == "/summary" or cmd == "/day":
        await _cmd_analyze(bot, chat_id, tg_user, flask_app, assistant_bot_id)
    elif cmd is None and message.chat.type == "private":
        await _cmd_natural_language(bot, chat_id, tg_user, text, flask_app, assistant_bot_id)


# ── /start ────────────────────────────────────────────────────────────────────

async def _cmd_start(bot: Bot, chat_id: int, tg_user):
    name = tg_user.first_name or "there"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Analyze My Day", callback_data="assist_pick:Analyze my day"),
         InlineKeyboardButton("📅 My Schedule", callback_data="assist_pick:What's on my schedule?")],
        [InlineKeyboardButton("👥 Group Health", callback_data="assist_pick:Any issues in my groups?"),
         InlineKeyboardButton("📋 My Tasks", callback_data="assist_pick:Show my tasks")],
    ])
    await _reply_with_keyboard(bot, chat_id, (
        f"👋 Hi <b>{name}</b>! I'm your Telegizer AI Assistant.\n\n"
        "I'm a hybrid AI — just talk to me naturally:\n\n"
        "💬 <b>Ask anything</b>\n"
        "• \"What is the capital of France?\"\n"
        "• \"Explain Telegram community growth\"\n"
        "• \"Write an announcement for my group\"\n\n"
        "🏢 <b>Manage your workspace</b>\n"
        "• \"Any issues in my groups?\"\n"
        "• \"Schedule a meeting tomorrow 3pm\"\n"
        "• \"Remind me to send report at 5pm\"\n"
        "• \"Analyze my day\"\n\n"
        "⚡ <b>Quick commands</b>\n"
        "/analyze — daily briefing\n"
        "/remind — set reminder\n"
        "/note — save a note\n"
        "/task — create a task\n\n"
        "<i>Just type anything — I understand natural language.</i>"
    ), keyboard)


# ── /help ─────────────────────────────────────────────────────────────────────

async def _cmd_help(bot: Bot, chat_id: int):
    await _reply(bot, chat_id, (
        "<b>Telegizer Assistant — Hybrid AI</b>\n\n"
        "Just talk to me naturally — no commands needed.\n\n"
        "<b>Examples:</b>\n"
        "• \"What's happening in my groups?\"\n"
        "• \"Schedule a call Friday 2pm with Ahmed\"\n"
        "• \"Remind me about the proposal tomorrow morning\"\n"
        "• \"Who is the current PM of UK?\"\n"
        "• \"Write a welcome message for my community\"\n"
        "• \"Analyze my day\"\n"
        "• \"Any low activity groups?\"\n"
        "• \"Create task: review analytics report\"\n\n"
        "<b>Quick commands:</b>\n"
        "/analyze — full daily briefing\n"
        "/remind 30m &lt;text&gt; — quick reminder\n"
        "/note &lt;text&gt; — save a note\n"
        "/task &lt;text&gt; — create a task"
    ))


# ── /remind ───────────────────────────────────────────────────────────────────

def _parse_remind_offset(raw: str):
    m = re.match(r"^(\d+)(m|h|d)$", raw.lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(minutes=n) if unit == "m" else timedelta(hours=n) if unit == "h" else timedelta(days=n)


async def _cmd_remind(bot: Bot, chat_id: int, tg_user, text: str, flask_app, assistant_bot_id: int):
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await _reply(bot, chat_id, "Usage: <code>/remind 30m Buy groceries</code>\nOr just say: \"Remind me to buy groceries in 30 minutes\"")
        return

    delta = _parse_remind_offset(parts[1])
    if not delta:
        # Fallback to natural language processing
        await _cmd_natural_language(bot, chat_id, tg_user, text[len("/remind "):], flask_app, assistant_bot_id)
        return

    remind_text = parts[2]
    remind_at = datetime.utcnow() + delta

    with flask_app.app_context():
        from ..models import db, AssistantBot, WorkspaceReminder
        abot = AssistantBot.query.get(assistant_bot_id)
        if not abot:
            return
        r = WorkspaceReminder(
            owner_user_id=abot.user_id,
            reminder_text=remind_text,
            remind_at=remind_at,
        )
        db.session.add(r)
        db.session.commit()

    when_str = remind_at.strftime("%d %b %Y at %H:%M UTC")
    await _reply(bot, chat_id, f"⏰ Reminder set for <b>{when_str}</b>:\n<i>{remind_text}</i>")


# ── /note ─────────────────────────────────────────────────────────────────────

async def _cmd_note(bot: Bot, chat_id: int, tg_user, text: str, flask_app, assistant_bot_id: int):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await _reply(bot, chat_id, "Usage: <code>/note Meeting decided to launch on Friday</code>\nOr just say: \"Note this: ...\"")
        return

    content = parts[1]

    with flask_app.app_context():
        from ..models import db, AssistantBot, Note
        abot = AssistantBot.query.get(assistant_bot_id)
        if not abot:
            return
        note = Note(user_id=abot.user_id, content=content, source="assistant_bot")
        db.session.add(note)
        db.session.commit()

    await _reply(bot, chat_id, f"📝 Note saved:\n<i>{content}</i>")


# ── /task ─────────────────────────────────────────────────────────────────────

async def _cmd_task(bot: Bot, chat_id: int, tg_user, text: str, flask_app, assistant_bot_id: int):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await _reply(bot, chat_id, "Usage: <code>/task Write the product spec by Friday</code>\nOr just say: \"Create task: ...\"")
        return

    title = parts[1]

    with flask_app.app_context():
        from ..models import db, AssistantBot, Task
        abot = AssistantBot.query.get(assistant_bot_id)
        if not abot:
            return
        task = Task(user_id=abot.user_id, title=title, status="todo", source="bot")
        db.session.add(task)
        db.session.commit()

    await _reply(bot, chat_id, f"✅ Task created:\n<i>{title}</i>")


# ── /analyze (/summary, /day) ─────────────────────────────────────────────────

async def _cmd_analyze(bot: Bot, chat_id: int, tg_user, flask_app, assistant_bot_id: int):
    await _reply(bot, chat_id, "⏳ Analyzing your workspace…")

    with flask_app.app_context():
        from ..models import AssistantBot
        from ..assistant.ai_key_resolver import get_workspace_ai_key
        from ..models import User

        abot = AssistantBot.query.get(assistant_bot_id)
        if not abot:
            return

        user = User.query.get(abot.user_id)
        if not user:
            return

        try:
            key_info = get_workspace_ai_key(user)
        except Exception:
            key_info = {}

        try:
            from ..assistant.handlers.analyze import handle_analyze_day
            result = handle_analyze_day(abot.user_id, key_info)
            reply_text = result.get("reply", "No analysis available.")
            suggestions = result.get("suggestions", [])
        except Exception as exc:
            _log.warning("_cmd_analyze failed: %s", exc)
            reply_text = "Couldn't generate analysis right now. Try asking: \"Analyze my day\""
            suggestions = []

    keyboard = _build_suggestion_keyboard(suggestions)
    await _reply_with_keyboard(bot, chat_id, reply_text, keyboard)


# ── Suggestion button callback ────────────────────────────────────────────────

async def _handle_callback(callback_query, bot: Bot, flask_app, assistant_bot_id: int):
    await callback_query.answer()
    data = callback_query.data or ""
    chat_id = callback_query.message.chat_id

    if data == "assist_custom":
        try:
            await callback_query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await bot.send_message(chat_id=chat_id, text="Go ahead — type your message:")
        return

    if not data.startswith("assist_pick:"):
        return

    value = data[len("assist_pick:"):]
    if not value:
        return

    try:
        await callback_query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    with flask_app.app_context():
        from ..models import db, AssistantBot, BotDMMessage
        from ..assistant.personal_assistant import process_message

        abot = AssistantBot.query.get(assistant_bot_id)
        if not abot:
            return

        uid = abot.user_id
        try:
            db.session.add(BotDMMessage(user_id=uid, direction="in", content=value, intent="assistant_pick"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            result = process_message(user_id=uid, message=value)
        except Exception as exc:
            _log.warning("assist_pick process_message failed: %s", exc)
            return

        reply_text = result.get("reply") or "Got it!"

        try:
            db.session.add(BotDMMessage(user_id=uid, direction="out", content=reply_text, intent=result.get("intent", "general")))
            db.session.commit()
        except Exception:
            db.session.rollback()

    await bot.send_message(chat_id=chat_id, text=f"▶ {value}")
    keyboard = _build_suggestion_keyboard(result.get("suggestions"))
    await _reply_with_keyboard(bot, chat_id, reply_text, keyboard)


# ── Natural language DM ───────────────────────────────────────────────────────

async def _cmd_natural_language(bot: Bot, chat_id: int, tg_user, text: str, flask_app, assistant_bot_id: int):
    """
    Free-text DMs — routed through the full hybrid AI personal assistant.
    This is the same engine as the web sidebar, so all AI upgrades apply:
    general chat, workspace intelligence, expand analysis, etc.
    """
    with flask_app.app_context():
        from ..models import db, AssistantBot, BotDMMessage
        from ..assistant.personal_assistant import process_message

        abot = AssistantBot.query.get(assistant_bot_id)
        if not abot:
            return

        uid = abot.user_id

        try:
            db.session.add(BotDMMessage(user_id=uid, direction="in", content=text, intent="telegram_dm"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            result = process_message(user_id=uid, message=text)
        except Exception as exc:
            _log.warning("natural_language process_message failed: %s", exc)
            await _reply(bot, chat_id, "I had trouble processing that. Try rephrasing or type /help.")
            return

        reply_text = result.get("reply") or "I'm not sure how to help with that. Try asking differently."

        try:
            db.session.add(BotDMMessage(user_id=uid, direction="out", content=reply_text, intent=result.get("intent", "general")))
            db.session.commit()
        except Exception:
            db.session.rollback()

        keyboard = _build_suggestion_keyboard(result.get("suggestions"))

    await _reply_with_keyboard(bot, chat_id, reply_text, keyboard)
