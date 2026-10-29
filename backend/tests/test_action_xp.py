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
