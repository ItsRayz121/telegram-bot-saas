"""AI Activity logging + reporting layer (Analytics → AI Activity tab).

This module is the single entry point for recording AI-generated actions and
for reading them back as metrics + a timeline. It is deliberately a thin,
best-effort layer:

  • `log_ai_activity(...)` NEVER raises and NEVER triggers a new AI call. It
    swallows every error so a logging failure can never break a live bot
    handler. It is safe to call from inside python-telegram-bot async handlers.

  • `activity_summary(...)` returns the dashboard metrics (today / week / month
    / total) plus a paginated timeline for the frontend.

Group addressing mirrors BotHealthEvent: scope ∈ {official, custom} and a
string `group_ref` (telegram_group_id for official, str(Group.id) for custom).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

_log = logging.getLogger("ai_activity")

_VALID_CATEGORIES = {"moderation", "knowledge", "engagement", "automation", "analytics"}
_VALID_STATUS = {"ok", "failed", "skipped"}


def log_ai_activity(
    scope: str,
    group_ref,
    category: str,
    action: str,
    *,
    detail: str | None = None,
    target: str | None = None,
    status: str = "ok",
    source: str | None = None,
    meta: dict | None = None,
    db=None,
    commit: bool = True,
) -> None:
    """Record one AI action. Best-effort: any failure is logged and swallowed.

    Pass `db` when you already have one imported (handlers do); otherwise it is
    imported lazily. Set `commit=False` when the caller owns the transaction.
    """
    try:
        if not group_ref or category not in _VALID_CATEGORIES:
            return
        if status not in _VALID_STATUS:
            status = "ok"
        if db is None:
            from .models import db as _db
            db = _db
        from .models import AIActivity

        row = AIActivity(
            scope=str(scope or "custom"),
            group_ref=str(group_ref),
            category=category,
            action=(action or "AI action")[:120],
            detail=(detail or None) if detail is None else str(detail)[:2000],
            target=(str(target)[:255] if target else None),
            status=status,
            source=(str(source)[:40] if source else None),
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
        _log.debug("log_ai_activity failed (%s/%s): %s", scope, category, exc)


def derive_scope_ref(group=None, telegram_group_id=None, group_id=None):
    """Resolve (scope, group_ref) from whatever a call site has on hand.

    Priority: an explicit telegram_group_id (official) wins; otherwise a legacy
    Group object/id maps to custom scope. Returns (None, None) if unresolvable.
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


def ai_status(scope: str, group_ref, *, moderation_enabled, integrations_connected,
              kb_configured, provider_connected) -> dict:
    """Build the AI Status panel payload for one group.

    The four booleans are resolved by the caller (the route) because the
    underlying models differ between official and custom groups. Last-action
    timestamps are read from the shared AIActivity table.
    """
    from .models import AIActivity

    base = AIActivity.query.filter_by(scope=str(scope), group_ref=str(group_ref))
    last = base.order_by(AIActivity.created_at.desc()).first()
    last_ok = base.filter(
        AIActivity.status == "ok",
        AIActivity.category.in_(("knowledge", "engagement", "automation", "analytics")),
    ).order_by(AIActivity.created_at.desc()).first()

    return {
        "smart_moderation": "enabled" if moderation_enabled else "disabled",
        "ai_integrations": "connected" if integrations_connected else "not_connected",
        "knowledge_base": "configured" if kb_configured else "not_configured",
        "openai_provider": "connected" if provider_connected else "missing_key",
        "last_ai_action": last.created_at.isoformat() if last and last.created_at else None,
        "last_successful_response": last_ok.created_at.isoformat() if last_ok and last_ok.created_at else None,
    }


def _count_since(query, since):
    from .models import AIActivity
    return query.filter(AIActivity.created_at >= since).count()


def activity_summary(scope: str, group_ref, page: int = 1, per_page: int = 50,
                     category: str | None = None) -> dict:
    """Return metrics + a paginated timeline for one group's AI activity."""
    from .models import AIActivity

    now = datetime.utcnow()
    base = AIActivity.query.filter_by(scope=str(scope), group_ref=str(group_ref))

    metrics = {
        "today": _count_since(base, now - timedelta(days=1)),
        "week": _count_since(base, now - timedelta(days=7)),
        "month": _count_since(base, now - timedelta(days=30)),
        "total": base.count(),
    }

    # Per-category counts (last 30 days) for the category chips.
    by_category = {}
    for cat in _VALID_CATEGORIES:
        by_category[cat] = base.filter(
            AIActivity.category == cat,
            AIActivity.created_at >= now - timedelta(days=30),
        ).count()

    timeline_q = base
    if category and category in _VALID_CATEGORIES:
        timeline_q = timeline_q.filter(AIActivity.category == category)
    timeline_q = timeline_q.order_by(AIActivity.created_at.desc())
    paginated = timeline_q.paginate(page=page, per_page=min(per_page, 100), error_out=False)

    return {
        "metrics": metrics,
        "by_category": by_category,
        "events": [e.to_dict() for e in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    }
