"""Moderation/protection dashboard endpoints.

  GET  /api/guilds/<id>/moderation
  PUT  /api/guilds/<id>/moderation
  POST /api/guilds/<id>/moderation/lockdown   {minutes: int}  (0 clears)
  GET  /api/guilds/<id>/protection/events?limit=50

All require a session + can_manage. Updates take effect on the bot within its
next event (settings are read per-event), no resync needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

import moderation_runtime
import protection
from auth import login_required
from models import Guild, MemberWarning, ProtectionEvent, UserGuild

protection_bp = Blueprint("protection", __name__)

_ACTIONS = {"delete", "warn", "timeout", "kick", "ban"}
_LOCKDOWN_ACTIONS = {"timeout", "kick"}


def _manage_or_403(guild_id: int):
    membership = g.db.get(UserGuild, {"user_id": g.user_id, "guild_id": guild_id})
    if membership is None or not membership.can_manage:
        return False, (jsonify(error="forbidden"), 403)
    if g.db.get(Guild, guild_id) is None:
        return False, (jsonify(error="not_found"), 404)
    return True, None


def _as_int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


@protection_bp.get("/api/guilds/<int:guild_id>/moderation")
@login_required
def get_moderation(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = protection.get_or_create(g.db, guild_id)
    g.db.commit()
    return jsonify({**row.to_dict(), **protection._merged_extra(row)})


@protection_bp.put("/api/guilds/<int:guild_id>/moderation")
@login_required
def update_moderation(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    row = protection.get_or_create(g.db, guild_id)

    # content filter
    if "cf_enabled" in body:
        row.cf_enabled = bool(body["cf_enabled"])
    if "cf_action" in body and body["cf_action"] in _ACTIONS:
        row.cf_action = body["cf_action"]
    if "cf_nsfw" in body:
        row.cf_nsfw = bool(body["cf_nsfw"])
    if "cf_invites" in body:
        row.cf_invites = bool(body["cf_invites"])
    if "cf_links" in body:
        row.cf_links = bool(body["cf_links"])
    if "cf_custom_words" in body:
        words = body["cf_custom_words"] or []
        row.cf_custom_words = [str(w).strip()[:40] for w in words if str(w).strip()][:50]

    # raid guard
    if "rg_enabled" in body:
        row.rg_enabled = bool(body["rg_enabled"])
    if "rg_window_seconds" in body:
        row.rg_window_seconds = _as_int(body["rg_window_seconds"], 60, 10, 600)
    if "rg_trigger_violators" in body:
        row.rg_trigger_violators = _as_int(body["rg_trigger_violators"], 5, 2, 50)
    if "rg_duplicate_threshold" in body:
        row.rg_duplicate_threshold = _as_int(body["rg_duplicate_threshold"], 5, 2, 50)
    if "rg_lockdown_minutes" in body:
        row.rg_lockdown_minutes = _as_int(body["rg_lockdown_minutes"], 10, 1, 1440)
    if "rg_lockdown_action" in body and body["rg_lockdown_action"] in _LOCKDOWN_ACTIONS:
        row.rg_lockdown_action = body["rg_lockdown_action"]
    if "rg_notify" in body:
        row.rg_notify = bool(body["rg_notify"])
    if "rg_notify_channel_id" in body:
        v = body["rg_notify_channel_id"]
        row.rg_notify_channel_id = int(v) if v and str(v).isdigit() else None

    # join gate
    if "jg_min_account_age_days" in body:
        row.jg_min_account_age_days = _as_int(body["jg_min_account_age_days"], 0, 0, 365)

    # Phase 10: automod matrix + warning ladder + auto-clean (extra JSON column).
    # Only known sections/keys are accepted; merged over defaults on read.
    extra = dict(row.extra or {})
    if isinstance(body.get("automod"), dict):
        am_in = body["automod"]
        am = dict(extra.get("automod") or {})
        for section, defaults in protection.EXTRA_DEFAULTS["automod"].items():
            if not isinstance(am_in.get(section), dict):
                continue
            cur = dict(am.get(section) or {})
            sec_in = am_in[section]
            for key, default_val in defaults.items():
                if key not in sec_in:
                    continue
                val = sec_in[key]
                if key == "action":
                    if val in _ACTIONS:
                        cur[key] = val
                elif key == "whitelist":
                    cur[key] = [str(d).strip().lower()[:100] for d in (val or []) if str(d).strip()][:50]
                elif key == "scripts":
                    cur[key] = [str(s).strip().lower() for s in (val or []) if str(s).strip()][:10]
                elif isinstance(default_val, bool):
                    cur[key] = bool(val)
                elif isinstance(default_val, int):
                    cur[key] = _as_int(val, default_val, 1, 1000)
            am[section] = cur
        extra["automod"] = am
    if isinstance(body.get("warnings"), dict):
        w_in = body["warnings"]
        w = dict(extra.get("warnings") or {})
        if "max_warnings" in w_in:
            w["max_warnings"] = _as_int(w_in["max_warnings"], 3, 1, 20)
        if w_in.get("action") in ("timeout", "kick", "ban", "none"):
            w["action"] = w_in["action"]
        if "timeout_minutes" in w_in:
            w["timeout_minutes"] = _as_int(w_in["timeout_minutes"], 30, 1, 40320)
        extra["warnings"] = w
    if isinstance(body.get("auto_clean"), dict):
        ac = dict(extra.get("auto_clean") or {})
        if "join_messages" in body["auto_clean"]:
            ac["join_messages"] = bool(body["auto_clean"]["join_messages"])
        extra["auto_clean"] = ac
    row.extra = extra

    row.updated_at = datetime.utcnow()
    g.db.commit()
    return jsonify({**row.to_dict(), **protection._merged_extra(row)})


@protection_bp.post("/api/guilds/<int:guild_id>/moderation/lockdown")
@login_required
def set_lockdown(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    minutes = _as_int(body.get("minutes", 0), 0, 0, 1440)
    row = protection.get_or_create(g.db, guild_id)
    if minutes <= 0:
        row.manual_lockdown_until = None
        protection.log_event(g.db, guild_id, "manual_lockdown", "none", detail="Lockdown lifted")
    else:
        row.manual_lockdown_until = datetime.utcnow() + timedelta(minutes=minutes)
        protection.log_event(g.db, guild_id, "manual_lockdown", "restricted",
                             detail=f"Emergency lockdown for {minutes} min")
    row.updated_at = datetime.utcnow()
    g.db.commit()
    return jsonify(row.to_dict())


@protection_bp.get("/api/guilds/<int:guild_id>/protection/events")
@login_required
def list_events(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    limit = _as_int(request.args.get("limit", 50), 50, 1, 200)
    events = (
        g.db.query(ProtectionEvent)
        .filter(ProtectionEvent.guild_id == guild_id)
        .order_by(ProtectionEvent.created_at.desc(), ProtectionEvent.id.desc())
        .limit(limit)
        .all()
    )
    return jsonify(events=[e.to_dict() for e in events])


# --- Phase 10: warnings + reports queues ---------------------------------------
@protection_bp.get("/api/guilds/<int:guild_id>/warnings")
@login_required
def list_warnings(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    user_id = request.args.get("user_id")
    uid = int(user_id) if user_id and user_id.isdigit() else None
    limit = _as_int(request.args.get("limit", 50), 50, 1, 200)
    rows = moderation_runtime.list_warnings(g.db, guild_id, uid, limit)
    return jsonify(warnings=[w.to_dict() for w in rows])


@protection_bp.delete("/api/guilds/<int:guild_id>/warnings/<int:warning_id>")
@login_required
def delete_warning(guild_id: int, warning_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = g.db.get(MemberWarning, warning_id)
    if row is None or row.guild_id != guild_id:
        return jsonify(error="not_found"), 404
    g.db.delete(row)
    g.db.commit()
    return jsonify(ok=True)


@protection_bp.get("/api/guilds/<int:guild_id>/reports")
@login_required
def list_reports(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    status = request.args.get("status", "open")
    if status == "all":
        status = None
    limit = _as_int(request.args.get("limit", 50), 50, 1, 200)
    rows = moderation_runtime.list_reports(g.db, guild_id, status, limit)
    return jsonify(reports=[r.to_dict() for r in rows])


@protection_bp.post("/api/guilds/<int:guild_id>/reports/<int:report_id>/review")
@login_required
def review_report(guild_id: int, report_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    row = moderation_runtime.review_report(g.db, guild_id, report_id, status, g.user_id)
    if row is None:
        return jsonify(error="invalid_status_or_not_found"), 400
    g.db.commit()
    return jsonify(report=row.to_dict())
