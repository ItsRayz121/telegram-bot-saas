"""
Official Telegizer shared bot — serves all users/groups from one token.

Architecture:
- Single python-telegram-bot Application instance (long-polling)
- Runs in a background thread inside the Flask process
- All group settings are isolated in the DB per telegram_group_id
- No cross-user data leakage
"""

import asyncio
import logging
import threading
import secrets
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, MenuButtonCommands,
)
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

from .config import Config

_log = logging.getLogger(__name__)

_official_bot_instance = None  # OfficialBotRunner singleton
_official_bot_lock = threading.Lock()


# ─── Helper: log bot event ────────────────────────────────────────────────────

def _log_event(app_ctx, group_id, event_type, message=None, meta=None):
    """Fire-and-forget DB event log (runs in calling thread with app context)."""
    try:
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
        _log.warning("BotEvent log failed: %s", exc)
        try:
            from .models import db
            db.session.rollback()
        except Exception:
            pass


# ─── Permission checker ───────────────────────────────────────────────────────

async def _check_and_store_permissions(bot, telegram_group_id: str, app_ctx):
    """Fetch bot member info and persist permission flags."""
    try:
        member = await bot.get_chat_member(chat_id=int(telegram_group_id), user_id=bot.id)
        perms = {
            "delete_messages": getattr(member, "can_delete_messages", False),
            "ban_users": getattr(member, "can_restrict_members", False),
            "pin_messages": getattr(member, "can_pin_messages", False),
            "manage_topics": getattr(member, "can_manage_topics", False),
        }
        with app_ctx:
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=telegram_group_id).first()
            if tg:
                tg.bot_permissions = perms
                tg.bot_status = "active"
                db.session.commit()
        return perms
    except Exception as exc:
        _log.warning("Permission check failed for %s: %s", telegram_group_id, exc)
        return {}


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return

    app_ctx = context.bot_data.get("flask_app_ctx")
    user = update.effective_user
    first = user.first_name or "there"
    frontend = Config.FRONTEND_URL

    # Detect pending (unlinked) groups for this telegram user
    pending_groups = []
    if app_ctx:
        with app_ctx:
            from .models import TelegramGroup
            pending_groups = TelegramGroup.query.filter_by(
                owner_user_id=None,
                bot_status="pending",
            ).all()
            # Narrow to groups where this telegram user triggered the add
            # (we store creator via bot_events metadata)
            from .models import BotEvent
            my_group_ids = {
                e.telegram_group_id for e in BotEvent.query.filter_by(
                    event_type="bot_added",
                ).filter(
                    BotEvent.metadata_.op("->>")(  # type: ignore[attr-defined]
                        "added_by_telegram_id"
                    ) == str(user.id)
                ).all()
            }
            pending_groups = [g for g in pending_groups if g.telegram_group_id in my_group_ids]

    text = (
        f"👋 *Welcome to Telegizer, {first}!*\n\n"
        "Your all-in-one Telegram Group Management Hub.\n\n"
        "Manage groups, set up automation, and grow your community — "
        "all from one place."
    )

    keyboard = [
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

    if pending_groups:
        keyboard.insert(0, [
            InlineKeyboardButton(
                f"⚠️ {len(pending_groups)} Group(s) Awaiting Setup",
                callback_data="menu:pending_groups",
            )
        ])

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─── /help ────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    frontend = Config.FRONTEND_URL
    text = (
        "*Telegizer Help*\n\n"
        "*Setup your group:*\n"
        "1. Add @TelegizerBot to your Telegram group\n"
        "2. In the group run `/linkgroup`\n"
        "3. Copy the code shown\n"
        "4. Paste it in the Dashboard → Add Group\n\n"
        "*Commands:*\n"
        "`/linkgroup` — Generate a group link code (use in group)\n"
        "`/status` — Check bot status & permissions (use in group)\n"
        "`/start` — Open companion hub (private chat)\n\n"
        f"*Dashboard:* {frontend}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── /linkgroup ───────────────────────────────────────────────────────────────

async def cmd_linkgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group-only: generate a 10-min single-use link code."""
    chat = update.effective_chat
    user = update.effective_user
    app_ctx = context.bot_data.get("flask_app_ctx")

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "⚠️ Use `/linkgroup` inside your Telegram group, not in private chat.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not app_ctx:
        await update.message.reply_text("⚠️ Service temporarily unavailable. Try again in a moment.")
        return

    group_id = str(chat.id)
    group_title = chat.title or "Untitled Group"

    with app_ctx:
        from .models import db, TelegramGroup, TelegramGroupLinkCode

        # Ensure the group record exists
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

        # If already linked, show status
        if tg.owner_user_id and tg.bot_status == "active":
            await update.message.reply_text(
                "✅ This group is already linked to a Telegizer account.\n"
                "Use `/status` to view details.",
                parse_mode=ParseMode.MARKDOWN,
            )
            db.session.commit()
            return

        # Expire old unused codes for this group
        old_codes = TelegramGroupLinkCode.query.filter_by(
            telegram_group_id=group_id,
        ).filter(
            TelegramGroupLinkCode.used_at.is_(None),
            TelegramGroupLinkCode.expires_at > datetime.utcnow(),
        ).all()
        for c in old_codes:
            c.expires_at = datetime.utcnow()  # Invalidate

        # Generate fresh code
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

        _log_event(app_ctx, group_id, "link_code_generated", f"Code generated by {user.id}", {
            "code": code,
            "telegram_user_id": str(user.id),
        })

    frontend = Config.FRONTEND_URL
    text = (
        f"🔗 *Group Link Code*\n\n"
        f"Group: *{group_title}*\n\n"
        f"Your verification code:\n"
        f"`{code}`\n\n"
        f"⏱️ Expires in *12 minutes*. Single use only.\n\n"
        f"Paste this code at:\n{frontend}/add-group"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── /status ──────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    app_ctx = context.bot_data.get("flask_app_ctx")

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "Use `/status` inside your Telegram group.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    group_id = str(chat.id)

    if app_ctx:
        perms = await _check_and_store_permissions(context.bot, group_id, app_ctx)
        with app_ctx:
            from .models import TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
    else:
        tg = None
        perms = {}

    if not tg:
        await update.message.reply_text(
            "ℹ️ This group is not yet registered with Telegizer.\n"
            "Run `/linkgroup` to generate a link code.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    linked = "✅ Linked" if tg.owner_user_id else "⏳ Not linked to dashboard"
    bot_type = tg.linked_via_bot_type.capitalize()

    missing = [k for k, v in (perms or {}).items() if not v]
    perm_status = "✅ All permissions granted" if not missing else f"⚠️ Missing: {', '.join(missing)}"

    text = (
        f"*Telegizer Status — {chat.title}*\n\n"
        f"🔗 Link status: {linked}\n"
        f"🤖 Bot type: {bot_type}\n"
        f"🛡️ Permissions: {perm_status}\n"
    )
    if missing:
        text += "\nGrant admin permissions to enable all features."

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── Callback query handler (inline keyboard) ─────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    app_ctx = context.bot_data.get("flask_app_ctx")
    frontend = Config.FRONTEND_URL
    user = update.effective_user

    if data == "menu:my_groups":
        groups = []
        if app_ctx:
            with app_ctx:
                from .models import TelegramGroup
                # Only show groups this telegram user has in pending state
                # or groups linked to their account (by telegram_user in bot events)
                from .models import BotEvent
                my_group_ids = {
                    e.telegram_group_id for e in BotEvent.query.filter_by(
                        event_type="bot_added",
                    ).filter(
                        BotEvent.metadata_.op("->>")(  # type: ignore[attr-defined]
                            "added_by_telegram_id"
                        ) == str(user.id)
                    ).all()
                }
                groups = TelegramGroup.query.filter(
                    TelegramGroup.telegram_group_id.in_(my_group_ids)
                ).all() if my_group_ids else []

        if not groups:
            text = (
                "📋 *My Groups*\n\n"
                "No groups found.\n\n"
                "Add Telegizer Bot to a group, then run `/linkgroup` inside it."
            )
            keyboard = [[InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group")],
                        [InlineKeyboardButton("« Back", callback_data="menu:main")]]
        else:
            lines = [f"📋 *My Groups* ({len(groups)} total)\n"]
            for g in groups[:10]:
                status_emoji = "✅" if g.owner_user_id else "⏳"
                lines.append(f"{status_emoji} {g.title}")
            text = "\n".join(lines)
            text += f"\n\nManage your groups at {frontend}/my-groups"
            keyboard = [
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]

        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "menu:add_group":
        bot_username = Config.TELEGRAM_BOT_USERNAME.lstrip("@").lstrip("http://t.me/").lstrip("https://t.me/")
        add_url = f"https://t.me/{bot_username}?startgroup=setup"
        text = (
            "*Add Group to Telegizer*\n\n"
            "Steps:\n"
            "1️⃣ Click below to add Telegizer Bot to your group\n"
            "2️⃣ Once added, run `/linkgroup` inside the group\n"
            "3️⃣ Copy the code and paste it in the Dashboard\n\n"
            "That's it! Your group will be live on the dashboard."
        )
        keyboard = [
            [InlineKeyboardButton("➕ Add Bot to Group", url=add_url)],
            [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/add-group")],
            [InlineKeyboardButton("« Back", callback_data="menu:main")],
        ]
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "menu:pending_groups":
        pending = []
        if app_ctx:
            with app_ctx:
                from .models import TelegramGroup, BotEvent
                my_group_ids = {
                    e.telegram_group_id for e in BotEvent.query.filter_by(
                        event_type="bot_added",
                    ).filter(
                        BotEvent.metadata_.op("->>")(  # type: ignore[attr-defined]
                            "added_by_telegram_id"
                        ) == str(user.id)
                    ).all()
                }
                pending = TelegramGroup.query.filter(
                    TelegramGroup.telegram_group_id.in_(my_group_ids),
                    TelegramGroup.owner_user_id.is_(None),
                ).all() if my_group_ids else []

        if not pending:
            text = "✅ No groups awaiting setup."
        else:
            lines = ["*Groups Awaiting Setup*\n\n"
                     "Telegizer has been added to the following groups:\n"]
            for g in pending:
                lines.append(f"• {g.title}")
            lines.append(
                "\nTo link them to your dashboard account:\n"
                "1. Go to the group\n"
                "2. Run `/linkgroup`\n"
                "3. Paste the code in the Dashboard"
            )
            text = "\n".join(lines)

        keyboard = [
            [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/add-group")],
            [InlineKeyboardButton("➕ Add Another Group", callback_data="menu:add_group")],
            [InlineKeyboardButton("« Back", callback_data="menu:main")],
        ]
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "menu:advanced":
        text = "*Advanced Options*"
        keyboard = [
            [
                InlineKeyboardButton("🤖 My Bots", callback_data="menu:my_bots"),
                InlineKeyboardButton("🔌 Connect Own Bot", callback_data="menu:connect_bot"),
            ],
            [InlineKeyboardButton("⚙️ Settings", url=f"{frontend}/settings")],
            [InlineKeyboardButton("« Back", callback_data="menu:main")],
        ]
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "menu:my_bots":
        custom_bots = []
        if app_ctx:
            with app_ctx:
                from .models import CustomBot, BotEvent
                # Try to find user by their telegram id via BotEvent history
                # (We don't store telegram_user_id <-> website user mapping directly,
                # so we show a dashboard link instead)
                pass

        text = (
            "*My Bots*\n\n"
            "1. 🟢 *Official Telegizer Bot* (shared)\n"
            "   Works in all your groups automatically.\n\n"
            "Manage custom bots and see connected groups on the dashboard."
        )
        keyboard = [
            [InlineKeyboardButton("🖥️ Manage Bots", url=f"{frontend}/my-bots")],
            [InlineKeyboardButton("🔌 Connect Own Bot", callback_data="menu:connect_bot")],
            [InlineKeyboardButton("« Back", callback_data="menu:advanced")],
        ]
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "menu:connect_bot":
        text = (
            "*Connect Your Own Bot*\n\n"
            "White-label or agency users can connect a custom bot token.\n\n"
            "Steps:\n"
            "1. Create a bot via @BotFather\n"
            "2. Copy the bot token\n"
            "3. Add it in the Dashboard → My Bots → Connect Own Bot"
        )
        keyboard = [
            [InlineKeyboardButton("🖥️ Connect on Dashboard", url=f"{frontend}/my-bots")],
            [InlineKeyboardButton("« Back", callback_data="menu:advanced")],
        ]
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "menu:support":
        text = (
            "*Telegizer Support*\n\n"
            "Need help? We're here.\n\n"
            f"📖 Documentation & guides: {frontend}/help\n"
            "💬 Contact support via the dashboard."
        )
        keyboard = [
            [InlineKeyboardButton("🖥️ Open Dashboard", url=frontend)],
            [InlineKeyboardButton("« Back", callback_data="menu:main")],
        ]
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "menu:main":
        # Re-render main menu
        text = (
            "👋 *Telegizer — Telegram Growth & Management Hub*\n\n"
            "What would you like to do?"
        )
        keyboard = [
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
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


# ─── Group event handlers ──────────────────────────────────────────────────────

async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fired when the official bot is added to a group."""
    chat = update.effective_chat
    app_ctx = context.bot_data.get("flask_app_ctx")

    if not chat or chat.type == ChatType.PRIVATE:
        return

    group_id = str(chat.id)
    group_title = chat.title or "Untitled Group"

    # Identify who added the bot
    added_by_id = None
    if update.message and update.message.from_user:
        added_by_id = str(update.message.from_user.id)

    if app_ctx:
        with app_ctx:
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if not tg:
                tg = TelegramGroup(
                    telegram_group_id=group_id,
                    title=group_title,
                    username=chat.username,
                    bot_status="pending",
                )
                db.session.add(tg)
            else:
                tg.title = group_title
                tg.bot_status = "pending"
            db.session.commit()

        _log_event(app_ctx, group_id, "bot_added", f"Bot added to {group_title}", {
            "added_by_telegram_id": added_by_id,
            "group_title": group_title,
        })

        # Check permissions
        await _check_and_store_permissions(context.bot, group_id, app_ctx)

    # Minimal group message — no spam
    await update.effective_chat.send_message(
        "✅ *Telegizer connected successfully.*\n\n"
        f"Open @{Config.TELEGRAM_BOT_USERNAME.lstrip('@').lstrip('http://t.me/').lstrip('https://t.me/')} "
        "to complete setup and manage this group.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def on_bot_removed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fired when the official bot is removed from a group."""
    chat = update.effective_chat
    app_ctx = context.bot_data.get("flask_app_ctx")

    if not chat or chat.type == ChatType.PRIVATE:
        return

    group_id = str(chat.id)

    if app_ctx:
        with app_ctx:
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if tg:
                tg.bot_status = "removed"
                db.session.commit()

        _log_event(app_ctx, group_id, "bot_removed", f"Bot removed from group {group_id}", {})


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in groups — trigger custom commands and update last_activity."""
    chat = update.effective_chat
    message = update.message
    app_ctx = context.bot_data.get("flask_app_ctx")

    if not chat or chat.type == ChatType.PRIVATE or not message:
        return

    group_id = str(chat.id)
    text = (message.text or "").strip()

    if not app_ctx:
        return

    # Update last_activity
    with app_ctx:
        from .models import db, TelegramGroup
        tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        if tg:
            tg.last_activity = datetime.utcnow()
            db.session.commit()

    # Handle custom commands (/rules, /support, etc.)
    if text.startswith("/"):
        cmd_raw = text.split()[0].lstrip("/").split("@")[0].lower()
        with app_ctx:
            from .models import CustomCommand
            cmd_obj = CustomCommand.query.filter_by(
                telegram_group_id=group_id,
                command=cmd_raw,
                enabled=True,
            ).first()

        if cmd_obj:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = None
            if cmd_obj.buttons:
                rows = []
                for row in cmd_obj.buttons:
                    btn_row = [InlineKeyboardButton(b["text"], url=b["url"]) for b in row if b.get("url")]
                    if btn_row:
                        rows.append(btn_row)
                if rows:
                    keyboard = InlineKeyboardMarkup(rows)

            parse_mode = ParseMode.MARKDOWN if cmd_obj.response_type == "markdown" else None
            await message.reply_text(
                cmd_obj.response_text,
                parse_mode=parse_mode,
                reply_markup=keyboard,
            )

            _log_event(app_ctx, group_id, "command_triggered", f"/{cmd_raw} triggered", {
                "command": cmd_raw,
                "user_id": str(message.from_user.id) if message.from_user else None,
            })


# ─── OfficialBotRunner ────────────────────────────────────────────────────────

class OfficialBotRunner:
    def __init__(self):
        self.application = None
        self.loop = None
        self._thread = None
        self._running = False

    def start(self, flask_app):
        """Start the official bot in a background thread."""
        global _official_bot_instance
        token = Config.TELEGRAM_BOT_TOKEN
        if not token:
            _log.warning("[OfficialBot] TELEGRAM_BOT_TOKEN not set — official bot not started")
            return

        with _official_bot_lock:
            if self._running:
                return

            self._thread = threading.Thread(
                target=self._run_loop,
                args=(flask_app,),
                daemon=True,
                name="official-bot",
            )
            self._thread.start()
            self._running = True
            _official_bot_instance = self
            _log.info("[OfficialBot] Started in background thread")

    def stop(self):
        self._running = False
        if self.application and self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.application.stop(), self.loop)

    def _run_loop(self, flask_app):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start_polling(flask_app))
        except Exception as exc:
            _log.error("[OfficialBot] Fatal error: %s", exc, exc_info=True)
        finally:
            self.loop.close()
            self._running = False

    async def _start_polling(self, flask_app):
        token = Config.TELEGRAM_BOT_TOKEN
        app_ctx = flask_app.app_context()

        self.application = (
            Application.builder()
            .token(token)
            .build()
        )

        # Inject Flask app context so handlers can reach the DB
        self.application.bot_data["flask_app_ctx"] = app_ctx

        # Register handlers
        self.application.add_handler(CommandHandler("start", cmd_start))
        self.application.add_handler(CommandHandler("help", cmd_help))
        self.application.add_handler(CommandHandler("linkgroup", cmd_linkgroup))
        self.application.add_handler(CommandHandler("status", cmd_status))
        self.application.add_handler(CallbackQueryHandler(callback_handler))

        # Group member updates (bot added/removed)
        self.application.add_handler(
            MessageHandler(
                filters.StatusUpdate.NEW_CHAT_MEMBERS,
                on_bot_added,
            )
        )
        self.application.add_handler(
            MessageHandler(
                filters.StatusUpdate.LEFT_CHAT_MEMBER,
                on_bot_removed,
            )
        )

        # All group messages (custom commands + activity tracking)
        self.application.add_handler(
            MessageHandler(
                filters.Chat(chat_type=[ChatType.GROUP, ChatType.SUPERGROUP]) & filters.TEXT,
                on_message,
            )
        )

        # Set bot commands menu
        try:
            await self.application.bot.set_my_commands([
                BotCommand("start", "Open Telegizer companion hub"),
                BotCommand("help", "Setup guide and help"),
                BotCommand("linkgroup", "Generate group link code (use in group)"),
                BotCommand("status", "Check bot status & permissions (use in group)"),
            ])
        except Exception as exc:
            _log.warning("[OfficialBot] Failed to set commands: %s", exc)

        _log.info("[OfficialBot] Polling started")
        await self.application.run_polling(drop_pending_updates=True)


# ─── Module-level singleton start ─────────────────────────────────────────────

_runner = OfficialBotRunner()


def start_official_bot(flask_app):
    """Called from app.py after Flask is ready."""
    _runner.start(flask_app)
