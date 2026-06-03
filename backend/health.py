"""
Fail-safe bot health/error recorder.

`record_bot_error()` writes one row to bot_health_events. It is designed to be
called from anywhere — bot threads, webhooks, AI helpers — and to NEVER raise or
slow down the caller. If anything goes wrong (no app context, DB unavailable,
etc.) it silently no-ops. Bot behavior must never change because of this module.
"""
from __future__ import annotations

import logging
import random

from datetime import datetime, timedelta

_log = logging.getLogger("bot_health")

# Best-effort retention: occasionally prune rows older than this.
_RETENTION_DAYS = 7
# Roughly 1-in-N inserts also triggers a prune, so we don't run DELETE every time.
_PRUNE_EVERY = 50


def record_bot_error(scope: str, ref, category: str, detail: str) -> None:
    """Record a single bot failure. Swallows all exceptions — never raises."""
    try:
        from flask import has_app_context

        if not has_app_context():
            # Safe to call from contexts without Flask (e.g. raw AI helpers) —
            # just skip silently rather than crash the caller.
            return

        from .models import db, BotHealthEvent
        from .error_classification import classify_error

        error_class, severity, _label = classify_error(detail)
        ev = BotHealthEvent(
            scope=(scope or "")[:20],
            ref=(str(ref)[:64] if ref is not None else None),
            category=(category or "")[:20],
            detail=(str(detail)[:500] if detail else None),
            severity=severity,
            error_class=error_class,
            created_at=datetime.utcnow(),
        )
        db.session.add(ev)
        db.session.commit()

        # Occasionally prune old rows so the table can't grow unbounded.
        if random.randint(1, _PRUNE_EVERY) == 1:
            _prune_old(db, BotHealthEvent)
    except Exception as exc:  # pragma: no cover - defensive
        try:
            # Roll back so a poisoned session doesn't break the caller's own commit.
            from .models import db
            db.session.rollback()
        except Exception:
            pass
        _log.debug("record_bot_error failed (ignored): %s", exc)


def _prune_old(db, BotHealthEvent) -> None:
    try:
        cutoff = datetime.utcnow() - timedelta(days=_RETENTION_DAYS)
        BotHealthEvent.query.filter(BotHealthEvent.created_at < cutoff).delete(
            synchronize_session=False
        )
        db.session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        try:
            db.session.rollback()
        except Exception:
            pass
        _log.debug("bot_health prune failed (ignored): %s", exc)
