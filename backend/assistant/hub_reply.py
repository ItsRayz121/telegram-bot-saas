"""
Assistant Hub — @mention reply engine.

handle_mention(bot_token, bot_username, message_text, chat_id, message_id,
               bot_id, user_id, flask_app):
  1. Rate-check: 5 replies per group per hour (Redis counter)
  2. Strip @username prefix, extract query
  3. Keyword/tag match against HubKnowledgeCard for the bot
  4. If match  → reply with card content, increment use_count
  5. If no match + Enterprise → GPT-4o-mini with memory context
  6. If no match + Free/Pro → polite fallback message

Called by:
  - official_bot.py  on_message handler (PTB)
  - hub.py /webhook/<bot_id> Flask route (custom bots)
"""
import logging
import os

_log = logging.getLogger(__name__)

_RATE_LIMIT = 5          # replies per group per hour
_RATE_WINDOW = 3600      # seconds


def handle_mention(
    bot_token: str,
    bot_username: str,
    message_text: str,
    chat_id: int,
    message_id: int,
    bot_id: str,
    user_id: int,
    flask_app,
) -> bool:
    """
    Synchronous wrapper safe to call from Flask routes or Celery tasks.
    Returns True if a reply was sent.
    """
    with flask_app.app_context():
        return _handle(bot_token, bot_username, message_text,
                       chat_id, message_id, bot_id, user_id)


async def handle_mention_async(
    bot_token: str,
    bot_username: str,
    message_text: str,
    chat_id: int,
    message_id: int,
    bot_id: str,
    user_id: int,
    flask_app,
) -> bool:
    """
    Async variant for use inside PTB handlers (official bot).
    Runs the synchronous DB work in a thread executor to avoid blocking the event loop.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        handle_mention,
        bot_token, bot_username, message_text,
        chat_id, message_id, bot_id, user_id, flask_app,
    )


# ── Internal ───────────────────────────────────────────────────────────────────

def _handle(bot_token, bot_username, message_text, chat_id, message_id, bot_id, user_id) -> bool:
    import redis as _redis
    import requests as _req
    from ..config import Config
    from ..assistant.hub_models import HubKnowledgeCard
    from ..assistant.hub_crypto import _dec, _enc
    from ..models import User

    redis_url = os.environ.get("REDIS_URL", Config.REDIS_URL)
    r = _redis.from_url(redis_url, decode_responses=True)

    # ── Rate limit: 5 replies per group per hour ──────────────────────────────
    from datetime import datetime
    hour_key = f"assistant:reply_rate:{bot_id}:{chat_id}:{datetime.utcnow().strftime('%Y%m%d%H')}"
    current = r.incr(hour_key)
    if current == 1:
        r.expire(hour_key, _RATE_WINDOW)
    if current > _RATE_LIMIT:
        _log.debug("hub_reply: rate limit hit bot=%s group=%s", bot_id, chat_id)
        return False

    # ── Extract query (strip @username mention) ────────────────────────────────
    query = message_text or ""
    if bot_username:
        query = query.replace(f"@{bot_username}", "").strip()
    if not query:
        return False

    # ── Knowledge card match ───────────────────────────────────────────────────
    cards = HubKnowledgeCard.query.filter_by(bot_id=bot_id, user_id=user_id).all()
    matched_card = None
    query_lower = query.lower()

    for card in cards:
        title = (_dec(card.title) or "").lower()
        tags = [t.lower() for t in (card.tags or [])]
        # Exact title match, or title contains query, or any tag matches
        if (query_lower == title
                or query_lower in title
                or title in query_lower
                or any(t in query_lower or query_lower in t for t in tags)):
            matched_card = card
            break

    reply_text = None

    if matched_card:
        content = _dec(matched_card.content) or ""
        reply_text = content[:4000]
        # Increment use count
        try:
            matched_card.use_count = (matched_card.use_count or 0) + 1
            from ..models import db
            db.session.commit()
        except Exception:
            pass

    else:
        # No card match — check plan
        user = User.query.get(user_id)
        plan = (user.subscription_tier or "free") if user else "free"

        if plan == "enterprise":
            reply_text = _gpt_answer(query, bot_id, user_id)
        else:
            reply_text = (
                "I don't have a knowledge card for that. "
                "Ask the group admin to add one in Hub Settings → Knowledge."
            )

    if not reply_text:
        return False

    # ── Send reply ─────────────────────────────────────────────────────────────
    try:
        _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": reply_text,
                "parse_mode": "Markdown",
                "reply_to_message_id": message_id,
            },
            timeout=10,
        )
        _log.info("hub_reply: replied bot=%s group=%s matched=%s",
                  bot_id, chat_id, bool(matched_card))
        return True
    except Exception as exc:
        _log.warning("hub_reply: send failed bot=%s group=%s: %s", bot_id, chat_id, exc)
        return False


def _gpt_answer(query: str, bot_id: str, user_id: int) -> str | None:
    """Enterprise plan: answer via GPT-4o-mini with memory context."""
    try:
        from openai import OpenAI
        from ..assistant.hub_models import (
            HubBotSettings, HubMemoryGlobal, HubMemoryPerson, HubMemoryProject,
        )
        from ..assistant.hub_crypto import _dec
        from .ai_key_resolver import get_workspace_ai_key, QuotaExceededError, record_token_usage
        from ..models import User

        user = User.query.get(user_id)
        if not user:
            return None
        try:
            key_config = get_workspace_ai_key(user)
        except QuotaExceededError:
            return None
        if not key_config.get("api_key"):
            return None

        client_kwargs = {"api_key": key_config["api_key"]}
        if key_config.get("base_url"):
            client_kwargs["base_url"] = key_config["base_url"]
        _openai_client = OpenAI(**client_kwargs)
        _model = key_config.get("model") or "gpt-4o-mini"
        _key_source = key_config.get("source", "unknown")

        # Build system prompt from bot personality + memory
        settings = HubBotSettings.query.filter_by(bot_id=bot_id).first()
        personality = (settings.ai_personality_note or "") if settings else ""

        mem = HubMemoryGlobal.query.filter_by(user_id=user_id).first()
        context_lines = []
        if mem:
            if mem.company_name:
                context_lines.append(f"Company: {mem.company_name}")
            if mem.role:
                context_lines.append(f"Role: {mem.role}")
            if mem.free_notes:
                context_lines.append(f"Context: {_dec(mem.free_notes)}")

        people = HubMemoryPerson.query.filter_by(user_id=user_id).limit(10).all()
        if people:
            names = ", ".join(p.name for p in people)
            context_lines.append(f"Key people: {names}")

        projects = HubMemoryProject.query.filter_by(user_id=user_id).limit(5).all()
        if projects:
            proj_names = ", ".join(p.name for p in projects)
            context_lines.append(f"Active projects: {proj_names}")

        system = "You are a helpful Telegram group assistant."
        if personality:
            system += f" {personality}"
        if context_lines:
            system += "\n\nContext about the workspace:\n" + "\n".join(context_lines)

        resp = _openai_client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
            max_tokens=400,
            temperature=0.4,
        )
        if _key_source == "platform":
            tokens_used = resp.usage.total_tokens if resp.usage else 0
            record_token_usage(user, tokens_used)
        return resp.choices[0].message.content.strip()[:4000]
    except Exception as exc:
        _log.warning("hub_reply: GPT fallback failed: %s", exc)
        return None
