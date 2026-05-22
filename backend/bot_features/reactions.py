"""
Sentiment-based emoji reactions.

Reacts to messages based on their emotional tone. Rule-based (no AI) to
keep latency and cost at zero. A short per-user cooldown prevents the bot
from reacting to every rapid-fire message from the same person.
"""
import re
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# (group_id, user_id) → unix timestamp of last reaction sent
_last_reaction: dict = {}
_COOLDOWN_SECONDS = 15  # minimum gap between reactions to the same user


# Ordered by specificity — first match wins
SENTIMENT_RULES = [
    # Celebratory / praise
    (re.compile(
        r'\b(congrat(?:ulation|s)?|well done|amazing|awesome|excellent|fantastic|'
        r'brilliant|legend(?:ary)?|incredible|outstanding)\b', re.I), '🎉'),
    # Funny / humour
    (re.compile(
        r'\b(lol|lmao|haha+|hehe|rofl|funny|hilarious|😂|💀|🤣)\b', re.I), '😂'),
    # Hype / fire / energy
    (re.compile(
        r'\b(fire|lit|insane|unbelievable|mindblown|jaw.?drop|🔥|🤯|banger|goat)\b', re.I), '🔥'),
    # Appreciation / love / warmth
    (re.compile(
        r'\b(thank(?:s| you| u|ks?)|thx|ty\b|tysm|appreciate|grateful|gratitude|'
        r'love|lovely|beautiful|wonderful|sweet|kind(?:ness)?|heart(?:warming)?)\b', re.I), '❤️'),
    # Agreement / correct
    (re.compile(
        r'\b(exactly|correct|right(?:\s+on)?|true|absolutely|100%|agree(?:d)?|'
        r'spot on|nailed it|perfect|well said|couldn\'t agree more)\b', re.I), '👍'),
    # Sad / sympathy / loss
    (re.compile(
        r'\b(sorry(?: to hear| for your)?|condolence|rip\b|so sad|unfortunately|'
        r'miss (?:you|him|her|them)|(?:my )?(?:thoughts|prayers)|deepest sympathies)\b', re.I), '🫂'),
]


def detect_sentiment_reaction(text: str) -> Optional[str]:
    """Return an emoji if the text has a clear detectable sentiment, else None."""
    if not text or not text.strip():
        return None
    # Skip long messages — sentiment is too diluted to react reliably
    if len(text.split()) > 50:
        return None
    for pattern, emoji in SENTIMENT_RULES:
        if pattern.search(text):
            return emoji
    return None


def should_react(group_id, user_id) -> bool:
    key = (str(group_id), str(user_id))
    last = _last_reaction.get(key, 0)
    return (time.time() - last) >= _COOLDOWN_SECONDS


def mark_reacted(group_id, user_id):
    _last_reaction[(str(group_id), str(user_id))] = time.time()


async def send_reaction(bot, chat_id: int, message_id: int, emoji: str) -> bool:
    """Send an emoji reaction to a message. Returns True on success."""
    try:
        from telegram import ReactionTypeEmoji
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
            is_big=False,
        )
        return True
    except Exception as e:
        logger.debug(f"Reaction send failed (chat={chat_id}, msg={message_id}, emoji={emoji}): {e}")
        return False
