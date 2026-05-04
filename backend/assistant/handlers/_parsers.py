"""Keyword parsers and datetime extraction helpers."""
from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Optional

from ._patterns import (
    SCHEDULE_PATTERNS, MEETING_NOUN, LIST_MEETINGS_PATTERNS,
    UPCOMING_SCHEDULE_PATTERNS, CREATE_REMINDER_PATTERNS,
    LIST_REMINDERS_PATTERNS, GROUP_PATTERNS, GROUP_ISSUE_SIGNALS,
    SAVE_NOTE_PATTERNS, LIST_NOTES_PATTERNS, SAVE_LINK_PATTERNS,
    CREATE_TASK_PATTERNS, LIST_TASKS_PATTERNS,
)

# Vocabulary of intent-bearing words to fuzzy-match against.
# Each canonical word maps to a replacement word that the patterns already handle.
_FUZZY_VOCAB = {
    "reminder": "reminder",
    "reminders": "reminders",
    "remind": "remind",
    "meeting": "meeting",
    "meetings": "meetings",
    "schedule": "schedule",
    "schedule": "schedule",
    "calendar": "schedule",
    "appointment": "appointment",
    "task": "task",
    "tasks": "tasks",
    "todo": "task",
    "note": "note",
    "notes": "notes",
    "group": "group",
    "groups": "groups",
    "upcoming": "upcoming",
    "briefing": "briefing",
    "announcement": "announcement",
    "cancel": "cancel",
    "reschedule": "reschedule",
    "booking": "book",
    "book": "book",
}
_FUZZY_WORDS = list(_FUZZY_VOCAB.keys())


def normalize_typos(message: str) -> str:
    """
    Replace misspelled intent-bearing words with their canonical forms.
    Only corrects words that are clearly close to one known word (cutoff=0.72,
    n=1) and longer than 3 chars to avoid false positives on short words.
    """
    tokens = message.split()
    corrected = []
    for token in tokens:
        # Strip punctuation for matching, keep original punctuation
        core = re.sub(r"[^a-zA-Z]", "", token).lower()
        if len(core) > 3 and core not in _FUZZY_VOCAB:
            matches = get_close_matches(core, _FUZZY_WORDS, n=1, cutoff=0.72)
            if matches:
                canonical = _FUZZY_VOCAB[matches[0]]
                # Preserve original casing style
                token = token.lower().replace(core, canonical)
        corrected.append(token)
    return " ".join(corrected)


def low_confidence_suggestions(message: str) -> list[dict]:
    """
    When we can't parse intent, check which intent keywords the message words
    are close to and return 'did you mean?' suggestion buttons.
    """
    tokens = [re.sub(r"[^a-zA-Z]", "", t).lower() for t in message.split() if len(t) > 3]
    seen: set[str] = set()
    suggestions = []
    for token in tokens:
        matches = get_close_matches(token, _FUZZY_WORDS, n=1, cutoff=0.65)
        if matches and matches[0] not in seen:
            seen.add(matches[0])
            canonical = _FUZZY_VOCAB[matches[0]]
            suggestions.append({"label": f'Did you mean "{canonical}"?', "value": canonical})
    return suggestions[:3]


def keyword_intent(message: str) -> Optional[str]:
    msg = message.lower()

    if LIST_REMINDERS_PATTERNS.search(msg):
        return "list_reminders"
    if LIST_MEETINGS_PATTERNS.search(msg):
        return "list_meetings"
    if LIST_NOTES_PATTERNS.search(msg):
        return "list_notes"
    if LIST_TASKS_PATTERNS.search(msg):
        return "list_tasks"
    if UPCOMING_SCHEDULE_PATTERNS.search(msg):
        return "upcoming_schedule"
    if GROUP_PATTERNS.search(msg) and GROUP_ISSUE_SIGNALS.search(msg):
        return "group_query"
    if CREATE_REMINDER_PATTERNS.search(msg):
        return "create_reminder"
    if SAVE_NOTE_PATTERNS.search(msg):
        return "save_note"
    if re.search(r"https?://", msg) and re.search(r"\b(save|remember|bookmark|keep|note)\b", msg):
        return "save_link"
    if CREATE_TASK_PATTERNS.search(msg):
        return "create_task"
    if SCHEDULE_PATTERNS.search(msg) or MEETING_NOUN.search(msg):
        return "schedule_meeting"
    if re.search(r"\b(search|find|look\s+for|look\s+up)\b.*\bnotes?\b", msg):
        return "search_notes"
    if re.search(r"\b(summarize|summary\s+of)\b.*\bnotes?\b", msg):
        return "summarize_notes"
    if re.search(r"\b(trigger|send|run)\b.*\bdigest\b", msg):
        return "trigger_digest"
    if re.search(r"\b(post|announce|broadcast|send)\b.*(announcement|message|update).*\bgroup\b", msg):
        return "post_announcement"
    if re.search(r"\b(group\s+stats?|group\s+health|how.*group.*doing|show.*groups?)\b", msg):
        return "get_group_stats"
    if re.search(r"\b(list|show)\b.*(auto.?repl|keyword|trigger)s?\b", msg):
        return "list_auto_replies"
    if re.search(r"\b(enable|disable|turn\s+on|turn\s+off)\b.*\b(automod|auto.?mod)\b", msg):
        return "update_automod"
    return None


def extract_datetime_hint(message: str) -> Optional[str]:
    day_pat = re.compile(
        r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
        r"|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)"
        r"|this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"|in\s+\d+\s+days?)\b",
        re.IGNORECASE,
    )
    time_pat = re.compile(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)\b",
        re.IGNORECASE,
    )
    in_pat = re.compile(
        r"\b(in\s+\d+\s*(?:minutes?|hours?|days?|weeks?))\b",
        re.IGNORECASE,
    )
    day_m = day_pat.search(message)
    time_m = time_pat.search(message)
    in_m = in_pat.search(message)
    parts = []
    if day_m:
        parts.append(day_m.group(0).strip())
    if time_m:
        t = time_m.group(0).strip()
        if t not in parts:
            parts.append(t)
    if parts:
        return " ".join(parts)
    if in_m:
        return in_m.group(0).strip()
    return None


def parse_reminder_minutes(text: str) -> int:
    t = text.lower()
    m = re.search(r"(\d+)\s*(min|minute|hour|day|week)", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit.startswith("min"):
            return n
        if unit.startswith("hour"):
            return n * 60
        if unit.startswith("day"):
            return n * 1440
        if unit.startswith("week"):
            return n * 10080
    if "hour" in t:
        return 60
    if "day" in t:
        return 1440
    return 15


def keyword_parse(message: str) -> dict:
    title_match = re.search(
        r"(?:schedule|book|set up|create|plan|arrange)\s+(?:a\s+|an\s+)?(?:meeting|call|standup|sync|catchup|session|appointment|interview|demo|webinar)?\s*(?:for|with|titled|called|:)?\s*(.+?)(?:\s+(?:on|at|for|tomorrow|today|next|this|\d)|$)",
        message, re.IGNORECASE,
    )
    title = title_match.group(1).strip() if title_match else None
    if title and len(title) < 3:
        title = None
    dt_hint = extract_datetime_hint(message)
    return {"intent": "schedule_meeting", "title": title, "datetime_hint": dt_hint}


def keyword_parse_note(message: str) -> Optional[str]:
    for pat in (r"note this:\s*(.+)", r"note:\s*(.+)", r"save this as note:\s*(.+)",
                r"remember this:\s*(.+)", r"jot this down:\s*(.+)",
                r"quick note:\s*(.+)", r"make a note(?:\s*of)?:\s*(.+)"):
        m = re.search(pat, message, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    return None


def keyword_parse_task(message: str) -> Optional[str]:
    for pat in (r"(?:create|add|new)\s+task[:\s]+(.+)", r"task:\s*(.+)",
                r"to.?do:\s*(.+)", r"add\s+(.+?)\s+to\s+(?:my\s+)?(?:task|to.?do)\s+list",
                r"i need to\s+(.+)", r"don.t forget to\s+(.+)"):
        m = re.search(pat, message, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    return None


def keyword_parse_reminder(message: str) -> tuple[Optional[str], Optional[str]]:
    for pat in (
        r"remind me to\s+(.+?)(?:\s+(?:at|on|tomorrow|today|in\s+\d+|next\s+|this\s+).*)?$",
        r"remind me about\s+(.+?)(?:\s+(?:at|on|tomorrow|today|in\s+\d+|next\s+|this\s+).*)?$",
        r"remind me\s+(.+?)(?:\s+(?:at|on|tomorrow|today|in\s+\d+|next\s+|this\s+).*)?$",
        r"set a reminder(?:\s+for)?\s+(.+)",
    ):
        m = re.search(pat, message, re.IGNORECASE | re.DOTALL)
        if m:
            text = m.group(1).strip()
            if len(text) >= 2:
                return text, extract_datetime_hint(message)
    return None, extract_datetime_hint(message)
