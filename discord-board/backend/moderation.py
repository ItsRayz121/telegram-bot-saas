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
    if category == "external_link":
        return "🚫 External links aren't allowed here."
    if category == "emoji_flood":
        return "🚫 That message was removed — too many emojis."
    if category == "caps_lock":
        return "🚫 That message was removed — please don't shout in all caps."
    if category == "language":
        return "🚫 That message was removed by the server's language filter."
    if category == "homoglyphs":
        return "🚫 That message was removed — disguised/look-alike characters aren't allowed."
    if category == "flood":
        return "🚫 Slow down — you're sending messages too quickly."
    if category in ("attachment", "sticker", "voice_message", "photo", "video", "gif"):
        return "🚫 That content type isn't allowed in this server."
    if category == "email_detection":
        return "🚫 That message was removed — please don't share email addresses here."
    if category == "contact_sharing":
        return "🚫 That message was removed — please don't share phone numbers here."
    if category == "spoiler_content":
        return "🚫 Spoiler content isn't allowed here."
    if category == "bot_mentions":
        return "🚫 Mentioning bots isn't allowed here."
    if category == "smart_mod":
        return "🚫 That message looked like unsolicited promotion and was removed."
    return "🚫 That message was removed by the content filter."


# --- Phase 10: extended automod matrix (config lives in cfg["automod"]) --------
def evaluate_automod(text: str, cfg: dict) -> dict | None:
    """Extra heuristics beyond the core filter: link whitelist, emoji flood,
    caps lock, foreign-script filter. Pure; same decision shape as evaluate()."""
    am = (cfg or {}).get("automod") or {}
    text = text or ""

    links = am.get("external_links") or {}
    if links.get("enabled"):
        for url in cf.extract_urls(text):
            if not cf.domain_allowed(url, links.get("whitelist") or []):
                return {"category": "external_link", "action": _norm_action(links.get("action", "delete")),
                        "matched": url, "detail": f"Non-whitelisted link: {cf._domain(url)}"}

    emo = am.get("excessive_emojis") or {}
    if emo.get("enabled"):
        n = cf.count_emojis(text)
        if n > int(emo.get("max_emojis", 15)):
            return {"category": "emoji_flood", "action": _norm_action(emo.get("action", "delete")),
                    "matched": str(n), "detail": f"{n} emojis (max {emo.get('max_emojis', 15)})"}

    caps = am.get("caps_lock") or {}
    if caps.get("enabled"):
        pct, letters = cf.caps_percent(text)
        if letters >= int(caps.get("min_length", 15)) and pct >= int(caps.get("threshold_percent", 80)):
            return {"category": "caps_lock", "action": _norm_action(caps.get("action", "delete")),
                    "matched": f"{pct}%", "detail": f"{pct}% caps over {letters} letters"}

    lang = am.get("language_filter") or {}
    if lang.get("enabled"):
        hit = cf.script_hit(text, lang.get("scripts") or [])
        if hit:
            return {"category": "language", "action": _norm_action(lang.get("action", "delete")),
                    "matched": hit, "detail": f"Filtered script: {hit}"}

    homo = am.get("homoglyphs") or {}
    if homo.get("enabled"):
        hit = cf.homoglyph_match(text)
        if hit:
            return {"category": "homoglyphs", "action": _norm_action(homo.get("action", "delete")),
                    "matched": hit, "detail": f"Mixed-script spoofing: {hit}"}

    return None


def evaluate_media(flags: dict, cfg: dict) -> dict | None:
    """Media-type toggles. flags = {attachments, stickers, voice, photos, videos,
    gifs} booleans the bot derives from the message; config decides which types
    get removed."""
    media = ((cfg or {}).get("automod") or {}).get("media") or {}
    action = _norm_action(media.get("action", "delete"))
    flags = flags or {}
    # (config key, message flag, category, detail) — first match wins.
    rules = (
        ("block_attachments", "attachments", "attachment", "File/image attachments are blocked here"),
        ("block_photos", "photos", "photo", "Photos are blocked here"),
        ("block_videos", "videos", "video", "Videos are blocked here"),
        ("block_gifs", "gifs", "gif", "GIFs are blocked here"),
        ("block_stickers", "stickers", "sticker", "Stickers are blocked here"),
        ("block_voice", "voice", "voice_message", "Voice messages are blocked here"),
    )
    for cfg_key, flag_key, category, detail in rules:
        if media.get(cfg_key) and flags.get(flag_key):
            return {"category": category, "action": action, "matched": category, "detail": detail}
    return None


def evaluate_content(text: str, flags: dict, cfg: dict) -> dict | None:
    """Extended content rules (Phase 18): email / phone / spoiler text patterns
    and bot mentions. Each rule is its own automod sub-section {enabled, action}."""
    am = (cfg or {}).get("automod") or {}
    text = text or ""
    flags = flags or {}
    text_rules = (
        ("email_detection", cf.email_match, "Email address shared"),
        ("contact_sharing", cf.phone_match, "Phone number shared"),
        ("spoiler_content", cf.spoiler_match, "Spoiler content"),
    )
    for key, detector, detail in text_rules:
        rule = am.get(key) or {}
        if rule.get("enabled"):
            hit = detector(text)
            if hit:
                return {"category": key, "action": _norm_action(rule.get("action", "delete")),
                        "matched": str(hit), "detail": detail}
    bm = am.get("bot_mentions") or {}
    if bm.get("enabled") and flags.get("mentions_bot"):
        return {"category": "bot_mentions", "action": _norm_action(bm.get("action", "delete")),
                "matched": "bot", "detail": "Bot mention"}
    return None


def evaluate_smart_patterns(text: str, cfg: dict) -> dict | None:
    """Smart Moderation Layer 2 — rule-based promo / obfuscated-URL detection.
    Runs with no AI cost; the AI relevance layer (Layer 3) is handled by the bot
    only when smart_mod.ai_enabled. trusted_user_ids bypass is applied upstream."""
    sm = ((cfg or {}).get("automod") or {}).get("smart_mod") or {}
    if not sm.get("enabled"):
        return None
    text = text or ""
    action = _norm_action(sm.get("action", "delete"))
    if sm.get("promotional_detection"):
        hit = cf.promo_match(text, allow_referral=bool(sm.get("allow_referral_codes")))
        if hit:
            return {"category": "smart_mod", "action": action, "matched": hit,
                    "detail": f"Promotional pattern: {hit}"}
    if sm.get("hidden_url_detection"):
        hit = cf.hidden_url_match(text)
        if hit:
            return {"category": "smart_mod", "action": action, "matched": hit,
                    "detail": f"Hidden/obfuscated URL: {hit}"}
    return None
