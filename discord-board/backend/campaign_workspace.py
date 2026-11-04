"""Read-only data behind the Guildizer campaign workspace (overview, directory,
review queue, per-campaign summary and activity).

  GET /api/guilds/<id>/campaign-workspace/overview?days=
  GET /api/guilds/<id>/campaign-workspace/campaigns?q&status&type&sort&dir&page&per_page
  GET /api/guilds/<id>/campaign-workspace/queue?status&campaign_id&q&flagged&sort&page&per_page
  GET /api/guilds/<id>/campaign-workspace/campaigns/<cid>/summary?days=
  GET /api/guilds/<id>/campaign-workspace/campaigns/<cid>/activity

Ported from Telegizer's engagement_insights (logic copied, not imported).
Everything is scoped to ONE server: the campaign base query filters on guild_id and
every submission query joins through it, so a campaign or submission id from another
server can never be returned, even if guessed. Nothing here writes, posts to Discord
or calls AI. Reviewing, publishing, editing and deleting stay in campaigns_api.

Honesty rules (same as Telegizer):
  * "Approved" means submissions with status `verified`; each submission counts once.
    The deduplicated people count is returned separately and labelled.
  * Review decisions are counted by reviewed_at, submissions by created_at - the two
    series are never mixed.
  * Verification source is derived from what is actually stored.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import String, case, cast, func

import access
import campaign_rewards
from auth import login_required
from models import Campaign, CampaignSubmission as S, CampaignTask, CampaignCustomField, Guild

workspace_bp = Blueprint("campaign_workspace", __name__)

MAX_ROWS = 50000
# A pending submission is flagged "waiting long" after this many hours. There is no
# configured review SLA, so this is a display threshold only and is returned with
# the response so the UI can state it.
STALE_REVIEW_HOURS = 48
ENDING_SOON_HOURS = 24
CAMPAIGN_SORTS = ("created_at", "title", "ends_at", "status", "type", "submitted", "approved", "pending")


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _int(name, default, lo=1, hi=1000):
    try:
        return min(hi, max(lo, int(request.args.get(name, default))))
    except (TypeError, ValueError):
        return default


def _campaigns(guild_id):
    return g.db.query(Campaign).filter(Campaign.guild_id == guild_id)


def _submissions(guild_id):
    return (g.db.query(S).join(Campaign, Campaign.id == S.campaign_id)
            .filter(Campaign.guild_id == guild_id))


def _daily(datetimes, days):
    today = datetime.utcnow().date()
    counts = Counter(d.date() for d in datetimes if d)
    return {(today - timedelta(days=i)).isoformat(): counts.get(today - timedelta(days=i), 0)
            for i in range(days - 1, -1, -1)}


def verification_source(campaign, sub):
    """Where a verified submission's approval came from, derived from stored fields."""
    if sub.status != "verified":
        return None
    if sub.reviewer_id:
        return "admin"
    if campaign.type == "raid" and (campaign.settings or {}).get("auto_verify_x"):
        return "api"
    return {"honor": "self_reported", "auto": "automatic", "link": "link_check"}.get(
        campaign.verification_mode, "automatic")


def _progress(campaign, status_user_pairs, proofs=None):
    """Progress only where a real target exists: unique approved people vs
    max_participants, and per-action verified counts vs raid/social goals (a
    different unit, so they are returned separately)."""
    out = {}
    if campaign.max_participants:
        done = len({u for st, u in status_user_pairs if st == "verified"})
        out["participants"] = {"done": done, "target": campaign.max_participants}
    if proofs is not None:
        try:
            from campaign_runtime import campaign_action_goals
            goals = campaign_action_goals(campaign)
        except Exception:
            goals = []
        if goals:
            rows = []
            for gk, act, target in goals:
                done = sum(1 for p in proofs
                           if (((p or {}).get("actions") or {}).get(act) or {}).get("status") == "verified")
                rows.append({"goal": gk, "action": act, "done": done, "target": int(target)})
            out["actions"] = rows
    return out


def _counts_by_campaign(guild_id, ids):
    """{campaign_id: {total, pending, verified, rejected}} in one grouped query."""
    if not ids:
        return {}
    rows = (g.db.query(S.campaign_id, S.status, func.count(S.id))
            .filter(S.campaign_id.in_(ids)).group_by(S.campaign_id, S.status).all())
    out = {i: {"total": 0, "pending": 0, "verified": 0, "rejected": 0} for i in ids}
    for cid, status, n in rows:
        d = out[cid]
        d["total"] += int(n)
        if status in d:
            d[status] = int(n)
    return out


def _running_row(c, counts):
    rows = (g.db.query(S.status, S.user_id, S.proof).filter(S.campaign_id == c.id).limit(MAX_ROWS).all())
    pairs = [(r[0], r[1]) for r in rows]
    return {
        "id": c.id, "title": c.title, "type": c.type, "platform": c.platform, "status": c.status,
        "ends_at": _iso(c.ends_at), "post_status": c.post_status or "none",
        "counts": counts, "progress": _progress(c, pairs, [r[2] for r in rows]),
        # Telegizer-shaped flat counters (the shared workspace pages read these).
        "submitted": counts["total"], "pending": counts["pending"], "approved": counts["verified"],
    }


# ── overview ───────────────────────────────────────────────────────────────────
def overview(guild_id, days=30):
    days = days if days in (7, 14, 30, 90) else 30
    now = datetime.utcnow()
    since = now - timedelta(days=days)

    status_counts = dict(_submissions(guild_id).with_entities(S.status, func.count(S.id)).group_by(S.status).all())
    pending = int(status_counts.get("pending", 0))
    approved = int(status_counts.get("verified", 0))
    rejected = int(status_counts.get("rejected", 0))
    unique_approved = (_submissions(guild_id).filter(S.status == "verified")
                       .with_entities(func.count(func.distinct(S.user_id))).scalar() or 0)
    camp_counts = dict(_campaigns(guild_id).with_entities(Campaign.status, func.count(Campaign.id))
                       .group_by(Campaign.status).all())

    # attention: only conditions that exist in the data
    attention = []
    for c in _campaigns(guild_id).filter(Campaign.status == "active", Campaign.post_status == "failed").all():
        attention.append({"kind": "post_failed", "campaign_id": c.id, "title": c.title,
                          "detail": c.post_error or "The last attempt to post to the server failed."})
    for c in _campaigns(guild_id).filter(Campaign.status == "active", Campaign.post_status == "none").all():
        attention.append({"kind": "not_posted", "campaign_id": c.id, "title": c.title,
                          "detail": "Active but not posted to the server yet."})
    stale_q = _submissions(guild_id).filter(S.status == "pending",
                                            S.created_at <= now - timedelta(hours=STALE_REVIEW_HOURS))
    stale = stale_q.count()
    if stale:
        oldest = stale_q.with_entities(func.min(S.created_at)).scalar()
        attention.append({"kind": "stale_reviews", "count": stale, "oldest_at": _iso(oldest),
                          "detail": f"{stale} submission{'s' if stale != 1 else ''} waiting more than {STALE_REVIEW_HOURS} hours."})
    flagged = _submissions(guild_id).filter(S.status == "pending", S.flagged.is_(True)).count()
    if flagged:
        attention.append({"kind": "flagged_pending", "count": flagged,
                          "detail": f"{flagged} pending submission{'s' if flagged != 1 else ''} flagged as possible duplicates."})
    for c in (_campaigns(guild_id).filter(Campaign.status == "active", Campaign.ends_at.isnot(None),
                                          Campaign.ends_at > now,
                                          Campaign.ends_at <= now + timedelta(hours=ENDING_SOON_HOURS)).all()):
        attention.append({"kind": "ending_soon", "campaign_id": c.id, "title": c.title, "ends_at": _iso(c.ends_at),
                          "detail": f"Ends within {ENDING_SOON_HOURS} hours."})

    sub_dates = [r[0] for r in _submissions(guild_id).filter(S.created_at >= since)
                 .with_entities(S.created_at).limit(MAX_ROWS)]
    dec_dates = [r[0] for r in _submissions(guild_id).filter(S.reviewed_at.isnot(None), S.reviewed_at >= since)
                 .with_entities(S.reviewed_at).limit(MAX_ROWS)]
    s_by, d_by = _daily(sub_dates, days), _daily(dec_dates, days)
    series = [{"date": d, "submitted": s_by[d], "decisions": d_by[d]} for d in s_by]

    running = (_campaigns(guild_id).filter(Campaign.status == "active")
               .order_by(func.coalesce(Campaign.ends_at, datetime(9999, 1, 1)).asc(),
                         Campaign.created_at.desc()).limit(8).all())
    counts = _counts_by_campaign(guild_id, [c.id for c in running])
    guild = g.db.get(Guild, guild_id)
    x_status = "disabled"
    try:
        import twitter_verify
        x_status = twitter_verify.autoverify_status(guild.owner_id) if guild else "disabled"
    except Exception:
        pass
    return {
        "days": days, "generated_at": now.isoformat() + "Z",
        "timezone": "UTC", "group_title": guild.name if guild else None,
        "x_autoverify_status": x_status,
        "totals": {
            "active_campaigns": int(camp_counts.get("active", 0)),
            "pending_review": pending, "approved_submissions": approved, "rejected_submissions": rejected,
            "approved_unique_participants": int(unique_approved),
            "campaigns_total": int(sum(camp_counts.values())),
            "campaigns_by_status": {k: int(v) for k, v in camp_counts.items()},
        },
        "attention": attention, "stale_review_hours": STALE_REVIEW_HOURS,
        "series": series,
        "series_totals": {"submitted": sum(s_by.values()), "decisions": sum(d_by.values())},
        "series_note": "Submissions are counted by the time they were sent; decisions by the time a reviewer approved or rejected. Automatic approvals are not review decisions.",
        "running": [_running_row(c, counts[c.id]) for c in running],
    }


# ── directory ──────────────────────────────────────────────────────────────────
def campaigns_page(guild_id, q="", status="", ctype="", sort="created_at", direction="desc", page=1, per_page=20):
    base = _campaigns(guild_id)
    if q:
        base = base.filter(Campaign.title.ilike("%" + q.replace("%", "").replace("_", "") + "%"))
    if status:
        base = base.filter(Campaign.status == status)
    if ctype:
        base = base.filter(Campaign.type == ctype)
    total = base.count()

    # per-campaign counts as a subquery so the counter sorts can run in SQL
    sub = (g.db.query(S.campaign_id.label("cid"),
                      func.count(S.id).label("submitted"),
                      func.sum(case((S.status == "verified", 1), else_=0)).label("approved"),
                      func.sum(case((S.status == "pending", 1), else_=0)).label("pending"))
           .group_by(S.campaign_id).subquery())
    sort = sort if sort in CAMPAIGN_SORTS else "created_at"
    keyed = base.outerjoin(sub, sub.c.cid == Campaign.id)
    col = {
        "created_at": Campaign.created_at, "title": func.lower(Campaign.title), "status": Campaign.status,
        "type": Campaign.type, "ends_at": Campaign.ends_at,
        "submitted": func.coalesce(sub.c.submitted, 0), "approved": func.coalesce(sub.c.approved, 0),
        "pending": func.coalesce(sub.c.pending, 0),
    }[sort]
    order = col.asc() if direction == "asc" else col.desc()
    if sort == "ends_at":
        # campaigns without a deadline always sort last
        keyed = keyed.order_by(Campaign.ends_at.is_(None), order, Campaign.id.desc())
    else:
        keyed = keyed.order_by(order, Campaign.id.desc())
    rows = keyed.offset((page - 1) * per_page).limit(per_page).all()
    counts = _counts_by_campaign(guild_id, [c.id for c in rows])
    return {
        "campaigns": [{
            "id": c.id, "title": c.title, "type": c.type, "platform": c.platform, "status": c.status,
            "created_at": _iso(c.created_at), "starts_at": _iso(c.starts_at), "ends_at": _iso(c.ends_at),
            "post_status": c.post_status or "none", "post_error": c.post_error,
            "reward_xp": c.reward_xp or 0, "reward_label": c.reward_label, "counts": counts[c.id],
            "submitted": counts[c.id]["total"], "approved": counts[c.id]["verified"],
            "pending": counts[c.id]["pending"],
        } for c in rows],
        "page": page, "per_page": per_page, "total": total,
        "pages": max(1, -(-total // per_page)),
        "status_counts": {k: int(v) for k, v in
                          _campaigns(guild_id).with_entities(Campaign.status, func.count(Campaign.id))
                          .group_by(Campaign.status).all()},
        "timezone": "UTC",
    }


# ── review queue ───────────────────────────────────────────────────────────────
def queue(guild_id, status="pending", campaign_id=None, q="", flagged=False, sort="oldest", page=1, per_page=25):
    base = _submissions(guild_id)
    if status in ("pending", "verified", "rejected"):
        base = base.filter(S.status == status)
    if campaign_id:
        base = base.filter(S.campaign_id == campaign_id)
    if flagged:
        base = base.filter(S.flagged.is_(True))
    if q:
        like = "%" + q.replace("%", "").replace("_", "") + "%"
        base = base.filter(S.username.ilike(like) | (cast(S.user_id, String) == q) | Campaign.title.ilike(like))
    total = base.count()
    base = base.order_by(S.created_at.desc() if sort == "newest" else S.created_at.asc(), S.id.asc())
    rows = base.offset((page - 1) * per_page).limit(per_page).all()
    camps = {c.id: c for c in g.db.query(Campaign).filter(Campaign.id.in_({r.campaign_id for r in rows})).all()} if rows else {}
    tasks = {t.id: t for t in g.db.query(CampaignTask).filter(
        CampaignTask.id.in_({r.task_id for r in rows if r.task_id})).all()} if rows else {}
    fields = {}
    if camps:
        for f in g.db.query(CampaignCustomField).filter(CampaignCustomField.campaign_id.in_(list(camps))).all():
            fields.setdefault(f.campaign_id, {})[f.key or f.label] = {"label": f.label, "field_type": f.field_type or "text"}
    now = datetime.utcnow()
    out = []
    for r in rows:
        c = camps.get(r.campaign_id)
        d = r.to_dict()
        d.update({
            # Telegizer-shaped aliases so the shared pages render Discord rows unchanged.
            "telegram_user_id": d["user_id"], "telegram_username": r.username,
            "payload": r.proof or {}, "has_file": bool(r.file_url),
            "reviewed_by_name": r.reviewer_name,
            "campaign_status": c.status if c else None,
            "task_title": tasks[r.task_id].title if r.task_id in tasks else None,
            "field_labels": {"value": {"label": "Proof", "field_type": "text"}, **fields.get(r.campaign_id, {})},
            "campaign_title": c.title if c else None, "campaign_type": c.type if c else None,
            "waiting_hours": round((now - r.created_at).total_seconds() / 3600, 1) if r.created_at and r.status == "pending" else None,
            "waiting_long": bool(r.status == "pending" and r.created_at and now - r.created_at > timedelta(hours=STALE_REVIEW_HOURS)),
            "verification_source": verification_source(c, r) if c else None,
        })
        out.append(d)
    return {"submissions": out, "items": out, "page": page, "per_page": per_page, "total": total,
            "pages": max(1, -(-total // per_page)), "stale_review_hours": STALE_REVIEW_HOURS,
            "pending_total": _submissions(guild_id).filter(S.status == "pending").count(),
            "timezone": "UTC",
            "campaigns": [{"id": c.id, "title": c.title, "status": c.status} for c in
                          _campaigns(guild_id).order_by(Campaign.created_at.desc()).limit(200).all()]}


# ── one campaign ───────────────────────────────────────────────────────────────
def campaign_summary(c, days=30):
    days = days if days in (7, 14, 30, 90) else 30
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    subs = g.db.query(S).filter(S.campaign_id == c.id).limit(MAX_ROWS).all()
    by_status = Counter(s.status for s in subs)
    approved_users = {s.user_id for s in subs if s.status == "verified"}
    sources = Counter(verification_source(c, s) for s in subs if s.status == "verified")
    review_hours = [(s.reviewed_at - s.created_at).total_seconds() / 3600
                    for s in subs if s.reviewer_id and s.reviewed_at and s.created_at]
    by_task = []
    for t in g.db.query(CampaignTask).filter(CampaignTask.campaign_id == c.id).order_by(CampaignTask.order).all():
        ts = [s for s in subs if s.task_id == t.id]
        by_task.append({"task_id": t.id, "title": t.title,
                        "submitted": len(ts), "approved": sum(1 for s in ts if s.status == "verified"),
                        "pending": sum(1 for s in ts if s.status == "pending")})
    reviewers = Counter(s.reviewer_name for s in subs if s.reviewer_name)
    oldest_pending = min((s.created_at for s in subs if s.status == "pending" and s.created_at), default=None)
    s_by = _daily([s.created_at for s in subs if s.created_at and s.created_at >= since], days)
    d_by = _daily([s.reviewed_at for s in subs if s.reviewed_at and s.reviewed_at >= since], days)
    return {
        "campaign": {"id": c.id, "title": c.title, "type": c.type, "platform": c.platform, "status": c.status,
                     "starts_at": _iso(c.starts_at), "ends_at": _iso(c.ends_at), "reward_xp": c.reward_xp or 0,
                     "post_status": c.post_status, "post_error": c.post_error,
                     "max_participants": c.max_participants},
        "counts": {"total": len(subs), "pending": by_status.get("pending", 0),
                   "verified": by_status.get("verified", 0), "rejected": by_status.get("rejected", 0),
                   "flagged_pending": sum(1 for s in subs if s.status == "pending" and s.flagged),
                   "submitted": len(subs), "approved": by_status.get("verified", 0),
                   "flagged": sum(1 for s in subs if s.flagged)},
        "approved_unique_participants": len(approved_users),
        "xp_granted": int(sum((s.reward_granted or 0) for s in subs)),
        "verification_sources": dict(sources),
        "avg_review_hours": round(sum(review_hours) / len(review_hours), 1) if review_hours else None,
        "progress": _progress(c, [(s.status, s.user_id) for s in subs], [s.proof for s in subs]),
        # Telegizer-shaped blocks (shared Summary tab).
        "campaign_id": c.id,
        "people": {"submitted_unique": len({s.user_id for s in subs}), "approved_unique": len(approved_users)},
        "rewards": {"xp_per_approval": campaign_rewards.effective_reward(c), "action_xp": campaign_rewards.action_xp_map(c),
                    "submissions_rewarded": sum(1 for s in subs if (s.reward_granted or 0) > 0),
                    "label": c.reward_label,
                    "note": "XP is granted once per approved submission. Reward labels are free text; no payments are recorded."},
        "oldest_pending_at": _iso(oldest_pending),
        "oldest_pending_hours": round((now - oldest_pending).total_seconds() / 3600, 1) if oldest_pending else None,
        "by_task": by_task,
        "reviewers": [{"name": n, "decisions": k} for n, k in reviewers.most_common(5)],
        "series": [{"date": d, "submitted": s_by[d], "decisions": d_by[d]} for d in s_by],
        "days": days,
    }


def _who(s):
    return f"@{s.username}" if s.username else f"User {s.user_id}"


def campaign_activity(c, limit=60):
    """Newest-first timeline built from stored rows: submissions and decisions."""
    subs = (g.db.query(S).filter(S.campaign_id == c.id).order_by(S.id.desc()).limit(200).all())
    events = []
    for s in subs:
        if s.created_at:
            events.append({"at": _iso(s.created_at), "kind": "submitted", "user_id": str(s.user_id),
                           "username": s.username, "who": _who(s), "submission_id": s.id})
        if s.reviewed_at and s.status in ("verified", "rejected"):
            events.append({"at": _iso(s.reviewed_at), "kind": "approved" if s.status == "verified" else "rejected",
                           "user_id": str(s.user_id), "username": s.username, "who": _who(s),
                           "submission_id": s.id, "by": s.reviewer_name or ("automatic" if not s.reviewer_id else None),
                           "reason": s.review_reason})
    events.sort(key=lambda e: e["at"], reverse=True)
    if c.posted_at:
        events.append({"at": _iso(c.posted_at), "kind": "posted", "who": None})
    return {"events": events[:limit], "created_at": _iso(c.created_at)}


# ── routes ─────────────────────────────────────────────────────────────────────
def _guard(guild_id):
    ok, err = access.manage_or_403(g.db, g.user_id, guild_id)
    return None if ok else err


@workspace_bp.get("/api/guilds/<int:guild_id>/campaign-workspace/overview")
@login_required
def ws_overview(guild_id: int):
    err = _guard(guild_id)
    if err:
        return err
    return jsonify(overview(guild_id, days=_int("days", 30, 1, 90)))


@workspace_bp.get("/api/guilds/<int:guild_id>/campaign-workspace/campaigns")
@login_required
def ws_campaigns(guild_id: int):
    err = _guard(guild_id)
    if err:
        return err
    return jsonify(campaigns_page(
        guild_id, q=(request.args.get("q") or "").strip()[:100], status=request.args.get("status") or "",
        ctype=request.args.get("type") or "", sort=request.args.get("sort") or "created_at",
        direction=request.args.get("dir") or "desc", page=_int("page", 1, 1, 100000),
        per_page=_int("per_page", 20, 1, 100)))


@workspace_bp.get("/api/guilds/<int:guild_id>/campaign-workspace/queue")
@login_required
def ws_queue(guild_id: int):
    err = _guard(guild_id)
    if err:
        return err
    cid = request.args.get("campaign_id") or ""
    return jsonify(queue(
        guild_id, status=request.args.get("status") or "pending",
        campaign_id=int(cid) if cid.isdigit() else None, q=(request.args.get("q") or "").strip()[:100],
        flagged=request.args.get("flagged") == "true", sort=request.args.get("sort") or "oldest",
        page=_int("page", 1, 1, 100000), per_page=_int("per_page", 25, 1, 100)))


def _campaign_or_404(guild_id, cid):
    c = g.db.get(Campaign, cid)
    return c if c is not None and c.guild_id == guild_id else None


@workspace_bp.get("/api/guilds/<int:guild_id>/campaign-workspace/campaigns/<int:cid>/summary")
@login_required
def ws_summary(guild_id: int, cid: int):
    err = _guard(guild_id)
    if err:
        return err
    c = _campaign_or_404(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    return jsonify(campaign_summary(c, days=_int("days", 30, 1, 90)))


@workspace_bp.get("/api/guilds/<int:guild_id>/campaign-workspace/campaigns/<int:cid>/activity")
@login_required
def ws_activity(guild_id: int, cid: int):
    err = _guard(guild_id)
    if err:
        return err
    c = _campaign_or_404(guild_id, cid)
    if c is None:
        return jsonify(error="not_found"), 404
    return jsonify(campaign_activity(c))
