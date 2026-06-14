"""Human-like social replies (Phase 3 parity).

Detects appreciation messages ("thanks", "this helped", "you rock") and responds
warmly. Zero AI cost — static, personality-aware reply pools, mirroring the
Telegizer social-replies feature. Pure functions over plain strings, so the
detector + pool selection unit-test on their own; the bot does the sending.

mode: minimal | professional | friendly | community_manager
"""
from __future__ import annotations

import random
import re

# Appreciation signals — lowercased substring/word checks after normalisation.
_APPRECIATION_PATTERNS = [
    r"\bthank(s| you| u)?\b", r"\bthx\b", r"\bty\b", r"\btysm\b",
    r"\bappreciate(d|s| it| this)?\b", r"\bmuch appreciated\b",
    r"\bthis (really )?help(ed|s)\b", r"\bvery helpful\b", r"\bso helpful\b",
    r"\blifesaver\b", r"\byou (rock|the best|guys rock)\b", r"\blegend\b",
    r"\bgrateful\b", r"\bcheers\b", r"\bbig help\b",
]
_APPRECIATION_RE = [re.compile(p, re.I) for p in _APPRECIATION_PATTERNS]

# Per-mode reply pools. A random line is picked so the bot doesn't feel robotic.
_POOLS = {
    "minimal": ["🙏", "👍", "Anytime!"],
    "professional": [
        "You're welcome — glad we could help.",
        "Happy to help. Let us know if anything else comes up.",
        "Glad that was useful!",
    ],
    "friendly": [
        "Anytime! 😊", "You're so welcome! 🙌", "Happy to help! 🎉",
        "Aw, glad it helped! 💜", "No problem at all! 👍",
    ],
    "community_manager": [
        "That's what this community is all about — glad you got sorted! 🤝",
        "Love to see members helping each other thrive! 🙌",
        "You're welcome! Stick around, there's plenty more good stuff here. ✨",
        "So glad that helped — welcome to lean on the community anytime! 💜",
    ],
}
_DEFAULT_MODE = "friendly"
_APPRECIATION_EMOJI = "🙏"


def is_appreciation(text: str) -> bool:
    """True if the message reads as thanks/appreciation."""
    if not text:
        return False
    # Keep it short-message biased so we don't reply to long messages that merely
    # contain "thanks" in passing.
    if len(text) > 200:
        return False
    return any(rx.search(text) for rx in _APPRECIATION_RE)


def pick_reply(mode: str) -> str:
    """A random reply line for the configured personality mode."""
    pool = _POOLS.get(mode) or _POOLS[_DEFAULT_MODE]
    return random.choice(pool)


def appreciation_emoji() -> str:
    return _APPRECIATION_EMOJI
