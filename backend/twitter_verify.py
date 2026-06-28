"""Twitter/X per-user action verification via twitterapi.io (Phase: Raid auto-verify).

This powers real-time verification of raid goals (like / retweet / comment /
follow) for a SPECIFIC participant — i.e. "did @user actually retweet this
tweet?" — using the low-cost twitterapi.io provider. The same key
(`TWITTERAPI_IO_KEY`, resolved DB-first via secret_vault) already drives the
link-existence checks in engagement_verify.

SAFETY CONTRACT — this module can only ever UPGRADE a submission to verified on a
positive match. It never auto-rejects on uncertainty: any missing key, network
error, unexpected response shape, or "not found in the pages we fetched" returns
"unknown", which the caller treats as "leave pending for manual review". The only
case that returns "failed" is the follow relationship endpoint giving a single,
authoritative negative answer. This makes auto-verify purely additive: it saves
admins work on true positives and never wrongly approves or wrongly rejects.

Gating (free vs Pro/Enterprise) is enforced at campaign create/update time in
engagement.py — this module just does the lookups when asked.
"""

import logging
import re

logger = logging.getLogger(__name__)

_BASE = "https://api.twitterapi.io"
_TIMEOUT = 6
_MAX_PAGES = 5          # cap pagination so one verify never hammers the API
_PAGE_SLEEP = 0.0       # twitterapi.io is paid/rate-limited; keep it tight

_TWEET_ID_RE = re.compile(r"/status(?:es)?/(\d{5,25})")
# Author handle is the path segment immediately before /status/.
_AUTHOR_RE = re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})/status", re.I)

# Map raid-goal keys (and common synonyms) to a canonical action.
_ACTION_ALIASES = {
    "like": "like", "likes": "like",
    "retweet": "retweet", "retweets": "retweet", "repost": "retweet", "reposts": "retweet",
    "comment": "comment", "comments": "comment", "reply": "comment", "replies": "comment",
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
    """True iff a twitterapi.io key is configured (so auto-verify can run)."""
    return bool(_key())


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


def _json_contains_handle(obj, handle_lc):
    """Recursively scan a JSON blob for a username/screen_name equal to handle_lc.
    Defensive against twitterapi.io shape differences across endpoints."""
    USERNAME_KEYS = ("username", "user_name", "screen_name", "screenname", "handle")
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(v, str) and k.lower() in USERNAME_KEYS:
                    if v.lstrip("@").strip().lower() == handle_lc:
                        return True
                elif isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


def _paged_contains(path, id_param, tweet_id, handle_lc, key):
    """Walk up to _MAX_PAGES of a cursor-paginated list endpoint looking for the
    handle. Returns "verified" if found, else "unknown" (never a definitive
    negative — pagination means we can't prove absence)."""
    cursor = None
    for _ in range(_MAX_PAGES):
        params = {id_param: tweet_id}
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
        if _json_contains_handle(body, handle_lc):
            return "verified"
        # Advance the cursor if the API exposes one; stop otherwise.
        cursor = body.get("next_cursor") or body.get("cursor")
        has_next = body.get("has_next_page")
        if not cursor or has_next is False:
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
            # Accept a few likely shapes for the "is following" boolean.
            following = (
                body.get("following")
                or body.get("is_following")
                or (body.get("data") or {}).get("following")
                or (body.get("relationship") or {}).get("following")
            )
            if following is True:
                return "verified", f"@{handle} follows @{tgt}"
            if following is False:
                return "failed", f"@{handle} does not follow @{tgt}"
            return "unknown", "Follow status unclear"

        if not tweet_id:
            return "unknown", "No tweet id to check against"

        if act == "retweet":
            return _paged_contains("/twitter/tweet/retweeters", "tweetId", tweet_id, handle_lc, key), None
        if act == "comment":
            return _paged_contains("/twitter/tweet/replies", "tweetId", tweet_id, handle_lc, key), None
        if act == "like":
            # Likers are the least reliably exposed by X; attempt, else unknown.
            return _paged_contains("/twitter/tweet/likers", "tweetId", tweet_id, handle_lc, key), None
    except Exception as e:
        logger.info("twitter_verify verify_action(%s) failed: %s", act, e)
        return "unknown", "Verification error"
    return "unknown", None


def verify_raid(campaign, username, *, goals=None):
    """Verify every selected raid goal for a participant.

    Returns a dict: {
        "overall": "verified" | "pending",
        "results": {goal_key: {"status": ..., "detail": ...}},
    }
    overall is "verified" only when EVERY selected goal verified; otherwise
    "pending" so an admin still reviews (we never auto-reject).
    """
    key = _key()
    settings = campaign.settings or {}
    goals = goals or (settings.get("raid_goals") or {})
    tweet_id = extract_tweet_id(campaign.task_url)
    target = settings.get("raid_follow_target") or extract_author_handle(campaign.task_url)

    results = {}
    all_verified = bool(goals)
    for gkey, gval in goals.items():
        try:
            if not gval:  # goal not requested (0 / falsy)
                continue
        except Exception:
            pass
        status, detail = verify_action(
            gkey, username=username, tweet_id=tweet_id, target_handle=target, key=key,
        )
        results[gkey] = {"status": status, "detail": detail}
        if status != "verified":
            all_verified = False

    return {"overall": "verified" if (all_verified and results) else "pending", "results": results}
