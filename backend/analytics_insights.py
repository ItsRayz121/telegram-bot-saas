"""Read-only analytics insights for the group Analytics section.

Everything here is a pure read: no Telegram calls, no AI calls, no writes. The
numbers are computed on the server over the *full* matching dataset (not a page
of the table) so the summary cards, the grouped views and the underlying records
always reconcile - grouped counts and the per-event list come from the same
normalised event list.

Two bot lineages share one shape (same pattern as ai_activity.py):
  * official -> TelegramGroup / OfficialMember / OfficialWarning / BotEvent
  * custom   -> Group / Member / AuditLog (warnings are AuditLog 'warn' rows)

Honesty rules:
  * "unknown" is None, never 0 (e.g. new/active members for the all-time view).
  * Active warnings (records that currently count) are kept apart from warnings
    *issued* in a period (which also include ones later removed, where the
    lineage keeps them: official only - custom deletes the row on removal).
  * Nothing here changes any enforcement threshold; grouping is display only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

# Safety cap on rows pulled into Python for grouping. The response carries a
# `truncated` flag when it is hit so the UI can say so instead of silently
# under-counting.
MAX_ROWS = 20000

PERIOD_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}

# Event types shown in the official Audit Log. mod_warn (the /warn command) and
# mod_tempmute were missing from the list the endpoint used, so those actions
# never appeared in the log even though the bot writes them.
OFFICIAL_MOD_EVENT_TYPES = (
    "mod_warning", "mod_warn", "mod_ban", "mod_kick", "mod_mute", "mod_tempmute",
    "mod_unmute", "mod_unban", "mod_tempban", "mod_purge", "automod_action",
)

_OFFICIAL_ACTION = {
    "mod_warn": "warn", "mod_warning": "warn",
    "mod_ban": "ban", "mod_unban": "unban", "mod_kick": "kick",
    "mod_mute": "mute", "mod_unmute": "unmute",
    "mod_tempban": "tempban", "mod_tempmute": "tempmute",
    "mod_purge": "purge", "automod_action": "purge",
}

_AUTOMATIC_MODERATORS = {"automod", "raid_guard", "raidguard", "telegizer automod"}


def _utcnow():
    return datetime.utcnow()


def _iso(dt):
    return dt.isoformat() if dt else None


def categorize_reason(reason):
    """Short, stable label for a free-text reason (mirrors the dashboard's
    categorizeReason so grouped rows read the same as individual rows)."""
    if not reason:
        return "No reason recorded"
    r = reason.lower()
    if "t.me/+" in r or "joinchat" in r or ("invite" in r and "link" in r):
        return "Invite link"
    if "telegizer" in r or "tracked link" in r:
        return "Telegizer link"
    if "t.me/" in r or "telegram.me/" in r:
        return "Telegram link"
    if "http" in r or "external link" in r or "url" in r:
        return "External link"
    if "spam" in r or "promotional" in r or "adverti" in r:
        return "Spam"
    if any(k in r for k in ("unrelated", "off-topic", "off topic", "different community", "not related")):
        return "Off-topic"
    if any(k in r for k in ("bad word", "profanity", "inappropriate language")):
        return "Bad words"
    if "caps" in r or "uppercase" in r:
        return "Caps lock"
    if "forward" in r:
        return "Forwarded message"
    if "emoji" in r:
        return "Excessive emojis"
    if "link" in r:
        return "Contains link"
    base = reason.split(" — ", 1)[-1] if " — " in reason else reason
    dot = base.find(". ")
    if 0 < dot < 55:
        return base[:dot]
    return base[:38] + ("…" if len(base) > 38 else "")


# ── Scope adapter ──────────────────────────────────────────────────────────────

class GroupScope:
    """One group in one bot lineage. Every query below is constrained to it."""

    def __init__(self, scope, group):
        self.scope = scope            # 'official' | 'custom'
        self.group = group
        if scope == "official":
            self.key = str(group.telegram_group_id)
        else:
            self.key = group.id

    # members ------------------------------------------------------------------
    @property
    def member_model(self):
        from .models import OfficialMember, Member
        return OfficialMember if self.scope == "official" else Member

    def members_q(self):
        M = self.member_model
        if self.scope == "official":
            return M.query.filter(M.telegram_group_id == self.key)
        return M.query.filter(M.group_id == self.key)

    # warnings -----------------------------------------------------------------
    def warning_rows(self, active_only=True, user_id=None, since=None):
        """Normalised warning records, newest first (capped at MAX_ROWS)."""
        out = []
        if self.scope == "official":
            from .models import OfficialWarning as W
            q = W.query.filter(W.telegram_group_id == self.key)
            if active_only:
                q = q.filter(W.active.is_(True))
            if user_id is not None:
                q = q.filter(W.target_user_id == str(user_id))
            if since is not None:
                q = q.filter(W.created_at >= since)
            for w in q.order_by(W.created_at.desc()).limit(MAX_ROWS).all():
                out.append({
                    "id": w.id, "user_id": w.target_user_id, "username": w.target_username,
                    "moderator": w.moderator_username or w.moderator_user_id,
                    "moderator_id": w.moderator_user_id, "reason": w.reason,
                    "message_text": w.message_text, "active": bool(w.active),
                    "created_at": w.created_at,
                })
        else:
            from .models import AuditLog as A
            q = A.query.filter(A.group_id == self.key, A.action_type == "warn")
            if user_id is not None:
                q = q.filter(A.target_user_id == str(user_id))
            if since is not None:
                q = q.filter(A.timestamp >= since)
            for a in q.order_by(A.timestamp.desc()).limit(MAX_ROWS).all():
                out.append({
                    "id": a.id, "user_id": a.target_user_id, "username": a.target_username,
                    "moderator": a.moderator_username or a.moderator_id,
                    "moderator_id": a.moderator_id, "reason": a.reason,
                    "message_text": (a.extra_data or {}).get("message_text"),
                    "active": True, "created_at": a.timestamp,
                })
        return out

    # audit events -------------------------------------------------------------
    def audit_events(self, since=None, search="", action=None, user_id=None):
        """Normalised moderation events, newest first.

        Returns (events, truncated). `action` filters on the normalised action
        name; the search matches the same fields the existing Audit Log search
        does.
        """
        rows = []
        if self.scope == "official":
            from .models import BotEvent as E, db
            q = E.query.filter(
                E.telegram_group_id == self.key,
                E.event_type.in_(OFFICIAL_MOD_EVENT_TYPES),
            )
            if since is not None:
                q = q.filter(E.created_at >= since)
            if search:
                like = f"%{search}%"
                q = q.filter(db.or_(E.message.ilike(like), db.cast(E.metadata_, db.Text).ilike(like)))
            fetched = q.order_by(E.created_at.desc()).limit(MAX_ROWS + 1).all()
            for e in fetched:
                m = e.metadata_ or {}
                act = _OFFICIAL_ACTION.get(e.event_type, e.event_type)
                is_auto = e.event_type == "automod_action" or \
                    str(m.get("moderator_username") or "").lower() in _AUTOMATIC_MODERATORS
                rule = m.get("rule")
                reason = m.get("reason") or (rule if e.event_type == "automod_action" and rule else None) or e.message
                rows.append({
                    "id": e.id, "action": act,
                    "user_id": str(m.get("target_user_id") or m.get("telegram_user_id") or "") or None,
                    "username": m.get("target_username") or None,
                    "moderator": m.get("moderator_username") or m.get("moderator_id") or None,
                    "automatic": bool(is_auto), "rule": rule, "reason": reason,
                    "enforced": m.get("action") if e.event_type == "automod_action" else None,
                    "message_text": m.get("message_text") or m.get("text") or m.get("message"),
                    "source": m.get("source"), "ts": e.created_at,
                })
        else:
            from .models import AuditLog as A, db
            q = A.query.filter(A.group_id == self.key)
            if since is not None:
                q = q.filter(A.timestamp >= since)
            if search:
                like = f"%{search}%"
                q = q.filter(db.or_(
                    A.target_username.ilike(like), A.target_user_id.ilike(like),
                    A.moderator_username.ilike(like), A.reason.ilike(like), A.action_type.ilike(like),
                ))
            fetched = q.order_by(A.timestamp.desc()).limit(MAX_ROWS + 1).all()
            for a in fetched:
                ex = a.extra_data or {}
                at = a.action_type or ""
                is_auto = at.startswith("auto") or \
                    str(a.moderator_id or "").lower() in _AUTOMATIC_MODERATORS or \
                    str(a.moderator_username or "").lower() in _AUTOMATIC_MODERATORS
                rows.append({
                    "id": a.id, "action": at, "user_id": a.target_user_id or None,
                    "username": a.target_username or None,
                    "moderator": a.moderator_username or a.moderator_id or None,
                    "automatic": bool(is_auto), "rule": None, "reason": a.reason,
                    "enforced": None,
                    "message_text": ex.get("message_text") or ex.get("text"),
                    "source": ex.get("source"), "ts": a.timestamp,
                })
        truncated = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]
        if action:
            rows = [r for r in rows if r["action"] == action]
        if user_id is not None:
            rows = [r for r in rows if r["user_id"] == str(user_id)]
        return rows, truncated

    # xp ledger ----------------------------------------------------------------
    def xp_period_map(self, period):
        """{member_pk: window XP} from the XP ledger for this group's members."""
        from .database import xp_period_subquery
        sq = xp_period_subquery(self.scope, period)
        if sq is None:
            return {}
        M = self.member_model
        from .models import db
        rows = (
            db.session.query(sq.c.mid, sq.c.psum)
            .join(M, M.id == sq.c.mid)
            .filter(M.telegram_group_id == self.key if self.scope == "official" else M.group_id == self.key)
            .all()
        )
        return {mid: int(p or 0) for mid, p in rows}


def _identity(m):
    """Display identity for a member row (or None)."""
    if m is None:
        return {}
    name = getattr(m, "first_name", None)
    last = getattr(m, "last_name", None)
    if last:
        name = " ".join(p for p in (name, last) if p) or None
    return {"name": name, "member_username": m.username}


def _member_lookup(sc, user_ids):
    M = sc.member_model
    if not user_ids:
        return {}
    return {m.telegram_user_id: m for m in sc.members_q().filter(M.telegram_user_id.in_(list(user_ids))).all()}


def _display(uid, username, m):
    ident = _identity(m)
    return {
        "user_id": uid,
        "name": ident.get("name"),
        "username": username or ident.get("member_username"),
    }


def _daily(dts, days):
    """[{date, count}] for the last `days` days (zero-filled), from datetimes."""
    today = _utcnow().date()
    counts = Counter(d.date() for d in dts if d)
    return [
        {"date": (today - timedelta(days=i)).isoformat(),
         "count": counts.get(today - timedelta(days=i), 0)}
        for i in range(days - 1, -1, -1)
    ]


def warned_user_ids_query(sc):
    """Query of the user ids that currently hold at least one active warning record."""
    from .models import db
    if sc.scope == "official":
        from .models import OfficialWarning as W
        return db.session.query(W.target_user_id).filter(
            W.telegram_group_id == sc.key, W.active.is_(True))
    from .models import AuditLog as A
    return db.session.query(A.target_user_id).filter(
        A.group_id == sc.key, A.action_type == "warn", A.target_user_id.isnot(None))


def active_warning_counts(sc, user_ids):
    """{user_id: active warning records} for the given members (one grouped query)."""
    user_ids = [str(u) for u in user_ids if u is not None]
    if not user_ids:
        return {}
    from .models import db
    if sc.scope == "official":
        from .models import OfficialWarning as W
        rows = db.session.query(W.target_user_id, db.func.count(W.id)).filter(
            W.telegram_group_id == sc.key, W.active.is_(True), W.target_user_id.in_(user_ids)
        ).group_by(W.target_user_id).all()
    else:
        from .models import AuditLog as A
        rows = db.session.query(A.target_user_id, db.func.count(A.id)).filter(
            A.group_id == sc.key, A.action_type == "warn", A.target_user_id.in_(user_ids)
        ).group_by(A.target_user_id).all()
    return {u: int(c) for u, c in rows}


# ── Members ────────────────────────────────────────────────────────────────────

def members_summary(sc, period="all"):
    from .models import db, XpEvent
    M = sc.member_model
    days = PERIOD_DAYS.get(period)
    cutoff = _utcnow() - timedelta(days=days) if days else None
    base = sc.members_q()
    total = base.count()

    out = {
        "period": period, "window_days": days, "total_members": total,
        # None = not measurable for the all-time view (shown as "-", not 0).
        "new_members": base.filter(M.joined_at >= cutoff).count() if cutoff else None,
        "active_members": base.filter(M.last_message_at >= cutoff).count() if cutoff else None,
    }

    active = sc.warning_rows(active_only=True)
    per_user = Counter(w["user_id"] for w in active)
    out["members_with_active_warnings"] = len(per_user)
    out["members_with_multiple_warnings"] = sum(1 for c in per_user.values() if c >= 2)
    out["active_warning_records"] = len(active)

    # Repeat-warned members (>=2 active warning records), most first.
    top_rep = [(u, c) for u, c in per_user.most_common() if c >= 2][:5]
    lookup = _member_lookup(sc, {u for u, _ in top_rep})
    last_by_user = {}
    for w in active:
        last_by_user.setdefault(w["user_id"], w["created_at"])
    out["repeat_warned"] = [
        {**_display(u, next((w["username"] for w in active if w["user_id"] == u and w["username"]), None), lookup.get(u)),
         "warnings": c, "last_warned_at": _iso(last_by_user.get(u))}
        for u, c in top_rep
    ]

    # Leading contributors for the selected scope.
    top = []
    if cutoff and period in ("1d", "7d", "30d"):
        pm = sc.xp_period_map(period)
        ranked = sorted(((mid, x) for mid, x in pm.items() if x > 0), key=lambda t: (-t[1], t[0]))[:5]
        rows = {m.id: m for m in base.filter(M.id.in_([r[0] for r in ranked])).all()} if ranked else {}
        for mid, x in ranked:
            m = rows.get(mid)
            if m:
                top.append({**_display(m.telegram_user_id, m.username, m), "xp": x, "level": m.level})
    else:
        for m in base.filter(M.xp > 0).order_by(M.xp.desc(), M.id.asc()).limit(5).all():
            top.append({**_display(m.telegram_user_id, m.username, m), "xp": m.xp, "level": m.level})
    out["top_contributors"] = top
    out["top_contributors_basis"] = f"XP earned in the last {days} day(s)" if days and days <= 30 else "Lifetime XP"

    # Activity chart: members who earned XP per day + joins per day. For the
    # all-time view we chart the last 30 days (labelled as such by the client).
    series_days = days if days and days <= 90 else 30
    since = _utcnow() - timedelta(days=series_days)
    ids_q = base.with_entities(M.id).scalar_subquery()
    xp_rows = (
        db.session.query(db.func.date(XpEvent.created_at), db.func.count(db.distinct(XpEvent.member_id)))
        .filter(XpEvent.scope == sc.scope, XpEvent.member_id.in_(ids_q),
                XpEvent.created_at >= since, XpEvent.amount > 0)
        .group_by(db.func.date(XpEvent.created_at)).all()
    )
    xp_by_day = {str(d)[:10]: int(c) for d, c in xp_rows}
    joined = [r[0] for r in base.filter(M.joined_at >= since).with_entities(M.joined_at).limit(MAX_ROWS).all()]
    joins = {d["date"]: d["count"] for d in _daily(joined, series_days)}
    today = _utcnow().date()
    out["series_days"] = series_days
    out["series"] = [
        {"date": (today - timedelta(days=i)).isoformat(),
         "active_contributors": xp_by_day.get((today - timedelta(days=i)).isoformat(), 0),
         "joins": joins.get((today - timedelta(days=i)).isoformat(), 0)}
        for i in range(series_days - 1, -1, -1)
    ]
    out["series_note"] = "Members who earned XP that day (from the XP ledger); older ledger rows may have been pruned by retention."
    return out


# ── Leaderboard helpers ────────────────────────────────────────────────────────

def week_xp_for(sc, member_ids):
    """{member_pk: XP earned in the last 7 days} for the given members."""
    if not member_ids:
        return {}
    pm = sc.xp_period_map("7d")
    return {mid: pm.get(mid, 0) for mid in member_ids}


# ── Audit log ──────────────────────────────────────────────────────────────────

def _since_for(days):
    return _utcnow() - timedelta(days=days) if days else None


def _event_out(e):
    return {
        "id": e["id"], "action": e["action"], "user_id": e["user_id"], "username": e["username"],
        "moderator": e["moderator"], "automatic": e["automatic"], "rule": e["rule"],
        "reason": e["reason"], "enforced": e["enforced"], "message_text": e["message_text"],
        "source": e["source"], "timestamp": _iso(e["ts"]),
    }


def _group_key(e):
    # Stable member id first (usernames change); fall back to the username only
    # when no id was recorded. Reason side: the rule if the event names one
    # (AutoMod), otherwise the short normalised reason label.
    who = e["user_id"] or (f"@{e['username']}" if e["username"] else "unknown")
    why = e["rule"] or categorize_reason(e["reason"])
    return (who, e["action"], why)


def audit_summary(sc, days=30, search="", action=None):
    since = _since_for(days)
    events, truncated = sc.audit_events(since=since, search=search, action=action)
    per_member = Counter(e["user_id"] for e in events if e["user_id"])
    by_action = Counter(e["action"] for e in events)
    lookup = _member_lookup(sc, {u for u, c in per_member.most_common(5) if c >= 2})
    names = {}
    for e in events:
        if e["user_id"] and e["username"]:
            names.setdefault(e["user_id"], e["username"])
    repeat = [
        {**_display(u, names.get(u), lookup.get(u)), "actions": c}
        for u, c in per_member.most_common() if c >= 2
    ]
    rules = Counter((e["rule"] or categorize_reason(e["reason"])) for e in events)
    span = days if days else 30
    return {
        "days": days, "total_actions": len(events),
        "unique_members": len(per_member),
        "events_without_member": sum(1 for e in events if not e["user_id"]),
        "automatic": sum(1 for e in events if e["automatic"]),
        "manual": sum(1 for e in events if not e["automatic"]),
        "by_action": dict(by_action),
        "members_with_repeats": len(repeat),
        "repeat_members": repeat[:5],
        "top_rules": [{"label": k, "count": v} for k, v in rules.most_common(6)],
        "series": [{"date": d["date"], "count": d["count"]} for d in _daily([e["ts"] for e in events], min(span, 90))],
        "truncated": truncated, "row_cap": MAX_ROWS,
    }


def audit_groups(sc, days=30, search="", action=None, min_count=1, page=1, per_page=25, inline=20):
    since = _since_for(days)
    events, truncated = sc.audit_events(since=since, search=search, action=action)
    buckets = defaultdict(list)
    for e in events:  # events are newest-first, so each bucket stays newest-first
        buckets[_group_key(e)].append(e)
    groups = []
    for (who, act, why), evs in buckets.items():
        if len(evs) < min_count:
            continue
        uname = next((e["username"] for e in evs if e["username"]), None)
        mods = Counter((e["moderator"] or "Unknown") for e in evs)
        groups.append({
            "key": f"{who}|{act}|{why}", "user_id": evs[0]["user_id"], "username": uname,
            "action": act, "reason_label": why,
            "full_reason": next((e["reason"] for e in evs if e["reason"]), None),
            "count": len(evs), "automatic": sum(1 for e in evs if e["automatic"]),
            "manual": sum(1 for e in evs if not e["automatic"]),
            "actors": [{"name": n, "count": c} for n, c in mods.most_common(5)],
            "first_at": _iso(evs[-1]["ts"]), "latest_at": _iso(evs[0]["ts"]),
            "events": [_event_out(e) for e in evs[:inline]],
        })
    groups.sort(key=lambda g: (g["count"], g["latest_at"] or ""), reverse=True)
    total = len(groups)
    start = (max(1, page) - 1) * per_page
    page_groups = groups[start:start + per_page]
    lookup = _member_lookup(sc, {g["user_id"] for g in page_groups if g["user_id"]})
    for g in page_groups:
        g.update({k: v for k, v in _display(g["user_id"], g["username"], lookup.get(g["user_id"])).items() if k != "user_id"})
    return {
        "groups": page_groups, "total_groups": total, "total_events": len(events),
        "page": page, "per_page": per_page, "pages": max(1, (total + per_page - 1) // per_page),
        "truncated": truncated,
    }


def audit_group_events(sc, user_id, action, label, days=30, search="", page=1, per_page=50):
    """Every underlying event of one group, so 'show all' reconciles with count."""
    since = _since_for(days)
    events, truncated = sc.audit_events(since=since, search=search, action=action, user_id=user_id if user_id else None)
    if not user_id:
        events = [e for e in events if not e["user_id"]]
    events = [e for e in events if (e["rule"] or categorize_reason(e["reason"])) == label]
    start = (max(1, page) - 1) * per_page
    return {
        "events": [_event_out(e) for e in events[start:start + per_page]],
        "total": len(events), "page": page, "per_page": per_page,
        "pages": max(1, (len(events) + per_page - 1) // per_page), "truncated": truncated,
    }


# ── Warnings ───────────────────────────────────────────────────────────────────

def _escalation_rules(sc):
    """Read-only copy of the group's existing escalation settings (display only)."""
    s = (sc.group.settings or {}) if sc.group is not None else {}
    mod = s.get("moderation", {}) or {}
    we = s.get("warning_escalation", {}) or {}
    return {
        "max_warnings": mod.get("max_warnings", 3),
        "warning_action": mod.get("warning_action"),
        "ladder_enabled": bool(mod.get("escalation_enabled")),
        "ladder_steps": mod.get("escalation_steps") or [],
        "single_threshold": {
            "enabled": bool(we.get("enabled")),
            "threshold": we.get("warning_threshold"),
            "action": we.get("action_type"),
            "window_hours": we.get("time_window_hours"),
        },
    }


def warnings_summary(sc, days=30):
    since = _since_for(days)
    active = sc.warning_rows(active_only=True)
    per_user = Counter(w["user_id"] for w in active)
    issued = sc.warning_rows(active_only=False, since=since) if since else sc.warning_rows(active_only=False)
    reasons = Counter(categorize_reason(w["reason"]) for w in active)
    by_issuer = Counter("Automation" if str(w["moderator"] or "").lower() in _AUTOMATIC_MODERATORS
                        else "Moderator" for w in active)
    return {
        "days": days,
        "active_records": len(active),
        "members_with_active": len(per_user),
        "members_with_multiple": sum(1 for c in per_user.values() if c >= 2),
        "max_active_per_member": max(per_user.values()) if per_user else 0,
        "issued_in_period": len(issued),
        "issued_members_in_period": len({w["user_id"] for w in issued}),
        # Official keeps removed warnings as inactive rows; custom deletes them,
        # so "removed" is only knowable for the official lineage.
        "removed_in_period": (sum(1 for w in issued if not w["active"]) if sc.scope == "official" else None),
        "by_reason": [{"label": k, "count": v} for k, v in reasons.most_common(8)],
        "by_issuer": dict(by_issuer),
        "series": [{"date": d["date"], "count": d["count"]}
                   for d in _daily([w["created_at"] for w in issued], min(days or 30, 90))],
        "escalation": _escalation_rules(sc),
        "truncated": len(active) >= MAX_ROWS,
    }


def warnings_members(sc, search="", min_count=1, page=1, per_page=25):
    active = sc.warning_rows(active_only=True)
    by_user = defaultdict(list)
    for w in active:  # newest first
        by_user[w["user_id"]].append(w)
    lookup = _member_lookup(sc, set(by_user))
    q = (search or "").strip().lower()
    rows = []
    for uid, ws in by_user.items():
        if len(ws) < min_count:
            continue
        m = lookup.get(uid)
        uname = next((w["username"] for w in ws if w["username"]), None)
        d = _display(uid, uname, m)
        if q and q not in " ".join(str(x or "").lower() for x in (
                uid, d["name"], d["username"], *[w["reason"] for w in ws], *[w["moderator"] for w in ws])):
            continue
        rc = Counter(categorize_reason(w["reason"]) for w in ws)
        issuers = Counter((w["moderator"] or "Unknown") for w in ws)
        rows.append({
            **d, "active_warnings": len(ws),
            "reasons": [{"label": k, "count": v} for k, v in rc.most_common(5)],
            "issuers": [{"name": k, "count": v} for k, v in issuers.most_common(4)],
            "first_at": _iso(ws[-1]["created_at"]), "latest_at": _iso(ws[0]["created_at"]),
            "warning_ids": [w["id"] for w in ws[:50]],
        })
    rows.sort(key=lambda r: (r["active_warnings"], r["latest_at"] or ""), reverse=True)
    start = (max(1, page) - 1) * per_page
    return {
        "members": rows[start:start + per_page], "total": len(rows),
        "page": page, "per_page": per_page, "pages": max(1, (len(rows) + per_page - 1) // per_page),
    }


# ── Single-member context (powers the shared member profile) ──────────────────

def member_context(sc, user_id):
    uid = str(user_id)
    M = sc.member_model
    m = sc.members_q().filter(M.telegram_user_id == uid).first()
    warnings = sc.warning_rows(active_only=False, user_id=uid)
    events, truncated = sc.audit_events(user_id=uid)
    xp = None
    if m is not None:
        pm1, pm7, pm30 = (sc.xp_period_map(p) for p in ("1d", "7d", "30d"))
        xp = {"lifetime": m.xp, "level": m.level,
              "xp_1d": pm1.get(m.id, 0), "xp_7d": pm7.get(m.id, 0), "xp_30d": pm30.get(m.id, 0)}
    return {
        "user_id": uid, "in_group": m is not None,
        "member": m.to_dict() if m is not None else None,
        "xp": xp,
        "warnings": [{
            "id": w["id"], "reason": w["reason"], "moderator": w["moderator"], "active": w["active"],
            "message_text": w["message_text"], "created_at": _iso(w["created_at"]),
        } for w in warnings[:100]],
        "active_warnings": sum(1 for w in warnings if w["active"]),
        "moderation_events": [_event_out(e) for e in events[:100]],
        "moderation_event_total": len(events),
        "truncated": truncated,
    }


# ── AI Activity ────────────────────────────────────────────────────────────────

def ai_overview(scope, group_ref, days=30):
    """Outcome counts + a daily trend for the AI Activity overview.

    Only the statuses the table actually records are reported (ok / failed /
    skipped). There is no pending state and no confidence score in the data, so
    none is shown.
    """
    from .models import AIActivity as A
    since = _utcnow() - timedelta(days=days)
    base = A.query.filter(A.scope == str(scope), A.group_ref == str(group_ref), A.created_at >= since)
    rows = base.with_entities(A.created_at, A.category, A.status).limit(MAX_ROWS).all()
    by_status = Counter(r[2] for r in rows)
    by_cat = Counter(r[1] for r in rows)
    cat_status = defaultdict(Counter)
    for _, c, s in rows:
        cat_status[c][s] += 1
    fb_rows = [r for r in A.query.filter(A.scope == str(scope), A.group_ref == str(group_ref),
                                         A.created_at >= since).with_entities(A.meta).limit(MAX_ROWS).all()]
    rated = Counter(((r[0] or {}).get("feedback") or {}).get("rating") for r in fb_rows)
    return {
        "days": days, "total": len(rows),
        "by_status": {"ok": by_status.get("ok", 0), "failed": by_status.get("failed", 0),
                      "skipped": by_status.get("skipped", 0)},
        "by_category": dict(by_cat),
        "category_status": {c: dict(s) for c, s in cat_status.items()},
        "feedback": {"good": rated.get("good", 0), "bad": rated.get("bad", 0)},
        "series": [{"date": d["date"], "count": d["count"]} for d in _daily([r[0] for r in rows], min(days, 90))],
        "truncated": len(rows) >= MAX_ROWS,
    }
