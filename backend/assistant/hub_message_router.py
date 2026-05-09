"""
Assistant Hub — Message router.

Called from official_bot.on_message() for every group message.
Responsibilities:
  1. Check if the group is a connected Hub group (active, consent confirmed)
  2. Detect immediate-trigger keywords → priority buffer
  3. Otherwise → standard buffer
  4. Track priority flag so extraction cron knows which buffer to process first

Buffer key format:  assistant:buffer:{bot_id}:{group_id}
Priority flag key:  assistant:priority:{bot_id}:{group_id}   (value "1", TTL 2h)
Extraction lock:    assistant:lock:{bot_id}:{group_id}        (prevents concurrent workers)

Each buffer entry is a JSON string:
  {"ts": "ISO8601", "sender": "Name", "text": "message text"}
"""
import json
import logging
import re
from datetime import datetime

_log = logging.getLogger(__name__)

# Patterns that indicate time-sensitive content → priority extraction
_TRIGGER_PATTERNS = [
    re.compile(r'\b(tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.I),
    re.compile(r'\b(\d{1,2}(am|pm|:\d{2}))\b', re.I),
    re.compile(r'\b(remind me|don\'t forget|deadline|due date|due by|schedule|meeting|call|asap|urgent)\b', re.I),
]

MAX_BUFFER = 500       # hard cap per group per bot
BUFFER_TTL = 72 * 3600  # 72 hours in seconds


def _has_trigger(text: str) -> bool:
    return any(p.search(text) for p in _TRIGGER_PATTERNS)


def buffer_hub_message(flask_app, telegram_group_id: int, message) -> None:
    """
    Entry point from official_bot.on_message().
    Silently no-ops if group is not a connected Hub group.
    """
    try:
        with flask_app.app_context():
            _do_buffer(flask_app, telegram_group_id, message)
    except Exception as exc:
        _log.debug("hub_message_router: unhandled error for group %s: %s", telegram_group_id, exc)


def _do_buffer(flask_app, telegram_group_id: int, message) -> None:
    from ..assistant.hub_models import HubConnectedGroup
    import redis as _redis_module
    import os

    # Lookup connected Hub group record
    group = HubConnectedGroup.query.filter_by(
        telegram_group_id=telegram_group_id,
        is_active=True,
    ).filter(
        HubConnectedGroup.consent_confirmed_at.isnot(None)
    ).first()

    if not group:
        return  # group not connected to Hub or paused

    # Check silence window
    if group.silence_start and group.silence_end:
        now_time = datetime.utcnow().time()
        if _in_silence_window(now_time, group.silence_start, group.silence_end):
            return

    # Build the buffer entry
    sender_name = "Unknown"
    if message.from_user:
        sender_name = (message.from_user.full_name or "").strip() or str(message.from_user.id)

    text = (message.text or message.caption or "").strip()
    if not text:
        return  # no text content to buffer

    entry = json.dumps({
        "ts": datetime.utcnow().isoformat(),
        "sender": sender_name[:80],
        "text": text[:2000],  # cap individual message length
    }, ensure_ascii=False)

    # Write to Redis
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = _redis_module.from_url(redis_url, decode_responses=True)

    buffer_key = f"assistant:buffer:{group.bot_id}:{group.id}"
    priority_key = f"assistant:priority:{group.bot_id}:{group.id}"

    pipe = r.pipeline()
    pipe.rpush(buffer_key, entry)
    pipe.ltrim(buffer_key, -MAX_BUFFER, -1)   # keep only the latest 500
    pipe.expire(buffer_key, BUFFER_TTL)

    # Set priority flag if message contains trigger keywords
    if _has_trigger(text):
        pipe.set(priority_key, "1", ex=7200)   # 2-hour TTL

    pipe.execute()


def _in_silence_window(now_time, start_time, end_time) -> bool:
    """Return True if now_time falls within [start_time, end_time) across midnight."""
    if start_time <= end_time:
        return start_time <= now_time < end_time
    # Overnight window (e.g. 22:00 – 07:00)
    return now_time >= start_time or now_time < end_time


def get_groups_with_buffered_messages(priority_only: bool = False):
    """
    Return list of (bot_id, group_id) tuples that have pending buffer entries.
    Called by the extraction Celery tasks.
    """
    import redis as _redis_module
    import os

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = _redis_module.from_url(redis_url, decode_responses=True)

    if priority_only:
        keys = r.keys("assistant:priority:*")
        results = []
        for k in keys:
            # key format: assistant:priority:{bot_id}:{group_id}
            parts = k.split(":", 3)
            if len(parts) == 4:
                _, _, bot_id, group_id = parts
                results.append((bot_id, group_id))
        return results
    else:
        keys = r.keys("assistant:buffer:*")
        results = []
        for k in keys:
            parts = k.split(":", 3)
            if len(parts) == 4:
                _, _, bot_id, group_id = parts
                # Only include if buffer is non-empty
                if r.llen(k) > 0:
                    results.append((bot_id, group_id))
        return results
