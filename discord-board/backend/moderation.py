"""Content-filter decision engine for Guildizer.

Pure: given a message's text and a guild's content-filter config (a plain dict),
decide what action to take. The bot performs the Discord-side action. No
discord.py types here, so it unit-tests standalone.

Action vocabulary: delete | warn | timeout | kick | ban. CSAM always forces ban;
invites/links force a plain delete (link policy, not user punishment).
"""
from __future__ import annotations

import content_filter as cf

_VALID_ACTIONS = {"delete", "warn", "timeout", "kick", "ban"}


def _norm_action(action: str) -> str:
    return action if action in _VALID_ACTIONS else "delete"


def evaluate(text: str, cfg: dict) -> dict | None:
    """Return a decision dict {category, action, detail, matched} or None if clean.

    cfg keys: cf_enabled, cf_action, cf_nsfw, cf_invites, cf_links, cf_custom_words.
    """
    if not cfg or not cfg.get("cf_enabled"):
        return None
    if not text:
        text = ""

    base_action = _norm_action(cfg.get("cf_action", "delete"))

    # 1. CSAM — always the hardest action, regardless of config toggles.
    term, is_csam = cf.nsfw_match(text)
    if is_csam:
        return {"category": "csam", "action": "ban", "matched": term,
                "detail": "CSAM pattern matched"}

    # 2. NSFW (built-in vocabulary)
    if cfg.get("cf_nsfw") and term:
        return {"category": "nsfw", "action": base_action, "matched": term,
                "detail": f"NSFW term: {term}"}

    # 3. Custom admin words
    custom = cfg.get("cf_custom_words") or []
    if custom:
        hit, _ = cf.nsfw_match(text, extra_words=custom)
        # only treat as custom if a custom word (not built-in nsfw, handled above)
        norm = cf.normalize_for_match(text)
        for w in custom:
            wn = cf.normalize_for_match(str(w))
            if wn and wn in norm:
                return {"category": "custom", "action": base_action, "matched": str(w),
                        "detail": f"Blocked term: {w}"}

    # 4. Foreign Discord invites
    if cfg.get("cf_invites"):
        invite = cf.find_discord_invite(text)
        if invite:
            return {"category": "invite", "action": "delete", "matched": invite,
                    "detail": "Discord invite link"}

    # 5. Suspicious links (shorteners / scam TLDs)
    if cfg.get("cf_links"):
        for url in cf.extract_urls(text):
            if cf.is_suspicious_link(url):
                return {"category": "link", "action": "delete", "matched": url,
                        "detail": f"Suspicious link: {cf._domain(url)}"}

    return None


def warning_text(category: str) -> str:
    """Short, linkless in-channel warning posted after a delete/warn action."""
    if category in ("nsfw", "csam"):
        return "🚫 That message was removed — explicit content isn't allowed here."
    if category == "invite":
        return "🚫 External server invites aren't allowed here."
    if category == "link":
        return "🚫 That link was removed — suspicious or shortened links aren't allowed."
    return "🚫 That message was removed by the content filter."
