"""Saved X handle per Discord account: saved once, reused, one handle = one account,
and the campaign submit path falls back to it.

Run from discord-board/backend:  python -m pytest tests/test_social_handles.py
"""
import os
import sys
import tempfile

_DB = os.path.join(tempfile.mkdtemp(), "sh.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _init():
    from database import SessionLocal, init_db
    from models import SocialIdentity
    init_db()
    db = SessionLocal()
    db.query(SocialIdentity).delete()
    db.commit()
    db.close()
    SessionLocal.remove()


def test_save_once_reuse_and_change():
    import social_handles as sh
    assert sh.get_handle(1) is None
    assert sh.set_handle(1, "@Alice") == "Alice"
    assert sh.get_handle(1) == "Alice"            # any campaign reads the same value
    assert sh.set_handle(1, "https://x.com/alice2") == "alice2"   # change
    assert sh.get_handle(1) == "alice2"


def test_bad_input_is_rejected():
    import social_handles as sh
    assert sh.set_handle(2, "") is None
    assert sh.set_handle(2, "not a handle!!") is None
    assert sh.set_handle(2, "waytoolongusername_x") is None
    assert sh.get_handle(2) is None


def test_one_handle_one_discord_account_and_kill_switch(monkeypatch):
    import social_handles as sh
    assert sh.set_handle(10, "@Farmer") == "Farmer"
    assert sh.set_handle(11, "@farmer") == sh.TAKEN        # case-insensitive
    assert sh.get_handle(11) is None
    assert sh.set_handle(10, "@Farmer") == "Farmer"        # own re-save is fine
    monkeypatch.setenv("SOCIAL_HANDLE_UNIQUE", "0")
    assert sh.set_handle(11, "@farmer") == "farmer"


def test_resolve_handle_rules():
    import campaign_runtime as rt
    import social_handles as sh
    # nothing saved: a typed handle is used and remembered
    assert rt._resolve_handle(20, "bob") == "bob"
    assert sh.get_handle(20) == "bob"
    # blank field: the saved one is used
    assert rt._resolve_handle(20, None) == "bob"
    # typed handle owned by another account is never used
    sh.set_handle(21, "@taken_one")
    assert rt._resolve_handle(22, "taken_one") is None
    assert sh.get_handle(22) is None
    # a different typed handle does not silently replace the saved one
    assert rt._resolve_handle(20, "carol") == "carol"
    assert sh.get_handle(20) == "bob"
    # no user id (legacy callers): behaves as before
    assert rt._resolve_handle(None, "dave") == "dave"
