"""Optional AI assistant backend for Guildizer, via the Anthropic API.

Thin wrapper around the Messages API. The SDK is imported lazily so the bot runs
fine without `anthropic` installed or a key set — callers get is_configured()
== False and a graceful message instead of a crash. Defaults to a small, cheap
Claude model (configurable via GUILDIZER_AI_MODEL).
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


@dataclass
class AIResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def is_configured() -> bool:
    return bool(Config.ANTHROPIC_API_KEY)


def ask(prompt: str) -> AIResult | None:
    """Return an AIResult, or None if AI is unavailable/errored."""
    if not is_configured():
        return None
    try:
        import anthropic  # lazy: optional dependency
    except ImportError:
        log.warning("anthropic SDK not installed; /ask disabled")
        return None

    try:
        client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=Config.AI_MODEL,
            max_tokens=Config.AI_MAX_TOKENS,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt[:4000]}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        usage = resp.usage
        return AIResult(
            text=text.strip() or "(no answer)",
            model=Config.AI_MODEL,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )
    except Exception:  # noqa: BLE001 — never let an AI error crash the handler
        log.exception("AI ask failed")
        return None


def complete(system: str, prompt: str, max_tokens: int | None = None) -> AIResult | None:
    """Generic completion with a custom system prompt (Phase 16). Same graceful
    degradation as ask()."""
    if not is_configured():
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=Config.AI_MODEL,
            max_tokens=max_tokens or Config.AI_MAX_TOKENS,
            system=system[:4000],
            messages=[{"role": "user", "content": prompt[:6000]}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        usage = resp.usage
        return AIResult(
            text=text.strip() or "",
            model=Config.AI_MODEL,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )
    except Exception:  # noqa: BLE001
        log.exception("AI complete failed")
        return None


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
    verdict = "promo" if "PROMO" in result.text.upper() else "ok"
    return verdict, result


def check_image(image_url: str) -> tuple[str, AIResult] | None:
    """Vision moderation: 'nsfw' | 'ok'. Returns None when AI unavailable."""
    if not is_configured():
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=Config.AI_MODEL,
            max_tokens=5,
            system=("You are an image-safety classifier for a Discord community. "
                    "Reply with exactly one word: NSFW if the image contains nudity, "
                    "sexual content, or graphic gore; OK otherwise."),
            messages=[{
                "role": "user",
                "content": [{"type": "image", "source": {"type": "url", "url": image_url}}],
            }],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        usage = resp.usage
        result = AIResult(text=text.strip(), model=Config.AI_MODEL,
                          input_tokens=getattr(usage, "input_tokens", 0) or 0,
                          output_tokens=getattr(usage, "output_tokens", 0) or 0)
        return ("nsfw" if "NSFW" in text.upper() else "ok"), result
    except Exception:  # noqa: BLE001
        log.exception("AI image check failed")
        return None
