"""
Telegizer Echo — dedicated official assistant bot runner.

Echo handles only Assistant Hub features:
  - Observer onboarding (consent DM when added to a group)
  - Message buffering for AI extraction
  - Hub consent / intro / classify callbacks

Management features (automod, verification, XP, digests, scheduled messages,
/linkgroup, /status etc.) remain in official_bot.py (the main Telegizer bot).

Webhook endpoint: POST /api/echo-bot-update
Env vars required: ECHO_BOT_TOKEN, ECHO_BOT_USERNAME (set in Railway → Variables)
"""
import asyncio
import logging
import threading

from telegram import BotCommand
from telegram.ext import Application

from .config import Config

_log = logging.getLogger(__name__)


class EchoBotRunner:
    def __init__(self):
        self.application = None
        self.loop = None
        self._thread = None
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self, flask_app):
        token = Config.ECHO_BOT_TOKEN
        if not token:
            _log.warning(
                "[EchoBot] ECHO_BOT_TOKEN not set — Echo assistant bot disabled. "
                "Set ECHO_BOT_TOKEN in Railway → Variables."
            )
            return
        with self._lock:
            if self._running:
                _log.info("[EchoBot] Already running, skipping duplicate start.")
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop, args=(flask_app,),
                daemon=True, name="telegizer-echo-bot",
            )
            self._thread.start()
            self._running = True
            _log.info(
                "[EchoBot] Thread started. token_prefix=%s… username=%s",
                token[:12], Config.ECHO_BOT_USERNAME,
            )

    def stop(self, timeout: float = 8.0):
        """Signal the loop to stop and wait briefly for the thread to exit.

        Called on process shutdown so the event loop unwinds cleanly before
        interpreter teardown (avoids the "cannot schedule new futures after
        interpreter shutdown" race). Best-effort; never raises.
        """
        self._stop_event.set()
        try:
            if self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(lambda: None)
        except Exception:
            pass
        t = self._thread
        if t and t.is_alive():
            try:
                t.join(timeout=timeout)
            except Exception:
                pass
        with self._lock:
            self._running = False

    def _run_loop(self, flask_app):
        """Webhook bot loop with exponential-backoff auto-restart on crash."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        base_delay = 5
        max_delay = 300
        attempt = 0

        while not self._stop_event.is_set():
            try:
                _log.info("[EchoBot] Starting webhook mode (attempt %d)…", attempt)
                self.loop.run_until_complete(self._poll(flask_app))
                _log.info("[EchoBot] Bot finished cleanly — exiting restart loop.")
                break
            except Exception as exc:
                _log.error("[EchoBot] Crash on attempt %d: %s", attempt, exc, exc_info=True)

            if self._stop_event.is_set():
                break

            delay = min(base_delay * (2 ** attempt), max_delay)
            _log.info("[EchoBot] Restarting in %ds…", delay)
            if self._stop_event.wait(timeout=delay):
                break
            attempt += 1

        with self._lock:
            self._running = False
        _log.info("[EchoBot] Thread exited")

    async def _poll(self, flask_app):
        from .bot_ratelimit import make_rate_limiter
        self.application = (
            Application.builder()
            .token(Config.ECHO_BOT_TOKEN)
            .rate_limiter(make_rate_limiter())
            .build()
        )
        self.application.bot_data["flask_app"] = flask_app

        # Expose the application on flask_app so the webhook route can forward updates.
        flask_app.echo_bot_instance = self

        # ── Register hub handlers via shared engine ───────────────────────────
        # hub_bot_id=None → Echo uses the per-user 'official' HubBotIdentity
        # (the same identity that _get_or_create_official_bot() creates for each user).
        from .assistant.hub_bot_handler import register_hub_handlers
        register_hub_handlers(self.application, flask_app, hub_bot_id=None)

        # ── Error handler ─────────────────────────────────────────────────────
        async def _error_handler(update, context):
            from telegram.error import RetryAfter, TimedOut, NetworkError
            exc = context.error
            if isinstance(exc, RetryAfter):
                _log.warning("[EchoBot] Flood control: retry after %ss", exc.retry_after)
                await asyncio.sleep(exc.retry_after)
            elif isinstance(exc, (TimedOut, NetworkError)):
                _log.warning("[EchoBot] Network error (transient): %s", exc)
            else:
                _log.error("[EchoBot] Unhandled update error: %s", exc, exc_info=exc)

        self.application.add_error_handler(_error_handler)

        _log.info("[EchoBot] Initializing application…")
        await self.application.initialize()
        await self.application.start()

        # ── Bot commands & description ────────────────────────────────────────
        try:
            await self.application.bot.set_my_commands([
                BotCommand("start", "Open your Assistant Hub"),
            ])
        except Exception as exc:
            _log.warning("[EchoBot] set_my_commands: %s", exc)

        try:
            await self.application.bot.set_my_description(
                "Telegizer Echo — your AI assistant that observes your Telegram groups "
                "and surfaces tasks, meetings, reminders, and decisions in your Telegizer Hub. "
                "Visit telegizer.com to connect."
            )
            await self.application.bot.set_my_short_description(
                "AI assistant: tasks, meetings & reminders from your groups"
            )
        except Exception as exc:
            _log.warning("[EchoBot] set_my_description: %s", exc)

        # ── Register webhook ──────────────────────────────────────────────────
        webhook_url = f"{Config.BACKEND_URL}/api/echo-bot-update"
        secret_token = getattr(Config, "TELEGRAM_WEBHOOK_SECRET", None) or Config.SECRET_KEY[:32]
        allowed_updates = [
            "message",
            "callback_query",
            "my_chat_member",
        ]
        try:
            await self.application.bot.set_webhook(
                url=webhook_url,
                secret_token=secret_token,
                allowed_updates=allowed_updates,
                drop_pending_updates=True,
            )
            _log.info("[EchoBot] Webhook registered at %s", webhook_url)
        except Exception as exc:
            _log.error("[EchoBot] Failed to register webhook: %s", exc)
            raise

        _log.info("[EchoBot] Webhook mode active — Echo bot is live.")
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass
        finally:
            _log.info("[EchoBot] Shutting down…")
            try:
                await self.application.bot.delete_webhook()
            except Exception:
                pass
            for _coro in (self.application.stop(), self.application.shutdown()):
                try:
                    await _coro
                except Exception:
                    pass


# ── Module-level singleton + public API ──────────────────────────────────────

_runner = EchoBotRunner()


def start_echo_bot(flask_app):
    _runner.start(flask_app)


def stop_echo_bot(timeout: float = 8.0):
    """Stop the Echo bot thread on process shutdown. Best-effort."""
    _runner.stop(timeout=timeout)


def get_echo_bot_loop():
    """Return (bot, loop) for use by scheduler/digest sender. Returns (None, None) if not running."""
    if _runner.application and _runner.loop and _runner.loop.is_running():
        return _runner.application.bot, _runner.loop
    return None, None
