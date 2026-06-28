"""Twitter/X per-user action verification via twitterapi.io (Phase: Raid auto-verify).

This powers real-time verification of raid goals (retweet / comment / follow) for
a SPECIFIC participant — i.e. "did @user actually retweet this tweet?" — using the
low-cost twitterapi.io provider. The same key (`TWITTERAPI_IO_KEY`, resolved
DB-first via secret_vault) already drives the link-existence checks in
engagement_verify.

Verified against the live twitterapi.io API (2026-06):
  - retweets  → GET /twitter/tweet/retweeters?tweetId=<id>  → users[].userName
  - comments  → GET /twitter/tweet/replies?tweetId=<id>     → tweets[].author.userName
  - quotes    → GET /twitter/tweet/quotes?tweetId=<id>       → tweets[].author.userName
  - follow    → GET /twitter/user/check_follow_relationship → data.following (bool)
  - likes     → NOT SUPPORTED by twitterapi.io (X privatized likes in 2024; there
                is no read endpoint for who liked a tweet) → always manual review
All list endpoints paginate with has_next_page / next_cursor and use the
`X-API-Key` header.

SAFETY CONTRACT — this module can only ever UPGRADE a submission to verified on a
positive match. It never auto-rejects on uncertainty: any missing key, network
error, unexpected response shape, unsupported action, or "not found in the pages
we fetched" returns "unknown", which the caller treats as "leave pending for
manual review". The ONLY case that returns "failed" is the follow relationship
endpoint giving a single, authoritative negative. This makes auto-verify purely
additive: it saves admins work on true positives and never wrongly approves or
wrongly rejects.

Likes are a special case: they return the distinct status "manual" (not "unknown")
because they are *inherently* unverifiable — X has no likers endpoint, so no key,
retry or pagination could ever prove them. verify_raid treats "manual" as
NON-BLOCKING so a likes-inclusive raid still auto-verifies on its provable goals
(follow / retweet / quote) and leaves only the likes for an admin to eyeball.

A platform-wide admin kill-switch (`engagement_x_autoverify_enabled` feature flag)
gates the whole thing, and per-owner Pro/Enterprise gating is enforced at campaign
create/update time in engagement.py — this module just does the lookups.
"""

import logging
import re

logger = logging.getLogger(__name__)

_BASE = "https://api.twitterapi.io"
_TIMEOUT = 8            # seconds per call
_MAX_PAGES = 3          # cap pagination — this runs synchronously in the submit path
_PER_PAGE_HINT = 100    # twitterapi.io returns ~100 users/page

_TWEET_ID_RE = re.compile(r"/status(?:es)?/(\d{5,25})")
# Author handle is the path segment immediately before /status/.
_AUTHOR_RE = re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})/status", re.I)

# Map raid-goal keys (and common synonyms) to a canonical action.
_ACTION_ALIASES = {
    "like": "like", "likes": "like",
    "retweet": "retweet", "retweets": "retweet", "repost": "retweet", "reposts": "retweet",
    "comment": "comment", "comments": "comment", "reply": "comment", "replies": "comment",
    "quote": "quote", "quotes": "quote", "quote_tweet": "quote", "quote_tweets": "quote",
    "follow": "follow", "follows": "follow",
}


def _key():
    """Resolve the twitterapi.io key DB-first (admin vault) with env fallback."""
    try:
        from . import secret_vault as _sv
        return _sv.get_secret("TWITTERAPI_IO_KEY")
    except Exception:
        from .config import Config
        return getattr(Config, "TWITTERAPI_IO_KEY", "") or ""


def enabled():
    """True iff X auto-verify can run: the admin kill-switch is on AND a key is set.

    The feature flag lets an admin enable/disable the whole feature from the panel
    at any time without a redeploy; with it off, every raid degrades to manual
    review even for Pro owners with a key configured."""
    try:
        from . import platform_config
        if not platform_config.is_feature_enabled("engagement_x_autoverify_enabled", True):
            return False
    except Exception:
        pass  # if the flag system is unavailable, fall back to key presence
    return bool(_key())


def health_check(*, use_cache=True, cache_ttl=300):
    """Live, Redis-cached health probe for the twitterapi.io key — for the admin
    System Health page. Never raises. Returns one of:

      "disabled"          — no key configured (optional feature, NOT an error)
      "ok"                — the key authenticates against the live API
      "error: <reason>"   — key is configured but the API rejected it / is down

    The result is cached in Redis for `cache_ttl` seconds so repeated health-page
    polls don't burn twitterapi.io credits on every refresh.
    """
    key = _key()
    if not key:
        return "disabled"

    cache_key = "twitterapi_io:health"
    r = None
    if use_cache:
        try:
            import redis as _redis
            from .config import Config
            r = _redis.from_url(Config.REDIS_URL or "redis://localhost:6379/0", socket_timeout=2)
            cached = r.get(cache_key)
            if cached:
                return cached.decode() if isinstance(cached, bytes) else str(cached)
        except Exception:
            r = None

    status = _probe_key(key)
    if r is not None:
        try:
            r.setex(cache_key, cache_ttl, status)
        except Exception:
            pass
    return status


def _probe_key(key):
    """One cheap, verified call to confirm the key authenticates. We only read the
    HTTP status, not the body. tweetId=20 is Jack Dorsey's first tweet — a stable,
    always-public id, so a valid key reliably yields 200."""
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
    """Strip @, surrounding whitespace and a profile-URL wrapper → bare username."""
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
# Precise (not a blind deep-scan) so we only ever match the ACTUAL actor —
# the retweeter / the replier — never a nested quoted/mentioned author.

def _handles_retweeters(body):
    return [u.get("userName") for u in (body.get("users") or []) if isinstance(u, dict)]


# Replies and quotes share the same shape: tweets[].author.userName (the actor).
def _handles_tweet_authors(body):
    out = []
    for t in (body.get("tweets") or []):
        if isinstance(t, dict):
            author = t.get("author") or {}
            if isinstance(author, dict):
                out.append(author.get("userName"))
    return out


def _paged_contains(path, tweet_id, handle_lc, key, extractor):
    """Walk up to _MAX_PAGES of a cursor-paginated list endpoint, pulling actor
    handles via `extractor`, looking for handle_lc. Returns "verified" if found,
    else "unknown" (pagination means we can't prove a definitive absence)."""
    cursor = ""
    for _ in range(_MAX_PAGES):
        params = {"tweetId": tweet_id}
        if cursor:
            params["cursor"] = cursor
        try:
            resp = _get(path, params, key)
        except Exception as e:
            logger.info("twitter_verify paged %s failed: %s", path, e)
            return "unknown"
        if resp.status_code != 200:
            logger.info("twitter_verify paged %s status %s", path, resp.status_code)
            return "unknown"
        body = resp.json() or {}
        for h in extractor(body):
            if h and str(h).lstrip("@").strip().lower() == handle_lc:
                return "verified"
        cursor = body.get("next_cursor") or ""
        if not body.get("has_next_page") or not cursor:
            break
    return "unknown"


def verify_action(action, *, username, tweet_id=None, target_handle=None, key=None):
    """Verify a single raid action for one participant.

    Returns (status, detail) where status ∈ {"verified", "failed", "unknown"}.
    "unknown" means "couldn't confirm — leave for manual review" and is the safe
    fallback for every error/uncertainty. Only `follow` can return "failed".
    """
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

    # twitterapi.io exposes no likers endpoint, so a like can't be auto-verified.
    # Return the distinct "manual" status (not "unknown"): verify_raid uses it to
    # leave likes for manual review WITHOUT blocking the raid's provable goals.
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
            # Real shape is {"data": {"following": bool, ...}}; tolerate a flat
            # shape too. NB: read explicitly — an `or` chain would collapse a
            # legitimate False into None and lose the authoritative negative.
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
        logger.info("twitter_verify verify_action(%s) failed: %s", act, e)
        return "unknown", "Verification error"
    return "unknown", None


def verify_raid(campaign, username, *, goals=None):
    """Verify every selected raid goal for a participant.

    Returns {"overall": "verified"|"pending", "results": {goal: {status, detail}}},
    where each goal status is "verified", "failed", "unknown" or "manual".

    Likes return "manual" (X has no likers endpoint) and are treated as
    NON-BLOCKING: a likes-inclusive raid still auto-verifies on its provable goals
    (follow / retweet / quote), leaving only the likes for an admin. Without this,
    every raid that asked for likes would degrade to full manual review.

    overall is "verified" only when at least one goal actually verified AND no
    provable goal came back non-verified — a "failed"/"unknown" blocks it. A raid
    of likes ALONE therefore stays "pending" (nothing was provable). We never
    auto-reject; a blocking goal just leaves the whole submission for review. Stops
    at the first blocking (non-verified, non-manual) goal to bound latency.
    """
    key = _key()
    settings = campaign.settings or {}
    goals = goals or (settings.get("raid_goals") or {})
    tweet_id = extract_tweet_id(campaign.task_url)
    target = settings.get("raid_follow_target") or extract_author_handle(campaign.task_url)

    results = {}
    requested = {k: v for k, v in goals.items() if v}
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
            continue  # likes — can't prove, but don't block the provable goals
        else:
            blocked = True  # "failed"/"unknown" → leave the submission for review
            break

    overall = "verified" if (verified_any and not blocked) else "pending"
    return {"overall": overall, "results": results}
