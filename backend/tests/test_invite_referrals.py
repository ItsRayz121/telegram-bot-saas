"""Telegram referral links: XP for the inviter, and the rules that stop it being farmed.

Run from the repo root:  python -m pytest backend/tests/test_invite_referrals.py
In-memory SQLite; no Telegram.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask

from backend import invite_referrals as ref
from backend.models import db, InviteLink, InviteLinkJoin
import backend.assistant.hub_models  # noqa: F401


# ── pure rules ────────────────────────────────────────────────────────────────

def test_amount_is_clamped_and_junk_means_off():
    assert ref.xp_per_invite({"invites": {"xp_per_invite": 25}}) == 25
    assert ref.xp_per_invite({"invites": {"xp_per_invite": 99999}}) == ref.MAX_XP
    assert ref.xp_per_invite({"invites": {"xp_per_invite": -5}}) == 0
    for junk in (None, "abc", [], {}, 0, "0"):
        assert ref.xp_per_invite({"invites": {"xp_per_invite": junk}}) == 0
    assert ref.xp_per_invite({}) == 0 and ref.xp_per_invite(None) == 0
    assert ref.xp_per_invite({"invites": "oops"}) == 0


def test_personal_link_name_keeps_prefix_within_telegram_limit():
    n = ref.personal_link_name("   Maya   the   Great  ")
    assert n == "Invite by Maya the Great" and len(n) <= 32
    long = ref.personal_link_name("x" * 100)
    assert len(long) == 32 and long.startswith(ref.REF_PREFIX)
    assert ref.personal_link_name("") == "Invite by member"


def _decide(**kw):
    base = dict(xp=25, link_name="Invite by Maya", link_creator_id="7", joiner_id="9", joiner_is_bot=False, already_counted=False)
    base.update(kw)
    return ref.decide_xp(**base)


def test_a_normal_invite_pays():
    assert _decide() == 25


@pytest.mark.parametrize("kw", [
    {"xp": 0},                                   # feature off (the default)
    {"link_name": "Twitter raid"},               # an admin's campaign link never pays its creator
    {"link_creator_id": None},                   # a link nobody owns
    {"joiner_id": "7"},                          # inviting yourself
    {"joiner_is_bot": True},                     # bot accounts
    {"already_counted": True},                   # leave and re-join / second link
])
def test_cases_that_must_not_pay(kw):
    assert _decide(**kw) == 0


def test_kill_switch_stops_xp(monkeypatch):
    monkeypatch.setenv("INVITE_XP_ENABLED", "0")
    assert _decide() == 0
    monkeypatch.setenv("INVITE_XP_ENABLED", "1")
    assert _decide() == 25


# ── database behaviour ────────────────────────────────────────────────────────

@pytest.fixture()
def ctx():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


G1 = {"telegram_group_id": "-1001"}
G2 = {"telegram_group_id": "-1002"}
ON = {"invites": {"xp_per_invite": 25}}


def _link(group, name, url, creator="7", active=True):
    row = InviteLink(name=name, telegram_invite_link=url, created_by_telegram_id=creator, is_active=active, **group)
    db.session.add(row)
    db.session.commit()
    return row


def test_first_join_through_a_personal_link_pays_and_is_recorded(ctx):
    lnk = _link(G1, "Invite by Maya", "https://t.me/+aaa")
    res = ref.record_join(G1, "https://t.me/+aaa", 9, "leo", False, ON)
    assert res.xp == 25 and res.inviter_id == "7"
    assert InviteLink.query.get(lnk.id).uses_count == 1
    assert InviteLinkJoin.query.filter_by(invite_link_id=lnk.id, joined_user_id="9").count() == 1


def test_leaving_and_rejoining_does_not_pay_twice(ctx):
    _link(G1, "Invite by Maya", "https://t.me/+aaa")
    assert ref.record_join(G1, "https://t.me/+aaa", 9, "leo", False, ON).xp == 25
    again = ref.record_join(G1, "https://t.me/+aaa", 9, "leo", False, ON)
    assert again.xp == 0
    assert InviteLinkJoin.query.filter_by(joined_user_id="9").count() == 2   # still recorded for the stats


def test_second_personal_link_for_a_known_person_pays_nothing(ctx):
    _link(G1, "Invite by Maya", "https://t.me/+aaa", creator="7")
    _link(G1, "Invite by Ana", "https://t.me/+bbb", creator="8")
    assert ref.record_join(G1, "https://t.me/+aaa", 9, "leo", False, ON).xp == 25
    assert ref.record_join(G1, "https://t.me/+bbb", 9, "leo", False, ON).xp == 0


def test_admin_campaign_link_is_tracked_but_never_pays(ctx):
    lnk = _link(G1, "Twitter raid", "https://t.me/+ccc", creator="1")
    res = ref.record_join(G1, "https://t.me/+ccc", 9, "leo", False, ON)
    assert res.xp == 0 and InviteLink.query.get(lnk.id).uses_count == 1


def test_off_by_default_even_for_personal_links(ctx):
    _link(G1, "Invite by Maya", "https://t.me/+aaa")
    assert ref.record_join(G1, "https://t.me/+aaa", 9, "leo", False, {}).xp == 0


def test_another_group_does_not_count_as_already_joined(ctx):
    _link(G1, "Invite by Maya", "https://t.me/+aaa")
    _link(G2, "Invite by Ana", "https://t.me/+bbb", creator="8")
    assert ref.record_join(G1, "https://t.me/+aaa", 9, "leo", False, ON).xp == 25
    assert ref.record_join(G2, "https://t.me/+bbb", 9, "leo", False, ON).xp == 25


def test_unknown_or_inactive_links_are_ignored(ctx):
    _link(G1, "Invite by Maya", "https://t.me/+old", active=False)
    assert ref.record_join(G1, "https://t.me/+old", 9, "leo", False, ON) is None
    assert ref.record_join(G1, "https://t.me/+nope", 9, "leo", False, ON) is None
    assert InviteLinkJoin.query.count() == 0


def test_personal_link_is_reused_not_duplicated(ctx):
    assert ref.get_personal_link(G1, 7) is None
    ref.save_personal_link(G1, 7, "maya", "Invite by Maya", "https://t.me/+aaa")
    found = ref.get_personal_link(G1, 7)
    assert found and found.telegram_invite_link == "https://t.me/+aaa"
    assert ref.get_personal_link(G1, 8) is None          # someone else's link is not theirs
    assert ref.get_personal_link(G2, 7) is None          # nor is it valid in another group
