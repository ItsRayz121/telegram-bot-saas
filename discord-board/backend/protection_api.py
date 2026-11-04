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

import discord_api
import moderation_runtime
import protection
import access
import ai
from auth import login_required
from config import Config
from models import Guild, KnowledgeDocument, MemberWarning, ProtectionEvent, UserGuild

_AI_CATEGORIES = ("smart_mod", "smart_promo", "image_ai", "image_nsfw", "ask", "ai", "escalation")

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
            if section == "slow_mode":
                continue  # validated explicitly below (exempt_min_level must allow 0)
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
                elif key == "ai_mode":
                    # enforce = act on a confident AI verdict; observe = log only
                    cur[key] = str(val).lower() if str(val).lower() in ("enforce", "observe") else "enforce"
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
        # Smart slow mode — validated on its own so exempt_min_level can be 0
        # (the generic int handler clamps to >= 1).
        if isinstance(am_in.get("slow_mode"), dict):
            sm_in = am_in["slow_mode"]
            sm = dict(am.get("slow_mode") or {})
            if "enabled" in sm_in:
                sm["enabled"] = bool(sm_in["enabled"])
            if "seconds_between_messages" in sm_in:
                sm["seconds_between_messages"] = _as_int(sm_in["seconds_between_messages"], 60, 5, 3600)
            if sm_in.get("action") in ("delete", "warn", "timeout"):
                sm["action"] = sm_in["action"]
            if "timeout_minutes" in sm_in:
                sm["timeout_minutes"] = _as_int(sm_in["timeout_minutes"], 5, 1, 40320)
            if "exempt_min_level" in sm_in:
                sm["exempt_min_level"] = _as_int(sm_in["exempt_min_level"], 0, 0, 1000)
            if "notify" in sm_in:
                sm["notify"] = bool(sm_in["notify"])
            am["slow_mode"] = sm
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
    if isinstance(body.get("image_understanding"), dict):
        iu_in = body["image_understanding"]
        iu = dict(extra.get("image_understanding") or {})
        for key in ("enabled", "mention_only", "require_caption", "escalate_low_confidence"):
            if key in iu_in:
                iu[key] = bool(iu_in[key])
        if iu_in.get("cost_mode") in ("aggressive_savings", "balanced", "quality"):
            iu["cost_mode"] = iu_in["cost_mode"]
        if "confidence_threshold" in iu_in:
            try:
                iu["confidence_threshold"] = min(0.9, max(0.3, float(iu_in["confidence_threshold"])))
            except (TypeError, ValueError):
                pass
        if "max_image_size_mb" in iu_in:
            iu["max_image_size_mb"] = _as_int(iu_in["max_image_size_mb"], 5, 1, 10)
        extra["image_understanding"] = iu
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


# Channel types that carry a native per-user cooldown we manage: text (0) and
# voice-channel chat (2). Announcement/forum/stage channels are left alone.
_SLOWMODE_TYPES = {0, 2}
_SLOWMODE_MAX_BULK = 50


def _live_slowmode_channels(guild: Guild):
    """Read the guild's channels straight from Discord (not our synced shadow
    copy) so cooldowns changed in Discord itself show up. Returns (channels, token)."""
    import discord_api
    import team_direct
    token = team_direct.bot_token_for(g.db, guild)
    raw = discord_api.get_guild_channels(guild.id, token=token)
    chans = [
        {"id": str(c["id"]), "name": c.get("name") or "", "type": c.get("type"),
         "seconds": int(c.get("rate_limit_per_user") or 0),
         "parent_id": str(c["parent_id"]) if c.get("parent_id") else None,
         "position": c.get("position", 0)}
        for c in raw if c.get("type") in _SLOWMODE_TYPES
    ]
    chans.sort(key=lambda c: (c["position"], c["name"]))
    return chans, token


def _served_guild_or_error(guild_id: int):
    guild = g.db.get(Guild, guild_id)
    if guild is None:
        return None, (jsonify(error="not_found"), 404)
    if not guild.is_served:
        return None, (jsonify(error="bot_not_in_server"), 409)
    return guild, None


@protection_bp.get("/api/guilds/<int:guild_id>/native-slowmode")
@login_required
def get_native_slowmode(guild_id: int):
    """Live native cooldown of every text/voice-chat channel, read from Discord."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild, err = _served_guild_or_error(guild_id)
    if err:
        return err
    try:
        chans, _tok = _live_slowmode_channels(guild)
    except Exception:
        return jsonify(error="discord_unavailable"), 502
    return jsonify(channels=chans)


def _error_code_for(exc) -> str:
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    if status in (401, 403):
        return "missing_permission"
    if status == 404:
        return "channel_not_found"
    if status == 429:
        return "rate_limited"
    return "discord_error"


@protection_bp.post("/api/guilds/<int:guild_id>/native-slowmode")
@login_required
def set_native_slowmode(guild_id: int):
    """Set native Discord Slowmode on one OR many channels in a single call.

    Body: {channel_ids: [..]  (or legacy channel_id), seconds: 0..21600}.
    Every id must be a channel of THIS server (checked against Discord live), so
    a manager can never touch another server's channels. Returns a per-channel
    outcome list so partial failures are precise and a retry is safe (setting the
    same value twice is idempotent). seconds=0 turns the cooldown off — it never
    deletes a channel."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild, err = _served_guild_or_error(guild_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    ids = body.get("channel_ids")
    if ids is None and body.get("channel_id") is not None:
        ids = [body.get("channel_id")]
    if not isinstance(ids, list) or not ids:
        return jsonify(error="bad_channel_id"), 400
    ids = list(dict.fromkeys(str(i) for i in ids))
    if len(ids) > _SLOWMODE_MAX_BULK or not all(i.isdigit() for i in ids):
        return jsonify(error="bad_channel_id"), 400
    try:
        seconds = int(body.get("seconds", 0))
    except (TypeError, ValueError):
        return jsonify(error="bad_seconds"), 400
    if not 0 <= seconds <= 21600:
        return jsonify(error="bad_seconds"), 400

    import time as _time
    import discord_api
    try:
        live, token = _live_slowmode_channels(guild)
    except Exception:
        return jsonify(error="discord_unavailable"), 502
    by_id = {c["id"]: c for c in live}

    results = []
    for cid in ids:
        ch = by_id.get(cid)
        if ch is None:
            results.append({"channel_id": cid, "ok": False, "error": "not_in_server"})
            continue
        if ch["seconds"] == seconds:
            results.append({"channel_id": cid, "name": ch["name"], "ok": True,
                            "seconds": seconds, "unchanged": True})
            continue
        err_code = None
        for attempt in (0, 1):
            try:
                discord_api.set_channel_slowmode(
                    int(cid), seconds, "Guildizer dashboard: native Slowmode", token=token)
                err_code = None
                break
            except Exception as exc:  # noqa: BLE001 - classify, never leak details
                err_code = _error_code_for(exc)
                if err_code == "rate_limited" and attempt == 0:
                    wait = 1.0
                    try:
                        wait = min(5.0, float(exc.response.headers.get("Retry-After", 1)))
                    except Exception:  # noqa: BLE001
                        pass
                    _time.sleep(wait)
                    continue
                break
        if err_code:
            results.append({"channel_id": cid, "name": ch["name"], "ok": False, "error": err_code})
        else:
            results.append({"channel_id": cid, "name": ch["name"], "ok": True, "seconds": seconds})

    done = [r for r in results if r["ok"] and not r.get("unchanged")]
    failed = [r for r in results if not r["ok"]]
    if done or failed:
        names = ", ".join("#" + (r.get("name") or r["channel_id"]) for r in done[:8])
        detail = (f"Native Slowmode {'set to ' + str(seconds) + 's' if seconds else 'turned off'}"
                  f" · {len(done)} channel(s): {names}"
                  + (f" · {len(failed)} failed" if failed else ""))
        g.db.add(ProtectionEvent(
            guild_id=guild_id, category="moderation", action="slowmode", detail=detail[:255]))
        g.db.commit()
    return jsonify(ok=not failed, seconds=seconds, results=results), (200 if not failed else 207)


# ── Trusted bots (identity + one-at-a-time add/remove) ─────────────────────────
# The allowlist is honoured by ONE protection only: Bot Protection's
# "untrusted bot joins" policy (bot_policy.handle_bot_join). It does not exempt a
# bot from anti-nuke, spam, raid or content rules.

def _trusted_ids(guild_id: int) -> list[str]:
    row = protection.get_or_create(g.db, guild_id)
    ids = (protection._merged_extra(row).get("bot_policy") or {}).get("trusted_bot_ids") or []
    out: list[str] = []
    for t in ids:                      # legacy data may hold "1,2" strings / ints / dupes
        for part in str(t).replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit() and part not in out:
                out.append(part)
    return out


def _bot_card(u: dict, **extra):
    return {"id": str(u["id"]), "name": u.get("global_name") or u.get("username") or str(u["id"]),
            "username": u.get("username"), "avatar_url": discord_api.avatar_url(u), **extra}


@protection_bp.get("/api/guilds/<int:guild_id>/trusted-bots")
@login_required
def list_trusted_bots(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild, err = _served_guild_or_error(guild_id)
    if err:
        return err
    import team_direct
    token = team_direct.bot_token_for(g.db, guild)
    trusted = _trusted_ids(guild_id)
    installed, members_ok = {}, True
    try:
        installed = {str(u["id"]): u for u in discord_api.list_guild_bots(guild_id, token)}
    except Exception:
        members_ok = False             # e.g. Server Members intent off — still show saved ids
    rows = []
    for tid in trusted:
        u = installed.get(tid)
        status = "installed" if u else "unresolved"
        if u is None:
            try:
                u = discord_api.get_user(int(tid), token)
                status = "not_in_server" if u and u.get("bot") else ("not_a_bot" if u else "unresolved")
            except Exception:
                u, status = None, "unresolved"
        rows.append(_bot_card(u, status=status) if u else
                    {"id": tid, "name": tid, "username": None, "avatar_url": None, "status": status})
    return jsonify(trusted=rows, members_ok=members_ok,
                   installed=[_bot_card(u, trusted=str(u["id"]) in trusted) for u in installed.values()
                              if str(u["id"]) != str(Config.DISCORD_CLIENT_ID)])


@protection_bp.post("/api/guilds/<int:guild_id>/trusted-bots")
@login_required
def add_trusted_bot(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild, err = _served_guild_or_error(guild_id)
    if err:
        return err
    raw = str((request.get_json(silent=True) or {}).get("id") or "").strip()
    if not raw.isdigit() or not 15 <= len(raw) <= 21:
        return jsonify(error="bad_id"), 400
    import team_direct
    token = team_direct.bot_token_for(g.db, guild)
    try:
        u = discord_api.get_user(int(raw), token)
    except Exception:
        u = False                       # Discord unreachable: can't verify, allow as unresolved
    if u is None:
        return jsonify(error="unknown_user"), 404
    if u and not u.get("bot"):
        return jsonify(error="not_a_bot"), 400   # a human account is never a trusted bot
    ids = _trusted_ids(guild_id)
    if raw not in ids:
        if len(ids) >= 50:
            return jsonify(error="limit_reached"), 400
        ids.append(raw)
        protection.update_extra_section(g.db, guild_id, "bot_policy", {"trusted_bot_ids": ids})
        g.db.add(ProtectionEvent(guild_id=guild_id, category="bot_policy", action="trusted_added",
                                 user_id=int(raw), username=(u or {}).get("username"),
                                 detail="Trusted from the dashboard"))
        g.db.commit()
    return jsonify(ok=True, trusted_bot_ids=ids, resolved=bool(u))


@protection_bp.delete("/api/guilds/<int:guild_id>/trusted-bots/<bot_id>")
@login_required
def remove_trusted_bot(guild_id: int, bot_id: str):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    if not bot_id.isdigit():
        return jsonify(error="bad_id"), 400
    ids = _trusted_ids(guild_id)
    if bot_id in ids:
        ids.remove(bot_id)
        protection.update_extra_section(g.db, guild_id, "bot_policy", {"trusted_bot_ids": ids})
        g.db.add(ProtectionEvent(guild_id=guild_id, category="bot_policy", action="trusted_removed",
                                 user_id=int(bot_id), detail="Removed from the dashboard"))
        g.db.commit()
    return jsonify(ok=True, trusted_bot_ids=ids)


@protection_bp.get("/api/guilds/<int:guild_id>/protection/events")
@login_required
def list_events(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    limit = _as_int(request.args.get("limit", 50), 50, 1, 200)
    offset = _as_int(request.args.get("offset", 0), 0, 0, 1000000)
    q = g.db.query(ProtectionEvent).filter(ProtectionEvent.guild_id == guild_id)
    days = request.args.get("days", "")
    if days.isdigit() and 0 < int(days) <= 365:
        q = q.filter(ProtectionEvent.created_at >= datetime.utcnow() - timedelta(days=int(days)))
    category = (request.args.get("category") or request.args.get("action_type") or "").strip()[:24]
    if category:
        q = q.filter(ProtectionEvent.category == category)
    total = q.count()
    events = (
        q.order_by(ProtectionEvent.created_at.desc(), ProtectionEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return jsonify(events=[e.to_dict() for e in events], total=total, offset=offset, limit=limit)


@protection_bp.get("/api/guilds/<int:guild_id>/ai-status")
@login_required
def ai_status(guild_id: int):
    """Powers the AI Activity status panel: which AI layers are on + action counts.
    Each block carries a `link` (tab/sub[/focus]) so the dashboard chips can jump
    straight to the relevant setting."""
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    row = protection.get_or_create(g.db, guild_id)
    extra = protection._merged_extra(row)
    smart = (extra.get("automod") or {}).get("smart_mod") or {}
    social = extra.get("social_replies") or {}
    kb = extra.get("kb_replies") or {}
    docs = g.db.query(KnowledgeDocument).filter(KnowledgeDocument.guild_id == guild_id).count()

    now = datetime.utcnow()
    day = now - timedelta(days=1)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)

    def _count(since=None):
        q = g.db.query(ProtectionEvent).filter(
            ProtectionEvent.guild_id == guild_id,
            ProtectionEvent.category.in_(_AI_CATEGORIES))
        if since is not None:
            q = q.filter(ProtectionEvent.created_at >= since)
        return q.count()

    last = (g.db.query(ProtectionEvent)
            .filter(ProtectionEvent.guild_id == guild_id,
                    ProtectionEvent.category.in_(_AI_CATEGORIES))
            .order_by(ProtectionEvent.created_at.desc()).first())

    return jsonify(
        provider=ai._provider(),
        provider_connected=ai.is_configured(),
        smart_moderation=bool(smart.get("enabled")),
        smart_mod_ai=bool(smart.get("ai_enabled", True)),
        human_like=bool(social.get("enabled")),
        kb_configured=bool(docs > 0 or kb.get("enabled")),
        kb_docs=docs,
        last_action_at=last.created_at.isoformat() + "Z" if last and last.created_at else None,
        counts={"today": _count(day), "week": _count(week),
                "month": _count(month), "total": _count()},
        links={
            "smart_moderation": {"tab": "Moderation", "sub": "Behavior", "focus": "gz.moderation.smart_moderation"},
            "human_like": {"tab": "Moderation", "sub": "Behavior", "focus": "gz.moderation.social_replies"},
            "knowledge_base": {"tab": "AI & Integrations", "sub": "Knowledge Base", "focus": "ai.knowledge_base"},
            "provider": {"tab": "AI & Integrations", "sub": "Knowledge Base", "focus": "ai.platform_ai"},
        },
    )


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


# --- Dashboard moderation actions (Telegizer-parity audit/warnings row menu) ---
# warn / mute (timeout) / kick / tempban / ban, performed via Discord REST so the
# web can act on a member without a gateway. Each is logged to the audit feed.
_MOD_ACTIONS = {"warn", "mute", "kick", "tempban", "ban", "unmute", "unban"}
_EVENT_ACTION = {"warn": "warned", "mute": "timeout", "kick": "kick", "tempban": "ban", "ban": "ban",
                 "unmute": "untimeout", "unban": "unban"}


@protection_bp.post("/api/guilds/<int:guild_id>/moderation/action")
@login_required
def moderation_action(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    guild = g.db.get(Guild, guild_id)
    if guild is None:
        return jsonify(error="not_found"), 404
    if not guild.is_served:
        return jsonify(error="bot_not_in_server"), 409

    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").lower()
    if action not in _MOD_ACTIONS:
        return jsonify(error="bad_action"), 400
    uid_raw = str(body.get("user_id") or "")
    if not uid_raw.isdigit():
        return jsonify(error="bad_user_id"), 400
    user_id = int(uid_raw)
    username = (body.get("username") or "")[:120] or None
    reason = (body.get("reason") or "Dashboard action")[:300]
    minutes = _as_int(body.get("minutes", 60), 60, 1, 40320)  # mute/tempban window

    import discord_api
    try:
        if action == "warn":
            g.db.add(MemberWarning(
                guild_id=guild_id, user_id=user_id, username=username,
                moderator_id=None, moderator_name="Dashboard", reason=reason,
            ))
        elif action == "mute":
            until = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat() + "Z"
            discord_api.timeout_member(guild_id, user_id, until, reason)
        elif action == "kick":
            discord_api.kick_member(guild_id, user_id, reason)
        elif action == "ban":
            discord_api.ban_member(guild_id, user_id, reason)
        elif action == "tempban":
            discord_api.ban_member(guild_id, user_id, reason)
            moderation_runtime.schedule_unban(g.db, guild_id, user_id, username, minutes * 60, reason)
        elif action == "unmute":
            discord_api.timeout_member(guild_id, user_id, None, reason)
        elif action == "unban":
            discord_api.unban_member(guild_id, user_id, reason)
    except Exception:
        return jsonify(error="discord_action_failed"), 502

    g.db.add(ProtectionEvent(
        guild_id=guild_id, category="moderation", action=_EVENT_ACTION[action],
        user_id=user_id, username=username, detail=f"{action} · {reason}"[:255],
    ))
    g.db.commit()
    return jsonify(ok=True, action=action)


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
