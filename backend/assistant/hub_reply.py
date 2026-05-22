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
    flask_app=None,
) -> bool:
    """
    Synchronous wrapper safe to call from Flask routes or Celery tasks.
    Returns True if a reply was sent.

    flask_app is optional — omit (or pass None) when already inside an app
    context (e.g. from a Flask route handler).  Pass the app object when
    calling from a background thread or Celery task.
    """
    if flask_app is not None:
        with flask_app.app_context():
            return _handle(bot_token, bot_username, message_text,
                           chat_id, message_id, bot_id, user_id,
                           flask_app=flask_app)
    return _handle(bot_token, bot_username, message_text,
                   chat_id, message_id, bot_id, user_id,
                   flask_app=None)


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

def _handle(bot_token, bot_username, message_text, chat_id, message_id, bot_id, user_id,
            flask_app=None, sender_id=None, sender_username=None) -> bool:
    import redis as _redis
    import requests as _req
    from ..config import Config
    from ..assistant.hub_models import HubKnowledgeCard
    from ..assistant.hub_crypto import _dec
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

    # ── Load bot community reply settings ─────────────────────────────────────
    from ..assistant.hub_models import HubBotSettings as _HubBotSettings
    _bot_settings = _HubBotSettings.query.filter_by(bot_id=bot_id).first()
    _reply_sensitivity = (_bot_settings.reply_sensitivity or "medium") if _bot_settings else "medium"
    _tone = (_bot_settings.tone or "friendly") if _bot_settings else "friendly"
    _escalation_contact = (_bot_settings.escalation_contact) if _bot_settings else None

    # ── Smart pre-filter: sentiment-aware short message handler ───────────────
    pre_reply = _pre_filter(query, bot_token, chat_id, message_id, sensitivity=_reply_sensitivity)
    if pre_reply == "__SILENCE__":
        return False   # human-to-human chat — bot stays quiet
    if pre_reply:
        _send_reply(bot_token, chat_id, message_id, pre_reply, parse_mode="HTML")
        return True

    # ── Knowledge card match (keyword first, semantic fallback) ───────────────
    cards = HubKnowledgeCard.query.filter_by(bot_id=bot_id, user_id=user_id).all()
    matched_card = None
    query_lower = query.lower()

    for card in cards:
        title = (_dec(card.title) or "").lower()
        tags = [t.lower() for t in (card.tags or [])]
        if (query_lower == title
                or query_lower in title
                or title in query_lower
                or any(t in query_lower or query_lower in t for t in tags)):
            matched_card = card
            break

    # Semantic fallback when keyword match fails (reuses already-loaded cards list)
    if not matched_card and cards:
        try:
            from .hub_knowledge_capture import semantic_search_cards
            from .ai_key_resolver import get_workspace_ai_key, QuotaExceededError
            from ..models import User as _User
            _u = _User.query.get(user_id)
            if _u:
                try:
                    _kc = get_workspace_ai_key(_u)
                    sem_results = semantic_search_cards(
                        query, bot_id, user_id, _kc, limit=1, preloaded_cards=cards
                    )
                    if sem_results:
                        matched_card = sem_results[0]
                except QuotaExceededError:
                    pass
        except Exception as _se:
            _log.debug("hub_reply: semantic search error: %s", _se)

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
            reply_text = _gpt_answer(query, bot_id, user_id, tone=_tone)
        else:
            # Attempt global escalation before sending generic reply
            if flask_app:
                try:
                    from ..models import Group
                    from ..bot_features.escalation import trigger_escalation as _esc
                    import asyncio

                    grp = Group.query.filter_by(telegram_group_id=str(chat_id)).first()
                    esc_settings = (grp.settings if grp else {}).get("escalation", {})
                    if esc_settings.get("enabled") and "ai_kb" in esc_settings.get("types", []):
                        ctx = {
                            "group_name": getattr(grp, "group_name", str(chat_id)) if grp else str(chat_id),
                            "user_id": sender_id,
                            "username": sender_username or "",
                        }
                        loop = asyncio.new_event_loop()
                        import telegram as _tg
                        _bot_obj = _tg.Bot(token=bot_token)
                        loop.run_until_complete(_esc(
                            bot=_bot_obj,
                            group_settings=grp.settings if grp else {},
                            issue_type="ai_kb",
                            original_content=query,
                            context_data=ctx,
                            app=flask_app,
                            group_id=grp.id if grp else None,
                            telegram_group_id=str(chat_id),
                        ))
                        loop.close()
                        # Send ack instead of generic reply
                        _req.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": "Your question has been forwarded to an admin. They'll respond shortly.",
                                "reply_to_message_id": message_id,
                            },
                            timeout=8,
                        )
                        return True
                except Exception:
                    pass  # fall through to generic reply

            # Notify escalation_contact admin via DM if configured
            if _escalation_contact:
                try:
                    import requests as _req2
                    _req2.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": _escalation_contact,
                            "text": (
                                f"❓ <b>Unanswered question in group {chat_id}</b>\n\n"
                                f"{query}"
                            ),
                            "parse_mode": "HTML",
                        },
                        timeout=8,
                    )
                except Exception:
                    pass

            reply_text = (
                "I don't have a knowledge card for that. "
                "Ask the group admin to add one in Hub Settings → Knowledge."
            )

    if not reply_text:
        return False

    # ── Send reply ─────────────────────────────────────────────────────────────
    sent = _send_reply(bot_token, chat_id, message_id, reply_text, parse_mode="HTML")
    if sent:
        _log.info("hub_reply: replied bot=%s group=%s matched=%s",
                  bot_id, chat_id, bool(matched_card))
    return sent


def _gpt_answer(query: str, bot_id: str, user_id: int, tone: str = "friendly") -> str | None:
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

        from .handlers._prompts import HUB_COMMUNITY_REPLY_SYSTEM
        knowledge_context = "\n".join(context_lines) if context_lines else "No specific workspace context available."
        system = HUB_COMMUNITY_REPLY_SYSTEM.format(knowledge_context=knowledge_context)
        if personality:
            system += f"\n\nBot personality note from owner: {personality}"
        _tone_map = {
            "professional": "Maintain a formal, professional tone. Be precise and avoid casual language.",
            "neutral": "Use a neutral, balanced tone — neither too casual nor too formal.",
            "friendly": "Be warm, approachable, and conversational.",
        }
        tone_note = _tone_map.get(tone, _tone_map["friendly"])
        system += f"\n\nTone instruction: {tone_note}"

        resp = _openai_client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
            max_tokens=500,
            temperature=0.6,
        )
        if _key_source == "platform":
            tokens_used = resp.usage.total_tokens if resp.usage else 0
            record_token_usage(user, tokens_used)
        return resp.choices[0].message.content.strip()[:4000]
    except Exception as exc:
        _log.warning("hub_reply: GPT fallback failed: %s", exc)
        return None


# ── Send helper ────────────────────────────────────────────────────────────────

def _send_reply(bot_token: str, chat_id: int, message_id: int,
                text: str, parse_mode: str = "HTML") -> bool:
    import requests as _req
    try:
        _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_to_message_id": message_id,
            },
            timeout=10,
        )
        return True
    except Exception as exc:
        _log.warning("hub_reply: send failed: %s", exc)
        return False


# ── Smart pre-filter ───────────────────────────────────────────────────────────
# Returns:
#   "__SILENCE__"  → human-to-human chat, bot stays quiet
#   str            → ready-to-send reply (greeting or clarification ask)
#   None           → no match, proceed to normal pipeline

import random as _random
import re as _re

_GREETINGS = {
    "hi", "hey", "hello", "helo", "hy", "heya",
    "gm", "good morning", "good afternoon", "good evening", "good night",
    "morning", "evening", "afternoon", "yo", "sup", "howdy",
    "salam", "assalam", "assalamu alaikum", "assalamualaikum",
}

_GREETING_REPLIES = [
    "Hey! 👋 Happy to help — what's on your mind?",
    "Hi there! 😊 What can I do for you today?",
    "Hello! Feel free to ask anything — I'm here to help.",
    "Good to see you! What would you like to know?",
    "Hey! What can I help you with?",
    "Hi! Ask away — I'll do my best to help. 🙌",
]

_CLARIFICATION_REPLIES = [
    "Could you share a bit more detail? I want to make sure I give you the right answer.",
    "Happy to help — could you tell me a little more about what you're looking for?",
    "I think I need a bit more context to answer that properly. Could you explain further?",
    "Sure, I can help with that! What specifically would you like to know?",
    "Could you describe the issue in a little more detail? That way I can give you a proper answer.",
]

# Single-word fragments too vague to answer usefully
_FRAGMENT_KEYWORDS = {
    "wallet", "reward", "rewards", "airdrop", "help", "issue",
    "problem", "support", "verify", "verification", "link", "links",
    "join", "error", "bug", "not working", "broken", "stuck",
}

# Exact short phrases that are clearly human-to-human
_HUMAN_CHAT_EXACT = {
    "ok", "okay", "k", "lol", "haha", "hehe", "nice", "cool",
    "thanks", "thank you", "ty", "thx", "np", "no problem",
    "sure", "yeah", "yep", "nope", "nah", "gg", "wb",
}


def _pre_filter(query: str, bot_token: str, chat_id: int, message_id: int,
                sensitivity: str = "medium"):
    """
    Sentiment-aware pre-filter before the knowledge card / AI pipeline.

    sensitivity:
      "low"    → never silence; reply to everything
      "medium" → default: silence human-chat, clarify vague fragments
      "high"   → also clarify 1-3 word messages not in GREETINGS or HUMAN_CHAT_EXACT

    1. Greeting → engage warmly (always)
    2. Known human-chat phrase → stay silent (unless sensitivity=low)
    3. Single vague fragment keyword → ask for more detail (medium+)
    4. Short unknown message → ask for more detail (high only)
    5. Otherwise → None (proceed to normal pipeline)
    """
    text = query.strip().lower()
    clean = _re.sub(r"[^\w\s]", "", text).strip()

    # 1. Greeting — always engage regardless of sensitivity
    if clean in _GREETINGS or any(clean.startswith(g) for g in _GREETINGS if len(g) > 2):
        return _random.choice(_GREETING_REPLIES)

    # 2. Human-to-human short phrases
    if clean in _HUMAN_CHAT_EXACT:
        if sensitivity == "low":
            return None  # don't silence — pass to pipeline
        return "__SILENCE__"

    words = clean.split()

    # 3. Vague fragment — ask for detail (medium and high)
    if sensitivity != "low" and len(words) <= 2 and clean in _FRAGMENT_KEYWORDS:
        return _random.choice(_CLARIFICATION_REPLIES)

    # 4. High sensitivity — ask for detail on any short unclear message
    if sensitivity == "high" and len(words) <= 3 and clean not in _GREETINGS:
        return _random.choice(_CLARIFICATION_REPLIES)

    # 5. Proceed normally
    return None
