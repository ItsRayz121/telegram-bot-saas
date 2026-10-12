"""Read-only analytics summaries for the Guildizer dashboard.

  GET /api/guilds/<id>/insights/members
  GET /api/guilds/<id>/insights/audit?days=
  GET /api/guilds/<id>/insights/warnings?days=
  GET /api/guilds/<id>/insights/ai?days=
  GET /api/guilds/<id>/insights/digest-preview?label=

Ported from Telegizer's analytics_insights (logic copied, not imported). Summaries
are computed on the server over the WHOLE server (not just the rows the table shows
on screen) and are scoped to the one server in the URL. Nothing here writes, sends a
Discord message or calls an AI model; the digest preview builds the text the real
digest would post and never posts it.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

import access
import digest_runtime
from auth import login_required
from models import AITokenUsage, FeatureUsageEvent, Guild, Member, MemberWarning, ProtectionEvent

insights_bp = Blueprint("analytics_insights", __name__)

MAX_ROWS = 50000
LEVEL_BUCKETS = ((1, 4), (5, 9), (10, 19), (20, 49), (50, 10 ** 6))
# Categories that come from AI layers (used to split "AI" from rule-based events).
AI_CATEGORIES = ("smart_mod", "smart_promo", "image_ai", "image_nsfw", "ask", "ai", "escalation")


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _days(default=30):
    try:
        d = int(request.args.get("days", default))
    except (TypeError, ValueError):
        d = default
    return d if d in (7, 14, 30, 90) else default


def _daily(datetimes, days):
    today = datetime.utcnow().date()
    counts = Counter(d.date() for d in datetimes if d)
    return [{"date": (today - timedelta(days=i)).isoformat(),
             "count": counts.get(today - timedelta(days=i), 0)} for i in range(days - 1, -1, -1)]


def _guard(guild_id):
    ok, err = access.manage_or_403(g.db, g.user_id, guild_id)
    return None if ok else err


# ── members ────────────────────────────────────────────────────────────────────
def members_summary(db, guild_id):
    now = datetime.utcnow()
    base = db.query(Member).filter(Member.guild_id == guild_id)
    total = base.count()

    def active_since(delta):
        return base.filter(Member.last_seen >= now - delta).count()

    # A LIST, not a dict: JSON objects are serialised with sorted keys ("10-19"
    # before "5-9"), which scrambled the order the buckets are meant to read in.
    levels = []
    for lo, hi in LEVEL_BUCKETS:
        label = f"{lo}+" if hi >= 10 ** 6 else (f"{lo}" if lo == hi else f"{lo}-{hi}")
        levels.append({"label": label, "count": base.filter(Member.level >= lo, Member.level <= hi).count()})
    warned = (db.query(func.count(func.distinct(MemberWarning.user_id)))
              .filter(MemberWarning.guild_id == guild_id).scalar() or 0)
    return {
        "total": total,
        "active": {"24h": active_since(timedelta(days=1)), "7d": active_since(timedelta(days=7)),
                   "30d": active_since(timedelta(days=30))},
        "never_seen": base.filter(Member.last_seen.is_(None)).count(),
        "verified": base.filter(Member.verified.is_(True)).count(),
        "with_wallet": base.filter(Member.wallet.isnot(None), Member.wallet != "").count(),
        "with_warnings": int(warned),
        "total_xp": int(base.with_entities(func.coalesce(func.sum(Member.xp), 0)).scalar() or 0),
        "level_distribution": levels,
        "generated_at": now.isoformat() + "Z",
        "note": "Active means the member was seen sending a message in that window. Counts cover every tracked member, not only the rows on screen.",
    }


# ── audit log ──────────────────────────────────────────────────────────────────
def audit_summary(db, guild_id, days):
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    rows = (db.query(ProtectionEvent.category, ProtectionEvent.action, ProtectionEvent.user_id,
                     ProtectionEvent.username, ProtectionEvent.created_at)
            .filter(ProtectionEvent.guild_id == guild_id, ProtectionEvent.created_at >= since)
            .limit(MAX_ROWS).all())
    by_cat = Counter(r[0] or "other" for r in rows)
    by_action = Counter(r[1] or "none" for r in rows)
    by_pair = Counter((r[0] or "other", r[1] or "none") for r in rows)
    users = Counter((r[2], r[3]) for r in rows if r[2])
    ai = sum(n for c, n in by_cat.items() if c in AI_CATEGORIES)
    return {
        "days": days, "total": len(rows),
        "by_category": [{"category": k, "count": v} for k, v in by_cat.most_common()],
        "by_action": [{"action": k, "count": v} for k, v in by_action.most_common()],
        "grouped": [{"category": c, "action": a, "count": n} for (c, a), n in by_pair.most_common(30)],
        "most_actioned_members": [{"user_id": str(u), "username": name, "count": n}
                                  for (u, name), n in users.most_common(5)],
        "ai_events": ai, "rule_events": len(rows) - ai,
        "series": _daily([r[4] for r in rows], days),
        "truncated": len(rows) >= MAX_ROWS,
    }


# ── warnings ───────────────────────────────────────────────────────────────────
def warnings_summary(db, guild_id, days):
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    all_rows = (db.query(MemberWarning.user_id, MemberWarning.username, MemberWarning.moderator_id,
                         MemberWarning.moderator_name, MemberWarning.created_at)
                .filter(MemberWarning.guild_id == guild_id).limit(MAX_ROWS).all())
    recent = [r for r in all_rows if r[4] and r[4] >= since]
    per_user = Counter((r[0], r[1]) for r in all_rows)
    automod = sum(1 for r in all_rows if r[2] is None)
    by_mod = Counter(r[3] or str(r[2]) for r in all_rows if r[2] is not None)
    return {
        "days": days,
        "total": len(all_rows),
        "members_warned": len({r[0] for r in all_rows}),
        "recent": len(recent),
        "from_automod": automod, "from_moderators": len(all_rows) - automod,
        "repeat_offenders": sum(1 for n in per_user.values() if n >= 2),
        "top_warned": [{"user_id": str(u), "username": name, "count": n}
                       for (u, name), n in per_user.most_common(5)],
        "by_moderator": [{"name": k, "count": v} for k, v in by_mod.most_common(5)],
        "series": _daily([r[4] for r in recent], days),
        "note": "Warnings stay on record until a moderator removes them, so every stored warning counts as active.",
    }


# ── AI activity ────────────────────────────────────────────────────────────────
def ai_summary(db, guild_id, days):
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    usage = (db.query(AITokenUsage.model, AITokenUsage.input_tokens, AITokenUsage.output_tokens,
                      AITokenUsage.created_at)
             .filter(AITokenUsage.guild_id == guild_id, AITokenUsage.created_at >= since)
             .limit(MAX_ROWS).all())
    by_model = Counter()
    tokens_in = tokens_out = 0
    for model, i, o, _ in usage:
        by_model[model or "unknown"] += 1
        tokens_in += i or 0
        tokens_out += o or 0
    events = (db.query(ProtectionEvent.category, ProtectionEvent.action)
              .filter(ProtectionEvent.guild_id == guild_id, ProtectionEvent.created_at >= since,
                      ProtectionEvent.category.in_(AI_CATEGORIES)).limit(MAX_ROWS).all())
    removed = sum(1 for c, a in events if a not in (None, "none"))
    feature = dict(db.query(FeatureUsageEvent.feature, func.count(FeatureUsageEvent.id))
                   .filter(FeatureUsageEvent.guild_id == guild_id, FeatureUsageEvent.created_at >= since,
                           FeatureUsageEvent.feature.ilike("%ai%"))
                   .group_by(FeatureUsageEvent.feature).all())
    return {
        "days": days,
        "requests": len(usage),
        "tokens_in": tokens_in, "tokens_out": tokens_out,
        "by_model": [{"model": k, "requests": v} for k, v in by_model.most_common()],
        "moderation_decisions": len(events), "moderation_removals": removed,
        "moderation_no_action": len(events) - removed,
        "feature_usage": {k: int(v) for k, v in feature.items()},
        "series": _daily([u[3] for u in usage], days),
        "note": "Requests and tokens come from the AI usage ledger; moderation decisions from Protection Activity (AI layers only). Review-mode and unsure verdicts are counted as no action.",
    }


# ── digest preview ─────────────────────────────────────────────────────────────
def digest_preview(guild, label):
    """The text the digest would post right now. Built by the real digest builder;
    nothing is sent."""
    label = label if label in ("Daily", "Weekly", "Monthly") else "Daily"
    cfg = digest_runtime.get_config(guild.id)
    return {
        "label": label,
        "text": digest_runtime.build_stats_text(guild.id, guild.name or str(guild.id), label),
        "enabled": bool(cfg.get("enabled")),
        "channel_id": cfg.get("channel_id"),
        "cadence": cfg.get("cadence"),
        "note": "Preview only: nothing was posted. Figures cover today so far.",
    }


# ── routes ─────────────────────────────────────────────────────────────────────
@insights_bp.get("/api/guilds/<int:guild_id>/insights/members")
@login_required
def r_members(guild_id: int):
    err = _guard(guild_id)
    return err or jsonify(members_summary(g.db, guild_id))


@insights_bp.get("/api/guilds/<int:guild_id>/insights/audit")
@login_required
def r_audit(guild_id: int):
    err = _guard(guild_id)
    return err or jsonify(audit_summary(g.db, guild_id, _days()))


@insights_bp.get("/api/guilds/<int:guild_id>/insights/warnings")
@login_required
def r_warnings(guild_id: int):
    err = _guard(guild_id)
    return err or jsonify(warnings_summary(g.db, guild_id, _days()))


@insights_bp.get("/api/guilds/<int:guild_id>/insights/ai")
@login_required
def r_ai(guild_id: int):
    err = _guard(guild_id)
    return err or jsonify(ai_summary(g.db, guild_id, _days()))


@insights_bp.get("/api/guilds/<int:guild_id>/insights/digest-preview")
@login_required
def r_digest(guild_id: int):
    err = _guard(guild_id)
    if err:
        return err
    guild = g.db.get(Guild, guild_id)
    return jsonify(digest_preview(guild, request.args.get("label", "Daily")))
