"""Proof-link validity checks (Phase 14). Keyless: uses the public oEmbed
endpoints for YouTube and X, generic reachability for everything else.

Returns "valid" | "invalid" | "unknown" — annotation for the review queue,
never an auto-reject. Sync (call from worker threads); ~6s budget.
"""
from __future__ import annotations

import logging
import re

import requests

import urlguard

log = logging.getLogger("guildizer.linkcheck")

_TIMEOUT = 6
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.I)

_OEMBED = [
    (re.compile(r"(youtube\.com|youtu\.be)/", re.I),
     "https://www.youtube.com/oembed"),
    (re.compile(r"(twitter\.com|x\.com)/\w+/status/", re.I),
     "https://publish.twitter.com/oembed"),
]


def first_url(text: str) -> str | None:
    m = _URL_RE.search(text or "")
    return m.group(0) if m else None


def check_link(url: str) -> str:
    """Validity verdict for one URL."""
    if not url:
        return "unknown"
    for pattern, endpoint in _OEMBED:
        if pattern.search(url):
            try:
                resp = requests.get(endpoint, params={"url": url, "format": "json"},
                                    timeout=_TIMEOUT)
                if resp.status_code == 200:
                    return "valid"
                if resp.status_code in (400, 401, 403, 404):
                    return "invalid"
                return "unknown"
            except requests.RequestException:
                return "unknown"
    # generic: does the page exist at all? (never probe non-public hosts)
    if not urlguard.is_public_url(url):
        return "unknown"
    try:
        resp = requests.head(url, timeout=_TIMEOUT, allow_redirects=True)
        if resp.status_code == 405:  # HEAD not allowed — page likely exists
            return "valid"
        return "valid" if resp.status_code < 400 else "invalid"
    except requests.RequestException:
        return "unknown"


def check_proof_text(text: str) -> str | None:
    """Verdict for the first URL in a proof blob, or None if it has no URL."""
    url = first_url(text)
    if url is None:
        return None
    return check_link(url)
