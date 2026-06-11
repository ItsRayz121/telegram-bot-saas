"""Scheduled messages / polls / auto-responses dashboard endpoints (Phase 12).

  GET/POST           /api/guilds/<id>/scheduled-messages
  PUT/DELETE         /api/guilds/<id>/scheduled-messages/<mid>
  GET/POST           /api/guilds/<id>/polls
  DELETE             /api/guilds/<id>/polls/<pid>        (pending only)
  GET/POST           /api/guilds/<id>/auto-responses
  PUT/DELETE         /api/guilds/<id>/auto-responses/<rid>

All require session + can_manage. The bot picks work up from the DB
(next_run_at / needs_post) — no direct bot calls.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import login_required
from models import AutoResponse, Guild, Poll, ScheduledMessage, UserGuild

content_bp = Blueprint("content", __name__)

RECURRENCES = {"none", "hourly", "daily", "weekly"}


def _manage_or_403(guild_id: int):
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})
    if membership is None or not membership.can_manage:
        return False, (jsonify(error="forbidden"), 403)
    if g.db.get(Guild, guild_id) is None:
        return False, (jsonify(error="not_found"), 404)
    return True, None


def _parse_dt(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


# --- scheduled messages -------------------------------------------------------------
@content_bp.get("/api/guilds/<int:guild_id>/scheduled-messages")
@login_required
def list_scheduled(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(ScheduledMessage)
        .filter(ScheduledMessage.guild_id == guild_id)
        .order_by(ScheduledMessage.next_run_at)
        .limit(100)
        .all()
    )
    return jsonify(messages=[r.to_dict() for r in rows])


@content_bp.post("/api/guilds/<int:guild_id>/scheduled-messages")
@login_required
def create_scheduled(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    content = str(body.get("content") or "").strip()[:2000]
    channel_id = body.get("channel_id")
    next_run = _parse_dt(body.get("next_run_at"))
    if not content or not (channel_id and str(channel_id).isdigit()) or next_run is None:
        return jsonify(error="content_channel_and_time_required"), 400
    recurrence = body.get("recurrence") if body.get("recurrence") in RECURRENCES else "none"
    row = ScheduledMessage(
        guild_id=guild_id, channel_id=int(channel_id), content=content,
        recurrence=recurrence, next_run_at=next_run, created_by=g.user_id,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(message=row.to_dict()), 201


@content_bp.put("/api/guilds/<int:guild_id>/scheduled-messages/<int:mid>")
@login_required
def update_scheduled(guild_id: int, mid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(ScheduledMessage, mid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "content" in body:
        row.content = str(body["content"] or "").strip()[:2000]
    if body.get("channel_id") and str(body["channel_id"]).isdigit():
        row.channel_id = int(body["channel_id"])
    if body.get("recurrence") in RECURRENCES:
        row.recurrence = body["recurrence"]
    if "next_run_at" in body:
        dt = _parse_dt(body["next_run_at"])
        if dt is not None:
            row.next_run_at = dt
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    g.db.commit()
    return jsonify(message=row.to_dict())


@content_bp.delete("/api/guilds/<int:guild_id>/scheduled-messages/<int:mid>")
@login_required
def delete_scheduled(guild_id: int, mid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(ScheduledMessage, mid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- polls ----------------------------------------------------------------------------
@content_bp.get("/api/guilds/<int:guild_id>/polls")
@login_required
def list_polls(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(Poll)
        .filter(Poll.guild_id == guild_id)
        .order_by(Poll.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify(polls=[r.to_dict() for r in rows])


@content_bp.post("/api/guilds/<int:guild_id>/polls")
@login_required
def create_poll(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    question = str(body.get("question") or "").strip()[:300]
    answers = [str(a).strip()[:55] for a in (body.get("answers") or []) if str(a).strip()][:10]
    channel_id = body.get("channel_id")
    if not question or len(answers) < 2 or not (channel_id and str(channel_id).isdigit()):
        return jsonify(error="question_two_answers_and_channel_required"), 400
    try:
        duration = max(1, min(768, int(body.get("duration_hours", 24))))
    except (TypeError, ValueError):
        duration = 24
    row = Poll(
        guild_id=guild_id, channel_id=int(channel_id), question=question,
        answers=answers, duration_hours=duration,
        multiselect=bool(body.get("multiselect")), created_by=g.user_id,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(poll=row.to_dict()), 201


@content_bp.delete("/api/guilds/<int:guild_id>/polls/<int:pid>")
@login_required
def delete_poll(guild_id: int, pid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(Poll, pid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    if row.status == "open":
        return jsonify(error="poll_is_live"), 409
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


# --- auto-responses ----------------------------------------------------------------------
@content_bp.get("/api/guilds/<int:guild_id>/auto-responses")
@login_required
def list_responses(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    rows = (
        g.db.query(AutoResponse)
        .filter(AutoResponse.guild_id == guild_id)
        .order_by(AutoResponse.created_at)
        .limit(100)
        .all()
    )
    return jsonify(responses=[r.to_dict() for r in rows])


@content_bp.post("/api/guilds/<int:guild_id>/auto-responses")
@login_required
def create_response(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    trigger = str(body.get("trigger") or "").strip()[:120]
    response = str(body.get("response") or "").strip()[:2000]
    if not trigger or not response:
        return jsonify(error="trigger_and_response_required"), 400
    try:
        cooldown = max(1, min(3600, int(body.get("cooldown_seconds", 30))))
    except (TypeError, ValueError):
        cooldown = 30
    row = AutoResponse(
        guild_id=guild_id, trigger=trigger, response=response,
        match_type=body.get("match_type") if body.get("match_type") in ("contains", "exact") else "contains",
        cooldown_seconds=cooldown,
    )
    g.db.add(row)
    g.db.commit()
    return jsonify(response=row.to_dict()), 201


@content_bp.put("/api/guilds/<int:guild_id>/auto-responses/<int:rid>")
@login_required
def update_response(guild_id: int, rid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(AutoResponse, rid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "trigger" in body and str(body["trigger"]).strip():
        row.trigger = str(body["trigger"]).strip()[:120]
    if "response" in body and str(body["response"]).strip():
        row.response = str(body["response"]).strip()[:2000]
    if body.get("match_type") in ("contains", "exact"):
        row.match_type = body["match_type"]
    if "cooldown_seconds" in body:
        try:
            row.cooldown_seconds = max(1, min(3600, int(body["cooldown_seconds"])))
        except (TypeError, ValueError):
            pass
    if "enabled" in body:
        row.enabled = bool(body["enabled"])
    g.db.commit()
    return jsonify(response=row.to_dict())


@content_bp.delete("/api/guilds/<int:guild_id>/auto-responses/<int:rid>")
@login_required
def delete_response(guild_id: int, rid: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(AutoResponse, rid)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)
