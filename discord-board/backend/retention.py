"""Data retention for Guildizer — caps the append-only tables. Self-contained.

Port of Telegizer's backend/retention.py. Per the isolation rule the logic is COPIED,
never imported: this module touches only Guildizer's engine and models.

Why: xp_events grows by one row per XP grant and was never pruned, and five other
tables are append-only too. Storage is cheap, but the indexes sit in Postgres RAM,
which Railway bills per GB-minute — so these tables turn every new user into a
permanent, compounding line on the bill.

Two guarantees, both verified against the code rather than assumed:

1. NOBODY LOSES XP. Lifetime XP/level live on Member.xp / Member.level (running-total
   columns) which this never touches. xp_events only backs the rolling leaderboard
   windows via member_stats.xp_by_user(since=...).

   ⚠️ LOAD-BEARING: member_stats.xp_by_user() sums the WHOLE ledger when `since` is
   None. Today that never happens — crm_api.py:58 and leveling_api.py:173 both guard
   with `if period and period != "all"`, so the "all" period reads Member.xp instead
   and the largest window that ever reaches the ledger is 30 days (PERIOD_DAYS).
   If anyone ever removes that guard, an all-time leaderboard would start summing a
   PRUNED table and silently under-report. Keep the guard, or read Member.xp.

   We prune at 180 days — a 6x margin over that 30-day maximum.

2. NO HISTORY IS LOST. Expiring rows fold into xp_monthly first, so per-member monthly
   history survives forever at one row per member per month.

Safety of the sweep: batched (never long-locks the table out from under the bot),
atomic (DELETE ... RETURNING drives the roll-up in ONE transaction, so a crash rolls
back both and a re-run can neither double-count nor drop an unarchived row), capped
per run, and DRY-RUN BY DEFAULT.

NOT swept: guild_events. Despite the "event" name it is the Discord scheduled-events
feature (start_at/end_at), i.e. real user content — not a log.
"""

import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import engine

logger = logging.getLogger("guildizer.retention")


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


# Dry-run defaults ON: the first deploy reports what it would delete and deletes nothing.
DRY_RUN = _env_flag("RETENTION_DRY_RUN", True)
ENABLED = _env_flag("RETENTION_ENABLED", True)

BATCH_SIZE = _env_int("RETENTION_BATCH_SIZE", 5_000)
MAX_ROWS_PER_RUN = _env_int("RETENTION_MAX_ROWS_PER_RUN", 200_000)

XP_DAYS = _env_int("RETENTION_XP_DAYS", 180)
AUDIT_DAYS = _env_int("RETENTION_AUDIT_DAYS", 365)
DEFAULT_DAYS = _env_int("RETENTION_DEFAULT_DAYS", 180)

# (table, timestamp column, days). Hardcoded — never taken from user input, since these
# are interpolated into SQL.
_TABLES = [
    ("admin_audit_logs", "created_at", AUDIT_DAYS),
    ("protection_events", "created_at", DEFAULT_DAYS),
    ("feature_usage_events", "created_at", DEFAULT_DAYS),
    ("bot_health_events", "created_at", DEFAULT_DAYS),
]


def _count_older(db, table, ts_col, cutoff):
    n = db.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE {ts_col} < :cutoff"), {"cutoff": cutoff}
    ).scalar()
    return int(n or 0)


def _prune_table(db, table, ts_col, days, dry_run=True):
    cutoff = datetime.utcnow() - timedelta(days=days)

    if dry_run:
        n = _count_older(db, table, ts_col, cutoff)
        logger.info("[RETENTION][dry-run] %s: %d rows older than %dd would be deleted", table, n, days)
        return n

    sql = text(
        f"DELETE FROM {table} WHERE id IN ("
        f"  SELECT id FROM {table} WHERE {ts_col} < :cutoff ORDER BY id LIMIT :batch"
        f")"
    )
    total = 0
    while total < MAX_ROWS_PER_RUN:
        res = db.execute(sql, {"cutoff": cutoff, "batch": BATCH_SIZE})
        db.commit()
        deleted = res.rowcount or 0
        total += deleted
        if deleted < BATCH_SIZE:
            break

    if total:
        logger.info("[RETENTION] %s: deleted %d rows older than %dd", table, total, days)
    return total


def _rollup_and_prune_xp(db, dry_run=True):
    """Archive expiring xp_events into xp_monthly, then delete them — atomically."""
    cutoff = datetime.utcnow() - timedelta(days=XP_DAYS)

    if dry_run:
        n = _count_older(db, "xp_events", "created_at", cutoff)
        logger.info(
            "[RETENTION][dry-run] xp_events: %d rows older than %dd would be rolled up "
            "into xp_monthly and deleted (lifetime XP on Member.xp is untouched)",
            n, XP_DAYS,
        )
        return n

    delete_sql = text(
        "DELETE FROM xp_events WHERE id IN ("
        "  SELECT id FROM xp_events WHERE created_at < :cutoff ORDER BY id LIMIT :batch"
        ") RETURNING guild_id, user_id, amount, created_at"
    )
    upsert_sql = text(
        "INSERT INTO xp_monthly (guild_id, user_id, period, total_xp, event_count) "
        "VALUES (:guild_id, :user_id, :period, :total_xp, :event_count) "
        "ON CONFLICT (guild_id, user_id, period) DO UPDATE SET "
        "  total_xp    = xp_monthly.total_xp    + EXCLUDED.total_xp, "
        "  event_count = xp_monthly.event_count + EXCLUDED.event_count"
    )

    total = 0
    while total < MAX_ROWS_PER_RUN:
        rows = db.execute(delete_sql, {"cutoff": cutoff, "batch": BATCH_SIZE}).fetchall()
        if not rows:
            db.commit()
            break

        buckets = {}
        for guild_id, user_id, amount, created_at in rows:
            key = (guild_id, user_id, created_at.strftime("%Y-%m"))
            xp, count = buckets.get(key, (0, 0))
            buckets[key] = (xp + int(amount or 0), count + 1)

        for (guild_id, user_id, period), (xp, count) in buckets.items():
            db.execute(upsert_sql, {
                "guild_id": guild_id, "user_id": user_id, "period": period,
                "total_xp": xp, "event_count": count,
            })

        # One commit for the delete AND its roll-up — they stand or fall together.
        db.commit()

        total += len(rows)
        if len(rows) < BATCH_SIZE:
            break

    if total:
        logger.info("[RETENTION] xp_events: archived + deleted %d rows older than %dd", total, XP_DAYS)
    return total


def run_retention_sweep(dry_run=None):
    """Daily entry point. Safe to call repeatedly; never raises."""
    if not ENABLED:
        logger.info("[RETENTION] disabled (RETENTION_ENABLED=0) — skipping")
        return {}

    dry = DRY_RUN if dry_run is None else dry_run
    report = {}

    # An independent Session, not the request-scoped SessionLocal — this runs on the
    # bot's task loop, outside any request context.
    db = Session(engine)
    try:
        try:
            report["xp_events"] = _rollup_and_prune_xp(db, dry_run=dry)
        except Exception as exc:
            db.rollback()
            logger.error("[RETENTION] xp_events sweep failed: %s", exc)

        for table, ts_col, days in _TABLES:
            try:
                report[table] = _prune_table(db, table, ts_col, days, dry_run=dry)
            except Exception as exc:
                # A missing table on an older database is expected, not fatal — one bad
                # table must not stop the rest.
                db.rollback()
                logger.error("[RETENTION] %s sweep failed: %s", table, exc)
    finally:
        db.close()

    logger.info(
        "[RETENTION] sweep complete (dry_run=%s) — %s",
        dry, ", ".join(f"{k}={v}" for k, v in report.items()) or "nothing to do",
    )
    return report
