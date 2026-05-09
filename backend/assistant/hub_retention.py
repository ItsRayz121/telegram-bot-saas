"""
Assistant Hub — Data retention enforcement.

Runs as a daily cron (03:00 UTC). Safe to call manually at any time.

Retention rules (from spec):
  - hub_digests older than 90 days  → DELETE
  - hub_extraction_batches older than 180 days → DELETE
  - hub_inbox_items dismissed more than 30 days ago → DELETE
  - Redis TTL handles raw buffer automatically (set on write, no action here)
"""
import logging
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)


def enforce_retention(app=None):
    """
    Delete expired Hub records per the retention policy.
    Pass a Flask app instance, or call inside an active app_context.
    """
    ctx = app.app_context() if app else None
    if ctx:
        ctx.push()
    try:
        _run()
    finally:
        if ctx:
            ctx.pop()


def _run():
    from ..models import db
    from ..assistant.hub_models import HubDigest, HubExtractionBatch, HubInboxItem

    now = datetime.utcnow()

    # Digests older than 90 days
    cutoff_digests = now - timedelta(days=90)
    deleted_digests = HubDigest.query.filter(
        HubDigest.generated_at < cutoff_digests
    ).delete(synchronize_session=False)

    # Extraction batch logs older than 180 days
    cutoff_batches = now - timedelta(days=180)
    deleted_batches = HubExtractionBatch.query.filter(
        HubExtractionBatch.completed_at < cutoff_batches,
        HubExtractionBatch.completed_at.isnot(None),
    ).delete(synchronize_session=False)

    # Dismissed inbox items older than 30 days post-dismissal
    cutoff_inbox = now - timedelta(days=30)
    deleted_inbox = HubInboxItem.query.filter(
        HubInboxItem.dismissed_at < cutoff_inbox,
        HubInboxItem.dismissed_at.isnot(None),
    ).delete(synchronize_session=False)

    db.session.commit()

    _log.info(
        "Hub retention: deleted digests=%d batches=%d inbox=%d",
        deleted_digests, deleted_batches, deleted_inbox,
    )
    return {
        "digests_deleted": deleted_digests,
        "batches_deleted": deleted_batches,
        "inbox_deleted": deleted_inbox,
    }
