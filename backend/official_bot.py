"""
Official Telegizer shared bot.

Key design decisions:
- flask_app (not app_context) stored in bot_data; every handler creates
  a FRESH with flask_app.app_context() per call.
- /start connect_<code>: links Telegram user ID to website account, then
  auto-links any pending groups created by this Telegram user.
- /linkgroup: if the running user already has a linked website account,
  the group is linked directly (no code exchange needed).  Otherwise
  a TLG-XXXXXXXX code is generated and DMed privately.
- on_private_text: accepts bot tokens from linked users when
  context.user_data["awaiting_bot_token"] is True.  The token message
  is deleted immediately and rate-limited to 3 attempts per 10 min.
- Tokens and codes are never logged.
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta

import requests as _http

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatType, ParseMode
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ChatMemberHandler, ContextTypes, filters,
)

from .config import Config

_log = logging.getLogger(__name__)

_MAX_CUSTOM_BOTS = {"free": 0, "pro": 2, "enterprise": 10}


# ─── Tiny DB helpers ──────────────────────────────────────────────────────────

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


def _frontend():
    return Config.FRONTEND_URL or "https://telegizer.xyz"


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return

    flask_app = context.bot_data.get("flask_app")
    user = update.effective_user
    first = user.first_name or "there"
    frontend = _frontend()
    bot_un = _bot_username()
    args = context.args or []

    _log.info("[OfficialBot] /start from tg_user=%s username=%s args=%s flask_app=%s",
              user.id, user.username, args, "ok" if flask_app else "MISSING")

    # ── Handle ?start=connect_<code> deep-link ────────────────────────────────
    if args and args[0].startswith("connect_"):
        code = args[0][len("connect_"):]
        if flask_app:
            await _handle_account_connect(update, context, user, flask_app, frontend, bot_un, code)
        else:
            await update.message.reply_text("⚠️ Service temporarily unavailable. Try again shortly.")
        return

    # ── Regular /start: companion hub ────────────────────────────────────────
    pending_groups = []
    is_linked = False
    tg_username_on_account = None

    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramConnectCode, TelegramGroup, User
                website_user = User.query.filter_by(telegram_user_id=str(user.id)).first()
                is_linked = website_user is not None
                if website_user:
                    tg_username_on_account = website_user.email

                codes = TelegramConnectCode.query if False else None  # unused path below
                from .models import TelegramGroupLinkCode
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
            _log.debug("cmd_start context fetch failed: %s", exc)

    text = (
        f"👋 *Welcome to Telegizer, {first}!*\n\n"
        "Your all-in-one Telegram Group Management Hub.\n\n"
        "Manage groups, automate moderation, and grow your community — "
        "all from one place."
    )

    keyboard = []

    if is_linked:
        keyboard.append([
            InlineKeyboardButton("✅ Account Connected", callback_data="menu:account_info"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("🔗 Connect Website Account", url=f"{frontend}/settings"),
        ])

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


async def _handle_account_connect(update, context, user, flask_app, frontend, bot_un, code):
    """Process /start connect_<code>: link Telegram identity to website account."""
    _log.info("[OfficialBot] account_connect attempt tg_user=%s code_prefix=%s", user.id, code[:8])
    linked_email = None
    error_msg = None
    auto_linked_groups = []

    try:
        with flask_app.app_context():
            from .models import db, TelegramConnectCode, User, TelegramGroup, TelegramGroupLinkCode

            tc = TelegramConnectCode.query.filter_by(code=code, used_at=None).filter(
                TelegramConnectCode.expires_at > datetime.utcnow()
            ).first()

            if not tc:
                error_msg = "❌ This link has expired or already been used.\n\nGenerate a new one from *Settings → Connect Telegram* on the website."
            else:
                # Check if this Telegram account is already linked to a different user
                existing = User.query.filter_by(telegram_user_id=str(user.id)).first()
                if existing and existing.id != tc.user_id:
                    error_msg = "❌ This Telegram account is already linked to a different Telegizer account.\n\nDisconnect it first from Settings on the website."
                else:
                    website_user = User.query.get(tc.user_id)
                    if not website_user:
                        error_msg = "❌ Website account not found."
                    else:
                        website_user.telegram_user_id = str(user.id)
                        website_user.telegram_username = user.username
                        website_user.telegram_first_name = user.first_name
                        website_user.telegram_connected_at = datetime.utcnow()
                        tc.used_at = datetime.utcnow()
                        tc.telegram_user_id = str(user.id)
                        linked_email = website_user.email
                        _log.info("[OfficialBot] account_connect success tg_user=%s linked_to_user_id=%s email=%s",
                                  user.id, website_user.id, linked_email)

                        # Auto-link any pending groups this Telegram user created
                        pending_codes = TelegramGroupLinkCode.query.filter_by(
                            created_by_telegram_user_id=str(user.id),
                            used_at=None,
                        ).filter(
                            TelegramGroupLinkCode.expires_at > datetime.utcnow()
                        ).all()
                        for pc in pending_codes:
                            tg = TelegramGroup.query.filter_by(
                                telegram_group_id=pc.telegram_group_id,
                                owner_user_id=None,
                            ).first()
                            if tg:
                                tg.owner_user_id = website_user.id
                                tg.bot_status = "active"
                                tg.linked_at = datetime.utcnow()
                                tg.linked_via_bot_type = "official"
                                pc.used_at = datetime.utcnow()
                                auto_linked_groups.append(tg.title)

                        db.session.commit()
    except Exception as exc:
        _log.error("Account connect failed for tg user %s: %s", user.id, exc)
        error_msg = "❌ An error occurred. Please try again."

    if error_msg:
        await update.message.reply_text(
            error_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Go to Settings", url=f"{frontend}/settings")],
            ]),
        )
        return

    lines = [
        f"✅ *Telegram connected successfully.*\n\n"
        f"Your Telegram is now linked with your Telegizer account ({linked_email}).\n\n"
        f"• Groups added by you will belong to your account\n"
        f"• Custom bot tokens sent here are saved under your account\n"
        f"• My Groups / My Bots in this bot show only your data"
    ]
    if auto_linked_groups:
        lines.append(f"\n\n🔗 *Auto-linked {len(auto_linked_groups)} pending group(s):*")
        for title in auto_linked_groups[:5]:
            lines.append(f"• {title}")

    await update.message.reply_text(
        "".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 My Groups", url=f"{frontend}/my-groups")],
            [InlineKeyboardButton("🖥️ Open Dashboard", url=frontend)],
        ]),
    )

    _log_event(flask_app, None, "telegram_account_connected",
               f"tg user {user.id} linked to {linked_email}",
               {"telegram_user_id": str(user.id)})


# ─── /help ────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_un = _bot_username()
    frontend = _frontend()
    await update.message.reply_text(
        "*Telegizer Help*\n\n"
        "*How to link your account:*\n"
        f"1. Go to {frontend}/settings → Connect Telegram\n"
        "2. Click the link to open this bot\n"
        "3. Your Telegram is now linked!\n\n"
        "*How to link a group:*\n"
        f"1. Add @{bot_un} to your Telegram group as admin\n"
        "2. Run `/linkgroup` inside the group\n"
        "3. If your account is linked, the group links automatically\n"
        "4. Otherwise, paste the code at Dashboard → Add Group\n\n"
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
    Group-only. If the running user has a linked website account the group is
    linked directly.  Otherwise a private code is generated and DMed.
    """
    chat = update.effective_chat
    user = update.effective_user
    flask_app = context.bot_data.get("flask_app")
    frontend = _frontend()

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "⚠️ Use `/linkgroup` *inside your Telegram group*, not here.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not flask_app:
        await update.message.reply_text("⚠️ Service temporarily unavailable. Try again shortly.")
        return

    try:
        cm = await context.bot.get_chat_member(chat.id, user.id)
        if cm.status not in ("creator", "administrator"):
            await update.message.reply_text("❌ Only group admins can link this group.")
            return
    except Exception:
        pass

    group_id = str(chat.id)
    group_title = chat.title or "Untitled Group"
    bot_un = _bot_username()

    _log.info("[OfficialBot] /linkgroup from tg_user=%s group=%s (%s)", user.id, group_id, group_title)

    # -- Gather everything needed inside one context block --------------------
    already_linked = False
    linked_user_id = None   # if Telegram account is already linked to website
    code = None             # set when falling back to code flow

    with flask_app.app_context():
        from .models import db, TelegramGroup, TelegramGroupLinkCode, User

        tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
        if not tg:
            tg = TelegramGroup(
                telegram_group_id=group_id, title=group_title,
                username=chat.username, bot_status="pending",
            )
            db.session.add(tg)
            db.session.flush()

        if tg.owner_user_id and tg.bot_status == "active":
            already_linked = True
            db.session.commit()
        else:
            # Check if this Telegram user has a linked website account
            website_user = User.query.filter_by(telegram_user_id=str(user.id)).first()

            if website_user:
                # Auto-link: no code exchange needed
                tg.owner_user_id = website_user.id
                tg.bot_status = "active"
                tg.linked_at = datetime.utcnow()
                tg.linked_via_bot_type = "official"
                # Expire any leftover codes for this group from this user
                TelegramGroupLinkCode.query.filter_by(
                    telegram_group_id=group_id,
                    created_by_telegram_user_id=str(user.id),
                    used_at=None,
                ).update({"expires_at": datetime.utcnow()})
                db.session.commit()
                linked_user_id = website_user.id
            else:
                # Code flow
                TelegramGroupLinkCode.query.filter_by(
                    telegram_group_id=group_id,
                    used_at=None,
                ).filter(
                    TelegramGroupLinkCode.expires_at > datetime.utcnow()
                ).update({"expires_at": datetime.utcnow()})

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

    # -- Send Telegram messages outside the DB context -------------------------
    if already_linked:
        await update.message.reply_text(
            "✅ This group is already linked to a Telegizer account.\n"
            "Use `/status` to view details.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if linked_user_id:
        # Auto-linked — minimal group message + DM confirmation
        await update.message.reply_text(
            f"✅ *{group_title}* has been linked to your Telegizer account.\n\n"
            "View it in your dashboard.",
            parse_mode=ParseMode.MARKDOWN,
        )
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    f"✅ *Group linked!*\n\n"
                    f"*{group_title}* is now in your dashboard.\n"
                    f"[Open My Groups]({frontend}/my-groups)"
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 My Groups", url=f"{frontend}/my-groups")],
                ]),
            )
        except Exception:
            pass
        _log_event(flask_app, group_id, "group_auto_linked",
                   f"Auto-linked by tg user {user.id}",
                   {"telegram_user_id": str(user.id), "website_user_id": linked_user_id})
        return

    # Code flow: post non-revealing group message + DM the code
    _log_event(flask_app, group_id, "link_code_generated",
               f"Code generated by tg user {user.id}",
               {"telegram_user_id": str(user.id)})

    await update.message.reply_text(
        f"✅ *Link request created.*\n\n"
        f"Open @{bot_un} privately to complete secure setup.\n"
        "_Your verification code will only be shown there._",
        parse_mode=ParseMode.MARKDOWN,
    )

    private_text = (
        f"🔐 *Your Group Link Code*\n\n"
        f"Group: *{group_title}*\n\n"
        f"Verification code:\n"
        f"`{code}`\n\n"
        f"⏱ Expires in *15 minutes* — single use only.\n\n"
        f"Paste this code at:\n"
        f"{frontend}/my-groups\n\n"
        f"_Or connect your Telegram account at Settings to skip codes in future._"
    )

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=private_text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except (Forbidden, BadRequest):
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"⚠️ @{user.username or user.first_name}, I couldn't DM you the code.\n\n"
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


# ─── Private message handler (bot token submission) ───────────────────────────

async def on_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles free-text in private chat when user is submitting a bot token."""
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    if not context.user_data.get("awaiting_bot_token"):
        return

    flask_app = context.bot_data.get("flask_app")
    user = update.effective_user
    message = update.message
    frontend = _frontend()

    # Rate limit: 3 attempts per 10 minutes
    now = datetime.utcnow()
    attempts = [t for t in context.user_data.get("bot_token_attempts", [])
                if (now - t).total_seconds() < 600]
    if len(attempts) >= 3:
        await message.reply_text(
            "⚠️ Too many attempts. Please wait 10 minutes before trying again."
        )
        return
    context.user_data["bot_token_attempts"] = attempts + [now]

    token = (message.text or "").strip()

    # Delete the token message immediately — security hygiene
    try:
        await message.delete()
    except Exception:
        pass

    # Basic format check
    if ":" not in token or len(token) < 30:
        await context.bot.send_message(
            chat_id=user.id,
            text="❌ Invalid token format.\nExpected: `1234567890:AAAA...`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_bot_token")],
            ]),
        )
        return

    # Only users with linked website accounts may submit tokens
    website_user_id = None
    website_tier = "free"
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import User
                u = User.query.filter_by(telegram_user_id=str(user.id)).first()
                if u:
                    website_user_id = u.id
                    website_tier = u.subscription_tier
        except Exception:
            pass

    if not website_user_id:
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "❌ Your Telegram account is not linked to a Telegizer account.\n\n"
                "Go to *Settings → Connect Telegram* on the website first."
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Go to Settings", url=f"{frontend}/settings")],
            ]),
        )
        return

    # Verify token with Telegram
    bot_name = None
    bot_username_verified = None
    try:
        resp = _http.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        result = resp.json()
        if not result.get("ok"):
            await context.bot.send_message(
                chat_id=user.id,
                text="❌ Telegram rejected this token. Please check it is correct.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_bot_token")],
                ]),
            )
            return
        tg_data = result.get("result", {})
        bot_name = tg_data.get("first_name")
        bot_username_verified = tg_data.get("username")
    except Exception as exc:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"❌ Could not verify token with Telegram. Try again.",
        )
        return

    # Save under the linked website account
    save_error = None
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import db, CustomBot, User

                u = User.query.get(website_user_id)
                max_bots = _MAX_CUSTOM_BOTS.get(u.subscription_tier, 0)
                current_count = CustomBot.query.filter_by(owner_user_id=website_user_id).count()
                if current_count >= max_bots:
                    save_error = (
                        f"❌ Your {u.subscription_tier} plan allows {max_bots} custom bot(s). "
                        "Upgrade to connect more."
                    )
                else:
                    dup = CustomBot.query.filter_by(bot_username=bot_username_verified).first()
                    if dup:
                        save_error = f"ℹ️ @{bot_username_verified} is already connected."
                    else:
                        cb = CustomBot(
                            owner_user_id=website_user_id,
                            bot_name=bot_name,
                            bot_username=bot_username_verified,
                            status="active",
                        )
                        cb.set_token(token)
                        db.session.add(cb)
                        db.session.commit()
        except Exception as exc:
            _log.error("Bot token save failed (tg user %s): %s", user.id, exc)
            save_error = "❌ Failed to save bot. Please try again or use the website dashboard."

    context.user_data["awaiting_bot_token"] = False

    if save_error:
        await context.bot.send_message(
            chat_id=user.id,
            text=save_error,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-bots")],
                [InlineKeyboardButton("« Back to Menu", callback_data="menu:main")],
            ]),
        )
        return

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            f"✅ *@{bot_username_verified} connected!*\n\n"
            f"*{bot_name}* is saved securely. View it in My Bots."
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 View My Bots", url=f"{frontend}/my-bots")],
            [InlineKeyboardButton("« Back to Menu", callback_data="menu:main")],
        ]),
    )
    _log_event(flask_app, None, "custom_bot_added_via_telegram",
               f"@{bot_username_verified} added by tg user {user.id}",
               {"telegram_user_id": str(user.id)})


# ─── Inline keyboard callbacks ────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    flask_app = context.bot_data.get("flask_app")
    frontend = _frontend()
    user = update.effective_user
    bot_un = _bot_username()

    # ── cancel bot token submission ───────────────────────────────────────────
    if data == "cancel_bot_token":
        context.user_data["awaiting_bot_token"] = False
        await _render_main_menu(query, user, flask_app, frontend)
        return

    # ── account info ──────────────────────────────────────────────────────────
    if data == "menu:account_info":
        tg_email = None
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User
                    u = User.query.filter_by(telegram_user_id=str(user.id)).first()
                    if u:
                        tg_email = u.email
            except Exception:
                pass
        text = (
            f"✅ *Account Connected*\n\n"
            f"Your Telegram is linked to: `{tg_email}`\n\n"
            f"Groups you add will appear in your dashboard automatically."
        ) if tg_email else (
            "ℹ️ No Telegizer account linked.\n\n"
            f"Visit {frontend}/settings to connect."
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Open Dashboard", url=frontend)],
                [InlineKeyboardButton("⚙️ Settings", url=f"{frontend}/settings")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]),
        )
        return

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
            lines = ["*Groups Awaiting Setup*\n"]
            for p in pending:
                lines.append(f"• *{p['title']}*")
            lines.append("\nTap a group to see its code.")
            text = "\n".join(lines)

            code_buttons = [
                [InlineKeyboardButton(
                    f"📋 {p['title']}",
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
        groups = []
        is_linked = False
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User, TelegramGroup
                    wu = User.query.filter_by(telegram_user_id=str(user.id)).first()
                    is_linked = wu is not None
                    if wu:
                        groups = TelegramGroup.query.filter_by(
                            owner_user_id=wu.id, is_disabled=False,
                        ).order_by(TelegramGroup.linked_at.desc()).limit(10).all()
                        groups = [{"title": g.title, "status": g.bot_status,
                                   "group_id": g.telegram_group_id,
                                   "cmd_count": len(g.custom_commands)} for g in groups]
            except Exception:
                pass

        if not is_linked:
            await query.edit_message_text(
                "📋 *My Groups*\n\n"
                "Connect your Telegizer website account to see your groups here.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Account", url=f"{frontend}/settings")],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        if not groups:
            text = (
                "📋 *My Groups*\n\n"
                "You have no linked groups yet.\n"
                "Add the bot to a group and run `/linkgroup` to get started."
            )
            keyboard = [
                [InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group")],
                [InlineKeyboardButton("🖥️ Open Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]
        else:
            status_icon = {"active": "🟢", "pending": "🟡", "removed": "🔴", "disabled": "⛔"}
            lines = ["📋 *My Linked Groups*\n"]
            for g in groups:
                icon = status_icon.get(g["status"], "⚪")
                cmd_txt = f" · {g['cmd_count']} cmd" if g["cmd_count"] else ""
                lines.append(f"{icon} *{g['title']}*{cmd_txt}")
            text = "\n".join(lines)
            keyboard = [
                [InlineKeyboardButton("🖥️ Manage on Dashboard", url=f"{frontend}/my-groups")],
                [InlineKeyboardButton("➕ Add Another Group", callback_data="menu:add_group")],
                [InlineKeyboardButton("« Back", callback_data="menu:main")],
            ]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # ── add_group ─────────────────────────────────────────────────────────────
    elif data == "menu:add_group":
        add_url = f"https://t.me/{bot_un}?startgroup=setup"
        await query.edit_message_text(
            "*Add Group to Telegizer*\n\n"
            "1️⃣ Add the bot to your group using the button below\n"
            "2️⃣ In the group, run `/linkgroup`\n"
            "3️⃣ If your account is connected, it links automatically\n"
            "   Otherwise paste the code from here into the Dashboard",
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
        custom_bots_list = []
        is_linked = False
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User, CustomBot
                    wu = User.query.filter_by(telegram_user_id=str(user.id)).first()
                    is_linked = wu is not None
                    if wu:
                        custom_bots_list = CustomBot.query.filter_by(
                            owner_user_id=wu.id,
                        ).order_by(CustomBot.created_at.desc()).limit(10).all()
                        custom_bots_list = [{"username": b.bot_username, "name": b.bot_name,
                                             "status": b.status,
                                             "groups": len(b.linked_groups)} for b in custom_bots_list]
            except Exception:
                pass

        if not is_linked:
            await query.edit_message_text(
                "🤖 *My Bots*\n\n"
                "Connect your Telegizer website account to see your bots here.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Connect Account", url=f"{frontend}/settings")],
                    [InlineKeyboardButton("« Back", callback_data="menu:advanced")],
                ]),
            )
            return

        status_icon = {"active": "🟢", "inactive": "🟡", "error": "🔴"}
        lines = [
            "🤖 *My Bots*\n",
            "🟢 *Official Telegizer Bot* (shared · always active)",
        ]
        if custom_bots_list:
            lines.append("\n*Custom Bots:*")
            for b in custom_bots_list:
                icon = status_icon.get(b["status"], "⚪")
                grp_txt = f" · {b['groups']} group{'s' if b['groups'] != 1 else ''}" if b["groups"] else ""
                lines.append(f"{icon} @{b['username']}{grp_txt}")
        else:
            lines.append("\n_No custom bots connected yet._")

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥️ Manage Bots", url=f"{frontend}/my-bots")],
                [InlineKeyboardButton("🔌 Connect Own Bot", callback_data="menu:connect_bot")],
                [InlineKeyboardButton("« Back", callback_data="menu:advanced")],
            ]),
        )

    elif data == "menu:connect_bot":
        # Check website account is linked before accepting a token
        is_linked = False
        if flask_app:
            try:
                with flask_app.app_context():
                    from .models import User
                    u = User.query.filter_by(telegram_user_id=str(user.id)).first()
                    is_linked = u is not None
            except Exception:
                pass

        if not is_linked:
            await query.edit_message_text(
                "*Connect Your Own Bot*\n\n"
                "⚠️ You need to link your Telegram account to a Telegizer website account first.\n\n"
                "Go to *Settings → Connect Telegram* on the website, then come back here.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖥️ Go to Settings", url=f"{frontend}/settings")],
                    [InlineKeyboardButton("« Back", callback_data="menu:advanced")],
                ]),
            )
            return

        context.user_data["awaiting_bot_token"] = True
        await query.edit_message_text(
            "*Connect Your Own Bot*\n\n"
            "Paste your *BotFather token* in the next message.\n\n"
            "⚠️ Your message will be deleted immediately after processing.\n"
            "Format: `1234567890:AAAA...`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_bot_token")],
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

    elif data == "menu:main":
        await _render_main_menu(query, user, flask_app, frontend)


async def _render_main_menu(query, user, flask_app, frontend):
    pending_count = 0
    is_linked = False
    if flask_app:
        try:
            with flask_app.app_context():
                from .models import TelegramGroupLinkCode, TelegramGroup, User
                wu = User.query.filter_by(telegram_user_id=str(user.id)).first()
                is_linked = wu is not None
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
    if is_linked:
        keyboard.append([InlineKeyboardButton("✅ Account Connected", callback_data="menu:account_info")])
    else:
        keyboard.append([InlineKeyboardButton("🔗 Connect Website Account", url=f"{frontend}/settings")])

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

    try:
        with flask_app.app_context():
            from .models import db, TelegramGroup
            tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
            if tg:
                tg.last_activity = datetime.utcnow()
                db.session.commit()
    except Exception:
        pass

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
                "Set TELEGRAM_BOT_TOKEN in Railway → Variables."
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
            _log.info(
                "[OfficialBot] Thread started. token_prefix=%s… username=%s",
                token[:12], Config.TELEGRAM_BOT_USERNAME,
            )

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
        # Private text: bot token submission (must come before group message handler)
        a.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
                on_private_text,
            )
        )
        a.add_handler(
            MessageHandler(
                filters.Chat(chat_type=[ChatType.GROUP, ChatType.SUPERGROUP]) & filters.TEXT,
                on_message,
            )
        )

        _log.info("[OfficialBot] Initializing application...")
        await a.initialize()
        await a.start()
        try:
            await a.bot.set_my_commands([
                BotCommand("start", "Open companion hub"),
                BotCommand("help", "Setup guide"),
                BotCommand("linkgroup", "Link this group (use in group)"),
                BotCommand("status", "Check bot status (use in group)"),
            ])
        except Exception as exc:
            _log.warning("[OfficialBot] set_my_commands: %s", exc)
        await a.updater.start_polling(drop_pending_updates=True)
        _log.info("[OfficialBot] Long-polling active — bot is live.")
        # Keep the coroutine alive; process exit stops the daemon thread.
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            _log.info("[OfficialBot] Shutting down polling...")
            for _coro in (a.updater.stop(), a.stop(), a.shutdown()):
                try:
                    await _coro
                except Exception:
                    pass


_runner = OfficialBotRunner()


def start_official_bot(flask_app):
    _runner.start(flask_app)
