"""Warning ladder fires each step once, on the warning that crosses it."""
import os
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "wl.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

G, U = 9390, 9391


@pytest.fixture()
def db():
    from database import SessionLocal, init_db
    from models import Guild, MemberWarning
    init_db()
    s = SessionLocal()
    if s.get(Guild, G) is None:
        s.add(Guild(id=G, name="W", owner_id=None, plan="free"))
        s.commit()
    s.query(MemberWarning).filter(MemberWarning.guild_id == G).delete()
    s.commit()
    yield s
    s.close()


LADDER = {"enabled": True, "steps": [
    {"at": 3, "action": "timeout", "minutes": 10},
    {"at": 5, "action": "timeout", "minutes": 1440},
    {"at": 7, "action": "kick"}]}


def _run(db, n):
    import moderation_runtime as m
    out = []
    for _ in range(n):
        _, esc = m.add_warning(db, G, U, "u", None, "t", "r", {}, LADDER)
        out.append(esc and (esc["at"], esc["action"]))
    return out


def test_each_step_fires_once(db):
    assert _run(db, 8) == [None, None, (3, "timeout"), None, (5, "timeout"), None, (7, "kick"), None]


def test_kill_switch_restores_repeat(db, monkeypatch):
    monkeypatch.setenv("WARN_LADDER_ONCE", "0")
    assert _run(db, 4)[3] == (3, "timeout")


def test_step_without_window_inherits_global(db):
    import moderation_runtime as m
    from datetime import datetime, timedelta
    from models import MemberWarning
    old = datetime.utcnow() - timedelta(hours=100)
    for _ in range(2):
        db.add(MemberWarning(guild_id=G, user_id=U, created_at=old))
    db.flush()
    _, esc = m.add_warning(db, G, U, "u", None, "t", "r", {"window_hours": 24}, LADDER)
    assert esc is None            # only 1 warning inside the 24h lookback; old ones don't count
