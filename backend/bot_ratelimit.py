"""
Shared PTB rate limiter (anti-ban) — BINDING.

Every long-running python-telegram-bot `Application` (official @telegizer_bot,
Echo, and every custom bot) and every per-update assistant `Bot` attaches the
limiter returned by `make_rate_limiter()` so ALL outbound sends inherit the same
flood protection — the live message-reply path, not just forwarding/automation.

What it enforces (via PTB's `AIORateLimiter`):
  • Global cap   — <=`OVERALL_MAX_RATE` sends/sec across all chats for one bot,
                   under Telegram's documented ~30 msg/s ceiling.
  • Per-group cap — <=`GROUP_MAX_RATE` sends per `GROUP_TIME_PERIOD`s to any one
                    group/channel, at Telegram's documented ~20/min per chat.
  • Flood retry  — a `RetryAfter` (429) is honored automatically and the send is
                   retried up to `MAX_RETRIES` times instead of being dropped.

This is the proactive counterpart to `automation.anti_ban.AntiBanGovernor`
(used by forwarding) and `telegram_safe.safe_send_message` (sync tasks); together
they mean no bot — official or custom — can ever be banned for flooding.

`AIORateLimiter` needs the `aiolimiter` package (the `python-telegram-bot[rate-limiter]`
extra). If it is somehow missing at runtime we log and return `None` so the bot
still starts unthrottled rather than crashing on boot — `.rate_limiter(None)` is
PTB's default.
"""
import logging

_log = logging.getLogger(__name__)

# ── Conservative, Telegram-safe limits (mirror automation/anti_ban.py) ────────
OVERALL_MAX_RATE = 25     # sends/sec across all chats for one bot (<30 cap)
OVERALL_TIME_PERIOD = 1   # ...measured over this many seconds
GROUP_MAX_RATE = 19       # sends per group/channel per window (<20/min cap)
GROUP_TIME_PERIOD = 60    # ...measured over this many seconds
MAX_RETRIES = 3           # auto-retry a 429 flood-wait this many times


def make_rate_limiter():
    """Return a fresh `AIORateLimiter` with our anti-ban limits, or `None` if the
    optional dependency is unavailable (so the bot can still start)."""
    try:
        from telegram.ext import AIORateLimiter
        return AIORateLimiter(
            overall_max_rate=OVERALL_MAX_RATE,
            overall_time_period=OVERALL_TIME_PERIOD,
            group_max_rate=GROUP_MAX_RATE,
            group_time_period=GROUP_TIME_PERIOD,
            max_retries=MAX_RETRIES,
        )
    except Exception as exc:  # ImportError (missing extra) or RuntimeError
        _log.warning(
            "AIORateLimiter unavailable (%s) — bot will run WITHOUT proactive "
            "rate limiting. Install python-telegram-bot[rate-limiter].", exc,
        )
        return None
