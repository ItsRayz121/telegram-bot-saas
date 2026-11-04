"""Guild sync: one failing part must not wipe the others (codes GS-100/200/300)."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import guild_sync
import sync_errors
from models import Base, Channel, Guild, Role


def _db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _dguild(owner_id=999):
    ch = SimpleNamespace(id=1, name="general", type=SimpleNamespace(value=0), position=0, category_id=None)
    role = SimpleNamespace(id=2, name="Mod", color=SimpleNamespace(value=1), position=1,
                           permissions=SimpleNamespace(value=8), managed=False, mentionable=False)
    return SimpleNamespace(id=10, name="G", icon=None, member_count=38, owner_id=owner_id,
                           channels=[ch], roles=[role])


def test_unregistered_owner_does_not_abort_sync():
    db = _db()
    status, code = guild_sync.full_sync(db, _dguild())
    db.commit()
    assert (status, code) == ("ok", None)
    g = db.get(Guild, 10)
    assert g.owner_id is None and g.member_count == 38 and g.sync_status == "ok"
    assert db.query(Channel).count() == 1 and db.query(Role).count() == 1


def test_roles_failure_keeps_channels_and_marks_partial(monkeypatch):
    db = _db()

    def boom(*a, **k):
        raise RuntimeError("roles exploded")

    monkeypatch.setattr(guild_sync, "sync_roles", boom)
    status, code = guild_sync.full_sync(db, _dguild())
    db.commit()
    assert (status, code) == ("partial", "GS-300")
    g = db.get(Guild, 10)
    assert g.sync_status == "partial" and g.sync_error_code == "GS-300"
    assert db.query(Channel).count() == 1 and db.query(Role).count() == 0


def test_error_classification():
    class R:  # minimal requests-like response
        def __init__(self, c): self.status_code = c

    class E(Exception):
        def __init__(self, c): self.response = R(c)

    assert sync_errors.classify_rest_error(E(401)) == "GS-402"
    assert sync_errors.classify_rest_error(E(403)) == "GS-401"
    assert sync_errors.classify_rest_error(E(404)) == "GS-403"
    assert sync_errors.classify_rest_error(E(429)) == "GS-404"
    assert sync_errors.classify_rest_error(E(502)) == "GS-405"
    assert all(sync_errors.describe(c)["message"] for c in sync_errors.CODES)
