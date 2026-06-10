"""Message-level content heuristics for Guildizer.

Copied (not imported) from the Telegizer content filter and re-pointed at
Discord: same NSFW/CSAM vocabulary and link heuristics, but the Telegram
inline-keyboard surface is replaced by Discord invite detection. Pure functions
over plain strings — no discord.py types — so it's unit-testable on its own.
"""
from __future__ import annotations

import re
import unicodedata

# ── Normalization ─────────────────────────────────────────────────────────────
_LEET = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
    "7": "t", "8": "b", "9": "g", "@": "a", "$": "s", "+": "t",
})
_ZERO_WIDTH = re.compile(r"[​-‏‪-‮⁠﻿]")
_REPEAT = re.compile(r"(.)\1{2,}")          # 3+ repeats → 1 (fuuuck → fuck)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_for_match(text: str) -> str:
    """Lowercase + strip accents + de-leet + collapse runs. Match-only, never shown."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = _ZERO_WIDTH.sub("", t).lower().translate(_LEET)
    t = _REPEAT.sub(r"\1", t)
    return t


def _compact(text: str) -> str:
    """Drop non-alphanumerics so 'p o r n' / 'o-n-l-y-f-a-n-s' collapse to one token."""
    return _NON_ALNUM.sub("", normalize_for_match(text))


# ── NSFW / CSAM vocabulary ────────────────────────────────────────────────────
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
_NSFW_COMPACT_TERMS = [
    "porn", "xvideos", "xnxx", "pornhub", "onlyfans", "creampie", "hentai",
    "gangbang", "blowjob", "deepthroat", "cumshot", "schoolgirl", "sextape",
    "sexvideo", "sexcam", "nudes",
]
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
_SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".click", ".link", ".monster", ".cyou", ".rest", ".gq",
    ".tk", ".ml", ".cf", ".ga", ".work", ".fit", ".sbs", ".cfd", ".lol",
    ".quest", ".live", ".icu", ".buzz", ".date", ".loan", ".online",
}
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.I)
_URL_DOMAIN_RE = re.compile(r"https?://([^/\s:]+)", re.I)
# Discord invite surfaces: discord.gg/x, discord.com/invite/x, dsc.gg/x, etc.
_DISCORD_INVITE_RE = re.compile(
    r"(discord\.gg/|discord(?:app)?\.com/invite/|discord\.me/|dsc\.gg/|invite\.gg/)\S+",
    re.I,
)


def extract_urls(text: str) -> list[str]:
    return _URL_RE.findall(text or "")


def _domain(url: str) -> str:
    m = _URL_DOMAIN_RE.search(url or "")
    if not m:
        return ""
    host = m.group(1).lower()
    return host[4:] if host.startswith("www.") else host


def is_suspicious_link(url: str) -> bool:
    """True for known URL shorteners or scam-leaning TLDs (redirect cloaking)."""
    host = _domain(url)
    if not host:
        return False
    if host in _SHORTENERS:
        return True
    return any(host.endswith(tld) for tld in _SUSPICIOUS_TLDS)


def find_discord_invite(text: str):
    """Return the first foreign Discord invite in the text, or None."""
    m = _DISCORD_INVITE_RE.search(text or "")
    return m.group(0) if m else None
