"""Guildizer referral XP: pays once per person per server, and can be switched off without a deploy.

Run from discord-board/backend:  python -m pytest tests/test_invite_xp_rules.py
Throwaway SQLite database; no Discord connection.
"""
import os
import sys
import tempfile

_DB = os.path.join(tempfile.mkdtemp(), "ix.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

G = 9810
INVITER = 111


@pytest.fixture()
def db():
    from database import SessionLocal, init_db
    from models import Guild, GuildSettings, InviteJoin, InviteLink, Member
    init_db()
    s = SessionLocal()
    for M in (InviteJoin, InviteLink, Member):
        s.query(M).filter(M.guild_id == G).delete()
    if s.get(Guild, G) is None:
        s.add(Guild(id=G, name="G", owner_id=1, plan="free"))
        s.flush()
    gs = s.get(GuildSettings, G) or GuildSettings(guild_id=G)
    gs.extra = {"referrals": {"xp_per_referral": 25}}
    s.add(gs)
    s.commit()
    yield s
    s.close()


def _xp(db):
    from models import Member
    db.expire_all()
    m = db.get(Member, {"guild_id": G, "user_id": INVITER})
    return m.xp if m else 0


def _join(joiner, code="abc"):
    import invite_tracking as it
    return it.record_join(G, code, INVITER, "maya", joiner, f"user{joiner}")


def test_a_first_invite_pays_the_configured_amount(db):
    assert _join(900) == 25
    assert _xp(db) == 25


def test_leaving_and_rejoining_pays_nothing_more_but_is_still_recorded(db):
    from models import InviteJoin, InviteLink
    assert _join(900) == 25
    assert _join(900) == 0
    assert _xp(db) == 25
    db.expire_all()
    assert db.query(InviteJoin).filter(InviteJoin.guild_id == G, InviteJoin.joiner_id == 900).count() == 2
    assert db.query(InviteLink).filter(InviteLink.code == "abc").one().uses == 2


def test_a_second_invite_code_for_a_known_person_pays_nothing(db):
    assert _join(900, "abc") == 25
    assert _join(900, "xyz") == 0
    assert _xp(db) == 25


def test_a_different_person_pays_again(db):
    assert _join(900) == 25
    assert _join(901) == 25
    assert _xp(db) == 50


def test_off_by_default(db):
    from models import GuildSettings
    gs = db.get(GuildSettings, G)
    gs.extra = {}
    db.commit()
    assert _join(900) == 0
    assert _xp(db) == 0


def test_kill_switch_stops_xp_but_keeps_tracking(db, monkeypatch):
    from models import InviteJoin
    monkeypatch.setenv("INVITE_XP_ENABLED", "0")
    assert _join(900) == 0
    assert _xp(db) == 0
    db.expire_all()
    assert db.query(InviteJoin).filter(InviteJoin.guild_id == G).count() == 1
    monkeypatch.setenv("INVITE_XP_ENABLED", "1")
    assert _join(901) == 25
