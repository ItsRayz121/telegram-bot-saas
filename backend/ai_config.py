"""AI management settings (Phase 4 admin-panel overhaul).

DB-overridable AI knobs — default model, daily platform spend cap, and per-tier
daily token limits — editable by an Admin (ai.manage) without a redeploy. Values
resolve DB-first (PlatformSetting rows, separate key namespace) with the existing
Config/hardcoded defaults as fallback.

Stored in the generic PlatformSetting KV table (is_public=False) so no new table /
migration is needed. Distinct from platform_config (branding/maintenance, which is
config.manage / super-only) because AI management is delegable to the Admin role.
"""

import json
import time
import logging
from .config import Config

_log = logging.getLogger("ai_config")

_CACHE_TTL = 30
_cache = {"data": None, "ts": 0.0}

# key -> default. Defaults mirror the previous hardcoded values so behaviour is
# identical until an admin overrides them.
AI_DEFAULTS = {
    "ai_default_model": "openai/gpt-4o-mini",
    "ai_default_base_url": "https://openrouter.ai/api/v1",
    "ai_daily_spend_cap_usd": float(getattr(Config, "MAX_DAILY_AI_SPEND_USD", 50) or 50),
    "ai_tokens_free": 10000,
    "ai_tokens_pro": 200000,
    "ai_tokens_enterprise": 500000,
}
AI_KEYS = set(AI_DEFAULTS.keys())


def _load():
    merged = dict(AI_DEFAULTS)
    try:
        from .models import PlatformSetting
        rows = PlatformSetting.query.filter(PlatformSetting.key.in_(AI_KEYS)).all()
        for row in rows:
            try:
                merged[row.key] = json.loads(row.value_json) if row.value_json is not None else AI_DEFAULTS[row.key]
            except Exception:
                merged[row.key] = AI_DEFAULTS[row.key]
    except Exception as e:
        _log.warning("ai_config load failed, using defaults: %s", e)
    return merged


def _resolved():
    if _cache["data"] is None or (time.time() - _cache["ts"]) > _CACHE_TTL:
        _cache["data"] = _load()
        _cache["ts"] = time.time()
    return _cache["data"]


def invalidate_cache():
    _cache["data"] = None


def get(key):
    return _resolved().get(key, AI_DEFAULTS.get(key))


def set_value(key, value, user_id=None):
    if key not in AI_KEYS:
        raise ValueError(f"Unknown AI setting: {key}")
    # Coerce to the default's type.
    default = AI_DEFAULTS[key]
    if isinstance(default, bool):
        value = bool(value)
    elif isinstance(default, int) and not isinstance(default, bool):
        value = int(float(value))   # tolerate "200000" and "200000.0"
    elif isinstance(default, float):
        value = float(value)
    else:
        value = str(value)
    from .models import db, PlatformSetting
    row = PlatformSetting.query.filter_by(key=key).first()
    if not row:
        row = PlatformSetting(key=key, category="ai", is_public=False)
        db.session.add(row)
    row.value_json = json.dumps(value)
    row.category = "ai"
    row.is_public = False
    if user_id:
        row.updated_by = user_id
    db.session.commit()
    invalidate_cache()
    return value


# ── Convenience accessors used by the AI key resolver ──────────────────────────

def default_model():
    return get("ai_default_model") or AI_DEFAULTS["ai_default_model"]


def default_base_url():
    return get("ai_default_base_url") or AI_DEFAULTS["ai_default_base_url"]


def daily_spend_cap():
    try:
        return float(get("ai_daily_spend_cap_usd"))
    except (TypeError, ValueError):
        return AI_DEFAULTS["ai_daily_spend_cap_usd"]


def daily_token_limit(tier):
    key = {"enterprise": "ai_tokens_enterprise", "pro": "ai_tokens_pro"}.get(tier, "ai_tokens_free")
    try:
        return int(get(key))
    except (TypeError, ValueError):
        return AI_DEFAULTS[key]


def all_settings():
    """Settings list for the admin UI."""
    data = _resolved()
    return [{"key": k, "value": data.get(k, AI_DEFAULTS[k]), "default": AI_DEFAULTS[k]} for k in AI_DEFAULTS]
