"""Fire-and-forget job dispatch that does not need a Celery worker.

The celery-worker service is idled (see railway.worker.toml) — it was a second
always-on Railway container whose tasks each rebuilt the whole Flask app. The
handful of `.delay()` call sites we had are all "don't block the HTTP response"
work, not durable queue work, so they run in a daemon thread instead. That is the
same pattern the codebase already uses for outbound email and reward payouts.

The task bodies in scheduler.py are unchanged and still Celery-decorated. Setting
USE_CELERY=1 routes dispatch back through the broker, so the worker can be brought
back at any time without touching call sites.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)


def _use_celery():
    return os.environ.get("USE_CELERY", "").strip().lower() in ("1", "true", "yes")


def dispatch(task, *args, **kwargs):
    """Run *task* in the background. Returns immediately.

    Errors are logged, never raised — callers treat dispatch as best-effort, exactly
    as they did with .delay().
    """
    if _use_celery():
        try:
            return task.delay(*args, **kwargs)
        except Exception as exc:
            logger.error("dispatch: broker enqueue failed for %s: %s", task, exc)
            return None

    # Capture the live app so the thread runs inside a real app context. The task
    # bodies call create_app(), which returns the current app when one is active.
    app = None
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            app = current_app._get_current_object()
    except Exception:
        pass

    def _run():
        try:
            if app is not None:
                with app.app_context():
                    task(*args, **kwargs)
            else:
                task(*args, **kwargs)
        except Exception as exc:
            logger.error("dispatch: %s failed: %s", getattr(task, "name", task), exc, exc_info=True)

    threading.Thread(target=_run, daemon=True).start()
    return None
