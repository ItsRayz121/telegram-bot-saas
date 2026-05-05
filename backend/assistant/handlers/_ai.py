"""
AI call helpers using httpx (sync) for better connection pooling and HTTP/2.

Replaces requests-based calls from the original personal_assistant.py.
httpx.Client is used as a module-level singleton for connection reuse.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx

from ._prompts import RESOLVE_DATETIME_SYSTEM

_log = logging.getLogger(__name__)

# Singleton httpx client — reuses TCP connections, supports HTTP/2
_client = httpx.Client(timeout=25.0, http2=False)


def call_ai(key_info: dict, system: str, user_msg: str) -> str:
    """Call AI expecting a JSON response."""
    provider = key_info.get("provider", "gemini")
    api_key = key_info["api_key"]
    model = key_info.get("model", "gemini-1.5-flash")

    _log.debug("call_ai provider=%s model=%s msg_len=%d", provider, model, len(user_msg))

    if provider == "gemini":
        resp = _client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "candidateCount": 1,
                    "responseMimeType": "application/json",
                },
            },
        )
        if not resp.is_success:
            _log.error("Gemini API error %d: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    if provider == "anthropic":
        resp = _client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": model or "claude-haiku-4-5-20251001",
                "max_tokens": 512,
                "system": system,
                "messages": [{"role": "user", "content": user_msg}],
            },
        )
        if not resp.is_success:
            _log.error("Anthropic API error %d: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()

    base = key_info.get("base_url", "https://api.openai.com/v1")
    resp = _client.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model or "gpt-4o-mini",
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        },
    )
    if not resp.is_success:
        _log.error("OpenAI API error %d: %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def call_ai_text(key_info: dict, system: str, user_msg: str) -> str:
    """Call AI expecting a plain-text response (not JSON)."""
    provider = key_info.get("provider", "gemini")
    api_key = key_info["api_key"]
    model = key_info.get("model", "gemini-1.5-flash")

    if provider == "gemini":
        resp = _client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
                "generationConfig": {"temperature": 0.3, "candidateCount": 1},
            },
        )
        if not resp.is_success:
            _log.error("Gemini API error %d: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    if provider == "anthropic":
        resp = _client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": model or "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user_msg}],
            },
        )
        if not resp.is_success:
            _log.error("Anthropic API error %d: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()

    base = key_info.get("base_url", "https://api.openai.com/v1")
    resp = _client.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model or "gpt-4o-mini",
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        },
    )
    if not resp.is_success:
        _log.error("OpenAI API error %d: %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON in AI response: {text[:200]!r}")


def resolve_datetime(key_info: dict, hint: str, user_tz: Optional[str]) -> dict:
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    tz_note = f" User timezone: {user_tz}." if user_tz else ""
    prompt = f'Today is {now_str}.{tz_note}\nParse this date/time phrase: "{hint}"'
    try:
        raw = call_ai(key_info, RESOLVE_DATETIME_SYSTEM, prompt)
        result = parse_json(raw)
        _log.debug("datetime resolve hint=%r → %s", hint, result)
        if not result.get("iso"):
            result = fallback_datetime(hint)
        return result
    except Exception as exc:
        _log.warning("datetime resolve failed: %s — using fallback", exc)
        return fallback_datetime(hint)


def fallback_datetime(hint: str) -> dict:
    now = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    h = hint.lower()
    weekday_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    target = None
    if "today" in h:
        target = now
    elif "tomorrow" in h:
        target = now + timedelta(days=1)
    else:
        for word, wd in weekday_map.items():
            if word in h:
                days_ahead = (wd - now.weekday()) % 7 or 7
                target = now + timedelta(days=days_ahead)
                break
    if target:
        time_m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", h, re.IGNORECASE)
        if time_m:
            hour = int(time_m.group(1))
            minute = int(time_m.group(2) or 0)
            meridiem = time_m.group(3).lower()
            if meridiem == "pm" and hour != 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            target = target.replace(hour=hour, minute=minute)
        return {"iso": target.strftime("%Y-%m-%dT%H:%M:%S"), "human": target.strftime("%A %d %B at %I:%M %p UTC")}
    in_m = re.search(r"in\s+(\d+)\s*(minute|hour|day)s?", h, re.IGNORECASE)
    if in_m:
        n, unit = int(in_m.group(1)), in_m.group(2).lower()
        delta = (timedelta(minutes=n) if unit == "minute"
                 else timedelta(hours=n) if unit == "hour"
                 else timedelta(days=n))
        target = datetime.utcnow() + delta
        return {"iso": target.strftime("%Y-%m-%dT%H:%M:%S"), "human": target.strftime("%A %d %B at %I:%M %p UTC")}
    return {"iso": None, "human": hint}
