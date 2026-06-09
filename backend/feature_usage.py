"""Feature-usage logging layer (admin Feature Usage + Proof Metrics).

Single entry point for recording discrete feature actions across BOTH bot
lineages and the Echo assistant. Mirrors `backend.ai_activity` by design:

  • `log_feature_usage(...)` NEVER raises and NEVER blocks a live handler. Any
    failure is swallowed so usage logging can never break message processing or
    trip the anti-ban governor. Safe to call from inside python-telegram-bot
    async handlers.

  • Group addressing matches AIActivity / BotHealthEvent: scope ∈
    {official, custom, echo} with a string `group_ref` (telegram_group_id for
    official, str(Group.id) for custom).

The companion model is `FeatureUsageEvent` (models.py). Reporting/aggregation
helpers (for the Feature Usage tab) land in a later phase; this module is the
write path that starts collecting real data now.
"""
from __future__ import annotations

import logging
from datetime import datetime

_log = logging.getLogger("feature_usage")

# Canonical feature keys. Kept permissive (unknown keys are still stored, just
# normalised) so a new feature emitting usage never silently drops rows — but
# the catalog documents the expected set for the admin UI grouping.
FEATURE_KEYS = {
    # Moderation / protection
    "automod", "spam", "link", "ai_mod", "warn", "mute", "ban", "kick",
    "content_filter", "raid", "captcha", "nsfw", "flood",
    # Engagement / ops
    "welcome", "scheduler", "announce", "referral", "command",
    "forwarding", "workflow", "poll", "knowledge",
    # Echo assistant
    "assistant", "summary", "digest", "reminder", "task",
}

_VALID_STATUS = {"ok", "failed", "skipped"}
_VALID_SCOPE = {"official", "custom", "echo"}


def log_feature_usage(
    scope: str,
    feature: str,
    *,
    group_ref=None,
    bot_ref=None,
    user_ref=None,
    action: str | None = None,
    count: int = 1,
    status: str = "ok",
    meta: dict | None = None,
    db=None,
    commit: bool = True,
) -> None:
    """Record one feature action. Best-effort: every failure is swallowed.

    Args:
        scope: 'official' | 'custom' | 'echo'.
        feature: stable feature key (see FEATURE_KEYS).
        group_ref: telegram_group_id (official) or str(Group.id) (custom).
        bot_ref: 'official' or str(CustomBot.id).
        user_ref: telegram user id of the actor/target (for "most active users").
        action: specific action or command name.
        count: increment (defaults to 1).
        status: 'ok' | 'failed' | 'skipped'.
        meta: optional JSON context (never put secrets/PII raw here).
        db: pass an already-imported db; otherwise imported lazily.
        commit: set False when the caller owns the transaction.
    """
    try:
        if not feature:
            return
        scope = str(scope or "custom").lower()
        if scope not in _VALID_SCOPE:
            scope = "custom"
        if status not in _VALID_STATUS:
            status = "ok"
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 1
        if count <= 0:
            count = 1

        if db is None:
            from .models import db as _db
            db = _db
        from .models import FeatureUsageEvent

        row = FeatureUsageEvent(
            scope=scope,
            bot_ref=(str(bot_ref)[:64] if bot_ref is not None else None),
            group_ref=(str(group_ref)[:64] if group_ref is not None else None),
            user_ref=(str(user_ref)[:64] if user_ref is not None else None),
            feature=str(feature)[:40],
            action=(str(action)[:120] if action else None),
            count=count,
            status=status,
            meta=meta or None,
            created_at=datetime.utcnow(),
        )
        db.session.add(row)
        if commit:
            db.session.commit()
    except Exception as exc:  # never break a live handler over logging
        try:
            from .models import db as _db
            _db.session.rollback()
        except Exception:
            pass
        _log.debug("log_feature_usage failed (%s/%s): %s", scope, feature, exc)


def automod_feature(rule_or_reason) -> str:
    """Map an automod rule key / human reason to a protection feature key.

    Lets "Spam protection" and "Link protection" get their own usage counts
    instead of everything collapsing into a generic "automod". Unknown rules
    fall back to "automod".
    """
    s = str(rule_or_reason or "").lower()
    if any(k in s for k in ("link", "url", "domain", "invite")):
        return "link"
    if any(k in s for k in ("spam", "flood")):
        return "spam"
    if any(k in s for k in ("nsfw", "porn", "explicit")):
        return "nsfw"
    if any(k in s for k in ("caps", "emoji", "forward", "email", "blacklist", "word")):
        return "automod"
    return "automod"


def derive_scope_ref(group=None, telegram_group_id=None, group_id=None):
    """Resolve (scope, group_ref) from whatever a call site has on hand.

    An explicit telegram_group_id (official) wins; otherwise a legacy Group
    object/id maps to custom scope. Returns (None, None) if unresolvable.
    """
    tgid = telegram_group_id
    gid = group_id
    if group is not None:
        tgid = tgid or getattr(group, "telegram_group_id", None)
        if gid is None and not tgid:
            gid = getattr(group, "id", None)
    if tgid:
        return "official", str(tgid)
    if gid is not None:
        return "custom", str(gid)
    return None, None


# ── Reporting layer (admin Feature Usage tab) ──────────────────────────────────

# Human labels + grouping for the UI. Order matters (drives display order).
FEATURE_LABELS = {
    "automod": "AutoMod",
    "spam": "Spam Protection",
    "link": "Link Protection",
    "nsfw": "NSFW Filter",
    "content_filter": "Content Filter",
    "ai_mod": "AI Moderation",
    "warn": "Warnings",
    "mute": "Muting",
    "ban": "Bans",
    "kick": "Kicks",
    "raid": "Raid Guard",
    "captcha": "Captcha",
    "flood": "Flood Control",
    "welcome": "Welcome",
    "scheduler": "Scheduler",
    "announce": "Announcements",
    "referral": "Referrals",
    "command": "Commands",
    "forwarding": "Forwarding",
    "workflow": "Workflows",
    "poll": "Polls",
    "knowledge": "Knowledge Base",
}


def _trend_label(recent: int, prior: int) -> str:
    """Classify a feature as heavy / growing / steady / declining / dormant."""
    if recent == 0 and prior == 0:
        return "dormant"
    if prior == 0 and recent > 0:
        return "growing"
    if recent >= 1000:
        return "heavy"
    if recent > prior * 1.25:
        return "growing"
    if recent < prior * 0.75:
        return "declining"
    return "steady"


def usage_overview(scopes) -> dict:
    """Per-feature usage metrics over a set of scopes (e.g. official+custom).

    One grouped query for the headline metrics, plus small top-N queries for the
    most-active users/groups. All counts are real sums from FeatureUsageEvent —
    if nothing has been logged yet a feature simply reports zeros (honest).
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func, case, distinct
    from .models import db, FeatureUsageEvent, TelegramGroup

    if isinstance(scopes, str):
        scopes = [scopes]
    now = datetime.utcnow()
    d1, d7, d30, d14 = (now - timedelta(days=n) for n in (1, 7, 30, 14))

    base = FeatureUsageEvent.query.filter(FeatureUsageEvent.scope.in_(scopes))

    def _sum_since(ts):
        return func.coalesce(func.sum(case((FeatureUsageEvent.created_at >= ts, FeatureUsageEvent.count), else_=0)), 0)

    rows = (
        db.session.query(
            FeatureUsageEvent.feature.label("feature"),
            func.coalesce(func.sum(FeatureUsageEvent.count), 0).label("all_time"),
            _sum_since(d1).label("today"),
            _sum_since(d7).label("d7"),
            _sum_since(d30).label("d30"),
            func.count(distinct(FeatureUsageEvent.user_ref)).label("users"),
            func.count(distinct(FeatureUsageEvent.group_ref)).label("groups"),
            func.coalesce(func.sum(case((FeatureUsageEvent.status == "failed", FeatureUsageEvent.count), else_=0)), 0).label("errors"),
            func.max(FeatureUsageEvent.created_at).label("last_used"),
        )
        .filter(FeatureUsageEvent.scope.in_(scopes))
        .group_by(FeatureUsageEvent.feature)
        .all()
    )

    # Prior-7d window (days 7–14 ago) for trend, computed separately to keep the
    # main query readable.
    prior_rows = dict(
        db.session.query(
            FeatureUsageEvent.feature,
            func.coalesce(func.sum(FeatureUsageEvent.count), 0),
        )
        .filter(
            FeatureUsageEvent.scope.in_(scopes),
            FeatureUsageEvent.created_at >= d14,
            FeatureUsageEvent.created_at < d7,
        )
        .group_by(FeatureUsageEvent.feature)
        .all()
    )

    features = []
    for r in rows:
        recent7 = int(r.d7)
        prior7 = int(prior_rows.get(r.feature, 0))
        features.append({
            "feature": r.feature,
            "label": FEATURE_LABELS.get(r.feature, r.feature.replace("_", " ").title()),
            "users": int(r.users or 0),
            "groups": int(r.groups or 0),
            "today": int(r.today or 0),
            "d7": recent7,
            "d30": int(r.d30 or 0),
            "all_time": int(r.all_time or 0),
            "errors": int(r.errors or 0),
            "last_used": r.last_used.isoformat() if r.last_used else None,
            "trend": _trend_label(recent7, prior7),
        })
    features.sort(key=lambda f: f["all_time"], reverse=True)

    # Most-active groups (top 5 by all-time usage), enriched with title.
    top_groups_raw = (
        db.session.query(
            FeatureUsageEvent.group_ref,
            func.coalesce(func.sum(FeatureUsageEvent.count), 0).label("c"),
        )
        .filter(FeatureUsageEvent.scope.in_(scopes), FeatureUsageEvent.group_ref.isnot(None))
        .group_by(FeatureUsageEvent.group_ref)
        .order_by(func.coalesce(func.sum(FeatureUsageEvent.count), 0).desc())
        .limit(5).all()
    )
    top_groups = []
    for gref, c in top_groups_raw:
        tg = TelegramGroup.query.filter_by(telegram_group_id=gref).first()
        top_groups.append({"group_ref": gref, "title": tg.title if tg else gref, "count": int(c)})

    # Most-active users (top 5 by all-time usage).
    top_users_raw = (
        db.session.query(
            FeatureUsageEvent.user_ref,
            func.coalesce(func.sum(FeatureUsageEvent.count), 0).label("c"),
        )
        .filter(FeatureUsageEvent.scope.in_(scopes), FeatureUsageEvent.user_ref.isnot(None))
        .group_by(FeatureUsageEvent.user_ref)
        .order_by(func.coalesce(func.sum(FeatureUsageEvent.count), 0).desc())
        .limit(5).all()
    )
    top_users = [{"user_ref": u, "count": int(c)} for u, c in top_users_raw]

    return {
        "features": features,
        "top_groups": top_groups,
        "top_users": top_users,
        "totals": {
            "events_all_time": sum(f["all_time"] for f in features),
            "events_today": sum(f["today"] for f in features),
            "active_groups": base.filter(FeatureUsageEvent.created_at >= d30).with_entities(
                func.count(distinct(FeatureUsageEvent.group_ref))).scalar() or 0,
            "distinct_features": len(features),
        },
        "tracking_note": "Usage is tracked from the day this feature shipped — historical actions are not backfilled.",
    }


def echo_overview() -> dict:
    """Echo assistant usage from AIActivity (+ any echo-scoped usage events).

    AIActivity has no per-user FK and no cost column, so per-user attribution and
    per-feature cost are reported as not-tracked rather than fabricated.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func, case, distinct
    from .models import db, AIActivity, FeatureUsageEvent

    now = datetime.utcnow()
    d1, d7, d30 = (now - timedelta(days=n) for n in (1, 7, 30))

    def _ai_sum_since(ts):
        return func.coalesce(func.sum(case((AIActivity.created_at >= ts, 1), else_=0)), 0)

    cat_rows = (
        db.session.query(
            AIActivity.category,
            func.count(AIActivity.id).label("all_time"),
            _ai_sum_since(d1).label("today"),
            _ai_sum_since(d7).label("d7"),
            _ai_sum_since(d30).label("d30"),
            func.coalesce(func.sum(case((AIActivity.status == "failed", 1), else_=0)), 0).label("errors"),
            func.max(AIActivity.created_at).label("last_used"),
        )
        .group_by(AIActivity.category)
        .all()
    )
    categories = [{
        "category": r.category,
        "all_time": int(r.all_time or 0),
        "today": int(r.today or 0),
        "d7": int(r.d7 or 0),
        "d30": int(r.d30 or 0),
        "errors": int(r.errors or 0),
        "last_used": r.last_used.isoformat() if r.last_used else None,
    } for r in cat_rows]
    categories.sort(key=lambda c: c["all_time"], reverse=True)

    active_groups = db.session.query(
        func.count(distinct(AIActivity.group_ref))
    ).filter(AIActivity.created_at >= d30).scalar() or 0

    # Echo-scoped usage events (assistant/summary/digest/reminder/task), if any.
    echo_features = usage_overview(["echo"])["features"]

    return {
        "categories": categories,
        "echo_features": echo_features,
        "totals": {
            "ai_requests_all_time": sum(c["all_time"] for c in categories),
            "ai_requests_today": sum(c["today"] for c in categories),
            "active_groups_30d": active_groups,
        },
        "cost_tracking": "not_tracked",
        "cost_note": "Per-feature AI cost is not yet attributed. Platform-wide AI spend is on the AI tab.",
        "tracking_note": "Echo usage reflects logged AI actions; per-user attribution is not yet tracked.",
    }
