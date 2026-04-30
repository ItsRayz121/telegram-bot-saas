"""
AI Daily Digest summarizer.

Key resolution order:
  1. Group-scoped UserApiKey (user's own key tied to the group)
  2. Workspace-scoped UserApiKey (user's personal workspace key)
  3. Platform Gemini key (Telegizer-provided, token-limited)
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


def _resolve_ai_key(user_id: int, group_id: str) -> dict | None:
    """
    Return { provider, api_key, model, base_url, source } or None.

    Priority:
      1. Group-scoped key for this specific group
      2. Any active group-scoped key owned by user (legacy)
      3. Workspace-scoped key (user's personal workspace key or platform Gemini)
    """
    from ..models import UserApiKey
    from ..utils.encryption import decrypt_value
    from .ai_key_resolver import get_workspace_ai_key
    from ..models import User

    # 1. Group-scoped key
    group_key = UserApiKey.query.filter_by(
        user_id=user_id,
        scope="group",
        is_active=True,
    ).first()
    if group_key:
        raw = decrypt_value(group_key.api_key_encrypted)
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
    ws = get_workspace_ai_key(user)
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

        return summary

    except Exception as exc:
        _log.warning("get_group_ai_summary failed for %s: %s", telegram_group_id, exc)
        return None
