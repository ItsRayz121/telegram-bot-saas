"""CRM + analytics endpoints (Phase 15).

  GET /api/guilds/<id>/members?search=&sort=&limit=     member CRM list
  PUT /api/guilds/<id>/members/<uid>                    admin notes / wallet edit
  GET /api/guilds/<id>/analytics?days=14                daily rollups + totals
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

import access
import member_stats
import settings as settings_mod
from auth import login_required
from models import Guild, GuildDailyStat, Member, UserGuild

crm_bp = Blueprint("crm", __name__)

SORTS = {
    "xp": Member.xp,
    "messages": Member.messages,
    "last_seen": Member.last_seen,
}


def _manage_or_403(guild_id: int):
    return access.manage_or_403(g.db, g.user_id, guild_id)


@crm_bp.get("/api/guilds/<int:guild_id>/members")
@login_required
def list_members(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    q = g.db.query(Member).filter(Member.guild_id == guild_id)
    search = (request.args.get("search") or "").strip()
    if search:
        if search.isdigit():
            q = q.filter(Member.user_id == int(search))
        else:
            like = f"%{search}%"
            q = q.filter((Member.username.ilike(like)) | (Member.wallet.ilike(like)))
    if (request.args.get("has_wallet") or "").lower() in ("1", "true", "yes"):
        q = q.filter(Member.wallet.isnot(None), Member.wallet != "")
    period = request.args.get("period")  # 1d|today|7d|30d|all
    sort = SORTS.get(request.args.get("sort", "xp"), Member.xp)
    try:
        limit = max(1, min(200, int(request.args.get("limit", 50))))
    except ValueError:
        limit = 50

    # Period-aware XP (Telegizer parity): sum the ledger over the window and rank
    # by it. All-time keeps the cheaper Member.xp ordering.
    since = member_stats.period_since(period)
    xp_period = member_stats.xp_by_user(g.db, guild_id, since) if period and period != "all" else None
    if xp_period is not None:
        rows = q.all()
        rows.sort(key=lambda m: xp_period.get(m.user_id, 0), reverse=True)
        rows = rows[:limit]
    else:
        rows = q.order_by(sort.desc().nullslast()).limit(limit).all()

    warns = member_stats.warnings_by_user(g.db, guild_id)
    settings_row = settings_mod.get_or_create(g.db, guild_id)
    role_rewards = ((settings_row.extra or {}).get("leveling2") or {}).get("role_rewards") or []
    roles_by_level = member_stats.role_label_map(g.db, guild_id, role_rewards)

    out = []
    for m in rows:
        d = m.to_dict()
        d["warnings"] = warns.get(m.user_id, 0)
        d["verified"] = bool(getattr(m, "verified", False))
        d["has_wallet"] = bool(m.wallet)
        d["role"] = roles_by_level.get(m.level or 1)
        if xp_period is not None:
            d["xp_period"] = xp_period.get(m.user_id, 0)
        out.append(d)
    total = g.db.query(Member).filter(Member.guild_id == guild_id).count()
    return jsonify(members=out, total=total, period=period or "all")


@crm_bp.put("/api/guilds/<int:guild_id>/members/<int:user_id>")
@login_required
def update_member(guild_id: int, user_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    m = g.db.get(Member, {"guild_id": guild_id, "user_id": user_id})
    if m is None:
        return jsonify(error="not_found"), 404
    body = request.get_json(silent=True) or {}
    if "admin_notes" in body:
        m.admin_notes = str(body["admin_notes"] or "").strip()[:2000] or None
    if "wallet" in body:
        m.wallet = str(body["wallet"] or "").strip()[:120] or None
    g.db.commit()
    return jsonify(member=m.to_dict())


@crm_bp.get("/api/guilds/<int:guild_id>/analytics")
@login_required
def analytics(guild_id: int):
    ok, err = _manage_or_403(guild_id)
    if not ok:
        return err
    try:
        days = max(1, min(90, int(request.args.get("days", 14))))
    except ValueError:
        days = 14
    since = (datetime.utcnow() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    rows = (
        g.db.query(GuildDailyStat)
        .filter(GuildDailyStat.guild_id == guild_id, GuildDailyStat.day >= since)
        .order_by(GuildDailyStat.day)
        .all()
    )
    # fill missing days with zeros so charts stay continuous
    by_day = {r.day: r.to_dict() for r in rows}
    series = []
    for i in range(days):
        day = (datetime.utcnow() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        series.append(by_day.get(day, {"day": day, "messages": 0, "joins": 0, "leaves": 0}))

    midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    actives_today = (
        g.db.query(Member)
        .filter(Member.guild_id == guild_id, Member.last_seen >= midnight)
        .count()
    )
    totals = {
        "messages": sum(d["messages"] for d in series),
        "joins": sum(d["joins"] for d in series),
        "leaves": sum(d["leaves"] for d in series),
        "actives_today": actives_today,
    }
    return jsonify(series=series, totals=totals, days=days)
