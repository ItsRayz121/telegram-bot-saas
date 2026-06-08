"""
Message-level content filtering (Phase 2 of the bot-spam protection work).

Catches spam that IS visible to us — posted by humans, userbots (automated user
accounts), or sent "via @inlinebot" by a human (sender is the human, so the
message is delivered). It does NOT help against content posted directly by a bot
*member* — Telegram never delivers that to us; that's handled at join time by
bot_guard (Phase 1).

Two surfaces matter and they carry very different false-positive risk:

  • Plain text / caption — a real person might curse or quote. NSFW here is
    handled conservatively (delete + warn by default).
  • Inline keyboard buttons (text + URLs) and hidden text-link URLs — ordinary
    Telegram clients CANNOT attach inline keyboards; only bots / userbots / inline
    mode can. So NSFW or scam links riding on buttons are almost never legitimate
    → safe to ban. This module exposes the button/entity URL surface so callers
    can apply the harsher action there.

Runtime-agnostic: pure functions over a python-telegram-bot Message. Both the
official bot (_automod_check) and custom bots (ModerationSystem.check_automod)
call into it so the two lineages stay in lockstep (bot-lineage rule).
"""

import re
import unicodedata

# ── Normalization ─────────────────────────────────────────────────────────────

# Leetspeak / symbol substitutions applied before keyword matching so "p0rn",
# "pr0n", "s3x", "@dult" all fold onto their plain forms.
_LEET = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
    "7": "t", "8": "b", "9": "g", "@": "a", "$": "s", "+": "t",
})
_ZERO_WIDTH = re.compile(r"[​-‏‪-‮⁠﻿]")
_REPEAT = re.compile(r"(.)\1{2,}")          # 3+ repeats → 1 (fuuuck → fuck)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_for_match(text: str) -> str:
    """Lowercase + strip accents + de-leet + collapse runs. Used only for
    keyword matching, never shown to anyone."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = _ZERO_WIDTH.sub("", t).lower().translate(_LEET)
    t = _REPEAT.sub(r"\1", t)
    return t


def _compact(text: str) -> str:
    """Drop every non-alphanumeric char so 'p o r n' / 'o-n-l-y-f-a-n-s' collapse
    to a single token (catches letter-spacing evasion)."""
    return _NON_ALNUM.sub("", normalize_for_match(text))


# ── NSFW / adult vocabulary ─────────────────────────────────────────────────
# Boundary-matched terms — matched as whole words on normalized text, so "sex"
# won't fire inside "Sussex" and "porn" won't fire inside "important".
_NSFW_WORD_TERMS = [
    "porn", "pron", "xxx", "xvideos", "xnxx", "pornhub", "redtube", "brazzers",
    "youporn", "nsfw", "onlyfans", "fansly", "camgirl", "camsex", "camwhore",
    "hentai", "rule34", "milf", "gilf", "creampie", "blowjob", "handjob",
    "deepthroat", "gangbang", "bukkake", "cumshot", "cumming", "squirting",
    "fingering", "masturbate", "masturbation", "dildo", "buttplug", "fleshlight",
    "nudes", "nudez", "titties", "schoolgirl", "stepsister", "stepmom",
    "escort", "hookup", "sexdate", "fuckbuddy", "horny", "slut", "whore",
    "sexcam", "sexchat", "sextape", "sexvideo",
]
# Multi-word / phrase patterns (searched in the normalized, space-preserved text)
_NSFW_PHRASE_PATTERNS = [
    r"sex\s*(video|tape|cam|chat|date|clip)",
    r"(free|hot|live|teen|young)\s*(sex|nudes|porn|girls|cam)",
    r"adult\s*(content|video|chat|cam)",
    r"(leaked|exclusive)\s*(nudes|content|pics|videos)",
    r"18\s*\+?\s*(only|content|video|nsfw)",
    r"dick\s*pic",
    r"nude\s*(pic|photo|girl|teen)",
    r"join\s*(for|the)?\s*(porn|nudes|xxx|sex)",
]
# Distinctive strings safe to match even after all separators are stripped
# (long & non-substring of common words) — defeats letter-spacing.
_NSFW_COMPACT_TERMS = [
    "porn", "xvideos", "xnxx", "pornhub", "onlyfans", "creampie", "hentai",
    "gangbang", "blowjob", "deepthroat", "cumshot", "schoolgirl", "sextape",
    "sexvideo", "sexcam", "nudes",
]

# CSAM — zero tolerance, always treated as the hardest action regardless of
# where it appears. Kept deliberately specific to avoid catastrophic false bans.
_CSAM_PATTERNS = [
    r"child\s*p(orn|0rn)?",
    r"\bcp\s*(video|content|link|pack)\b",
    r"\b(preteen|pre-teen)\b",
    r"\bunderage\s*(sex|nude|porn|girl)",
    r"\bloli(con)?\b",
    r"\bj+a+i+l+b+a+i+t+\b",
]

_NSFW_WORD_RE = re.compile(r"\b(" + "|".join(_NSFW_WORD_TERMS) + r")\b")
_NSFW_PHRASE_RE = [re.compile(p) for p in _NSFW_PHRASE_PATTERNS]
_CSAM_RE = [re.compile(p) for p in _CSAM_PATTERNS]


def nsfw_match(text: str, extra_words=None):
    """Return (matched_term, is_csam) or (None, False).

    extra_words: admin-supplied additions (plain substrings, case-insensitive)."""
    if not text:
        return None, False
    norm = normalize_for_match(text)

    for rx in _CSAM_RE:
        m = rx.search(norm)
        if m:
            return m.group(0).strip(), True

    m = _NSFW_WORD_RE.search(norm)
    if m:
        return m.group(1), False

    for rx in _NSFW_PHRASE_RE:
        m = rx.search(norm)
        if m:
            return m.group(0).strip(), False

    compact = _compact(text)
    for term in _NSFW_COMPACT_TERMS:
        if term in compact:
            return term, False

    for w in (extra_words or []):
        wn = normalize_for_match(str(w))
        if wn and wn in norm:
            return str(w), False

    return None, False


# ── URL / link heuristics ─────────────────────────────────────────────────────

_SHORTENERS = {
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd", "buff.ly",
    "cutt.ly", "rebrand.ly", "shorturl.at", "rb.gy", "tiny.cc", "bl.ink",
    "soo.gd", "s.id", "linktr.ee", "lnkd.in", "qr.ae", "adf.ly", "shorte.st",
    "bc.vc", "ouo.io", "linkvertise.com", "gg.gg", "v.gd", "clck.ru",
}
# TLDs disproportionately used by throwaway scam/redirect domains.
_SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".click", ".link", ".monster", ".cyou", ".rest", ".gq",
    ".tk", ".ml", ".cf", ".ga", ".work", ".fit", ".sbs", ".cfd", ".lol",
    ".quest", ".live", ".icu", ".buzz", ".date", ".loan", ".online",
}
_URL_DOMAIN_RE = re.compile(r"https?://([^/\s:]+)", re.I)
_TELEGRAM_LINK_RE = re.compile(r"(t\.me/|telegram\.me/|telegram\.dog/)", re.I)


def _domain(url: str) -> str:
    m = _URL_DOMAIN_RE.search(url or "")
    if not m:
        return ""
    host = m.group(1).lower()
    return host[4:] if host.startswith("www.") else host


def is_suspicious_link(url: str) -> bool:
    """True for known URL shorteners or scam-leaning TLDs (classic redirect
    cloaking for buttons/captions)."""
    host = _domain(url)
    if not host:
        return False
    if host in _SHORTENERS:
        return True
    return any(host.endswith(tld) for tld in _SUSPICIOUS_TLDS)


def is_telegram_invite(url: str) -> bool:
    return bool(_TELEGRAM_LINK_RE.search(url or ""))


# ── Message surface extraction ──────────────────────────────────────────────

def extract_buttons(message):
    """Return (button_texts, button_urls) from a message's inline keyboard.
    Ordinary user clients can't attach these, so their presence on a non-admin
    message is itself a strong spam signal."""
    texts, urls = [], []
    rm = getattr(message, "reply_markup", None)
    rows = getattr(rm, "inline_keyboard", None) if rm else None
    if not rows:
        return texts, urls
    for row in rows:
        for btn in row:
            t = getattr(btn, "text", None)
            if t:
                texts.append(t)
            u = getattr(btn, "url", None)
            if u:
                urls.append(u)
    return texts, urls


def extract_entity_urls(message):
    """Hidden URLs behind hyperlinked text (TextLink entities) in text + caption."""
    urls = []
    for e in list(getattr(message, "entities", None) or []) + \
             list(getattr(message, "caption_entities", None) or []):
        u = getattr(e, "url", None)
        if u:
            urls.append(u)
    return urls


def has_inline_buttons(message) -> bool:
    rm = getattr(message, "reply_markup", None)
    return bool(getattr(rm, "inline_keyboard", None)) if rm else False
