"""Guildizer editable announcement: switches + template. Run from discord-board/backend."""
import os
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'pt.db')}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta  # noqa: E402

import campaign_views as cv  # noqa: E402
import campaign_limits  # noqa: E402


def _data(**kw):
    d = {"id": 0, "title": "Elyon KOLs", "description": "Share your post.", "type": "content_submission",
         "task_url": None, "raid_goals": {}, "social_targets": {}, "show_targets": False, "auto_verify_x": False,
         "has_action_flow": False, "reward_xp": 10, "reward_label": "Up To 100$", "verification_mode": "x_api",
         "ends_at": datetime.utcnow() + timedelta(hours=24), "proof_summary": "a link", "progress": {},
         "submissions_rule": "", "tasks": [], "post_template": "", "post_hide": []}
    d.update(kw)
    return d


def _names(e):
    return [f["name"] for f in e.to_dict().get("fields", [])]


def test_automatic_embed_unchanged():
    e = cv.build_embed(_data())
    assert e.title == "Elyon KOLs" and e.description == "Share your post."
    assert _names(e) == ["Reward", "\U0001F4DD Proof", "\u23F3 Ends"]
    assert e.to_dict()["fields"][0]["value"] == "10 XP \u00B7 Up To 100$"


def test_hide_switches():
    e = cv.build_embed(_data(post_hide=["proof", "deadline"]))
    assert _names(e) == ["Reward"]
    e = cv.build_embed(_data(post_hide=["xp"]))
    assert e.to_dict()["fields"][0]["value"] == "Up To 100$"
    e = cv.build_embed(_data(post_hide=["xp", "reward"]))
    assert "Reward" not in _names(e)


def test_template_replaces_the_whole_post():
    e = cv.build_embed(_data(post_template="**{title}**\nReward: {reward}\nSubs: {submissions}\nEnds {deadline}"))
    d = e.to_dict()
    assert "title" not in d and not d.get("fields")
    assert d["description"].startswith("**Elyon KOLs**\nReward: Up To 100$\nEnds <t:")
    assert "Subs" not in d["description"]            # empty -> line dropped


def test_default_template_matches_automatic_content():
    tpl = cv.default_post_template(_data())
    d = cv.build_embed(_data(post_template=tpl)).to_dict()["description"]
    for want in ("**Elyon KOLs**", "Share your post.", "Reward:** Up To 100$", "XP:** 10 XP", "Proof:** a link", "Ends:** <t:"):
        assert want in d


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("POST_CUSTOMIZE_ENABLED", "0")
    e = cv.build_embed(_data(post_template="custom only", post_hide=["proof"]))
    assert e.title == "Elyon KOLs" and "\U0001F4DD Proof" in _names(e)


def test_settings_cleaning():
    out = campaign_limits.clean_settings({"post_template": "  ", "post_hide": ["proof", "bogus"]})
    assert "post_template" not in out and out["post_hide"] == ["proof"]
