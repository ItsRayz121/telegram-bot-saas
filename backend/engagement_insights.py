"""Read-only data behind the campaign workspace (overview, directory, review queue).

Everything is scoped to ONE group: the campaign base query below filters on the
group's anchor (telegram_group_id for the official bot, groups.id for custom
bots), and every submission query joins through that same filter. A submission or
campaign id from another group can therefore never be returned, even if guessed.

Nothing here writes. Reviewing, publishing, editing and deleting stay in
engagement.py and keep their existing business rules.

Honesty rules:
  * "Approved" means submissions with status `verified` - each submission counts
    once. The deduplicated people count is returned separately and labelled.
  * Review decisions are counted by reviewed_at, submissions by created_at - the
    two series are never mixed.
  * Verification source is derived from what is actually stored (reviewed_by set =
    an administrator decided; otherwise the campaign's verification mode).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import case, func

from .models import (
    db, EngagementCampaign as C, EngagementSubmission as S, EngagementTask as T, User,
)
from . import engagement as eng

MAX_ROWS = 50000
# A pending submission is flagged "waiting long" after this many hours. There is no
# configured review SLA in the product, so this is a display threshold only and is
# returned with the response so the UI can state it.
STALE_REVIEW_HOURS = 48
ENDING_SOON_HOURS = 24

CAMPAIGN_SORTS = ("created_at", "title", "ends_at", "status", "type", "submitted", "approved", "pending")


class CampaignScope:
    """One group in one bot lineage."""

    def __init__(self, scope, group):
        self.scope = scope
        self.group = group
        if scope == "official":
            self.ref = str(group.telegram_group_id)
            self.timezone = group.timezone or "UTC"
            self.title = group.title
        else:
            self.ref = group.id
            self.timezone = group.timezone or "UTC"
            self.title = group.group_name

    def campaign_filter(self):
        if self.scope == "official":
            return C.telegram_group_id == self.ref
        return C.group_id == self.ref

    def campaigns(self):
        return C.query.filter(self.campaign_filter())

    def submissions(self):
        return S.query.join(C, C.id == S.campaign_id).filter(self.campaign_filter())


def _iso(dt):
    return dt.isoformat() if dt else None


def _daily(datetimes, days):
    today = datetime.utcnow().date()
    counts = Counter(d.date() for d in datetimes if d)
    return {(today - timedelta(days=i)).isoformat(): counts.get(today - timedelta(days=i), 0)
            for i in range(days - 1, -1, -1)}


def verification_source(campaign, sub):
    """Where a verified submission's approval came from, derived from stored fields."""
    if sub.status != "verified":
        return None
    if sub.reviewed_by:
        return "admin"
    settings = campaign.settings or {}
    if campaign.type in ("raid", "social_task") and settings.get("auto_verify_x"):
        return "api"
    return {"honor": "self_reported", "auto": "telegram_auto", "link": "link_check"}.get(
        campaign.verification_mode, "automatic")


def _reviewer_names(rows):
    ids = {int(r) for r in rows if r and str(r).isdigit()}
    if not ids:
        return {}
    return {str(u.id): (u.full_name or u.email) for u in User.query.filter(User.id.in_(ids)).all()}


# ── Overview ───────────────────────────────────────────────────────────────────

def overview(cs, days=30):
    days = days if days in (7, 14, 30, 90) else 30
    now = datetime.utcnow()
    since = now - timedelta(days=days)

    status_counts = dict(
        cs.submissions().with_entities(S.status, func.count(S.id)).group_by(S.status).all())
    pending = int(status_counts.get("pending", 0))
    approved = int(status_counts.get("verified", 0))
    rejected = int(status_counts.get("rejected", 0))
    unique_approved = cs.submissions().filter(S.status == "verified").with_entities(
        func.count(func.distinct(S.telegram_user_id))).scalar() or 0

    camp_counts = dict(cs.campaigns().with_entities(C.status, func.count(C.id)).group_by(C.status).all())

    # ── attention: only conditions that exist in the data ─────────────────────
    attention = []
    failed = cs.campaigns().filter(C.status == "active", C.post_status == "failed").all()
    for c in failed:
        attention.append({"kind": "post_failed", "campaign_id": c.id, "title": c.title,
                          "detail": c.post_error or "The last attempt to post to the group failed."})
    unposted = cs.campaigns().filter(C.status == "active", C.post_status == "none").all()
    for c in unposted:
        attention.append({"kind": "not_posted", "campaign_id": c.id, "title": c.title,
                          "detail": "Active but not posted to the group yet."})
    stale_cut = now - timedelta(hours=STALE_REVIEW_HOURS)
    stale_q = cs.submissions().filter(S.status == "pending", S.created_at <= stale_cut)
    stale = stale_q.count()
    if stale:
        oldest = stale_q.with_entities(func.min(S.created_at)).scalar()
        attention.append({"kind": "stale_reviews", "count": stale, "oldest_at": _iso(oldest),
                          "detail": f"{stale} submission{'s' if stale != 1 else ''} waiting more than {STALE_REVIEW_HOURS} hours."})
    flagged = cs.submissions().filter(S.status == "pending", S.flagged.is_(True)).count()
    if flagged:
        attention.append({"kind": "flagged_pending", "count": flagged,
                          "detail": f"{flagged} pending submission{'s' if flagged != 1 else ''} flagged as possible duplicates."})
    soon = cs.campaigns().filter(C.status == "active", C.ends_at.isnot(None), C.ends_at > now,
                                 C.ends_at <= now + timedelta(hours=ENDING_SOON_HOURS)).all()
    for c in soon:
        attention.append({"kind": "ending_soon", "campaign_id": c.id, "title": c.title, "ends_at": _iso(c.ends_at),
                          "detail": f"Ends within {ENDING_SOON_HOURS} hours."})

    # ── activity: submitted vs review decisions ───────────────────────────────
    sub_dates = [r[0] for r in cs.submissions().filter(S.created_at >= since).with_entities(S.created_at).limit(MAX_ROWS)]
    dec_dates = [r[0] for r in cs.submissions().filter(S.reviewed_at.isnot(None), S.reviewed_at >= since)
                 .with_entities(S.reviewed_at).limit(MAX_ROWS)]
    s_by, d_by = _daily(sub_dates, days), _daily(dec_dates, days)
    series = [{"date": d, "submitted": s_by[d], "decisions": d_by[d]} for d in s_by]

    # ── running campaigns with the figures that matter ────────────────────────
    running = cs.campaigns().filter(C.status == "active").order_by(
        func.coalesce(C.ends_at, datetime(9999, 1, 1)).asc(), C.created_at.desc()).limit(8).all()
    return {
        "days": days, "timezone": cs.timezone, "group_title": cs.title,
        "totals": {
            "active_campaigns": int(camp_counts.get("active", 0)),
            "pending_review": pending,
            "approved_submissions": approved,
            "rejected_submissions": rejected,
            "approved_unique_participants": int(unique_approved),
            "campaigns_total": int(sum(camp_counts.values())),
            "campaigns_by_status": {k: int(v) for k, v in camp_counts.items()},
        },
        "attention": attention, "stale_review_hours": STALE_REVIEW_HOURS,
        "series": series,
        "series_totals": {"submitted": sum(s_by.values()), "decisions": sum(d_by.values())},
        "series_note": "Submissions are counted by the time they were sent; decisions by the time a reviewer approved or rejected. Automatic approvals are not review decisions.",
        "running": [_running_row(c) for c in running],
        "generated_at": now.isoformat() + "Z",
    }


def _progress(campaign, subs):
    """Progress figures for a campaign, only where a real target exists.

    participants: unique approved people vs max_participants (a participant target).
    actions: per-action verified counts vs the raid/social goals (a different unit).
    """
    out = {}
    if campaign.max_participants:
        done = len({s.telegram_user_id for s in subs if s.status == "verified"})
        out["participants"] = {"done": done, "target": campaign.max_participants}
    goals = eng.campaign_action_goals(campaign)
    if goals:
        rows = []
        for gk, act, target in goals:
            done = 0
            for s in subs:
                a = ((s.payload or {}).get("actions") or {}).get(act) or {}
                if a.get("status") == "verified":
                    done += 1
            rows.append({"goal": gk, "action": act, "done": done, "target": int(target)})
        out["actions"] = rows
    return out


def _running_row(c):
    subs = S.query.filter(S.campaign_id == c.id).with_entities(
        S.status, S.telegram_user_id, S.payload).limit(MAX_ROWS).all()
    wrapped = [type("R", (), {"status": r[0], "telegram_user_id": r[1], "payload": r[2]}) for r in subs]
    return {
        "id": c.id, "title": c.title, "type": c.type, "status": c.status,
        "ends_at": _iso(c.ends_at), "post_status": c.post_status or "none",
        "submitted": len(subs), "pending": sum(1 for r in subs if r[0] == "pending"),
        "approved": sum(1 for r in subs if r[0] == "verified"),
        "progress": _progress(c, wrapped),
    }


# ── Directory ──────────────────────────────────────────────────────────────────

def campaigns_page(cs, *, q="", status="", ctype="", sort="created_at", direction="desc", page=1, per_page=20):
    cnt = (
        db.session.query(
            S.campaign_id.label("cid"),
            func.count(S.id).label("submitted"),
            func.sum(case((S.status == "verified", 1), else_=0)).label("approved"),
            func.sum(case((S.status == "pending", 1), else_=0)).label("pending"),
        ).group_by(S.campaign_id).subquery()
    )
    submitted = func.coalesce(cnt.c.submitted, 0)
    approved = func.coalesce(cnt.c.approved, 0)
    pending = func.coalesce(cnt.c.pending, 0)
    base = db.session.query(C, submitted, approved, pending).outerjoin(cnt, cnt.c.cid == C.id).filter(cs.campaign_filter())
    if q:
        base = base.filter(C.title.ilike(f"%{q}%"))
    if status:
        base = base.filter(C.status == status)
    if ctype:
        base = base.filter(C.type == ctype)
    total = base.count()
    sort = sort if sort in CAMPAIGN_SORTS else "created_at"
    col = {"created_at": C.created_at, "title": func.lower(C.title), "ends_at": C.ends_at, "status": C.status,
           "type": C.type, "submitted": submitted, "approved": approved, "pending": pending}[sort]
    base = base.order_by(col.desc() if direction != "asc" else col.asc(), C.id.desc())
    per_page = min(100, max(1, per_page))
    page = max(1, page)
    rows = base.offset((page - 1) * per_page).limit(per_page).all()
    facets = dict(cs.campaigns().with_entities(C.status, func.count(C.id)).group_by(C.status).all())
    return {
        "campaigns": [{
            "id": c.id, "title": c.title, "type": c.type, "platform": c.platform, "status": c.status,
            "ends_at": _iso(c.ends_at), "starts_at": _iso(c.starts_at), "created_at": _iso(c.created_at),
            "post_status": c.post_status or "none", "post_error": c.post_error,
            "reward_xp": c.reward_xp, "reward_label": c.reward_label,
            "submitted": int(s or 0), "approved": int(a or 0), "pending": int(p or 0),
        } for c, s, a, p in rows],
        "total": total, "page": page, "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "status_counts": {k: int(v) for k, v in facets.items()},
        "timezone": cs.timezone,
    }


# ── Review queue ───────────────────────────────────────────────────────────────

def queue(cs, *, status="pending", campaign_id=None, q="", flagged=None, sort="oldest", page=1, per_page=25):
    base = cs.submissions()
    if status in ("pending", "verified", "rejected"):
        base = base.filter(S.status == status)
    if campaign_id:
        base = base.filter(S.campaign_id == int(campaign_id))
    if flagged:
        base = base.filter(S.flagged.is_(True))
    if q:
        like = f"%{q}%"
        base = base.filter(db.or_(S.telegram_username.ilike(like), S.telegram_user_id.ilike(like), C.title.ilike(like)))
    total = base.count()
    order = S.created_at.desc() if sort == "newest" else S.created_at.asc()
    per_page = min(100, max(1, per_page))
    page = max(1, page)
    rows = base.order_by(order, S.id.asc()).offset((page - 1) * per_page).limit(per_page).all()

    camps = {c.id: c for c in C.query.filter(C.id.in_({r.campaign_id for r in rows})).all()} if rows else {}
    tasks = {t.id: t for t in T.query.filter(T.id.in_({r.task_id for r in rows if r.task_id})).all()} if rows else {}
    names = _reviewer_names(r.reviewed_by for r in rows)
    fields = {}
    for c in camps.values():
        fields[c.id] = {f.key: {"label": f.label, "field_type": f.field_type} for f in c.custom_fields.all()}
        for t in c.tasks.all():
            for f in t.custom_fields.all():
                fields[c.id].setdefault(f.key, {"label": f.label, "field_type": f.field_type})
    items = []
    for s in rows:
        c = camps.get(s.campaign_id)
        d = s.to_dict()
        d.update({
            "campaign_title": c.title if c else None, "campaign_type": c.type if c else None,
            "campaign_status": c.status if c else None,
            "task_title": tasks[s.task_id].title if s.task_id in tasks else None,
            "has_file": bool(s.file_id), "field_labels": fields.get(s.campaign_id, {}),
            "reviewed_by_name": names.get(str(s.reviewed_by)) if s.reviewed_by else None,
            "verification_source": verification_source(c, s) if c else None,
        })
        d.pop("file_id", None)
        d.pop("file_hash", None)
        items.append(d)
    pending_total = cs.submissions().filter(S.status == "pending").count()
    return {
        "items": items, "total": total, "page": page, "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "pending_total": pending_total, "timezone": cs.timezone,
        "campaigns": [{"id": c.id, "title": c.title, "status": c.status} for c in
                      cs.campaigns().order_by(C.created_at.desc()).limit(200).all()],
    }


# ── One campaign ───────────────────────────────────────────────────────────────

def campaign_summary(campaign, days=30):
    days = days if days in (7, 14, 30, 90) else 30
    subs = S.query.filter(S.campaign_id == campaign.id).order_by(S.created_at.asc()).limit(MAX_ROWS).all()
    by_status = Counter(s.status for s in subs)
    unique_people = {s.telegram_user_id for s in subs}
    approved_people = {s.telegram_user_id for s in subs if s.status == "verified"}
    since = datetime.utcnow() - timedelta(days=days)
    s_by = _daily([s.created_at for s in subs if s.created_at and s.created_at >= since], days)
    d_by = _daily([s.reviewed_at for s in subs if s.reviewed_at and s.reviewed_at >= since], days)
    sources = Counter(verification_source(campaign, s) for s in subs if s.status == "verified")
    now = datetime.utcnow()
    oldest = min((s.created_at for s in subs if s.status == "pending"), default=None)
    xp_awarded = sum(1 for s in subs if s.rewarded)
    return {
        "campaign_id": campaign.id, "days": days,
        "counts": {"submitted": len(subs), "pending": by_status.get("pending", 0),
                   "approved": by_status.get("verified", 0), "rejected": by_status.get("rejected", 0),
                   "flagged": sum(1 for s in subs if s.flagged)},
        "people": {"submitted_unique": len(unique_people), "approved_unique": len(approved_people)},
        "verification_sources": {k: v for k, v in sources.items() if k},
        "rewards": {"xp_per_approval": campaign.reward_xp, "submissions_rewarded": xp_awarded,
                    "label": campaign.reward_label,
                    "note": "XP is granted once per approved submission. Reward labels are free text; no payments are recorded."},
        "progress": _progress(campaign, subs),
        "oldest_pending_at": _iso(oldest),
        "oldest_pending_hours": round((now - oldest).total_seconds() / 3600, 1) if oldest else None,
        "series": [{"date": d, "submitted": s_by[d], "decisions": d_by[d]} for d in s_by],
    }


def campaign_activity(campaign, limit=100):
    """Real history only: when each submission arrived and when it was decided."""
    subs = S.query.filter(S.campaign_id == campaign.id).order_by(S.created_at.desc()).limit(500).all()
    names = _reviewer_names(s.reviewed_by for s in subs)
    ev = []
    for s in subs:
        who = f"@{s.telegram_username}" if s.telegram_username else f"User {s.telegram_user_id}"
        ev.append({"at": _iso(s.created_at), "kind": "submitted", "who": who, "submission_id": s.id})
        if s.reviewed_at:
            ev.append({"at": _iso(s.reviewed_at), "kind": "approved" if s.status == "verified" else "rejected",
                       "who": who, "submission_id": s.id,
                       "by": names.get(str(s.reviewed_by)) or (f"account {s.reviewed_by}" if s.reviewed_by else None),
                       "reason": s.review_reason})
    ev.sort(key=lambda e: e["at"] or "", reverse=True)
    posted = []
    if campaign.posted_at:
        posted.append({"at": _iso(campaign.posted_at), "kind": "posted", "who": None})
    return {"events": (ev + posted)[:limit], "created_at": _iso(campaign.created_at)}


# ── Preview ────────────────────────────────────────────────────────────────────

class _Rel:
    """Stands in for a dynamic relationship (.all() / .count()) on an unsaved campaign."""

    def __init__(self, items):
        self._i = list(items)

    def all(self):
        return self._i

    def count(self):
        return len(self._i)


def preview_message(cs, user, data):
    """Render the group announcement for a campaign that is NOT saved.

    Uses engagement_telegram.build_campaign_message - the same function that builds
    the real post - on a duck-typed stand-in, so what the admin sees is what the
    bot would send. Nothing is written and nothing is sent.
    """
    from types import SimpleNamespace as NS
    from .engagement_telegram import build_campaign_message

    data = data or {}
    hours = data.get("duration_hours")
    ends_at = None
    try:
        if data.get("ends_at"):
            ends_at = eng._parse_dt(data.get("ends_at"), "ends_at")
        elif hours:
            ends_at = datetime.utcnow() + timedelta(hours=int(hours))
    except Exception:
        ends_at = None

    def _fields(items):
        return _Rel(NS(label=f.get("label"), field_type=f.get("field_type", "text"),
                       required=bool(f.get("required", True))) for f in (items or []) if (f.get("label") or f.get("field_type")))

    tasks = [NS(title=t.get("title") or "", reward_xp=int(t.get("reward_xp") or 0), custom_fields=_fields(t.get("custom_fields")))
             for t in (data.get("tasks") or []) if (t.get("title") or "").strip()]
    camp = NS(
        id=None, title=(data.get("title") or "").strip() or "New campaign", type=data.get("type") or "proof_collection",
        description=data.get("description") or None, task_url=data.get("task_url") or None,
        platform=data.get("platform"), verification_mode=data.get("verification_mode") or "manual",
        reward_xp=int(data.get("reward_xp") or 0), reward_label=data.get("reward_label") or None,
        status="active", ends_at=ends_at, starts_at=None, settings=data.get("settings") or {},
        owner_user_id=user.id, group_id=None, telegram_group_id=None,
        tasks=_Rel(tasks), custom_fields=_fields(data.get("custom_fields")),
    )
    bot_username = "your_bot"
    if cs.scope == "official":
        from .config import Config
        bot_username = (Config.TELEGRAM_BOT_USERNAME or "telegizer_bot").lstrip("@")
    text, markup = build_campaign_message(camp, bot_username)
    buttons = [[{"text": b.text, "url": b.url} for b in row] for row in markup.inline_keyboard]
    return {"html": text, "buttons": buttons, "note": "Preview only - nothing is posted. Shown as it will appear when the campaign is active."}
