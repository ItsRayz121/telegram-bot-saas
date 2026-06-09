"""Platform configuration & feature-flag resolver (Phase 2 admin-panel overhaul).

DB-first with hardcoded defaults. Admins edit values in the panel; everything
else in the codebase reads through ``get_setting`` / ``is_feature_enabled`` so a
value can change without a redeploy.

Caching: each process keeps a short-TTL in-memory cache so hot paths (e.g. the
maintenance gate on every request) don't hit the DB each time. Writes clear the
local cache immediately; other gunicorn workers pick up changes within TTL
seconds. Config changes are not latency-critical, so this is the right trade-off.
"""

import json
import logging
import time
from .config import Config

_log = logging.getLogger("platform_config")

_CACHE_TTL = 30  # seconds
_settings_cache = {"data": None, "ts": 0.0}
_flags_cache = {"data": None, "ts": 0.0}

# ── Seed defaults ──────────────────────────────────────────────────────────────
# key -> {value, category, is_public}. ``env`` (optional) names a Config attribute
# used as the fallback when no DB row exists and the default value is empty.
DEFAULT_SETTINGS = {
    # Branding
    "app_name":      {"value": "Telegizer", "category": "branding", "is_public": True},
    "app_tagline":   {"value": "Telegram group management, automation & AI", "category": "branding", "is_public": True},
    "logo_url":      {"value": "", "category": "branding", "is_public": True},
    "primary_color": {"value": "", "category": "branding", "is_public": True},
    # Links
    "support_url":   {"value": "", "category": "links", "is_public": True},
    "support_email": {"value": "", "category": "links", "is_public": True},
    "docs_url":      {"value": "", "category": "links", "is_public": True},
    "status_url":    {"value": "", "category": "links", "is_public": True},
    "terms_url":     {"value": "/terms", "category": "links", "is_public": True},
    "privacy_url":   {"value": "/privacy", "category": "links", "is_public": True},
    "frontend_url":  {"value": "", "category": "links", "is_public": True, "env": "FRONTEND_URL"},
    "mini_app_url":  {"value": "", "category": "links", "is_public": True},
    # Localization
    "default_timezone": {"value": "UTC", "category": "localization", "is_public": True},
    # Maintenance
    "maintenance_mode":    {"value": False, "category": "maintenance", "is_public": True},
    "maintenance_message": {"value": "Telegizer is undergoing scheduled maintenance. We'll be back shortly.",
                            "category": "maintenance", "is_public": True},
    # Onboarding
    "onboarding_tour_enabled": {"value": True, "category": "onboarding", "is_public": True},
}

# key -> {enabled, description}
DEFAULT_FLAGS = {
    "registrations_enabled":   {"enabled": True, "description": "Allow new account sign-ups. Off = registration is blocked."},
    "ai_features_enabled":     {"enabled": True, "description": "Master switch for AI features platform-wide."},
    "marketplace_enabled":     {"enabled": True, "description": "Enable the marketplace section."},
    "referrals_enabled":       {"enabled": True, "description": "Enable the referral program."},
    "new_bot_creation_enabled":{"enabled": True, "description": "Allow users to create/connect new bots."},
}

SETTING_KEYS = set(DEFAULT_SETTINGS.keys())
FLAG_KEYS = set(DEFAULT_FLAGS.keys())


# ── Internal cache loaders ─────────────────────────────────────────────────────

def _now():
    return time.time()


def _load_settings():
    """Return {key: value} merged from defaults, env fallback, and DB rows."""
    merged = {}
    for k, meta in DEFAULT_SETTINGS.items():
        val = meta.get("value")
        env_attr = meta.get("env")
        if (val in (None, "")) and env_attr:
            val = getattr(Config, env_attr, "") or val
        merged[k] = val
    try:
        from .models import PlatformSetting
        # Only this module's own keys — the platform_settings table is shared with
        # ai_config / billing_config, so filtering keeps namespaces isolated.
        for row in PlatformSetting.query.filter(PlatformSetting.key.in_(SETTING_KEYS)).all():
            try:
                merged[row.key] = json.loads(row.value_json) if row.value_json is not None else None
            except Exception:
                merged[row.key] = row.value_json
    except Exception as e:
        _log.warning("platform settings load failed, using defaults: %s", e)
    return merged


def _load_flags():
    merged = {k: meta["enabled"] for k, meta in DEFAULT_FLAGS.items()}
    try:
        from .models import FeatureFlag
        for row in FeatureFlag.query.all():
            merged[row.key] = bool(row.enabled)
    except Exception as e:
        _log.warning("feature flags load failed, using defaults: %s", e)
    return merged


def _settings():
    if _settings_cache["data"] is None or (_now() - _settings_cache["ts"]) > _CACHE_TTL:
        _settings_cache["data"] = _load_settings()
        _settings_cache["ts"] = _now()
    return _settings_cache["data"]


def _flags():
    if _flags_cache["data"] is None or (_now() - _flags_cache["ts"]) > _CACHE_TTL:
        _flags_cache["data"] = _load_flags()
        _flags_cache["ts"] = _now()
    return _flags_cache["data"]


def invalidate_cache():
    _settings_cache["data"] = None
    _flags_cache["data"] = None


# ── Public API ─────────────────────────────────────────────────────────────────

def get_setting(key, default=None):
    """Return the resolved value for ``key`` (DB > env > hardcoded default)."""
    data = _settings()
    if key in data:
        return data[key]
    if key in DEFAULT_SETTINGS:
        return DEFAULT_SETTINGS[key]["value"]
    return default


def set_setting(key, value, user_id=None):
    """Upsert a setting. Returns the new value. Raises ValueError on unknown key."""
    if key not in SETTING_KEYS:
        raise ValueError(f"Unknown setting key: {key}")
    from .models import db, PlatformSetting
    meta = DEFAULT_SETTINGS[key]
    # Coerce to the default's type so a stringy "false" can't be stored as a
    # truthy string (bool("false") is True). Protects the maintenance gate etc.
    if isinstance(meta.get("value"), bool) and not isinstance(value, bool):
        value = str(value).strip().lower() in ("true", "1", "yes", "on")
    row = PlatformSetting.query.filter_by(key=key).first()
    if not row:
        row = PlatformSetting(key=key, category=meta["category"], is_public=meta["is_public"])
        db.session.add(row)
    row.value_json = json.dumps(value)
    row.category = meta["category"]
    row.is_public = meta["is_public"]
    if user_id:
        row.updated_by = user_id
    db.session.commit()
    invalidate_cache()
    return value


def is_feature_enabled(key, default=True):
    """Return whether a feature flag is on (DB > hardcoded default)."""
    data = _flags()
    if key in data:
        return bool(data[key])
    if key in DEFAULT_FLAGS:
        return DEFAULT_FLAGS[key]["enabled"]
    return default


def set_feature_flag(key, enabled, user_id=None, description=None):
    if key not in FLAG_KEYS:
        raise ValueError(f"Unknown feature flag: {key}")
    from .models import db, FeatureFlag
    row = FeatureFlag.query.filter_by(key=key).first()
    if not row:
        row = FeatureFlag(key=key, description=DEFAULT_FLAGS[key]["description"])
        db.session.add(row)
    row.enabled = bool(enabled)
    if description is not None:
        row.description = description
    if user_id:
        row.updated_by = user_id
    db.session.commit()
    invalidate_cache()
    return bool(enabled)


def is_maintenance_enabled():
    return bool(get_setting("maintenance_mode", False))


def maintenance_message():
    return get_setting("maintenance_message") or "We'll be back shortly."


def public_config():
    """Return only is_public settings + public flag states, for unauthenticated UI."""
    settings = _settings()
    public = {k: settings.get(k, DEFAULT_SETTINGS[k]["value"])
              for k, meta in DEFAULT_SETTINGS.items() if meta["is_public"]}
    return {
        "settings": public,
        "flags": _flags(),
    }


def admin_config():
    """Full settings + flags with metadata, for the admin panel."""
    settings = _settings()
    flags = _flags()
    settings_out = []
    for k, meta in DEFAULT_SETTINGS.items():
        settings_out.append({
            "key": k,
            "value": settings.get(k, meta["value"]),
            "category": meta["category"],
            "is_public": meta["is_public"],
        })
    flags_out = [{
        "key": k,
        "enabled": flags.get(k, meta["enabled"]),
        "description": meta["description"],
    } for k, meta in DEFAULT_FLAGS.items()]
    return {"settings": settings_out, "flags": flags_out}
