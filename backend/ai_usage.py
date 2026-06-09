"""AI token/cost usage ledger recorder (Phase 5 admin-panel overhaul).

`record_ai_usage(...)` writes one AITokenUsage row per AI completion, best-effort
(never raises — must never break a live AI path). Token counts are exact when the
provider returns usage, else estimated from text length (~4 chars/token) and
flagged meta.estimated=True. Cost is priced from the configured per-1M rates
(ai_config.compute_cost_usd).

Mirrors backend.feature_usage conventions (lazy db import, swallow-all). Shared by
both bot lineages + Echo so all AI surfaces feed the same ledger.
"""

import logging
from datetime import datetime

_log = logging.getLogger("ai_usage")

_VALID_SCOPE = {"official", "custom", "echo", "workspace"}


def estimate_tokens(text) -> int:
    """Rough token estimate (~4 chars/token). Used when the provider omits usage."""
    if not text:
        return 0
    try:
        return max(1, int(len(str(text)) / 4))
    except Exception:
        return 0


def record_ai_usage(
    scope: str,
    feature: str,
    *,
    user_ref=None,
    group_ref=None,
    bot_ref=None,
    email=None,
    provider=None,
    model=None,
    key_source=None,
    input_tokens=None,
    output_tokens=None,
    input_text=None,
    output_text=None,
    cost_usd=None,
    meta: dict | None = None,
    db=None,
    commit: bool = True,
) -> None:
    """Record one AI completion's token usage + cost. Best-effort.

    Provide exact ``input_tokens``/``output_tokens`` when the provider returns
    usage; otherwise pass ``input_text``/``output_text`` and they'll be estimated.
    ``cost_usd`` is computed from configured rates when not supplied.
    """
    try:
        if not feature:
            return
        scope = str(scope or "workspace").lower()
        if scope not in _VALID_SCOPE:
            scope = "workspace"

        estimated = False
        if input_tokens is None:
            input_tokens = estimate_tokens(input_text)
            if input_text is not None:
                estimated = True
        if output_tokens is None:
            output_tokens = estimate_tokens(output_text)
            if output_text is not None:
                estimated = True
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        total = input_tokens + output_tokens

        if cost_usd is None:
            try:
                from . import ai_config
                cost_usd = ai_config.compute_cost_usd(input_tokens, output_tokens)
            except Exception:
                cost_usd = 0.0

        meta = dict(meta or {})
        if estimated:
            meta["estimated"] = True

        # Resolve owner email only for workspace scope, where user_ref is a real
        # app User.id. For echo/official/custom the user_ref is a Telegram user
        # id (a different namespace), so a PK lookup would be wrong — leave email
        # to be passed explicitly by those call sites.
        if email is None and user_ref is not None and scope == "workspace":
            try:
                from .models import User
                u = User.query.get(int(user_ref))
                if u:
                    email = u.email
            except Exception:
                pass

        if db is None:
            from .models import db as _db
            db = _db
        from .models import AITokenUsage

        row = AITokenUsage(
            scope=scope,
            bot_ref=(str(bot_ref)[:64] if bot_ref is not None else None),
            group_ref=(str(group_ref)[:64] if group_ref is not None else None),
            user_ref=(str(user_ref)[:64] if user_ref is not None else None),
            email=(str(email)[:255] if email else None),
            feature=str(feature)[:40],
            provider=(str(provider)[:40] if provider else None),
            model=(str(model)[:120] if model else None),
            key_source=(str(key_source)[:20] if key_source else None),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            cost_usd=cost_usd or 0,
            meta=meta or None,
            created_at=datetime.utcnow(),
        )
        db.session.add(row)
        if commit:
            db.session.commit()
    except Exception as exc:  # never break a live AI path over logging
        try:
            from .models import db as _db
            _db.session.rollback()
        except Exception:
            pass
        _log.debug("record_ai_usage failed (%s/%s): %s", scope, feature, exc)


def record_from_key_info(scope, feature, key_info, *, input_text=None, output_text=None,
                         input_tokens=None, output_tokens=None, **kw):
    """Convenience wrapper that pulls provider/model/source from a resolved
    ai_key_resolver key_info dict."""
    ki = key_info or {}
    return record_ai_usage(
        scope, feature,
        provider=ki.get("provider"),
        model=ki.get("model"),
        key_source=ki.get("source"),
        input_text=input_text, output_text=output_text,
        input_tokens=input_tokens, output_tokens=output_tokens,
        **kw,
    )
