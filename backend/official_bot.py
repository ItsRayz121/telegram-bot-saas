"""
Official Telegizer shared bot.

Key design decisions:
- flask_app (not app_context) stored in bot_data; every handler creates
  a FRESH with flask_app.app_context() per call.
- /linkgroup does NOT post the verification code in the group.
  It creates a pending record and attempts to DM the code to the
  user privately. The code is NEVER visible to others in the group.
- Private /start shows only the pending groups that the current
  Telegram user initiated (via created_by_telegram_user_id).
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatType, ParseMode
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ChatMemberHandler, ContextTypes, filters,
)

from .config import Config

_log = logging.getLogger(__name__)


# ─── Tiny DB helpers ──────────────────────────────────────────────────────────

def _with_app(flask_app, fn):
    """Run fn(session) inside a fresh app context. Returns fn's return value."""
    with flask_app.app_context():
        return fn()


def _log_event(flask_app, group_id, event_type, message=None, meta=None):
    try:
        with flask_app.app_context():
            from .models import db, BotEvent
            db.session.add(BotEvent(
                telegram_group_id=str(group_id) if group_id else None,
                event_type=event_type,
                message=message,
                metadata_=meta or {},
            ))
            db.session.commit()
    except Exception as exc:
        _log.debug("BotEvent log failed (%s): %s", event_type, exc)


def _upsert_group(flask_app, group_id: str, title: str, username=None):
    try:
        with flask_app.app_context():
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if not tg:
                tg = TelegramGroup(
                    telegram_group_id=group_id, title=title,
                    username=username, bot_status="pending",
                )
                db.session.add(tg)
            else:
                tg.title = title
            db.session.commit()
    except Exception as exc:
        _log.debug("_upsert_group failed: %s", exc)


async def _refresh_permissions(bot, group_id: str, flask_app):
    try:
        me = await bot.get_chat_member(chat_id=int(group_id), user_id=bot.id)
        perms = {
            "delete_messages": getattr(me, "can_delete_messages", False),
            "ban_users": getattr(me, "can_restrict_members", False),
            "pin_messages": getattr(me, "can_pin_messages", False),
            "manage_topics": getattr(me, "can_manage_topics", False),
        }
        with flask_app.app_context():
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if tg:
                tg.bot_permissions = perms
                tg.bot_status = "active"
                db.session.commit()
        return perms
    except Exception:
        return {}


def _bot_username():
    raw = Config.TELEGRAM_BOT_USERNAME or "telegizer_bot"
    return raw.strip().lstrip("@").split("/")[-1]


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Private companion hub — show pending groups for this Telegram user."""
    if update.effective_chat.type != ChatType.PRIVATE:
        return

    flask_app = context.bot_data.get("flask_app")
    user = update.effective_user
    first = user.first_name or "there"
    frontend = Config.FRONTEND_URL

    # Find pending link codes created by this exact Telegram user
    pending_groups = []
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroupLinkCode, TelegramGroup
                codes = TelegramGroupLinkCode.query.filter_by(
                    created_by_telegram_user_id=str(user.id),
                    used_at=None,
                ).filter(
                    TelegramGroupLinkCode.expires_at > datetime.utcnow()
                ).all()
                for c in codes:
                    tg = TelegramGroup.query.filter_by(
                        telegram_group_id=c.telegram_group_id
                    ).first()
                    if tg and not tg.owner_user_id:
                        pending_groups.append({
                            "title": tg.title,
                            "code": c.code,
                            "group_id": tg.telegram_group_id,
                        })
        except Exception as exc:
            _log.debug("pending_groups fetch failed: %s", exc)

    text = (
        f"👋 *Welcome to Telegizer, {first}!*\n\n"
        "Your all-in-one Telegram Group Management Hub.\n\n"
        "Manage groups, automate moderation, and grow your community — "
        "all from one place."
    )

    keyboard = []

    if pending_groups:
        keyboard.append([
            InlineKeyboardButton(
                f"⚠️ {len(pending_groups)} Group(s) Awaiting Setup",
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
    bot_un = _bot_username()
    frontend = Config.FRONTEND_URL
    await update.message.reply_text(
        "*Telegizer Help*\n\n"
        "*How to link a group:*\n"
        f"1. Add @{bot_un} to your Telegram group as admin\n"
        "2. Run `/linkgroup` inside the group\n"
        f"3. The bot will DM you the secure code here in @{bot_un}\n"
        "4. Paste the code at the Dashboard → Add Group\n\n"
        "*Group commands:*\n"
        "`/linkgroup` — start the link flow (run in group)\n"
        "`/status` — check bot status & permissions\n\n"
        "*Private commands:*\n"
        "`/start` — open companion hub\n\n"
        f"Dashboard: {frontend}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /linkgroup ───────────────────────────────────────────────────────────────

async def cmd_linkgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Group-only. Creates a secure pending link request.
    The verification code is sent PRIVATELY to the user — never posted in the group.
    """
    chat = update.effective_chat
    user = update.effective_user
    flask_app = context.bot_data.get("flask_app")

    # Must be used in a group
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "⚠️ Use `/linkgroup` *inside your Telegram group*, not here.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not flask_app:
        await update.message.reply_text("⚠️ Service temporarily unavailable. Try again shortly.")
        return

    # Only admins/creators may initiate
    try:
        cm = await context.bot.get_chat_member(chat.id, user.id)
        if cm.status not in ("creator", "administrator"):
            await update.message.reply_text(
                "❌ Only group admins can link this group."
            )
            return
    except Exception:
        pass

    group_id = str(chat.id)
    group_title = chat.title or "Untitled Group"
    bot_un = _bot_username()

    with flask_app.app_context():
        from .models import db, TelegramGroup, TelegramGroupLinkCode

        # Ensure group record exists
        tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        if not tg:
            tg = TelegramGroup(
                telegram_group_id=group_id, title=group_title,
                username=chat.username, bot_status="pending",
            )
            db.session.add(tg)
            db.session.flush()

        # Already linked?
        if tg.owner_user_id and tg.bot_status == "active":
            await update.message.reply_text(
                "✅ This group is already linked to a Telegizer account.\n"
                "Use `/status` to view details.",
                parse_mode=ParseMode.MARKDOWN,
            )
            db.session.commit()
            return

        # Invalidate any old unused codes for this group
        TelegramGroupLinkCode.query.filter_by(
            telegram_group_id=group_id,
            used_at=None,
        ).filter(
            TelegramGroupLinkCode.expires_at > datetime.utcnow()
        ).update({"expires_at": datetime.utcnow()})

        # Generate unique code
        code = TelegramGroupLinkCode.generate_code()
        while TelegramGroupLinkCode.query.filter_by(code=code).first():
            code = TelegramGroupLinkCode.generate_code()

        link_code = TelegramGroupLinkCode(
            code=code,
            telegram_group_id=group_id,
            telegram_group_title=group_title,
            created_by_telegram_user_id=str(user.id),
            expires_at=datetime.utcnow() + timedelta(minutes=15),
        )
        db.session.add(link_code)
        db.session.commit()

    _log_event(flask_app, group_id, "link_code_generated",
               f"Code generated by tg user {user.id}",
               {"telegram_user_id": str(user.id)})

    # ── Step 1: Post minimal non-revealing message in the group ──────────────
    await update.message.reply_text(
        f"✅ *Link request created.*\n\n"
        f"Open @{bot_un} privately to complete secure setup.\n"
        "_Your verification code will only be shown there._",
        parse_mode=ParseMode.MARKDOWN,
    )

    # ── Step 2: DM the code privately to the user ────────────────────────────
    frontend = Config.FRONTEND_URL
    private_text = (
        f"🔐 *Your Group Link Code*\n\n"
        f"Group: *{group_title}*\n\n"
        f"Verification code:\n"
        f"`{code}`\n\n"
        f"⏱ Expires in *15 minutes* — single use only.\n\n"
        f"Paste this code at:\n"
        f"{frontend}/my-groups\n\n"
        f"_This code is private — do not share it._"
    )

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=private_text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except (Forbidden, BadRequest):
        # User hasn't started a private chat with the bot yet
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"⚠️ @{user.username or user.first_name}, I couldn't send you the code privately.\n\n"
                    f"Please start a private chat with @{bot_un} first, "
                    "then run `/linkgroup` again here."
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass
    except Exception as exc:
        _log.warning("DM code failed for user %s: %s", user.id, exc)


# ─── /status ──────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    flask_app = context.bot_data.get("flask_app")

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "Use `/status` *inside your Telegram group*.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    group_id = str(chat.id)
    perms = {}
    if flask_app:
        perms = await _refresh_permissions(context.bot, group_id, flask_app)

    tg = None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroup
                tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        except Exception:
            pass

    if not tg:
        bot_un = _bot_username()
        await update.message.reply_text(
            "ℹ️ This group is not yet registered.\n"
            f"Run `/linkgroup` here, then open @{bot_un} privately.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    linked = "✅ Linked to dashboard" if tg.owner_user_id else "⏳ Not linked — run /linkgroup"
    missing = [k for k, v in (perms or {}).items() if not v]
    perm_line = "✅ All permissions granted" if not missing else f"⚠️ Missing: {', '.join(missing)}"

    await update.message.reply_text(
        f"*Telegizer Status — {chat.title}*\n\n"
        f"🔗 {linked}\n"
        f"🤖 Bot: {tg.linked_via_bot_type.capitalize()}\n"
        f"🛡️ Permissions: {perm_line}"
        + ("\n\n_Grant admin rights to enable all features._" if missing else ""),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Inline keyboard callbacks ────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    flask_app = context.bot_data.get("flask_app")
    frontend = Config.FRONTEND_URL
    user = update.effective_user
    bot_un = _bot_username()

    # ── pending_groups ────────────────────────────────────────────────────────
    if data == "menu:pending_groups":
        pending = []
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import TelegramGroupLinkCode, TelegramGroup
                    codes = TelegramGroupLinkCode.query.filter_by(
                        created_by_telegram_user_id=str(user.id),
                        used_at=None,
                    ).filter(
                        TelegramGroupLinkCode.expires_at > datetime.utcnow()
                    ).all()
                    for c in codes:
                        tg = TelegramGroup.query.filter_by(
                            telegram_group_id=c.telegram_group_id
                        ).first()
                        if tg and not tg.owner_user_id:
                            pending.append({"title": tg.title, "code": c.code})
            except Exception:
                pass

        if not pending:
            text = (
                "✅ *No groups awaiting setup.*\n\n"
                "All your groups are already linked, or your codes have expired.\n"
                "Run `/linkgroup` in a group to generate a new code."
            )
            keyboard = [[InlineKeyboardButton("« Back", callback_data="menu:main")]]
        else:
            lines = ["*Groups Awaiting Setup*\n\n"
                     "You have the following groups ready to link:\n"]
            for p in pending:
                lines.append(f"• *{p['title']}*")
            lines.append(
                "\nCopy the code shown below and paste it at the Dashboard → Add Group."
            )
            text = "\n".join(lines)

            # Show each code as a button users can copy-paste
            code_buttons = [
                [InlineKeyboardButton(
                    f"📋 {p['title']} — Code: {p['code']}",
                    callback_data=f"show_code:{p['code']}",
                )]
                for p in pending[:5]
            ]
            keyboard = code_buttons + [
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("➕ Add Another Group", callback_data="menu:add_group")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]

        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # ── show individual code ──────────────────────────────────────────────────
    elif data.startswith("show_code:"):
        code = data.split(":", 1)[1]
        # Verify this code belongs to this user before showing it
        valid = False
        group_title = ""
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import TelegramGroupLinkCode
                    lc = TelegramGroupLinkCode.query.filter_by(
                        code=code,
                        created_by_telegram_user_id=str(user.id),
                        used_at=None,
                    ).filter(
                        TelegramGroupLinkCode.expires_at > datetime.utcnow()
                    ).first()
                    if lc:
                        valid = True
                        group_title = lc.telegram_group_title or ""
            except Exception:
                pass

        if not valid:
            await query.edit_message_text(
                "⚠️ This code has expired or already been used. "
                "Run `/linkgroup` in the group again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Back", callback_data="menu:pending_groups")]
                ]),
            )
            return

        await query.edit_message_text(
            f"🔐 *Link Code for {group_title}*\n\n"
            f"`{code}`\n\n"
            f"Paste this at:\n{frontend}/my-groups\n\n"
            "_Single use · expires in 15 min_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:pending_groups")],
            ]),
        )

    # ── my_groups ─────────────────────────────────────────────────────────────
    elif data == "menu:my_groups":
        await query.edit_message_text(
            "📋 *My Groups*\n\n"
            "View and manage all your linked groups on the dashboard.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open My Groups", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    # ── add_group ─────────────────────────────────────────────────────────────
    elif data == "menu:add_group":
        add_url = f"https://t.me/{bot_un}?startgroup=setup"
        await query.edit_message_text(
            "*Add Group to Telegizer*\n\n"
            "1️⃣ Add the bot to your group using the button below\n"
            "2️⃣ In the group, run `/linkgroup`\n"
            "3️⃣ Come back here — you'll see the group in *Groups Awaiting Setup*\n"
            "4️⃣ Copy the code and paste it in the Dashboard",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Bot to Group", url=add_url)],
                [InlineKeyboardButton("🖥️ Dashboard → Add Group", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    # ── advanced ──────────────────────────────────────────────────────────────
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
            "1. 🟢 *Official Telegizer Bot* (shared — always active)\n\n"
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
            "Create a bot via @BotFather, copy the token, and add it in:\n"
            "Dashboard → My Bots → Connect Own Bot",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Connect on Dashboard", url=f"{frontend}/my-bots")],
                [InlineKeyboardButton("« Back", callback_data="menu:advanced")],
            ]),
        )

    elif data == "menu:support":
        await query.edit_message_text(
            f"*Telegizer Support*\n\nContact us via the dashboard.\n\n{frontend}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=frontend)],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )

    # ── back to main menu ─────────────────────────────────────────────────────
    elif data == "menu:main":
        await _render_main_menu(query, user, flask_app, frontend)


async def _render_main_menu(query, user, flask_app, frontend):
    pending_count = 0
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroupLinkCode, TelegramGroup
                codes = TelegramGroupLinkCode.query.filter_by(
                    created_by_telegram_user_id=str(user.id),
                    used_at=None,
                ).filter(
                    TelegramGroupLinkCode.expires_at > datetime.utcnow()
                ).all()
                for c in codes:
                    tg = TelegramGroup.query.filter_by(
                        telegram_group_id=c.telegram_group_id
                    ).first()
                    if tg and not tg.owner_user_id:
                        pending_count += 1
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


# ─── Group membership events ──────────────────────────────────────────────────

async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track when the official bot is added to or removed from a group."""
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
    added_by = str(my_member.from_user.id) if my_member.from_user else None
    bot_un = _bot_username()

    if new_status in ("member", "administrator"):
        _upsert_group(flask_app, group_id, group_title, chat.username)
        _log_event(flask_app, group_id, "bot_added",
                   f"Bot added to {group_title}",
                   {"added_by_telegram_id": added_by})
        if flask_app:
            await _refresh_permissions(context.bot, group_id, flask_app)

        # Minimal, non-spammy group message
        try:
            await chat.send_message(
                f"✅ *Telegizer connected.*\n\n"
                f"Run `/linkgroup` here, then open @{bot_un} privately to complete setup.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc:
            _log.debug("Group welcome failed: %s", exc)

    elif new_status in ("left", "kicked"):
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


# ─── Group message handler (last_activity + custom commands) ──────────────────

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        cmd_data = None
        try:
            with flask_app.app_context():
                from .models import CustomCommand
                obj = CustomCommand.query.filter_by(
                    telegram_group_id=group_id,
                    command=cmd_raw,
                    enabled=True,
                ).first()
                if obj:
                    cmd_data = {
                        "text": obj.response_text,
                        "type": obj.response_type,
                        "buttons": obj.buttons,
                    }
        except Exception:
            pass

        if cmd_data:
            keyboard = None
            if cmd_data["buttons"]:
                rows = [
                    [InlineKeyboardButton(b["text"], url=b["url"])
                     for b in row if b.get("url")]
                    for row in cmd_data["buttons"]
                ]
                rows = [r for r in rows if r]
                if rows:
                    keyboard = InlineKeyboardMarkup(rows)
            try:
                await message.reply_text(
                    cmd_data["text"],
                    parse_mode=ParseMode.MARKDOWN if cmd_data["type"] == "markdown" else None,
                    reply_markup=keyboard,
                )
                _log_event(flask_app, group_id, "command_triggered",
                           f"/{cmd_raw}", {"command": cmd_raw})
            except Exception as exc:
                _log.debug("Custom command reply failed: %s", exc)


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
                "[OfficialBot] TELEGRAM_BOT_TOKEN not set — official bot disabled. "
                "Add it in Railway → Variables."
            )
            return
        with self._lock:
            if self._running:
                _log.info("[OfficialBot] Already running, skipping duplicate start.")
                return
            self._thread = threading.Thread(
                target=self._run_loop, args=(flask_app,),
                daemon=True, name="telegizer-official-bot",
            )
            self._thread.start()
            self._running = True
            _log.info("[OfficialBot] Thread started (token prefix: %s…)", token[:12])

    def _run_loop(self, flask_app):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._poll(flask_app))
        except Exception as exc:
            _log.error("[OfficialBot] Fatal error: %s", exc, exc_info=True)
        finally:
            self._running = False
            _log.info("[OfficialBot] Thread exited")

    async def _poll(self, flask_app):
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        self.application.bot_data["flask_app"] = flask_app

        a = self.application
        a.add_handler(CommandHandler("start", cmd_start))
        a.add_handler(CommandHandler("help", cmd_help))
        a.add_handler(CommandHandler("linkgroup", cmd_linkgroup))
        a.add_handler(CommandHandler("status", cmd_status))
        a.add_handler(CallbackQueryHandler(callback_handler))
        a.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
        a.add_handler(
            MessageHandler(
                filters.Chat(chat_type=[ChatType.GROUP, ChatType.SUPERGROUP]) & filters.TEXT,
                on_message,
            )
        )

        try:
            await a.bot.set_my_commands([
                BotCommand("start", "Open companion hub"),
                BotCommand("help", "Setup guide"),
                BotCommand("linkgroup", "Link this group (use in group)"),
                BotCommand("status", "Check bot status (use in group)"),
            ])
        except Exception as exc:
            _log.warning("[OfficialBot] set_my_commands: %s", exc)

        _log.info("[OfficialBot] Long-polling started")
        await a.run_polling(drop_pending_updates=True)


_runner = OfficialBotRunner()


def start_official_bot(flask_app):
    _runner.start(flask_app)
