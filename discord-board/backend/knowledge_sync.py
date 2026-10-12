"""Controlled sync for external knowledge sources (Guildizer).

Everything that decides WHETHER a provider fetch may happen lives here, so the
manual button, the opt-in schedule and the preview all go through the same gate:

  1. kill switches  - KNOWLEDGE_SOURCES_ENABLED, KNOWLEDGE_X_SYNC_ENABLED,
                      KNOWLEDGE_SCHEDULED_SYNC_ENABLED
  2. Pro entitlement of the server (checked again at run time, so a lapsed plan
     stops scheduled syncs)
  3. a shared rolling cooldown (X: 24h) claimed ATOMICALLY before any fetch, keyed
     by credential + server owner + canonical handle. Manual clicks, schedules and
     duplicate workers all draw from this one window, so a manual sync can never
     be followed by an immediate scheduled one and two racing requests cannot
     both fetch.
  4. budgets reserved BEFORE the fetch at source / owner / shared-credential
     level, corrected afterwards. A failed or retried attempt stays counted.

Copied (not imported) from Telegizer's knowledge_sync.py and re-pointed at this
service's SQLAlchemy sessions. Budget numbers are small defaults, overridable by
env var. The shared-credential figure is only this feature's SLICE of the
platform twitterapi.io key: the rest is left for X raid verification.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import case, func, text as _sql_text
from sqlalchemy.exc import IntegrityError

from models import Guild, KnowledgeSource, KnowledgeSyncCooldown, KnowledgeSyncLedger

log = logging.getLogger("guildizer.kb.sync")

SCHEDULES = {
    "manual": None,
    "daily": timedelta(days=1),
    "every_3_days": timedelta(days=3),
    "weekly": timedelta(days=7),
}

X_CREDENTIAL_KEY = "twitterapi_io:guildizer"


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


def sources_enabled() -> bool:
    return os.environ.get("KNOWLEDGE_SOURCES_ENABLED", "1") != "0"


def x_sync_enabled() -> bool:
    return os.environ.get("KNOWLEDGE_X_SYNC_ENABLED", "1") != "0"


def scheduled_sync_enabled() -> bool:
    return os.environ.get("KNOWLEDGE_SCHEDULED_SYNC_ENABLED", "1") != "0"


def is_paid(db, guild_id: int) -> bool:
    """Pro entitlement of the server. Uses the same plan resolution as the rest of
    the dashboard (server Pro, or the owner's account-level Pro)."""
    import plan_limits
    return plan_limits.plan_of(db, guild_id) == "pro"


def owner_user_id(db, source):
    """The server owner whose budget governs this source."""
    guild = db.get(Guild, source.guild_id)
    return guild.owner_id if guild else None


def cooldown_key(owner_id, handle):
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
    updated = (db.query(KnowledgeSyncCooldown)
               .filter(KnowledgeSyncCooldown.key == key, KnowledgeSyncCooldown.next_eligible_at <= now)
               .update({"next_eligible_at": new_until}, synchronize_session=False))
    if updated:
        db.commit()
        return True
    try:
        db.add(KnowledgeSyncCooldown(key=key, next_eligible_at=new_until))
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def cooldown_until(db, key):
    row = db.get(KnowledgeSyncCooldown, key)
    return row.next_eligible_at if row else None


def extend_cooldown(db, key, until):
    """Push the window out (rate limit). Never shortens it."""
    (db.query(KnowledgeSyncCooldown)
       .filter(KnowledgeSyncCooldown.key == key, KnowledgeSyncCooldown.next_eligible_at < until)
       .update({"next_eligible_at": until}, synchronize_session=False))
    db.commit()


def release_cooldown(db, key, previous):
    """Give the window back - ONLY for attempts that never reached the provider."""
    if previous is None:
        db.query(KnowledgeSyncCooldown).filter(KnowledgeSyncCooldown.key == key).delete(synchronize_session=False)
    else:
        (db.query(KnowledgeSyncCooldown).filter(KnowledgeSyncCooldown.key == key)
           .update({"next_eligible_at": previous}, synchronize_session=False))
    db.commit()


# ── budgets ──────────────────────────────────────────────────────────────────

def _sum_pages(db, since, **filters):
    L = KnowledgeSyncLedger
    spent = case((L.pages_used > L.pages_reserved, L.pages_used), else_=L.pages_reserved)
    q = db.query(func.coalesce(func.sum(spent), 0)).filter(L.created_at >= since)
    for col, val in filters.items():
        q = q.filter(getattr(L, col) == val)
    return int(q.scalar() or 0)


def remaining_budget(db, source, owner_id, now):
    """Pages still available to this run, with the scope that limits it."""
    lim = limits()
    day, month = now - timedelta(days=1), now - timedelta(days=30)
    scopes = (
        ("source", lim["source_pages_30d"] - _sum_pages(db, month, source_id=source.id)),
        ("server owner", lim["workspace_pages_day"] - _sum_pages(db, day, workspace_user_id=owner_id)),
        ("shared credential", lim["credential_pages_day"] - _sum_pages(db, day, credential_key=X_CREDENTIAL_KEY)),
    )
    scope, left = min(scopes, key=lambda x: x[1])
    return max(0, min(left, lim["pages_per_run"])), scope


def reserve(db, source, owner_id, trigger, now):
    """Reserve pages BEFORE fetching. Returns (ledger_row | None, pages, limiting_scope).

    Insert-then-verify under a Postgres advisory lock so two concurrent sources
    cannot both spend the last pages."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(_sql_text("SELECT pg_advisory_xact_lock(884201)"))
    pages, scope = remaining_budget(db, source, owner_id, now)
    if pages < 1:
        db.rollback()
        return None, 0, scope
    row = KnowledgeSyncLedger(source_id=source.id, workspace_user_id=owner_id,
                              credential_key=X_CREDENTIAL_KEY, trigger=trigger,
                              pages_reserved=pages, status="reserved", created_at=now)
    db.add(row)
    db.commit()
    return row, pages, scope


def finish_ledger(db, row, status, usage):
    try:
        row.status = status
        row.pages_used = int((usage or {}).get("requests") or 0)
        row.resources_returned = int((usage or {}).get("resources") or 0)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("could not finalise sync ledger row")


# ── failure policy ───────────────────────────────────────────────────────────

def record_failure(source, now, *, fatal=False):
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
    S = KnowledgeSource
    return (db.query(S)
            .filter(S.enabled.is_(True), S.sync_schedule != "manual", S.next_sync_at.isnot(None),
                    S.next_sync_at <= now, S.schedule_paused_reason.is_(None))
            .order_by(S.next_sync_at.asc()).limit(limit).all())
