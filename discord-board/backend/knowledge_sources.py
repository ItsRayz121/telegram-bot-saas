"""External-source ingestion for the Guildizer AI knowledge base.

An admin registers a URL (a website, an X handle or a YouTube channel) and clicks
"Sync now" in the dashboard, or opts the source into a schedule. This module turns
that URL into plain text; kb_sources.sync_source runs the result through the same
chunk + embed pipeline as an uploaded file.

Copied (not imported) from Telegizer's knowledge_sources.py, with the Telegram
channel connector dropped and credentials read from the Discord service env.

Fetches happen only on an explicit admin click or an opt-in per-source schedule,
never in response to a member's question.

Every fetcher is defensive: a network error, an unexpected response shape or a
missing credential returns a result with ok=False and a human-readable reason
instead of raising, so a sync failure is always a clear dashboard message.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from config import Config

log = logging.getLogger("guildizer.kb.sources")

_TIMEOUT = 12                  # seconds; runs inside a request handler or a worker thread
_MAX_CHARS = 50_000            # cap ingested text per source so embedding cost stays bounded
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_MAX_REDIRECTS = 5
_USER_AGENT = "Mozilla/5.0 (compatible; GuildizerBot/1.0; +https://telegizer.com)"

SOURCE_TYPES = ("website", "twitter", "youtube")


class _UnsafeUrlError(Exception):
    """A URL that must not be fetched. Only a generic reason is ever shown."""


def _assert_public_host(url: str) -> None:
    """Reject anything that is not a plain http(s) URL resolving only to public IPs.
    This admin-supplied URL is fetched server-side, so without this check an admin
    could point a source at cloud metadata (169.254.169.254), localhost or an
    internal Railway service and have the response reflected back (SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise _UnsafeUrlError("Only http:// and https:// URLs are allowed.")
    host = parsed.hostname
    if not host:
        raise _UnsafeUrlError("That URL has no host.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise _UnsafeUrlError("Could not resolve that host.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            raise _UnsafeUrlError("That URL points to a non-public address, which isn't allowed.")


def _safe_get(url: str, *, max_redirects: int = _MAX_REDIRECTS):
    """requests.get where every hop (including redirects) is host-validated and the
    body is capped, so a redirect to an internal address is caught too."""
    import requests

    for _ in range(max_redirects + 1):
        _assert_public_host(url)
        resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT},
                            allow_redirects=False, stream=True)
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise _UnsafeUrlError("Redirected with no destination.")
            url = urljoin(url, location)
            continue
        chunks, total = [], 0
        for chunk in resp.iter_content(chunk_size=8192):
            total += len(chunk)
            if total > _MAX_RESPONSE_BYTES:
                resp.close()
                raise _UnsafeUrlError("That page's response was too large.")
            chunks.append(chunk)
        resp._content = b"".join(chunks)
        return resp
    raise _UnsafeUrlError("Too many redirects.")


def detect_source_type(url: str) -> str:
    """Best-effort guess from the URL so the admin does not have to pick a type."""
    low = (url or "").lower()
    if "youtube.com" in low or "youtu.be" in low:
        return "youtube"
    if "x.com/" in low or "twitter.com/" in low:
        return "twitter"
    return "website"


def _result(ok, text="", error=None, **extra):
    """Uniform connector result.

    published_at: newest content date the PROVIDER reported (naive UTC) or None.
        Never filled with the fetch time.
    incomplete:   True when a page/post budget stopped the import early.
    state:        opaque connector state to persist (X: cursor, high-water id, posts).
    usage:        {"requests": n, "resources": n}, provider calls actually made.
    rate_limited_until / fatal: set on a 429 / on invalid or exhausted credentials.
    """
    r = {
        "ok": ok, "text": text, "error": error, "published_at": None, "incomplete": False,
        "state": None, "usage": {"requests": 0, "resources": 0},
        "rate_limited_until": None, "fatal": False,
    }
    r.update(extra)
    return r


def fetch_source(source_type: str, url: str, state=None, max_pages: int = 3, initial_cap: int = 60):
    """Fetch a source's current content. Returns a dict (see _result). Never raises."""
    try:
        if source_type == "youtube":
            return _fetch_youtube(url)
        if source_type == "twitter":
            return _fetch_twitter(url, state=state, max_pages=max_pages, initial_cap=initial_cap)
        return _fetch_website(url)
    except Exception as exc:  # noqa: BLE001
        log.error("fetch_source(%s, %s) failed: %s", source_type, url, exc)
        return _result(False, error="Sync failed unexpectedly - check the server logs.")


# ── helpers ────────────────────────────────────────────────────────────────────

_LOGIN_HINT = re.compile(
    r"(log\s?in|sign\s?in|sign\s?up|create (an )?account|enable javascript|"
    r"verify you are human|access denied|just a moment)", re.I)


def _looks_like_login_page(title: str, text: str) -> bool:
    """A login wall / bot challenge is not knowledge. Short pages that are mostly
    login wording are rejected so they never replace a good version."""
    if len(text) > 1500:
        return False
    return bool(_LOGIN_HINT.search(title or "")) or len(_LOGIN_HINT.findall(text)) >= 2


def _parse_dt(value):
    """Provider timestamp -> naive UTC datetime, or None if it cannot be read."""
    if not value:
        return None
    value = str(value).strip()
    dt = None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(value)
        except Exception:  # noqa: BLE001
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ── website ────────────────────────────────────────────────────────────────────

def _fetch_website(url: str):
    """Generic page scrape."""
    import requests
    from bs4 import BeautifulSoup

    try:
        resp = _safe_get(url)
    except _UnsafeUrlError as exc:
        return _result(False, error=str(exc))
    except requests.RequestException as exc:
        return _result(False, error=f"Could not reach that URL: {exc}")
    if resp.status_code != 200:
        return _result(False, error=f"That URL returned HTTP {resp.status_code}.")

    soup = BeautifulSoup(resp.text, "html.parser")
    # Only an explicit page-level date counts as a publication date.
    published = None
    for attrs in ({"property": "article:modified_time"}, {"property": "article:published_time"},
                  {"itemprop": "dateModified"}, {"itemprop": "datePublished"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            published = _parse_dt(tag["content"])
            if published:
                break
    for tag in soup(["script", "style", "nav", "footer", "noscript", "header", "svg"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    lines = [ln.strip() for ln in soup.get_text(separator="\n").splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    if not text:
        return _result(False, error="That page had no extractable text.")
    if _looks_like_login_page(title, text):
        return _result(False, error="That page looks like a login or bot-check page, not content. Nothing was changed.")
    combined = (f"{title}\n\n{text}" if title else text)[:_MAX_CHARS]
    return _result(True, combined, published_at=published)


# ── X / Twitter (twitterapi.io, incremental) ──────────────────────────────────

_X_ENDPOINT = "https://api.twitterapi.io/twitter/user/last_tweets"
_X_MAX_RETAINED_POSTS = 200
_X_MAX_BACKOFF_SECONDS = 48 * 3600   # bound on a provider-supplied reset time


def x_handle(url: str):
    m = re.search(r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})", url or "", re.I)
    if m:
        return m.group(1).lower()
    # A bare handle ("@foo" / "foo") is accepted; anything else (a link with no
    # handle in it) is not a handle.
    bare = re.fullmatch(r"@?([A-Za-z0-9_]{1,15})", (url or "").strip())
    return bare.group(1).lower() if bare else None


def _post_id(t):
    try:
        return int(str(t.get("id") or t.get("id_str") or ""))
    except ValueError:
        return None


def _render_posts(posts):
    ordered = sorted(posts, key=lambda p: int(p["id"]), reverse=True)
    out = []
    for p in ordered:
        day = (p.get("created_at") or "")[:10]
        out.append((f"[{day}] " if day else "") + p["text"])
    return "\n\n---\n\n".join(out)[:_MAX_CHARS]


def _fetch_twitter(url: str, state=None, max_pages: int = 3, initial_cap: int = 60):
    """Incremental recent-posts import for a handle.

    - Bounded: at most ``max_pages`` provider requests per run and ``initial_cap``
      posts on the very first import (that bounded first import is complete by
      design; it is NOT a partial import).
    - Incremental: stops at the high-water post id once the first page (always read
      in full, to reconcile edits and deletions among the latest posts) is done.
    - Resumable: when the page budget ends before reaching the high-water mark, the
      cursor and the newest id seen are kept in ``state`` and the completed
      high-water mark is NOT advanced, so no unprocessed post is skipped.
    - Retained: posts are merged into the retained feed (bounded), not wiped.
    - Failure handling: 429 -> honour Retry-After (bounded), 401/402/403 -> fatal,
      no retries inside a run.
    """
    import requests

    username = x_handle(url)
    if not username:
        return _result(False, error="Could not find a handle in that URL.")
    key = Config.TWITTERAPI_IO_KEY
    if not key:
        return _result(False, fatal=True,
                       error="No twitterapi.io API key is configured on this platform yet.")

    st = dict(state or {})
    posts = {str(p["id"]): dict(p) for p in (st.get("posts") or []) if p.get("id")}
    high_water = int(st["high_water"]) if st.get("high_water") else None
    cursor = st.get("cursor") or None
    pending_max = int(st["pending_max_id"]) if st.get("pending_max_id") else None
    first_import = high_water is None and not st.get("posts")
    resuming = bool(cursor)   # a resumed page is NOT the top of the timeline

    requests_made = resources = pages_read = 0
    first_page_ids = None
    complete = False

    while pages_read < max_pages:
        params = {"userName": username}
        if cursor:
            params["cursor"] = cursor
        try:
            resp = requests.get(_X_ENDPOINT, params=params, headers={"X-API-Key": key}, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            return _result(False, error=f"Could not reach twitterapi.io: {exc}",
                           usage={"requests": requests_made + 1, "resources": resources}, state=st)
        requests_made += 1
        if resp.status_code == 429:
            try:
                wait = int(float(resp.headers.get("Retry-After") or resp.headers.get("x-rate-limit-reset-seconds") or 900))
            except ValueError:
                wait = 900
            wait = max(60, min(wait, _X_MAX_BACKOFF_SECONDS))
            return _result(False, error="twitterapi.io rate limit reached; the next attempt is delayed until it resets.",
                           rate_limited_until=datetime.utcnow() + timedelta(seconds=wait),
                           usage={"requests": requests_made, "resources": resources}, state=st)
        if resp.status_code in (401, 402, 403):
            return _result(False, fatal=True,
                           error=f"twitterapi.io rejected the platform credential (HTTP {resp.status_code}). Sync stopped.",
                           usage={"requests": requests_made, "resources": resources}, state=st)
        if resp.status_code != 200:
            return _result(False, error=f"twitterapi.io returned HTTP {resp.status_code}.",
                           usage={"requests": requests_made, "resources": resources}, state=st)
        try:
            body = resp.json() or {}
        except ValueError:
            return _result(False, error="twitterapi.io returned an unexpected response.",
                           usage={"requests": requests_made, "resources": resources}, state=st)

        tweets = (body.get("tweets") or (body.get("data") or {}).get("tweets")
                  or (body.get("data") if isinstance(body.get("data"), list) else None) or [])
        if not isinstance(tweets, list):
            tweets = []
        pages_read += 1
        resources += len(tweets)

        page_ids, hit_old = [], False
        for t in tweets:
            if not isinstance(t, dict):
                continue
            pid = _post_id(t)
            txt = t.get("text") or t.get("full_text") or t.get("fullText")
            if pid is None or not txt:
                continue
            page_ids.append(pid)
            created = _parse_dt(t.get("createdAt") or t.get("created_at"))
            if pending_max is None or pid > pending_max:
                pending_max = pid
            if not (pages_read == 1 and not resuming) and high_water is not None and pid <= high_water:
                hit_old = True
                continue
            posts[str(pid)] = {"id": str(pid), "text": str(txt).strip(),
                               "created_at": created.isoformat() if created else None}
        if pages_read == 1 and not resuming:
            first_page_ids = page_ids

        has_next = bool(body.get("has_next_page"))
        next_cursor = body.get("next_cursor") or None
        if not page_ids or hit_old or not has_next or not next_cursor:
            complete, cursor = True, None
            break
        if first_import and len(posts) >= initial_cap:
            complete, cursor = True, None   # bounded first import: complete by design
            break
        if pages_read == 1 and not resuming and high_water is not None and page_ids and min(page_ids) <= high_water:
            complete, cursor = True, None
            break
        cursor = next_cursor

    # Reconcile the latest window: a retained post that lies inside the id range of
    # the page just read in full, but is absent from it, was deleted.
    if first_page_ids:
        lo, hi = min(first_page_ids), max(first_page_ids)
        keep = set(map(str, first_page_ids))
        for pid in [k for k in posts if lo <= int(k) <= hi and k not in keep]:
            posts.pop(pid, None)

    if len(posts) > _X_MAX_RETAINED_POSTS:
        for pid in sorted(posts, key=int)[: len(posts) - _X_MAX_RETAINED_POSTS]:
            posts.pop(pid, None)

    new_state = {"posts": list(posts.values())}
    if complete:
        new_state["high_water"] = str(max([int(pending_max or 0), int(high_water or 0)]) or "") or None
        new_state["cursor"] = None
        new_state["pending_max_id"] = None
    else:
        new_state["high_water"] = str(high_water) if high_water else None
        new_state["cursor"] = cursor
        new_state["pending_max_id"] = str(pending_max) if pending_max else None

    usage = {"requests": requests_made, "resources": resources}
    if not posts:
        return _result(False, error="No recent posts found for that handle.", usage=usage, state=new_state)
    dates = [p["created_at"] for p in posts.values() if p.get("created_at")]
    published = _parse_dt(max(dates)) if dates else None
    return _result(True, _render_posts(list(posts.values())), published_at=published,
                   incomplete=not complete, state=new_state, usage=usage)


# ── YouTube ────────────────────────────────────────────────────────────────────

def _youtube_key() -> str:
    import os
    return os.getenv("YOUTUBE_API_KEY", "")


def _fetch_youtube(url: str):
    """Recent video titles + descriptions via the YouTube Data API."""
    import requests

    key = _youtube_key()
    if not key:
        return _result(False, error="No YouTube Data API key is configured on this platform yet.")

    channel_id = _resolve_youtube_channel_id(url, key)
    if not channel_id:
        return _result(False, error="Could not resolve a YouTube channel from that URL.")

    try:
        ch_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "contentDetails", "id": channel_id, "key": key}, timeout=_TIMEOUT)
        if ch_resp.status_code != 200:
            return _result(False, error=f"YouTube Data API returned HTTP {ch_resp.status_code} - check the configured API key/quota.")
        items = (ch_resp.json() or {}).get("items") or []
        uploads = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads") if items else None
        if not uploads:
            return _result(False, error="That channel has no public uploads.")
        pl_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "snippet", "playlistId": uploads, "maxResults": 15, "key": key}, timeout=_TIMEOUT)
        if pl_resp.status_code != 200:
            return _result(False, error=f"YouTube Data API returned HTTP {pl_resp.status_code} - check the configured API key/quota.")
        pl_items = (pl_resp.json() or {}).get("items") or []
    except requests.RequestException as exc:
        return _result(False, error=f"Could not reach YouTube: {exc}")

    videos, newest = [], None
    for it in pl_items:
        snip = it.get("snippet") or {}
        title = (snip.get("title") or "").strip()
        desc = (snip.get("description") or "").strip()
        when = _parse_dt(snip.get("publishedAt"))
        if when and (newest is None or when > newest):
            newest = when
        if title:
            videos.append((f"[{when.date().isoformat()}] " if when else "") + f"{title}\n{desc}".strip())
    if not videos:
        return _result(False, error="No recent videos found for that channel.")
    return _result(True, "\n\n---\n\n".join(videos)[:_MAX_CHARS], published_at=newest,
                   usage={"requests": 2, "resources": len(pl_items)})


def _resolve_youtube_channel_id(url: str, api_key: str):
    import requests

    m = re.search(r"youtube\.com/channel/([A-Za-z0-9_-]{10,40})", url, re.I)
    if m:
        return m.group(1)
    handle_m = re.search(r"youtube\.com/(?:@|c/|user/)([A-Za-z0-9_.-]{2,60})", url, re.I)
    if not handle_m and "youtube.com" not in url.lower() and "youtu.be" not in url.lower():
        handle_m = re.match(r"^@?([A-Za-z0-9_.-]{2,60})$", url.strip())
    handle = handle_m.group(1) if handle_m else None
    if not handle:
        return None
    try:
        resp = requests.get("https://www.googleapis.com/youtube/v3/channels",
                            params={"part": "id", "forHandle": handle, "key": api_key}, timeout=_TIMEOUT)
        items = (resp.json() or {}).get("items") or []
        if items:
            return items[0]["id"]
    except requests.RequestException:
        pass
    try:
        resp = requests.get("https://www.googleapis.com/youtube/v3/search",
                            params={"part": "snippet", "q": handle, "type": "channel", "maxResults": 1, "key": api_key},
                            timeout=_TIMEOUT)
        items = (resp.json() or {}).get("items") or []
        if items:
            return items[0]["snippet"]["channelId"]
    except requests.RequestException:
        pass
    return None
