"""
Telegram webhook receiver for user-owned Assistant Bots.

Telegram POSTs updates to:
  POST /api/tg-update/<token_hash>

token_hash is HMAC-SHA256(bot_token, WEBHOOK_SECRET) — so the raw bot token
never appears in the URL and the endpoint can't be enumerated.
"""

import asyncio
import hashlib
import hmac
import logging

from flask import Blueprint, request, jsonify, current_app
from telegram import Bot, Update

from ..models import AssistantBot
from ..config import Config

telegram_updates_bp = Blueprint("telegram_updates", __name__, url_prefix="/api")

_log = logging.getLogger("telegram_updates")


def _token_hash(bot_token: str) -> str:
    """Derive the URL path segment from a raw bot token."""
    secret = (Config.SECRET_KEY or "telegizer-webhook-secret").encode()
    return hmac.new(secret, bot_token.encode(), hashlib.sha256).hexdigest()  # type: ignore[attr-defined]


@telegram_updates_bp.route("/tg-update/<token_hash>", methods=["POST"])
def receive_telegram_update(token_hash: str):
    """
    Receive a Telegram update for a user-owned bot (AssistantBot or custom Hub bot)
    identified by token_hash.
    """
    flask_app = current_app._get_current_object()

    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception as exc:
        _log.warning("Failed to parse JSON: %s", exc)
        return jsonify({"ok": True}), 200

    # ── 1. Try legacy AssistantBot match ──────────────────────────────────────
    bots = AssistantBot.query.filter_by(is_active=True).all()
    matched_assistant = None
    for ab in bots:
        raw = ab.bot_token
        if raw and hmac.compare_digest(_token_hash(raw), token_hash):
            matched_assistant = ab
            break

    if matched_assistant:
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _dispatch_assistant(payload, matched_assistant.bot_token, flask_app, matched_assistant.id)
            )
            loop.close()
        except Exception as exc:
            _log.error("assistant update dispatch error: %s", exc, exc_info=True)
            try:
                from ..health import record_bot_error
                record_bot_error("assistant", matched_assistant.id, "webhook", str(exc))
            except Exception:
                pass
        return jsonify({"ok": True}), 200

    # ── 2. Try custom Hub bot match (HubBotIdentity with bot_type='custom') ──
    try:
        from ..assistant.hub_models import HubBotIdentity
        hub_bots = HubBotIdentity.query.filter_by(bot_type="custom", is_active=True).all()
        matched_hub = None
        for hb in hub_bots:
            raw = hb.telegram_bot_token
            if raw and hmac.compare_digest(_token_hash(raw), token_hash):
                matched_hub = hb
                break

        if matched_hub:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    _dispatch_hub_custom_bot(payload, matched_hub.telegram_bot_token, flask_app, matched_hub.id)
                )
                loop.close()
            except Exception as exc:
                _log.error("hub custom bot dispatch error: %s", exc, exc_info=True)
                try:
                    from ..health import record_bot_error
                    record_bot_error("custom", matched_hub.id, "webhook", str(exc))
                except Exception:
                    pass
            return jsonify({"ok": True}), 200
    except Exception as exc:
        _log.debug("hub bot match error: %s", exc)

    # Unknown bot — return 200 so Telegram doesn't retry
    return jsonify({"ok": True}), 200


async def _dispatch_assistant(payload: dict, bot_token: str, flask_app, assistant_bot_id: int):
    """Dispatch an update for a legacy AssistantBot."""
    from ..assistant.assistant_bot_handler import handle_update
    bot = Bot(token=bot_token)
    async with bot:
        # Re-parse with bot reference so callback queries can call answer()
        update = Update.de_json(payload, bot)
        # Also buffer group messages for Hub extraction if this AssistantBot
        # has a linked HubBotIdentity (custom type).
        _sync_hub_buffer(update, bot_token, flask_app)
        await handle_update(update, bot, flask_app, assistant_bot_id)


async def _dispatch_hub_custom_bot(payload: dict, bot_token: str, flask_app, hub_bot_id: str):
    """
    Dispatch an update for a custom Hub assistant bot (HubBotIdentity, bot_type='custom').
    Routes all hub-specific handling through the shared hub_bot_handler engine.
    """
    bot = Bot(token=bot_token)
    async with bot:
        update = Update.de_json(payload, bot)

        # ── my_chat_member: bot added to group → consent DM ──────────────────
        if update.my_chat_member:
            chat = update.effective_chat
            new_status = update.my_chat_member.new_chat_member.status
            added_by = str(update.my_chat_member.from_user.id) if update.my_chat_member.from_user else None
            if chat and new_status in ("member", "administrator") and added_by:
                try:
                    from ..assistant.hub_consent import handle_bot_added_to_group
                    await handle_bot_added_to_group(
                        bot=bot,
                        flask_app=flask_app,
                        chat=chat,
                        added_by_tg_id=added_by,
                        hub_bot_id=hub_bot_id,
                    )
                except Exception as exc:
                    _log.debug("hub custom bot: consent flow error: %s", exc)

        # ── callback_query: hub consent / intro / classify ────────────────────
        if update.callback_query:
            data = update.callback_query.data or ""
            if data.startswith(("hub_consent:", "hub_intro:", "hub_classify:")):
                try:
                    from ..assistant.hub_consent import handle_consent_callback

                    class _Ctx:
                        def __init__(self, b):
                            self.bot = b
                            self.bot_data = {"flask_app": flask_app}

                    await handle_consent_callback(update, _Ctx(bot), flask_app)
                except Exception as exc:
                    _log.debug("hub custom bot: consent callback error: %s", exc)

        # ── message: buffer for AI extraction ────────────────────────────────
        msg = update.effective_message
        chat = update.effective_chat
        if msg and chat and chat.type in ("group", "supergroup"):
            try:
                from ..assistant.hub_message_router import buffer_hub_message
                buffer_hub_message(flask_app, chat.id, msg, hub_bot_id=hub_bot_id)
            except Exception as exc:
                _log.debug("hub custom bot: buffer error: %s", exc)


def _sync_hub_buffer(update: Update, bot_token: str, flask_app):
    """
    For legacy AssistantBots that are also Hub custom bots: buffer group
    messages under the correct HubBotIdentity's Redis key.
    """
    try:
        msg = update.effective_message
        chat = update.effective_chat
        if not msg or not chat or chat.type not in ("group", "supergroup"):
            return
        with flask_app.app_context():
            from ..assistant.hub_models import HubBotIdentity
            hub_identity = HubBotIdentity.query.filter_by(
                telegram_bot_token=bot_token,
                bot_type="custom",
                is_active=True,
            ).first()
            if not hub_identity:
                return
            from ..assistant.hub_message_router import buffer_hub_message
            buffer_hub_message(flask_app, chat.id, msg, hub_bot_id=hub_identity.id)
    except Exception as exc:
        _log.debug("_sync_hub_buffer error: %s", exc)


def make_webhook_url(bot_token: str) -> str:
    """Return the full public webhook URL for any bot token (AssistantBot or custom Hub bot)."""
    return f"{Config.BACKEND_URL}/api/tg-update/{_token_hash(bot_token)}"


# ── Official @telegizer_bot webhook endpoint ─────────────────────────────────

@telegram_updates_bp.route("/official-bot-update", methods=["POST"])
def receive_official_bot_update():
    """Receive Telegram updates for the shared @telegizer_bot via webhook."""
    flask_app = current_app._get_current_object()

    # Validate the X-Telegram-Bot-Api-Secret-Token header
    secret = getattr(Config, "TELEGRAM_WEBHOOK_SECRET", None) or Config.SECRET_KEY[:32]
    incoming_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(incoming_secret, secret):
        _log.warning("official-bot-update: invalid secret token")
        return jsonify({"ok": False}), 403

    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception as exc:
        _log.warning("official-bot-update: failed to parse JSON: %s", exc)
        return jsonify({"ok": True}), 200

    official_bot = getattr(flask_app, "official_bot_instance", None)
    if official_bot is None:
        _log.warning("official-bot-update: official bot not running")
        return jsonify({"ok": True}), 200

    # Submit the update to the bot's own event loop (running in its background thread).
    # Never create a new event loop here — the PTB Application and its httpx client
    # were created in official_bot._runner.loop; crossing loops causes RuntimeError.
    try:
        runner_loop = getattr(official_bot, "loop", None)
        # OfficialBotRunner stores the PTB Application as .application (not ._app)
        app = getattr(official_bot, "application", None)

        if runner_loop is None or not runner_loop.is_running() or app is None:
            _log.warning("official-bot-update: runner loop not ready")
            return jsonify({"ok": True}), 200

        from telegram import Update as TGUpdate
        bot = app.bot
        update = TGUpdate.de_json(payload, bot)

        future = asyncio.run_coroutine_threadsafe(
            app.process_update(update),
            runner_loop,
        )
        # Wait up to 25 s so Telegram doesn't retry the webhook (timeout is 30 s)
        future.result(timeout=25)
    except Exception as exc:
        _log.error("official-bot-update dispatch error: %s", exc, exc_info=True)

    return jsonify({"ok": True}), 200


# ── Telegizer Echo assistant bot webhook endpoint ─────────────────────────────

@telegram_updates_bp.route("/echo-bot-update", methods=["POST"])
def receive_echo_bot_update():
    """Receive Telegram updates for the Echo assistant bot via webhook."""
    flask_app = current_app._get_current_object()

    secret = getattr(Config, "TELEGRAM_WEBHOOK_SECRET", None) or Config.SECRET_KEY[:32]
    incoming_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(incoming_secret, secret):
        _log.warning("echo-bot-update: invalid secret token")
        return jsonify({"ok": False}), 403

    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception as exc:
        _log.warning("echo-bot-update: failed to parse JSON: %s", exc)
        return jsonify({"ok": True}), 200

    echo_bot = getattr(flask_app, "echo_bot_instance", None)
    if echo_bot is None:
        _log.warning("echo-bot-update: Echo bot not running")
        return jsonify({"ok": True}), 200

    try:
        runner_loop = getattr(echo_bot, "loop", None)
        app = getattr(echo_bot, "application", None)

        if runner_loop is None or not runner_loop.is_running() or app is None:
            _log.warning("echo-bot-update: runner loop not ready")
            return jsonify({"ok": True}), 200

        from telegram import Update as TGUpdate
        bot = app.bot
        update = TGUpdate.de_json(payload, bot)

        future = asyncio.run_coroutine_threadsafe(
            app.process_update(update),
            runner_loop,
        )
        future.result(timeout=25)
    except Exception as exc:
        _log.error("echo-bot-update dispatch error: %s", exc, exc_info=True)

    return jsonify({"ok": True}), 200
