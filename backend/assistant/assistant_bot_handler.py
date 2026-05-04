"""
Handler for user-owned Assistant Bots.

Receives a parsed python-telegram-bot Update and dispatches to the correct
command handler.  All handlers are async and receive the Flask app context
so they can write to the DB.

Supported commands: /remind, /note, /task, /summary, /start, /help
"""

import logging
import re
from datetime import datetime, timedelta

from telegram import Bot, Update
from telegram.constants import ParseMode

_log = logging.getLogger("assistant_bot_handler")

# ── helpers ───────────────────────────────────────────────────────────────────

def _user_desc(tg_user):
    return f"@{tg_user.username}" if tg_user.username else tg_user.first_name or str(tg_user.id)


async def _reply(bot: Bot, chat_id: int, text: str):
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        _log.warning("assistant_bot send_message failed chat_id=%s: %s", chat_id, exc)


# ── space auto-registration ───────────────────────────────────────────────────

def _register_space(flask_app, assistant_bot_id: int, message):
    """Upsert an AssistantSpace row for the chat this message came from."""
    try:
        chat = message.chat
        chat_id_str = str(chat.id)
        title = getattr(chat, "title", None) or getattr(chat, "first_name", None) or chat_id_str
        chat_type = chat.type or "unknown"

        with flask_app.app_context():
            from ..models import db, AssistantSpace
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy import text

            now = datetime.utcnow()
            # Try upsert via raw SQL so it's a single round-trip
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
                # Fallback for SQLite (dev)
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
                        chat_title=title,
                        chat_type=chat_type,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    db.session.add(space)
                db.session.commit()
    except Exception as exc:
        _log.warning("_register_space failed: %s", exc)


# ── command dispatcher ────────────────────────────────────────────────────────

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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


async def handle_update(update: Update, bot: Bot, flask_app, assistant_bot_id: int):
    """Entry point called by the webhook receiver for every incoming update."""
    # Handle suggestion button taps
    if update.callback_query:
        await _handle_callback(update.callback_query, bot, flask_app, assistant_bot_id)
        return

    message = update.message or update.edited_message
    if not message or not message.text:
        return

    # Auto-register this chat as an assistant space on every message
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
    elif cmd == "/summary":
        await _cmd_summary(bot, chat_id, tg_user, text, flask_app, assistant_bot_id)
    elif cmd is None and message.chat.type == "private":
        # Natural language DM — route through personal assistant
        await _cmd_natural_language(bot, chat_id, tg_user, text, flask_app, assistant_bot_id)


# ── /start ────────────────────────────────────────────────────────────────────

async def _cmd_start(bot: Bot, chat_id: int, tg_user):
    name = tg_user.first_name or "there"
    await _reply(bot, chat_id, (
        f"👋 Hi {name}! I'm your personal Telegizer Assistant Bot.\n\n"
        "Here's what I can do:\n"
        "• `/remind <time> <text>` — set a reminder\n"
        "• `/note <text>` — save a quick note\n"
        "• `/task <text>` — create a task\n"
        "• `/summary` — get an AI summary of recent activity\n\n"
        "Type /help for details."
    ))


# ── /help ─────────────────────────────────────────────────────────────────────

async def _cmd_help(bot: Bot, chat_id: int):
    await _reply(bot, chat_id, (
        "*Assistant Bot Commands*\n\n"
        "*/remind* `<time> <text>`\n"
        "  Set a reminder. Time examples: `30m`, `2h`, `tomorrow 9am`\n\n"
        "*/note* `<text>`\n"
        "  Save a note to your Workspace.\n\n"
        "*/task* `<text>`\n"
        "  Create a task in your Workspace.\n\n"
        "*/summary*\n"
        "  AI summary of your recent workspace activity."
    ))


# ── /remind ───────────────────────────────────────────────────────────────────

def _parse_remind_offset(raw: str):
    """Parse simple offsets like '30m', '2h', '1d'. Returns timedelta or None."""
    m = re.match(r"^(\d+)(m|h|d)$", raw.lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(minutes=n) if unit == "m" else timedelta(hours=n) if unit == "h" else timedelta(days=n)


async def _cmd_remind(bot: Bot, chat_id: int, tg_user, text: str, flask_app, assistant_bot_id: int):
    # /remind <offset> <reminder text>
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await _reply(bot, chat_id, "Usage: `/remind 30m Buy groceries`\nSupported: `30m`, `2h`, `1d`")
        return

    delta = _parse_remind_offset(parts[1])
    if not delta:
        await _reply(bot, chat_id, f"Unrecognised time `{parts[1]}`. Use `30m`, `2h`, `1d`, etc.")
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

    when_str = remind_at.strftime("%Y-%m-%d %H:%M UTC")
    await _reply(bot, chat_id, f"⏰ Reminder set for *{when_str}*:\n_{remind_text}_")


# ── /note ─────────────────────────────────────────────────────────────────────

async def _cmd_note(bot: Bot, chat_id: int, tg_user, text: str, flask_app, assistant_bot_id: int):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await _reply(bot, chat_id, "Usage: `/note Meeting decided to launch on Friday`")
        return

    content = parts[1]

    with flask_app.app_context():
        from ..models import db, AssistantBot, Note
        abot = AssistantBot.query.get(assistant_bot_id)
        if not abot:
            return
        note = Note(
            user_id=abot.user_id,
            content=content,
            source="assistant_bot",
        )
        db.session.add(note)
        db.session.commit()

    await _reply(bot, chat_id, f"📝 Note saved:\n_{content}_")


# ── /task ─────────────────────────────────────────────────────────────────────

async def _cmd_task(bot: Bot, chat_id: int, tg_user, text: str, flask_app, assistant_bot_id: int):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await _reply(bot, chat_id, "Usage: `/task Write the product spec by Friday`")
        return

    title = parts[1]

    with flask_app.app_context():
        from ..models import db, AssistantBot, Task
        abot = AssistantBot.query.get(assistant_bot_id)
        if not abot:
            return
        task = Task(
            user_id=abot.user_id,
            title=title,
            status="todo",
            source="bot",
        )
        db.session.add(task)
        db.session.commit()

    await _reply(bot, chat_id, f"✅ Task created:\n_{title}_")


# ── /summary ──────────────────────────────────────────────────────────────────

async def _cmd_summary(bot: Bot, chat_id: int, tg_user, text: str, flask_app, assistant_bot_id: int):
    await _reply(bot, chat_id, "⏳ Generating your workspace summary…")

    try:
        with flask_app.app_context():
            from ..models import AssistantBot, Note, Task, WorkspaceReminder
            from ..assistant.ai_key_resolver import resolve_ai_key
            import openai as _openai

            abot = AssistantBot.query.get(assistant_bot_id)
            if not abot:
                return

            uid = abot.user_id
            now = datetime.utcnow()
            since = now - timedelta(days=7)

            notes = Note.query.filter(Note.user_id == uid, Note.created_at >= since).order_by(Note.created_at.desc()).limit(5).all()
            tasks = Task.query.filter(Task.user_id == uid, Task.status == "pending").order_by(Task.created_at.desc()).limit(5).all()
            reminders = WorkspaceReminder.query.filter(WorkspaceReminder.owner_user_id == uid, WorkspaceReminder.remind_at >= now, WorkspaceReminder.is_delivered == False).order_by(WorkspaceReminder.remind_at).limit(5).all()

            lines = []
            if notes:
                lines.append("*Recent notes:*\n" + "\n".join(f"- {n.content[:80]}" for n in notes))
            if tasks:
                lines.append("*Pending tasks:*\n" + "\n".join(f"- {t.title[:80]}" for t in tasks))
            if reminders:
                lines.append("*Upcoming reminders:*\n" + "\n".join(f"- {r.reminder_text[:80]} ({r.remind_at.strftime('%b %d %H:%M')})" for r in reminders))

            if not lines:
                await _reply(bot, chat_id, "Your workspace is empty — nothing to summarise yet.")
                return

            context_text = "\n\n".join(lines)

            api_key = resolve_ai_key(uid)
            client = _openai.AsyncOpenAI(api_key=api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Summarise the user's workspace activity concisely in 3-5 bullet points."},
                    {"role": "user", "content": context_text},
                ],
                max_tokens=300,
            )
            summary = resp.choices[0].message.content.strip()

        await _reply(bot, chat_id, f"*Your Workspace Summary*\n\n{summary}")

    except Exception as exc:
        _log.warning("assistant /summary failed: %s", exc)
        await _reply(bot, chat_id, "Sorry, summary generation failed. Try again later.")


# ── Suggestion button callback ────────────────────────────────────────────────

async def _handle_callback(callback_query, bot: Bot, flask_app, assistant_bot_id: int):
    """Handle assistant suggestion button taps."""
    await callback_query.answer()
    data = callback_query.data or ""
    chat_id = callback_query.message.chat_id

    if data == "assist_custom":
        try:
            await callback_query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await bot.send_message(chat_id=chat_id, text="Go ahead — type your response:")
        return

    if not data.startswith("assist_pick:"):
        return

    value = data[len("assist_pick:"):]
    if not value or not flask_app:
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
        db.session.add(BotDMMessage(user_id=uid, direction="in", content=value, intent="assistant_pick"))
        db.session.commit()

        try:
            result = process_message(user_id=uid, message=value)
        except Exception as exc:
            _log.warning("assistant_pick handler failed: %s", exc)
            return

        reply_text = result.get("reply") or "Got it!"
        db.session.add(BotDMMessage(user_id=uid, direction="out", content=reply_text, intent=result.get("intent", "general")))
        db.session.commit()

        await bot.send_message(chat_id=chat_id, text=f"▶ {value}")
        keyboard = _build_suggestion_keyboard(result.get("suggestions"))
        await bot.send_message(chat_id=chat_id, text=reply_text, reply_markup=keyboard)


# ── Natural language DM ───────────────────────────────────────────────────────

async def _cmd_natural_language(bot: Bot, chat_id: int, tg_user, text: str, flask_app, assistant_bot_id: int):
    """Handle free-text DMs via the shared personal assistant NLP service."""
    with flask_app.app_context():
        from ..models import db, AssistantBot, BotDMMessage
        from ..assistant.personal_assistant import process_message

        abot = AssistantBot.query.get(assistant_bot_id)
        if not abot:
            return

        uid = abot.user_id

        inbound = BotDMMessage(user_id=uid, direction="in", content=text, intent="telegram_dm")
        db.session.add(inbound)
        db.session.commit()

        try:
            result = process_message(user_id=uid, message=text)
        except Exception as exc:
            _log.warning("natural language handler failed: %s", exc)
            await _reply(bot, chat_id, "Sorry, I couldn't process that. Try /help for available commands.")
            return

        reply_text = result.get("reply") or "I'm not sure how to help with that."

        outbound = BotDMMessage(user_id=uid, direction="out", content=reply_text, intent=result.get("intent", "general"))
        db.session.add(outbound)
        db.session.commit()

        keyboard = _build_suggestion_keyboard(result.get("suggestions"))

    if keyboard:
        try:
            await bot.send_message(chat_id=chat_id, text=reply_text, reply_markup=keyboard)
        except Exception:
            await _reply(bot, chat_id, reply_text)
    else:
        await _reply(bot, chat_id, reply_text)
