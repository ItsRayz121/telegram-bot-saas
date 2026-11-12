"""A rejected platform OpenAI key (401) falls back to the OpenRouter key for embeddings.

Run from discord-board/backend:  python -m pytest tests/test_kb_embed_fallback.py
"""
import os
import sys
import tempfile
import types

os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'kb.db')}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Err(Exception):
    status_code = 401


def _fake_openai(calls):
    class Emb:
        def __init__(self, base_url):
            self.base_url = base_url

        def create(self, model, input):
            calls.append((self.base_url, model))
            if self.base_url is None:
                raise _Err("bad key")
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[0.1, 0.2]) for _ in input])

    class Client:
        def __init__(self, api_key=None, base_url=None):
            self.embeddings = Emb(base_url)
    return types.SimpleNamespace(OpenAI=Client)


def test_401_retries_through_openrouter(monkeypatch):
    import kb_index
    calls = []
    monkeypatch.setitem(sys.modules, "openai", _fake_openai(calls))
    monkeypatch.setattr(kb_index.Config, "OPENAI_API_KEY", "sk-bad", raising=False)
    monkeypatch.setattr(kb_index.Config, "OPENROUTER_API_KEY", "or-good", raising=False)
    out = kb_index._embed(["a", "b"])
    assert out == [[0.1, 0.2], [0.1, 0.2]]
    assert calls[0][0] is None and calls[1][0] == kb_index._OPENROUTER_BASE_URL
    assert calls[1][1].startswith("openai/")


def test_401_without_fallback_key_degrades_to_none(monkeypatch):
    import kb_index
    monkeypatch.setitem(sys.modules, "openai", _fake_openai([]))
    monkeypatch.setattr(kb_index.Config, "OPENAI_API_KEY", "sk-bad", raising=False)
    monkeypatch.setattr(kb_index.Config, "OPENROUTER_API_KEY", None, raising=False)
    assert kb_index._embed(["a"]) == [None]
    assert "error" in kb_index.embed_failure_message().lower()
