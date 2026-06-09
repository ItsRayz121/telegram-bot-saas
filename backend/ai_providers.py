"""AI provider balance / spend helpers (Phase 4 admin-panel overhaul).

Surfaces, for the AI Management control center:
  • OpenRouter — live credits via GET https://openrouter.ai/api/v1/credits
    (uses the platform OpenRouter key from the secret vault).
  • OpenAI — no public balance API, so we report manual config (purchased
    balance) + computed spend (today, from the Redis spend counter; historical
    cost comes from the AI usage ledger in Phase 5).

Everything is best-effort: a provider that errors or has no key returns a
status row rather than raising, so the admin page always renders.
"""

import logging
from datetime import date

_log = logging.getLogger("ai_providers")

# Curated cheap-model presets shown in the admin UI. Each preset fills the
# provider, base URL and default model in one click.
MODEL_PRESETS = [
    {"id": "openrouter_gpt4o_mini", "label": "OpenRouter · GPT-4o mini (cheap)",
     "provider": "openrouter", "base_url": "https://openrouter.ai/api/v1",
     "model": "openai/gpt-4o-mini", "cost_in": 0.15, "cost_out": 0.60},
    {"id": "openrouter_deepseek", "label": "OpenRouter · DeepSeek Chat (cheap)",
     "provider": "deepseek", "base_url": "https://openrouter.ai/api/v1",
     "model": "deepseek/deepseek-chat", "cost_in": 0.14, "cost_out": 0.28},
    {"id": "openrouter_llama", "label": "OpenRouter · Llama 3.1 8B (open-source)",
     "provider": "llama", "base_url": "https://openrouter.ai/api/v1",
     "model": "meta-llama/llama-3.1-8b-instruct", "cost_in": 0.05, "cost_out": 0.08},
    {"id": "openai_gpt4o_mini", "label": "OpenAI · GPT-4o mini (cheap)",
     "provider": "openai", "base_url": "https://api.openai.com/v1",
     "model": "gpt-4o-mini", "cost_in": 0.15, "cost_out": 0.60},
    {"id": "custom", "label": "Custom provider / model",
     "provider": "custom", "base_url": "", "model": "", "cost_in": 0.0, "cost_out": 0.0},
]


def _spend_today_usd():
    try:
        import redis as _redis
        from .config import Config
        r = _redis.from_url(Config.REDIS_URL or "redis://localhost:6379/0", socket_timeout=2)
        return round(float(r.get(f"platform_ai_spend:{date.today().isoformat()}") or 0), 4)
    except Exception:
        return None


def _openrouter_balance():
    """Live OpenRouter credits. Returns a status dict (never raises)."""
    from . import secret_vault
    key = secret_vault.get_secret("PLATFORM_OPENROUTER_API_KEY") or secret_vault.get_secret("OPENAI_API_KEY")
    if not key:
        return {"provider": "openrouter", "source": "missing", "configured": False}
    try:
        import httpx
        resp = httpx.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {key}"}, timeout=8.0,
        )
        if resp.status_code != 200:
            return {"provider": "openrouter", "source": "error", "configured": True,
                    "error": f"HTTP {resp.status_code}"}
        data = (resp.json() or {}).get("data", {}) or {}
        total = float(data.get("total_credits") or 0)
        used = float(data.get("total_usage") or 0)
        return {
            "provider": "openrouter", "source": "live", "configured": True,
            "total_usd": round(total, 4), "used_usd": round(used, 4),
            "remaining_usd": round(total - used, 4),
        }
    except Exception as e:
        _log.warning("openrouter balance fetch failed: %s", e)
        return {"provider": "openrouter", "source": "error", "configured": True, "error": str(e)[:160]}


def _openai_balance():
    """OpenAI exposes no balance API — report manual config + computed spend."""
    from . import ai_config, secret_vault
    configured = bool(secret_vault.get_secret("OPENAI_API_KEY"))
    purchased = 0.0
    try:
        purchased = float(ai_config.get("ai_purchased_balance_usd") or 0)
    except (TypeError, ValueError):
        purchased = 0.0
    spend_today = _spend_today_usd()
    return {
        "provider": "openai", "source": "manual", "configured": configured,
        "purchased_usd": round(purchased, 4),
        "spend_today_usd": spend_today,
        "remaining_usd": (round(purchased - (spend_today or 0), 4) if purchased else None),
    }


def get_balances():
    """All provider balance rows for the admin UI (best-effort)."""
    return [_openrouter_balance(), _openai_balance()]


def budget_status():
    """Monthly budget + alert threshold snapshot for the admin UI."""
    from . import ai_config
    try:
        monthly = float(ai_config.get("ai_monthly_budget_usd") or 0)
    except (TypeError, ValueError):
        monthly = 0.0
    try:
        alert_pct = int(ai_config.get("ai_alert_threshold_pct") or 0)
    except (TypeError, ValueError):
        alert_pct = 0
    return {"monthly_budget_usd": monthly, "alert_threshold_pct": alert_pct,
            "spend_today_usd": _spend_today_usd()}
