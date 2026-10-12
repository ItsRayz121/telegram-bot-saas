"""Wiring tests: the custom-bot route lineage, the scheduler job and isolation.

Run from the repo root:  python -m pytest backend/tests/test_knowledge_sources_wiring.py
Every provider call is mocked.
"""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("DISABLE_BACKGROUND_THREADS", "1")

import pytest
import requests
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from backend import knowledge_sync as kg
from backend.bot_features import knowledge_sources as ks
from backend.bot_features.knowledge_base import KnowledgeBaseSystem
from backend.models import (
    db, User, Bot, Group, KnowledgeSource, KnowledgeDocument, KnowledgeSourceVersion, KnowledgeSyncLedger,
)
from backend.routes.knowledge import knowledge_bp
import backend.assistant.hub_models  # noqa: F401


class _Page:
    status_code = 200

    def __init__(self, html):
        self.text = html


HTML = "<html><title>Rewards</title><body>" + ("<p>The referral reward is 5 points per member who joins. </p>" * 40) + "</body></html>"


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("GROUP_TEAM_ACCESS_ENABLED", raising=False)
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY=os.environ["JWT_SECRET_KEY"],
                      JWT_TOKEN_LOCATION=["headers"], TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(knowledge_bp)
    with app.app_context():
        db.create_all()
        pro = User(email="pro@x.io", full_name="Pro", auth_provider="email", subscription_tier="pro")
        free = User(email="free@x.io", full_name="Free", auth_provider="email")
        other = User(email="o@x.io", full_name="O", auth_provider="email", subscription_tier="pro")
        db.session.add_all([pro, free, other])
        db.session.flush()
        bots = {}
        for key, u in (("pro", pro), ("free", free), ("other", other)):
            b = Bot(user_id=u.id, bot_token="x", bot_username=f"{key}_bot")
            db.session.add(b)
            db.session.flush()
            g = Group(bot_id=b.id, telegram_group_id=f"-100{key}", group_name=key)
            db.session.add(g)
            db.session.flush()
            bots[key] = (b.id, g.id)
        db.session.commit()
        ids = dict(pro=pro.id, free=free.id, other=other.id)
        tokens = {k: create_access_token(identity=str(v)) for k, v in ids.items()}
    monkeypatch.setattr(KnowledgeBaseSystem, "_embed", lambda self, texts, **kw: [[0.1, 0.2] for _ in texts])
    monkeypatch.setattr(ks, "_safe_get", lambda url, **k: _Page(HTML))
    return NS(app=app, client=app.test_client(), bots=bots, h=lambda who: {"Authorization": f"Bearer {tokens[who]}"},
              kb=KnowledgeBaseSystem(app))


def _url(env, who, tail=""):
    b, g = env.bots[who]
    return f"/api/bots/{b}/groups/{g}/knowledge/sources{tail}"


def _make(env, who="pro"):
    r = env.client.post(_url(env, who), json={"url": "https://e.example/rewards"}, headers=env.h(who))
    return r


def test_custom_lineage_full_flow_sync_preview_schedule_versions_delete(env):
    r = _make(env)
    assert r.status_code == 201
    src = r.get_json()["source"]
    assert src["sync_schedule"] == "manual" and src["enabled"] is True        # new sources default to Manual
    sid = src["id"]

    s = env.client.post(_url(env, "pro", f"/{sid}/sync"), headers=env.h("pro"))
    assert s.status_code == 200 and s.get_json()["source"]["last_sync_status"] == "success"

    p = env.client.get(_url(env, "pro", f"/{sid}/preview?q=referral"), headers=env.h("pro")).get_json()
    assert p["available"] and "referral reward" in p["text"] and p["match_count"] > 0 and p["dates"]["published"] is None

    u = env.client.patch(_url(env, "pro", f"/{sid}"), json={"sync_schedule": "weekly"}, headers=env.h("pro"))
    assert u.status_code == 200 and u.get_json()["source"]["next_sync_at"]

    v = env.client.get(_url(env, "pro", f"/{sid}/versions"), headers=env.h("pro")).get_json()
    assert len(v["versions"]) == 1 and v["versions"][0]["status"] == "active"

    assert env.client.delete(_url(env, "pro", f"/{sid}"), headers=env.h("pro")).status_code == 200
    with env.app.app_context():
        assert KnowledgeSource.query.count() == 0 and KnowledgeSourceVersion.query.count() == 0
        assert KnowledgeDocument.query.count() == 0


def test_custom_lineage_group_isolation(env):
    sid = _make(env).get_json()["source"]["id"]
    # another owner cannot see, preview, change, sync or delete it - and a free user cannot sync their own
    b, g = env.bots["pro"]
    base = f"/api/bots/{b}/groups/{g}/knowledge/sources/{sid}"
    for method, tail in (("get", "/preview"), ("patch", ""), ("post", "/sync"), ("get", "/versions"), ("delete", "")):
        r = getattr(env.client, method)(base + tail, headers=env.h("other"), json={} if method in ("patch", "post") else None)
        assert r.status_code in (403, 404), (method, tail, r.status_code)


def test_custom_lineage_pro_is_enforced_server_side(env):
    r = _make(env, "free")
    assert r.status_code == 403                                   # cannot even add a source on Free
    # a free owner who somehow has a row still cannot sync or schedule it
    b, g = env.bots["free"]
    with env.app.app_context():
        s = KnowledgeSource(group_id=g, source_type="website", url="https://e.example/x")
        db.session.add(s)
        db.session.commit()
        sid = s.id
    assert env.client.post(_url(env, "free", f"/{sid}/sync"), headers=env.h("free")).status_code == 403
    assert env.client.patch(_url(env, "free", f"/{sid}"), json={"sync_schedule": "daily"}, headers=env.h("free")).status_code == 403
    assert env.client.post(_url(env, "free", f"/{sid}/versions/1/activate"), headers=env.h("free")).status_code == 403


def test_x_cooldown_returns_429_with_next_available_and_keeps_stored_text(env, monkeypatch):
    monkeypatch.setattr("backend.secret_vault.get_secret", lambda n, d=None: "k" if n == "TWITTERAPI_IO_KEY" else d)

    class _R:
        status_code = 200
        headers = {}

        def json(self):
            return {"data": {"tweets": [{"id": "5", "text": "hello", "createdAt": "2026-10-01T10:00:00Z"}]}, "has_next_page": False}
    monkeypatch.setattr(requests, "get", lambda *a, **k: _R())
    b, g = env.bots["pro"]
    sid = env.client.post(_url(env, "pro"), json={"url": "https://x.com/acme"}, headers=env.h("pro")).get_json()["source"]["id"]
    assert env.client.post(_url(env, "pro", f"/{sid}/sync"), headers=env.h("pro")).status_code == 200
    r = env.client.post(_url(env, "pro", f"/{sid}/sync"), headers=env.h("pro"))
    body = r.get_json()
    assert r.status_code == 429 and body["next_available_at"] and body["serving_stored_version"] is True
    p = env.client.get(_url(env, "pro", f"/{sid}/preview"), headers=env.h("pro")).get_json()
    assert p["available"] and "hello" in p["text"] and p["dates"]["next_available"]
    assert p["dates"]["published"].startswith("2026-10-01")       # the post's own date, not the fetch time


# ── scheduler job (backend.app._run_knowledge_source_sync) ────────────────────

@pytest.fixture()
def sched(monkeypatch):
    import backend.app as appmod
    return appmod


def test_scheduler_runs_only_due_opt_in_sources_and_moves_them_forward(env, sched, monkeypatch):
    b, g = env.bots["pro"]
    with env.app.app_context():
        due = KnowledgeSource(group_id=g, source_type="website", url="https://e.example/a", sync_schedule="daily",
                              next_sync_at=datetime.utcnow() - timedelta(minutes=1))
        manual = KnowledgeSource(group_id=g, source_type="website", url="https://e.example/b")
        future = KnowledgeSource(group_id=g, source_type="website", url="https://e.example/c", sync_schedule="daily",
                                 next_sync_at=datetime.utcnow() + timedelta(hours=5))
        paused = KnowledgeSource(group_id=g, source_type="website", url="https://e.example/d", sync_schedule="daily",
                                 next_sync_at=datetime.utcnow() - timedelta(minutes=1), schedule_paused_reason="x")
        disabled = KnowledgeSource(group_id=g, source_type="website", url="https://e.example/e", sync_schedule="daily",
                                   next_sync_at=datetime.utcnow() - timedelta(minutes=1), enabled=False)
        db.session.add_all([due, manual, future, paused, disabled])
        db.session.commit()
        ids = dict(due=due.id, manual=manual.id, future=future.id)
    called = []
    orig = KnowledgeBaseSystem.sync_external_source

    def spy(self, source, trigger="manual"):
        called.append((source.url, trigger))
        return orig(self, source, trigger=trigger)
    monkeypatch.setattr(KnowledgeBaseSystem, "sync_external_source", spy)
    sched._run_knowledge_source_sync(env.app)
    assert called == [("https://e.example/a", "scheduled")]
    with env.app.app_context():
        s = KnowledgeSource.query.get(ids["due"])
        assert s.last_sync_status == "success" and s.next_sync_at > datetime.utcnow() + timedelta(hours=23)
        assert KnowledgeSource.query.get(ids["manual"]).last_synced_at is None


def test_scheduler_kill_switch_and_plan_lapse(env, sched, monkeypatch):
    b, g = env.bots["free"]
    with env.app.app_context():
        s = KnowledgeSource(group_id=g, source_type="website", url="https://e.example/a", sync_schedule="daily",
                            next_sync_at=datetime.utcnow() - timedelta(minutes=1))
        db.session.add(s)
        db.session.commit()
        sid = s.id
    monkeypatch.setenv("KNOWLEDGE_SCHEDULED_SYNC_ENABLED", "0")
    sched._run_knowledge_source_sync(env.app)
    with env.app.app_context():
        assert KnowledgeSource.query.get(sid).last_synced_at is None          # kill switch: nothing ran
    monkeypatch.delenv("KNOWLEDGE_SCHEDULED_SYNC_ENABLED")
    sched._run_knowledge_source_sync(env.app)                                  # plan lapsed: pause, do not fetch
    with env.app.app_context():
        row = KnowledgeSource.query.get(sid)
        assert row.schedule_paused_reason and row.next_sync_at is None and row.last_success_at is None
        assert KnowledgeSyncLedger.query.count() == 0


def test_scheduler_prunes_old_ledger_rows(env, sched):
    with env.app.app_context():
        db.session.add_all([
            KnowledgeSyncLedger(source_id=1, credential_key="c", created_at=datetime.utcnow() - timedelta(days=60)),
            KnowledgeSyncLedger(source_id=1, credential_key="c", created_at=datetime.utcnow() - timedelta(days=1)),
        ])
        db.session.commit()
    sched._run_knowledge_source_sync(env.app)
    with env.app.app_context():
        assert KnowledgeSyncLedger.query.count() == 1
