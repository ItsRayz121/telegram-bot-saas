"""Rate-limit governor for Guildizer's Discord actions.

Telegizer carried heavy anti-ban paranoia because Telegram bans bots that look
spammy. Discord is different: it won't ban a well-behaved bot, and discord.py
*already* enforces the API's per-route 429 buckets internally (it queues and
retries automatically). So the "governor" here is deliberately thin — we lean on
discord.py's limiter and only add:

  • safe(): swallow the expected Forbidden / HTTPException around a moderation
    action so one failed call never crashes an event handler, returning a bool.

Keep moderation actions idempotent-ish and infrequent; do not loop-hammer the
API. That, plus discord.py's bucket handling, is the whole policy.
"""
from __future__ import annotations

import logging

import discord

log = logging.getLogger("guildizer.governor")


async def safe(coro, *, what: str = "discord action"):
    """Await a discord.py coroutine, absorbing the expected permission/HTTP
    errors. Returns the coroutine's result on success (True when the result is
    None, so the return value is always truthy), False otherwise."""
    try:
        result = await coro
        return True if result is None else result
    except discord.Forbidden:
        log.warning("Missing permission for %s", what)
    except discord.HTTPException as exc:
        log.warning("%s failed: %s", what, exc)
    except Exception:  # noqa: BLE001
        log.exception("Unexpected error during %s", what)
    return False
