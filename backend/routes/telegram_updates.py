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
    """Receive a Telegram update for an assistant bot identified by token_hash."""
    flask_app = current_app._get_current_object()

    # Find the matching AssistantBot by comparing hashes
    bots = AssistantBot.query.filter_by(is_active=True).all()
    matched = None
    for ab in bots:
        raw = ab.bot_token
        if raw and hmac.compare_digest(_token_hash(raw), token_hash):
            matched = ab
            break

    if not matched:
        # Return 200 so Telegram doesn't retry — unknown/removed bot
        return jsonify({"ok": True}), 200

    try:
        payload = request.get_json(force=True, silent=True) or {}
        update = Update.de_json(payload, None)
    except Exception as exc:
        _log.warning("Failed to parse Telegram update: %s", exc)
        return jsonify({"ok": True}), 200

    bot_token = matched.bot_token
    assistant_bot_id = matched.id

    # Dispatch asynchronously in a temporary event loop (this is a sync Flask view)
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_dispatch(update, bot_token, flask_app, assistant_bot_id))
        loop.close()
    except Exception as exc:
        _log.error("assistant update dispatch error: %s", exc, exc_info=True)

    return jsonify({"ok": True}), 200


async def _dispatch(update: Update, bot_token: str, flask_app, assistant_bot_id: int):
    from ..assistant.assistant_bot_handler import handle_update
    bot = Bot(token=bot_token)
    async with bot:
        await handle_update(update, bot, flask_app, assistant_bot_id)


def make_webhook_url(bot_token: str) -> str:
    """Return the full public webhook URL for a given bot token."""
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
