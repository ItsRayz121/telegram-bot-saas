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

# ── Feature catalog ─────────────────────────────────────────────────────────
# (key, label, lineage, section, plan) — the authoritative map of every platform
# module the admin Feature Usage tab should surface. `lineage` is 'group' (both
# bot lineages) or 'echo'. `plan` is the tier the feature is available on (badge).
# Kept permissive: unknown emitted keys are still stored, just not grouped.
FEATURE_CATALOG = [
    # ── Group Management — Moderation ──
    ("automod", "AutoMod", "group", "Moderation", "free"),
    ("spam", "Spam Protection", "group", "Moderation", "free"),
    ("link", "Link Protection", "group", "Moderation", "free"),
    ("nsfw", "NSFW Filter", "group", "Moderation", "pro"),
    ("content_filter", "Content Filter", "group", "Moderation", "pro"),
    ("ai_mod", "AI Moderation", "group", "Moderation", "pro"),
    ("behavior", "Behavior Rules", "group", "Moderation", "pro"),
    ("reports", "Reports", "group", "Moderation", "free"),
    ("warn", "Warnings", "group", "Moderation", "free"),
    ("mute", "Muting", "group", "Moderation", "free"),
    ("ban", "Bans", "group", "Moderation", "free"),
    ("kick", "Kicks", "group", "Moderation", "free"),
    ("raid", "Raid Guard", "group", "Moderation", "pro"),
    ("captcha", "Captcha", "group", "Moderation", "free"),
    ("flood", "Flood Control", "group", "Moderation", "free"),
    # ── Group Management — Members ──
    ("verification", "Verification", "group", "Members", "free"),
    ("welcome", "Welcome", "group", "Members", "free"),
    ("xp_roles", "XP & Roles", "group", "Members", "pro"),
    ("invite", "Invite Links", "group", "Members", "free"),
    ("members", "Members Analytics", "group", "Members", "free"),
    ("leaderboard", "Leaderboard", "group", "Members", "pro"),
    # ── Group Management — Engagement ──
    ("campaign", "Campaigns", "group", "Engagement", "pro"),
    ("referral", "Referrals", "group", "Engagement", "free"),
    # ── Group Management — AI & Integrations ──
    ("knowledge", "Knowledge Base", "group", "AI & Integrations", "pro"),
    ("escalation", "Escalation", "group", "AI & Integrations", "pro"),
    # ── Group Management — Automation ──
    ("scheduler", "Scheduler", "group", "Automation", "pro"),
    ("auto_reply", "Auto Reply", "group", "Automation", "pro"),
    ("poll", "Polls", "group", "Automation", "free"),
    ("forwarding", "Forwarding", "group", "Automation", "pro"),
    ("workflow", "Workflows", "group", "Automation", "pro"),
    ("webhook", "Webhooks", "group", "Automation", "pro"),
    # ── Group Management — Analytics / ops ──
    ("command", "Commands", "group", "Analytics", "free"),
    ("announce", "Announcements", "group", "Analytics", "free"),
    ("audit", "Audit Log", "group", "Analytics", "free"),
    ("digest", "Digest", "group", "Analytics", "pro"),
    ("ai_activity", "AI Activity", "group", "Analytics", "pro"),
    # ── Echo assistant ──
    ("assistant", "Assistant Chat", "echo", "Echo", "free"),
    ("notes", "Notes", "echo", "Echo", "free"),
    ("reminder", "Reminders", "echo", "Echo", "free"),
    ("task", "Tasks", "echo", "Echo", "free"),
    ("template", "Templates", "echo", "Echo", "pro"),
    ("automation", "Automation", "echo", "Echo", "pro"),
    ("meeting", "Meetings", "echo", "Echo", "pro"),
    ("summary", "Summaries", "echo", "Echo", "pro"),
]

# Derived structures.
FEATURE_META = {c[0]: {"label": c[1], "lineage": c[2], "section": c[3], "plan": c[4]} for c in FEATURE_CATALOG}
FEATURE_KEYS = set(FEATURE_META.keys())
# Section display order per lineage (drives UI grouping order).
GROUP_SECTION_ORDER = ["Moderation", "Members", "Engagement", "AI & Integrations", "Automation", "Analytics"]

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


# Map a settings-section key (what the dashboard PUTs) to a feature key, so that
# saving/configuring a module records a real "configured" usage event. This is the
# single highest-leverage instrumentation point: every module's settings flow
# through the two settings-save endpoints, so wiring it here lights up active vs
# dormant honestly for the whole catalog. Unknown sections are simply ignored.
SETTINGS_SECTION_FEATURE = {
    "verification": "verification",
    "welcome": "welcome",
    "levels": "xp_roles",
    "xp": "xp_roles",
    "automod": "automod",
    "moderation": "automod",
    "auto_clean": "automod",
    "reports": "reports",
    "bot_policy": "spam",
    "raid_guard": "raid",
    "content_filter": "content_filter",
    "knowledge_base": "knowledge",
    "auto_responses": "auto_reply",
    "social_replies": "auto_reply",
    "image_ai": "ai_mod",
    "escalation": "escalation",
    "admin_alerts": "escalation",
    "digest": "digest",
    "raids": "raid",
    "invites": "invite",
    "reactions": "automod",
    "forwarding": "forwarding",
    "workflows": "workflow",
    "webhooks": "webhook",
    "scheduler": "scheduler",
    "polls": "poll",
}


def log_settings_saved(scope, sections, *, group_ref=None, bot_ref=None, user_ref=None, db=None):
    """Record a 'configured' feature event for each known settings section saved.

    Best-effort and de-duplicated per call. Never raises (delegates to
    log_feature_usage). Pass the iterable of section keys from the PUT payload.
    """
    try:
        seen = set()
        for section in sections or []:
            feat = SETTINGS_SECTION_FEATURE.get(str(section))
            if not feat or feat in seen:
                continue
            seen.add(feat)
            log_feature_usage(
                scope, feat, group_ref=group_ref, bot_ref=bot_ref, user_ref=user_ref,
                action="configured", db=db, commit=False,
            )
        if seen and db is not None:
            db.session.commit()
    except Exception:
        pass


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

# Human labels for the UI — derived from the catalog (single source of truth).
FEATURE_LABELS = {k: m["label"] for k, m in FEATURE_META.items()}


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

    # Which lineage are we reporting? Drives which catalog features to surface
    # (with honest zeros) even when nothing has been logged for them yet.
    lineage = "echo" if (list(scopes) == ["echo"]) else "group"

    def _meta(key):
        return FEATURE_META.get(key, {"label": key.replace("_", " ").title(), "section": "Other", "plan": "free", "lineage": lineage})

    features = []
    seen = set()
    for r in rows:
        seen.add(r.feature)
        recent7 = int(r.d7)
        prior7 = int(prior_rows.get(r.feature, 0))
        m = _meta(r.feature)
        features.append({
            "feature": r.feature,
            "label": m["label"],
            "section": m["section"],
            "plan": m["plan"],
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

    # Surface every catalog feature for this lineage — zero rows are honest
    # ("tracked, not yet used") so the admin sees the full module set, not just
    # whatever has happened to fire.
    for key, m in FEATURE_META.items():
        if m["lineage"] != lineage or key in seen:
            continue
        features.append({
            "feature": key, "label": m["label"], "section": m["section"], "plan": m["plan"],
            "users": 0, "groups": 0, "today": 0, "d7": 0, "d30": 0,
            "all_time": 0, "errors": 0, "last_used": None, "trend": "dormant",
        })

    # Sort by section order, then by all-time usage within a section.
    _order = {s: i for i, s in enumerate(GROUP_SECTION_ORDER)}
    features.sort(key=lambda f: (_order.get(f["section"], 99), -f["all_time"], f["label"]))

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
            "distinct_features": sum(1 for f in features if f["all_time"] > 0),
            "catalog_features": len(features),
        },
        "tracking_note": "Usage is tracked from the day this feature shipped — historical actions are not backfilled.",
    }


# Proof metrics that are safe to expose publicly by default (no internal/ops
# numbers like error counts or active-user counts).
DEFAULT_PUBLIC_PROOF_KEYS = [
    "groups_managed", "members_protected", "spam_deleted", "links_blocked",
    "warnings_issued", "moderation_actions", "ai_checks", "commands_handled",
]

PROOF_METRIC_LABELS = {
    "groups_managed": "Total groups managed",
    "members_protected": "Total members protected",
    "spam_deleted": "Spam messages deleted",
    "links_blocked": "Suspicious links blocked",
    "warnings_issued": "Warnings issued",
    "muted": "Members muted",
    "banned": "Members banned",
    "kicked": "Members kicked",
    "moderation_actions": "Total moderation actions",
    "commands_handled": "Bot commands handled",
    "ai_checks": "AI moderation checks",
    "active_groups_today": "Active groups today",
    "active_members_today": "Active members today",
    "custom_bots_created": "Custom bots created",
    "errors_24h": "Errors (last 24h)",
}

# Human-readable data source for each metric, shown as a tooltip in the admin
# Proof Metrics tab so it's auditable that every number is real DB-derived.
PROOF_METRIC_SOURCES = {
    "groups_managed": "telegram_groups (bot_status='active', not disabled)",
    "members_protected": "SUM(telegram_groups.member_count) for active groups — synced live from Telegram",
    "spam_deleted": "feature_usage_events (feature in spam, automod)",
    "links_blocked": "feature_usage_events (feature='link')",
    "warnings_issued": "feature_usage_events (feature='warn')",
    "muted": "feature_usage_events (feature='mute')",
    "banned": "feature_usage_events (feature='ban')",
    "kicked": "feature_usage_events (feature='kick')",
    "moderation_actions": "feature_usage_events (all moderation features summed)",
    "commands_handled": "feature_usage_events (feature='command')",
    "ai_checks": "ai_activity (category='moderation')",
    "active_groups_today": "telegram_groups (last_activity >= today 00:00 UTC)",
    "active_members_today": "feature_usage_events (distinct user_ref since today 00:00 UTC)",
    "custom_bots_created": "custom_bots + bots tables (row count)",
    "errors_24h": "bot_health_events (severity != 'info', last 24h)",
}


def compute_proof_metrics(public_keys=None) -> dict:
    """Platform-wide proof metrics from real DB/event sources (never fabricated).

    `public_keys` (list) marks which metrics are flagged safe for the landing
    page. Returns an ordered list of {key,label,value,public}.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func, distinct
    from .models import (
        db, TelegramGroup, FeatureUsageEvent, AIActivity, BotHealthEvent, CustomBot, Bot,
    )

    if public_keys is None:
        public_keys = DEFAULT_PUBLIC_PROOF_KEYS
    public_set = set(public_keys)

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Groups + members (active, non-disabled).
    active_groups = TelegramGroup.query.filter(
        TelegramGroup.bot_status == "active", TelegramGroup.is_disabled == False  # noqa: E712
    )
    groups_managed = active_groups.count()
    members_protected = db.session.query(
        func.coalesce(func.sum(TelegramGroup.member_count), 0)
    ).filter(TelegramGroup.bot_status == "active", TelegramGroup.is_disabled == False).scalar() or 0  # noqa: E712

    # Member-count freshness: member_count drifts low until member_sync reconciles
    # it to the live getChatMemberCount. Surface how fresh the sum actually is so a
    # stale "members protected" (e.g. before migrate.py / the 6h job has run) is
    # visible instead of silently wrong.
    # Wrapped defensively: on a DB where the column hasn't been added yet (pre
    # migration) this query would raise — that must never 500 the proof endpoint.
    synced_at_col = getattr(TelegramGroup, "member_count_synced_at", None)
    members_synced_at = None
    members_never_synced = None
    if synced_at_col is not None:
        try:
            members_synced_at = db.session.query(func.max(synced_at_col)).filter(
                TelegramGroup.bot_status == "active", TelegramGroup.is_disabled == False  # noqa: E712
            ).scalar()
            members_never_synced = active_groups.filter(synced_at_col.is_(None)).count()
        except Exception:
            db.session.rollback()
            members_synced_at = None
            members_never_synced = None

    # Feature-usage sums by feature (one grouped query).
    usage_rows = db.session.query(
        FeatureUsageEvent.feature, func.coalesce(func.sum(FeatureUsageEvent.count), 0)
    ).group_by(FeatureUsageEvent.feature).all()
    usage = {feat: int(c) for feat, c in usage_rows}

    spam_deleted = usage.get("spam", 0) + usage.get("automod", 0)
    links_blocked = usage.get("link", 0)
    warnings_issued = usage.get("warn", 0)
    muted, banned, kicked = usage.get("mute", 0), usage.get("ban", 0), usage.get("kick", 0)
    commands_handled = usage.get("command", 0)
    moderation_actions = sum(usage.get(k, 0) for k in ("spam", "link", "automod", "warn", "mute", "ban", "kick", "nsfw"))

    ai_checks = db.session.query(func.count(AIActivity.id)).filter(
        AIActivity.category == "moderation"
    ).scalar() or 0

    active_groups_today = TelegramGroup.query.filter(
        TelegramGroup.last_activity >= today_start
    ).count()
    active_members_today = db.session.query(
        func.count(distinct(FeatureUsageEvent.user_ref))
    ).filter(FeatureUsageEvent.created_at >= today_start, FeatureUsageEvent.user_ref.isnot(None)).scalar() or 0

    custom_bots_created = (CustomBot.query.count() or 0) + (Bot.query.count() or 0)

    errors_24h = BotHealthEvent.query.filter(
        BotHealthEvent.created_at >= now - timedelta(days=1),
        db.or_(BotHealthEvent.severity != "info", BotHealthEvent.severity.is_(None)),
    ).count()

    raw = {
        "groups_managed": groups_managed,
        "members_protected": int(members_protected),
        "spam_deleted": spam_deleted,
        "links_blocked": links_blocked,
        "warnings_issued": warnings_issued,
        "muted": muted, "banned": banned, "kicked": kicked,
        "moderation_actions": moderation_actions,
        "commands_handled": commands_handled,
        "ai_checks": int(ai_checks),
        "active_groups_today": active_groups_today,
        "active_members_today": int(active_members_today),
        "custom_bots_created": custom_bots_created,
        "errors_24h": errors_24h,
    }

    metrics = [
        {
            "key": k,
            "label": PROOF_METRIC_LABELS.get(k, k),
            "value": v,
            "public": k in public_set,
            "source": PROOF_METRIC_SOURCES.get(k, "Derived from platform DB"),
        }
        for k, v in raw.items()
    ]
    return {
        "metrics": metrics,
        "generated_at": now.isoformat(),
        "members_sync": {
            "last_synced_at": members_synced_at.isoformat() if members_synced_at else None,
            "never_synced_groups": members_never_synced,
            "note": (
                "member_count is reconciled to live Telegram counts by a 6h job and "
                "on demand. Until it runs, busy groups read low (only members the bot "
                "witnessed). Use 'Refresh member counts' to reconcile now."
            ),
        },
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
