"""Twitter/X per-user action verification via twitterapi.io (Guildizer raid auto-verify).

Self-contained Discord-side port of the Telegizer engine — NO cross-imports (the
two boards are separate products; logic is copied, never shared). Powers real-time
verification of raid goals (retweet / comment / follow) for a specific participant:
"did @user actually retweet this tweet?" using the low-cost twitterapi.io provider.

Verified against the live twitterapi.io API (2026-06):
  - retweets  → GET /twitter/tweet/retweeters?tweetId=<id>  → users[].userName
  - comments  → GET /twitter/tweet/replies?tweetId=<id>     → tweets[].author.userName
  - quotes    → GET /twitter/tweet/quotes?tweetId=<id>       → tweets[].author.userName
  - follow    → GET /twitter/user/check_follow_relationship → data.following (bool)
  - likes     → NOT SUPPORTED (X privatized likes in 2024; no read endpoint) → manual

SAFETY CONTRACT — this module can only ever UPGRADE a submission to verified on a
positive match. It never auto-rejects on uncertainty: any missing key, network
error, unexpected shape, unsupported action, or "not found in the pages we fetched"
returns "unknown" (caller leaves it pending for manual review). The ONLY case that
returns "failed" is the follow relationship endpoint giving an authoritative negative.

Key resolution is OWNER-AWARE: the guild owner's own twitterapi.io key (account-level,
Fernet-encrypted on users.twitter_api_key_encrypted) first, then the shared platform
key (TWITTERAPI_IO_KEY env). Pass the owner's user id everywhere in the verify path.
"""
from __future__ import annotations

import logging
import re
import time

log = logging.getLogger("guildizer.twitter_verify")

_BASE = "https://api.twitterapi.io"
_TIMEOUT = 8            # seconds per call
_MAX_PAGES = 3          # cap pagination — runs synchronously in the submit path
_PER_PAGE_HINT = 100

_TWEET_ID_RE = re.compile(r"/status(?:es)?/(\d{5,25})")
_AUTHOR_RE = re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})/status", re.I)

_ACTION_ALIASES = {
    "like": "like", "likes": "like",
    "retweet": "retweet", "retweets": "retweet", "repost": "retweet", "reposts": "retweet",
    "comment": "comment", "comments": "comment", "reply": "comment", "replies": "comment",
    "quote": "quote", "quotes": "quote", "quote_tweet": "quote", "quote_tweets": "quote",
    "follow": "follow", "follows": "follow",
}

# In-process health cache (Guildizer has no Redis dependency here). {key_hash: (status, expires_at)}
_HEALTH_CACHE: dict[str, tuple[str, float]] = {}
_HEALTH_TTL = 300


# ── Key resolution (owner BYO → platform) ─────────────────────────────────────
def _owner_key(owner_user_id) -> str:
    """The guild owner's own account-level twitterapi.io key, if set. Stored
    Fernet-encrypted on users.twitter_api_key_encrypted; account-level by design
    (one key covers all the owner's guilds). Returns "" if none / undecryptable."""
    if not owner_user_id:
        return ""
    # Use an INDEPENDENT session bound to the engine (not the thread-local
    # scoped SessionLocal) — this runs inside web requests where g.db IS the
    # scoped session, and a stray .remove() would dispose the request's session.
    from sqlalchemy.orm import Session
    from database import engine
    from models import User
    from crypto import decrypt_token
    try:
        with Session(engine) as db:
            u = db.get(User, int(owner_user_id))
            enc = getattr(u, "twitter_api_key_encrypted", None) if u else None
            if enc:
                return decrypt_token(enc) or ""
    except Exception:
        log.debug("twitter_verify owner-key lookup failed", exc_info=True)
    return ""


def _platform_key() -> str:
    from config import Config
    return getattr(Config, "TWITTERAPI_IO_KEY", "") or ""


def _key(owner_user_id=None) -> str:
    """Effective key for an owner: their own BYO key first, then the platform key."""
    return _owner_key(owner_user_id) or _platform_key()


def enabled(owner_user_id=None) -> bool:
    """True iff X auto-verify can run for this owner — a key is available."""
    return bool(_key(owner_user_id))


# ── Health / 3-state status ───────────────────────────────────────────────────
def _cached_probe(key: str, *, use_cache=True) -> str:
    """Probe a specific key, cached in-process by a hash of the key (BYO and platform
    cache independently; rotation re-probes). Returns "ok" or "error: <reason>"."""
    if not key:
        return "error: no key"
    import hashlib
    kh = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    now = time.time()
    if use_cache:
        hit = _HEALTH_CACHE.get(kh)
        if hit and hit[1] > now:
            return hit[0]
    status = _probe_key(key)
    _HEALTH_CACHE[kh] = (status, now + _HEALTH_TTL)
    return status


def _probe_key(key: str) -> str:
    """One cheap verified call. tweetId=20 is Jack's first tweet — always public,
    so a valid key reliably yields 200. We read only the HTTP status."""
    try:
        resp = _get("/twitter/tweet/retweeters", {"tweetId": "20"}, key)
    except Exception as e:
        return f"error: {str(e)[:50]}"
    code = resp.status_code
    if code == 200:
        return "ok"
    if code in (401, 403):
        return "error: invalid or unauthorized key"
    if code == 402:
        return "error: insufficient credits"
    if code == 429:
        return "error: rate limited"
    return f"error: status {code}"


def health_check(*, use_cache=True) -> str:
    """Live health probe for the PLATFORM key — "disabled" (no key) / "ok" / "error:.."."""
    key = _platform_key()
    if not key:
        return "disabled"
    return _cached_probe(key, use_cache=use_cache)


def autoverify_status(owner_user_id=None, *, use_cache=True) -> str:
    """Owner-aware 3-state for the campaign-builder chip:
      "live"     — the effective key (BYO or platform) authenticates → auto-verify on
      "rejected" — a key is set but the live probe was rejected → manual fallback
      "disabled" — no key for this owner → manual review
    Account-level + cached, so identical across all the owner's guilds. Never raises."""
    key = _key(owner_user_id)
    if not key:
        return "disabled"
    try:
        return "live" if _cached_probe(key, use_cache=use_cache) == "ok" else "rejected"
    except Exception:
        return "rejected"


# ── URL / handle helpers ──────────────────────────────────────────────────────
def extract_tweet_id(url):
    if not url:
        return None
    m = _TWEET_ID_RE.search(url)
    return m.group(1) if m else None


def extract_author_handle(url):
    if not url:
        return None
    m = _AUTHOR_RE.search(url)
    return m.group(1) if m else None


def normalize_handle(handle):
    """Strip @, whitespace and a profile-URL wrapper → bare username."""
    if not handle:
        return None
    h = str(handle).strip()
    m = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})", h, re.I)
    if m:
        return m.group(1)
    return h.lstrip("@").strip() or None


def _get(path, params, key):
    import requests
    return requests.get(
        f"{_BASE}{path}", params=params,
        headers={"X-API-Key": key}, timeout=_TIMEOUT,
    )


# ── Per-endpoint handle extractors ─────────────────────────────────────────────
def _handles_retweeters(body):
    return [u.get("userName") for u in (body.get("users") or []) if isinstance(u, dict)]


def _handles_tweet_authors(body):
    out = []
    for t in (body.get("tweets") or []):
        if isinstance(t, dict):
            author = t.get("author") or {}
            if isinstance(author, dict):
                out.append(author.get("userName"))
    return out


def _paged_contains(path, tweet_id, handle_lc, key, extractor):
    """Walk up to _MAX_PAGES of a cursor-paginated endpoint for handle_lc. Returns
    "verified" if found, else "unknown" (pagination can't prove a definitive absence)."""
    cursor = ""
    for _ in range(_MAX_PAGES):
        params = {"tweetId": tweet_id}
        if cursor:
            params["cursor"] = cursor
        try:
            resp = _get(path, params, key)
        except Exception as e:
            log.info("twitter_verify paged %s failed: %s", path, e)
            return "unknown"
        if resp.status_code != 200:
            log.info("twitter_verify paged %s status %s", path, resp.status_code)
            return "unknown"
        body = resp.json() or {}
        for h in extractor(body):
            if h and str(h).lstrip("@").strip().lower() == handle_lc:
                return "verified"
        cursor = body.get("next_cursor") or ""
        if not body.get("has_next_page") or not cursor:
            break
    return "unknown"


# ── Verification ──────────────────────────────────────────────────────────────
def verify_action(action, *, username, tweet_id=None, target_handle=None, key=None):
    """Verify a single raid action for one participant.

    Returns (status, detail), status ∈ {"verified","failed","unknown","manual"}.
    "unknown" = couldn't confirm → leave for manual review (safe fallback). Only
    `follow` can return "failed"; `like` returns "manual" (inherently unverifiable)."""
    key = key or _key()
    if not key:
        return "unknown", "X auto-verify not configured"
    handle = normalize_handle(username)
    if not handle:
        return "unknown", "No X username provided"
    handle_lc = handle.lower()
    act = _ACTION_ALIASES.get((action or "").lower())
    if not act:
        return "unknown", f"Unsupported action: {action}"

    if act == "like":
        return "manual", "Likes can't be auto-verified — review manually"

    try:
        if act == "follow":
            tgt = normalize_handle(target_handle)
            if not tgt:
                return "unknown", "No target account to check follow against"
            resp = _get(
                "/twitter/user/check_follow_relationship",
                {"source_user_name": handle, "target_user_name": tgt}, key,
            )
            if resp.status_code != 200:
                return "unknown", "Follow check unavailable"
            body = resp.json() or {}
            data = body.get("data") if isinstance(body.get("data"), dict) else body
            following = data.get("following")
            if following is None:
                following = data.get("is_following")
            if following is True:
                return "verified", f"@{handle} follows @{tgt}"
            if following is False:
                return "failed", f"@{handle} does not follow @{tgt}"
            return "unknown", "Follow status unclear"

        if not tweet_id:
            return "unknown", "No tweet id to check against"

        if act == "retweet":
            return _paged_contains("/twitter/tweet/retweeters", tweet_id, handle_lc, key, _handles_retweeters), None
        if act == "comment":
            return _paged_contains("/twitter/tweet/replies", tweet_id, handle_lc, key, _handles_tweet_authors), None
        if act == "quote":
            return _paged_contains("/twitter/tweet/quotes", tweet_id, handle_lc, key, _handles_tweet_authors), None
    except Exception as e:
        log.info("twitter_verify verify_action(%s) failed: %s", act, e)
        return "unknown", "Verification error"
    return "unknown", None


def verify_raid(task_url, goals, username, *, owner_user_id=None, follow_target=None):
    """Verify every selected raid goal for a participant.

    Returns {"overall": "verified"|"pending", "results": {goal: {status, detail}}}.
    Likes return "manual" and are NON-BLOCKING (a likes-inclusive raid still
    auto-verifies on its provable goals). overall is "verified" only when at least
    one goal verified AND no provable goal came back non-verified. Never auto-rejects."""
    key = _key(owner_user_id)
    tweet_id = extract_tweet_id(task_url)
    target = follow_target or extract_author_handle(task_url)

    results = {}
    requested = {k: v for k, v in (goals or {}).items() if v}
    verified_any = False
    blocked = False
    for gkey in requested:
        status, detail = verify_action(
            gkey, username=username, tweet_id=tweet_id, target_handle=target, key=key,
        )
        results[gkey] = {"status": status, "detail": detail}
        if status == "verified":
            verified_any = True
        elif status == "manual":
            continue
        else:
            blocked = True
            break

    overall = "verified" if (verified_any and not blocked) else "pending"
    return {"overall": overall, "results": results}
