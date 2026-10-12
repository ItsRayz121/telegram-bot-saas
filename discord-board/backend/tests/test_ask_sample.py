"""KB "try a question" sample endpoint (Guildizer).

Run from discord-board/backend:  python -m pytest tests/test_ask_sample.py
The AI provider is mocked; the test proves the sample writes nothing.
"""
import os
import sys
import tempfile
import types

_DB = os.path.join(tempfile.mkdtemp(), "as.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

ME, G, STRANGER = 9951, 9960, 9961


@pytest.fixture()
def client():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal, init_db
    from models import Guild, KnowledgeDocument, User, UserGuild
    init_db()
    s = SessionLocal()
    if s.get(User, ME) is None:
        s.add(User(id=ME, username="admin"))
        s.flush()
        s.add_all([Guild(id=G, name="G", owner_id=ME), Guild(id=STRANGER, name="S", owner_id=ME)])
        s.flush()
        s.add(UserGuild(user_id=ME, guild_id=G, can_manage=True, is_owner=True))
        s.add(KnowledgeDocument(guild_id=G, title="Refunds", content="Refunds are possible within thirty days.", enabled=True))
        s.commit()
    s.close()
    SessionLocal.remove()
    import knowledge_api
    knowledge_api._sample_last.clear()
    knowledge_api._sample_day.clear()
    c = appmod.app.test_client()
    c.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(ME))
    return c


def fake_ai(monkeypatch, text, calls=None):
    import knowledge_api
    monkeypatch.setattr(knowledge_api.ai, "is_configured", lambda: True)

    def complete(system, prompt, max_tokens=None):
        if calls is not None:
            calls.append((system, prompt))
        return types.SimpleNamespace(text=text, model="m", input_tokens=1, output_tokens=1) if text is not None else None
    monkeypatch.setattr(knowledge_api.ai, "complete", complete)


def counts():
    from database import SessionLocal
    from models import AITokenUsage, Member, ProtectionEvent, XpEvent
    s = SessionLocal()
    try:
        return [s.query(m).count() for m in (AITokenUsage, XpEvent, Member, ProtectionEvent)]
    finally:
        s.close()
        SessionLocal.remove()


def url(gid=G):
    return f"/api/guilds/{gid}/knowledge/ask-sample"


def test_answers_like_the_bot_and_writes_nothing(client, monkeypatch):
    calls = []
    fake_ai(monkeypatch, "Refunds are possible within thirty days.", calls)
    before = counts()
    r = client.post(url(), json={"question": "can I get a refund?"})
    assert r.status_code == 200
    j = r.get_json()
    assert j["status"] == "answered" and "thirty days" in j["answer"] and j["confident"] is True
    assert "[Source: Refunds" in calls[0][0] and "SERVER KNOWLEDGE" in calls[0][0]      # same prompt the bot uses
    assert counts() == before                                                       # no usage row, XP, member or event


@pytest.mark.parametrize("model_text,status", [("NO_ANSWER", "no_answer"), ("CONFLICT", "conflict")])
def test_no_answer_and_conflict_are_reported_not_posted(client, monkeypatch, model_text, status):
    fake_ai(monkeypatch, model_text)
    j = client.post(url(), json={"question": "what is the price?"}).get_json()
    assert j["status"] == status and j["answer"] is None


def test_validation_access_and_switches(client, monkeypatch):
    fake_ai(monkeypatch, "x")
    assert client.post(url(), json={"question": "a"}).status_code == 400
    assert client.post(url(STRANGER), json={"question": "hello there"}).status_code == 403
    monkeypatch.setenv("AI_SAMPLES_ENABLED", "0")
    assert client.post(url(), json={"question": "hello there"}).status_code == 503
    monkeypatch.delenv("AI_SAMPLES_ENABLED")
    import knowledge_api
    monkeypatch.setattr(knowledge_api.ai, "is_configured", lambda: False)
    assert client.post(url(), json={"question": "hello there"}).status_code == 503


def test_cooldown_and_daily_limit_protect_spend(client, monkeypatch):
    import knowledge_api
    calls = []
    fake_ai(monkeypatch, "ok answer", calls)
    assert client.post(url(), json={"question": "first question"}).status_code == 200
    assert client.post(url(), json={"question": "second question"}).status_code == 429       # too fast
    assert len(calls) == 1                                                                    # the second never reached the provider
    knowledge_api._sample_last.clear()
    knowledge_api._sample_day[G] = (__import__("datetime").datetime.utcnow().strftime("%Y-%m-%d"), 20)
    assert client.post(url(), json={"question": "third question"}).status_code == 429
    assert len(calls) == 1


def test_provider_failure_is_a_clean_error(client, monkeypatch):
    fake_ai(monkeypatch, None)
    assert client.post(url(), json={"question": "anything at all"}).status_code == 502
