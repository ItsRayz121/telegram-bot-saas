"""Automation dashboard endpoints (Phase 13).

  GET/POST            /api/guilds/<id>/workflows
  PUT/DELETE          /api/guilds/<id>/workflows/<wid>
  GET                 /api/guilds/<id>/workflows/<wid>/executions
  GET/POST            /api/guilds/<id>/mirrors
  DELETE              /api/guilds/<id>/mirrors/<mid>          (+ PUT enable toggle)
  GET/POST            /api/guilds/<id>/inbound-webhooks
  DELETE              /api/guilds/<id>/inbound-webhooks/<hid>
  GET/POST            /api/guilds/<id>/outbound-webhooks
  PUT/DELETE          /api/guilds/<id>/outbound-webhooks/<hid>
  POST                /webhooks/in/<token>                     (public — token is the credential)

The public inbound endpoint relays into the channel by enqueuing a one-shot
ScheduledMessage; the bot's content_loop posts it within ~30s. Bot and API
still coordinate only through the DB.
"""
from __future__ import annotations

import secrets
from datetime import datetime

from flask import Blueprint, g, jsonify, request

import automation_runtime
import access
import plan_limits
import settings as settings_mod
import urlguard
from auth import login_required
from config import Config
from database import SessionLocal
from models import (
    AutomationExecution,
    AutomationWorkflow,
    Channel,
    Guild,
    InboundWebhook,
    MirrorRule,
    OutboundWebhook,
    ScheduledMessage,
    UserGuild,
)

automation_bp = Blueprint("automation", __name__)

MAX_WORKFLOWS = 25
MAX_MIRRORS = 10
MAX_HOOKS = 10


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


def _clean_actions(raw) -> list[dict]:
    out = []
    for a in (raw or [])[:5]:
        if not isinstance(a, dict):
            continue
        atype = a.get("type")
        if atype not in automation_runtime.ACTION_TYPES:
            continue
        item = {"type": atype}
        if atype == "send_message":
            item["text"] = str(a.get("text") or "")[:2000]
            if a.get("channel_id") and str(a["channel_id"]).isdigit():
                item["channel_id"] = str(a["channel_id"])
            if not item["text"]:
                continue
        elif atype in ("add_role", "remove_role"):
            if not (a.get("role_id") and str(a["role_id"]).isdigit()):
                continue
            item["role_id"] = str(a["role_id"])
        elif atype == "timeout":
            try:
                item["minutes"] = max(1, min(40320, int(a.get("minutes", 10))))
            except (TypeError, ValueError):
                item["minutes"] = 10
        elif atype == "webhook":
            url = str(a.get("url") or "").strip()[:500]
            if not url.startswith(("http://", "https://")) or not urlguard.is_public_url(url):
                continue
            item["url"] = url
        out.append(item)
    return out


# --- auto-publish announcements (Phase 4 native) ------------------------------------
def _auto_publish_public(extra: dict | None) -> dict:
    return {**settings_mod.AUTO_PUBLISH_DEFAULTS,
            **((extra or {}).get("auto_publish") or {})}


@automation_bp.get("/api/guilds/<int:guild_id>/auto-publish")
@login_required
def get_auto_publish(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = settings_mod.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify(_auto_publish_public(row.extra))


@automation_bp.put("/api/guilds/<int:guild_id>/auto-publish")
@login_required
def update_auto_publish(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    row = settings_mod.get_or_create(g.db, guild_id)
    cfg = _auto_publish_public(row.extra)

    if "enabled" in body:
        cfg["enabled"] = bool(body["enabled"])
    if "channel_ids" in body:
        cfg["channel_ids"] = [str(c).strip() for c in (body["channel_ids"] or [])
                              if str(c).strip().isdigit()][:25]

    extra = dict(row.extra or {})
    extra["auto_publish"] = cfg
    row.extra = extra
    settings_mod.touch(row)
    g.db.commit()
    return jsonify(cfg)


# --- workflows ---------------------------------------------------------------------
@automation_bp.get("/api/guilds/<int:guild_id>/workflows")
@login_required
def list_workflows(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(AutomationWorkflow)
        .filter(AutomationWorkflow.guild_id == guild_id)
        .order_by(AutomationWorkflow.created_at)
        .limit(100)
        .all()
    )
    return jsonify(workflows=[r.to_dict() for r in rows])


@automation_bp.post("/api/guilds/<int:guild_id>/workflows")
@login_required
def create_workflow(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    count = g.db.query(AutomationWorkflow).filter(AutomationWorkflow.guild_id == guild_id).count()
    cap = plan_limits.limit(g.db, guild_id, "workflows")
    if count >= cap:
        return plan_limits.limit_response("workflows", cap)
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()[:120]
    trigger_type = body.get("trigger_type")
    actions = _clean_actions(body.get("actions"))
    if not name or trigger_type not in automation_runtime.TRIGGER_TYPES or not actions:
        return jsonify(error="name_trigger_and_actions_required"), 400
    trigger_value = str(body.get("trigger_value") or "").strip()[:120]
    if trigger_type == "message_contains" and not trigger_value:
        return jsonify(error="trigger_value_required"), 400
    cf = body.get("channel_filter")
    try:
        cooldown = max(0, min(86400, int(body.get("cooldown_seconds", 0))))
    except (TypeError, ValueError):
        cooldown = 0
    row = AutomationWorkflow(
        guild_id=guild_id, name=name, trigger_type=trigger_type,
        trigger_value=trigger_value or None,
        channel_filter=int(cf) if cf and str(cf).isdigit() else None,
        actions=actions, cooldown_seconds=cooldown,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(workflow=row.to_dict()), 201


@automation_bp.put("/api/guilds/<int:guild_id>/workflows/<int:wid>")
@login_required
def update_workflow(guild_id: int, wid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(AutomationWorkflow, wid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "name" in body and str(body["name"]).strip():
        row.name = str(body["name"]).strip()[:120]
    if body.get("trigger_type") in automation_runtime.TRIGGER_TYPES:
        row.trigger_type = body["trigger_type"]
    if "trigger_value" in body:
        row.trigger_value = str(body["trigger_value"] or "").strip()[:120] or None
    if "channel_filter" in body:
        cf = body["channel_filter"]
        row.channel_filter = int(cf) if cf and str(cf).isdigit() else None
    if "actions" in body:
        actions = _clean_actions(body["actions"])
        if actions:
            row.actions = actions
    if "cooldown_seconds" in body:
        try:
            row.cooldown_seconds = max(0, min(86400, int(body["cooldown_seconds"])))
        except (TypeError, ValueError):
            pass
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    # Never leave a keyword trigger without its keyword — it would silently
    # never fire.
    if row.trigger_type == "message_contains" and not (row.trigger_value or "").strip():
        g.db.rollback()
        return jsonify(error="trigger_value_required"), 400
    g.db.commit()
    return jsonify(workflow=row.to_dict())


@automation_bp.delete("/api/guilds/<int:guild_id>/workflows/<int:wid>")
@login_required
def delete_workflow(guild_id: int, wid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(AutomationWorkflow, wid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.query(AutomationExecution).filter(AutomationExecution.workflow_id == wid).delete()
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


@automation_bp.get("/api/guilds/<int:guild_id>/workflows/<int:wid>/executions")
@login_required
def list_executions(guild_id: int, wid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(AutomationExecution)
        .filter(AutomationExecution.workflow_id == wid,
                AutomationExecution.guild_id == guild_id)
        .order_by(AutomationExecution.created_at.desc())
        .limit(25)
        .all()
    )
    return jsonify(executions=[r.to_dict() for r in rows])


# --- mirrors -----------------------------------------------------------------------
@automation_bp.get("/api/guilds/<int:guild_id>/mirrors")
@login_required
def list_mirrors(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = g.db.query(MirrorRule).filter(MirrorRule.guild_id == guild_id).all()
    return jsonify(mirrors=[r.to_dict() for r in rows])


@automation_bp.post("/api/guilds/<int:guild_id>/mirrors")
@login_required
def create_mirror(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    cap = plan_limits.limit(g.db, guild_id, "mirrors")
    if g.db.query(MirrorRule).filter(MirrorRule.guild_id == guild_id).count() >= cap:
        return plan_limits.limit_response("mirrors", cap)
    body = request.get_json(silent=True) or {}
    src_id, dest_id = body.get("source_channel_id"), body.get("dest_channel_id")
    if not (src_id and str(src_id).isdigit() and dest_id and str(dest_id).isdigit()):
        return jsonify(error="source_and_dest_channel_required"), 400
    if str(src_id) == str(dest_id):
        return jsonify(error="source_equals_dest"), 400
    # Cross-guild mirrors need the user's consent on BOTH ends: the destination
    # channel must belong to this guild or to another guild the user manages.
    dest = g.db.get(Channel, int(dest_id))
    if dest is None:
        return jsonify(error="dest_channel_unknown",
                       message="Destination channel not found — the bot must be in that server."), 400
    if dest.guild_id != guild_id and not access.can_manage_guild(g.db, g.user_id, dest.guild_id):
        return jsonify(error="dest_not_managed",
                       message="You can only mirror into servers you manage."), 403
    row = MirrorRule(guild_id=guild_id, source_channel_id=int(src_id),
                     dest_channel_id=int(dest_id))
    g.db.add(row)
    g.db.commit()
    return jsonify(mirror=row.to_dict()), 201


@automation_bp.put("/api/guilds/<int:guild_id>/mirrors/<int:mid>")
@login_required
def update_mirror(guild_id: int, mid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(MirrorRule, mid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    g.db.commit()
    return jsonify(mirror=row.to_dict())


@automation_bp.delete("/api/guilds/<int:guild_id>/mirrors/<int:mid>")
@login_required
def delete_mirror(guild_id: int, mid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(MirrorRule, mid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- inbound webhooks -----------------------------------------------------------------
@automation_bp.get("/api/guilds/<int:guild_id>/inbound-webhooks")
@login_required
def list_inbound(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = g.db.query(InboundWebhook).filter(InboundWebhook.guild_id == guild_id).all()
    out = []
    for r in rows:
        data = r.to_dict()
        data["url"] = f"{Config.BACKEND_URL}/webhooks/in/{r.token}"
        out.append(data)
    return jsonify(webhooks=out)


@automation_bp.post("/api/guilds/<int:guild_id>/inbound-webhooks")
@login_required
def create_inbound(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    cap = plan_limits.limit(g.db, guild_id, "inbound_webhooks")
    if g.db.query(InboundWebhook).filter(InboundWebhook.guild_id == guild_id).count() >= cap:
        return plan_limits.limit_response("inbound_webhooks", cap)
    body = request.get_json(silent=True) or {}
    channel_id = body.get("channel_id")
    if not (channel_id and str(channel_id).isdigit()):
        return jsonify(error="channel_required"), 400
    row = InboundWebhook(
        guild_id=guild_id, channel_id=int(channel_id),
        name=str(body.get("name") or "Inbound webhook").strip()[:120],
        token=secrets.token_urlsafe(32),
    )
    g.db.add(row)
    g.db.commit()
    data = row.to_dict()
    data["url"] = f"{Config.BACKEND_URL}/webhooks/in/{row.token}"
    return jsonify(webhook=data), 201


@automation_bp.delete("/api/guilds/<int:guild_id>/inbound-webhooks/<int:hid>")
@login_required
def delete_inbound(guild_id: int, hid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(InboundWebhook, hid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- outbound webhooks ------------------------------------------------------------------
@automation_bp.get("/api/guilds/<int:guild_id>/outbound-webhooks")
@login_required
def list_outbound(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = g.db.query(OutboundWebhook).filter(OutboundWebhook.guild_id == guild_id).all()
    return jsonify(webhooks=[r.to_dict() for r in rows])


@automation_bp.post("/api/guilds/<int:guild_id>/outbound-webhooks")
@login_required
def create_outbound(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    cap = plan_limits.limit(g.db, guild_id, "outbound_webhooks")
    if g.db.query(OutboundWebhook).filter(OutboundWebhook.guild_id == guild_id).count() >= cap:
        return plan_limits.limit_response("outbound_webhooks", cap)
    body = request.get_json(silent=True) or {}
    url = str(body.get("url") or "").strip()[:500]
    if not url.startswith(("http://", "https://")):
        return jsonify(error="valid_url_required"), 400
    if not urlguard.is_public_url(url):
        return jsonify(error="url_not_public",
                       message="Webhook URLs must point to a public host."), 400
    events = [e for e in (body.get("events") or []) if e in automation_runtime.OUTBOUND_EVENTS]
    row = OutboundWebhook(
        guild_id=guild_id, url=url, events=events,
        secret=str(body.get("secret") or "").strip()[:120] or None,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(webhook=row.to_dict()), 201


@automation_bp.put("/api/guilds/<int:guild_id>/outbound-webhooks/<int:hid>")
@login_required
def update_outbound(guild_id: int, hid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(OutboundWebhook, hid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    if "events" in body:
        row.events = [e for e in (body["events"] or []) if e in automation_runtime.OUTBOUND_EVENTS]
    g.db.commit()
    return jsonify(webhook=row.to_dict())


@automation_bp.delete("/api/guilds/<int:guild_id>/outbound-webhooks/<int:hid>")
@login_required
def delete_outbound(guild_id: int, hid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(OutboundWebhook, hid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- public inbound relay (token IS the credential; no session) ---------------------------
@automation_bp.post("/webhooks/in/<token>")
def inbound_relay(token: str):
    target = automation_runtime.consume_inbound(token)
    if target is None:
        return jsonify(error="unknown_webhook"), 404
    body = request.get_json(silent=True) or {}
    content = str(body.get("content") or body.get("text") or "").strip()[:2000]
    if not content:
        return jsonify(error="content_required"), 400
    db = SessionLocal()
    try:
        db.add(ScheduledMessage(
            guild_id=target["guild_id"], channel_id=target["channel_id"],
            content=content, recurrence="none", next_run_at=datetime.utcnow(),
        ))
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()
    return jsonify(ok=True, queued=True), 202
