"""
AI Daily Digest summarizer.

Key resolution order:
  1. Group-scoped UserApiKey (user's own key tied to the group)
  2. Workspace-scoped UserApiKey (user's personal workspace key)
  3. Platform Gemini key (Telegizer-provided, token-limited)
"""
from __future__ import annotations
import logging
import re

_log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a community manager assistant. "
    "Summarize the following Telegram group messages into a concise daily digest. "
    "Focus on: main topics discussed, important announcements, questions asked, "
    "and overall community mood. Keep it under 300 words. Use plain text, no markdown."
)


def generate_ai_summary(
    messages: list[dict],  # [{"sender": str, "text": str}]
    provider: str,
    api_key: str,
    model: str | None,
    base_url: str | None = None,
) -> str | None:
    """Call the LLM and return a summary string, or None on failure."""
    if not messages or not api_key:
        return None

    conversation = "\n".join(
        f"[{m.get('sender', 'User')}]: {m.get('text', '')}"
        for m in messages[:500]
    )
    user_message = f"Here are today's messages:\n\n{conversation}"

    try:
        if provider == "anthropic":
            return _call_anthropic(api_key, model or "claude-haiku-4-5-20251001", user_message)
        else:
            # openai | openrouter | gemini | custom — all use OpenAI-compatible endpoint
            return _call_openai_compatible(api_key, model or "gpt-4o-mini", user_message, base_url)
    except Exception as exc:
        _log.warning("AI digest generation failed (provider=%s): %s", provider, exc)
        return None


def _call_openai_compatible(api_key: str, model: str, user_message: str, base_url: str | None) -> str | None:
    import urllib.request
    import json

    url = (base_url or "https://api.openai.com/v1") + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 500,
        "temperature": 0.4,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def _call_anthropic(api_key: str, model: str, user_message: str) -> str | None:
    import urllib.request
    import json

    payload = json.dumps({
        "model": model,
        "max_tokens": 500,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_message}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"].strip()


# ── Content Safety (1-G-02) ────────────────────────────────────────────────────

_HARD_BLOCK_PATTERNS = [
    re.compile(r"(how to.*(harm|hurt|attack|kill))", re.IGNORECASE),
    re.compile(r"(bomb|explosive|weapon).*(make|build|create)", re.IGNORECASE),
]
_DISCLAIMER_PATTERNS = {
    "medical":   (re.compile(r"(medical|health|diagnos|treatment|medication|dosage|prescri)", re.IGNORECASE),
                  "⚠️ This is general information only. Consult a healthcare professional."),
    "legal":     (re.compile(r"(legal|lawsuit|sue|court|attorney|lawyer)", re.IGNORECASE),
                  "⚠️ This is general information only. Consult a qualified lawyer."),
    "financial": (re.compile(r"(financial advice|invest|buy.*stock|portfolio|trading signal)", re.IGNORECASE),
                  "⚠️ This is general information only. Not financial advice."),
}


def content_safety_check(text: str) -> tuple[bool, str]:
    """
    Return (is_safe, modified_text).
    is_safe=False means the text must not be sent.
    modified_text may have a disclaimer appended for sensitive topics.
    """
    for pattern in _HARD_BLOCK_PATTERNS:
        if pattern.search(text):
            return False, ""

    for _topic, (pattern, disclaimer) in _DISCLAIMER_PATTERNS.items():
        if pattern.search(text):
            return True, text + f"\n\n{disclaimer}"

    return True, text


# ── AI Cost Tracking (1-G-04) ──────────────────────────────────────────────────

_MODEL_COSTS_PER_1K = {
    "gpt-3.5-turbo":              {"input": 0.0005, "output": 0.0015},
    "gpt-4o":                     {"input": 0.005,  "output": 0.015},
    "gpt-4o-mini":                {"input": 0.00015,"output": 0.0006},
    "gemini-2.0-flash":           {"input": 0.00035,"output": 0.00105},
    "gemini-1.5-flash":           {"input": 0.00035,"output": 0.00105},
    "claude-haiku-4-5-20251001":  {"input": 0.0008, "output": 0.004},
    "claude-sonnet-4-6":          {"input": 0.003,  "output": 0.015},
}


def track_ai_cost(user_id: int, model: str, input_tokens: int, output_tokens: int) -> None:
    """Increment the user's daily AI cost counter. Silently ignored on any error."""
    try:
        costs = _MODEL_COSTS_PER_1K.get(model, {"input": 0.001, "output": 0.002})
        cost = (input_tokens / 1000 * costs["input"]) + (output_tokens / 1000 * costs["output"])
        from ..models import db, User
        from decimal import Decimal
        from datetime import datetime, date
        user = User.query.get(user_id)
        if user is None:
            return
        today = date.today()
        reset_at = getattr(user, "ai_cost_reset_at", None)
        if reset_at is None or (hasattr(reset_at, "date") and reset_at.date() < today):
            user.ai_cost_usd_today = Decimal("0")
            user.ai_cost_reset_at = datetime.utcnow()
        user.ai_cost_usd_today = (user.ai_cost_usd_today or Decimal("0")) + Decimal(str(round(cost, 6)))
        db.session.commit()
    except Exception as exc:
        _log.debug("track_ai_cost error for user %s: %s", user_id, exc)


def _resolve_ai_key(user_id: int, group_id: str) -> dict | None:
    """
    Return { provider, api_key, model, base_url, source } or None.

    Priority:
      1. Group-scoped key for this specific group
      2. Any active group-scoped key owned by user (legacy)
      3. Workspace-scoped key (user's personal workspace key or platform Gemini)
    """
    from ..models import UserApiKey
    from ..utils.encryption import decrypt_value, DecryptionError
    from .ai_key_resolver import get_workspace_ai_key
    from ..models import User
    import logging as _log

    # 1. Group-scoped key
    group_key = UserApiKey.query.filter_by(
        user_id=user_id,
        scope="group",
        is_active=True,
    ).first()
    if group_key:
        try:
            raw = decrypt_value(group_key.api_key_encrypted)
        except DecryptionError:
            _log.getLogger(__name__).error("digest_ai: group key decryption failed for user %s", user_id)
            raw = None
        if raw:
            return {
                "provider": group_key.provider,
                "api_key": raw,
                "model": group_key.model_name,
                "base_url": group_key.base_url,
                "source": "group_key",
            }

    # 2 + 3. Workspace key (user's own or platform Gemini)
    user = User.query.get(user_id)
    if not user:
        return None
    from .ai_key_resolver import QuotaExceededError
    try:
        ws = get_workspace_ai_key(user)
    except QuotaExceededError as qe:
        _log.getLogger(__name__).warning("digest_ai: quota exceeded for user %s: %s", user_id, qe)
        return None
    if not ws.get("api_key"):
        return None
    ws["source"] = ws.get("source", "platform")
    return ws


def get_group_ai_summary(telegram_group_id: str) -> str | None:
    """
    Fetch buffered messages, resolve the best available AI key, generate a
    summary, log the result, and return the summary text (or None on failure).
    Must be called from within an active Flask app context.
    """
    try:
        from ..models import MessageBuffer, TelegramGroup, DigestLog, db
        from datetime import datetime, timedelta

        tg = TelegramGroup.query.filter_by(telegram_group_id=telegram_group_id).first()
        if not tg or not tg.owner_user_id:
            return None

        key_info = _resolve_ai_key(tg.owner_user_id, telegram_group_id)
        if not key_info:
            _log.info("No AI key available for group %s — skipping digest", telegram_group_id)
            return None

        cutoff = datetime.utcnow() - timedelta(hours=48)
        rows = (
            MessageBuffer.query
            .filter(
                MessageBuffer.telegram_group_id == telegram_group_id,
                MessageBuffer.created_at >= cutoff,
            )
            .order_by(MessageBuffer.created_at.asc())
            .limit(500)
            .all()
        )
        if not rows:
            return None

        messages = [{"sender": r.sender_name or "User", "text": r.message_text} for r in rows]
        summary = generate_ai_summary(
            messages=messages,
            provider=key_info["provider"],
            api_key=key_info["api_key"],
            model=key_info.get("model"),
            base_url=key_info.get("base_url"),
        )

        if summary:
            try:
                log = DigestLog(
                    group_id=telegram_group_id,
                    user_id=tg.owner_user_id,
                    content_preview=summary[:280],
                    provider=key_info["provider"],
                )
                db.session.add(log)
                db.session.commit()
            except Exception as log_exc:
                _log.warning("Failed to log digest for %s: %s", telegram_group_id, log_exc)

            # AI Activity (reporting only — best-effort)
            try:
                from ..ai_activity import log_ai_activity
                log_ai_activity(
                    "official", telegram_group_id, "analytics",
                    "Activity summary generated",
                    detail=summary[:300], source="ai_digest",
                )
            except Exception:
                pass

            # Record platform token usage (rough estimate: ~1 token per 4 chars)
            if key_info.get("source") == "platform":
                try:
                    from ..models import User as _User
                    from .ai_key_resolver import record_token_usage
                    _u = _User.query.get(tg.owner_user_id)
                    if _u:
                        estimated = len(summary) // 4 + sum(len(m["text"]) for m in messages) // 4
                        record_token_usage(_u, estimated)
                except Exception as _te:
                    _log.warning("Failed to record token usage: %s", _te)

        return summary

    except Exception as exc:
        _log.warning("get_group_ai_summary failed for %s: %s", telegram_group_id, exc)
        return None
