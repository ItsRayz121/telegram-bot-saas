"""Billing / pricing configuration (Phase 4 admin-panel overhaul).

DB-overridable tier prices, editable by a Super Admin (pricing.manage) without a
redeploy. CRITICAL: every place that needs a price — the checkout amount, the
webhook amount-verification, and the public /plans display — reads through
get_tier_prices()/get_plans() here, so display, charge and verification can never
drift apart.

Stored in the generic PlatformSetting KV table (is_public=True; prices are public)
so no new table/migration is needed. Falls back to the previous hardcoded values.
"""

import copy
import json
import time
import logging
from .config import Config

_log = logging.getLogger("billing_config")

_CACHE_TTL = 30
_cache = {"data": None, "ts": 0.0}

# Previous hardcoded values (billing._TIER_PRICES_USD) — the fallback defaults.
PRICE_DEFAULTS = {
    "pro": {"monthly": 9, "annual": 86},
    "enterprise": {"monthly": 49, "annual": 392},
}
TIERS = ("pro", "enterprise")
PERIODS = ("monthly", "annual")


def _key(tier, period):
    return f"price_{tier}_{period}"


PRICE_KEYS = {_key(t, p) for t in TIERS for p in PERIODS}


def _load():
    prices = copy.deepcopy(PRICE_DEFAULTS)
    try:
        from .models import PlatformSetting
        rows = PlatformSetting.query.filter(PlatformSetting.key.in_(PRICE_KEYS)).all()
        by_key = {r.key: r for r in rows}
        for t in TIERS:
            for p in PERIODS:
                row = by_key.get(_key(t, p))
                if row and row.value_json is not None:
                    try:
                        val = float(json.loads(row.value_json))
                        if val > 0:
                            prices[t][p] = val
                    except Exception:
                        pass
    except Exception as e:
        _log.warning("billing_config load failed, using defaults: %s", e)
    return prices


def get_tier_prices():
    """Return {tier: {period: usd}} — DB-first with hardcoded fallback (cached)."""
    if _cache["data"] is None or (time.time() - _cache["ts"]) > _CACHE_TTL:
        _cache["data"] = _load()
        _cache["ts"] = time.time()
    return _cache["data"]


def invalidate_cache():
    _cache["data"] = None


def set_tier_price(tier, period, usd, user_id=None):
    if tier not in TIERS or period not in PERIODS:
        raise ValueError("Invalid tier/period")
    usd = float(usd)
    if usd <= 0:
        raise ValueError("Price must be greater than 0")
    from .models import db, PlatformSetting
    key = _key(tier, period)
    row = PlatformSetting.query.filter_by(key=key).first()
    if not row:
        row = PlatformSetting(key=key, category="pricing", is_public=True)
        db.session.add(row)
    row.value_json = json.dumps(usd)
    row.category = "pricing"
    row.is_public = True
    if user_id:
        row.updated_by = user_id
    db.session.commit()
    invalidate_cache()
    return usd


def get_plans():
    """Config.PLANS with prices overridden from the resolved tier prices (cents)."""
    plans = copy.deepcopy(Config.PLANS)
    prices = get_tier_prices()
    for tier in TIERS:
        if tier in plans:
            plans[tier]["price"] = int(round(prices[tier]["monthly"] * 100))
            plans[tier]["price_annual"] = int(round(prices[tier]["annual"] * 100))
    return plans
