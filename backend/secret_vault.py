"""Platform secret/API-key vault (Phase 3 admin-panel overhaul).

Lets a Super Admin manage platform secrets (AI keys, bot tokens, payment &
email provider keys, social API keys, OAuth secrets) from the admin panel
instead of editing Railway env vars + redeploying.

Design:
  • Stored Fernet-encrypted, reusing utils.encryption (same key + rotation logic
    as bot tokens / TOTP — never a second crypto scheme).
  • Resolved DB-first with env fallback: ``get_secret(name)`` returns the DB value
    if set, else the ``Config`` env value. Call sites pass through this so a key
    can be rotated without a redeploy.
  • The plaintext is NEVER returned by the API — only a masked hint
    (first4****last4). Setting a value is write-only.
  • Short-TTL in-process cache so hot paths don't decrypt every call. Writes clear
    the cache locally; other workers refresh within TTL.

Live vs. restart: keys read through get_secret() at call time (AI keys, X/YouTube
checks) take effect within ~TTL seconds. Long-lived connections established at
startup (e.g. a running bot's Telegram session) pick up a new token on the next
restart/redeploy — the vault still stores/tests/audits them.
"""

import time
import logging
from .config import Config

_log = logging.getLogger("secret_vault")

_CACHE_TTL = 30
_cache = {"data": None, "ts": 0.0}

# ── Catalog ────────────────────────────────────────────────────────────────────
# name (== Config attr) -> metadata. ``test`` controls the Test Connection button.
SECRET_CATALOG = [
    # AI
    {"name": "PLATFORM_OPENROUTER_API_KEY", "label": "OpenRouter (platform AI key)", "category": "ai", "provider": "openrouter", "test": "ai", "live": True},
    {"name": "OPENAI_API_KEY", "label": "OpenAI API key", "category": "ai", "provider": "openai", "test": "ai", "live": True},
    {"name": "PLATFORM_GEMINI_API_KEY", "label": "Google Gemini API key", "category": "ai", "provider": "gemini", "test": "ai", "live": True},
    # Telegram bots
    {"name": "TELEGRAM_BOT_TOKEN", "label": "Official bot token (@telegizer_bot)", "category": "telegram", "provider": "telegram", "test": "telegram", "live": False},
    {"name": "ECHO_BOT_TOKEN", "label": "Echo assistant bot token", "category": "telegram", "provider": "telegram", "test": "telegram", "live": False},
    # Payments
    {"name": "NOWPAYMENTS_API_KEY", "label": "NOWPayments API key", "category": "payments", "provider": "nowpayments", "test": None, "live": True},
    {"name": "NOWPAYMENTS_IPN_SECRET", "label": "NOWPayments IPN secret", "category": "payments", "provider": "nowpayments", "test": None, "live": True},
    {"name": "LS_API_KEY", "label": "Lemon Squeezy API key", "category": "payments", "provider": "lemonsqueezy", "test": None, "live": True},
    {"name": "LS_WEBHOOK_SECRET", "label": "Lemon Squeezy webhook secret", "category": "payments", "provider": "lemonsqueezy", "test": None, "live": True},
    # Email
    {"name": "RESEND_API_KEY", "label": "Resend email API key", "category": "email", "provider": "resend", "test": None, "live": True},
    {"name": "SMTP_PASSWORD", "label": "SMTP password", "category": "email", "provider": "smtp", "test": None, "live": True},
    # Social / link checks
    {"name": "YOUTUBE_API_KEY", "label": "YouTube Data API key", "category": "social", "provider": "youtube", "test": None, "live": True},
    {"name": "TWITTERAPI_IO_KEY", "label": "twitterapi.io key", "category": "social", "provider": "twitterapi", "test": None, "live": True},
    {"name": "X_BEARER_TOKEN", "label": "X / Twitter bearer token", "category": "social", "provider": "x", "test": None, "live": True},
    # OAuth
    {"name": "GOOGLE_CLIENT_SECRET", "label": "Google OAuth client secret", "category": "oauth", "provider": "google", "test": None, "live": True},
]

CATALOG_BY_NAME = {s["name"]: s for s in SECRET_CATALOG}
SECRET_NAMES = set(CATALOG_BY_NAME.keys())


def _now():
    return time.time()


def _load():
    """Build {name: resolved_plaintext} — DB value if set, else env (Config)."""
    resolved = {}
    db_values = {}
    try:
        from .models import PlatformSecret
        for row in PlatformSecret.query.all():
            val = row.get_value()
            if val:
                db_values[row.name] = val
    except Exception as e:
        _log.warning("secret vault DB load failed, using env: %s", e)
    for name in SECRET_NAMES:
        if name in db_values:
            resolved[name] = db_values[name]
        else:
            resolved[name] = getattr(Config, name, "") or ""
    return resolved


def _resolved():
    if _cache["data"] is None or (_now() - _cache["ts"]) > _CACHE_TTL:
        _cache["data"] = _load()
        _cache["ts"] = _now()
    return _cache["data"]


def invalidate_cache():
    _cache["data"] = None


def get_secret(name, default=None):
    """Resolve a platform secret: DB override first, then env (Config), then default."""
    data = _resolved()
    val = data.get(name)
    if val:
        return val
    env_val = getattr(Config, name, None)
    return env_val if env_val else default


def _mask(value):
    from .utils.encryption import mask_key
    return mask_key(value) if value else None


def set_secret(name, value, user_id=None):
    """Encrypt and store a secret. Returns its masked hint. Raises ValueError on
    unknown name or empty value."""
    if name not in SECRET_NAMES:
        raise ValueError(f"Unknown secret: {name}")
    value = (value or "").strip()
    if not value:
        raise ValueError("Value must not be empty")
    from .models import db, PlatformSecret
    from .utils.encryption import encrypt_value
    meta = CATALOG_BY_NAME[name]
    row = PlatformSecret.query.filter_by(name=name).first()
    if not row:
        row = PlatformSecret(name=name)
        db.session.add(row)
    row.value_encrypted = encrypt_value(value)
    row.masked_hint = _mask(value)
    row.provider = meta.get("provider")
    row.category = meta.get("category")
    row.last_test_ok = None
    row.last_tested_at = None
    if user_id:
        row.updated_by = user_id
    db.session.commit()
    invalidate_cache()
    return row.masked_hint


def clear_secret(name, user_id=None):
    """Delete the DB override so the secret falls back to the env value."""
    if name not in SECRET_NAMES:
        raise ValueError(f"Unknown secret: {name}")
    from .models import db, PlatformSecret
    row = PlatformSecret.query.filter_by(name=name).first()
    if row:
        db.session.delete(row)
        db.session.commit()
    invalidate_cache()


def status():
    """Return per-secret status for the admin UI. NEVER includes plaintext."""
    rows = {}
    try:
        from .models import PlatformSecret
        rows = {r.name: r for r in PlatformSecret.query.all()}
    except Exception as e:
        _log.warning("secret vault status DB read failed: %s", e)

    out = []
    for meta in SECRET_CATALOG:
        name = meta["name"]
        row = rows.get(name)
        env_val = getattr(Config, name, "") or ""
        if row and row.value_encrypted:
            source = "db"
            masked = row.masked_hint
            is_set = True
        elif env_val:
            source = "env"
            masked = _mask(env_val)
            is_set = True
        else:
            source = "none"
            masked = None
            is_set = False
        out.append({
            "name": name,
            "label": meta["label"],
            "category": meta["category"],
            "provider": meta.get("provider"),
            "testable": bool(meta.get("test")),
            "live": meta.get("live", True),
            "source": source,
            "is_set": is_set,
            "masked": masked,
            "last_test_ok": row.last_test_ok if row else None,
            "last_tested_at": row.last_tested_at.isoformat() if (row and row.last_tested_at) else None,
            "updated_at": row.updated_at.isoformat() if (row and row.updated_at) else None,
        })
    return out


def test_secret(name, value=None):
    """Test connectivity for a secret. Uses ``value`` if given, else the resolved
    value. Returns (ok: bool, message: str). Persists the result on the row."""
    if name not in SECRET_NAMES:
        return False, "Unknown secret"
    meta = CATALOG_BY_NAME[name]
    kind = meta.get("test")
    key = (value or "").strip() or get_secret(name)
    if not key:
        return False, "No value configured"

    ok, message = False, "Not testable"
    try:
        if kind == "ai":
            from .routes.api_keys import _test_connection
            ok, message = _test_connection(meta["provider"], key, None, None)
        elif kind == "telegram":
            import httpx
            resp = httpx.get(f"https://api.telegram.org/bot{key}/getMe", timeout=8.0)
            body = resp.json()
            if resp.status_code == 200 and body.get("ok"):
                ok, message = True, f"@{body.get('result', {}).get('username')}"
            else:
                ok, message = False, body.get("description") or f"HTTP {resp.status_code}"
        else:
            return False, "No automated test for this secret"
    except Exception as e:
        ok, message = False, str(e)[:200]

    # Persist the result (only if a stored row exists; don't create one for an env-only test)
    try:
        from .models import db, PlatformSecret
        from datetime import datetime
        row = PlatformSecret.query.filter_by(name=name).first()
        if row:
            row.last_test_ok = ok
            row.last_tested_at = datetime.utcnow()
            db.session.commit()
    except Exception:
        pass
    return ok, message
