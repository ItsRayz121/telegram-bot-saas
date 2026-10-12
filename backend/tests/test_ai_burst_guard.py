"""Per-group cap on cheap per-event platform-AI calls (welcome / level-up).

Run from the repo root:  python -m pytest backend/tests/test_ai_burst_guard.py
"""
import asyncio
import os
import sys
import types

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

from backend.bot_features import ai_burst_guard as g


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    g.reset()
    monkeypatch.delenv("AI_BURST_GUARD", raising=False)
    yield
    g.reset()


def test_group_is_capped_and_others_are_unaffected():
    assert all(g.allow("welcome", "A", limit=3) for _ in range(3))
    assert g.allow("welcome", "A", limit=3) is False
    assert g.allow("welcome", "B", limit=3) is True        # another group
    assert g.allow("levelup", "A", limit=3) is True        # another feature


def test_window_expires(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(g.time, "monotonic", lambda: t[0])
    assert g.allow("welcome", "A", limit=1, window=60)
    assert not g.allow("welcome", "A", limit=1, window=60)
    t[0] += 61
    assert g.allow("welcome", "A", limit=1, window=60)


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("AI_BURST_GUARD", "0")
    assert all(g.allow("welcome", "A", limit=1) for _ in range(5))


def test_memory_is_bounded(monkeypatch):
    monkeypatch.setattr(g, "_MAX_KEYS", 10)
    results = [g.allow("welcome", f"g{i}", limit=5) for i in range(30)]
    assert len(g._HITS) <= 10
    assert results[-1] is False  # saturated -> fails closed to the free template


def _fake_openai(calls):
    class Resp:  # shape of openai's response
        choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=" Hi! "))]

    class Client:
        def __init__(self, **kw):
            calls.append(("init", kw))
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

        def _create(self, **kw):
            calls.append(("create", kw))
            return Resp()

    return types.SimpleNamespace(OpenAI=Client)


def test_welcome_stops_calling_the_provider_after_the_cap(monkeypatch):
    from backend.config import Config
    from backend.bot_features.welcome import WelcomeSystem
    calls = []
    monkeypatch.setattr(Config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "openai", _fake_openai(calls))
    monkeypatch.setattr(g, "DEFAULT_LIMIT", 2)
    ws = WelcomeSystem.__new__(WelcomeSystem)

    async def run():
        return [await ws._generate_ai_welcome("Ann", "G", group_key="grp") for _ in range(4)]

    out = asyncio.run(run())
    assert out == ["Hi!", "Hi!", None, None]
    assert len([c for c in calls if c[0] == "create"]) == 2   # provider untouched after the cap
    init = next(c[1] for c in calls if c[0] == "init")
    assert init["timeout"] == 8.0 and init["max_retries"] == 0   # bounded latency, no retry storms
