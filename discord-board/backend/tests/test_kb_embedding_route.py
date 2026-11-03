"""Guildizer knowledge-base embeddings: key route and honest failure reason.

Run from discord-board/backend:  python -m pytest tests/test_kb_embedding_route.py
No network: the OpenAI client is replaced by a recorder.
"""
import os
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'kbe.db')}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import kb_index  # noqa: E402
from config import Config  # noqa: E402


class _Client:
    made = []

    def __init__(self, api_key=None, base_url=None):
        self.api_key, self.base_url, self.model, self.fail = api_key, base_url, None, None
        self.embeddings = self
        _Client.made.append(self)

    def create(self, model, input):
        self.model = model
        if _Client.fail:
            raise RuntimeError(_Client.fail)
        return type("R", (), {"data": [type("E", (), {"embedding": [0.1, 0.2]})() for _ in input]})()


@pytest.fixture(autouse=True)
def fake_openai(monkeypatch):
    import types
    _Client.made, _Client.fail = [], None
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_Client))


def _keys(monkeypatch, openai="", openrouter=""):
    monkeypatch.setattr(Config, "OPENAI_API_KEY", openai)
    monkeypatch.setattr(Config, "OPENROUTER_API_KEY", openrouter)


def test_openai_key_wins(monkeypatch):
    _keys(monkeypatch, openai="oa", openrouter="or")
    assert kb_index._embed(["x"]) == [[0.1, 0.2]]
    c = _Client.made[-1]
    assert c.api_key == "oa" and c.base_url is None and c.model == "text-embedding-3-small"


def test_openrouter_is_used_when_there_is_no_openai_key(monkeypatch):
    _keys(monkeypatch, openrouter="or")
    assert kb_index._embed(["x", "y"]) == [[0.1, 0.2], [0.1, 0.2]]
    c = _Client.made[-1]
    assert c.api_key == "or" and c.base_url == "https://openrouter.ai/api/v1"
    assert c.model == "openai/text-embedding-3-small"


def test_no_key_says_so(monkeypatch):
    _keys(monkeypatch)
    assert kb_index._embed(["x"]) == [None]
    assert "no OPENAI_API_KEY or OPENROUTER_API_KEY" in kb_index.embed_failure_message()


def test_provider_error_is_not_reported_as_a_missing_key(monkeypatch):
    _keys(monkeypatch, openrouter="or")
    _Client.fail = "insufficient_quota"
    assert kb_index._embed(["x"]) == [None]
    msg = kb_index.embed_failure_message()
    assert "insufficient_quota" in msg and "no OPENAI_API_KEY" not in msg
