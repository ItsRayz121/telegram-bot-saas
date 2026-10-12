"""Smart Moderation accuracy (Layer 2 rule match, Layer 3 AI verdicts).

Run from discord-board/backend:  python -m pytest tests/test_moderation_accuracy.py
No Discord, no AI provider, no database: pure functions plus a fake message for the
bot's Layer 3 flow.
"""
import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import ai  # noqa: E402
import content_filter as cf  # noqa: E402
import moderation  # noqa: E402


# ── Layer 2: labelled matrix ───────────────────────────────────────────────────
REMOVED = [
    ("DM me for guaranteed profit", "promo_strong"),
    ("Earn $500 daily from home", "promo_strong"),
    ("link in bio", "promo_strong"),
    ("Use my code https://evil.xyz/x", "promo_cta"),
    # a "scam warning" framing does not excuse a call to action with a link
    ("Scam warning! sign up using my code https://evil.xyz", "promo_cta"),
    ("Great referral program https://evil.xyz/join", "promo_topic"),
    # a quoted solicitation inside a fake warning still counts
    ("Beware of scams, but DM me to join", "promo_strong"),
]
ALLOWED = [
    "what is the referral code for this server?",
    "How does the referral program work?",
    "Is crypto signals a scam?",
    "scam warning: someone posted a referral link https://evil.xyz, don't click",
    "I need to make 20 commits before the deadline",
    "the ref said it was offside",
    "reference the docs please",
    "promo code questions go to #support",       # topic phrase, no link
]


@pytest.mark.parametrize("text,label", REMOVED)
def test_removed(text, label):
    assert cf.promo_rule_match(text) == label


@pytest.mark.parametrize("text", ALLOWED)
def test_allowed(text):
    assert cf.promo_rule_match(text) is None


def test_whitelisted_link_never_counts():
    text = "referral details here https://docs.mine.com/ref"
    assert cf.promo_rule_match(text) == "promo_topic"
    assert cf.promo_rule_match(text, trusted_hosts=["mine.com"]) is None


def test_allow_referral_codes_exempts_topic_but_not_strong():
    assert cf.promo_rule_match("use my referral code abc", allow_referral=True) is None
    assert cf.promo_rule_match("DM me my referral code", allow_referral=True) == "promo_strong"


def test_kill_switch_restores_legacy_matching(monkeypatch):
    monkeypatch.setenv("MODERATION_PROMO_CONTEXT_GUARD", "0")
    # legacy behaviour: a bare referral question is removed again
    assert cf.promo_rule_match("what is the referral code?") == "promo_legacy"
    monkeypatch.delenv("MODERATION_PROMO_CONTEXT_GUARD")
    assert cf.promo_rule_match("what is the referral code?") is None


def test_evaluate_smart_patterns_uses_whitelist_and_names_the_rule():
    cfg = {"automod": {
        "smart_mod": {"enabled": True, "promotional_detection": True, "action": "delete"},
        "external_links": {"whitelist": ["mine.com"]},
    }}
    d = moderation.evaluate_smart_patterns("referral https://evil.xyz/x", cfg)
    assert d and d["rule"] == "promo_topic" and "promo_topic" in d["detail"]
    assert moderation.evaluate_smart_patterns("referral https://mine.com/x", cfg) is None


# ── Layer 3 ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ('{"verdict":"promotional","confidence":"high","reason":"ad"}', ("promotional", "ad")),
    ('{"verdict":"promotional","confidence":"low","reason":"maybe"}', ("uncertain", "maybe")),
    ('{"verdict":"ok","confidence":"low","reason":"fine"}', ("ok", "fine")),
    ('```json\n{"verdict":"irrelevant","confidence":"high","reason":"off"}\n```', ("irrelevant", "off")),
    ("PROMO", ("unavailable", "malformed model output")),
    ('{"verdict":"nuke"}', ("unavailable", "malformed model output")),
    ("", ("unavailable", "malformed model output")),
])
def test_parse_classification(raw, expected):
    assert ai.parse_classification(raw) == expected


def test_trusted_ids_compare_as_strings():
    assert moderation.is_trusted_user(123, ["123"])
    assert moderation.is_trusted_user("123", [123])
    assert not moderation.is_trusted_user(None, ["123"])


def test_revalidate():
    base = {"enabled": True, "ai_enabled": True, "trusted_user_ids": [], "ai_mode": "enforce"}
    rv = moderation.revalidate_ai_decision
    assert rv(base, 1, "promotional") == "apply"
    assert rv(None, 1, "promotional") == "skip:settings_unavailable"      # fail safe
    assert rv({**base, "enabled": False}, 1, "promotional") == "skip:disabled_since"
    assert rv({**base, "ai_enabled": False}, 1, "promotional") == "skip:disabled_since"
    assert rv({**base, "trusted_user_ids": ["1"]}, 1, "promotional") == "skip:trusted_since"
    assert rv({**base, "ai_mode": "observe"}, 1, "promotional") == "observe"


def test_duplicate_events_are_claimed_once():
    assert moderation.claim_message_event(1, 2, 3001, None) is True
    assert moderation.claim_message_event(1, 2, 3001, None) is False
    # an edit of the same message is a different event
    assert moderation.claim_message_event(1, 2, 3001, "2026-10-12T10:00:00") is True
    # no id: never guess
    assert moderation.claim_message_event(1, 2, None, None) is True
    assert moderation.claim_message_event(1, 2, None, None) is True


# ── bot flow ───────────────────────────────────────────────────────────────────
class _Perms:
    administrator = manage_guild = manage_messages = False


def _make(monkeypatch, verdict, fresh_sm=None, staff_now=False):
    import bot_core
    sm = {"enabled": True, "ai_enabled": True, "ai_mode": "enforce", "action": "delete",
          "trusted_user_ids": [], "group_topic": "defi", "ai_rate_limit_seconds": 5}
    cfg = {"automod": {"smart_mod": sm}}
    fresh = {"automod": {"smart_mod": {**sm, **(fresh_sm or {})}}}
    calls = {"exec": [], "log": []}

    class Core(bot_core.CoreMixin):
        def __init__(self):
            pass

        @staticmethod
        def _load_moderation(gid):
            return fresh

        @staticmethod
        def _log_ai(*a):
            pass

        @staticmethod
        def _log(gid, category, action, uid=None, uname=None, cid=None, detail=None):
            calls["log"].append((category, action, detail))

        async def _execute_action(self, message, decision, cfg=None):
            calls["exec"].append(decision["action"])
            return "deleted"

    usage = types.SimpleNamespace(model="m", input_tokens=1, output_tokens=1, text="")
    monkeypatch.setattr(bot_core.ai, "is_configured", lambda: True)
    monkeypatch.setattr(bot_core.ai, "classify_message", lambda t, g, r=None: (verdict, "why", usage))
    bot_core._smartmod_last.clear()
    author = types.SimpleNamespace(id=7, __str__=lambda s: "u")
    member = types.SimpleNamespace(guild_permissions=_Perms() if not staff_now else
                                   types.SimpleNamespace(administrator=True, manage_guild=False,
                                                         manage_messages=False))
    guild = types.SimpleNamespace(id=1, get_member=lambda i: member)
    msg = types.SimpleNamespace(
        guild=guild, author=author, channel=types.SimpleNamespace(id=5),
        content="buy my amazing token now, limited presale https://x.example",
        reference=None)
    return Core(), msg, cfg, calls


def _run(core, msg, cfg):
    return asyncio.run(core._smart_mod_check(msg, cfg))


def test_confident_promo_is_removed(monkeypatch):
    core, msg, cfg, calls = _make(monkeypatch, "promotional")
    assert _run(core, msg, cfg) is True
    assert calls["exec"] == ["delete"]
    assert "L3:ai_promotional" in calls["log"][0][2]


@pytest.mark.parametrize("verdict", ["uncertain", "unavailable", "ok"])
def test_unsure_or_failed_never_acts(monkeypatch, verdict):
    core, msg, cfg, calls = _make(monkeypatch, verdict)
    assert _run(core, msg, cfg) is False
    assert calls["exec"] == []


def test_review_mode_logs_but_does_not_act(monkeypatch):
    core, msg, cfg, calls = _make(monkeypatch, "promotional", fresh_sm={"ai_mode": "observe"})
    assert _run(core, msg, cfg) is False
    assert calls["exec"] == []
    assert "promotional:review" in calls["log"][0][2] and calls["log"][0][1] == "none"


def test_setting_changed_during_the_model_call_is_honoured(monkeypatch):
    core, msg, cfg, calls = _make(monkeypatch, "promotional", fresh_sm={"enabled": False})
    assert _run(core, msg, cfg) is False
    assert calls["exec"] == []
    core, msg, cfg, calls = _make(monkeypatch, "promotional", fresh_sm={"trusted_user_ids": ["7"]})
    assert _run(core, msg, cfg) is False and calls["exec"] == []


def test_member_promoted_to_staff_meanwhile_is_not_punished(monkeypatch):
    core, msg, cfg, calls = _make(monkeypatch, "promotional", staff_now=True)
    assert _run(core, msg, cfg) is False and calls["exec"] == []


def test_irrelevant_needs_a_topic(monkeypatch):
    core, msg, cfg, calls = _make(monkeypatch, "irrelevant", fresh_sm={"group_topic": ""})
    cfg["automod"]["smart_mod"]["group_topic"] = ""
    assert _run(core, msg, cfg) is False and calls["exec"] == []
    core, msg, cfg, calls = _make(monkeypatch, "irrelevant")
    assert _run(core, msg, cfg) is True and calls["exec"] == ["delete"]
