"""Automation engine DB helpers + outbound event dispatcher (Phase 13).

No discord.py: the bot calls these via to_thread and performs the Discord-side
actions itself (bot_core._run_workflow_actions). Same pattern as the other
*_runtime modules. All loads are per-guild; the caller already serves() them.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime

import requests

from database import SessionLocal
from models import AutomationExecution, AutomationWorkflow, InboundWebhook, MirrorRule, OutboundWebhook

log = logging.getLogger("guildizer.automation")

OUTBOUND_EVENTS = {"member_join", "member_leave", "moderation_action", "raid_activated"}
ACTION_TYPES = {"send_message", "add_role", "remove_role", "timeout", "webhook"}
TRIGGER_TYPES = {"message_contains", "member_join", "member_leave", "reaction_add"}

_DISPATCH_TIMEOUT = 10


# --- workflows -----------------------------------------------------------------------
def load_workflows(guild_id: int, trigger_type: str) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(AutomationWorkflow)
            .filter(AutomationWorkflow.guild_id == guild_id,
                    AutomationWorkflow.enabled.is_(True),
                    AutomationWorkflow.trigger_type == trigger_type)
            .all()
        )
        return [r.to_dict() | {"guild_id": guild_id} for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def matches(workflow: dict, *, text: str | None = None, channel_id: int | None = None,
            emoji: str | None = None) -> bool:
    """Pure trigger check (channel filter + trigger value)."""
    cf = workflow.get("channel_filter")
    if cf and channel_id is not None and str(channel_id) != str(cf):
        return False
    value = (workflow.get("trigger_value") or "").strip().lower()
    ttype = workflow["trigger_type"]
    if ttype == "message_contains":
        return bool(value) and value in (text or "").lower()
    if ttype == "reaction_add":
        return not value or value == (emoji or "").lower()
    return True  # member_join / member_leave have no value


# in-memory workflow cooldowns: workflow id -> monotonic ts
_last_run: dict[int, float] = {}


def cooldown_ok(workflow: dict) -> bool:
    cd = int(workflow.get("cooldown_seconds") or 0)
    if cd <= 0:
        return True
    now = time.monotonic()
    if now - _last_run.get(workflow["id"], 0.0) < cd:
        return False
    _last_run[workflow["id"]] = now
    return True


def record_execution(workflow_id: int, guild_id: int, status: str, detail: str | None) -> None:
    db = SessionLocal()
    try:
        db.add(AutomationExecution(workflow_id=workflow_id, guild_id=guild_id,
                                   status=status, detail=(detail or "")[:300] or None))
        row = db.get(AutomationWorkflow, workflow_id)
        if row is not None:
            row.runs_count = (row.runs_count or 0) + 1
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("record_execution failed")
    finally:
        db.close()
        SessionLocal.remove()


def render(text: str, *, username: str = "", server: str = "", channel: str = "") -> str:
    return (text or "").replace("{user}", username).replace("{server}", server).replace("{channel}", channel)


# --- mirrors -------------------------------------------------------------------------
def mirrors_for_channel(guild_id: int, source_channel_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(MirrorRule)
            .filter(MirrorRule.guild_id == guild_id,
                    MirrorRule.source_channel_id == source_channel_id,
                    MirrorRule.enabled.is_(True))
            .all()
        )
        return [{"id": r.id, "dest_channel_id": r.dest_channel_id,
                 "webhook_url": r.webhook_url} for r in rows]
    finally:
        db.close()
        SessionLocal.remove()


def save_mirror_webhook(rule_id: int, webhook_url: str | None, error: str | None = None) -> None:
    db = SessionLocal()
    try:
        row = db.get(MirrorRule, rule_id)
        if row is None:
            return
        if webhook_url:
            row.webhook_url = webhook_url
            row.last_error = None
        if error:
            row.last_error = error[:200]
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def bump_mirror(rule_id: int) -> None:
    db = SessionLocal()
    try:
        row = db.get(MirrorRule, rule_id)
        if row is not None:
            row.mirrored_count = (row.mirrored_count or 0) + 1
            db.commit()
    finally:
        db.close()
        SessionLocal.remove()


# --- inbound -------------------------------------------------------------------------
def consume_inbound(token: str) -> dict | None:
    """Look up an enabled inbound webhook by token and bump its counters.
    Returns {guild_id, channel_id} or None."""
    db = SessionLocal()
    try:
        row = (
            db.query(InboundWebhook)
            .filter(InboundWebhook.token == token, InboundWebhook.enabled.is_(True))
            .one_or_none()
        )
        if row is None:
            return None
        row.received_count = (row.received_count or 0) + 1
        row.last_used_at = datetime.utcnow()
        db.commit()
        return {"guild_id": row.guild_id, "channel_id": row.channel_id}
    finally:
        db.close()
        SessionLocal.remove()


# --- outbound ------------------------------------------------------------------------
def dispatch_event(guild_id: int, event: str, data: dict) -> None:
    """POST the event to every subscribed outbound webhook. Sync (call via
    to_thread). Failures are recorded per hook; never raises."""
    db = SessionLocal()
    try:
        rows = (
            db.query(OutboundWebhook)
            .filter(OutboundWebhook.guild_id == guild_id,
                    OutboundWebhook.enabled.is_(True))
            .all()
        )
        hooks = [(r.id, r.url, r.secret, list(r.events or [])) for r in rows]
    finally:
        db.close()
        SessionLocal.remove()

    payload = {"event": event, "guild_id": str(guild_id),
               "timestamp": datetime.utcnow().isoformat() + "Z", "data": data}
    body = json.dumps(payload, default=str).encode()

    for hook_id, url, secret, events in hooks:
        if events and event not in events:
            continue
        headers = {"Content-Type": "application/json", "X-Guildizer-Event": event}
        if secret:
            headers["X-Guildizer-Signature"] = hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
        error = None
        try:
            resp = requests.post(url, data=body, headers=headers, timeout=_DISPATCH_TIMEOUT)
            if resp.status_code >= 400:
                error = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            error = str(exc)[:200]
        _record_delivery(hook_id, error)


def _record_delivery(hook_id: int, error: str | None) -> None:
    db = SessionLocal()
    try:
        row = db.get(OutboundWebhook, hook_id)
        if row is None:
            return
        if error:
            row.last_error = error[:200]
        else:
            row.delivered_count = (row.delivered_count or 0) + 1
            row.last_error = None
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
        SessionLocal.remove()
