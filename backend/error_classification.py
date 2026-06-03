"""Bot error classification (Bot Health Center, Part 6/7).

Turns a raw error string into a stable (error_class, severity, label) triple so
the Bot Health Center can distinguish *real outages* from harmless deployment /
restart noise.

Severities
    info     — deployment / worker / interpreter shutdown. NOT a real failure;
               excluded from outage counts and never alerts the owner.
    warning  — transient: network blips, Telegram API hiccups, deploy overlap.
    critical — genuine outage: invalid token, bot offline/unreachable.

The single most important rule (from the spec): the signature
    "cannot schedule new futures after interpreter shutdown"
is a Python interpreter teardown race during a Railway/worker restart. It means
the process was being shut down — the bot did not crash and users were not
affected. It is classified `info` and must never count as a failure.
"""
from __future__ import annotations

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}

# Ordered most-specific → least-specific. First match wins.
_RULES = [
    # ── info: shutdown / restart / deploy teardown (not real failures) ──────────
    ("deployment_restart", "info", (
        "cannot schedule new futures after interpreter shutdown",
        "interpreter shutdown",
        "cannot schedule new futures",
        "event loop is closed",
        "application is shutting down",
        "application is stopping",
        "this event loop is already running",
        "shutting down",
    )),
    ("worker_restart", "info", (
        "sigterm", "received signal", "worker exiting", "graceful shutdown",
        "loop is closed", "runtimeerror: cannot reuse",
    )),
    # ── critical: real outages ──────────────────────────────────────────────────
    ("invalid_token", "critical", (
        "unauthorized", "invalid token", "invalidtoken", "token is invalid",
        "http 401", "401:", "not enough rights", "bot was blocked",
        "bot token is incorrect",
    )),
    ("bot_offline", "critical", (
        "name or service not known", "no route to host",
        "failed to establish a new connection", "connection refused",
        "getme http 404", "chat not found and stopped",
    )),
    # ── warning: transient ───────────────────────────────────────────────────────
    ("deploy_overlap", "warning", (
        "conflict", "terminated by other getupdates", "http 409", "409:",
    )),
    ("telegram_api", "warning", (
        "bad gateway", "http 502", "http 503", "502:", "503:",
        "internal server error", "http 500", "flood control", "too many requests",
        "retry after",
    )),
    ("network_error", "warning", (
        "networkerror", "timed out", "timeout", "connection", "connectionerror",
        "temporary failure in name resolution", "getaddrinfo", "read timed out",
        "ssl", "remote end closed", "httpx", "pool timeout",
    )),
]


def classify_error(detail: str | None) -> tuple[str, str, str]:
    """Return (error_class, severity, human_label) for a raw error string."""
    text = (detail or "").lower()
    for error_class, severity, needles in _RULES:
        if any(n in text for n in needles):
            return error_class, severity, _LABELS[error_class]
    return "unknown", "warning", "Unclassified error"


_LABELS = {
    "deployment_restart": "Deployment restart",
    "worker_restart": "Worker restart",
    "invalid_token": "Invalid token",
    "bot_offline": "Bot offline",
    "deploy_overlap": "Deploy overlap (another instance)",
    "telegram_api": "Telegram API failure",
    "network_error": "Temporary network error",
    "unknown": "Unclassified error",
}


def is_real_failure(severity: str | None) -> bool:
    """True if this severity should count as an outage (warning/critical)."""
    return severity not in (None, "info") if severity else True
