"""
Anti-ban governor (D7) — shared throttle + flood-control for ALL bot sends.

BINDING RULE: no bot — official or custom — may ever perform an action Telegram
could read as spam/abuse. Every outbound send (forwarding, workflow actions)
goes through this governor so all lineages inherit the same protection.

What it does:
  • Per-chat spacing  — at most one send per ~`PER_CHAT_MIN_INTERVAL`s to the same chat.
  • Global rate limit  — sliding 1-second window capped at `GLOBAL_RATE` sends per bot.
  • Flood handling      — honors Telegram's `RetryAfter` exactly, with bounded retries
                          and small jitter, then backs off instead of hammering.
  • Failure triage      — `is_fatal_destination_error()` flags Forbidden / kicked /
                          missing-rights so callers can auto-pause a dead destination.

Telegram's documented limits are ~30 msg/s globally and ~1 msg/s per chat
(~20/min per group). We deliberately stay under those.

One governor exists per live bot object (keyed by `id(bot)`), so the official bot
and every custom bot are throttled independently — one busy bot can't starve another.
"""
import asyncio
import logging
import random
import re
import time
from collections import deque

_log = logging.getLogger(__name__)

# ── Conservative, Telegram-safe defaults ──────────────────────────────────────
GLOBAL_RATE = 25            # max sends/sec across all chats for one bot (<30 cap)
PER_CHAT_MIN_INTERVAL = 1.2  # min seconds between sends to the SAME chat (>1s cap)
MAX_RETRY_AFTER_WAIT = 120   # cap a single flood wait so we never sleep forever
MAX_SEND_RETRIES = 3         # bounded retries on RetryAfter before giving up


def _extract_retry_after(exc) -> float | None:
    """Pull a flood-wait duration (seconds) out of a Telegram error, or None."""
    ra = getattr(exc, "retry_after", None)
    if ra is not None:
        try:
            return float(ra)
        except (TypeError, ValueError):
            pass
    m = re.search(r"retry after (\d+)", str(exc).lower())
    if m:
        return float(m.group(1))
    return None


def is_fatal_destination_error(exc) -> bool:
    """True when the destination is unusable (not a transient blip), so the
    caller should auto-pause it instead of retrying forever."""
    name = type(exc).__name__.lower()
    s = str(exc).lower()
    if "forbidden" in name or "unauthorized" in name:
        return True
    fatal_markers = (
        "forbidden", "chat not found", "bot was kicked", "bot is not a member",
        "not enough rights", "need administrator", "have no rights",
        "user_id_invalid", "peer_id_invalid", "chat_write_forbidden",
        "topic_closed", "message thread not found",
    )
    return any(marker in s for marker in fatal_markers)


class AntiBanGovernor:
    """Per-bot async throttle. Create via `get_governor(bot)`; call `send()`."""

    def __init__(self):
        self._global_times: deque[float] = deque()   # send timestamps in last ~1s
        self._chat_last: dict[str, float] = {}        # chat_id -> last send monotonic
        self._lock = asyncio.Lock()

    async def _acquire(self, chat_id: str) -> None:
        """Block until both per-chat spacing and the global rate allow a send.
        Never sleeps while holding the lock, so one slow chat can't stall others."""
        key = str(chat_id)
        while True:
            async with self._lock:
                now = time.monotonic()
                # prune the global sliding window
                cutoff = now - 1.0
                while self._global_times and self._global_times[0] < cutoff:
                    self._global_times.popleft()

                chat_wait = 0.0
                last = self._chat_last.get(key)
                if last is not None:
                    chat_wait = PER_CHAT_MIN_INTERVAL - (now - last)

                global_wait = 0.0
                if len(self._global_times) >= GLOBAL_RATE:
                    global_wait = self._global_times[0] + 1.0 - now

                wait = max(chat_wait, global_wait, 0.0)
                if wait <= 0:
                    self._global_times.append(now)
                    self._chat_last[key] = now
                    return
            # release lock before sleeping; loop re-checks afterwards
            await asyncio.sleep(wait)

    async def send(self, chat_id, coro_factory):
        """Throttle, then run `coro_factory()` (a zero-arg callable returning a
        FRESH coroutine each call — needed so we can retry). Honors RetryAfter.

        Raises the last exception if it isn't a flood-wait, or after retries are
        exhausted, so the caller can log / pause the destination.
        """
        attempt = 0
        while True:
            await self._acquire(chat_id)
            try:
                return await coro_factory()
            except Exception as exc:  # noqa: BLE001 — re-raised below
                retry_after = _extract_retry_after(exc)
                if retry_after is not None and attempt < MAX_SEND_RETRIES:
                    wait = min(retry_after, MAX_RETRY_AFTER_WAIT) + random.uniform(0.1, 0.5)
                    _log.warning(
                        "Anti-ban: flood wait %.1fs for chat %s (attempt %d/%d)",
                        wait, chat_id, attempt + 1, MAX_SEND_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    attempt += 1
                    continue
                raise


# ── Per-bot registry ──────────────────────────────────────────────────────────
_governors: dict[int, AntiBanGovernor] = {}


def get_governor(bot) -> AntiBanGovernor:
    """Return the governor bound to this bot object, creating it on first use.

    Keyed by `id(bot)`: each live PTB bot instance gets its own throttle, so the
    official bot and every custom bot are rate-limited independently.
    """
    key = id(bot)
    gov = _governors.get(key)
    if gov is None:
        gov = AntiBanGovernor()
        _governors[key] = gov
    return gov
