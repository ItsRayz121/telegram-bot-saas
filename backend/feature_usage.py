"""Feature-usage logging layer (admin Feature Usage + Proof Metrics).

Single entry point for recording discrete feature actions across BOTH bot
lineages and the Echo assistant. Mirrors `backend.ai_activity` by design:

  • `log_feature_usage(...)` NEVER raises and NEVER blocks a live handler. Any
    failure is swallowed so usage logging can never break message processing or
    trip the anti-ban governor. Safe to call from inside python-telegram-bot
    async handlers.

  • Group addressing matches AIActivity / BotHealthEvent: scope ∈
    {official, custom, echo} with a string `group_ref` (telegram_group_id for
    official, str(Group.id) for custom).

The companion model is `FeatureUsageEvent` (models.py). Reporting/aggregation
helpers (for the Feature Usage tab) land in a later phase; this module is the
write path that starts collecting real data now.
"""
from __future__ import annotations

import logging
from datetime import datetime

_log = logging.getLogger("feature_usage")

# Canonical feature keys. Kept permissive (unknown keys are still stored, just
# normalised) so a new feature emitting usage never silently drops rows — but
# the catalog documents the expected set for the admin UI grouping.
FEATURE_KEYS = {
    # Moderation / protection
    "automod", "spam", "link", "ai_mod", "warn", "mute", "ban", "kick",
    "content_filter", "raid", "captcha", "nsfw", "flood",
    # Engagement / ops
    "welcome", "scheduler", "announce", "referral", "command",
    "forwarding", "workflow", "poll", "knowledge",
    # Echo assistant
    "assistant", "summary", "digest", "reminder", "task",
}

_VALID_STATUS = {"ok", "failed", "skipped"}
_VALID_SCOPE = {"official", "custom", "echo"}


def log_feature_usage(
    scope: str,
    feature: str,
    *,
    group_ref=None,
    bot_ref=None,
    user_ref=None,
    action: str | None = None,
    count: int = 1,
    status: str = "ok",
    meta: dict | None = None,
    db=None,
    commit: bool = True,
) -> None:
    """Record one feature action. Best-effort: every failure is swallowed.

    Args:
        scope: 'official' | 'custom' | 'echo'.
        feature: stable feature key (see FEATURE_KEYS).
        group_ref: telegram_group_id (official) or str(Group.id) (custom).
        bot_ref: 'official' or str(CustomBot.id).
        user_ref: telegram user id of the actor/target (for "most active users").
        action: specific action or command name.
        count: increment (defaults to 1).
        status: 'ok' | 'failed' | 'skipped'.
        meta: optional JSON context (never put secrets/PII raw here).
        db: pass an already-imported db; otherwise imported lazily.
        commit: set False when the caller owns the transaction.
    """
    try:
        if not feature:
            return
        scope = str(scope or "custom").lower()
        if scope not in _VALID_SCOPE:
            scope = "custom"
        if status not in _VALID_STATUS:
            status = "ok"
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 1
        if count <= 0:
            count = 1

        if db is None:
            from .models import db as _db
            db = _db
        from .models import FeatureUsageEvent

        row = FeatureUsageEvent(
            scope=scope,
            bot_ref=(str(bot_ref)[:64] if bot_ref is not None else None),
            group_ref=(str(group_ref)[:64] if group_ref is not None else None),
            user_ref=(str(user_ref)[:64] if user_ref is not None else None),
            feature=str(feature)[:40],
            action=(str(action)[:120] if action else None),
            count=count,
            status=status,
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
        _log.debug("log_feature_usage failed (%s/%s): %s", scope, feature, exc)


def automod_feature(rule_or_reason) -> str:
    """Map an automod rule key / human reason to a protection feature key.

    Lets "Spam protection" and "Link protection" get their own usage counts
    instead of everything collapsing into a generic "automod". Unknown rules
    fall back to "automod".
    """
    s = str(rule_or_reason or "").lower()
    if any(k in s for k in ("link", "url", "domain", "invite")):
        return "link"
    if any(k in s for k in ("spam", "flood")):
        return "spam"
    if any(k in s for k in ("nsfw", "porn", "explicit")):
        return "nsfw"
    if any(k in s for k in ("caps", "emoji", "forward", "email", "blacklist", "word")):
        return "automod"
    return "automod"


def derive_scope_ref(group=None, telegram_group_id=None, group_id=None):
    """Resolve (scope, group_ref) from whatever a call site has on hand.

    An explicit telegram_group_id (official) wins; otherwise a legacy Group
    object/id maps to custom scope. Returns (None, None) if unresolvable.
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
