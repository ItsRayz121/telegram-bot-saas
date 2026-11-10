"""Knowledge-base embeddings: which key/route is used, and an honest failure message.

Run from the repo root:  python -m pytest backend/tests/test_kb_embedding_route.py
No network: the OpenAI client is replaced by a recorder.
"""
import pytest

from backend.bot_features import knowledge_base as kbmod
from backend.bot_features.knowledge_base import KnowledgeBaseSystem


class _Client:
    def __init__(self, api_key, base_url=None, fail=None):
        self.api_key, self.base_url, self.fail = api_key, base_url, fail
        self.embeddings = self

    def create(self, model, input):
        if self.fail:
            raise RuntimeError(self.fail)
        self.model = model
        data = [type("E", (), {"embedding": [0.1, 0.2]})() for _ in input]
        return type("R", (), {"data": data})()


@pytest.fixture()
def kb(monkeypatch):
    system = KnowledgeBaseSystem(object())
    made = []

    def fake_client(self, api_key=None, base_url=None):
        if not api_key:
            return None
        c = _Client(api_key, base_url)
        made.append(c)
        return c

    monkeypatch.setattr(KnowledgeBaseSystem, "_get_openai_client", fake_client)
    monkeypatch.setattr(KnowledgeBaseSystem, "_load_group_api_key", lambda self, *a, **k: None)
    system.made = made
    return system


def _secrets(monkeypatch, **values):
    monkeypatch.setattr(KnowledgeBaseSystem, "_platform_secret", staticmethod(lambda name: values.get(name)))


def test_group_openai_key_is_used_directly(kb, monkeypatch):
    _secrets(monkeypatch, OPENAI_API_KEY="platform-oa")
    client, model = kb._embedding_route({"provider": "openai", "api_key": "group-oa"})
    assert client.api_key == "group-oa" and client.base_url is None and model == "text-embedding-3-small"


def test_platform_openai_key_beats_openrouter(kb, monkeypatch):
    _secrets(monkeypatch, OPENAI_API_KEY="platform-oa", PLATFORM_OPENROUTER_API_KEY="platform-or")
    client, model = kb._embedding_route({"provider": "openrouter", "api_key": "platform-or"})
    assert client.api_key == "platform-oa" and model == "text-embedding-3-small"


def test_openrouter_is_used_when_there_is_no_openai_key(kb, monkeypatch):
    """The Enterprise case: AI runs on the platform OpenRouter key, no OPENAI_API_KEY anywhere."""
    _secrets(monkeypatch, PLATFORM_OPENROUTER_API_KEY="platform-or")
    client, model = kb._embedding_route(None)
    assert client.api_key == "platform-or"
    assert client.base_url == "https://openrouter.ai/api/v1"
    assert model == "openai/text-embedding-3-small"


def test_a_groups_own_openrouter_key_is_used(kb, monkeypatch):
    _secrets(monkeypatch)
    client, model = kb._embedding_route({"provider": "openrouter", "api_key": "group-or"})
    assert client.api_key == "group-or" and model == "openai/text-embedding-3-small"


def test_no_key_anywhere_means_no_route(kb, monkeypatch):
    _secrets(monkeypatch)
    assert kb._embedding_route(None) == (None, None)


def test_missing_key_message_only_when_there_really_is_no_key(kb, monkeypatch):
    _secrets(monkeypatch)
    assert kb._embed(["hello"]) == [None]
    assert "no AI API key" in kb._embed_failure_message()


def test_a_provider_error_is_not_reported_as_a_missing_key(kb, monkeypatch):
    _secrets(monkeypatch, OPENAI_API_KEY="platform-oa")
    monkeypatch.setattr(KnowledgeBaseSystem, "_get_openai_client",
                        lambda self, api_key=None, base_url=None: _Client(api_key, base_url, fail="insufficient_quota"))
    assert kb._embed(["hello"]) == [None]
    msg = kb._embed_failure_message()
    assert "no AI API key" not in msg and "insufficient_quota" in msg


def test_embed_succeeds_through_openrouter_with_the_prefixed_model(kb, monkeypatch):
    _secrets(monkeypatch, PLATFORM_OPENROUTER_API_KEY="platform-or")
    out = kb._embed(["a", "b"])
    assert out == [[0.1, 0.2], [0.1, 0.2]]
    assert kb.made[-1].model == "openai/text-embedding-3-small"


class _AuthError(Exception):
    status_code = 401


def test_rejected_platform_openai_key_falls_back_to_openrouter(kb, monkeypatch):
    """A revoked/typo'd OPENAI_API_KEY (401) must not strand the KB when an OpenRouter key exists."""
    _secrets(monkeypatch, OPENAI_API_KEY="bad-oa", PLATFORM_OPENROUTER_API_KEY="platform-or")

    def fake_client(self, api_key=None, base_url=None):
        c = _Client(api_key, base_url)
        if api_key == "bad-oa":
            c.fail = None
            c.create = lambda model, input: (_ for _ in ()).throw(_AuthError("Incorrect API key"))
        return c

    monkeypatch.setattr(KnowledgeBaseSystem, "_get_openai_client", fake_client)
    out = kb._embed(["hello"])
    assert out == [[0.1, 0.2]]


def test_rejected_platform_openai_key_without_openrouter_reports_error(kb, monkeypatch):
    _secrets(monkeypatch, OPENAI_API_KEY="bad-oa")

    def fake_client(self, api_key=None, base_url=None):
        c = _Client(api_key, base_url)
        c.create = lambda model, input: (_ for _ in ()).throw(_AuthError("Incorrect API key"))
        return c

    monkeypatch.setattr(KnowledgeBaseSystem, "_get_openai_client", fake_client)
    assert kb._embed(["hello"]) == [None]
    assert "Incorrect API key" in kb._embed_failure_message()
