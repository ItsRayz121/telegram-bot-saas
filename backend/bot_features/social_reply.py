"""
Social / appreciation reply engine.

Detects positive social messages (thanks, appreciation, praise) and responds
naturally without calling the AI API — static personality-aware response pools
keep latency and cost at zero.

Anti-spam: 5-minute per-user per-group cooldown tracked in memory.
"""
import logging
import random
import re
import time

logger = logging.getLogger(__name__)

# ── Cooldown tracker ──────────────────────────────────────────────────────────
# Key: (group_id, user_id)  Value: unix timestamp of last social reply
_last_social_reply: dict[tuple, float] = {}
_DEFAULT_COOLDOWN = 300  # 5 minutes


def _on_cooldown(group_id, user_id, cooldown_seconds: int) -> bool:
    key = (str(group_id), str(user_id))
    last = _last_social_reply.get(key, 0)
    return (time.time() - last) < cooldown_seconds


def _mark_replied(group_id, user_id):
    _last_social_reply[(str(group_id), str(user_id))] = time.time()


# ── Appreciation detection ────────────────────────────────────────────────────

_APPRECIATION_PATTERNS = [
    r"\b(thank(?:s| you| u|ks?)|thx|ty|tysm|tyvm|tq|thq)\b",
    r"\b(appreciat(?:e|ed|ion)|grateful|gratitude)\b",
    r"\b(helpful|helped|that helped|help(?:ed)? me)\b",
    r"\b(great (?:bot|help|support|answer|reply|job)|good bot|nice bot|awesome bot)\b",
    r"\b(solved|problem solved|fixed|worked|worked (?:for me|out))\b",
    r"\b(exactly what i needed|what i (?:needed|was looking for))\b",
    r"\b(love this|love the bot|amazing(?: bot| help| support)?|fantastic)\b",
    r"\b(well done|nicely done|good (?:job|work|one)|great work)\b",
    r"\b(perfect(?: answer| reply| response)?|spot on|nailed it)\b",
    r"\b(got it[,!.]? (?:thanks|thank you|thx)|thanks for (?:the )?(?:help|reply|info|answer|clarification))\b",
    r"\b(much appreciated|highly appreciate|really appreciate)\b",
    r"\b(you(?:'re| are) (?:the best|amazing|awesome|great|helpful))\b",
    r"\brespect\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _APPRECIATION_PATTERNS]

_MAX_WORDS_FOR_APPRECIATION = 20  # long messages likely contain "thanks" in passing


def is_appreciation(text: str) -> bool:
    """Return True if the text is a short, clear appreciation/thank-you message."""
    if not text or not text.strip():
        return False
    words = text.split()
    if len(words) > _MAX_WORDS_FOR_APPRECIATION:
        return False
    # Must match at least one appreciation pattern
    return any(p.search(text) for p in _COMPILED)


# ── Response pools by personality ─────────────────────────────────────────────

_RESPONSES: dict[str, list[str]] = {
    "professional_support": [
        "You're welcome. Feel free to reach out if you need anything else.",
        "Happy to help. Don't hesitate to ask if you have more questions.",
        "Glad I could assist. I'm here whenever you need support.",
        "Of course. Let me know anytime you need further assistance.",
    ],
    "friendly_community": [
        "You're so welcome! 😊 Always here if you need anything!",
        "Happy to help! 🙌 Don't hesitate to ask anytime!",
        "Glad that helped! Feel free to ask more questions anytime 💙",
        "Anytime! That's what I'm here for 😄 Ask away whenever!",
    ],
    "enterprise_assistant": [
        "You're welcome.",
        "Glad to be of service. Please don't hesitate to follow up.",
        "Of course. Feel free to reach out with any further queries.",
        "Happy to assist. I'm available anytime you need information.",
    ],
    "web3_moderator": [
        "Anytime! 🚀 Keep building fren!",
        "No problem! Feel free to ask anytime — we're here for the community.",
        "LFG! 🙌 Happy to help. Drop more questions whenever.",
        "Always! That's what the community is for 💎",
    ],
    "gaming_community": [
        "No problem! 🎮 Hit me up anytime!",
        "Anytime! Keep the questions coming 🚀",
        "GG! Let me know if you need anything else!",
        "Always here to help! 🎯 Ask away whenever!",
    ],
    "technical_assistant": [
        "You're welcome. Feel free to open more questions anytime.",
        "Glad the information was helpful. Ask anytime.",
        "Happy to assist. Let me know if you need clarification on anything.",
        "Of course. I'm here for any technical questions you may have.",
    ],
    "creator_community": [
        "You're welcome! 💙 Keep creating!",
        "Happy to help! Don't hesitate to ask anytime 🌟",
        "Glad that helped! Keep going 🎨",
        "Anytime! That's what I'm here for — supporting creators like you 💙",
    ],
}

_FALLBACK_RESPONSES = [
    "You're welcome! Feel free to ask if you need anything else.",
    "Happy to help. Don't hesitate to reach out anytime.",
    "Glad I could assist.",
]


def get_response(personality_id: str) -> str:
    pool = _RESPONSES.get(personality_id, _FALLBACK_RESPONSES)
    return random.choice(pool)


# ── Reaction emojis by personality ────────────────────────────────────────────

_REACTION_EMOJIS: dict[str, list[str]] = {
    "professional_support": ["👍"],
    "friendly_community":   ["❤️", "🙌", "😊", "👍"],
    "enterprise_assistant": ["👍"],
    "web3_moderator":       ["🚀", "🔥", "👍"],
    "gaming_community":     ["🎮", "🔥", "👍"],
    "technical_assistant":  ["👍"],
    "creator_community":    ["❤️", "🌟", "👍"],
}

_FALLBACK_EMOJIS = ["👍"]


def get_reaction_emoji(personality_id: str) -> str:
    pool = _REACTION_EMOJIS.get(personality_id, _FALLBACK_EMOJIS)
    return random.choice(pool)


# ── Main handler ──────────────────────────────────────────────────────────────

async def maybe_handle_social_reply(bot, message, group_id, user_id,
                                    social_settings: dict, kb_settings: dict):
    """
    Check if the message is an appreciation/social message and respond if:
    - social_replies.enabled is True
    - user is not a bot
    - not on cooldown

    Sends an emoji reaction (if permissions allow) and/or a text reply.
    """
    if not social_settings.get("enabled", False):
        return False

    sender = message.from_user
    if not sender or sender.is_bot:
        return False

    text = (message.text or "").strip()
    if not is_appreciation(text):
        return False

    cooldown = int(social_settings.get("cooldown_minutes", 5)) * 60
    if _on_cooldown(group_id, user_id, cooldown):
        logger.debug(f"social_reply: on cooldown for user {user_id} in group {group_id}")
        return False

    personality = kb_settings.get("personality", "professional_support")
    mode = social_settings.get("mode", "friendly")

    # ── Reaction ──────────────────────────────────────────────────────────────
    if social_settings.get("react_to_appreciation", True):
        emoji = get_reaction_emoji(personality)
        # Minimal/professional modes use only 👍
        if mode in ("minimal", "professional"):
            emoji = "👍"
        try:
            from telegram import ReactionTypeEmoji
            await bot.set_message_reaction(
                chat_id=message.chat_id,
                message_id=message.message_id,
                reaction=[ReactionTypeEmoji(emoji=emoji)],
            )
        except Exception as exc:
            logger.debug(f"social_reply: reaction failed (permissions?): {exc}")

    # ── Text reply ────────────────────────────────────────────────────────────
    if social_settings.get("reply_to_appreciation", True):
        response = get_response(personality)

        # Mode overrides — minimal just reacts, no text
        if mode == "minimal":
            _mark_replied(group_id, user_id)
            return True

        # Professional/enterprise strip casual emoji from response
        if mode in ("professional",):
            response = re.sub(r"[\U0001F300-\U0001FFFF]", "", response).strip()

        try:
            await message.reply_text(response)
        except Exception as exc:
            logger.debug(f"social_reply: text reply failed: {exc}")

    _mark_replied(group_id, user_id)
    logger.debug(f"social_reply: handled appreciation from user {user_id} in group {group_id}")
    return True
