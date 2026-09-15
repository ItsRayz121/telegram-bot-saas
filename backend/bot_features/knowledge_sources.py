"""External-source ingestion for the AI Knowledge Base.

An admin registers a URL (a website, an official Telegram channel, an X/Twitter
handle, a YouTube channel, or literally any other page) and clicks "Sync now" in
the dashboard. This module turns that URL into plain text; the caller
(KnowledgeBaseSystem.process_external_source) runs the result through the same
chunk+embed pipeline as an uploaded file.

Deliberately on-demand only (no background job) — every fetch here is a single
synchronous HTTP call triggered by a real admin click, never a scheduled poll,
so this adds no new recurring load to the scheduler pool this project's
REVERT.md already flags as saturation-prone.

Every fetcher is defensive: a network error, an unexpected response shape, or a
missing credential returns (False, <human-readable reason>) instead of raising —
a sync failure should always be a clear dashboard message, never a 500.
"""
import logging
import re

logger = logging.getLogger(__name__)

_TIMEOUT = 12        # seconds — runs synchronously inside a request handler
_MAX_CHARS = 50_000  # cap ingested text per source so embedding cost stays bounded
_USER_AGENT = "Mozilla/5.0 (compatible; TelegizerBot/1.0; +https://telegizer.com)"

SOURCE_TYPES = ("website", "telegram", "twitter", "youtube")


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


def sync_source(source_type: str, url: str):
    """Fetch a source's current content. Returns (ok: bool, text_or_reason: str)."""
    try:
        if source_type == "youtube":
            return _fetch_youtube(url)
        if source_type == "telegram":
            return _fetch_telegram_channel(url)
        if source_type == "twitter":
            return _fetch_twitter(url)
        # "website" and anything else (the generic "any other URL" case) both
        # fall through to a plain page scrape.
        return _fetch_website(url)
    except Exception as exc:
        logger.error("knowledge_sources.sync_source(%s, %s) failed: %s", source_type, url, exc)
        return False, "Sync failed unexpectedly — check the server logs."


def _fetch_website(url: str):
    """Generic page scrape. Also the fallback for the 'any other' source type."""
    import requests
    from bs4 import BeautifulSoup

    try:
        resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
    except requests.RequestException as exc:
        return False, f"Could not reach that URL: {exc}"
    if resp.status_code != 200:
        return False, f"That URL returned HTTP {resp.status_code}."

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript", "header", "svg"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    body_text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in body_text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    if not text:
        return False, "That page had no extractable text."
    combined = (f"{title}\n\n{text}" if title else text)[:_MAX_CHARS]
    return True, combined


def _fetch_telegram_channel(url: str):
    """Public channels only — reads the same public HTML preview Telegram
    serves at t.me/s/<username>. This needs no bot admin rights, no MTProto user
    session, and no extra credentials — unlike a private channel, which this
    deliberately does not support (that would need a logged-in user session,
    which this project's Anti-Ban Rule treats as high-risk). A channel the bot
    already administers still gets new posts passively via the existing
    handle_channel_post flow in bot_manager.py; this is only the on-demand,
    "give me what's public right now" path.
    """
    import requests
    from bs4 import BeautifulSoup

    m = re.search(r"t(?:elegram)?\.me/(?:s/)?([A-Za-z0-9_]{3,64})", url, re.I)
    if not m:
        return False, "Could not find a channel username in that URL. Use a link like https://t.me/yourchannel."
    username = m.group(1)

    preview_url = f"https://t.me/s/{username}"
    try:
        resp = requests.get(preview_url, timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
    except requests.RequestException as exc:
        return False, f"Could not reach Telegram: {exc}"
    if resp.status_code != 200:
        return False, "That channel is private, doesn't exist, or has no public preview."

    soup = BeautifulSoup(resp.text, "html.parser")
    posts = [el.get_text(separator="\n").strip() for el in soup.select(".tgme_widget_message_text")]
    posts = [p for p in posts if p]
    if not posts:
        return False, "No public posts found for that channel."
    text = "\n\n---\n\n".join(posts)[:_MAX_CHARS]
    return True, text


def _fetch_twitter(url: str):
    """Recent posts for a handle via twitterapi.io — the same low-cost provider
    already used for engagement verification (engagement_verify.py,
    twitter_verify.py)."""
    import requests
    from .. import secret_vault as _sv

    m = re.search(r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})", url, re.I)
    username = m.group(1) if m else url.strip().lstrip("@")
    if not username:
        return False, "Could not find a handle in that URL."

    key = _sv.get_secret("TWITTERAPI_IO_KEY")
    if not key:
        return False, "No twitterapi.io API key is configured on this platform yet — add one in Admin → API Keys."

    try:
        resp = requests.get(
            "https://api.twitterapi.io/twitter/user/last_tweets",
            params={"userName": username},
            headers={"X-API-Key": key},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        return False, f"Could not reach twitterapi.io: {exc}"
    if resp.status_code != 200:
        return False, f"twitterapi.io returned HTTP {resp.status_code}."

    try:
        body = resp.json() or {}
    except ValueError:
        return False, "twitterapi.io returned an unexpected response."

    tweets = (
        body.get("tweets")
        or (body.get("data") or {}).get("tweets")
        or (body.get("data") if isinstance(body.get("data"), list) else None)
        or []
    )
    if not isinstance(tweets, list) or not tweets:
        return False, "No recent posts found for that handle."

    texts = []
    for t in tweets:
        if isinstance(t, dict):
            txt = t.get("text") or t.get("full_text") or t.get("fullText")
            if txt:
                texts.append(str(txt).strip())
    if not texts:
        return False, "That handle's posts had no readable text."
    return True, "\n\n---\n\n".join(texts)[:_MAX_CHARS]


def _fetch_youtube(url: str):
    """Recent video titles + descriptions via the YouTube Data API."""
    import requests
    from .. import secret_vault as _sv

    key = _sv.get_secret("YOUTUBE_API_KEY")
    if not key:
        return False, "No YouTube Data API key is configured on this platform yet — add one in Admin → API Keys."

    channel_id = _resolve_youtube_channel_id(url, key)
    if not channel_id:
        return False, "Could not resolve a YouTube channel from that URL."

    try:
        ch_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "contentDetails", "id": channel_id, "key": key},
            timeout=_TIMEOUT,
        )
        items = (ch_resp.json() or {}).get("items") or []
        uploads_playlist = None
        if items:
            uploads_playlist = (
                items[0].get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads")
            )
        if not uploads_playlist:
            return False, "That channel has no public uploads."

        pl_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "snippet", "playlistId": uploads_playlist, "maxResults": 15, "key": key},
            timeout=_TIMEOUT,
        )
        pl_items = (pl_resp.json() or {}).get("items") or []
    except requests.RequestException as exc:
        return False, f"Could not reach YouTube: {exc}"

    videos = []
    for it in pl_items:
        snip = it.get("snippet") or {}
        title = (snip.get("title") or "").strip()
        desc = (snip.get("description") or "").strip()
        if title:
            videos.append(f"{title}\n{desc}".strip())
    if not videos:
        return False, "No recent videos found for that channel."
    return True, "\n\n---\n\n".join(videos)[:_MAX_CHARS]


def _resolve_youtube_channel_id(url: str, api_key: str):
    import requests

    m = re.search(r"youtube\.com/channel/([A-Za-z0-9_-]{10,40})", url, re.I)
    if m:
        return m.group(1)

    handle_m = re.search(r"youtube\.com/(?:@|c/|user/)([A-Za-z0-9_.-]{2,60})", url, re.I)
    if not handle_m and "youtube.com" not in url.lower() and "youtu.be" not in url.lower():
        # Accept a bare "@handle" or "handle" typed directly into the field.
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
