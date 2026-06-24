"""
Resolve the Telegram bot token used to SEND assistant-lineage (Echo) messages.

The Assistant Hub is Lineage B — every Hub DM (daily digest, reminder, deadline
alert) MUST go out through the Echo bot or a custom assistant bot, NEVER through
the group-management bot (Config.TELEGRAM_BOT_TOKEN). Sending Hub content from
the group-management bot is a lineage violation: the user saw meeting digests
arrive from @telegizer_bot (group management) instead of @TelegizerEcho_bot.

See feedback_bot_lineage_rule: the two lineages never cross.
"""
import logging

from ..config import Config

_log = logging.getLogger(__name__)


def resolve_hub_send_token(bot_id: str | None = None) -> str | None:
    """Return the Telegram token to send an assistant-lineage message.

    - Custom assistant bot (HubBotIdentity.bot_type == 'custom'): its own
      per-bot encrypted token.
    - Official Echo bot (or bot_id None/unknown): the platform Echo token
      (Config.ECHO_BOT_TOKEN). Falls back to Config.TELEGRAM_BOT_TOKEN ONLY when
      ECHO_BOT_TOKEN is not configured, so an Echo-less deployment still delivers
      instead of going dark — and that fallback is logged as a warning.
    """
    if bot_id:
        try:
            from .hub_models import HubBotIdentity
            from .hub_crypto import _dec

            bot = HubBotIdentity.query.get(bot_id)
            if bot is not None and bot.bot_type == "custom" and bot.telegram_bot_token:
                tok = (_dec(bot.telegram_bot_token) or "").strip()
                if tok:
                    return tok
        except Exception as exc:
            _log.debug("resolve_hub_send_token: custom-bot token lookup failed for %s: %s", bot_id, exc)

    echo = (Config.ECHO_BOT_TOKEN or "").strip()
    if echo:
        return echo

    _log.warning(
        "resolve_hub_send_token: ECHO_BOT_TOKEN not set — falling back to the "
        "group-management token for Hub delivery (bot=%s)", bot_id,
    )
    return (Config.TELEGRAM_BOT_TOKEN or "").strip() or None
