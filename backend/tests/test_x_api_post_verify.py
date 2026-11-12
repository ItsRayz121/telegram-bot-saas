"""verify_post: the X-API content-submission check only ever says verified on a clear match."""
from unittest.mock import patch, MagicMock
from datetime import datetime

from backend import twitter_verify as tv

URL = "https://x.com/alice/status/1234567890123"


def _resp(tweets, code=200):
    r = MagicMock(status_code=code)
    r.json.return_value = {"tweets": tweets}
    return r


def _t(author="alice", created="Tue Dec 10 07:00:30 +0000 2024"):
    return {"author": {"userName": author}, "createdAt": created}


def _run(resp, handle="@Alice", since=None):
    with patch.object(tv, "_key", return_value="k"), patch.object(tv, "_get", return_value=resp):
        return tv.verify_post(URL, handle, since=since)[0]


def test_match_verified():
    assert _run(_resp([_t()])) == "verified"


def test_other_author_failed():
    assert _run(_resp([_t("bob")])) == "failed"


def test_older_than_campaign_failed():
    assert _run(_resp([_t()]), since=datetime(2025, 1, 1)) == "failed"


def test_newer_than_campaign_verified():
    assert _run(_resp([_t()]), since=datetime(2024, 12, 1)) == "verified"


def test_errors_are_unknown_never_failed():
    assert _run(_resp([], 200)) == "unknown"
    assert _run(_resp([_t()], 500)) == "unknown"
    assert _run(_resp([_t(created="garbage")]), since=datetime(2024, 1, 1)) == "unknown"


# ── end-to-end through create_submission (real sqlite) ────────────────────────
import os
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")
import pytest
from flask import Flask
from backend.models import db, User, EngagementCampaign, EngagementCustomField
import backend.assistant.hub_models  # noqa: F401
from backend import engagement as eng


@pytest.fixture()
def app_ctx():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()


def _camp(with_handle_field=True, one_per_user=False, tier="pro"):
    u = User(email="o@x.io", full_name="O", auth_provider="email", subscription_tier=tier)
    db.session.add(u); db.session.flush()
    c = EngagementCampaign(telegram_group_id="-100A", owner_user_id=u.id, type="content_submission",
                           title="C", status="active", verification_mode="x_api", platform="x",
                           one_per_user=one_per_user, settings={"max_submissions": 5} if not one_per_user else {})
    db.session.add(c); db.session.flush()
    db.session.add(EngagementCustomField(campaign_id=c.id, key="link", label="Post link",
                                         field_type="url", required=True, order=0))
    if with_handle_field:
        db.session.add(EngagementCustomField(campaign_id=c.id, key="h", label="X username",
                                             field_type="username", required=False, order=1))
    db.session.commit()
    return c


def _submit(c, uid, answers, monkeypatch, verdict="verified"):
    monkeypatch.setattr(tv, "enabled", lambda owner=None: True)
    calls = []
    monkeypatch.setattr(tv, "verify_post", lambda u, h, **kw: (calls.append((u, h)) or (verdict, None)))
    sub, err = eng.create_submission(c, telegram_user_id=uid, answers=answers)
    return sub, err, calls


def test_e2e_verified_with_own_handle(app_ctx, monkeypatch):
    c = _camp()
    sub, err, calls = _submit(c, 1, {"link": URL, "h": "@xapi_z1"}, monkeypatch)
    assert err is None and sub.status == "verified" and calls[0][1] == "xapi_z1"
    assert eng.saved_x_handle(1) == "xapi_z1"


def test_e2e_no_handle_never_trusts_post_author(app_ctx, monkeypatch):
    c = _camp(with_handle_field=False)
    sub, err, calls = _submit(c, 2, {"link": URL}, monkeypatch)
    assert sub.status == "pending" and calls == []      # would otherwise accept anyone's post


def test_e2e_same_post_cannot_be_resent(app_ctx, monkeypatch):
    c = _camp()
    s1, _, _ = _submit(c, 3, {"link": URL, "h": "@xapi_z3"}, monkeypatch)
    s2, _, calls = _submit(c, 3, {"link": URL, "h": "@xapi_z3"}, monkeypatch)
    assert s1.status == "verified" and s2.status == "pending" and calls == []


def test_e2e_failed_or_unknown_stays_pending_and_kill_switch(app_ctx, monkeypatch):
    c = _camp()
    for v in ("failed", "unknown"):
        sub, _, _ = _submit(c, 10, {"link": "https://x.com/alice/status/99999999%d" % len(v), "h": "@xapi_z10"}, monkeypatch, v)
        assert sub.status == "pending"
    monkeypatch.setenv("X_API_VERIFY_ENABLED", "0")
    sub, _, calls = _submit(c, 11, {"link": "https://x.com/alice/status/5555555555", "h": "@xapi_z11"}, monkeypatch)
    assert sub.status == "pending" and calls == []


def test_e2e_saved_handle_wins_over_typed(app_ctx, monkeypatch):
    c = _camp()
    eng.set_social_handle(4, "xapi_real", "x")
    sub, _, calls = _submit(c, 4, {"link": URL, "h": "@xapi_victim"}, monkeypatch)
    assert calls[0][1] == "xapi_real"


def test_e2e_bad_link_is_rejected_up_front(app_ctx, monkeypatch):
    c = _camp()
    sub, err, _ = _submit(c, 5, {"link": "not a link", "h": "@xapi_z5"}, monkeypatch)
    assert sub is None and err


def test_e2e_free_owner_never_spends_x_credits(app_ctx, monkeypatch):
    c = _camp(tier="free")
    sub, _, calls = _submit(c, 7, {"link": URL, "h": "@xapi_z7"}, monkeypatch)
    assert sub.status == "pending" and calls == []


# ── deleted-after-verification flag ────────────────────────────────────────────
from datetime import timedelta
from backend.models import EngagementSubmission


def _aged_verified(c, uid, hours=24, url=URL):
    from datetime import datetime
    s = EngagementSubmission(campaign_id=c.id, telegram_user_id=str(uid), scope="official", status="verified",
                             payload={"link": url}, flagged=False,
                             created_at=datetime.utcnow() - timedelta(hours=hours, minutes=2))
    db.session.add(s); db.session.commit()
    return s


def test_deleted_post_is_flagged_not_unverified(app_ctx, monkeypatch):
    c = _camp()
    s = _aged_verified(c, 21)
    monkeypatch.setattr(tv, "post_exists", lambda u, **kw: False)
    assert eng.flag_deleted_x_posts() == 1
    db.session.refresh(s)
    assert s.flagged and "deleted" in s.flag_reason and s.status == "verified"   # XP untouched


def test_still_there_or_unknown_is_not_flagged(app_ctx, monkeypatch):
    c = _camp()
    s = _aged_verified(c, 22)
    for ans in (True, None):
        monkeypatch.setattr(tv, "post_exists", lambda u, a=ans, **kw: a)
        assert eng.flag_deleted_x_posts() == 0
    db.session.refresh(s)
    assert not s.flagged


def test_deleted_check_ignores_other_modes_and_kill_switch(app_ctx, monkeypatch):
    c = _camp()
    c.verification_mode = "link"; db.session.commit()
    s = _aged_verified(c, 23)
    monkeypatch.setattr(tv, "post_exists", lambda u, **kw: False)
    assert eng.flag_deleted_x_posts() == 0
    c.verification_mode = "x_api"; db.session.commit()
    monkeypatch.setenv("X_API_VERIFY_ENABLED", "0")
    assert eng.flag_deleted_x_posts() == 0


def test_post_exists_only_false_on_clear_empty_answer():
    with patch.object(tv, "_key", return_value="k"):
        for resp, want in ((_resp([_t()]), True), (_resp([]), False), (_resp([], 500), None)):
            with patch.object(tv, "_get", return_value=resp):
                assert tv.post_exists(URL) is want
