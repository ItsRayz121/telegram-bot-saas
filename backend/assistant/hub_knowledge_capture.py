"""
Auto-knowledge capture — converts Telegram messages into HubKnowledgeCards.

auto_capture_message(message_text, bot_id, user_id) -> bool
  Uses GPT to decide if the message is "worthy" (useful FAQ/answer/fact),
  extracts title + content + tags, deduplicates, saves the card, and
  attempts to embed it for semantic search.

embed_card(card, key_config) -> None
  Compute and store JSON-encoded embedding on an existing card. Best-effort.

semantic_search_cards(query, bot_id, user_id, key_info, limit) -> list[HubKnowledgeCard]
  Embed query and rank cards by cosine similarity.
  Falls back to ILIKE keyword search when embeddings are unavailable.
"""
import json
import logging
import math
import uuid as _uuid_mod

_log = logging.getLogger(__name__)

_PARSE_SYSTEM = """\
You are a knowledge extraction assistant for a Telegram community bot.

Given a message from a Telegram group, decide whether it contains reusable knowledge
worth saving as a FAQ entry (an explanation, answer, instruction, policy, or factual statement).

Return ONLY valid JSON — no prose before or after:
{
  "worthy": true | false,
  "title": "Short FAQ-style headline (max 80 chars) or null",
  "content": "Clean, helpful answer text (max 500 chars) or null",
  "tags": ["tag1", "tag2"]
}

RULES
- worthy=true only for clear, reusable facts/answers:
    ✓ "To verify your wallet, go to Settings > Verify and connect via MetaMask"
    ✓ "The airdrop ends June 30th at midnight UTC"
    ✓ "Minimum stake is 500 tokens"
- worthy=false for: greetings, small talk, reactions, one-word replies, vague questions
- title: concise FAQ headline — "How to verify wallet", "Airdrop end date"
- content: clean, standalone answer text ready to show in a Telegram reply
- tags: 2–4 lowercase keywords relevant to this card
"""


def auto_capture_message(message_text: str, bot_id: str, user_id: int) -> bool:
    """
    Parse a message and create a HubKnowledgeCard if it contains worthy content.
    Returns True if a new card was created.
    """
    if not message_text or len(message_text.strip()) < 20:
        return False

    try:
        from ..assistant.hub_models import HubKnowledgeCard
        from ..assistant.hub_crypto import _enc, _dec
        from ..assistant.ai_key_resolver import get_workspace_ai_key, QuotaExceededError
        from ..models import User, db
        from openai import OpenAI

        user = User.query.get(user_id)
        if not user:
            return False

        try:
            key_config = get_workspace_ai_key(user)
        except QuotaExceededError:
            return False
        if not key_config.get("api_key"):
            return False

        client_kwargs = {"api_key": key_config["api_key"]}
        if key_config.get("base_url"):
            client_kwargs["base_url"] = key_config["base_url"]
        client = OpenAI(**client_kwargs)
        model = key_config.get("model") or "gpt-4o-mini"

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _PARSE_SYSTEM},
                {"role": "user", "content": message_text[:1500]},
            ],
            max_tokens=300,
            temperature=0.1,
        )

        raw = resp.choices[0].message.content.strip()
        parsed = json.loads(raw)

        if not parsed.get("worthy"):
            return False

        title = (parsed.get("title") or "").strip()
        content = (parsed.get("content") or "").strip()
        tags = [str(t).lower() for t in (parsed.get("tags") or [])[:5]]

        if not title or not content:
            return False

        # Dedup: skip if a card with the same title already exists
        existing = HubKnowledgeCard.query.filter_by(bot_id=bot_id, user_id=user_id).all()
        for card in existing:
            dec_title = _dec(card.title) or ""
            if dec_title.lower().strip() == title.lower().strip():
                _log.debug("hub_capture: duplicate title, skipping: %r", title)
                return False

        new_card = HubKnowledgeCard(
            id=str(_uuid_mod.uuid4()),
            bot_id=bot_id,
            user_id=user_id,
            title=_enc(title[:100]),
            content=_enc(content[:2000]),
            tags=tags,
            source="auto_capture",
        )
        db.session.add(new_card)
        db.session.commit()

        # Embed the card (best-effort — never block on failure)
        embed_card(new_card, key_config)

        _log.info("hub_capture: new card bot=%s title=%r", bot_id, title)
        return True

    except Exception as exc:
        _log.warning("hub_capture: auto_capture_message failed: %s", exc)
        return False


def embed_card(card, key_config: dict) -> None:
    """Compute and store a JSON-encoded embedding on a HubKnowledgeCard. Best-effort."""
    try:
        from ..assistant.embeddings import embed_text
        from ..assistant.hub_crypto import _dec
        from ..models import db

        text = f"{_dec(card.title) or ''}\n{_dec(card.content) or ''}"[:4000]
        vec = embed_text(text, key_config)
        if vec is not None:
            card.embedding = json.dumps(vec)
            db.session.commit()
    except Exception as exc:
        _log.debug("hub_capture: embed_card failed: %s", exc)


def semantic_search_cards(
    query: str,
    bot_id: str,
    user_id: int,
    key_info: dict,
    limit: int = 3,
):
    """
    Return the most relevant HubKnowledgeCards for a query.

    1. Embed query → cosine similarity against stored card embeddings
    2. If embeddings missing or unavailable → ILIKE keyword fallback on title/content
    """
    from ..assistant.hub_models import HubKnowledgeCard
    from ..assistant.hub_crypto import _dec
    from ..assistant.embeddings import embed_text

    all_cards = HubKnowledgeCard.query.filter_by(bot_id=bot_id, user_id=user_id).all()
    if not all_cards:
        return []

    # Try semantic path
    cards_with_embeddings = [c for c in all_cards if c.embedding]
    if cards_with_embeddings and key_info.get("api_key"):
        try:
            query_vec = embed_text(query, key_info)
            if query_vec:
                scored = []
                for card in cards_with_embeddings:
                    card_vec = json.loads(card.embedding)
                    score = _cosine(query_vec, card_vec)
                    scored.append((score, card))
                scored.sort(key=lambda x: x[0], reverse=True)
                # Return cards above a similarity threshold
                results = [c for score, c in scored if score > 0.55][:limit]
                if results:
                    return results
        except Exception as exc:
            _log.debug("hub_capture: semantic search failed, using keyword fallback: %s", exc)

    # Keyword fallback — search decrypted title and tags
    query_lower = query.lower()
    matched = []
    for card in all_cards:
        title = (_dec(card.title) or "").lower()
        tags = [t.lower() for t in (card.tags or [])]
        if (query_lower in title or title in query_lower
                or any(t in query_lower or query_lower in t for t in tags)):
            matched.append(card)
    return matched[:limit]


def _cosine(a: list, b: list) -> float:
    """Cosine similarity between two float vectors."""
    try:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
    except Exception:
        return 0.0
