"""Left / removed member flag (Guildizer). Throwaway SQLite DB; nothing is sent to Discord.

Run from discord-board/backend:  python -m pytest tests/test_member_presence.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

_DB = os.path.join(tempfile.mkdtemp(), "mp.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

G = 9710


@pytest.fixture()
def db():
    from database import SessionLocal, init_db
    from models import Guild, Member
    init_db()
    s = SessionLocal()
    s.query(Member).filter(Member.guild_id == G).delete()
    if s.get(Guild, G) is None:
        s.add(Guild(id=G, name="G", owner_id=1, plan="free"))
        s.flush()
    s.add(Member(guild_id=G, user_id=1, username="ann", xp=10))
    s.commit()
    yield s
    s.close()


def _m(db):
    from models import Member
    db.expire_all()
    return db.get(Member, {"guild_id": G, "user_id": 1})


def test_left_then_join_clears(db):
    import member_presence as mp
    mp.record_left(G, 1)
    m = _m(db)
    assert m.to_dict()["removed"]["status"] == "left"
    mp.record_joined(G, 1)
    assert _m(db).to_dict()["removed"] is None


def test_recent_dashboard_reason_is_kept(db):
    import member_presence as mp
    mp.mark(db, G, 1, "kicked")
    db.commit()
    mp.record_left(G, 1)          # the leave event that follows the kick
    assert _m(db).removed_reason == "kicked"


def test_ban_overwrites_and_activity_after_means_back(db):
    import member_presence as mp
    mp.record_left(G, 1)
    mp.record_banned(G, 1)
    assert _m(db).removed_reason == "banned"
    m = _m(db)
    m.last_seen = datetime.utcnow() + timedelta(minutes=5)
    db.commit()
    assert _m(db).to_dict()["removed"] is None


def test_kill_switch_and_no_row_creation(db, monkeypatch):
    import member_presence as mp
    from models import Member
    monkeypatch.setenv("MEMBER_LEAVE_TRACKING", "0")
    mp.record_left(G, 1)
    assert _m(db).removed_at is None
    monkeypatch.delenv("MEMBER_LEAVE_TRACKING")
    mp.record_left(G, 999)        # unknown member: no row is created
    assert db.get(Member, {"guild_id": G, "user_id": 999}) is None
