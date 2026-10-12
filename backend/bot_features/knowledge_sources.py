"""External-source ingestion for the AI Knowledge Base.

An admin registers a URL (a website, an official Telegram channel, an X/Twitter
handle, a YouTube channel, or literally any other page) and clicks "Sync now" in
the dashboard. This module turns that URL into plain text; the caller
(KnowledgeBaseSystem.process_external_source) runs the result through the same
chunk+embed pipeline as an uploaded file.

Fetches happen only on an explicit admin click ("Sync now") or on an opt-in,
per-source schedule (see knowledge_sync.py) - never in response to a member's
question. Existing sources are Manual until an owner chooses a schedule.

Every fetcher is defensive: a network error, an unexpected response shape, or a
missing credential returns (False, <human-readable reason>) instead of raising —
a sync failure should always be a clear dashboard message, never a 500.
"""
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

_TIMEOUT = 12                  # seconds — runs synchronously inside a request handler
_MAX_CHARS = 50_000            # cap ingested text per source so embedding cost stays bounded
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # stop reading a response body past 5MB
_MAX_REDIRECTS = 5
_USER_AGENT = "Mozilla/5.0 (compatible; TelegizerBot/1.0; +https://telegizer.com)"

SOURCE_TYPES = ("website", "telegram", "twitter", "youtube")


class _UnsafeUrlError(Exception):
    """Raised when a URL resolves to a non-public address — never surfaced
    verbatim to the caller with internal detail, just a generic reason."""


def _assert_public_host(url: str):
    """Reject anything that isn't a plain http(s) URL resolving only to public
    IP addresses — this admin-supplied URL is fetched server-side, so without
    this check an admin could point a source at cloud metadata endpoints
    (169.254.169.254), localhost, or an internal Railway service and have the
    scraped response reflected back through the dashboard (SSRF)."""
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
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            raise _UnsafeUrlError("That URL points to a non-public address, which isn't allowed.")


def _safe_get(url: str, *, max_redirects: int = _MAX_REDIRECTS):
    """requests.get, but every hop (including redirects) is host-validated and
    the body is capped at _MAX_RESPONSE_BYTES — a redirect to an internal
    address only this second check (not the initial-URL one) would catch."""
    import requests

    for _ in range(max_redirects + 1):
        _assert_public_host(url)
        resp = requests.get(
            url, timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT},
            allow_redirects=False, stream=True,
        )
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise _UnsafeUrlError("Redirected with no destination.")
            url = urljoin(url, location)
            continue

        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=8192):
            total += len(chunk)
            if total > _MAX_RESPONSE_BYTES:
                resp.close()
                raise _UnsafeUrlError("That page's response was too large.")
            chunks.append(chunk)
        resp._content = b"".join(chunks)  # so resp.text below decodes what we already read
        return resp
    raise _UnsafeUrlError("Too many redirects.")


def detect_source_type(url: str) -> str:
    """Best-effort guess from the URL so the admin doesn't have to pick a type."""
    low = (url or "").lower()
    if "youtube.com" in low or "youtu.be" in low:
        return "youtube"
    if "t.me/" in low or "telegram.me/" in low:
        return "telegram"
    if "x.com/" in low or "twitter.com/" in low:
        return "twitter"
    return "website"


def _result(ok, text="", error=None, **extra):
    """Uniform connector result.

    published_at: newest content date the PROVIDER reported (naive UTC datetime) or
        None when it did not report one. Never filled with the fetch time.
    incomplete:   True when a page/post budget stopped the import early.
    state:        opaque connector state to persist (X: cursor, high-water id, posts).
    usage:        {"requests": n, "resources": n} - provider calls actually made.
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
        if source_type == "telegram":
            return _fetch_telegram_channel(url)
        if source_type == "twitter":
            return _fetch_twitter(url, state=state, max_pages=max_pages, initial_cap=initial_cap)
        return _fetch_website(url)
    except Exception as exc:
        logger.error("knowledge_sources.fetch_source(%s, %s) failed: %s", source_type, url, exc)
        return _result(False, error="Sync failed unexpectedly - check the server logs.")


def sync_source(source_type: str, url: str):
    """Back-compat wrapper: (ok, text_or_reason)."""
    r = fetch_source(source_type, url)
    return (True, r["text"]) if r["ok"] else (False, r["error"])


# ── helpers ────────────────────────────────────────────────────────────────────

_LOGIN_HINT = re.compile(
    r"(log\s?in|sign\s?in|sign\s?up|create (an )?account|enable javascript|verify you are human|"
    r"access denied|just a moment)", re.I)


def _looks_like_login_page(title: str, text: str) -> bool:
    """A login wall / bot challenge is not knowledge. Short pages that are mostly
    login wording are rejected so they never replace a good version."""
    if len(text) > 1500:
        return False
    return bool(_LOGIN_HINT.search(title or "")) or len(_LOGIN_HINT.findall(text)) >= 2


def _parse_dt(value):
    """Provider timestamp -> naive UTC datetime, or None if it cannot be read."""
    from datetime import datetime, timezone
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
        except Exception:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ── website ────────────────────────────────────────────────────────────────────

def _fetch_website(url: str):
    """Generic page scrape. Also the fallback for the 'any other' source type."""
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
    body_text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in body_text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    if not text:
        return _result(False, error="That page had no extractable text.")
    if _looks_like_login_page(title, text):
        return _result(False, error="That page looks like a login or bot-check page, not content. Nothing was changed.")
    combined = (f"{title}\n\n{text}" if title else text)[:_MAX_CHARS]
    return _result(True, combined, published_at=published)


# ── Telegram public channel ───────────────────────────────────────────────────

def _fetch_telegram_channel(url: str):
    """Public channels only - reads the same public HTML preview Telegram serves
    at t.me/s/<username>. Needs no bot admin rights, no MTProto user session and
    no extra credentials (a private channel would need a logged-in user session,
    which this project's Anti-Ban Rule treats as high-risk)."""
    import requests
    from bs4 import BeautifulSoup

    m = re.search(r"t(?:elegram)?\.me/(?:s/)?([A-Za-z0-9_]{3,64})", url, re.I)
    if not m:
        return _result(False, error="Could not find a channel username in that URL. Use a link like https://t.me/yourchannel.")
    username = m.group(1)

    try:
        resp = _safe_get(f"https://t.me/s/{username}")
    except _UnsafeUrlError as exc:
        return _result(False, error=str(exc))
    except requests.RequestException as exc:
        return _result(False, error=f"Could not reach Telegram: {exc}")
    if resp.status_code != 200:
        return _result(False, error="That channel is private, doesn't exist, or has no public preview.")

    soup = BeautifulSoup(resp.text, "html.parser")
    posts, newest = [], None
    for wrap in soup.select(".tgme_widget_message"):
        body = wrap.select_one(".tgme_widget_message_text")
        txt = body.get_text(separator="\n").strip() if body else ""
        if not txt:
            continue
        tm = wrap.select_one("time[datetime]")
        when = _parse_dt(tm["datetime"]) if tm else None
        if when and (newest is None or when > newest):
            newest = when
        posts.append((f"[{when.date().isoformat()}] " if when else "") + txt)
    if not posts:
        return _result(False, error="No public posts found for that channel.")
    return _result(True, "\n\n---\n\n".join(posts)[:_MAX_CHARS], published_at=newest)


# ── X / Twitter (twitterapi.io, incremental) ──────────────────────────────────

_X_ENDPOINT = "https://api.twitterapi.io/twitter/user/last_tweets"
_X_MAX_RETAINED_POSTS = 200
_X_MAX_BACKOFF_SECONDS = 48 * 3600   # bound on a provider-supplied reset time


def x_handle(url: str):
    m = re.search(r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})", url or "", re.I)
    handle = m.group(1) if m else (url or "").strip().lstrip("@")
    return handle.lower() or None


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
      design; it is NOT treated as a partial import).
    - Incremental: stops at the high-water post id once the first page (always
      read in full, to reconcile edits and deletions among the latest posts) is done.
    - Resumable: when the page budget ends before reaching the high-water mark, the
      cursor and the newest id seen are kept in ``state`` and the completed
      high-water mark is NOT advanced, so no unprocessed post is skipped.
    - Retained: posts are merged into the retained feed (bounded) instead of
      wiping it each sync.
    - Failure handling: 429 -> honour Retry-After (bounded), 401/402/403 -> fatal,
      no retries inside a run.
    """
    import requests
    from datetime import datetime, timedelta
    from .. import secret_vault as _sv

    username = x_handle(url)
    if not username:
        return _result(False, error="Could not find a handle in that URL.")
    key = _sv.get_secret("TWITTERAPI_IO_KEY")
    if not key:
        return _result(False, error="No twitterapi.io API key is configured on this platform yet - add one in Admin → API Keys.", fatal=True)

    st = dict(state or {})
    posts = {str(p["id"]): dict(p) for p in (st.get("posts") or []) if p.get("id")}
    high_water = int(st["high_water"]) if st.get("high_water") else None
    cursor = st.get("cursor") or None
    pending_max = int(st["pending_max_id"]) if st.get("pending_max_id") else None
    first_import = high_water is None and not st.get("posts")
    resuming = bool(cursor)   # a resumed page is NOT the top of the timeline

    requests_made = resources = 0
    pages_read = 0
    first_page_ids = None
    seen_new = 0
    complete = False
    newest_dt = None

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
            if created and (newest_dt is None or created > newest_dt):
                newest_dt = created
            if pending_max is None or pid > pending_max:
                pending_max = pid
            if not (pages_read == 1 and not resuming) and high_water is not None and pid <= high_water:
                hit_old = True
                continue
            if str(pid) not in posts:
                seen_new += 1
            posts[str(pid)] = {"id": str(pid), "text": str(txt).strip(),
                               "created_at": created.isoformat() if created else None}
        if pages_read == 1 and not resuming:
            first_page_ids = page_ids

        has_next = bool(body.get("has_next_page"))
        next_cursor = body.get("next_cursor") or None
        if not page_ids or hit_old or not has_next or not next_cursor:
            complete = True
            cursor = None
            break
        if first_import and len(posts) >= initial_cap:
            complete = True   # bounded first import: complete by design
            cursor = None
            break
        if pages_read == 1 and not resuming and high_water is not None and page_ids and min(page_ids) <= high_water:
            complete = True
            cursor = None
            break
        cursor = next_cursor

    # Reconcile the latest window: a retained post that lies inside the id range of
    # the page we just read in full, but is absent from it, was deleted.
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
    published = None
    dates = [p["created_at"] for p in posts.values() if p.get("created_at")]
    if dates:
        published = _parse_dt(max(dates))
    return _result(True, _render_posts(list(posts.values())), published_at=published,
                   incomplete=not complete, state=new_state, usage=usage)


# ── YouTube ────────────────────────────────────────────────────────────────────

def _fetch_youtube(url: str):
    """Recent video titles + descriptions via the YouTube Data API."""
    import requests
    from .. import secret_vault as _sv

    key = _sv.get_secret("YOUTUBE_API_KEY")
    if not key:
        return _result(False, error="No YouTube Data API key is configured on this platform yet - add one in Admin → API Keys.")

    channel_id = _resolve_youtube_channel_id(url, key)
    if not channel_id:
        return _result(False, error="Could not resolve a YouTube channel from that URL.")

    try:
        ch_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "contentDetails", "id": channel_id, "key": key},
            timeout=_TIMEOUT,
        )
        if ch_resp.status_code != 200:
            return _result(False, error=f"YouTube Data API returned HTTP {ch_resp.status_code} - check the configured API key/quota.")
        items = (ch_resp.json() or {}).get("items") or []
        uploads_playlist = None
        if items:
            uploads_playlist = (items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"))
        if not uploads_playlist:
            return _result(False, error="That channel has no public uploads.")

        pl_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "snippet", "playlistId": uploads_playlist, "maxResults": 15, "key": key},
            timeout=_TIMEOUT,
        )
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
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "id", "forHandle": handle, "key": api_key},
            timeout=_TIMEOUT,
        )
        items = (resp.json() or {}).get("items") or []
        if items:
            return items[0]["id"]
    except requests.RequestException:
        pass

    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={"part": "snippet", "q": handle, "type": "channel", "maxResults": 1, "key": api_key},
            timeout=_TIMEOUT,
        )
        items = (resp.json() or {}).get("items") or []
        if items:
            return items[0]["snippet"]["channelId"]
    except requests.RequestException:
        pass
    return None
