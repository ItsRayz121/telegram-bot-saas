"""Per-action XP for Twitter raids (settings.action_xp)."""
from types import SimpleNamespace

from backend import engagement as eng


def _raid(settings, reward_xp=30):
    return SimpleNamespace(type="raid", platform="x", reward_xp=reward_xp, settings=settings)


GOALS = {"likes": 50, "retweets": 40, "comments": 60, "quotes": 25, "follows": 15}


def test_sum_of_targeted_actions():
    c = _raid({"raid_goals": GOALS, "action_xp": {"like": 5, "retweet": 10, "comment": 15, "quote": 20, "follow": 25}})
    assert eng.campaign_reward_xp(c) == 75


def test_untargeted_action_ignored():
    c = _raid({"raid_goals": {"likes": 10}, "action_xp": {"like": 5, "follow": 99}})
    assert eng.action_xp_map(c) == {"like": 5}
    assert eng.campaign_reward_xp(c) == 5


def test_falls_back_to_flat_reward():
    assert eng.campaign_reward_xp(_raid({"raid_goals": GOALS})) == 30
    assert eng.campaign_reward_xp(_raid({"raid_goals": GOALS, "action_xp": {"like": 0, "bad": "x"}})) == 30


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("ENGAGEMENT_ACTION_XP_ENABLED", "0")
    c = _raid({"raid_goals": GOALS, "action_xp": {"like": 5}})
    assert eng.campaign_reward_xp(c) == 30


def test_targets_line_per_action_counts():
    from backend.engagement_telegram import _targets_line
    line = _targets_line({"likes": 50, "follows": 20}, {"likes": 3, "follows": 1, "retweets": 9})
    assert "3/50 Likes" in line and "1/20 Follows" in line and "Retweets" not in line
    # legacy single number still works and is clamped
    assert "5/5 Likes" in _targets_line({"likes": 5}, 99)


def _sub(status, acts, paid=None):
    payload = {"actions": {a: {"status": s} for a, s in acts.items()}}
    if paid:
        payload["xp_awarded"] = paid
    return SimpleNamespace(status=status, payload=payload, rewarded=bool(paid))


XP = {"like": 10, "retweet": 20, "comment": 15, "quote": 30, "follow": 10}


def test_approval_pays_only_passed_actions_then_tops_up():
    c = _raid({"raid_goals": GOALS, "action_xp": XP})
    acts = {"like": "verified", "retweet": "verified", "comment": "verified",
            "quote": "failed", "follow": "verified"}
    first = eng._unpaid_action_xp(c, _sub("verified", acts))
    assert sum(first.values()) == 55 and "quote" not in first  # 85 total - 30 failed
    # later the member passes quote: only that action is still unpaid
    acts["quote"] = "verified"
    top_up = eng._unpaid_action_xp(c, _sub("verified", acts, paid=first))
    assert top_up == {"quote": 30}


def test_pending_submission_pays_nothing_and_manual_counts_once_approved():
    c = _raid({"raid_goals": {"likes": 5, "follows": 5}, "action_xp": XP})
    acts = {"like": "verified", "follow": "manual"}
    assert eng._unpaid_action_xp(c, _sub("pending", acts)) == {}
    assert eng._unpaid_action_xp(c, _sub("verified", acts)) == {"like": 10, "follow": 10}


def test_legacy_paid_submission_is_never_paid_again():
    c = _raid({"raid_goals": GOALS, "action_xp": XP})
    legacy = _sub("verified", {a: "verified" for a in XP})
    legacy.rewarded = True  # paid in full before xp_awarded existed
    assert eng._unpaid_action_xp(c, legacy) == {}


def test_user_replied_targeted_search(monkeypatch):
    from backend import twitter_verify as tv

    class R:
        status_code = 200
        def __init__(self, tweets): self._t = tweets
        def json(self): return {"tweets": self._t}

    seen = {}
    def fake_get(path, params, key):
        seen["q"] = params["query"]
        return R([{"id": "9", "author": {"userName": "DrMukty"}}])
    monkeypatch.setattr(tv, "_get", fake_get)
    assert tv._user_replied("1", "drmukty", "k") is True
    assert seen["q"] == "from:drmukty conversation_id:1"
    monkeypatch.setattr(tv, "_get", lambda *a, **k: R([]))
    assert tv._user_replied("1", "drmukty", "k") is False


def test_verify_miss_retries_then_goes_to_manual(monkeypatch):
    import os
    from flask import Flask
    from backend.models import db, User, EngagementCampaign
    import backend.assistant.hub_models  # noqa: F401
    from backend import twitter_verify as tv

    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True,
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    monkeypatch.setattr(eng, "campaign_owner_is_paid", lambda c: True)
    monkeypatch.setattr(tv, "enabled", lambda *a, **k: True)
    monkeypatch.setattr(tv, "_key", lambda *a, **k: "k")
    results = iter([("unknown", None), ("unknown", None), ("verified", "ok")])
    monkeypatch.setattr(tv, "verify_action", lambda *a, **k: next(results))
    monkeypatch.setattr(eng, "_refresh_post_progress", lambda c: None)
    monkeypatch.setattr(eng, "_submission_event", lambda *a, **k: None)
    with app.app_context():
        db.create_all()
        u = User(email="o@x.io", full_name="O", auth_provider="email")
        db.session.add(u); db.session.flush()
        c = EngagementCampaign(telegram_group_id="-1", owner_user_id=u.id, type="raid", title="r",
                               status="active", task_url="https://x.com/a/status/12345678",
                               settings={"raid_goals": {"retweets": 5}, "auto_verify_x": True})
        db.session.add(c); db.session.commit()
        kw = dict(telegram_user_id="7", telegram_username="u", action="retweet", handle="u")
        r1 = eng.verify_user_action(c, **kw)
        assert r1["status"] == "failed" and "Verify again" in r1["detail"]
        r2 = eng.verify_user_action(c, **kw)      # second miss -> manual review
        assert r2["status"] == "manual"
        r3 = eng.verify_user_action(c, **kw)      # later it is found -> verified
        assert r3["status"] == "verified"
