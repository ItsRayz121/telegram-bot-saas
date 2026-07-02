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
# Bare domains typed WITHOUT a scheme ("scamsite.xyz", "earn-now.top/join") that
# _URL_RE misses. Kept to a common/abused TLD allow-list so it doesn't fire on
# ordinary "file.txt" / "node.js" / "3.5" text.
_BARE_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:com|net|org|io|me|xyz|co|app|link|live|online|site|shop|store|"
    r"info|biz|tech|club|vip|gg|to|cc|tv|ru|cn|ly|pro|dev|ai|finance|"
    r"fund|cash|money|top|win|bet|casino|trade|pw|su|tk|ml|ga|cf)\b"
    r"(?:/[^\s]*)?",
    re.I,
)
# Discord invite surfaces: discord.gg/x, discord.com/invite/x, dsc.gg/x, etc.
_DISCORD_INVITE_RE = re.compile(
    r"(discord\.gg/|discord(?:app)?\.com/invite/|discord\.me/|dsc\.gg/|invite\.gg/)\S+",
    re.I,
)


def extract_urls(text: str) -> list[str]:
    return _URL_RE.findall(text or "")


def extract_bare_domains(text: str) -> list[str]:
    """Scheme-less domains ('scamsite.xyz') that extract_urls (http/https only)
    misses — spammers drop the scheme to slip past link filters."""
    return _BARE_DOMAIN_RE.findall(text or "")


def _domain(url: str) -> str:
    m = _URL_DOMAIN_RE.search(url or "")
    if m:
        host = m.group(1).lower()
    else:
        # Scheme-less bare domain like "scamsite.xyz/path" — take the host part.
        host = (url or "").strip().lower().split("/")[0].split(":")[0]
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


# --- Phase 10 automod heuristics (pure text analysis) --------------------------
# Unicode emoji + Discord custom emoji (<:name:id> / animated <a:name:id>).
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F"
    "\U0001F900-\U0001F9FF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]"
)
_CUSTOM_EMOJI_RE = re.compile(r"<a?:\w{2,32}:\d{15,21}>")

_SCRIPT_RANGES = {
    "cyrillic": re.compile(r"[Ѐ-ӿ]"),
    "chinese": re.compile(r"[一-鿿㐀-䶿]"),
    "korean": re.compile(r"[가-힯ᄀ-ᇿ]"),
    "arabic": re.compile(r"[؀-ۿݐ-ݿ]"),
    "japanese": re.compile(r"[぀-ヿ]"),
}


def count_emojis(text: str) -> int:
    if not text:
        return 0
    return len(_EMOJI_RE.findall(text)) + len(_CUSTOM_EMOJI_RE.findall(text))


def caps_percent(text: str) -> tuple[int, int]:
    """(percent_upper, letter_count) over alphabetic chars only."""
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return 0, 0
    upper = sum(1 for c in letters if c.isupper())
    return round(upper * 100 / len(letters)), len(letters)


def script_hit(text: str, scripts: list[str]) -> str | None:
    """First configured foreign script found in the text, else None."""
    for name in scripts or []:
        rx = _SCRIPT_RANGES.get(str(name).lower())
        if rx and rx.search(text or ""):
            return str(name).lower()
    return None


def domain_allowed(url: str, whitelist: list[str]) -> bool:
    """True if the URL's domain matches a whitelist entry (subdomains count)."""
    dom = _domain(url)
    for entry in whitelist or []:
        e = str(entry).lower().strip().lstrip("*.")
        if e and (dom == e or dom.endswith("." + e)):
            return True
    return False


# --- Phase 18: Smart-mod pattern layer (rule-based, no AI) + extended content --
# Promotional / solicitation patterns — the cheap Layer-2 net under the AI layer.
_PROMO_PATTERNS = [
    r"\bdm\s+me\b", r"\bpm\s+me\b", r"\bcheck\s+(out\s+)?my\b", r"\bjoin\s+my\b",
    r"\buse\s+(promo\s+)?code\b", r"\bpromo\s*code\b", r"\bdiscount\s*code\b",
    r"\bmake\s+\$?\d{2,}", r"\bearn\s+\$?\d{2,}", r"\bguaranteed\s+(profit|returns?)\b",
    r"\b(crypto|forex|nft)\s+(signals?|pump|giveaway|investment)\b",
    r"\bfollow\s+me\s+on\b", r"\bsubscribe\s+to\s+my\b", r"\blink\s+in\s+bio\b",
    r"\bcash\s*app\b", r"\bpaypal\.me\b", r"\bbuy\s+followers\b",
]
_PROMO_RE = [re.compile(p, re.I) for p in _PROMO_PATTERNS]
# A referral mention on its own — exempted when allow_referral_codes is on.
_REFERRAL_RE = re.compile(r"\b(referral|ref)\s*(code|link)?\b", re.I)


def promo_match(text: str, allow_referral: bool = False):
    """First promotional/solicitation pattern in the text, or None.

    When allow_referral is set, a bare referral mention does not count."""
    if not text:
        return None
    for rx in _PROMO_RE:
        m = rx.search(text)
        if m:
            term = m.group(0).strip()
            if allow_referral and _REFERRAL_RE.fullmatch(term):
                continue
            return term
    if not allow_referral:
        m = _REFERRAL_RE.search(text)
        if m:
            return m.group(0).strip()
    return None


# Obfuscated URLs the plain http(s) regex misses (cloaking to dodge link filters).
_HIDDEN_URL_PATTERNS = [
    r"\bhxxps?://",                                          # hxxp(s):// cloaking
    r"\b[\w-]+\s*[\[(]?\s*dot\s*[\])]?\s*(com|net|org|io|gg|me|ru|xyz|info)\b",  # "site dot com"
    r"\b[\w-]+_(com|net|org|io|gg|me)\b",                    # example_com
    r"\bt\s*[\[(]?\.?[\])]?\s*me\s*/\s*\w+",                 # t . me / x
]
_HIDDEN_URL_RE = [re.compile(p, re.I) for p in _HIDDEN_URL_PATTERNS]


def hidden_url_match(text: str):
    """First obfuscated/hidden URL in the text, or None."""
    for rx in _HIDDEN_URL_RE:
        m = rx.search(text or "")
        if m:
            return m.group(0).strip()
    return None


_EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
# Phone numbers: require a leading + or separated digit groups so raw Discord
# snowflake IDs (one long digit run) don't trip it.
_PHONE_RE = re.compile(
    r"(\+\d[\d\s().-]{7,16}\d|\b\d{3}[\s().-]\d{3}[\s().-]\d{3,4}\b)"
)
_SPOILER_RE = re.compile(r"\|\|.+?\|\|", re.S)


def email_match(text: str):
    m = _EMAIL_RE.search(text or "")
    return m.group(0) if m else None


def phone_match(text: str):
    m = _PHONE_RE.search(text or "")
    return m.group(0).strip() if m else None


def spoiler_match(text: str):
    return "spoiler" if _SPOILER_RE.search(text or "") else None


# --- Homoglyph / mixed-script spoofing -----------------------------------------
# Cyrillic & Greek letters that are visually confusable with ASCII Latin. A
# single token that mixes real Latin letters with these lookalikes is almost
# always deliberate filter-evasion (e.g. "pаypal" with a Cyrillic а). We only
# flag the MIXED case, never pure non-Latin words — genuine Cyrillic/Greek text
# is the language filter's job, so this stays near-zero false-positive.
_CONFUSABLE_CHARS = set(
    "аеоріјѕсухкңԁ"        # Cyrillic lowercase lookalikes (a e o p i j s c y x k …)
    "АЕОРСНХІЈЅВКМТ"       # Cyrillic uppercase lookalikes
    "οανρτυχικ"            # Greek lowercase lookalikes
    "ΟΑΝΡΤΥΧΙΚΒΕΗΜ"       # Greek uppercase lookalikes
)
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
_TOKEN_RE = re.compile(r"\S+")


def homoglyph_match(text: str):
    """Return the first token mixing ASCII Latin letters with confusable
    Cyrillic/Greek lookalikes (classic word-filter evasion), else None."""
    for token in _TOKEN_RE.findall(text or ""):
        if _ASCII_LETTER_RE.search(token) and any(ch in _CONFUSABLE_CHARS for ch in token):
            return token[:40]
    return None
