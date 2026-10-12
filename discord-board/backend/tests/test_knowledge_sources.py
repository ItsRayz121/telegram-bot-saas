"""Knowledge sources (website / X / YouTube) for Guildizer.

Run from discord-board/backend:  python -m pytest tests/test_knowledge_sources.py
Throwaway SQLite database. Provider calls (fetch, embeddings, HTTP) are mocked:
nothing here touches the network, Discord or an AI provider.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "ks.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import kb_index  # noqa: E402
import kb_sources  # noqa: E402
import knowledge  # noqa: E402
import knowledge_sources as ks  # noqa: E402
import knowledge_sync as kg  # noqa: E402

OWNER, OTHER_OWNER = 9101, 9102
PRO, FREE, PRO2, STRANGER = 9110, 9111, 9112, 9113


@pytest.fixture(scope="module", autouse=True)
def _world():
    from database import SessionLocal, init_db
    from models import Guild, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add_all([User(id=OWNER, username="owner"), User(id=OTHER_OWNER, username="other")])
    db.flush()
    db.add_all([Guild(id=PRO, name="Pro", owner_id=OWNER, plan="pro"),
                Guild(id=FREE, name="Free", owner_id=OTHER_OWNER, plan="free"),
                Guild(id=PRO2, name="Pro2", owner_id=OWNER, plan="pro"),
                Guild(id=STRANGER, name="Stranger", owner_id=OTHER_OWNER, plan="free")])
    db.flush()
    db.add_all([UserGuild(user_id=OWNER, guild_id=PRO, can_manage=True, is_owner=True),
                UserGuild(user_id=OWNER, guild_id=PRO2, can_manage=True, is_owner=True)])
    db.commit()
    db.close()


@pytest.fixture()
def db():
    from database import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()
    SessionLocal.remove()


@pytest.fixture()
def embed_calls(monkeypatch):
    calls = []

    def fake_embed(texts):
        calls.append(len(texts))
        return [[1.0, 0.0, float(len(t) % 7)] for t in texts]
    monkeypatch.setattr(kb_index, "_embed", fake_embed)
    return calls


def ok_result(text, **kw):
    r = ks._result(True, text, published_at=kw.pop("published_at", None), **kw)
    return r


def mock_fetch(monkeypatch, results):
    """fetch_source returns the queued results in order."""
    queue = list(results)
    seen = []

    def fake(source_type, url, state=None, max_pages=3, initial_cap=60):
        seen.append({"state": state, "max_pages": max_pages})
        return queue.pop(0) if len(queue) > 1 else queue[0]
    monkeypatch.setattr(ks, "fetch_source", fake)
    return seen


def make_source(db, guild_id=PRO, stype="website", url=None, **kw):
    from models import KnowledgeSource
    n = db.query(KnowledgeSource).count()
    s = KnowledgeSource(guild_id=guild_id, source_type=stype,
                        url=url or ("https://example.com/p%d" % n if stype == "website"
                                    else "https://x.com/handle%d" % n),
                        label=kw.pop("label", None), **kw)
    db.add(s)
    db.commit()
    return s


def doc_of(db, source):
    from models import KnowledgeDocument
    return db.query(KnowledgeDocument).filter(KnowledgeDocument.source_id == source.id).first()


# ── connectors ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://localhost/x", "http://169.254.169.254/latest",
                                 "http://10.0.0.5/", "ftp://example.com/", "http:///nohost"])
def test_ssrf_guard_rejects_non_public_hosts(url):
    with pytest.raises(ks._UnsafeUrlError):
        ks._assert_public_host(url)


def test_login_wall_is_not_knowledge():
    assert ks._looks_like_login_page("Sign in", "Please log in to continue. Sign in with email.")
    assert not ks._looks_like_login_page("Docs", "x" * 2000)


def test_source_type_detection_and_handle():
    assert ks.detect_source_type("https://x.com/Foo") == "twitter"
    assert ks.detect_source_type("https://youtube.com/@bar") == "youtube"
    assert ks.detect_source_type("https://example.com") == "website"
    assert ks.x_handle("https://twitter.com/Foo_Bar/status/1") == "foo_bar"


class FakeResp:
    def __init__(self, code=200, body=None, headers=None):
        self.status_code, self._b, self.headers = code, body or {}, headers or {}

    def json(self):
        return self._b


def tweets(ids, text="post"):
    return [{"id": str(i), "text": f"{text} {i}", "createdAt": "2026-10-01T10:00:00.000Z"} for i in ids]


def test_x_first_import_is_bounded_and_complete(monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "TWITTERAPI_IO_KEY", "k")
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(body={
        "tweets": tweets(range(100, 70, -1)), "has_next_page": True, "next_cursor": "c1"}))
    r = ks.fetch_source("twitter", "https://x.com/foo", initial_cap=20)
    assert r["ok"] and not r["incomplete"]               # bounded first import is complete by design
    assert r["usage"]["requests"] == 1
    assert r["state"]["high_water"] == "100" and r["state"]["cursor"] is None


def test_x_incremental_stops_at_high_water_and_reconciles_deletions(monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "TWITTERAPI_IO_KEY", "k")
    import requests
    state = {"high_water": "100", "posts": [{"id": str(i), "text": f"old {i}", "created_at": None}
                                            for i in (100, 99, 98)]}
    # newest page: 103, 102, 100 (98/99 are now outside; 101 never existed)
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(body={
        "tweets": tweets([103, 102, 100]), "has_next_page": True, "next_cursor": "c"}))
    r = ks.fetch_source("twitter", "https://x.com/foo", state=state)
    ids = {p["id"] for p in r["state"]["posts"]}
    assert {"103", "102", "100"} <= ids
    assert r["usage"]["requests"] == 1                   # stopped at the high-water mark
    assert r["state"]["high_water"] == "103"


def test_x_page_cap_keeps_cursor_and_does_not_advance_high_water(monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "TWITTERAPI_IO_KEY", "k")
    import requests
    pages = iter([tweets([300, 299]), tweets([298, 297])])
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(body={
        "tweets": next(pages), "has_next_page": True, "next_cursor": "more"}))
    state = {"high_water": "10", "posts": [{"id": "10", "text": "t", "created_at": None}]}
    r = ks.fetch_source("twitter", "https://x.com/foo", state=state, max_pages=2)
    assert r["incomplete"] is True
    assert r["state"]["cursor"] == "more"
    assert r["state"]["high_water"] == "10" and r["state"]["pending_max_id"] == "300"


def test_x_rate_limit_and_invalid_credentials(monkeypatch):
    from config import Config
    import requests
    monkeypatch.setattr(Config, "TWITTERAPI_IO_KEY", "k")
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(429, headers={"Retry-After": "7200"}))
    r = ks.fetch_source("twitter", "https://x.com/foo")
    assert not r["ok"] and r["rate_limited_until"] > datetime.utcnow() + timedelta(minutes=100)
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(401))
    r = ks.fetch_source("twitter", "https://x.com/foo")
    assert not r["ok"] and r["fatal"] is True
    monkeypatch.setattr(Config, "TWITTERAPI_IO_KEY", "")
    assert ks.fetch_source("twitter", "https://x.com/foo")["fatal"] is True


def test_youtube_without_key_is_a_clear_message(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    r = ks.fetch_source("youtube", "https://youtube.com/@x")
    assert not r["ok"] and "YouTube Data API key" in r["error"]


# ── sync: versions, safety ─────────────────────────────────────────────────────
def test_first_sync_creates_version_document_and_marks_unknown_publication(db, monkeypatch, embed_calls):
    s = make_source(db, label="Docs")
    mock_fetch(monkeypatch, [ok_result("Alpha beta gamma " * 20)])
    res = kb_sources.sync_source(db, s.id)
    assert res["ok"] and not res["unchanged"]
    db.refresh(s)
    assert s.last_sync_status == "success" and s.active_version_id
    d = doc_of(db, s)
    assert d and d.chunks and d.file_type == "website" and d.enabled is True
    label = kb_index.labels_for_docs(db, [d])[d.id]
    assert "external source: website" in label and "publication date unknown" in label and "fetched " in label
    assert d.source_id == s.id


def test_unchanged_content_is_not_re_embedded(db, monkeypatch, embed_calls):
    s = make_source(db)
    mock_fetch(monkeypatch, [ok_result("Same text " * 30)])
    assert kb_sources.sync_source(db, s.id)["ok"]
    n = len(embed_calls)
    s.last_synced_at = datetime.utcnow() - timedelta(minutes=5)
    db.commit()
    res = kb_sources.sync_source(db, s.id)
    assert res["ok"] and res["unchanged"] is True
    assert len(embed_calls) == n                       # no new embedding spend


def test_failed_fetch_keeps_the_old_version(db, monkeypatch, embed_calls):
    s = make_source(db)
    mock_fetch(monkeypatch, [ok_result("Good text " * 30)])
    kb_sources.sync_source(db, s.id)
    db.refresh(s)
    vid, before = s.active_version_id, doc_of(db, s).content_text
    s.last_synced_at = datetime.utcnow() - timedelta(minutes=5)
    db.commit()
    mock_fetch(monkeypatch, [ks._result(False, error="That page looks like a login or bot-check page, not content. Nothing was changed.")])
    res = kb_sources.sync_source(db, s.id)
    assert not res["ok"]
    db.refresh(s)
    assert s.active_version_id == vid and doc_of(db, s).content_text == before
    assert s.last_sync_status == "error" and "login" in s.last_sync_error
    assert kb_sources.source_status(s, True) == "stale"       # still serving the last good text


def test_embedding_failure_keeps_the_old_version(db, monkeypatch):
    s = make_source(db)
    monkeypatch.setattr(kb_index, "_embed", lambda texts: [[1.0, 0.0, 1.0] for _ in texts])
    mock_fetch(monkeypatch, [ok_result("Version one " * 30)])
    kb_sources.sync_source(db, s.id)
    db.refresh(s)
    vid = s.active_version_id
    s.last_synced_at = datetime.utcnow() - timedelta(minutes=5)
    db.commit()
    monkeypatch.setattr(kb_index, "_embed", lambda texts: [None for _ in texts])
    mock_fetch(monkeypatch, [ok_result("Version two " * 30)])
    res = kb_sources.sync_source(db, s.id)
    assert not res["ok"] and "Embeddings" in res["error"]
    db.refresh(s)
    assert s.active_version_id == vid


def test_changed_content_supersedes_and_rollback_reindexes(db, monkeypatch, embed_calls):
    from models import KnowledgeSourceVersion
    s = make_source(db)
    mock_fetch(monkeypatch, [ok_result("First facts " * 30)])
    kb_sources.sync_source(db, s.id)
    s.last_synced_at = datetime.utcnow() - timedelta(minutes=5)
    db.commit()
    mock_fetch(monkeypatch, [ok_result("Second facts " * 30)])
    kb_sources.sync_source(db, s.id)
    db.refresh(s)
    vs = db.query(KnowledgeSourceVersion).filter_by(source_id=s.id).order_by(KnowledgeSourceVersion.version_no).all()
    assert [v.status for v in vs] == ["superseded", "active"]
    assert "Second" in doc_of(db, s).content_text
    ok, err = kb_sources.activate_version(db, s.id, vs[0].id)
    assert ok and err is None
    db.refresh(s)
    assert s.active_version_id == vs[0].id and "First" in doc_of(db, s).content_text
    ok, err = kb_sources.activate_version(db, s.id, 99999999)
    assert not ok


def test_history_is_bounded_to_five_versions(db, monkeypatch, embed_calls):
    from models import KnowledgeSourceVersion
    s = make_source(db)
    for i in range(7):
        s.last_synced_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
        mock_fetch(monkeypatch, [ok_result(f"Revision {i} " * 30)])
        kb_sources.sync_source(db, s.id)
    assert db.query(KnowledgeSourceVersion).filter_by(source_id=s.id).count() == kb_sources.KEEP_VERSIONS


def test_double_click_is_busy(db, monkeypatch, embed_calls):
    s = make_source(db)
    mock_fetch(monkeypatch, [ok_result("Text " * 30)])
    assert kb_sources.sync_source(db, s.id)["ok"]
    res = kb_sources.sync_source(db, s.id)             # within the minute
    assert not res["ok"] and res["code"] == "busy"


def test_free_server_cannot_sync(db, monkeypatch, embed_calls):
    s = make_source(db, guild_id=FREE)
    seen = mock_fetch(monkeypatch, [ok_result("x " * 100)])
    res = kb_sources.sync_source(db, s.id)
    assert not res["ok"] and res["code"] == "plan" and not seen     # provider never called


def test_kill_switches(db, monkeypatch, embed_calls):
    s = make_source(db)
    seen = mock_fetch(monkeypatch, [ok_result("x " * 100)])
    monkeypatch.setenv("KNOWLEDGE_SOURCES_ENABLED", "0")
    assert kb_sources.sync_source(db, s.id)["code"] == "disabled"
    monkeypatch.delenv("KNOWLEDGE_SOURCES_ENABLED")
    monkeypatch.setenv("KNOWLEDGE_SCHEDULED_SYNC_ENABLED", "0")
    assert kb_sources.sync_source(db, s.id, trigger="scheduled")["code"] == "disabled"
    assert not seen


def test_disabled_source_is_not_searchable_and_enable_restores(db, monkeypatch, embed_calls):
    s = make_source(db)
    mock_fetch(monkeypatch, [ok_result("Refund policy is thirty days " * 20)])
    kb_sources.sync_source(db, s.id)
    payload, status = kb_sources.update_source(db, s, {"enabled": False}, True)
    assert status == 200 and doc_of(db, s).enabled is False
    res = kb_sources.sync_source(db, s.id)
    assert res["code"] == "disabled"
    kb_sources.update_source(db, s, {"enabled": True}, True)
    assert doc_of(db, s).enabled is True


def test_remove_source_deletes_everything_together(db, monkeypatch, embed_calls):
    from models import KnowledgeDocument, KnowledgeSource, KnowledgeSourceVersion
    s = make_source(db)
    mock_fetch(monkeypatch, [ok_result("Bye " * 50)])
    kb_sources.sync_source(db, s.id)
    sid = s.id
    kb_sources.delete_source(db, s)
    assert db.get(KnowledgeSource, sid) is None
    assert db.query(KnowledgeDocument).filter_by(source_id=sid).count() == 0
    assert db.query(KnowledgeSourceVersion).filter_by(source_id=sid).count() == 0


def test_partial_import_is_flagged(db, monkeypatch, embed_calls):
    s = make_source(db, stype="twitter")
    mock_fetch(monkeypatch, [ok_result("[2026-10-01] post " * 20, incomplete=True,
                                       state={"posts": [], "cursor": "c", "high_water": None},
                                       usage={"requests": 1, "resources": 5})])
    from config import Config
    monkeypatch.setattr(Config, "TWITTERAPI_IO_KEY", "k")
    res = kb_sources.sync_source(db, s.id)
    db.refresh(s)
    assert res["ok"] and res["partial"] and s.last_sync_status == "partial"
    assert kb_sources.source_status(s, True) == "partial"


# ── X: cooldown, budgets, failure policy ───────────────────────────────────────
def x_ok(**kw):
    return ok_result("[2026-10-01] hello " * 20, state={"posts": [], "high_water": "5", "cursor": None},
                     usage=kw.pop("usage", {"requests": 1, "resources": 3}), **kw)


@pytest.fixture()
def x_env(monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "TWITTERAPI_IO_KEY", "k")
    # Shared daily budgets are generous here so tests do not starve each other;
    # the budget tests tighten the one they exercise.
    monkeypatch.setenv("X_SYNC_WORKSPACE_PAGES_PER_DAY", "10000")
    monkeypatch.setenv("X_SYNC_CREDENTIAL_PAGES_PER_DAY", "10000")
    monkeypatch.setenv("X_SYNC_SOURCE_PAGES_PER_30D", "10000")


def test_x_cooldown_is_shared_across_sources_of_the_same_handle(db, monkeypatch, embed_calls, x_env):
    a = make_source(db, stype="twitter", url="https://x.com/sharedhandle")
    b = make_source(db, guild_id=PRO2, stype="twitter", url="https://twitter.com/SharedHandle")
    mock_fetch(monkeypatch, [x_ok()])
    assert kb_sources.sync_source(db, a.id)["ok"]
    res = kb_sources.sync_source(db, b.id)             # same owner + canonical handle
    assert not res["ok"] and res["code"] == "cooldown" and res["next_available_at"] > datetime.utcnow()


def test_x_scheduled_after_manual_is_blocked_by_the_same_window(db, monkeypatch, embed_calls, x_env):
    s = make_source(db, stype="twitter", url="https://x.com/windowhandle")
    mock_fetch(monkeypatch, [x_ok()])
    assert kb_sources.sync_source(db, s.id, trigger="manual")["ok"]
    assert kb_sources.sync_source(db, s.id, trigger="scheduled")["code"] == "cooldown"


def test_x_cooldown_claim_is_atomic(db):
    key = "x:test:atomic"
    now = datetime.utcnow()
    assert kg.claim_cooldown(db, key, now, timedelta(hours=24)) is True
    assert kg.claim_cooldown(db, key, now, timedelta(hours=24)) is False


def test_x_budget_exhaustion_blocks_and_refunds_the_window(db, monkeypatch, embed_calls, x_env):
    from models import KnowledgeSyncLedger
    s = make_source(db, stype="twitter", url="https://x.com/budgethandle")
    monkeypatch.setenv("X_SYNC_SOURCE_PAGES_PER_30D", "0")
    seen = mock_fetch(monkeypatch, [x_ok()])
    res = kb_sources.sync_source(db, s.id)
    assert not res["ok"] and res["code"] == "budget" and not seen     # nothing fetched
    # the window was handed back, so lifting the budget lets the next attempt through
    monkeypatch.delenv("X_SYNC_SOURCE_PAGES_PER_30D")
    assert kb_sources.sync_source(db, s.id)["ok"]
    assert db.query(KnowledgeSyncLedger).filter_by(source_id=s.id).count() == 1


def test_x_failed_attempt_still_counts_against_the_budget(db, monkeypatch, embed_calls, x_env):
    s = make_source(db, stype="twitter", url="https://x.com/failhandle")
    mock_fetch(monkeypatch, [ks._result(False, error="boom", usage={"requests": 2, "resources": 0})])
    kb_sources.sync_source(db, s.id)
    pages = kg._sum_pages(db, datetime.utcnow() - timedelta(days=1), source_id=s.id)
    assert pages >= 2


def test_x_rate_limit_extends_the_window_and_delays_the_schedule(db, monkeypatch, embed_calls, x_env):
    s = make_source(db, stype="twitter", url="https://x.com/limited", sync_schedule="daily",
                    next_sync_at=datetime.utcnow())
    until = datetime.utcnow() + timedelta(hours=40)
    mock_fetch(monkeypatch, [ks._result(False, error="rate", rate_limited_until=until,
                                        usage={"requests": 1, "resources": 0})])
    kb_sources.sync_source(db, s.id)
    db.refresh(s)
    cd = kg.cooldown_until(db, kg.cooldown_key(OWNER, "limited"))
    assert cd >= until - timedelta(seconds=1)
    assert s.next_sync_at >= until - timedelta(seconds=1)


def test_invalid_credentials_pause_the_schedule(db, monkeypatch, embed_calls, x_env):
    s = make_source(db, stype="twitter", url="https://x.com/badkey", sync_schedule="daily",
                    next_sync_at=datetime.utcnow())
    mock_fetch(monkeypatch, [ks._result(False, error="rejected", fatal=True, usage={"requests": 1, "resources": 0})])
    kb_sources.sync_source(db, s.id)
    db.refresh(s)
    assert s.schedule_paused_reason and s.next_sync_at is None
    assert kg.due_sources(db, datetime.utcnow() + timedelta(days=9)) == [] or s not in kg.due_sources(
        db, datetime.utcnow() + timedelta(days=9))


def test_repeated_failures_pause_the_schedule_but_not_manual(db, monkeypatch, embed_calls):
    s = make_source(db, sync_schedule="daily", next_sync_at=datetime.utcnow())
    for _ in range(3):
        s.last_synced_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
        mock_fetch(monkeypatch, [ks._result(False, error="down")])
        kb_sources.sync_source(db, s.id)
    db.refresh(s)
    assert s.consecutive_failures == 3 and "Paused after 3" in s.schedule_paused_reason
    m = make_source(db)                                  # manual sources never get paused
    for _ in range(4):
        m.last_synced_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
        kb_sources.sync_source(db, m.id)
    db.refresh(m)
    assert m.schedule_paused_reason is None


# ── schedules ──────────────────────────────────────────────────────────────────
def test_opting_in_never_fetches_immediately(db):
    s = make_source(db)
    payload, status = kb_sources.update_source(db, s, {"sync_schedule": "daily"}, True)
    assert status == 200
    db.refresh(s)
    assert s.next_sync_at > datetime.utcnow() + timedelta(hours=23)


def test_free_plan_cannot_pick_a_schedule_and_bad_values_are_rejected(db):
    s = make_source(db)
    assert kb_sources.update_source(db, s, {"sync_schedule": "daily"}, False)[1] == 402
    assert kb_sources.update_source(db, s, {"sync_schedule": "hourly"}, True)[1] == 400
    kb_sources.update_source(db, s, {"sync_schedule": "weekly"}, True)
    kb_sources.update_source(db, s, {"sync_schedule": "manual"}, True)
    db.refresh(s)
    assert s.next_sync_at is None and s.schedule_paused_reason is None


def _fresh():
    from database import SessionLocal
    SessionLocal.remove()
    return SessionLocal()


def test_scheduler_runs_only_due_opt_in_sources(db, monkeypatch, embed_calls):
    manual = make_source(db)                                                    # never due
    future = make_source(db, sync_schedule="daily", next_sync_at=datetime.utcnow() + timedelta(hours=5))
    due = make_source(db, sync_schedule="daily", next_sync_at=datetime.utcnow() - timedelta(minutes=1))
    off = make_source(db, sync_schedule="daily", next_sync_at=datetime.utcnow() - timedelta(minutes=1),
                      enabled=False)
    paused = make_source(db, sync_schedule="daily", next_sync_at=datetime.utcnow() - timedelta(minutes=1),
                         schedule_paused_reason="Paused")
    due_id, due_url = due.id, due.url
    skipped = [manual.url, future.url, off.url, paused.url]
    seen_urls = []

    def fake(source_type, url, state=None, max_pages=3, initial_cap=60):
        seen_urls.append(url)
        return ok_result("Scheduled text " * 30)
    monkeypatch.setattr(ks, "fetch_source", fake)
    ran = kb_sources.run_scheduled_sync(10)       # closes the thread-local session, like a worker thread
    assert due_url in seen_urls and ran >= 1
    for u in skipped:
        assert u not in seen_urls
    from models import KnowledgeSource
    check = _fresh()
    try:
        assert check.get(KnowledgeSource, due_id).next_sync_at > datetime.utcnow() + timedelta(hours=23)
    finally:
        check.close()


def test_scheduler_kill_switch_and_lapsed_plan(db, monkeypatch, embed_calls):
    s = make_source(db, guild_id=FREE, sync_schedule="daily", next_sync_at=datetime.utcnow() - timedelta(minutes=1))
    sid = s.id
    seen = mock_fetch(monkeypatch, [ok_result("x " * 100)])
    monkeypatch.setenv("KNOWLEDGE_SCHEDULED_SYNC_ENABLED", "0")
    assert kb_sources.run_scheduled_sync(10) == 0
    monkeypatch.delenv("KNOWLEDGE_SCHEDULED_SYNC_ENABLED")
    kb_sources.run_scheduled_sync(10)                    # free plan: runs the gate, fetches nothing
    assert not seen
    from models import KnowledgeSource
    check = _fresh()
    try:
        assert check.get(KnowledgeSource, sid).next_sync_at > datetime.utcnow() + timedelta(hours=23)   # not retried every tick
    finally:
        check.close()


# ── preview (stored rows only) ────────────────────────────────────────────────
def test_preview_reads_stored_text_and_never_calls_a_provider(db, monkeypatch, embed_calls):
    s = make_source(db)
    mock_fetch(monkeypatch, [ok_result("Hello knowledge world. " * 20, published_at=datetime(2026, 9, 1))])
    kb_sources.sync_source(db, s.id)

    def boom(*a, **k):
        raise AssertionError("preview must not fetch or embed")
    monkeypatch.setattr(ks, "fetch_source", boom)
    monkeypatch.setattr(kb_index, "_embed", boom)
    p = kb_sources.preview_payload(db, s, "knowledge")
    assert p["available"] and p["status"] == "ok" and p["match_count"] > 0
    assert p["dates"]["published"].startswith("2026-09-01")
    assert p["active_version"]["version_no"] == 1


def test_preview_of_a_never_synced_source_says_unavailable(db):
    s = make_source(db)
    p = kb_sources.preview_payload(db, s)
    assert p["available"] is False and p["status"] == "unavailable" and p["text"] is None


# ── retrieval + prompt ─────────────────────────────────────────────────────────
def test_retrieval_context_is_labelled_and_disabled_sources_are_excluded(db, monkeypatch):
    from models import KnowledgeDocument
    gid = PRO2
    db.query(KnowledgeDocument).filter_by(guild_id=gid).delete()
    db.commit()
    s = make_source(db, guild_id=gid, label="Site")
    monkeypatch.setattr(kb_index, "_embed", lambda texts: [[1.0, 0.0] for _ in texts])
    mock_fetch(monkeypatch, [ok_result("The airdrop snapshot is on 2026-11-01. " * 10, published_at=datetime(2026, 10, 2))])
    kb_sources.sync_source(db, s.id)
    system, confident = knowledge.grounded_with_confidence(gid, "when is the airdrop snapshot")
    assert system and confident
    assert "[Source: Site | external source: website | newest content published 2026-10-02 | fetched " in system
    kb_sources.update_source(db, s, {"enabled": False}, True)
    system, _ = knowledge.grounded_with_confidence(gid, "when is the airdrop snapshot")
    assert system is None or "airdrop" not in system


def test_prompt_treats_context_as_data_and_defines_conflict():
    h = knowledge._PROMPT_HEADER
    assert "DATA" in h and "CONFLICT" in h and "NO_ANSWER" in h
    assert "do NOT show when a fact was announced" in h
    assert knowledge.is_no_answer("CONFLICT") and knowledge.is_conflict(" `conflict.` ")
    assert not knowledge.is_no_answer("No answers are given for that.")


# ── HTTP layer ─────────────────────────────────────────────────────────────────
@pytest.fixture()
def client():
    import app as appmod
    import auth
    from config import Config
    c = appmod.app.test_client()
    c.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(OWNER))
    return c


def test_api_requires_pro_to_add_a_source(client, db):
    from models import UserGuild
    db.add(UserGuild(user_id=OWNER, guild_id=FREE, can_manage=True, is_owner=False))
    db.commit()
    r = client.post(f"/api/guilds/{FREE}/knowledge/sources", json={"url": "https://example.com"})
    assert r.status_code == 402 and r.get_json()["error"] == "pro_required"


def test_api_add_list_patch_delete_and_isolation(client, db, monkeypatch, embed_calls):
    from models import KnowledgeSource
    db.query(KnowledgeSource).filter_by(guild_id=PRO).delete()    # earlier tests filled this server's cap
    db.commit()
    r = client.post(f"/api/guilds/{PRO}/knowledge/sources", json={"url": "example.org/docs", "label": "Docs"})
    assert r.status_code == 201, r.get_json()
    src = r.get_json()["source"]
    assert src["url"] == "https://example.org/docs" and src["sync_schedule"] == "manual"
    assert client.post(f"/api/guilds/{PRO}/knowledge/sources", json={"url": "example.org/docs"}).status_code == 409
    assert client.post(f"/api/guilds/{PRO}/knowledge/sources", json={"url": "https://x.com/"}).status_code == 400
    lst = client.get(f"/api/guilds/{PRO}/knowledge/sources").get_json()
    assert any(s["id"] == src["id"] for s in lst["sources"]) and lst["pro"] is True
    # a source id from another server is a 404 on this server's URL
    assert client.patch(f"/api/guilds/{PRO2}/knowledge/sources/{src['id']}", json={"enabled": False}).status_code == 404
    assert client.get(f"/api/guilds/{PRO2}/knowledge/sources/{src['id']}/preview").status_code == 404
    # someone else's server is forbidden outright
    assert client.get(f"/api/guilds/{STRANGER}/knowledge/sources").status_code == 403

    mock_fetch(monkeypatch, [ok_result("API sync text " * 30)])
    r = client.post(f"/api/guilds/{PRO}/knowledge/sources/{src['id']}/sync")
    assert r.status_code == 200 and r.get_json()["source"]["last_sync_status"] == "success"
    r = client.post(f"/api/guilds/{PRO}/knowledge/sources/{src['id']}/sync")
    assert r.status_code == 429                                           # busy
    r = client.get(f"/api/guilds/{PRO}/knowledge/sources/{src['id']}/preview?q=sync")
    assert r.status_code == 200 and r.get_json()["match_count"] > 0
    assert len(client.get(f"/api/guilds/{PRO}/knowledge/sources/{src['id']}/versions").get_json()["versions"]) == 1
    # source documents never show up (or can be edited) as ordinary documents
    docs = client.get(f"/api/guilds/{PRO}/knowledge").get_json()["documents"]
    assert all(d["source_id"] is None for d in docs)
    from models import KnowledgeDocument
    sdoc = db.query(KnowledgeDocument).filter_by(source_id=src["id"]).first()
    assert client.delete(f"/api/guilds/{PRO}/knowledge/{sdoc.id}").status_code == 400
    assert client.put(f"/api/guilds/{PRO}/knowledge/{sdoc.id}", json={"enabled": False}).status_code == 400

    assert client.patch(f"/api/guilds/{PRO}/knowledge/sources/{src['id']}", json={"sync_schedule": "weekly"}).status_code == 200
    assert client.delete(f"/api/guilds/{PRO}/knowledge/sources/{src['id']}").status_code == 200
    assert client.get(f"/api/guilds/{PRO}/knowledge/sources/{src['id']}/preview").status_code == 404


def test_api_source_limit(client, db):
    from models import KnowledgeSource
    db.query(KnowledgeSource).filter_by(guild_id=PRO2).delete()
    db.commit()
    from models import UserGuild  # noqa: F401
    for i in range(kb_sources.MAX_SOURCES):
        make_source(db, guild_id=PRO2, url=f"https://limit.example/{i}")
    r = client.post(f"/api/guilds/{PRO2}/knowledge/sources", json={"url": "https://limit.example/overflow"})
    assert r.status_code == 400 and r.get_json()["error"] == "source_limit"


# ── cross-check regressions ────────────────────────────────────────────────────
def test_reenabling_a_scheduled_source_starts_a_fresh_interval(db):
    s = make_source(db, sync_schedule="daily", next_sync_at=datetime.utcnow() - timedelta(days=3))
    kb_sources.update_source(db, s, {"enabled": False}, True)
    kb_sources.update_source(db, s, {"enabled": True}, True)
    db.refresh(s)
    assert s.next_sync_at > datetime.utcnow() + timedelta(hours=23)       # not due the moment it is switched back on
    assert s not in kg.due_sources(db, datetime.utcnow())


def test_retrieval_window_covers_a_full_pro_server(db):
    """50 documents + 10 sources must all be searchable (the old window was 50)."""
    from models import KnowledgeDocument
    gid = STRANGER
    db.query(KnowledgeDocument).filter_by(guild_id=gid).delete()
    for i in range(60):
        db.add(KnowledgeDocument(guild_id=gid, title=f"d{i}", content="", content_text=f"topic{i} body", enabled=True,
                                 chunks=[{"text": f"topic{i} body", "embedding": [1.0, 0.0]}]))
    db.commit()
    system, confident = knowledge.grounded_with_confidence(gid, "topic59 body")      # the LAST one
    assert system and "topic59" in system
