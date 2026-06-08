"""Engagement Campaigns — verification engine (Phase 5).

The realistic, production-safe subset (see ENGAGEMENT_CAMPAIGNS_PLAN.md §4):
  - Telegram channel/group JOIN  → reliably auto-verifiable via getChatMember
    (the bot must be an admin in the target chat).
  - Link-validity                → URL shape + platform-host match (premium gate
    is enforced at campaign creation). Optional deep API checks degrade
    gracefully to shape-only when no API key is configured.

Everything else (X likes/follows, YouTube subscribe, IG/FB) stays manual/honor —
intentionally NOT auto-verified.
"""

import logging
import re
import time

logger = logging.getLogger(__name__)

# ── Deep link-validity ("does it exist") checks ────────────────────────────────
# Optional, API-key-gated. When no key is configured the checks degrade to the
# shape/host validation only (today's behaviour). Results are cached briefly so a
# campaign verifying many links doesn't hammer the upstream API.
_DEEP_CACHE = {}          # url → (expiry_ts, (ok, reason))
_DEEP_CACHE_TTL = 600.0   # 10 minutes
_DEEP_CACHE_MAX = 2000
_DEEP_TIMEOUT = 5         # seconds

_YOUTUBE_ID_RES = [
    re.compile(r"(?:youtu\.be/)([A-Za-z0-9_-]{11})"),
    re.compile(r"[?&]v=([A-Za-z0-9_-]{11})"),
    re.compile(r"/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})"),
]
_X_ID_RE = re.compile(r"/status(?:es)?/(\d{5,25})")

# Member-like statuses returned by getChatMember.
_MEMBER_STATUSES = {"creator", "administrator", "member", "owner"}

# Allowed hosts per platform for link-validity checks.
_PLATFORM_HOSTS = {
    "x": ["x.com", "twitter.com"],
    "youtube": ["youtube.com", "youtu.be"],
    "telegram": ["t.me", "telegram.me"],
    "instagram": ["instagram.com"],
    "facebook": ["facebook.com", "fb.com"],
}


async def verify_telegram_join(bot, chat_ref, user_id):
    """Return True iff user_id is a member of chat_ref. Never raises."""
    if not chat_ref:
        return False
    try:
        member = await bot.get_chat_member(chat_id=chat_ref, user_id=int(user_id))
        status = getattr(member, "status", None)
        status = getattr(status, "value", status)  # enum → str
        if status in _MEMBER_STATUSES:
            return True
        # 'restricted' members may still be in the chat.
        if status == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except Exception as e:
        logger.info("verify_telegram_join failed for chat=%s user=%s: %s", chat_ref, user_id, e)
        return False


# Human labels for platforms, used in field-level error messages.
_PLATFORM_LABEL = {
    "x": "Twitter/X", "youtube": "YouTube", "telegram": "Telegram",
    "instagram": "Instagram", "facebook": "Facebook",
}

_URL_RE = re.compile(r"^https?://", re.I)
_UID_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
_USERNAME_RE = re.compile(r"^@?[A-Za-z0-9._]{2,64}$")
_WALLET_RE = re.compile(r"^(0x[a-fA-F0-9]{40}|[A-Za-z0-9]{26,64})$")
_TXHASH_RE = re.compile(r"^(0x)?[A-Fa-f0-9]{40,128}$")


def _looks_like_url(value):
    return bool(_URL_RE.match((value or "").strip()))


def validate_field_value(field_type, value, *, platform=None):
    """Validate a single proof value by its declared type. Returns
    (ok, normalized_value, error_message). Used by BOTH the bot DM flow and the
    Mini App API so submissions are validated identically everywhere.

    Screenshots are validated separately (a photo upload), not here.
    """
    v = (value or "").strip()
    if not v:
        return False, v, "Please provide a value."

    if field_type == "url":
        ok, reason = validate_link(v, platform)
        if not ok:
            return False, v, reason
        return True, v, None

    if field_type == "uid":
        if _looks_like_url(v):
            return False, v, "Please submit your exchange UID, not a link."
        if not _UID_RE.match(v):
            return False, v, "That doesn’t look like a valid UID. Send the numbers/letters only (e.g. 123456789)."
        return True, v, None

    if field_type == "wallet":
        if _looks_like_url(v) or " " in v:
            return False, v, "Please submit a valid wallet address (no links or spaces)."
        if not _WALLET_RE.match(v):
            return False, v, "That doesn’t look like a valid wallet address. Double-check and resend."
        return True, v, None

    if field_type == "tx_hash":
        if _looks_like_url(v) or " " in v:
            return False, v, "Please submit a valid transaction hash."
        if not _TXHASH_RE.match(v):
            return False, v, "That doesn’t look like a valid transaction hash."
        return True, v, None

    if field_type == "username":
        if _looks_like_url(v) or " " in v:
            return False, v, "Please submit a username / handle, not a link."
        if not _USERNAME_RE.match(v):
            return False, v, "That doesn’t look like a valid username/handle."
        return True, v.lstrip("@"), None  # normalize: strip leading @

    # text and any unknown type → accept as-is.
    return True, v, None


def validate_link(url, platform=None):
    """Shape + platform-host validation, plus an optional deep existence check
    (YouTube/X) when an API key is configured. Returns (ok, reason)."""
    if not url or not re.match(r"^https?://", url.strip(), re.I):
        return False, "Please send a valid link starting with http:// or https://"
    if platform and platform in _PLATFORM_HOSTS:
        host_ok = any(h in url.lower() for h in _PLATFORM_HOSTS[platform])
        if not host_ok:
            label = _PLATFORM_LABEL.get(platform, platform)
            return False, f"Please submit a valid {label} URL."
    deep_ok, deep_reason = _deep_link_check(url.strip(), platform)
    if not deep_ok:
        return False, deep_reason
    return True, None


def _deep_link_check(url, platform):
    """Optional 'does it exist' check for YouTube/X. Returns (ok, reason).
    Always (True, None) when no API key is set or the platform isn't supported —
    so this never blocks unless we can prove the target is missing. Cached + never
    raises."""
    from .config import Config

    # Infer platform from the host when not declared.
    low = url.lower()
    if not platform:
        if "youtube.com" in low or "youtu.be" in low:
            platform = "youtube"
        elif "x.com" in low or "twitter.com" in low:
            platform = "x"

    if platform == "youtube" and Config.YOUTUBE_API_KEY:
        return _cached_check(url, lambda: _deep_check_youtube(url, Config.YOUTUBE_API_KEY))
    if platform == "x":
        # Prefer the low-cost twitterapi.io provider; fall back to official X v2.
        if Config.TWITTERAPI_IO_KEY:
            return _cached_check(url, lambda: _deep_check_x_twitterapi(url, Config.TWITTERAPI_IO_KEY))
        if Config.X_BEARER_TOKEN:
            return _cached_check(url, lambda: _deep_check_x(url, Config.X_BEARER_TOKEN))
    return True, None


def _cached_check(url, fn):
    now = time.monotonic()
    hit = _DEEP_CACHE.get(url)
    if hit and hit[0] > now:
        return hit[1]
    result = fn()
    # Only cache definitive results; size-cap the cache.
    if len(_DEEP_CACHE) > _DEEP_CACHE_MAX:
        _DEEP_CACHE.clear()
    _DEEP_CACHE[url] = (now + _DEEP_CACHE_TTL, result)
    return result


def _deep_check_youtube(url, api_key):
    """True iff the YouTube video resolves. Degrades to accept on any non-404
    error (rate limit / outage / quota)."""
    vid = None
    for rx in _YOUTUBE_ID_RES:
        m = rx.search(url)
        if m:
            vid = m.group(1)
            break
    if not vid:
        return True, None  # can't extract id → don't block (shape already passed)
    try:
        import requests
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "id", "id": vid, "key": api_key},
            timeout=_DEEP_TIMEOUT,
        )
        if resp.status_code == 200:
            items = (resp.json() or {}).get("items") or []
            if not items:
                return False, "That YouTube video doesn’t exist or is private. Check the link."
        return True, None
    except Exception as e:
        logger.info("youtube deep-check failed (accepting): %s", e)
        return True, None


def _deep_check_x_twitterapi(url, key):
    """X/Twitter existence check via twitterapi.io (low-cost provider). Returns
    (ok, reason). Conservative: only rejects on a clearly successful response that
    explicitly returns no tweet for the id; any other shape/error → accept."""
    m = _X_ID_RE.search(url)
    if not m:
        return True, None
    tweet_id = m.group(1)
    try:
        import requests
        resp = requests.get(
            "https://api.twitterapi.io/twitter/tweets",
            params={"tweet_ids": tweet_id},
            headers={"X-API-Key": key},
            timeout=_DEEP_TIMEOUT,
        )
        if resp.status_code == 200:
            body = resp.json() or {}
            tweets = body.get("tweets")
            # Definitive "missing": success response with an empty tweets list.
            if isinstance(tweets, list) and len(tweets) == 0:
                return False, "That post doesn’t exist or was deleted. Check the link."
        return True, None
    except Exception as e:
        logger.info("twitterapi.io deep-check failed (accepting): %s", e)
        return True, None


def _deep_check_x(url, bearer):
    """True iff the X/Twitter post resolves. Degrades to accept on anything other
    than a definitive 404 (the v2 lookup is rate-limited / tier-gated)."""
    m = _X_ID_RE.search(url)
    if not m:
        return True, None
    tweet_id = m.group(1)
    try:
        import requests
        resp = requests.get(
            f"https://api.twitter.com/2/tweets/{tweet_id}",
            headers={"Authorization": f"Bearer {bearer}"},
            timeout=_DEEP_TIMEOUT,
        )
        if resp.status_code == 404:
            return False, "That post doesn’t exist or was deleted. Check the link."
        if resp.status_code == 200:
            body = resp.json() or {}
            # v2 returns {"errors":[{"title":"Not Found Error",...}]} for missing ids.
            errs = body.get("errors") or []
            if not body.get("data") and any("not found" in (e.get("title", "").lower()) for e in errs):
                return False, "That post doesn’t exist or was deleted. Check the link."
        return True, None
    except Exception as e:
        logger.info("x deep-check failed (accepting): %s", e)
        return True, None


def validate_link_payload(campaign, answers):
    """For a link-mode campaign, validate the submitted link(s). Returns
    (ok, reason). Checks every URL-type field; if there are none, validates any
    answer that looks like a URL."""
    answers = answers or {}
    url_fields = [f for f in campaign.custom_fields.all() if f.field_type == "url"]
    values = []
    if url_fields:
        values = [(answers.get(f.key) or "").strip() for f in url_fields]
        if not any(values):
            return False, "Please submit the required link."
    else:
        values = [v for v in answers.values() if isinstance(v, str) and v.strip().lower().startswith("http")]
        if not values:
            return False, "Please submit a valid link."
    for v in values:
        if not v:
            continue
        ok, reason = validate_link(v, campaign.platform)
        if not ok:
            return False, reason
    return True, None
