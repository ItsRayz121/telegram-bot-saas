"""Bot Health Center (P1) — scheduled liveness pings, escalation, owner alerts.

The scheduled job pings every active bot (across the legacy `bots` and new
`custom_bots` tables) with Telegram getMe, rolls the result into a per-bot
BotHealthState row, escalates the health grade, and DMs/emails the owner when a
bot's grade gets worse.

`grade_for()` is a pure function so the escalation rules are unit-testable.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

_log = logging.getLogger("bot_health_monitor")

# Escalation thresholds (from the audit spec).
WARNING_FAILURES = 1     # 1 consecutive failure → warning
CRITICAL_FAILURES = 3    # 3 consecutive failures → critical
INACTIVE_AFTER = timedelta(days=7)    # no success in 7d → inactive
ARCHIVED_AFTER = timedelta(days=30)   # no success in 30d → archived

# Severity ordering so we can tell when a grade gets *worse* (alert) vs better.
_SEVERITY = {"healthy": 0, "warning": 1, "critical": 2, "inactive": 3, "archived": 4}


def grade_for(consecutive_failures: int, last_successful_ping, now=None) -> str:
    """Pure escalation function → one of healthy/warning/critical/inactive/archived."""
    now = now or datetime.utcnow()
    # Time-since-last-success dominates: a bot dark for weeks is inactive/archived
    # regardless of the failure counter.
    if last_successful_ping is not None:
        age = now - last_successful_ping
        if age >= ARCHIVED_AFTER:
            return "archived"
        if age >= INACTIVE_AFTER:
            return "inactive"
    if consecutive_failures >= CRITICAL_FAILURES:
        return "critical"
    if consecutive_failures >= WARNING_FAILURES:
        return "warning"
    return "healthy"


def is_worse(new_grade: str, old_grade: str | None) -> bool:
    """True if new_grade is strictly more severe than old_grade."""
    return _SEVERITY.get(new_grade, 0) > _SEVERITY.get(old_grade or "healthy", 0)


def _ping_telegram(token: str, timeout: int = 8):
    """Return (ok: bool, detail: str). Never raises."""
    try:
        import requests as _r
        resp = _r.get(f"https://api.telegram.org/bot{token}/getMe", timeout=timeout)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, ""
        return False, f"getMe HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # network / timeout / bad token
        return False, f"getMe error: {exc}"[:300]


def _iter_monitored_bots():
    """Yield (scope, ref, username, owner_user_id, token_or_none) for every active bot."""
    from .models import Bot, CustomBot
    for b in Bot.query.filter_by(is_active=True).all():
        token = None
        try:
            token = b.get_token()
        except Exception as exc:
            _log.warning("health: legacy bot %s token decrypt failed: %s", b.id, exc)
        yield ("legacy", str(b.id), b.bot_username, b.user_id, token)
    for cb in CustomBot.query.filter(CustomBot.status != "inactive").all():
        token = None
        try:
            token = cb.get_token()
        except Exception as exc:
            _log.warning("health: custom bot %s token decrypt failed: %s", cb.id, exc)
        yield ("custom", str(cb.id), cb.bot_username, cb.owner_user_id, token)


_RECOMMENDED_ACTION = {
    "warning": "We could not reach the bot once. If it persists, check that the "
               "bot is running and its token is valid.",
    "critical": "The bot has failed several checks. Verify the bot token in your "
                "dashboard and that the bot process/host is online.",
    "inactive": "No successful check in over 7 days. Re-deploy the bot or update "
                "its token to bring it back online.",
    "archived": "No successful check in over 30 days. This bot is archived — "
                "re-add a valid token to reactivate it.",
}


def _alert_owner(owner_user_id, bot_username, grade, detail, send_dm=None,
                 last_successful_ping=None):
    """Email + Telegram-DM the owner about a worsening bot. Best-effort.

    Includes bot name, error reason, last successful ping, and a grade-specific
    recommended action (Bot Health Notifications, Part 9).
    """
    from .models import User
    if not owner_user_id:
        return
    owner = User.query.get(owner_user_id)
    if not owner:
        return
    handle = ("@" + bot_username) if bot_username else "your bot"
    emoji = {"warning": "⚠️", "critical": "🚨", "inactive": "💤", "archived": "🗄"}.get(grade, "⚠️")
    last_ok = last_successful_ping.strftime("%Y-%m-%d %H:%M UTC") if last_successful_ping else "never"
    action = _RECOMMENDED_ACTION.get(grade, "Please check the bot token and that the bot is still running.")
    text = (
        f"{emoji} Telegizer Alert — {handle} is **{grade}**.\n\n"
        f"Error reason: {detail or 'unreachable'}\n"
        f"Last successful ping: {last_ok}\n\n"
        f"Recommended action: {action}\n\n"
        "Dashboard: https://telegizer.com/dashboard"
    )
    # Telegram DM
    if owner.telegram_user_id and send_dm:
        try:
            send_dm(owner.telegram_user_id, text)
        except Exception as exc:
            _log.debug("health: DM alert failed: %s", exc)
    # Email
    if owner.email:
        try:
            from .notifications import send_email
            html = (
                f"<p>{emoji} <b>{handle}</b> is <b>{grade}</b>.</p>"
                f"<p><b>Error reason:</b></p><pre>{(detail or 'unreachable')[:400]}</pre>"
                f"<p><b>Last successful ping:</b> {last_ok}</p>"
                f"<p><b>Recommended action:</b> {action}</p>"
                '<p><a href="https://telegizer.com/dashboard">Open dashboard</a></p>'
            )
            send_email(owner.email, f"{emoji} Bot health alert: {handle} is {grade}", html)
        except Exception as exc:
            _log.debug("health: email alert failed: %s", exc)


def run_health_checks(db, send_dm=None, now=None) -> dict:
    """Ping every monitored bot, update BotHealthState, escalate, alert on worsening.

    `send_dm` is injected (scheduler._send_telegram_dm) to keep this module free
    of Telegram-runtime imports. Returns a summary dict.
    """
    from .models import BotHealthState, BotHealthEvent
    now = now or datetime.utcnow()
    summary = {"checked": 0, "healthy": 0, "failed": 0, "alerts": 0}

    for scope, ref, username, owner_id, token in _iter_monitored_bots():
        summary["checked"] += 1
        state = BotHealthState.query.filter_by(scope=scope, ref=ref).first()
        if not state:
            state = BotHealthState(scope=scope, ref=ref)
            db.session.add(state)
        state.bot_username = username
        state.owner_user_id = owner_id
        state.last_ping_at = now

        if token:
            ok, detail = _ping_telegram(token)
        else:
            ok, detail = False, "no token / decrypt failed"

        if ok:
            state.consecutive_failures = 0
            state.last_successful_ping = now
            state.last_error = None
            summary["healthy"] += 1
        else:
            state.consecutive_failures = (state.consecutive_failures or 0) + 1
            state.last_failed_ping = now
            state.last_error = detail
            summary["failed"] += 1
            try:
                from .error_classification import classify_error
                err_class, severity, _ = classify_error(detail)
                db.session.add(BotHealthEvent(
                    scope=scope, ref=ref, category="ping",
                    detail=detail[:500], severity=severity, error_class=err_class,
                    created_at=now,
                ))
            except Exception:
                pass

        new_grade = grade_for(state.consecutive_failures, state.last_successful_ping, now)
        old_grade = state.health_grade
        state.health_grade = new_grade

        # Alert the owner only when the grade gets *worse* than what we last told
        # them about — this naturally rate-limits (no repeated alerts per cycle).
        if new_grade != "healthy" and is_worse(new_grade, state.last_alert_grade):
            _alert_owner(owner_id, username, new_grade, state.last_error,
                         send_dm=send_dm, last_successful_ping=state.last_successful_ping)
            state.last_alert_grade = new_grade
            summary["alerts"] += 1
        elif new_grade == "healthy":
            state.last_alert_grade = None  # recovered → re-arm alerts

    db.session.commit()
    _log.info("[bot_health] %s", summary)
    return summary
