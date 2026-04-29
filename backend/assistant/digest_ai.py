"""
AI Daily Digest summarizer.

Uses the group owner's UserApiKey (OpenAI-compatible or Anthropic) to
generate a plain-text summary of buffered messages.  Zero cost to us —
the API call is billed to the admin's own key.
"""
from __future__ import annotations
import logging

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

    # Build conversation text
    conversation = "\n".join(
        f"[{m.get('sender', 'User')}]: {m.get('text', '')}"
        for m in messages[:500]  # cap at 500 messages
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
    import urllib.error
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


def get_group_ai_summary(telegram_group_id: str) -> str | None:
    """
    Fetch buffered messages + owner API key, generate and return an AI summary.
    Must be called from within an active Flask app context.
    """
    try:
        from ..models import MessageBuffer, UserApiKey, TelegramGroup
        from ..utils.encryption import decrypt_value

        tg = TelegramGroup.query.filter_by(telegram_group_id=telegram_group_id).first()
        if not tg or not tg.owner_user_id:
            return None

        # AI digest must be enabled in group settings
        if not (tg.settings or {}).get("assistant", {}).get("ai_digest_enabled"):
            return None

        # Get the owner's API key for this group (or any key they have)
        api_key_row = UserApiKey.query.filter_by(
            user_id=tg.owner_user_id,
            is_active=True,
        ).first()
        if not api_key_row:
            return None

        raw_key = decrypt_value(api_key_row.api_key_encrypted)
        if not raw_key:
            return None

        # Fetch up to 500 buffered messages from last 48h
        from datetime import datetime, timedelta
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
        return generate_ai_summary(
            messages=messages,
            provider=api_key_row.provider,
            api_key=raw_key,
            model=api_key_row.model_name,
            base_url=api_key_row.base_url,
        )
    except Exception as exc:
        _log.warning("get_group_ai_summary failed for %s: %s", telegram_group_id, exc)
        return None
