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
import access
from auth import login_required
from models import Guild, MemberWarning, ProtectionEvent, UserGuild

protection_bp = Blueprint("protection", __name__)

_ACTIONS = {"delete", "warn", "timeout", "kick", "ban"}
_LOCKDOWN_ACTIONS = {"timeout", "kick"}


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


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
                elif key == "group_topic":
                    cur[key] = str(val or "")[:120]
                elif key == "trusted_user_ids":
                    cur[key] = [str(t).strip() for t in (val or [])
                                if str(t).strip().isdigit()][:50]
                elif key == "whitelist":
                    cur[key] = [str(d).strip().lower()[:100] for d in (val or []) if str(d).strip()][:50]
                elif key == "scripts":
                    cur[key] = [str(s).strip().lower() for s in (val or []) if str(s).strip()][:10]
                elif key == "alert_channel_id":
                    cur[key] = str(val) if val and str(val).isdigit() else None
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
        if "window_hours" in w_in:
            w["window_hours"] = _as_int(w_in["window_hours"], 0, 0, 720)
        extra["warnings"] = w
    if isinstance(body.get("escalation"), dict):
        e_in = body["escalation"]
        e = dict(extra.get("escalation") or {})
        if "enabled" in e_in:
            e["enabled"] = bool(e_in["enabled"])
        if "keywords" in e_in:
            e["keywords"] = [str(k).strip().lower()[:40] for k in (e_in["keywords"] or [])
                             if str(k).strip()][:30]
        if "alert_channel_id" in e_in:
            ch = e_in["alert_channel_id"]
            e["alert_channel_id"] = str(ch) if ch and str(ch).isdigit() else None
        if "types" in e_in:
            e["types"] = [t for t in (e_in["types"] or [])
                          if t in ("ai_kb", "ai_image", "automation", "command")]
        extra["escalation"] = e
    if isinstance(body.get("verification"), dict):
        v_in = body["verification"]
        v = dict(extra.get("verification") or {})
        if "enabled" in v_in:
            v["enabled"] = bool(v_in["enabled"])
        if v_in.get("method") in ("button", "math", "word"):
            v["method"] = v_in["method"]
        if "timeout_seconds" in v_in:
            v["timeout_seconds"] = _as_int(v_in["timeout_seconds"], 300, 60, 3600)
        if "max_attempts" in v_in:
            v["max_attempts"] = _as_int(v_in["max_attempts"], 3, 1, 10)
        if v_in.get("on_timeout") in ("kick", "keep"):
            v["on_timeout"] = v_in["on_timeout"]
        if v_in.get("verify_on") in ("join", "first_message"):
            v["verify_on"] = v_in["verify_on"]
        if "auto_delete_on_timeout" in v_in:
            v["auto_delete_on_timeout"] = bool(v_in["auto_delete_on_timeout"])
        extra["verification"] = v
    if isinstance(body.get("bot_policy"), dict):
        b_in = body["bot_policy"]
        b = dict(extra.get("bot_policy") or {})
        if "enabled" in b_in:
            b["enabled"] = bool(b_in["enabled"])
        if b_in.get("policy") in ("kick_untrusted", "alert_only"):
            b["policy"] = b_in["policy"]
        if "trusted_bot_ids" in b_in:
            b["trusted_bot_ids"] = [str(t).strip() for t in (b_in["trusted_bot_ids"] or [])
                                    if str(t).strip().isdigit()][:50]
        if "alert_channel_id" in b_in:
            ch = b_in["alert_channel_id"]
            b["alert_channel_id"] = str(ch) if ch and str(ch).isdigit() else None
        extra["bot_policy"] = b
    if isinstance(body.get("auto_clean"), dict):
        ac_in = body["auto_clean"]
        ac = dict(extra.get("auto_clean") or {})
        for key in ("join_messages", "boost_messages", "pin_notifications"):
            if key in ac_in:
                ac[key] = bool(ac_in[key])
        if "warn_messages_seconds" in ac_in:
            ac["warn_messages_seconds"] = _as_int(ac_in["warn_messages_seconds"], 0, 0, 86400)
        if "action_messages_seconds" in ac_in:
            ac["action_messages_seconds"] = _as_int(ac_in["action_messages_seconds"], 0, 0, 86400)
        extra["auto_clean"] = ac
    if isinstance(body.get("emoji_reactions"), dict):
        er_in = body["emoji_reactions"]
        er = dict(extra.get("emoji_reactions") or {})
        for key in ("enabled", "admin_thumbs_up", "sentiment_reactions"):
            if key in er_in:
                er[key] = bool(er_in[key])
        if "cooldown_minutes" in er_in:
            er["cooldown_minutes"] = _as_int(er_in["cooldown_minutes"], 10, 1, 1440)
        extra["emoji_reactions"] = er
    if isinstance(body.get("social_replies"), dict):
        sr_in = body["social_replies"]
        sr = dict(extra.get("social_replies") or {})
        for key in ("enabled", "react_to_appreciation", "reply_to_appreciation"):
            if key in sr_in:
                sr[key] = bool(sr_in[key])
        if "cooldown_minutes" in sr_in:
            sr["cooldown_minutes"] = _as_int(sr_in["cooldown_minutes"], 5, 1, 1440)
        if sr_in.get("mode") in ("minimal", "professional", "friendly", "community_manager"):
            sr["mode"] = sr_in["mode"]
        extra["social_replies"] = sr
    if isinstance(body.get("command_permissions"), dict):
        cp = dict(extra.get("command_permissions") or {})
        if "delete_unauthorized" in body["command_permissions"]:
            cp["delete_unauthorized"] = bool(body["command_permissions"]["delete_unauthorized"])
        pc_in = body["command_permissions"].get("per_command")
        if isinstance(pc_in, dict):
            pc = dict(cp.get("per_command") or {})
            for cmd in ("warn", "ban", "mute", "kick"):
                if cmd in pc_in:
                    pc[cmd] = "everyone" if pc_in[cmd] == "everyone" else "admins_only"
            cp["per_command"] = pc
        extra["command_permissions"] = cp
    if isinstance(body.get("warn_ladder"), dict):
        wl_in = body["warn_ladder"]
        wl = dict(extra.get("warn_ladder") or {})
        if "enabled" in wl_in:
            wl["enabled"] = bool(wl_in["enabled"])
        if isinstance(wl_in.get("steps"), list):
            steps = []
            for s in wl_in["steps"][:5]:
                if not isinstance(s, dict):
                    continue
                action = s.get("action") if s.get("action") in ("timeout", "kick", "ban") else "timeout"
                steps.append({
                    "at": _as_int(s.get("at"), 2, 1, 20),
                    "action": action,
                    "minutes": _as_int(s.get("minutes"), 30, 1, 40320),
                    "window_hours": _as_int(s.get("window_hours"), 0, 0, 720),
                })
            wl["steps"] = sorted(steps, key=lambda s: s["at"])
        extra["warn_ladder"] = wl
    if isinstance(body.get("anti_nuke"), dict):
        an_in = body["anti_nuke"]
        an = dict(extra.get("anti_nuke") or {})
        if "enabled" in an_in:
            an["enabled"] = bool(an_in["enabled"])
        if "window_seconds" in an_in:
            an["window_seconds"] = _as_int(an_in["window_seconds"], 300, 30, 3600)
        for key in ("max_bans", "max_kicks", "max_channel_deletes", "max_role_deletes"):
            if key in an_in:
                an[key] = _as_int(an_in[key], 0, 0, 100)
        if an_in.get("action") in ("strip_roles", "ban", "alert_only"):
            an["action"] = an_in["action"]
        if "whitelist_user_ids" in an_in:
            an["whitelist_user_ids"] = [str(u).strip() for u in (an_in["whitelist_user_ids"] or [])
                                        if str(u).strip().isdigit()][:50]
        if "alert_channel_id" in an_in:
            ch = an_in["alert_channel_id"]
            an["alert_channel_id"] = str(ch) if ch and str(ch).isdigit() else None
        extra["anti_nuke"] = an
    if isinstance(body.get("kb_replies"), dict):
        kb_in = body["kb_replies"]
        kb = dict(extra.get("kb_replies") or {})
        for key in ("enabled", "mention_only", "low_confidence_fallback"):
            if key in kb_in:
                kb[key] = bool(kb_in[key])
        if "min_words" in kb_in:
            kb["min_words"] = _as_int(kb_in["min_words"], 3, 1, 50)
        if kb_in.get("reply_length") in ("short", "medium", "long"):
            kb["reply_length"] = kb_in["reply_length"]
        if kb_in.get("emoji_usage") in ("none", "some", "lots"):
            kb["emoji_usage"] = kb_in["emoji_usage"]
        if kb_in.get("formality") in ("casual", "neutral", "formal"):
            kb["formality"] = kb_in["formality"]
        if kb_in.get("personality") in (
            "professional_support", "friendly", "expert", "concise", "community_manager",
        ):
            kb["personality"] = kb_in["personality"]
        if "custom_instructions" in kb_in:
            kb["custom_instructions"] = str(kb_in["custom_instructions"] or "")[:1200]
        extra["kb_replies"] = kb
    if isinstance(body.get("reports"), dict):
        rp = dict(extra.get("reports") or {})
        if "enabled" in body["reports"]:
            rp["enabled"] = bool(body["reports"]["enabled"])
        if "alert_channel_id" in body["reports"]:
            ch = body["reports"]["alert_channel_id"]
            rp["alert_channel_id"] = str(ch) if ch and str(ch).isdigit() else None
        extra["reports"] = rp
    if isinstance(body.get("mod_log"), dict):
        ml_in = body["mod_log"]
        ml = dict(extra.get("mod_log") or {})
        if "enabled" in ml_in:
            ml["enabled"] = bool(ml_in["enabled"])
        if "channel_id" in ml_in:
            ch = ml_in["channel_id"]
            ml["channel_id"] = str(ch) if ch and str(ch).isdigit() else None
        extra["mod_log"] = ml
    if isinstance(body.get("admin_alerts"), dict):
        aa_in = body["admin_alerts"]
        aa = dict(extra.get("admin_alerts") or {})
        for key in ("enabled", "on_ban", "on_raid", "on_nuke", "on_report"):
            if key in aa_in:
                aa[key] = bool(aa_in[key])
        if "channel_id" in aa_in:
            ch = aa_in["channel_id"]
            aa["channel_id"] = str(ch) if ch and str(ch).isdigit() else None
        extra["admin_alerts"] = aa

    # Native AutoMod sync: any change to the blocked words or the sync settings
    # queues a reconcile — the bot's 20s loop pushes the rule to Discord and
    # clears the flag (automod_sync.py).
    am_body = body.get("automod") if isinstance(body.get("automod"), dict) else {}
    if "cf_custom_words" in body or isinstance(am_body.get("native_sync"), dict):
        am = dict(extra.get("automod") or {})
        ns = dict(am.get("native_sync") or {})
        ns["dirty"] = True
        am["native_sync"] = ns
        extra["automod"] = am
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
