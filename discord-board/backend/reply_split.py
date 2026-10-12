"""Split a long AI answer into Discord-sized messages without cutting it off.

Discord rejects messages over 2000 characters. The bot used to truncate AI answers
at 1950 characters, which dropped the end of a long answer (sometimes mid-sentence).
This keeps paragraphs together and splits on the best boundary available:
paragraph break, then line break, then sentence end, then a space, and only as a last
resort hard-cuts a single word that is longer than the limit.
"""
from __future__ import annotations

import re

LIMIT = 1900          # headroom under Discord's 2000 for mentions / formatting
MAX_PARTS = 3         # an answer longer than this is trimmed with a clear marker

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _cut(text: str, limit: int) -> int:
    """Index at which to cut ``text`` (len > limit) at the best boundary."""
    window = text[:limit]
    for sep in ("\n\n", "\n"):
        i = window.rfind(sep)
        if i >= limit // 3:
            return i + len(sep)
    ends = list(_SENTENCE_END.finditer(window))
    if ends and ends[-1].end() >= limit // 3:
        return ends[-1].end()
    i = window.rfind(" ")
    if i >= limit // 3:
        return i + 1
    return limit


def split_reply(text: str, limit: int = LIMIT, max_parts: int = MAX_PARTS) -> list[str]:
    """Parts (each <= limit) that concatenate back to the answer. Never empty
    strings. If the answer would need more than ``max_parts`` messages the last
    part ends with an ellipsis marker instead of silently dropping text."""
    text = (text or "").strip()
    if not text:
        return []
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        if len(parts) == max_parts - 1:
            cut = _cut(rest, limit - 1)
            parts.append(rest[:cut].rstrip() + "…")
            break
        cut = _cut(rest, limit)
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return [p for p in parts if p]
