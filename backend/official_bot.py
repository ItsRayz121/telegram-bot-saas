"""
Official Telegizer shared bot — serves all users/groups from one token.

Key design:
- Stores flask_app (not app_context) in bot_data.
- Every handler creates a FRESH with flask_app.app_context(): for each DB call.
  Flask contexts must not be shared across coroutine invocations.
- Long-polling in its own asyncio event loop / daemon thread.
"""

import asyncio
import logging
import threading
import secrets
import string
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,
)
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

from .config import Config

_log = logging.getLogger(__name__)


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _log_event(flask_app, group_id, event_type, message=None, meta=None):
    """Write a BotEvent row; creates a fresh app context."""
    try:
        with flask_app.app_context():
            from .models import db, BotEvent
            ev = BotEvent(
                telegram_group_id=str(group_id) if group_id else None,
                event_type=event_type,
                message=message,
                metadata_=meta or {},
            )
            db.session.add(ev)
            db.session.commit()
    except Exception as exc:
        _log.warning("BotEvent log failed (%s): %s", event_type, exc)


def _upsert_group(flask_app, group_id: str, title: str, username=None):
    """Ensure a TelegramGroup row exists; returns nothing."""
    try:
        with flask_app.app_context():
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if not tg:
                tg = TelegramGroup(
                    telegram_group_id=group_id,
                    title=title,
                    username=username,
                    bot_status="pending",
                )
                db.session.add(tg)
            else:
                tg.title = title
            db.session.commit()
    except Exception as exc:
        _log.warning("_upsert_group failed: %s", exc)


async def _check_and_store_permissions(bot, group_id: str, flask_app):
    try:
        member = await bot.get_chat_member(chat_id=int(group_id), user_id=bot.id)
        perms = {
            "delete_messages": getattr(member, "can_delete_messages", False),
            "ban_users": getattr(member, "can_restrict_members", False),
            "pin_messages": getattr(member, "can_pin_messages", False),
            "manage_topics": getattr(member, "can_manage_topics", False),
        }
        with flask_app.app_context():
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if tg:
                tg.bot_permissions = perms
                tg.bot_status = "active"
                db.session.commit()
        return perms
    except Exception as exc:
        _log.warning("Permission check failed for %s: %s", group_id, exc)
        return {}


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return

    flask_app = context.bot_data.get("flask_app")
    user = update.effective_user
    first = user.first_name or "there"
    frontend = Config.FRONTEND_URL

    # Count pending groups (bot present but not yet linked to any account)
    pending_count = 0
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup
                pending_count = TelegramGroup.query.filter_by(
                    owner_user_id=None, bot_status="pending"
                ).count()
        except Exception:
            pass

    text = (
        f"👋 *Welcome to Telegizer, {first}!*\n\n"
        "Your all-in-one Telegram Group Management Hub.\n\n"
        "Manage groups, automate moderation, and grow your community — "
        "all from one place."
    )

    keyboard = []
    if pending_count:
        keyboard.append([
            InlineKeyboardButton(
                f"⚠️ {pending_count} Group(s) Awaiting Setup",
                callback_data="menu:pending_groups",
            )
        ])

    keyboard += [
        [
            InlineKeyboardButton("📋 My Groups", callback_data="menu:my_groups"),
            InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group"),
        ],
        [
            InlineKeyboardButton("🖥️ Dashboard", url=frontend),
            InlineKeyboardButton("💬 Support", callback_data="menu:support"),
        ],
        [InlineKeyboardButton("⚙️ Advanced Options", callback_data="menu:advanced")],
    ]

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─── /help ────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    frontend = Config.FRONTEND_URL
    bot_un = Config.TELEGRAM_BOT_USERNAME.strip("@").split("/")[-1]
    text = (
        "*Telegizer Help*\n\n"
        "*Link a group to your dashboard:*\n"
        "1. Add @" + bot_un + " to your Telegram group as admin\n"
        "2. Inside the group run `/linkgroup`\n"
        "3. Copy the code that appears\n"
        "4. Go to the Dashboard → Add Group and paste the code\n\n"
        "*Bot commands (use inside a group):*\n"
        "`/linkgroup` — generate a link code\n"
        "`/status` — check bot status & permissions\n\n"
        "*Bot commands (private chat):*\n"
        "`/start` — open companion hub\n\n"
        f"Dashboard: {frontend}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── /linkgroup ───────────────────────────────────────────────────────────────

async def cmd_linkgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    flask_app = context.bot_data.get("flask_app")

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "⚠️ Use `/linkgroup` *inside your Telegram group*, not in private chat.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not flask_app:
        await update.message.reply_text("⚠️ Service temporarily unavailable. Try again shortly.")
        return

    group_id = str(chat.id)
    group_title = chat.title or "Untitled Group"

    # Check if user is admin/creator
    try:
        cm = await context.bot.get_chat_member(chat.id, user.id)
        if cm.status not in ("creator", "administrator"):
            await update.message.reply_text("❌ Only group admins can generate link codes.")
            return
    except Exception:
        pass

    with flask_app.app_context():
        from .models import db, TelegramGroup, TelegramGroupLinkCode

        tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        if not tg:
            tg = TelegramGroup(
                telegram_group_id=group_id,
                title=group_title,
                username=chat.username,
                bot_status="pending",
            )
            db.session.add(tg)
            db.session.flush()

        if tg.owner_user_id and tg.bot_status == "active":
            await update.message.reply_text(
                "✅ This group is already linked to a Telegizer account.\n"
                "Use `/status` to see details.",
                parse_mode=ParseMode.MARKDOWN,
            )
            db.session.commit()
            return

        # Invalidate old unused codes
        old = TelegramGroupLinkCode.query.filter_by(
            telegram_group_id=group_id
        ).filter(
            TelegramGroupLinkCode.used_at.is_(None),
            TelegramGroupLinkCode.expires_at > datetime.utcnow(),
        ).all()
        for c in old:
            c.expires_at = datetime.utcnow()

        # Generate unique code
        code = TelegramGroupLinkCode.generate_code()
        while TelegramGroupLinkCode.query.filter_by(code=code).first():
            code = TelegramGroupLinkCode.generate_code()

        link_code = TelegramGroupLinkCode(
            code=code,
            telegram_group_id=group_id,
            telegram_group_title=group_title,
            created_by_telegram_user_id=str(user.id),
            expires_at=datetime.utcnow() + timedelta(minutes=12),
        )
        db.session.add(link_code)
        db.session.commit()

    _log_event(flask_app, group_id, "link_code_generated",
               f"Code generated by telegram user {user.id}",
               {"telegram_user_id": str(user.id)})

    frontend = Config.FRONTEND_URL
    await update.message.reply_text(
        f"🔗 *Group Link Code*\n\n"
        f"Group: *{group_title}*\n\n"
        f"Your verification code:\n"
        f"`{code}`\n\n"
        f"⏱ Expires in *12 minutes* — single use only.\n\n"
        f"Paste this code at:\n{frontend}/my-groups",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /status ──────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    flask_app = context.bot_data.get("flask_app")

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "Use `/status` inside your Telegram group.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    group_id = str(chat.id)

    perms = {}
    if flask_app:
        perms = await _check_and_store_permissions(context.bot, group_id, flask_app)

    tg = None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup
                tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        except Exception:
            pass

    if not tg:
        await update.message.reply_text(
            "ℹ️ This group is not yet registered.\n"
            "Run `/linkgroup` to get a link code.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    linked = "✅ Linked to dashboard" if tg.owner_user_id else "⏳ Not linked — run /linkgroup"
    bot_type = tg.linked_via_bot_type.capitalize()
    missing = [k for k, v in (perms or {}).items() if not v]
    perm_line = "✅ All permissions granted" if not missing else f"⚠️ Missing: {', '.join(missing)}"

    await update.message.reply_text(
        f"*Telegizer Status — {chat.title}*\n\n"
        f"🔗 {linked}\n"
        f"🤖 Bot type: {bot_type}\n"
        f"🛡️ Permissions: {perm_line}\n"
        + ("\n_Grant admin rights to the bot to enable all features._" if missing else ""),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Inline keyboard callbacks ────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    flask_app = context.bot_data.get("flask_app")
    frontend = Config.FRONTEND_URL
    bot_un = Config.TELEGRAM_BOT_USERNAME.strip("@").split("/")[-1]

    if data == "menu:my_groups":
        groups = []
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import TelegramGroup
                    groups = TelegramGroup.query.filter(
                        TelegramGroup.bot_status.in_(["active", "pending"])
                    ).order_by(TelegramGroup.created_at.desc()).limit(20).all()
                    groups = [{"title": g.title, "linked": bool(g.owner_user_id)} for g in groups]
            except Exception:
                pass

        if not groups:
            text = (
                "📋 *My Groups*\n\n"
                "No groups found yet.\n\n"
                "Add Telegizer Bot to a group, then run `/linkgroup` inside it."
            )
        else:
            lines = [f"📋 *Groups* ({len(groups)} total)\n"]
            for g in groups[:10]:
                em = "✅" if g["linked"] else "⏳"
                lines.append(f"{em} {g['title']}")
            text = "\n".join(lines) + f"\n\nManage all groups at {frontend}/my-groups"

        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    elif data == "menu:add_group":
        add_url = f"https://t.me/{bot_un}?startgroup=setup"
        await query.edit_message_text(
            "*Add Group to Telegizer*\n\n"
            "Steps:\n"
            "1️⃣ Click below to add the bot to your group\n"
            "2️⃣ Inside the group run `/linkgroup`\n"
            "3️⃣ Copy the code and paste it in the Dashboard\n\n"
            "Done! Your group will appear on the dashboard.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Bot to Group", url=add_url)],
                [InlineKeyboardButton("🖥️ Dashboard → Add Group", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    elif data == "menu:pending_groups":
        pending = []
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import TelegramGroup
                    pending = TelegramGroup.query.filter_by(
                        owner_user_id=None, bot_status="pending"
                    ).order_by(TelegramGroup.created_at.desc()).limit(20).all()
                    pending = [g.title for g in pending]
            except Exception:
                pass

        if not pending:
            text = "✅ No groups awaiting setup."
        else:
            lines = ["*Groups Awaiting Setup*\n\n"
                     "Telegizer has been added to these groups but not yet linked:\n"]
            for t in pending:
                lines.append(f"• {t}")
            lines.append(
                "\nTo link a group:\n"
                "1. Go to the group\n"
                "2. Run `/linkgroup`\n"
                "3. Paste the code in the Dashboard → Add Group"
            )
            text = "\n".join(lines)

        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("➕ Add Another Group", callback_data="menu:add_group")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    elif data == "menu:advanced":
        await query.edit_message_text(
            "*Advanced Options*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🤖 My Bots", callback_data="menu:my_bots"),
                    InlineKeyboardButton("🔌 Connect Own Bot", callback_data="menu:connect_bot"),
                ],
                [InlineKeyboardButton("⚙️ Settings", url=f"{frontend}/settings")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    elif data == "menu:my_bots":
        await query.edit_message_text(
            "*My Bots*\n\n"
            "1. 🟢 *Official Telegizer Bot* (shared)\n"
            "   Works in all your groups automatically.\n\n"
            "Connect and manage custom bots on the dashboard.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Manage Bots", url=f"{frontend}/my-bots")],
                [InlineKeyboardButton("🔌 Connect Own Bot", callback_data="menu:connect_bot")],
                [InlineKeyboardButton("« Back", callback_data="menu:advanced")],
            ]),
        )

    elif data == "menu:connect_bot":
        await query.edit_message_text(
            "*Connect Your Own Bot*\n\n"
            "White-label or agency users can use a custom bot token.\n\n"
            "Steps:\n"
            "1. Create a bot via @BotFather\n"
            "2. Copy the bot token\n"
            "3. Add it in Dashboard → My Bots → Connect Own Bot",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Connect on Dashboard", url=f"{frontend}/my-bots")],
                [InlineKeyboardButton("« Back", callback_data="menu:advanced")],
            ]),
        )

    elif data == "menu:support":
        await query.edit_message_text(
            f"*Telegizer Support*\n\n"
            f"Need help? Contact us via the dashboard.\n\n"
            f"{frontend}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=frontend)],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    elif data == "menu:main":
        pending_count = 0
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import TelegramGroup
                    pending_count = TelegramGroup.query.filter_by(
                        owner_user_id=None, bot_status="pending"
                    ).count()
            except Exception:
                pass

        keyboard = []
        if pending_count:
            keyboard.append([
                InlineKeyboardButton(
                    f"⚠️ {pending_count} Group(s) Awaiting Setup",
                    callback_data="menu:pending_groups",
                )
            ])
        keyboard += [
            [
                InlineKeyboardButton("📋 My Groups", callback_data="menu:my_groups"),
                InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group"),
            ],
            [
                InlineKeyboardButton("🖥️ Dashboard", url=frontend),
                InlineKeyboardButton("💬 Support", callback_data="menu:support"),
            ],
            [InlineKeyboardButton("⚙️ Advanced Options", callback_data="menu:advanced")],
        ]
        await query.edit_message_text(
            "*Telegizer — Telegram Growth & Management Hub*\n\nWhat would you like to do?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


# ─── Group events ──────────────────────────────────────────────────────────────

async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fired when the bot's own membership changes in a group."""
    flask_app = context.bot_data.get("flask_app")
    chat = update.effective_chat
    if not chat or chat.type == ChatType.PRIVATE:
        return

    my_member = update.my_chat_member
    if not my_member:
        return

    new_status = my_member.new_chat_member.status
    group_id = str(chat.id)
    group_title = chat.title or "Untitled Group"

    if new_status in ("member", "administrator"):
        # Bot was added
        added_by_id = str(my_member.from_user.id) if my_member.from_user else None
        _upsert_group(flask_app, group_id, group_title, chat.username)
        _log_event(flask_app, group_id, "bot_added",
                   f"Bot added to {group_title}",
                   {"added_by_telegram_id": added_by_id, "group_title": group_title})
        if flask_app:
            await _check_and_store_permissions(context.bot, group_id, flask_app)

        bot_un = Config.TELEGRAM_BOT_USERNAME.strip("@").split("/")[-1]
        try:
            await chat.send_message(
                f"✅ *Telegizer connected successfully.*\n\n"
                f"Open @{bot_un} to complete setup and manage this group.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc:
            _log.warning("Could not send group welcome: %s", exc)

    elif new_status in ("left", "kicked"):
        # Bot was removed
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import db, TelegramGroup
                    tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                    if tg:
                        tg.bot_status = "removed"
                        db.session.commit()
            except Exception:
                pass
        _log_event(flask_app, group_id, "bot_removed", f"Bot removed from {group_title}")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle group messages — update last_activity and dispatch custom commands."""
    chat = update.effective_chat
    message = update.message
    flask_app = context.bot_data.get("flask_app")
    if not chat or chat.type == ChatType.PRIVATE or not message or not flask_app:
        return

    group_id = str(chat.id)
    text = (message.text or "").strip()

    # Update last_activity
    try:
        with flask_app.app_context():
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if tg:
                tg.last_activity = datetime.utcnow()
                db.session.commit()
    except Exception:
        pass

    # Dispatch custom commands
    if text.startswith("/"):
        cmd_raw = text.split()[0].lstrip("/").split("@")[0].lower()
        cmd_obj = None
        try:
            with flask_app.app_context():
                from .models import CustomCommand
                cmd_obj = CustomCommand.query.filter_by(
                    telegram_group_id=group_id,
                    command=cmd_raw,
                    enabled=True,
                ).first()
                if cmd_obj:
                    # detach from session before exiting context
                    cmd_data = {
                        "response_text": cmd_obj.response_text,
                        "response_type": cmd_obj.response_type,
                        "buttons": cmd_obj.buttons,
                    }
        except Exception:
            cmd_data = None
            cmd_obj = None

        if cmd_obj and cmd_data:
            keyboard = None
            if cmd_data["buttons"]:
                rows = []
                for row in cmd_data["buttons"]:
                    btn_row = [InlineKeyboardButton(b["text"], url=b["url"]) for b in row if b.get("url")]
                    if btn_row:
                        rows.append(btn_row)
                if rows:
                    keyboard = InlineKeyboardMarkup(rows)

            parse_mode = ParseMode.MARKDOWN if cmd_data["response_type"] == "markdown" else None
            try:
                await message.reply_text(
                    cmd_data["response_text"],
                    parse_mode=parse_mode,
                    reply_markup=keyboard,
                )
            except Exception as exc:
                _log.warning("Custom command reply failed: %s", exc)

            _log_event(flask_app, group_id, "command_triggered",
                       f"/{cmd_raw} triggered",
                       {"command": cmd_raw,
                        "user_id": str(message.from_user.id) if message.from_user else None})


# ─── OfficialBotRunner ────────────────────────────────────────────────────────

class OfficialBotRunner:
    def __init__(self):
        self.application = None
        self.loop = None
        self._thread = None
        self._running = False
        self._lock = threading.Lock()

    def start(self, flask_app):
        token = Config.TELEGRAM_BOT_TOKEN
        if not token:
            _log.warning(
                "[OfficialBot] TELEGRAM_BOT_TOKEN is not set — official bot disabled. "
                "Add it to your Railway environment variables."
            )
            return

        with self._lock:
            if self._running:
                return
            self._thread = threading.Thread(
                target=self._run_loop,
                args=(flask_app,),
                daemon=True,
                name="telegizer-official-bot",
            )
            self._thread.start()
            self._running = True
            _log.info("[OfficialBot] Thread started — token prefix: %s...", token[:10])

    def _run_loop(self, flask_app):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._poll(flask_app))
        except Exception as exc:
            _log.error("[OfficialBot] Fatal: %s", exc, exc_info=True)
        finally:
            self._running = False
            _log.info("[OfficialBot] Thread exiting")

    async def _poll(self, flask_app):
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

        # Store flask_app — handlers call with flask_app.app_context() themselves
        self.application.bot_data["flask_app"] = flask_app

        a = self.application
        a.add_handler(CommandHandler("start", cmd_start))
        a.add_handler(CommandHandler("help", cmd_help))
        a.add_handler(CommandHandler("linkgroup", cmd_linkgroup))
        a.add_handler(CommandHandler("status", cmd_status))
        a.add_handler(CallbackQueryHandler(callback_handler))

        # Bot membership changes (added / removed from group)
        from telegram.ext import ChatMemberHandler
        a.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

        # Group messages for custom commands + activity tracking
        a.add_handler(
            MessageHandler(
                filters.Chat(chat_type=[ChatType.GROUP, ChatType.SUPERGROUP]) & filters.TEXT,
                on_message,
            )
        )

        # Set bot command menu
        try:
            await self.application.bot.set_my_commands([
                BotCommand("start", "Open Telegizer companion hub"),
                BotCommand("help", "Setup guide"),
                BotCommand("linkgroup", "Generate group link code (use in group)"),
                BotCommand("status", "Check bot status (use in group)"),
            ])
            _log.info("[OfficialBot] Bot commands menu set")
        except Exception as exc:
            _log.warning("[OfficialBot] set_my_commands failed: %s", exc)

        _log.info("[OfficialBot] Starting long-polling…")
        await self.application.run_polling(drop_pending_updates=True)


_runner = OfficialBotRunner()


def start_official_bot(flask_app):
    _runner.start(flask_app)
