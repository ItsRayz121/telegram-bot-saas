"""Hardening tests for the moderation changes: exceptions must not become blanket
bypasses, delayed AI verdicts are re-validated, retried events act once, and the
Markdown fallback never resends after an ambiguous failure.

Run from the repo root:  python -m pytest backend/tests/test_moderation_hardening.py
Pure unit tests: no DB, Telegram or AI provider.
"""
import asyncio
import os
from types import SimpleNamespace as NS

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

from backend.bot_features.moderation import (
    ModerationSystem, promo_rule_match, revalidate_ai_decision,
    claim_message_event, finish_message_event, duplicate_event_result, _event_log,
)

# (message, allow_referral_codes, trusted_hosts, expected rule)
PROMO_MATRIX = [
    # --- real spam stays caught ---
    ("DM me for 100% profit signals", False, (), "promo_strong"),
    ("Use my referral link t.me/mybot_ref join now", False, (), "promo_strong"),
    ("sign up using my invite code https://evil.example/r/9", False, (), "promo_cta"),
    ("invest now https://x.example/gem", False, (), "promo_cta"),
    ("Join the presale https://t.me/pump_now", False, (), "promo_topic"),
    # --- exceptions are not blanket bypasses ---
    ("Want to invest now? t.me/cryptopump", False, (), "promo_cta"),                       # promotional question
    ("Who wants passive income? sign up using https://evil.example/ref", False, (), "promo_cta"),
    ("Scam warning! Beware of fakes. Sign up using my invite code https://evil.example/r/9", False, (), "promo_cta"),
    ("Scam warning! Fake projects exist. DM me for the real one", False, (), "promo_strong"),
    ('Careful: scammers write "DM me" and "guaranteed profit"', False, (), "promo_strong"),  # quoted wording stays deterministic
    # --- genuine questions / discussion are not promotion ---
    ("How do I get my referral code?", False, (), None),
    ("Kya referral code ka reward milta hai", False, (), None),
    ("Should I invest in this project?", False, (), None),
    ("referral code kahan milega؟", False, (), None),
    ("presale is live", False, (), None),                                                   # bare topic word, no link
    ("Is this referral code link legit? https://t.me/somebody", False, (), None),
    ("Is the presale real? @ProjectOfficial", False, (), None),
    ("Beware of presale scams like t.me/fakepresale", False, (), None),
    ("Beware: fake invite code scam t.me/xyzscam do not click", False, (), None),
    # --- the group's own trusted links never count as "pointing somewhere" ---
    ("Should I invest in this? https://official.example/docs", False, ("official.example",), None),
    ("invest now https://official.example/pricing", False, ("official.example",), None),
    # --- explicit group policy / nothing promotional ---
    ("use my code WELCOME10", True, (), None),
    ("gm everyone", False, (), None),
    ("", False, (), None),
]


@pytest.mark.parametrize("text,allow,trusted,expected", PROMO_MATRIX)
def test_promo_matrix(text, allow, trusted, expected):
    assert promo_rule_match(text, allow, trusted_hosts=trusted) == expected


def test_kill_switch_restores_legacy_matching(monkeypatch):
    monkeypatch.setenv("MODERATION_PROMO_CONTEXT_GUARD", "0")
    assert promo_rule_match("How do I get my referral code?") == "promo_ambiguous"


# ── delayed AI decisions are re-validated against CURRENT configuration ───────

@pytest.mark.parametrize("fresh,expected", [
    (None, "skip:settings_unavailable"),
    ({"enabled": False, "ai_enabled": True}, "skip:disabled_since"),
    ({"enabled": True, "ai_enabled": False}, "skip:disabled_since"),
    ({"enabled": True, "ai_enabled": True, "trusted_users": [7]}, "skip:trusted_since"),
    ({"enabled": True, "ai_enabled": True, "ai_mode": "observe"}, "observe"),
    ({"enabled": True, "ai_enabled": True, "ai_mode": "enforce"}, "apply"),
    ({"enabled": True, "ai_enabled": True}, "apply"),
])
def test_revalidate_ai_decision(fresh, expected):
    assert revalidate_ai_decision(fresh, 7, "promotional")[0] == expected


class _Bot:
    def __init__(self, status="member"):
        self.status = status

    async def get_chat_member(self, chat, user):
        return NS(status=self.status)


def _l3(monkeypatch, fresh_cfg, verdict=("promotional", "ad"), admin=False):
    """ModerationSystem whose AI call returns ``verdict`` while the group's LIVE
    config (re-read after the call) is ``fresh_cfg``."""
    from flask import Flask
    ms = ModerationSystem(Flask(__name__))
    seen = {"actions": [], "logs": []}
    stale = {"enabled": True, "ai_enabled": True, "group_topic": "Acme", "action": "delete", "warn_user": True}
    monkeypatch.setattr(ModerationSystem, "_resolve_group_owner", staticmethod(lambda *a, **k: NS(id=1)))
    monkeypatch.setattr("backend.assistant.ai_key_resolver.get_workspace_ai_key", lambda owner: {"api_key": "k", "model": "m"})
    monkeypatch.setattr(ModerationSystem, "_call_ai_moderation", staticmethod(lambda *a, **k: verdict))
    monkeypatch.setattr(ms, "_fresh_smart_mod", lambda group: fresh_cfg)

    async def fake_exec(bot, message, group, action, **kw):
        seen["actions"].append((action, kw.get("warn"), kw.get("layer"), kw.get("rule")))
    ms.execute_automod_action = fake_exec
    ms._log_ai_decision = lambda g, u, m, v, r, **kw: seen["logs"].append(
        (v, kw.get("reason_code"), kw.get("status"), kw.get("executed")))
    msg = NS(from_user=NS(id=7, username="u"), chat=NS(id=-1, title="t"), reply_to_message=None,
             text="word " * 12, caption=None, message_id=1)

    def run():
        return asyncio.run(ms.check_ai_relevance(_Bot("administrator" if admin else "member"),
                                                 msg, msg.text, NS(id=1), {"smart_mod": stale}))
    return run, seen


def test_delayed_verdict_uses_the_current_action_not_the_stale_one(monkeypatch):
    run, seen = _l3(monkeypatch, {"enabled": True, "ai_enabled": True, "action": "mute", "warn_user": False})
    assert run() is True
    assert seen["actions"] == [("mute", False, "L3", "ai_promotional")]


@pytest.mark.parametrize("fresh,code", [
    ({"enabled": False, "ai_enabled": True}, "promotional:skip:disabled_since"),
    ({"enabled": True, "ai_enabled": True, "trusted_users": [7]}, "promotional:skip:trusted_since"),
    (None, "promotional:skip:settings_unavailable"),
    ({"enabled": True, "ai_enabled": True, "ai_mode": "observe"}, "promotional"),
])
def test_delayed_verdict_is_not_applied_when_config_changed(monkeypatch, fresh, code):
    run, seen = _l3(monkeypatch, fresh)
    assert run() is False
    assert seen["actions"] == []
    assert seen["logs"] == [("promotional", code, "skipped", "none")]


def test_delayed_verdict_is_not_applied_to_a_member_promoted_to_admin_meanwhile(monkeypatch):
    run, seen = _l3(monkeypatch, {"enabled": True, "ai_enabled": True}, admin=True)
    assert run() is False and seen["actions"] == []
    assert seen["logs"][0][1] == "promotional:skip:admin_since"


def test_audit_trail_separates_uncertain_unavailable_and_acceptable(monkeypatch):
    live = {"enabled": True, "ai_enabled": True}
    for verdict, status in (("uncertain", "skipped"), ("unavailable", "failed")):
        run, seen = _l3(monkeypatch, live, verdict=(verdict, "why"))
        assert run() is False and seen["actions"] == []
        assert seen["logs"] == [(verdict, verdict, status, "none")]
    # confirmed acceptable: silent in enforce mode, recorded as "acceptable" in review mode
    run, seen = _l3(monkeypatch, live, verdict=("ok", ""))
    assert run() is False and seen["logs"] == []
    run, seen = _l3(monkeypatch, {**live, "ai_mode": "observe"}, verdict=("ok", ""))
    assert run() is False and seen["logs"] == [("ok", "acceptable", "ok", "none")]


# ── duplicate / retried events ────────────────────────────────────────────────

def test_retried_event_is_claimed_once_and_reports_the_first_result():
    _event_log.clear()
    m = NS(message_id=11, edit_date=None)
    first, key = claim_message_event(-1, m)
    assert first is True
    dup, key2 = claim_message_event(-1, m)
    assert dup is False and key2 == key
    assert duplicate_event_result(key) is False          # still in flight: never acts again
    finish_message_event(key, True)
    assert duplicate_event_result(key) is True            # the first delivery blocked it
    assert claim_message_event(-1, NS(message_id=12, edit_date=None))[0]          # new message
    assert claim_message_event(-2, m)[0]                                          # other chat
    assert claim_message_event(-1, NS(message_id=11, edit_date=1700000000))[0]    # an EDIT is a new event


def test_check_automod_runs_the_rules_once_for_a_redelivered_update(monkeypatch):
    _event_log.clear()
    ms = ModerationSystem(NS())
    calls = []

    async def impl(bot, message, group):
        calls.append(message.message_id)
        return True
    monkeypatch.setattr(ms, "_check_automod_impl", impl)
    msg = NS(message_id=5, edit_date=None, chat=NS(id=-1))
    assert asyncio.run(ms.check_automod(None, msg, NS())) is True
    assert asyncio.run(ms.check_automod(None, msg, NS())) is True     # the retry gets the same answer ...
    assert calls == [5]                                               # ... with no second warning / punishment


# ── Markdown fallback ─────────────────────────────────────────────────────────

class BadRequest(Exception):
    """Same class name python-telegram-bot uses; the helper keys on it."""


class TimedOut(Exception):
    pass


class _Msg:
    def __init__(self, first_error=None):
        self.sent, self.first_error = [], first_error

    async def reply_text(self, text, parse_mode=None):
        self.sent.append((text, parse_mode))
        if self.first_error is not None and len(self.sent) == 1:
            raise self.first_error
        return NS(message_id=len(self.sent))


def test_markdown_falls_back_to_plain_only_on_a_confirmed_formatting_rejection():
    from backend.bot_utils import reply_ai_answer
    m = _Msg(BadRequest("Can't parse entities: can't find end of the entity starting at byte offset 5"))
    asyncio.run(reply_ai_answer(m, "snake_case and *bold"))
    assert m.sent == [("snake_case and *bold", "Markdown"), ("snake_case and *bold", None)]


@pytest.mark.parametrize("err", [TimedOut("Timed out"), BadRequest("Chat not found"), ConnectionError("reset")])
def test_ambiguous_failures_are_never_resent(err):
    from backend.bot_utils import reply_ai_answer
    m = _Msg(err)
    with pytest.raises(type(err)):
        asyncio.run(reply_ai_answer(m, "hello"))
    assert len(m.sent) == 1          # the answer may already be delivered: no duplicate post


def test_long_answers_keep_blank_lines_across_messages():
    from backend.bot_utils import reply_ai_answer
    m = _Msg()
    asyncio.run(reply_ai_answer(m, "\n\n".join(["p" * 1500] * 4), prefix="Answer:\n"))
    assert len(m.sent) == 2 and all(len(t) <= 4096 for t, _ in m.sent)
    assert "\n\n" in m.sent[0][0]


# ── regression: dashboard saves Telegram IDs as strings, the bot sees ints ────

def test_saved_string_ids_match_the_integer_sender_id():
    from backend.bot_features.moderation import is_trusted_user
    assert is_trusted_user(123456789, ["123456789"]) is True       # what the dashboard stores
    assert is_trusted_user(123456789, [123456789]) is True         # legacy integer entries
    assert is_trusted_user("123456789", [123456789]) is True
    assert is_trusted_user(123456789, ["987"]) is False
    assert is_trusted_user(None, ["1"]) is False
    assert is_trusted_user(5, None) is False


def test_delayed_verdict_honours_a_string_trusted_id(monkeypatch):
    run, seen = _l3(monkeypatch, {"enabled": True, "ai_enabled": True, "trusted_users": ["7"]})
    assert run() is False and seen["actions"] == []
    assert seen["logs"][0][1] == "promotional:skip:trusted_since"
