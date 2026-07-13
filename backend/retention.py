"""Data retention — caps the append-only tables that otherwise grow forever.

Several hot-path tables get one row per message (xp_events) or per moderation
action, and nothing ever deleted them. Storage is cheap, but the indexes are not:
they sit in Postgres RAM, which Railway bills per GB-minute, and they slow every
leaderboard query down. Left alone these tables grow in step with the user base
forever — which is exactly the cost curve a free tier must not have.

Two guarantees this module is built around:

1. NOBODY LOSES XP. Lifetime XP and level live on Member.xp / OfficialMember.xp,
   which are running-total columns this module never touches. xp_events is only
   the ledger behind the rolling 1/7/30-day windows (database.xp_period_subquery,
   scheduler.recompute_xp_periods) — nothing in the codebase reads a row older
   than 30 days. We prune at 180 by default: a 6x margin.

2. NO HISTORY IS LOST. Before an xp_events row is deleted it is folded into
   xp_monthly, so "how much XP did this member earn in March" is still answerable
   forever, at one row per member per month instead of thousands.

Safety properties of the sweep itself:

  * Batched. A single DELETE over millions of rows would hold a lock long enough
    to stall the bots. We delete in small batches and commit between them.
  * Atomic + re-runnable. The delete and the roll-up it feeds happen in ONE
    transaction (DELETE ... RETURNING drives the upsert). A crash mid-sweep rolls
    back both, so rows are never counted twice and never vanish uncounted.
  * Capped per run. A run stops after RETENTION_MAX_ROWS_PER_RUN so the first
    sweep over a huge backlog can't run for hours; the next run resumes.
  * Dry-run by default. RETENTION_DRY_RUN=1 (the default) reports what *would* be
    deleted and deletes nothing. Set it to 0 only once the reported numbers look
    right.
"""

import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import text

from .models import db

logger = logging.getLogger("retention")


def _env_int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _env_flag(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Dry-run defaults to ON. The first deploy must not delete anything until the
# reported row counts have been eyeballed.
DRY_RUN = _env_flag("RETENTION_DRY_RUN", True)
ENABLED = _env_flag("RETENTION_ENABLED", True)

BATCH_SIZE = _env_int("RETENTION_BATCH_SIZE", 5_000)
MAX_ROWS_PER_RUN = _env_int("RETENTION_MAX_ROWS_PER_RUN", 200_000)

XP_DAYS = _env_int("RETENTION_XP_DAYS", 180)
AUDIT_DAYS = _env_int("RETENTION_AUDIT_DAYS", 365)
DEFAULT_DAYS = _env_int("RETENTION_DEFAULT_DAYS", 180)

# (table, timestamp column, retention days, extra WHERE)
# Table and column names are hardcoded here and never taken from user input —
# they are interpolated into SQL, so this list is the trust boundary.
_TABLES = [
    ("audit_logs", "timestamp", AUDIT_DAYS, None),
    ("feature_usage_events", "created_at", DEFAULT_DAYS, None),
    ("auto_reply_logs", "triggered_at", DEFAULT_DAYS, None),
    ("forward_logs", "created_at", DEFAULT_DAYS, None),
    ("bot_health_events", "created_at", DEFAULT_DAYS, None),
    # Never drop a row an admin still has to action — escalation_events doubles as
    # the pending-review queue (bot_features/escalation.py reads status='pending').
    ("escalation_events", "created_at", DEFAULT_DAYS, "status <> 'pending'"),
]


def _count_older_than(table, ts_col, cutoff, extra_where=None):
    where = f"{ts_col} < :cutoff"
    if extra_where:
        where += f" AND ({extra_where})"
    row = db.session.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE {where}"), {"cutoff": cutoff}
    ).scalar()
    return int(row or 0)


def _prune_table(table, ts_col, days, extra_where=None, dry_run=True):
    """Batch-delete rows older than `days`. Returns the number deleted (or that
    would be deleted, in dry-run)."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    if dry_run:
        n = _count_older_than(table, ts_col, cutoff, extra_where)
        logger.info("[RETENTION][dry-run] %s: %d rows older than %dd would be deleted", table, n, days)
        return n

    where = f"{ts_col} < :cutoff"
    if extra_where:
        where += f" AND ({extra_where})"

    # Delete by primary key from a bounded subselect: keeps each statement short so
    # the lock is never held long enough to stall the bot's writes.
    sql = text(
        f"DELETE FROM {table} WHERE id IN ("
        f"  SELECT id FROM {table} WHERE {where} ORDER BY id LIMIT :batch"
        f")"
    )

    total = 0
    while total < MAX_ROWS_PER_RUN:
        res = db.session.execute(sql, {"cutoff": cutoff, "batch": BATCH_SIZE})
        db.session.commit()
        deleted = res.rowcount or 0
        total += deleted
        if deleted < BATCH_SIZE:
            break

    if total:
        logger.info("[RETENTION] %s: deleted %d rows older than %dd", table, total, days)
    return total


def _rollup_and_prune_xp(dry_run=True):
    """Fold expiring xp_events into xp_monthly, then delete them — atomically.

    The DELETE ... RETURNING feeds the roll-up in the SAME transaction, so the rows
    are archived if and only if they are removed. That is what makes a re-run (or a
    crash mid-sweep) safe: it can neither double-count a month nor drop a row that
    was never archived.
    """
    cutoff = datetime.utcnow() - timedelta(days=XP_DAYS)

    if dry_run:
        n = _count_older_than("xp_events", "created_at", cutoff)
        logger.info(
            "[RETENTION][dry-run] xp_events: %d rows older than %dd would be rolled "
            "up into xp_monthly and deleted (lifetime XP on Member.xp is untouched)",
            n, XP_DAYS,
        )
        return n

    delete_sql = text(
        "DELETE FROM xp_events WHERE id IN ("
        "  SELECT id FROM xp_events WHERE created_at < :cutoff ORDER BY id LIMIT :batch"
        ") RETURNING scope, member_id, amount, created_at"
    )
    upsert_sql = text(
        "INSERT INTO xp_monthly (scope, member_id, period, total_xp, event_count) "
        "VALUES (:scope, :member_id, :period, :total_xp, :event_count) "
        "ON CONFLICT (scope, member_id, period) DO UPDATE SET "
        "  total_xp    = xp_monthly.total_xp    + EXCLUDED.total_xp, "
        "  event_count = xp_monthly.event_count + EXCLUDED.event_count"
    )

    total = 0
    while total < MAX_ROWS_PER_RUN:
        rows = db.session.execute(
            delete_sql, {"cutoff": cutoff, "batch": BATCH_SIZE}
        ).fetchall()
        if not rows:
            db.session.commit()
            break

        buckets = {}
        for scope, member_id, amount, created_at in rows:
            key = (scope, member_id, created_at.strftime("%Y-%m"))
            xp, count = buckets.get(key, (0, 0))
            buckets[key] = (xp + int(amount or 0), count + 1)

        for (scope, member_id, period), (xp, count) in buckets.items():
            db.session.execute(upsert_sql, {
                "scope": scope, "member_id": member_id, "period": period,
                "total_xp": xp, "event_count": count,
            })

        # One commit for the delete AND its roll-up — they stand or fall together.
        db.session.commit()

        total += len(rows)
        if len(rows) < BATCH_SIZE:
            break

    if total:
        logger.info(
            "[RETENTION] xp_events: archived + deleted %d rows older than %dd",
            total, XP_DAYS,
        )
    return total


def run_retention_sweep(app=None, dry_run=None):
    """Daily entry point. Safe to call repeatedly; never raises."""
    if not ENABLED:
        logger.info("[RETENTION] disabled (RETENTION_ENABLED=0) — skipping")
        return {}

    dry = DRY_RUN if dry_run is None else dry_run
    report = {}

    try:
        report["xp_events"] = _rollup_and_prune_xp(dry_run=dry)
    except Exception as exc:
        db.session.rollback()
        logger.error("[RETENTION] xp_events sweep failed: %s", exc)

    for table, ts_col, days, extra_where in _TABLES:
        try:
            report[table] = _prune_table(table, ts_col, days, extra_where, dry_run=dry)
        except Exception as exc:
            # One bad table must not stop the rest — a missing table on an older
            # database is expected, not fatal.
            db.session.rollback()
            logger.error("[RETENTION] %s sweep failed: %s", table, exc)

    logger.info(
        "[RETENTION] sweep complete (dry_run=%s) — %s",
        dry, ", ".join(f"{k}={v}" for k, v in report.items()) or "nothing to do",
    )
    return report
