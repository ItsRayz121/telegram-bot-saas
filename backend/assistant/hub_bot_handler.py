"""
Shared Assistant Hub bot handler.

Registers Telegram-PTB handlers for any hub-aware bot (Echo or a custom
assistant bot).  The core logic lives in hub_consent.py and
hub_message_router.py — this module is the PTB wiring layer only.

Usage
-----
    from backend.assistant.hub_bot_handler import register_hub_handlers

    register_hub_handlers(application, flask_app, hub_bot_id=None)

hub_bot_id
    None  → treats the bot as the official Echo assistant (resolves to the
            per-user HubBotIdentity with bot_type='official').
    UUID  → treats the bot as a custom assistant; must match a HubBotIdentity
            row with bot_type='custom'.
"""
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, ChatMemberHandler,
    CommandHandler, ContextTypes, MessageHandler, filters,
)

_log = logging.getLogger(__name__)


# ── on_my_chat_member ─────────────────────────────────────────────────────────

async def _on_my_chat_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    hub_bot_id: str | None,
):
    """Bot added to / removed from a group — trigger consent DM for Hub."""
    flask_app = context.bot_data.get("flask_app")
    chat = update.effective_chat
    if not chat or chat.type == ChatType.PRIVATE:
        return

    my_member = update.my_chat_member
    if not my_member:
        return

    new_status = my_member.new_chat_member.status
    added_by = str(my_member.from_user.id) if my_member.from_user else None

    if new_status in ("member", "administrator") and flask_app and added_by:
        try:
            from .hub_consent import handle_bot_added_to_group
            await handle_bot_added_to_group(
                bot=context.bot,
                flask_app=flask_app,
                chat=chat,
                added_by_tg_id=added_by,
                hub_bot_id=hub_bot_id,
            )
        except Exception as exc:
            _log.debug("hub_bot_handler: consent flow error: %s", exc)

    # Bot removed from the group → deactivate the connection so it stops being
    # counted/shown. Without this, kicked/left groups linger as "active" forever.
    elif new_status in ("left", "kicked", "banned") and flask_app:
        try:
            with flask_app.app_context():
                from .hub_models import HubConnectedGroup, HubBotIdentity
                from ..models import db
                q = HubConnectedGroup.query.filter_by(telegram_group_id=chat.id)
                if hub_bot_id:
                    q = q.filter_by(bot_id=hub_bot_id)
                else:
                    # Official Echo carries no specific identity → only touch
                    # official-lineage rows, never a custom bot's connection to
                    # the same chat.
                    q = q.join(
                        HubBotIdentity, HubBotIdentity.id == HubConnectedGroup.bot_id
                    ).filter(HubBotIdentity.bot_type == "official")
                updated = 0
                for grp in q.all():
                    if grp.pause_reason != "bot_removed" or grp.is_active:
                        grp.is_active = False
                        grp.pause_reason = "bot_removed"
                        updated += 1
                if updated:
                    db.session.commit()
                    _log.info(
                        "hub_bot_handler: deactivated %d connection(s) for chat=%s (bot removed)",
                        updated, chat.id,
                    )
        except Exception as exc:
            _log.debug("hub_bot_handler: removal cleanup error chat=%s: %s", chat.id, exc)


# ── on_callback_query ─────────────────────────────────────────────────────────

async def _on_callback_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Route hub_consent:* / hub_intro:* / hub_classify:* callbacks."""
    flask_app = context.bot_data.get("flask_app")
    query = update.callback_query
    if not query:
        return

    data = query.data or ""

    if data == "echo_noop":
        await query.answer()
        return

    if not (
        data.startswith("hub_consent:")
        or data.startswith("hub_intro:")
        or data.startswith("hub_classify:")
    ):
        return

    try:
        from .hub_consent import handle_consent_callback
        await handle_consent_callback(update, context, flask_app)
    except Exception as exc:
        _log.debug("hub_bot_handler: consent callback error: %s", exc)


# ── on_message ────────────────────────────────────────────────────────────────

async def _on_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    hub_bot_id: str | None,
):
    """Buffer every group message for async AI extraction."""
    flask_app = context.bot_data.get("flask_app")
    chat = update.effective_chat
    message = update.effective_message

    if not flask_app or not chat or chat.type == ChatType.PRIVATE or not message:
        return

    try:
        from .hub_message_router import buffer_hub_message
        # Pass hub_bot_id so we buffer only under the correct HubBotIdentity's key,
        # preventing cross-identity double-buffering during the transition window.
        buffer_hub_message(flask_app, chat.id, message, hub_bot_id=hub_bot_id)
    except Exception as exc:
        _log.debug("hub_bot_handler: buffer error: %s", exc)


# ── /assist command ───────────────────────────────────────────────────────────

async def _on_assist_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    hub_bot_id: str | None,
):
    """
    /assist [template_name] — dispatch a Hub template into the current group.
    Owned by Echo (and custom assistant bots) once ECHO_BOT_TOKEN is configured.
    """
    flask_app = context.bot_data.get("flask_app")
    message = update.effective_message
    chat = update.effective_chat

    if not flask_app or not message or not chat or chat.type == ChatType.PRIVATE:
        return

    args = (message.text or "").split(maxsplit=1)
    template_name = args[1].strip() if len(args) > 1 else ""

    try:
        with flask_app.app_context():
            from .hub_models import HubConnectedGroup, HubTemplate
            from ..models import db

            q = HubConnectedGroup.query.filter_by(
                telegram_group_id=chat.id,
                is_active=True,
            ).filter(HubConnectedGroup.consent_confirmed_at.isnot(None))
            if hub_bot_id:
                q = q.filter_by(bot_id=hub_bot_id)
            connected = q.first()

            if not connected:
                return  # group not in Hub — silently ignore

            if not template_name:
                templates = HubTemplate.query.filter_by(
                    bot_id=connected.bot_id, user_id=connected.user_id
                ).order_by(HubTemplate.name.asc()).all()
                if not templates:
                    await message.reply_text(
                        "No templates yet. Create some at your Telegizer dashboard."
                    )
                else:
                    names = "\n".join(f"• /assist {t.name}" for t in templates)
                    await message.reply_text(f"Available templates:\n{names}")
                return

            template = HubTemplate.query.filter(
                HubTemplate.bot_id == connected.bot_id,
                HubTemplate.user_id == connected.user_id,
                db.func.lower(HubTemplate.name) == template_name.lower(),
            ).first()

            if not template:
                await message.reply_text(
                    f"Template '{template_name}' not found. Check your dashboard."
                )
                return

            await message.reply_text(template.content)
            template.use_count = (template.use_count or 0) + 1
            template.last_used_at = datetime.utcnow()
            db.session.commit()

    except Exception as exc:
        _log.debug("hub_bot_handler: /assist error chat=%s: %s", chat.id, exc)


# ── /start ────────────────────────────────────────────────────────────────────

async def _on_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    hub_bot_id: str | None,
):
    """Echo /start — greet the user and explain the Hub."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    flask_app = context.bot_data.get("flask_app")
    user = update.effective_user
    first = user.first_name or "there"

    is_linked = False
    frontend = "https://telegizer.com"

    if flask_app:
        try:
            with flask_app.app_context():
                from ..config import Config as _Cfg
                frontend = _Cfg.FRONTEND_URL or frontend
                from ..models import TelegramBotStarted, db
                TelegramBotStarted.record(user.id)
                db.session.commit()
                # Check if this Telegram user has a linked website account.
                from ..models import User
                linked = User.query.filter_by(
                    telegram_user_id=str(user.id)
                ).first()
                is_linked = linked is not None
        except Exception as exc:
            _log.debug("_on_start: db lookup failed: %s", exc)

    # In-Telegram Mini App deep links. Opening /mini-app authenticates silently
    # against Echo's bot token (see telegram_webapp._first_party_bot_tokens) and
    # lands on the same telegram_user_id account as the group-management bot — no
    # external browser, no re-login. The ?start=<code> picks the landing page
    # (see frontend MiniApp.resolveStartDestination).
    hub_webapp = WebAppInfo(url=f"{frontend}/mini-app?start=echo")
    app_webapp = WebAppInfo(url=f"{frontend}/mini-app?start=dashboard")

    text = (
        f"👋 *Hi {first}! I'm Echo — your AI group observer.*\n\n"
        "I watch your Telegram groups and automatically surface:\n"
        "📋 *Tasks* · 📅 *Meetings* · 🔔 *Reminders* · ✅ *Decisions*\n\n"
        "Add me to any group to start capturing insights.\n"
        "Open your Hub to see everything in one place."
    )

    # "Add Me to a Group" deep-link — opens Telegram's group picker.
    echo_un = ""
    try:
        from ..config import Config as _CfgUn
        echo_un = _CfgUn.ECHO_BOT_USERNAME or ""
        if echo_un.startswith("@"):
            echo_un = echo_un[1:]
    except Exception:
        pass
    add_to_group_url = f"https://t.me/{echo_un}?startgroup=true" if echo_un else None

    keyboard = []

    # Opening the Mini App auto-authenticates and links the account, so there's no
    # manual "connect" step anymore. Use the same label as the official bot for a
    # consistent feel across both boards. is_linked is left unused intentionally.
    keyboard.append([
        InlineKeyboardButton("🚀 Open Telegizer App", web_app=app_webapp),
    ])

    row2 = []
    if add_to_group_url:
        row2.append(InlineKeyboardButton("➕ Add Me to a Group", url=add_to_group_url))
    row2.append(InlineKeyboardButton("📊 Open My Hub", web_app=hub_webapp))
    keyboard.append(row2)

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Public registration entry point ──────────────────────────────────────────

def register_hub_handlers(
    application: Application,
    flask_app,
    hub_bot_id: str | None = None,
):
    """
    Attach all hub-specific PTB handlers to *application*.

    Call this once during bot startup after bot_data["flask_app"] is set.
    The hub_bot_id is captured via closure so handlers carry the right identity
    without needing per-call wiring.
    """
    # Store flask_app in bot_data so handlers can reach it (PTB pattern).
    application.bot_data["flask_app"] = flask_app

    # Closure helpers capture hub_bot_id once at registration time.
    async def _start_handler(update, ctx):
        await _on_start(update, ctx, hub_bot_id=hub_bot_id)

    async def _member_handler(update, ctx):
        await _on_my_chat_member(update, ctx, hub_bot_id=hub_bot_id)

    async def _message_handler(update, ctx):
        await _on_message(update, ctx, hub_bot_id=hub_bot_id)

    async def _assist_handler(update, ctx):
        await _on_assist_command(update, ctx, hub_bot_id=hub_bot_id)

    # ChatMemberHandler: fires when *the bot itself* is added/removed.
    application.add_handler(
        ChatMemberHandler(_member_handler, ChatMemberHandler.MY_CHAT_MEMBER),
        group=10,
    )

    # CallbackQueryHandler: hub consent / intro / classify callbacks only.
    application.add_handler(
        CallbackQueryHandler(
            _on_callback_query,
            pattern=r"^(hub_consent:|hub_intro:|hub_classify:)",
        ),
        group=10,
    )

    # MessageHandler: all group text/caption messages → buffer for extraction.
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & filters.ChatType.GROUPS,
            _message_handler,
        ),
        group=10,
    )

    # CommandHandler: /start — private DM welcome.
    application.add_handler(
        CommandHandler("start", _start_handler, filters=filters.ChatType.PRIVATE),
        group=10,
    )

    # CommandHandler: /assist — template dispatch in groups.
    application.add_handler(
        CommandHandler("assist", _assist_handler),
        group=10,
    )

    _log.info(
        "hub_bot_handler: registered hub handlers (hub_bot_id=%s)",
        hub_bot_id or "official",
    )
