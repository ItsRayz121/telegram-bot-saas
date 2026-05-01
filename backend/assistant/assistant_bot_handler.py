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


# ── command dispatcher ────────────────────────────────────────────────────────

async def handle_update(update: Update, bot: Bot, flask_app, assistant_bot_id: int):
    """Entry point called by the webhook receiver for every incoming update."""
    message = update.message or update.edited_message
    if not message or not message.text:
        return

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
    # Non-command messages silently ignored — assistant bot only responds to explicit commands


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
