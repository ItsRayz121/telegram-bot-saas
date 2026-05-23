"""
Assistant Hub — Custom bot webhook registration.

register_webhook(bot_id, token, base_url):
  Calls Telegram setWebhook with the hub webhook URL for a custom bot.
  Called once when a custom bot is created via POST /api/hub/bots.

unregister_webhook(token):
  Calls Telegram deleteWebhook. Called when a custom bot is deleted.
"""
import logging
import requests as _req

_log = logging.getLogger(__name__)

_WEBHOOK_PATH = "/api/hub/webhook"


def register_webhook(bot_id: str, token: str, base_url: str) -> bool:
    """
    Register a Telegram webhook for a custom bot.
    base_url: public HTTPS root of the Flask app e.g. https://api.telegizer.com
    Returns True on success.
    """
    webhook_url = f"{base_url.rstrip('/')}{_WEBHOOK_PATH}/{bot_id}"
    try:
        resp = _req.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={
                "url": webhook_url,
                "allowed_updates": ["message", "edited_message", "my_chat_member", "callback_query"],
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            _log.info("hub_custom_bot: webhook set bot_id=%s url=%s", bot_id, webhook_url)
            return True
        _log.warning("hub_custom_bot: setWebhook failed bot_id=%s: %s", bot_id, data)
        return False
    except Exception as exc:
        _log.warning("hub_custom_bot: setWebhook error bot_id=%s: %s", bot_id, exc)
        return False


def unregister_webhook(token: str) -> bool:
    """Delete the Telegram webhook for a custom bot token."""
    try:
        resp = _req.post(
            f"https://api.telegram.org/bot{token}/deleteWebhook",
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception as exc:
        _log.warning("hub_custom_bot: deleteWebhook error: %s", exc)
        return False
