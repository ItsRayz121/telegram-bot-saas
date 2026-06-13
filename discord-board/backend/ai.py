"""Optional AI assistant backend for Guildizer — provider-agnostic.

Pick the backend via GUILDIZER_AI_PROVIDER:
  openai      -> OpenAI Chat Completions (default). gpt-4o-mini handles text AND
                 vision in one cheap model.
  openrouter  -> OpenAI-compatible gateway (e.g. deepseek/deepseek-chat) for cheap
                 text. DeepSeek has no vision, so image checks fall back to OpenAI.
  anthropic   -> Claude (legacy / fallback).

SDKs are imported lazily, so the bot runs fine without them installed or a key
set — callers get is_configured() == False and a graceful None instead of a crash.

Image moderation (check_image) always needs a vision-capable model. If an OpenAI
key is present it is used for vision (Config.VISION_MODEL = gpt-4o-mini) no matter
what the text provider is, so an OpenRouter/DeepSeek text setup still gets working
NSFW image checks. Otherwise vision uses Anthropic (if that's the provider) or is
disabled gracefully.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from config import Config

log = logging.getLogger("guildizer.ai")

_SYSTEM = (
    "You are Guildizer's helpful assistant inside a Discord community. "
    "Answer concisely (a few sentences). Be friendly and practical. "
    "You cannot perform server actions — only answer questions and help."
)

_IMG_SYSTEM = (
    "You are an image-safety classifier for a Discord community. "
    "Reply with exactly one word: NSFW if the image contains nudity, sexual "
    "content, or graphic gore; OK otherwise."
)

# Per-provider default text model when GUILDIZER_AI_MODEL is unset.
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "openrouter": "deepseek/deepseek-chat",
    "anthropic": "claude-haiku-4-5-20251001",
}

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# OpenRouter recommends (does not require) attribution headers.
_OPENROUTER_HEADERS = {"X-Title": "Guildizer"}


@dataclass
class AIResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def _provider() -> str:
    return (Config.AI_PROVIDER or "openai").lower()


def _provider_chain() -> list[str]:
    """Ordered text-provider rollup: the configured provider first, then OpenAI as
    an automatic fallback (when it isn't already primary and a key is set). So an
    OpenRouter/DeepSeek setup tries DeepSeek first and quietly falls back to OpenAI
    if DeepSeek errors or returns nothing."""
    primary = _provider()
    chain = [primary]
    if primary != "openai" and Config.OPENAI_API_KEY:
        chain.append("openai")
    return chain


def _provider_configured(p: str) -> bool:
    if p == "openrouter":
        return bool(Config.OPENROUTER_API_KEY)
    if p == "anthropic":
        return bool(Config.ANTHROPIC_API_KEY)
    return bool(Config.OPENAI_API_KEY)


def _model_for(provider: str) -> str:
    """Model for a given provider. The GUILDIZER_AI_MODEL override only applies to
    the configured primary provider — a fallback provider always uses its own
    default (so a DeepSeek model id never leaks into an OpenAI fallback call)."""
    if provider == _provider() and Config.AI_MODEL:
        return Config.AI_MODEL
    return _DEFAULT_MODELS.get(provider, "gpt-4o-mini")


def is_configured() -> bool:
    """True if ANY provider in the rollup chain has a usable key."""
    return any(_provider_configured(p) for p in _provider_chain())


# --- lazy clients ------------------------------------------------------------

_oai_clients: dict[str, object] = {}
_anthropic_client = None


def _openai_client(api_key: str, base_url: str | None, default_headers: dict | None):
    """Shared OpenAI-SDK client keyed by endpoint (works for OpenAI & OpenRouter).
    None if the SDK isn't installed or no key is set."""
    if not api_key:
        return None
    cache_key = base_url or "openai"
    if cache_key not in _oai_clients:
        try:
            from openai import OpenAI  # lazy: optional dependency
        except ImportError:
            log.warning("openai SDK not installed; OpenAI/OpenRouter AI disabled")
            return None
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if default_headers:
            kwargs["default_headers"] = default_headers
        _oai_clients[cache_key] = OpenAI(**kwargs)
    return _oai_clients[cache_key]


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        if not Config.ANTHROPIC_API_KEY:
            return None
        try:
            import anthropic  # lazy: optional dependency
        except ImportError:
            log.warning("anthropic SDK not installed; Anthropic AI disabled")
            return None
        _anthropic_client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    return _anthropic_client


# --- endpoint resolution -----------------------------------------------------

def _attempt(provider: str, system: str, prompt: str, max_tokens: int) -> AIResult | None:
    """Run one text completion against a single provider. Returns None (never
    raises) so the rollup can move on to the next provider in the chain."""
    if not _provider_configured(provider):
        return None
    model = _model_for(provider)
    try:
        if provider == "anthropic":
            return _run_anthropic(model, system, prompt, max_tokens)
        if provider == "openrouter":
            return _run_openai(Config.OPENROUTER_API_KEY, _OPENROUTER_BASE_URL,
                               _OPENROUTER_HEADERS, model, system, prompt, max_tokens)
        return _run_openai(Config.OPENAI_API_KEY, None, None, model, system, prompt, max_tokens)
    except Exception:  # noqa: BLE001 — let the rollup try the next provider
        log.exception("AI attempt failed (provider=%s, model=%s)", provider, model)
        return None


# --- low-level runners -------------------------------------------------------

def _run_openai(api_key, base_url, headers, model, system, prompt, max_tokens,
                image_url=None) -> AIResult | None:
    client = _openai_client(api_key, base_url, headers)
    if client is None:
        return None
    if image_url:
        user_content = [
            {"type": "text", "text": prompt or "Classify this image."},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
    else:
        user_content = prompt
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_content})
    resp = client.chat.completions.create(
        model=model, max_tokens=max_tokens, messages=messages,
    )
    text = (resp.choices[0].message.content or "").strip()
    usage = resp.usage
    return AIResult(
        text=text,
        model=model,
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
    )


def _run_anthropic(model, system, prompt, max_tokens, image_url=None) -> AIResult | None:
    client = _get_anthropic_client()
    if client is None:
        return None
    if image_url:
        content = []
        if prompt:
            content.append({"type": "text", "text": prompt})
        content.append({"type": "image", "source": {"type": "url", "url": image_url}})
    else:
        content = prompt
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system or "",
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    usage = resp.usage
    return AIResult(
        text=text,
        model=model,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )


def _verdict(text: str, positive: str) -> str | None:
    """Strict one-word classifier parse: the reply must BE the positive label
    (not merely contain it — 'NOT PROMO' must read as ok)."""
    first = (text or "").strip().upper().strip(".,!\"'")
    return positive if first.split()[:1] == [positive] else None


# --- public API (stable; callers unchanged) ----------------------------------

def complete(system: str, prompt: str, max_tokens: int | None = None) -> AIResult | None:
    """Generic completion with a custom system prompt. Walks the provider rollup
    (e.g. DeepSeek -> OpenAI), returning the first usable result. Graceful: returns
    None only when every provider is unavailable, errors, or yields empty text."""
    mt = max_tokens or Config.AI_MAX_TOKENS
    sys_t = (system or "")[:4000]
    prompt_t = (prompt or "")[:6000]
    primary = _provider()
    for provider in _provider_chain():
        result = _attempt(provider, sys_t, prompt_t, mt)
        if result is not None and result.text:
            if provider != primary:
                log.info("AI rolled up to fallback provider=%s", provider)
            return result
    return None


def ask(prompt: str) -> AIResult | None:
    """Answer a user question with the default assistant persona."""
    if not is_configured():
        return None
    return complete(_SYSTEM, (prompt or "")[:4000])


def classify_promo(text: str, group_topic: str) -> tuple[str, AIResult] | None:
    """Smart-mod layer: is this message off-topic promotion/spam for this
    community? Returns ('promo'|'ok', usage) or None when AI unavailable."""
    system = (
        "You are a strict but fair Discord moderation classifier. "
        f"The community topic is: {group_topic or 'general'}. "
        "Reply with exactly one word: PROMO if the message is unsolicited promotion, "
        "advertising, or scam-like solicitation that does not belong here; OK otherwise."
    )
    result = complete(system, text, max_tokens=5)
    if result is None:
        return None
    verdict = "promo" if _verdict(result.text, "PROMO") else "ok"
    return verdict, result


def status() -> dict:
    """Non-calling config snapshot for the admin AI-health panel: the active
    provider, the rollup chain, which keys/models are set, and vision readiness.
    Makes NO network call (free, instant)."""
    return {
        "provider": _provider(),
        "chain": _provider_chain(),
        "configured": is_configured(),
        "max_tokens": Config.AI_MAX_TOKENS,
        "providers": {
            "openrouter": {"key_set": bool(Config.OPENROUTER_API_KEY),
                           "model": _model_for("openrouter")},
            "openai": {"key_set": bool(Config.OPENAI_API_KEY),
                       "model": _model_for("openai")},
            "anthropic": {"key_set": bool(Config.ANTHROPIC_API_KEY),
                          "model": _model_for("anthropic")},
        },
        "vision": {
            "available": bool(Config.OPENAI_API_KEY)
            or (_provider() == "anthropic" and bool(Config.ANTHROPIC_API_KEY)),
            "model": (Config.VISION_MODEL if Config.OPENAI_API_KEY
                      else _model_for("anthropic") if _provider() == "anthropic" else None),
        },
    }


def probe() -> dict:
    """Live one-shot health check: walks the rollup chain and reports which
    provider actually answered, the model, latency, tokens, and reply text.
    Cheap (max_tokens=5). Use sparingly — it spends a real (tiny) AI call."""
    import time
    chain = _provider_chain()
    t0 = time.perf_counter()
    for provider in chain:
        result = _attempt(provider, "You are a health check.",
                          "Reply with the single word OK.", 5)
        if result is not None and result.text:
            return {
                "ok": True, "provider_used": provider, "model": result.model,
                "text": result.text, "chain": chain,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
            }
    return {
        "ok": False, "provider_used": None, "chain": chain,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "error": "no_provider_responded — check keys/models in the service env",
    }


def check_image(image_url: str) -> tuple[str, AIResult] | None:
    """Vision moderation: 'nsfw' | 'ok'. Returns None when no vision-capable
    backend is available. Prefers OpenAI (gpt-4o-mini) whenever an OpenAI key is
    set — even if the text provider is OpenRouter/DeepSeek — so image checks keep
    working. Falls back to Anthropic vision when that's the provider."""
    try:
        if Config.OPENAI_API_KEY:
            result = _run_openai(
                Config.OPENAI_API_KEY, None, None, Config.VISION_MODEL,
                _IMG_SYSTEM, "Classify this image.", 5, image_url=image_url,
            )
        elif _provider() == "anthropic" and Config.ANTHROPIC_API_KEY:
            result = _run_anthropic(_model_for("anthropic"), _IMG_SYSTEM, "", 5, image_url=image_url)
        else:
            # OpenRouter/DeepSeek with no OpenAI key -> vision unsupported.
            return None
        if result is None:
            return None
        return ("nsfw" if _verdict(result.text, "NSFW") else "ok"), result
    except Exception:  # noqa: BLE001
        log.exception("AI image check failed")
        return None
