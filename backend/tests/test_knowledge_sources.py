"""Knowledge-source preview, versioning and controlled X sync.

Run from the repo root:  python -m pytest backend/tests/test_knowledge_sources.py
In-memory SQLite, every provider call mocked: nothing here touches X, YouTube,
Telegram or an AI provider.
"""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
import requests
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from backend import knowledge_sync as kg
from backend.bot_features import knowledge_sources as ks
from backend.bot_features.knowledge_base import KnowledgeBaseSystem, source_label, _is_no_answer, _is_conflict
from backend.models import (
    db, User, TelegramGroup, KnowledgeSource, KnowledgeDocument, KnowledgeSourceVersion,
    KnowledgeSyncLedger,
)
from backend.routes.telegram_groups import tg_groups_bp
import backend.assistant.hub_models  # noqa: F401


# ── harness ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("GROUP_TEAM_ACCESS_ENABLED", raising=False)
    for k in ("X_SYNC_WORKSPACE_PAGES_PER_DAY", "X_SYNC_CREDENTIAL_PAGES_PER_DAY",
              "X_SYNC_SOURCE_PAGES_PER_30D", "X_SYNC_MAX_PAGES_PER_RUN", "KNOWLEDGE_X_SYNC_ENABLED",
              "KNOWLEDGE_SOURCES_ENABLED"):
        monkeypatch.delenv(k, raising=False)
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
                      JWT_TOKEN_LOCATION=["headers"], TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(tg_groups_bp)
    with app.app_context():
        db.create_all()
        pro = User(email="pro@x.io", full_name="Pro", auth_provider="email", subscription_tier="pro")
        free = User(email="free@x.io", full_name="Free", auth_provider="email")
        stranger = User(email="s@x.io", full_name="S", auth_provider="email")
        db.session.add_all([pro, free, stranger])
        db.session.flush()
        db.session.add_all([
            TelegramGroup(telegram_group_id="-100A", title="A", owner_user_id=pro.id, bot_status="active"),
            TelegramGroup(telegram_group_id="-100F", title="F", owner_user_id=free.id, bot_status="active"),
        ])
        db.session.commit()
        ids = dict(pro=pro.id, free=free.id, stranger=stranger.id)
        tokens = {k: create_access_token(identity=str(v)) for k, v in ids.items()}
    # No real embedding call: every chunk gets a fixed vector; count calls.
    calls = {"embed": 0}

    def fake_embed(self, texts, **kw):
        calls["embed"] += 1
        return [[0.1, 0.2, 0.3] for _ in texts]
    monkeypatch.setattr(KnowledgeBaseSystem, "_embed", fake_embed)
    monkeypatch.setattr("backend.secret_vault.get_secret", lambda name, default=None: "k" if name == "TWITTERAPI_IO_KEY" else default)
    return NS(app=app, client=app.test_client(), ids=ids, calls=calls,
              h=lambda who: {"Authorization": f"Bearer {tokens[who]}"}, kb=KnowledgeBaseSystem(app))


def _mk_source(env, url="https://x.com/Acme", stype="twitter", gid="-100A", **kw):
    with env.app.app_context():
        s = KnowledgeSource(telegram_group_id=gid, source_type=stype, url=url, label="src", **kw)
        db.session.add(s)
        db.session.commit()
        return s.id


def _sync(env, sid, trigger="manual"):
    with env.app.app_context():
        return env.kb.sync_external_source(KnowledgeSource.query.get(sid), trigger=trigger)


class _Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._b, self.headers = status, body or {}, headers or {}

    def json(self):
        return self._b


def _tweet(i, text=None):
    return {"id": str(i), "text": text or f"post {i}", "createdAt": f"2026-10-{(i % 28) + 1:02d}T10:00:00Z"}


class _X:
    """Scripted twitterapi.io: list of (tweets, next_cursor) pages per call; records every request."""

    def __init__(self, monkeypatch, pages):
        self.pages, self.calls = list(pages), []
        monkeypatch.setattr(requests, "get", self._get)

    def _get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(dict(params or {}))
        item = self.pages.pop(0)
        if isinstance(item, _Resp):
            return item
        tweets, nxt = item
        return _Resp(200, {"data": {"tweets": tweets}, "has_next_page": bool(nxt), "next_cursor": nxt})


def _active_text(env, sid):
    with env.app.app_context():
        s = KnowledgeSource.query.get(sid)
        return KnowledgeSourceVersion.query.get(s.active_version_id).text


# ── X connector: bounded, incremental, resumable ──────────────────────────────

def test_first_x_import_is_bounded_and_complete_by_design(env, monkeypatch):
    monkeypatch.setenv("X_SYNC_INITIAL_MAX_POSTS", "5")
    x = _X(monkeypatch, [([_tweet(i) for i in range(100, 95, -1)], "c1"), ([_tweet(i) for i in range(95, 90, -1)], "c2")])
    sid = _mk_source(env)
    r = _sync(env, sid)
    assert r["ok"] and not r["partial"]
    assert len(x.calls) == 1                       # stopped at the initial cap, no second page
    with env.app.app_context():
        s = KnowledgeSource.query.get(sid)
        assert s.sync_state["high_water"] == "100" and s.sync_state["cursor"] is None


def test_incremental_run_stops_at_high_water_and_keeps_old_posts(env, monkeypatch):
    sid = _mk_source(env)
    _X(monkeypatch, [([_tweet(10), _tweet(9)], None)])
    assert _sync(env, sid)["ok"]
    with env.app.app_context():                       # second run is a different day
        env.app.cd = kg.cooldown_key(KnowledgeSource.query.get(sid), kg.owner_user_id(KnowledgeSource.query.get(sid)), "acme")
        db.session.execute(db.text("UPDATE knowledge_sync_cooldowns SET next_eligible_at = :n"), {"n": datetime.utcnow() - timedelta(minutes=1)})
        db.session.commit()
    x = _X(monkeypatch, [([_tweet(12), _tweet(11), _tweet(10), _tweet(9)], "more"), ([_tweet(1)], None)])
    r = _sync(env, sid)
    assert r["ok"]
    assert len(x.calls) == 1                          # page 1 already reached the high-water mark
    text = _active_text(env, sid)
    assert "post 12" in text and "post 9" in text      # merged with retained posts, not wiped


def test_edit_and_deletion_in_the_latest_window_are_reconciled(env, monkeypatch):
    sid = _mk_source(env)
    _X(monkeypatch, [([_tweet(10, "old reward 5%"), _tweet(9), _tweet(8)], None)])
    _sync(env, sid)
    with env.app.app_context():
        db.session.execute(db.text("UPDATE knowledge_sync_cooldowns SET next_eligible_at = :n"), {"n": datetime.utcnow() - timedelta(minutes=1)})
        db.session.commit()
    _X(monkeypatch, [([_tweet(10, "reward is now 7%"), _tweet(8)], None)])   # 9 deleted, 10 edited
    assert _sync(env, sid)["ok"]
    text = _active_text(env, sid)
    assert "reward is now 7%" in text and "old reward 5%" not in text
    assert "post 9" not in text and "post 8" in text


def test_page_cap_keeps_a_checkpoint_and_resumes_without_losing_posts(env, monkeypatch):
    monkeypatch.setenv("X_SYNC_MAX_PAGES_PER_RUN", "1")
    sid = _mk_source(env)
    _X(monkeypatch, [([_tweet(10), _tweet(9)], None)])
    _sync(env, sid)                                   # high-water = 10
    with env.app.app_context():
        db.session.execute(db.text("UPDATE knowledge_sync_cooldowns SET next_eligible_at = :n"), {"n": datetime.utcnow() - timedelta(minutes=1)})
        db.session.commit()
    _X(monkeypatch, [([_tweet(20), _tweet(19)], "cur-1")])            # cap hit before reaching 10
    r = _sync(env, sid)
    assert r["ok"] and r["partial"]
    with env.app.app_context():
        s = KnowledgeSource.query.get(sid)
        assert s.sync_state["high_water"] == "10"      # NOT advanced past unprocessed posts
        assert s.sync_state["cursor"] == "cur-1" and s.sync_state["pending_max_id"] == "20"
        assert s.last_sync_status == "partial"
        assert KnowledgeSourceVersion.query.get(s.active_version_id).is_partial is True
        db.session.execute(db.text("UPDATE knowledge_sync_cooldowns SET next_eligible_at = :n"), {"n": datetime.utcnow() - timedelta(minutes=1)})
        db.session.commit()
    x = _X(monkeypatch, [([_tweet(15), _tweet(11), _tweet(10)], None)])
    assert _sync(env, sid)["ok"]
    assert x.calls[0].get("cursor") == "cur-1"          # resumed where it stopped
    text = _active_text(env, sid)
    assert all(f"post {i}" in text for i in (20, 19, 15, 11, 10, 9))
    with env.app.app_context():
        st = KnowledgeSource.query.get(sid).sync_state
        assert st["high_water"] == "20" and st["cursor"] is None


# ── gate: cooldown, budgets, entitlement, rate limit, concurrency ─────────────

def test_shared_cooldown_blocks_a_second_sync_and_makes_no_provider_call(env, monkeypatch):
    sid = _mk_source(env)
    x = _X(monkeypatch, [([_tweet(5)], None)])
    assert _sync(env, sid)["ok"]
    x2 = _X(monkeypatch, [])
    r = _sync(env, sid, trigger="scheduled")           # a schedule right after a manual run
    assert not r["ok"] and r["code"] == "cooldown" and r["next_available_at"]
    assert x2.calls == [] and len(x.calls) == 1


def test_two_sources_for_one_handle_share_one_window(env, monkeypatch):
    a, b = _mk_source(env), _mk_source(env, url="https://twitter.com/acme")
    _X(monkeypatch, [([_tweet(5)], None)])
    assert _sync(env, a)["ok"]
    assert _sync(env, b)["code"] == "cooldown"


def test_claim_cooldown_is_atomic(env):
    with env.app.app_context():
        now = datetime.utcnow()
        assert kg.claim_cooldown(db, "k", now, timedelta(hours=24)) is True
        assert kg.claim_cooldown(db, "k", now, timedelta(hours=24)) is False   # racing second request loses
        assert kg.claim_cooldown(db, "k", now + timedelta(hours=25), timedelta(hours=24)) is True


def test_budget_exhaustion_denies_without_provider_call_and_releases_cooldown(env, monkeypatch):
    monkeypatch.setenv("X_SYNC_WORKSPACE_PAGES_PER_DAY", "1")
    monkeypatch.setenv("X_SYNC_MAX_PAGES_PER_RUN", "1")
    a, b = _mk_source(env), _mk_source(env, url="https://x.com/other")
    _X(monkeypatch, [([_tweet(5)], None)])
    assert _sync(env, a)["ok"]
    x = _X(monkeypatch, [])
    r = _sync(env, b)
    assert r["code"] == "budget" and "workspace" in r["error"]
    assert x.calls == []
    with env.app.app_context():
        # the denied attempt did not burn b's cooldown (it never reached the provider)
        assert kg.cooldown_until(db, kg.cooldown_key(KnowledgeSource.query.get(b), kg.owner_user_id(KnowledgeSource.query.get(b)), "other")) is None


def test_shared_credential_budget_is_enforced_across_workspaces(env, monkeypatch):
    monkeypatch.setenv("X_SYNC_CREDENTIAL_PAGES_PER_DAY", "1")
    with env.app.app_context():
        owner2 = User(email="p2@x.io", full_name="P2", auth_provider="email", subscription_tier="pro")
        db.session.add(owner2)
        db.session.flush()
        db.session.add(TelegramGroup(telegram_group_id="-100B", title="B", owner_user_id=owner2.id, bot_status="active"))
        db.session.commit()
    a, b = _mk_source(env), _mk_source(env, url="https://x.com/other", gid="-100B")
    _X(monkeypatch, [([_tweet(5)], None)])
    assert _sync(env, a)["ok"]
    assert _sync(env, b)["code"] == "budget"


def test_failed_and_retried_attempts_still_count_against_the_budget(env, monkeypatch):
    sid = _mk_source(env)
    _X(monkeypatch, [_Resp(500)])
    assert not _sync(env, sid)["ok"]
    with env.app.app_context():
        led = KnowledgeSyncLedger.query.one()
        assert led.status == "failed" and led.pages_used == 1
    r = _sync(env, sid)                                # an immediate retry is not a bypass
    assert r["code"] == "cooldown"


def test_429_honours_retry_after_and_extends_the_window(env, monkeypatch):
    sid = _mk_source(env)
    _X(monkeypatch, [_Resp(429, headers={"Retry-After": str(40 * 3600)})])
    r = _sync(env, sid)
    assert not r["ok"]
    with env.app.app_context():
        s = KnowledgeSource.query.get(sid)
        until = kg.cooldown_until(db, kg.cooldown_key(s, kg.owner_user_id(s), "acme"))
        assert until > datetime.utcnow() + timedelta(hours=39)     # beyond the plain 24h window
        assert KnowledgeSyncLedger.query.one().status == "rate_limited"


def test_invalid_credentials_stop_and_pause_the_schedule(env, monkeypatch):
    sid = _mk_source(env, sync_schedule="daily", next_sync_at=datetime.utcnow())
    _X(monkeypatch, [_Resp(401)])
    r = _sync(env, sid, trigger="scheduled")
    assert not r["ok"]
    with env.app.app_context():
        s = KnowledgeSource.query.get(sid)
        assert s.schedule_paused_reason and s.next_sync_at is None
        assert kg.due_sources(db, datetime.utcnow() + timedelta(days=9)) == []


def test_repeated_failures_pause_the_schedule_manual_stays_available(env):
    with env.app.app_context():
        s = KnowledgeSource(telegram_group_id="-100A", source_type="website", url="https://e.x", sync_schedule="daily",
                            next_sync_at=datetime.utcnow())
        db.session.add(s)
        db.session.commit()
        for _ in range(kg.limits()["max_failures"]):
            kg.record_failure(db, s, datetime.utcnow())
        assert s.schedule_paused_reason and s.next_sync_at is None
        kg.record_success(s, datetime.utcnow())
        assert s.schedule_paused_reason is None and s.next_sync_at is not None


def test_free_plan_cannot_sync_even_via_the_scheduler_path(env, monkeypatch):
    sid = _mk_source(env, gid="-100F")
    x = _X(monkeypatch, [])
    r = _sync(env, sid, trigger="scheduled")
    assert r["code"] == "plan" and x.calls == []


def test_x_kill_switch_stops_everything(env, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_X_SYNC_ENABLED", "0")
    x = _X(monkeypatch, [])
    assert _sync(env, _mk_source(env))["code"] == "disabled" and x.calls == []


# ── schedules ─────────────────────────────────────────────────────────────────

def test_existing_sources_default_to_manual_and_are_never_due(env):
    sid = _mk_source(env)
    with env.app.app_context():
        s = KnowledgeSource.query.get(sid)
        assert s.sync_schedule == "manual" and s.enabled is True and s.next_sync_at is None
        assert kg.due_sources(db, datetime.utcnow() + timedelta(days=400)) == []


def test_opting_in_to_a_schedule_does_not_fetch_and_validates_the_choice(env, monkeypatch):
    sid = _mk_source(env, stype="website", url="https://e.x")
    x = _X(monkeypatch, [])
    r = env.client.patch(f"/api/telegram-groups/-100A/knowledge/sources/{sid}", json={"sync_schedule": "every_3_days"}, headers=env.h("pro"))
    assert r.status_code == 200 and r.get_json()["source"]["sync_schedule"] == "every_3_days"
    nxt = datetime.fromisoformat(r.get_json()["source"]["next_sync_at"].rstrip("Z"))
    assert nxt > datetime.utcnow() + timedelta(days=2, hours=23) and x.calls == []
    bad = env.client.patch(f"/api/telegram-groups/-100A/knowledge/sources/{sid}", json={"sync_schedule": "hourly"}, headers=env.h("pro"))
    assert bad.status_code == 400


def test_free_owner_cannot_enable_a_schedule(env):
    sid = _mk_source(env, gid="-100F", stype="website", url="https://e.x")
    r = env.client.patch(f"/api/telegram-groups/-100F/knowledge/sources/{sid}", json={"sync_schedule": "daily"}, headers=env.h("free"))
    assert r.status_code == 403


def test_a_successful_sync_moves_the_next_scheduled_run_forward(env, monkeypatch):
    sid = _mk_source(env, sync_schedule="daily", next_sync_at=datetime.utcnow() - timedelta(minutes=5))
    _X(monkeypatch, [([_tweet(5)], None)])
    assert _sync(env, sid)["ok"]
    with env.app.app_context():
        assert KnowledgeSource.query.get(sid).next_sync_at > datetime.utcnow() + timedelta(hours=23)


# ── versions: replacement, failure preservation, unchanged, rollback, removal ─

class _Page:
    status_code = 200

    def __init__(self, html):
        self.text = html


def _site(monkeypatch, html):
    monkeypatch.setattr(ks, "_safe_get", lambda url, **k: _Page(html))


GOOD_V1 = "<html><title>Rewards</title><body>" + ("<p>The referral reward is 5 points per member who joins. </p>" * 40) + "</body></html>"
GOOD_V2 = "<html><title>Rewards</title><body>" + ("<p>The referral reward is 8 points per member who joins. </p>" * 40) + "</body></html>"


def test_replacing_a_fact_retires_the_old_chunks(env, monkeypatch):
    sid = _mk_source(env, stype="website", url="https://e.x")
    _site(monkeypatch, GOOD_V1)
    assert _sync(env, sid)["ok"]
    with env.app.app_context():
        db.session.execute(db.text("UPDATE knowledge_sources SET last_synced_at = :n"), {"n": datetime.utcnow() - timedelta(minutes=5)})
        db.session.commit()
    _site(monkeypatch, GOOD_V2)
    assert _sync(env, sid)["ok"]
    with env.app.app_context():
        doc = KnowledgeDocument.query.filter_by(source_id=sid).all()
        assert len(doc) == 1                               # replaced, not duplicated
        indexed = " ".join(c["text"] for c in doc[0].chunks)
        assert "8 points" in indexed and "5 points" not in indexed   # old fact no longer retrievable
        vs = KnowledgeSourceVersion.query.filter_by(source_id=sid).order_by(KnowledgeSourceVersion.version_no).all()
        assert [v.status for v in vs] == ["superseded", "active"]
        assert "5 points" in vs[0].text                    # kept for audit / rollback only


def test_unchanged_content_is_not_reindexed(env, monkeypatch):
    sid = _mk_source(env, stype="website", url="https://e.x")
    _site(monkeypatch, GOOD_V1)
    _sync(env, sid)
    n = env.calls["embed"]
    with env.app.app_context():
        db.session.execute(db.text("UPDATE knowledge_sources SET last_synced_at = :n"), {"n": datetime.utcnow() - timedelta(minutes=5)})
        db.session.commit()
    r = _sync(env, sid)
    assert r["ok"] and r["unchanged"] and env.calls["embed"] == n
    with env.app.app_context():
        assert KnowledgeSourceVersion.query.filter_by(source_id=sid).count() == 1


@pytest.mark.parametrize("bad_html", [
    "<html><title>Sign in</title><body>Log in to continue. Sign in with your account.</body></html>",
    "<html><body></body></html>",
])
def test_login_page_or_empty_extract_keeps_the_last_good_version(env, monkeypatch, bad_html):
    sid = _mk_source(env, stype="website", url="https://e.x")
    _site(monkeypatch, GOOD_V1)
    _sync(env, sid)
    with env.app.app_context():
        before = KnowledgeSource.query.get(sid).active_version_id
        db.session.execute(db.text("UPDATE knowledge_sources SET last_synced_at = :n"), {"n": datetime.utcnow() - timedelta(minutes=5)})
        db.session.commit()
    _site(monkeypatch, bad_html)
    r = _sync(env, sid)
    assert not r["ok"]
    with env.app.app_context():
        s = KnowledgeSource.query.get(sid)
        assert s.active_version_id == before and s.last_sync_status == "error"
        assert "5 points" in " ".join(c["text"] for c in KnowledgeDocument.query.filter_by(source_id=sid).one().chunks)


def test_failed_indexing_keeps_the_active_version(env, monkeypatch):
    sid = _mk_source(env, stype="website", url="https://e.x")
    _site(monkeypatch, GOOD_V1)
    _sync(env, sid)
    with env.app.app_context():
        before = KnowledgeSource.query.get(sid).active_version_id
        db.session.execute(db.text("UPDATE knowledge_sources SET last_synced_at = :n"), {"n": datetime.utcnow() - timedelta(minutes=5)})
        db.session.commit()
    _site(monkeypatch, GOOD_V2)
    monkeypatch.setattr(KnowledgeBaseSystem, "_embed", lambda self, texts, **kw: [None] * len(texts))
    assert not _sync(env, sid)["ok"]
    with env.app.app_context():
        assert KnowledgeSource.query.get(sid).active_version_id == before
        assert KnowledgeSourceVersion.query.filter_by(source_id=sid).count() == 1


def test_concurrent_manual_clicks_do_one_fetch(env, monkeypatch):
    sid = _mk_source(env, stype="website", url="https://e.x")
    seen = []
    monkeypatch.setattr(ks, "_safe_get", lambda url, **k: seen.append(url) or _Page(GOOD_V1))
    first, second = _sync(env, sid), _sync(env, sid)
    assert first["ok"] and second["code"] == "busy" and len(seen) == 1


def test_rollback_reindexes_the_chosen_version_only(env, monkeypatch):
    sid = _mk_source(env, stype="website", url="https://e.x")
    _site(monkeypatch, GOOD_V1)
    _sync(env, sid)
    with env.app.app_context():
        db.session.execute(db.text("UPDATE knowledge_sources SET last_synced_at = :n"), {"n": datetime.utcnow() - timedelta(minutes=5)})
        db.session.commit()
    _site(monkeypatch, GOOD_V2)
    _sync(env, sid)
    with env.app.app_context():
        v1 = KnowledgeSourceVersion.query.filter_by(source_id=sid, version_no=1).one().id
    r = env.client.post(f"/api/telegram-groups/-100A/knowledge/sources/{sid}/versions/{v1}/activate", headers=env.h("pro"))
    assert r.status_code == 200
    with env.app.app_context():
        indexed = " ".join(c["text"] for c in KnowledgeDocument.query.filter_by(source_id=sid).one().chunks)
        assert "5 points" in indexed and "8 points" not in indexed
        assert [v.status for v in KnowledgeSourceVersion.query.filter_by(source_id=sid).order_by(KnowledgeSourceVersion.version_no)] == ["active", "superseded"]


def test_disabling_blocks_sync_and_removing_deletes_everything(env, monkeypatch):
    sid = _mk_source(env, stype="website", url="https://e.x")
    _site(monkeypatch, GOOD_V1)
    _sync(env, sid)
    assert env.client.patch(f"/api/telegram-groups/-100A/knowledge/sources/{sid}", json={"enabled": False}, headers=env.h("pro")).status_code == 200
    assert _sync(env, sid)["code"] == "disabled"
    assert env.client.delete(f"/api/telegram-groups/-100A/knowledge/sources/{sid}", headers=env.h("pro")).status_code == 200
    with env.app.app_context():
        assert KnowledgeSource.query.count() == 0 and KnowledgeDocument.query.count() == 0
        assert KnowledgeSourceVersion.query.count() == 0


# ── preview ───────────────────────────────────────────────────────────────────

def test_preview_shows_stored_text_and_makes_no_provider_or_ai_call(env, monkeypatch):
    sid = _mk_source(env, stype="website", url="https://e.x")
    _site(monkeypatch, GOOD_V1)
    _sync(env, sid)
    embeds = env.calls["embed"]

    def boom(*a, **k):
        raise AssertionError("preview must not contact anything")
    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(ks, "_safe_get", boom)
    r = env.client.get(f"/api/telegram-groups/-100A/knowledge/sources/{sid}/preview?q=reward", headers=env.h("pro"))
    j = r.get_json()
    assert r.status_code == 200 and j["available"] and "referral reward is 5 points" in j["text"]
    assert j["chunk_count"] >= 1 and j["char_count"] == len(j["text"]) and j["match_count"] > 0
    assert j["dates"]["published"] is None             # the site gave no date: unknown, not the fetch time
    assert j["dates"]["last_success"] and j["dates"]["indexed"]
    assert env.calls["embed"] == embeds


def test_preview_states_unavailable_failed_and_stale(env, monkeypatch):
    sid = _mk_source(env, stype="website", url="https://e.x")
    j = env.client.get(f"/api/telegram-groups/-100A/knowledge/sources/{sid}/preview", headers=env.h("pro")).get_json()
    assert j["status"] == "unavailable" and j["text"] is None
    _site(monkeypatch, GOOD_V1)
    _sync(env, sid)
    with env.app.app_context():
        s = KnowledgeSource.query.get(sid)
        s.last_sync_status, s.last_sync_error = "error", "boom"
        db.session.commit()
    j = env.client.get(f"/api/telegram-groups/-100A/knowledge/sources/{sid}/preview", headers=env.h("pro")).get_json()
    assert j["status"] == "stale" and j["available"] and j["last_error"] == "boom"


def test_preview_respects_group_permissions(env):
    sid = _mk_source(env, stype="website", url="https://e.x")
    assert env.client.get(f"/api/telegram-groups/-100A/knowledge/sources/{sid}/preview", headers=env.h("stranger")).status_code == 404
    assert env.client.get(f"/api/telegram-groups/-100F/knowledge/sources/{sid}/preview", headers=env.h("free")).status_code == 404


def test_legacy_source_without_a_version_is_reconstructed_from_chunks(env):
    sid = _mk_source(env, stype="website", url="https://e.x")
    words = [f"w{i}" for i in range(500)]
    c1, c2 = " ".join(words[:400]), " ".join(words[350:])
    with env.app.app_context():
        db.session.add(KnowledgeDocument(telegram_group_id="-100A", filename="x", file_type="website", content_text="x",
                                         chunks=[{"text": c1, "embedding": [1]}, {"text": c2, "embedding": [1]}], source_id=sid))
        db.session.commit()
    j = env.client.get(f"/api/telegram-groups/-100A/knowledge/sources/{sid}/preview", headers=env.h("pro")).get_json()
    assert j["available"] and j["reconstructed_from_chunks"] and j["text"].split() == words


# ── provenance + conflict ─────────────────────────────────────────────────────

def test_labels_never_present_fetch_time_as_publication_time():
    doc = NS(filename="Feed", created_at=datetime(2026, 1, 1))
    src = NS(source_type="twitter", published_at=None, last_success_at=datetime(2026, 10, 12), last_synced_at=None)
    label = source_label(doc, src)
    assert "publication date unknown" in label and "fetched 2026-10-12" in label
    src.published_at = datetime(2026, 9, 1)
    assert "newest content published 2026-09-01" in source_label(doc, src)
    up = source_label(doc, None)
    assert "owner-approved uploaded document" in up and "publication date unknown" in up and "uploaded 2026-01-01" in up


def test_prompt_does_not_rank_by_fetch_time_and_has_a_conflict_verdict():
    from backend.bot_features.ai_personality import build_system_prompt
    p = build_system_prompt()
    assert "never prefer a source just because it was fetched or uploaded later" in p
    assert "exactly CONFLICT" in p and "not overridden by an external feed" in p


def test_conflict_verdict_takes_the_no_answer_path():
    assert _is_conflict("CONFLICT") and _is_conflict(" `conflict`. ")
    assert _is_no_answer("CONFLICT") and not _is_conflict("There is a conflict of interest policy.")


def test_disabled_source_is_excluded_from_answers(env, monkeypatch):
    """answer_question must skip a disabled source's chunks entirely."""
    import asyncio
    sid = _mk_source(env, stype="website", url="https://e.x")
    _site(monkeypatch, GOOD_V1)
    _sync(env, sid)
    seen = {}

    async def fake_generate(self, question, context, *a, **k):
        seen["context"] = context
        return "ok"
    monkeypatch.setattr(KnowledgeBaseSystem, "_generate_answer", fake_generate)
    monkeypatch.setattr(KnowledgeBaseSystem, "_load_group_api_key", lambda self, *a, **k: None)

    class _Emb:
        data = [NS(embedding=[0.1, 0.2, 0.3])]
    fake_client = NS(embeddings=NS(create=lambda **k: _Emb))
    monkeypatch.setattr(KnowledgeBaseSystem, "_get_openai_client", lambda self, **k: fake_client)
    monkeypatch.setattr("backend.config.Config.OPENAI_API_KEY", "x", raising=False)

    ans, _ = asyncio.run(env.kb.answer_question("what is the referral reward?", None, telegram_group_id="-100A"))
    assert ans == "ok" and "[Source: src | external source: website | publication date unknown" in seen["context"]
    with env.app.app_context():
        KnowledgeSource.query.get(sid).enabled = False
        db.session.commit()
    seen.clear()
    ans, _ = asyncio.run(env.kb.answer_question("what is the referral reward?", None, telegram_group_id="-100A"))
    assert ans is None and "context" not in seen
