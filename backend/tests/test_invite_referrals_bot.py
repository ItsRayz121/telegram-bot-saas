"""Referral XP as the bots apply it: the official bot's join handler and the custom-bot XP ledger.

Run from the repo root:  python -m pytest backend/tests/test_invite_referrals_bot.py
In-memory SQLite; no Telegram.
"""
import os
from types import SimpleNamespace as NS

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from flask import Flask

from backend import invite_referrals as ref
from backend.models import db, TelegramGroup, OfficialMember, InviteLink, InviteLinkJoin, XpEvent, Group, Member
import backend.assistant.hub_models  # noqa: F401

GID = "-100A"
URL = "https://t.me/+maya"


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", TESTING=True, SECRET_KEY="x",
                      SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}})
    db.init_app(app)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _setup(app, settings):
    with app.app_context():
        db.session.add(TelegramGroup(telegram_group_id=GID, title="G", owner_user_id=1, bot_status="active", settings=settings))
        db.session.commit()
        ref.save_personal_link({"telegram_group_id": GID}, 7, "maya", "Invite by Maya", URL)


def _join(app, ob, uid=9, bot=False, url=URL):
    ob._handle_invite_join(app, GID, NS(id=uid, username=f"u{uid}", is_bot=bot), NS(invite_link=url) if url else None)


def _inviter(app):
    with app.app_context():
        return OfficialMember.query.filter_by(telegram_group_id=GID, telegram_user_id="7").first()


ON = {"levels": {"enabled": True, "roles": [{"level": 2, "name": "Active Member"}]}, "invites": {"xp_per_invite": 150}}


def test_inviter_gets_xp_level_role_and_a_ledger_row(app):
    from backend import official_bot as ob
    _setup(app, ON)
    _join(app, ob)
    with app.app_context():
        m = _inviter(app)
        assert m.xp == 150 and m.xp_1d == 150 and m.xp_7d == 150 and m.xp_30d == 150
        assert m.level == 2 and m.role == "active_member"          # 150 XP is level 2 (100 XP per level)
        ev = XpEvent.query.filter_by(scope="official", member_id=m.id).all()
        assert [(e.amount, e.reason) for e in ev] == [(150, "referral")]
        assert InviteLinkJoin.query.filter_by(joined_user_id="9").count() == 1


def test_rejoining_pays_nothing_more(app):
    from backend import official_bot as ob
    _setup(app, ON)
    _join(app, ob)
    _join(app, ob)
    with app.app_context():
        assert _inviter(app).xp == 150


def test_nothing_is_paid_when_the_amount_is_zero_or_missing(app):
    from backend import official_bot as ob
    _setup(app, {"levels": {"enabled": True}})                       # no xp_per_invite set: the default
    _join(app, ob)
    with app.app_context():
        assert _inviter(app) is None                                  # no member row is even created
        assert InviteLinkJoin.query.count() == 1                      # the join is still tracked


def test_nothing_is_paid_when_the_group_has_xp_switched_off(app):
    from backend import official_bot as ob
    _setup(app, {"levels": {"enabled": False}, "invites": {"xp_per_invite": 50}})
    _join(app, ob)
    with app.app_context():
        assert _inviter(app) is None and InviteLinkJoin.query.count() == 1


def test_self_invite_and_bots_are_not_paid(app):
    from backend import official_bot as ob
    _setup(app, ON)
    _join(app, ob, uid=7)                 # the inviter joining with their own link
    _join(app, ob, uid=10, bot=True)      # a bot account
    with app.app_context():
        assert _inviter(app) is None


def test_kill_switch_stops_payment_but_keeps_tracking(app, monkeypatch):
    from backend import official_bot as ob
    _setup(app, ON)
    monkeypatch.setenv("INVITE_XP_ENABLED", "0")
    _join(app, ob)
    with app.app_context():
        assert _inviter(app) is None and InviteLinkJoin.query.count() == 1


def test_a_failure_here_never_breaks_the_join(app):
    from backend import official_bot as ob
    _setup(app, ON)
    _join(app, ob, url=None)                                          # join without an invite link
    ob._handle_invite_join(None, GID, NS(id=9, username="x", is_bot=False), NS(invite_link=URL))   # no app at all
    ob._handle_invite_join(app, GID, None, NS(invite_link=URL))       # broken user object: swallowed and logged
    with app.app_context():
        assert _inviter(app) is None


def test_custom_bot_xp_is_recorded_with_the_referral_reason(app):
    from backend.database import DatabaseManager
    with app.app_context():
        g = Group(bot_id=1, telegram_group_id="-100C", settings={"levels": {"enabled": True}})
        db.session.add(g)
        db.session.commit()
        member, leveled_up, level = DatabaseManager.add_xp(g.id, 7, 120, "maya", None, reason="referral")
        assert member.xp == 120 and leveled_up and level == 2
        assert [(e.amount, e.reason) for e in XpEvent.query.filter_by(scope="custom", member_id=member.id)] == [(120, "referral")]
        # the default reason is unchanged for every other caller
        DatabaseManager.add_xp(g.id, 7, 10, "maya", None)
        assert [e.reason for e in XpEvent.query.filter_by(scope="custom", member_id=member.id).order_by(XpEvent.id)] == ["referral", "award"]
