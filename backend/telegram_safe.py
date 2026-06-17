"""
Shared safe Telegram sender (anti-ban) — BINDING.

Every *synchronous* (requests-based) raw send to the Telegram Bot API — digests,
reminders, deadline alerts, assistant DMs, group auto-replies — must go through
`safe_send_message()` so we can NEVER be banned for flooding:

  • Global pacing  — a process-wide monotonic clock spaces sends to <=20/sec,
                     comfortably under Telegram's documented ~30 msg/sec cap.
  • 429 flood-wait — a `429` response is honored EXACTLY via the returned
                     `parameters.retry_after` (bounded), then retried once.
  • Never raises   — returns True on success, False otherwise, so a bad
                     destination can never crash a Celery task or web request.

Only ever call this with a chat/user that has already interacted with the bot
(started it, joined a managed group, or submitted to a campaign) — Telegram
forbids initiating conversations with strangers, and so do we.

Long-running PTB bot processes use `automation.anti_ban.AntiBanGovernor`
instead; this module is the synchronous counterpart for tasks/routes.
"""
import logging
import threading
import time

import requests

_log = logging.getLogger(__name__)

_SEND_LOCK = threading.Lock()
_LAST_SEND = [0.0]
_MIN_INTERVAL = 0.05          # <=20 sends/sec (Telegram global cap is ~30/sec)
_MAX_RETRY_AFTER = 60         # cap a single flood-wait so we never sleep forever
_API = "https://api.telegram.org/bot{token}/sendMessage"


def _pace() -> None:
    """Block just long enough to keep the global send rate under the cap."""
    with _SEND_LOCK:
        gap = time.monotonic() - _LAST_SEND[0]
        if gap < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - gap)
        _LAST_SEND[0] = time.monotonic()


def safe_send_message(
    bot_token: str,
    chat_id,
    text: str,
    *,
    parse_mode: str | None = None,
    reply_to_message_id=None,
    reply_markup=None,
    disable_web_page_preview=None,
    message_thread_id=None,
    timeout: int = 10,
) -> bool:
    """Send one Telegram message, paced and honoring 429. Returns True on success.

    Never raises. See module docstring for the anti-ban contract.
    """
    if not bot_token or chat_id in (None, ""):
        return False

    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if disable_web_page_preview is not None:
        payload["disable_web_page_preview"] = disable_web_page_preview
    if message_thread_id:
        payload["message_thread_id"] = message_thread_id

    url = _API.format(token=bot_token)
    for _attempt in range(2):
        _pace()
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
        except Exception as exc:  # network / timeout — give up quietly
            _log.warning("safe_send_message: network error chat=%s: %s", chat_id, exc)
            return False

        if resp.status_code == 429:
            retry_after = 1
            try:
                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 1))
            except Exception:
                pass
            wait = min(max(retry_after, 1), _MAX_RETRY_AFTER)
            _log.warning("safe_send_message: 429 flood-wait %ss chat=%s", wait, chat_id)
            time.sleep(wait)
            continue  # retry once after honoring the flood wait

        if not resp.ok:
            _log.info("safe_send_message: send failed chat=%s status=%s", chat_id, resp.status_code)
            return False
        return True

    return False
