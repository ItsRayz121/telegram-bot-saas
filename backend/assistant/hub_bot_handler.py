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

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application, CallbackQueryHandler, ChatMemberHandler,
    ContextTypes, MessageHandler, filters,
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
    async def _member_handler(update, ctx):
        await _on_my_chat_member(update, ctx, hub_bot_id=hub_bot_id)

    async def _message_handler(update, ctx):
        await _on_message(update, ctx, hub_bot_id=hub_bot_id)

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

    _log.info(
        "hub_bot_handler: registered hub handlers (hub_bot_id=%s)",
        hub_bot_id or "official",
    )
