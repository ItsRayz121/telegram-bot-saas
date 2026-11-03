"""Echo embeddings with an OpenRouter key: right base URL and the `openai/` model prefix.

Run from the repo root:  python -m pytest backend/tests/test_echo_embeddings_openrouter.py
No network.
"""
import sys
import types

import pytest

from backend.assistant import embedding_service as svc
from backend.assistant import embeddings


class _Resp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": [{"embedding": [0.5, 0.5]}]}


def test_hub_embed_text_uses_openrouter_base_and_prefixed_model(monkeypatch):
    import requests
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, model=json["model"])
        return _Resp()

    monkeypatch.setattr(requests, "post", fake_post)
    vec = embeddings.embed_text("hello", {"provider": "openrouter", "api_key": "sk-or-x"})
    assert vec == [0.5, 0.5]
    assert seen["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert seen["model"] == "openai/text-embedding-3-small"


def test_hub_embed_text_openai_is_unchanged(monkeypatch):
    import requests
    seen = {}
    monkeypatch.setattr(requests, "post", lambda url, headers=None, json=None, timeout=None:
                        (seen.update(url=url, model=json["model"]) or _Resp()))
    embeddings.embed_text("hello", {"provider": "openai", "api_key": "sk-x"})
    assert seen["url"] == "https://api.openai.com/v1/embeddings" and seen["model"] == "text-embedding-3-small"


class _Client:
    def __init__(self, api_key=None, base_url=None):
        self.api_key, self.base_url = api_key, base_url
        self.embeddings = self

    def create(self, model, input):
        self.model = model
        _Client.last = self
        return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[1.0])])


@pytest.fixture()
def fake_openai(monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_Client))


def test_notes_embedding_routes_openrouter_keys(fake_openai):
    assert svc.generate_embedding("note", "sk-or-abc") == [1.0]
    assert _Client.last.base_url == "https://openrouter.ai/api/v1"
    assert _Client.last.model == "openai/text-embedding-3-small"


def test_notes_embedding_leaves_openai_keys_alone(fake_openai):
    assert svc.generate_embedding("note", "sk-proj-abc") == [1.0]
    assert _Client.last.base_url is None and _Client.last.model == "text-embedding-3-small"
