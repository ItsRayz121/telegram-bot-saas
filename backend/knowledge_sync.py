"""Controlled sync for external knowledge sources.

Everything that decides WHETHER a provider fetch may happen lives here, so the
manual button, the opt-in schedule and the preview all go through the same gate:

  1. kill switches  - KNOWLEDGE_SOURCES_ENABLED, KNOWLEDGE_X_SYNC_ENABLED
  2. Pro entitlement of the workspace owner (checked again at run time, so a
     lapsed plan stops scheduled syncs)
  3. a shared rolling cooldown (X: 24h) claimed ATOMICALLY before any fetch, keyed
     by credential context + workspace + canonical handle. Manual clicks, schedules
     and duplicate workers all draw from this one window, so a manual sync can
     never be followed by an immediate scheduled one, and two racing requests
     cannot both fetch.
  4. budgets reserved BEFORE the fetch at source / workspace / shared-credential
     level, corrected afterwards. A failed or retried attempt stays counted.

Budget numbers are deliberately small defaults, overridable by env var. The shared
credential figure is only the knowledge feature's SLICE of the platform key: the
rest of the key's allowance is left for Campaign verification, which uses the same
credential.
"""
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import text as _sql_text
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

SCHEDULES = {
    "manual": None,
    "daily": timedelta(days=1),
    "every_3_days": timedelta(days=3),
    "weekly": timedelta(days=7),
}

X_CREDENTIAL_KEY = "twitterapi_io:platform"


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def limits():
    """Current limits (read on every call so an env change needs no code change)."""
    return {
        "cooldown": timedelta(hours=_int_env("X_SYNC_COOLDOWN_HOURS", 24)),
        "pages_per_run": max(1, _int_env("X_SYNC_MAX_PAGES_PER_RUN", 3)),
        "initial_posts": max(5, _int_env("X_SYNC_INITIAL_MAX_POSTS", 60)),
        "source_pages_30d": _int_env("X_SYNC_SOURCE_PAGES_PER_30D", 60),
        "workspace_pages_day": _int_env("X_SYNC_WORKSPACE_PAGES_PER_DAY", 15),
        "credential_pages_day": _int_env("X_SYNC_CREDENTIAL_PAGES_PER_DAY", 100),
        "max_failures": max(1, _int_env("X_SYNC_MAX_CONSECUTIVE_FAILURES", 3)),
    }


def is_paid(user) -> bool:
    from .utils.plan_gating import PAID_TIERS
    return bool(user and user.subscription_tier in PAID_TIERS and user.subscription_active)


def owner_user_id(source):
    """The workspace owner whose plan and budget govern this source."""
    from .models import Bot, Group, TelegramGroup
    if source.telegram_group_id:
        tg = TelegramGroup.query.filter_by(telegram_group_id=str(source.telegram_group_id)).first()
        return tg.owner_user_id if tg else None
    if source.group_id:
        grp = Group.query.get(source.group_id)
        bot = Bot.query.get(grp.bot_id) if grp else None
        return bot.user_id if bot else None
    return None


def cooldown_key(source, owner_id, handle):
    return f"x:{X_CREDENTIAL_KEY}:{owner_id}:{(handle or '').lower()}"[:160]


def next_scheduled(schedule, now):
    delta = SCHEDULES.get(schedule or "manual")
    return now + delta if delta else None


# ── cooldown ─────────────────────────────────────────────────────────────────

def claim_cooldown(db, key, now, window):
    """Atomically take the shared window. True = we own this run; False = cooling.

    UPDATE-where-eligible first; if the row does not exist yet, INSERT it (a unique
    key violation means a concurrent request created it first -> we lost)."""
    new_until = now + window
    res = db.session.execute(
        _sql_text("UPDATE knowledge_sync_cooldowns SET next_eligible_at = :n "
                  "WHERE key = :k AND next_eligible_at <= :now"),
        {"n": new_until, "k": key, "now": now})
    if res.rowcount:
        db.session.commit()
        return True
    try:
        db.session.execute(
            _sql_text("INSERT INTO knowledge_sync_cooldowns (key, next_eligible_at) VALUES (:k, :n)"),
            {"k": key, "n": new_until})
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def cooldown_until(db, key):
    row = db.session.execute(
        _sql_text("SELECT next_eligible_at FROM knowledge_sync_cooldowns WHERE key = :k"), {"k": key}).first()
    if not row:
        return None
    val = row[0]
    # Raw SQL returns text on SQLite (tests / local dev) and a datetime on Postgres.
    return datetime.fromisoformat(val) if isinstance(val, str) else val


def extend_cooldown(db, key, until):
    """Push the window out (rate limit). Never shortens it."""
    db.session.execute(
        _sql_text("UPDATE knowledge_sync_cooldowns SET next_eligible_at = :u "
                  "WHERE key = :k AND next_eligible_at < :u"), {"u": until, "k": key})
    db.session.commit()


def release_cooldown(db, key, previous):
    """Give the window back - ONLY for attempts that never reached the provider."""
    if previous is None:
        db.session.execute(_sql_text("DELETE FROM knowledge_sync_cooldowns WHERE key = :k"), {"k": key})
    else:
        db.session.execute(_sql_text("UPDATE knowledge_sync_cooldowns SET next_eligible_at = :p WHERE key = :k"),
                           {"p": previous, "k": key})
    db.session.commit()


# ── budgets ──────────────────────────────────────────────────────────────────

def _sum_pages(db, since, **filters):
    from .models import KnowledgeSyncLedger as L
    q = db.session.query(db.func.coalesce(db.func.sum(
        db.case((L.pages_used > L.pages_reserved, L.pages_used), else_=L.pages_reserved)), 0)
    ).filter(L.created_at >= since)
    for col, val in filters.items():
        q = q.filter(getattr(L, col) == val)
    return int(q.scalar() or 0)


def remaining_budget(db, source, owner_id, now):
    """Pages still available to this run, with the scope that limits it."""
    lim = limits()
    day, month = now - timedelta(days=1), now - timedelta(days=30)
    scopes = (
        ("source", lim["source_pages_30d"] - _sum_pages(db, month, source_id=source.id)),
        ("workspace", lim["workspace_pages_day"] - _sum_pages(db, day, workspace_user_id=owner_id)),
        ("shared credential", lim["credential_pages_day"] - _sum_pages(db, day, credential_key=X_CREDENTIAL_KEY)),
    )
    scope, left = min(scopes, key=lambda x: x[1])
    return max(0, min(left, lim["pages_per_run"])), scope


def reserve(db, source, owner_id, trigger, now):
    """Reserve pages BEFORE fetching. Returns (ledger_row | None, pages, limiting_scope).

    Insert-then-verify under a Postgres advisory lock so two concurrent sources
    cannot both spend the last pages."""
    from .models import KnowledgeSyncLedger as L
    if db.engine.dialect.name == "postgresql":
        db.session.execute(_sql_text("SELECT pg_advisory_xact_lock(884201)"))
    pages, scope = remaining_budget(db, source, owner_id, now)
    if pages < 1:
        db.session.rollback()
        return None, 0, scope
    row = L(source_id=source.id, workspace_user_id=owner_id, credential_key=X_CREDENTIAL_KEY,
            trigger=trigger, pages_reserved=pages, status="reserved", created_at=now)
    db.session.add(row)
    db.session.commit()
    return row, pages, scope


def finish_ledger(db, row, status, usage):
    try:
        row.status = status
        row.pages_used = int((usage or {}).get("requests") or 0)
        row.resources_returned = int((usage or {}).get("resources") or 0)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("could not finalise sync ledger row")


# ── failure policy ───────────────────────────────────────────────────────────

def record_failure(db, source, now, *, fatal=False, error=None):
    """Count a failed attempt. After N consecutive failures (or any fatal one, such
    as invalid credentials) the SCHEDULE is paused so it cannot retry forever; the
    manual button stays available."""
    source.consecutive_failures = int(source.consecutive_failures or 0) + 1
    if source.sync_schedule != "manual" and (fatal or source.consecutive_failures >= limits()["max_failures"]):
        source.schedule_paused_reason = (
            "Paused: credentials were rejected." if fatal else
            f"Paused after {source.consecutive_failures} failed attempts. Fix the source, then sync manually to resume."
        )
        source.next_sync_at = None


def record_success(source, now):
    source.consecutive_failures = 0
    source.schedule_paused_reason = None
    source.next_sync_at = next_scheduled(source.sync_schedule, now)


def due_sources(db, now, limit=3):
    from .models import KnowledgeSource as S
    return (S.query.filter(S.enabled.is_(True), S.sync_schedule != "manual", S.next_sync_at.isnot(None),
                           S.next_sync_at <= now, S.schedule_paused_reason.is_(None))
            .order_by(S.next_sync_at.asc()).limit(limit).all())
