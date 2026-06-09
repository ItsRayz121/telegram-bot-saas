"""Live Telegram member-count reconciliation for linked groups.

`TelegramGroup.member_count` is seeded at link time and nudged by join/leave
events, so it drifts low for busy groups (a group with 1,300 members shows the
handful the bot actually witnessed). This module reconciles it to the real
`getChatMemberCount` value Telegram reports.

Design notes
------------
* Loop-independent: we call the Telegram HTTP API directly with each group's bot
  token (official token from Config, custom token from CustomBot.get_token()),
  so this works in any process whether or not a bot polling loop is running.
* getChatMemberCount is a *read* — it is not a message and cannot be read as
  spam — but we still throttle between calls and honour HTTP 429 Retry-After to
  respect the platform anti-ban rule.
* Both lineages (official group-management + custom bots) are handled here in one
  shared place so custom bots inherit the behaviour automatically.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from .config import Config

_log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/getChatMemberCount"
_THROTTLE_SECONDS = 0.35   # gentle spacing between calls
_TIMEOUT_SECONDS = 10.0


def _token_for_group(tg, _custom_token_cache):
    """Resolve the bot token that can read this group's member count."""
    if (tg.linked_via_bot_type or "official") == "custom" and tg.linked_bot_id:
        if tg.linked_bot_id in _custom_token_cache:
            return _custom_token_cache[tg.linked_bot_id]
        from .models import CustomBot
        cb = CustomBot.query.get(tg.linked_bot_id)
        token = None
        if cb:
            try:
                token = cb.get_token()
            except Exception as exc:  # decryption failure — don't crash the sweep
                _log.warning("member_sync: token decrypt failed for custom bot %s: %s", tg.linked_bot_id, exc)
        _custom_token_cache[tg.linked_bot_id] = token
        return token
    return Config.TELEGRAM_BOT_TOKEN or None


def _fetch_count(client, token, chat_id):
    """Return (count:int|None, error:str|None). Honours 429 once."""
    try:
        r = client.get(_API.format(token=token), params={"chat_id": chat_id})
    except Exception as exc:
        return None, f"request failed: {exc}"

    if r.status_code == 429:
        retry_after = 1
        try:
            retry_after = int(r.json().get("parameters", {}).get("retry_after", 1))
        except Exception:
            pass
        time.sleep(min(retry_after, 30))  # honour Telegram back-off, then one retry
        try:
            r = client.get(_API.format(token=token), params={"chat_id": chat_id})
        except Exception as exc:
            return None, f"retry failed: {exc}"

    try:
        body = r.json()
    except Exception:
        return None, f"bad response (HTTP {r.status_code})"

    if not body.get("ok"):
        return None, body.get("description") or f"HTTP {r.status_code}"
    return int(body.get("result", 0)), None


def sync_member_counts(group_ids=None, throttle=_THROTTLE_SECONDS, limit=None):
    """Reconcile member_count for active, non-disabled linked groups.

    `group_ids` (list of telegram_group_id strings) restricts the sweep to those
    groups; None sweeps all eligible groups. Returns a summary dict — caller is
    responsible for being inside a Flask app context.
    """
    from .models import db, TelegramGroup

    q = TelegramGroup.query.filter(
        TelegramGroup.bot_status == "active",
        TelegramGroup.is_disabled == False,  # noqa: E712
    )
    if group_ids:
        q = q.filter(TelegramGroup.telegram_group_id.in_([str(g) for g in group_ids]))
    groups = q.order_by(TelegramGroup.member_count_synced_at.asc().nullsfirst()).all()
    if limit:
        groups = groups[:limit]

    results = []
    synced = failed = 0
    custom_token_cache = {}

    with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
        for i, tg in enumerate(groups):
            token = _token_for_group(tg, custom_token_cache)
            if not token:
                failed += 1
                results.append({
                    "id": tg.id, "telegram_group_id": tg.telegram_group_id,
                    "title": tg.title, "ok": False, "error": "no bot token available",
                })
                continue

            count, err = _fetch_count(client, token, tg.telegram_group_id)
            if err is not None:
                failed += 1
                results.append({
                    "id": tg.id, "telegram_group_id": tg.telegram_group_id,
                    "title": tg.title, "ok": False, "error": err,
                })
            else:
                tg.member_count = count
                tg.member_count_synced_at = datetime.utcnow()
                synced += 1
                results.append({
                    "id": tg.id, "telegram_group_id": tg.telegram_group_id,
                    "title": tg.title, "ok": True, "member_count": count,
                })

            if throttle and i < len(groups) - 1:
                time.sleep(throttle)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _log.error("member_sync: commit failed: %s", exc)
        return {"synced": 0, "failed": len(groups), "error": str(exc), "results": results}

    _log.info("member_sync: synced=%d failed=%d total=%d", synced, failed, len(groups))
    return {
        "synced": synced,
        "failed": failed,
        "total": len(groups),
        "results": results,
        "generated_at": datetime.utcnow().isoformat(),
    }
