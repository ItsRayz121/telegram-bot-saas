"""Editable campaign announcement: line switches + a free-text template.

One small module shared by the Telegram announcement (HTML) and, as a copy, the Discord
embed. Template syntax: plain text, `**bold**`, `__italic__` and `{placeholders}`.
A template line whose placeholders are ALL empty is dropped (so "Reward: {reward}" vanishes
when there is no reward). Everything the admin types is escaped; placeholder values are
already safe. Kill switch: POST_CUSTOMIZE_ENABLED=0 -> the automatic post is used.
"""
import html
import os
import re

HIDEABLE = ("reward", "xp", "submissions", "proof", "deadline", "status")
PLACEHOLDERS = ("title", "description", "tasks", "goals", "reward", "xp",
                "submissions", "proof", "deadline", "status", "link")
MAX_TEMPLATE = 3000

_PH = re.compile(r"\{(\w+)\}")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITAL = re.compile(r"__(.+?)__")


def enabled():
    return os.environ.get("POST_CUSTOMIZE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def clean_settings(out):
    """Normalise post_template / post_hide inside a settings dict (in place)."""
    if "post_template" in out:
        t = out.get("post_template")
        t = t.replace("\r\n", "\n").strip() if isinstance(t, str) else ""
        if t:
            out["post_template"] = t[:MAX_TEMPLATE]
        else:
            out.pop("post_template", None)
    if "post_hide" in out:
        h = out.get("post_hide")
        h = [k for k in h if k in HIDEABLE] if isinstance(h, list) else []
        if h:
            out["post_hide"] = sorted(set(h), key=HIDEABLE.index)
        else:
            out.pop("post_hide", None)
    return out


def hidden(settings):
    if not enabled():
        return set()
    return {k for k in ((settings or {}).get("post_hide") or []) if k in HIDEABLE}


def template_of(settings):
    if not enabled():
        return ""
    t = (settings or {}).get("post_template")
    return t.strip() if isinstance(t, str) else ""


def render(template, parts, *, escape):
    """Fill `template` with `parts` (placeholder -> already-safe text).

    escape=True  : Telegram HTML - admin text is escaped, **bold** / __italic__ become tags.
    escape=False : Discord markdown - text is used as written."""
    out = []
    for line in template.split("\n"):
        names = _PH.findall(line)
        if names and all((n in parts and not parts[n]) for n in names):
            continue                          # every placeholder on this line is empty
        if escape:
            line = html.escape(line, quote=False)
            line = _BOLD.sub(r"<b>\1</b>", line)
            line = _ITAL.sub(r"<i>\1</i>", line)
        line = _PH.sub(lambda m: parts[m.group(1)] if m.group(1) in parts else m.group(0), line)
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text
