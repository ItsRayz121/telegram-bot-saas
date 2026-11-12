"""Editable announcement: switches + template. The automatic post must stay byte-identical."""
import os
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from types import SimpleNamespace as NS

from backend import engagement_insights as ei, post_template as pt, engagement as eng

USER = NS(id=1)
CS = NS(scope="custom")


def _data(**kw):
    d = {"type": "content_submission", "title": "Elyon <KOL> & Co", "description": "Share your post.",
         "verification_mode": "x_api", "platform": "x", "reward_xp": 10, "reward_label": "Up To 100$",
         "duration_hours": 24, "custom_fields": [{"label": "Link", "field_type": "url", "required": True}],
         "settings": {}}
    d.update(kw)
    return d


def _html(settings=None, **kw):
    d = _data(**kw)
    d["settings"] = settings or {}
    return ei.preview_message(CS, USER, d)["html"]


def test_automatic_post_is_unchanged():
    t = _html()
    lines = t.split("\n")
    assert lines[0] == "\U0001F4DD <b>Elyon &lt;KOL&gt; &amp; Co</b>" or lines[0].endswith("<b>Elyon &lt;KOL&gt; &amp; Co</b>")
    assert lines[1] == "" and lines[2] == "Share your post." and lines[3] == ""
    assert "\U0001F381 <b>Reward:</b> Up To 100$" in t and "<b>XP:</b> 10" in t
    assert "<b>Proof:</b> a link" in t and "<b>Deadline:</b>" in t and "<b>Status:</b>" in t
    assert t.endswith("Tap below to take part \U0001F447")


def test_hide_switches_remove_only_those_lines():
    t = _html({"post_hide": ["proof", "deadline"]})
    assert "Proof" not in t and "Deadline" not in t
    assert "Reward" in t and "XP" in t and "Status" in t


def test_template_fills_live_values_and_drops_empty_lines():
    tpl = "**{title}**\n\nReward: {reward}\nSubmissions: {submissions}\nDeadline: {deadline}"
    t = _html({"post_template": tpl})
    assert t.startswith("<b>Elyon &lt;KOL&gt; &amp; Co</b>")
    assert "Reward: Up To 100$" in t and "Deadline: " in t
    assert "Submissions" not in t                    # empty value -> whole line dropped
    assert "Tap below" not in t                      # the admin's text is kept as written


def test_template_text_is_escaped_so_it_cannot_break_telegram_html():
    t = _html({"post_template": "<b>hack</b> <a href='x'>y</a> {title}"})
    assert "<a " not in t and "&lt;b&gt;hack&lt;/b&gt;" in t


def test_unknown_placeholder_stays_literal():
    assert "{nope}" in _html({"post_template": "hi {nope} {title}"})


def test_kill_switch_ignores_template_and_hide(monkeypatch):
    monkeypatch.setenv("POST_CUSTOMIZE_ENABLED", "0")
    t = _html({"post_template": "custom only", "post_hide": ["proof"]})
    assert "custom only" not in t and "Proof" in t


def test_settings_are_cleaned_on_save():
    out = eng._clean_multi_settings({"post_template": "   ", "post_hide": ["proof", "bogus", "proof"]})
    assert "post_template" not in out and out["post_hide"] == ["proof"]
    out = eng._clean_multi_settings({"post_template": "x" * 5000})
    assert len(out["post_template"]) == pt.MAX_TEMPLATE


def test_preview_returns_default_template_and_placeholders():
    r = ei.preview_message(CS, USER, _data())
    assert "{reward}" in r["default_template"] and "title" in r["placeholders"]
    # the default template renders to the same text as the automatic post
    assert _html({"post_template": r["default_template"]}).replace("\n\n\n", "\n\n") == _html()
