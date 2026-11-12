"""Per-task X auto-verify settings and the one-handle-one-account rule.

Run from the repo root:  python -m pytest backend/tests/test_task_x_autoverify.py
"""
import os
from datetime import datetime, timedelta

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask

from backend.models import db, User, EngagementCampaign, EngagementTask, EngagementCustomField
import backend.assistant.hub_models  # noqa: F401
from backend import engagement as eng


@pytest.fixture()
def ctx():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True, SECRET_KEY="x",
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}},
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def test_clean_task_settings_keeps_only_x_capable_options():
    clean = eng._clean_task_settings
    out = clean({"auto_verify_x": True, "raid_goals": {"retweets": "5", "likes": 0, "bogus": 9}}, "raid", "x")
    assert out == {"auto_verify_x": True, "raid_goals": {"retweets": 5}}
    # not an X task -> the X options are dropped, other keys survive
    out = clean({"auto_verify_x": True, "raid_goals": {"retweets": 5}, "note": "hi"}, "proof_collection", None)
    assert out == {"note": "hi"}
    # X social task keeps them; a non-X social task does not
    assert clean({"auto_verify_x": True}, "social_task", "x")["auto_verify_x"] is True
    assert "auto_verify_x" not in clean({"auto_verify_x": True}, "social_task", "discord")
    # garbage never raises
    assert clean(None, "raid", "x") == {}
    assert clean({"raid_goals": {"retweets": "abc"}}, "raid", "x") == {}


def test_tasks_want_autoverify():
    assert eng._tasks_want_autoverify([{"settings": {"auto_verify_x": True}}])
    assert not eng._tasks_want_autoverify([{"settings": {}}, {"title": "x"}])
    assert not eng._tasks_want_autoverify(None)


def _campaign(owner_id, task_settings, ttype="raid", platform="x"):
    c = EngagementCampaign(telegram_group_id="-100A", owner_user_id=owner_id, type="social_task",
                           title="Multi", status="active", settings={})
    db.session.add(c)
    db.session.flush()
    t = EngagementTask(campaign_id=c.id, order=0, title="Raid it", type=ttype, platform=platform,
                       task_url="https://x.com/proj/status/1234567890123", verification_mode="manual",
                       settings=task_settings)
    db.session.add(t)
    db.session.flush()
    db.session.add(EngagementCustomField(task_id=t.id, key="x", label="Your X @username",
                                         field_type="username", required=False, order=0))
    db.session.commit()
    return c, t


def _submit(c, t, uid, answers, monkeypatch, result):
    from backend import twitter_verify
    monkeypatch.setattr(twitter_verify, "enabled", lambda owner=None: True)
    calls = []

    def fake(shim, handle, **kw):
        calls.append((shim, handle))
        return {"overall": result}
    monkeypatch.setattr(twitter_verify, "verify_raid", fake)
    sub, err = eng.create_submission(c, telegram_user_id=uid, answers=answers, task_id=t.id)
    return sub, err, calls


def test_task_auto_verify_upgrades_on_positive_match(ctx, monkeypatch):
    u = User(email="o@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    sub, err, calls = _submit(c, t, 111, {"x": "@alice"}, monkeypatch, "verified")
    assert err is None and sub.status == "verified"
    shim, handle = calls[0]
    assert handle == "alice" and shim.settings["raid_goals"] == {"retweets": 3}
    assert shim.task_url.endswith("1234567890123")
    # the typed handle was remembered for next time
    assert eng.get_social_handle(111, "x") == "alice"


def test_task_auto_verify_never_rejects_and_respects_off_and_kill_switch(ctx, monkeypatch):
    u = User(email="o2@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    sub, _, _ = _submit(c, t, 112, {"x": "@bob"}, monkeypatch, "pending")
    assert sub.status == "pending"                      # uncertain -> manual review
    monkeypatch.setenv("TASK_X_AUTOVERIFY_ENABLED", "0")
    sub, _, calls = _submit(c, t, 113, {"x": "@cara"}, monkeypatch, "verified")
    assert sub.status == "pending" and calls == []      # kill switch -> no API call
    monkeypatch.delenv("TASK_X_AUTOVERIFY_ENABLED")
    c2, t2 = _campaign(u.id, {"raid_goals": {"retweets": 3}})   # switch off
    sub, _, calls = _submit(c2, t2, 114, {"x": "@dan"}, monkeypatch, "verified")
    assert sub.status == "pending" and calls == []


def test_blank_field_uses_saved_handle(ctx, monkeypatch):
    u = User(email="o3@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    eng.set_social_handle(120, "@saved_one", "x")
    sub, _, calls = _submit(c, t, 120, {}, monkeypatch, "verified")
    assert sub.status == "verified" and calls[0][1] == "saved_one"


def test_one_handle_one_account(ctx, monkeypatch):
    assert eng.set_social_handle(201, "@Farmer", "x") == "Farmer"
    assert eng.set_social_handle(202, "@farmer", "x") == eng.HANDLE_TAKEN     # case-insensitive
    assert eng.set_social_handle(201, "@Farmer2", "x") == "Farmer2"           # own change is fine
    assert eng.get_social_handle(202, "x") is None
    monkeypatch.setenv("SOCIAL_HANDLE_UNIQUE", "0")
    assert eng.set_social_handle(202, "@Farmer2", "x") == "Farmer2"           # kill switch


def test_typed_handle_owned_by_another_account_is_not_auto_verified(ctx, monkeypatch):
    u = User(email="o4@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    eng.set_social_handle(300, "@owner_of_it", "x")
    sub, _, calls = _submit(c, t, 301, {"x": "@owner_of_it"}, monkeypatch, "verified")
    assert sub.status == "pending" and calls == []


def test_dm_username_prompt_offers_the_saved_handle(ctx):
    from types import SimpleNamespace
    from backend import engagement_bot as eb
    eng.set_social_handle(777, "@saved_me", "x")
    msg = SimpleNamespace(chat=SimpleNamespace(id=777))
    assert eb._saved_handle_for(msg, {"field_type": "username"}) == "saved_me"
    assert eb._saved_handle_for(msg, {"field_type": "wallet"}) is None
    assert eb._saved_handle_for(SimpleNamespace(chat=SimpleNamespace(id=1)), {"field_type": "username"}) is None


def _pending_sub(c, t, uid, age_s, handle="@late"):
    from datetime import datetime, timedelta
    from backend.models import EngagementSubmission
    sub = EngagementSubmission(campaign_id=c.id, task_id=t.id, telegram_user_id=str(uid),
                               telegram_username="u", scope="custom", status="pending",
                               payload={"x": handle} if handle else {},
                               created_at=datetime.utcnow() - timedelta(seconds=age_s))
    db.session.add(sub)
    db.session.commit()
    return sub


def _patch_x(monkeypatch, result):
    from backend import twitter_verify
    calls = []
    monkeypatch.setattr(twitter_verify, "enabled", lambda owner=None: True)
    monkeypatch.setattr(twitter_verify, "verify_raid",
                        lambda shim, handle, **kw: calls.append(handle) or {"overall": result})
    return calls


def test_recheck_upgrades_a_pending_submission_once_x_shows_the_action(ctx, monkeypatch):
    u = User(email="r1@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    sub = _pending_sub(c, t, 401, age_s=240)
    calls = _patch_x(monkeypatch, "verified")
    assert eng.recheck_pending_x_tasks() == 1
    db.session.refresh(sub)
    assert sub.status == "verified" and sub.reviewed_by == "auto-x" and calls == ["@late"]
    assert eng.recheck_pending_x_tasks() == 0          # already verified: not checked again


def test_recheck_never_rejects_and_respects_window_flags_and_kill_switch(ctx, monkeypatch):
    u = User(email="r2@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    too_new = _pending_sub(c, t, 410, age_s=10)
    too_old = _pending_sub(c, t, 411, age_s=3 * 3600)
    flagged = _pending_sub(c, t, 412, age_s=240)
    flagged.flagged = True
    unsure = _pending_sub(c, t, 413, age_s=240)
    db.session.commit()
    calls = _patch_x(monkeypatch, "pending")
    assert eng.recheck_pending_x_tasks() == 0
    for s_ in (too_new, too_old, flagged, unsure):
        db.session.refresh(s_)
        assert s_.status == "pending"                   # never rejected, never upgraded
    assert calls == ["@late"]                           # only the eligible one was checked
    monkeypatch.setenv("TASK_X_AUTOVERIFY_ENABLED", "0")
    calls.clear()
    assert eng.recheck_pending_x_tasks() == 0 and calls == []


def test_follow_target_is_read_from_a_profile_link():
    from backend.twitter_verify import extract_author_handle as who
    assert who("https://x.com/ElyonChain") == "ElyonChain"
    assert who("https://twitter.com/@Elyon_Chain/") == "Elyon_Chain"
    assert who("https://x.com/ElyonChain?s=20") == "ElyonChain"
    assert who("https://x.com/proj/status/1234567890123") == "proj"      # unchanged
    for bad in ("https://x.com/home", "https://x.com/i/status/1", "https://x.com/search?q=1", "", None,
                "https://example.com/foo"):
        assert who(bad) is None


def test_task_options_that_cost_money_are_paid_only():
    msg = eng._task_pro_message
    assert msg([{"verification_mode": "auto", "platform": "telegram"}]) is None        # free: Telegram join check
    assert msg([{"verification_mode": "manual", "platform": "x"}]) is None
    assert "X verification" in msg([{"settings": {"auto_verify_x": True}}])
    assert "Link-validity" in msg([{"verification_mode": "link"}])
    assert "this platform" in msg([{"verification_mode": "auto", "platform": "x"}])
    assert msg(None) is None and msg([None, "x"]) is None


def test_free_owner_cannot_save_paid_task_options(ctx):
    free = User(email="free@x.io", full_name="F", auth_provider="email", subscription_tier="free")
    db.session.add(free); db.session.flush()
    c, t = _campaign(free.id, {})
    for bad in ({"verification_mode": "auto", "platform": "x"}, {"verification_mode": "link"}):
        with pytest.raises(eng.EngagementError) as e:
            eng.update_campaign(c, {"tasks": [dict(title="T", type="social_task", **bad)]}, user=free)
        assert e.value.status == 403 and e.value.code == "FEATURE_REQUIRES_PRO"
    # the free Telegram join check is allowed
    eng.update_campaign(c, {"tasks": [dict(title="Join", type="social_task", platform="telegram",
                                           verification_mode="auto")]}, user=free)


def test_free_plan_can_run_up_to_three_tasks_pro_more(ctx):
    free = User(email="f3@x.io", full_name="F", auth_provider="email", subscription_tier="free")
    db.session.add(free); db.session.flush()
    c, _ = _campaign(free.id, {})
    mk = lambda n: [dict(title=f"T{i}", type="social_task", verification_mode="manual") for i in range(n)]
    eng.update_campaign(c, {"tasks": mk(3)}, user=free)                          # 3 tasks: allowed on Free
    assert c.tasks.count() == 3
    with pytest.raises(eng.EngagementError) as e:
        eng.update_campaign(c, {"tasks": mk(4)}, user=free)
    assert e.value.status == 403 and e.value.code == "FEATURE_REQUIRES_PRO" and "up to 3 tasks" in e.value.message
    pro = User(email="p3@x.io", full_name="P", auth_provider="email", subscription_tier="pro")
    db.session.add(pro); db.session.flush()
    eng.update_campaign(c, {"tasks": mk(5)}, user=pro)
    assert c.tasks.count() == 5
    # creating directly with too many tasks on Free is refused by the gating helper
    with pytest.raises(eng.EngagementError):
        eng._check_create_gating(free, scope="official", group_id=None, telegram_group_id="-100A", status="draft",
                                 verification_mode="manual", platform=None, field_count=0, task_count=4)
    eng._check_create_gating(free, scope="official", group_id=None, telegram_group_id="-100A", status="draft",
                             verification_mode="manual", platform=None, field_count=0, task_count=3)


def test_recheck_still_runs_after_the_campaign_ended_but_not_for_drafts_or_archived(ctx, monkeypatch):
    u = User(email="late@x.io", full_name="O", auth_provider="email")
    db.session.add(u); db.session.flush()
    c, t = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    late = _pending_sub(c, t, 601, age_s=240)                          # submitted while it was open
    c.status, c.ends_at = "closed", datetime.utcnow() - timedelta(minutes=2)
    db.session.commit()
    _patch_x(monkeypatch, "verified")
    assert eng.recheck_pending_x_tasks() == 1                           # ended campaign: our limit, not theirs
    db.session.refresh(late)
    assert late.status == "verified"
    c2, t2 = _campaign(u.id, {"auto_verify_x": True, "raid_goals": {"retweets": 3}})
    arch = _pending_sub(c2, t2, 602, age_s=240)
    c2.status = "archived"
    db.session.commit()
    assert eng.recheck_pending_x_tasks() == 0
    db.session.refresh(arch)
    assert arch.status == "pending"
