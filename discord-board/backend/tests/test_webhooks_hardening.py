"""Outbound webhooks: DNS-pinned fetch, editable URL/secret, test-fire. No network."""
import os
import socket
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "wh.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

OWNER, G = 9881, 9890
B = "/api/guilds/%d" % G


@pytest.fixture(scope="module")
def owner():
    import app as appmod
    import auth
    from config import Config
    from database import SessionLocal, init_db
    from models import Guild, User, UserGuild
    init_db()
    db = SessionLocal()
    db.add(User(id=OWNER, username="o"))
    db.flush()
    db.add(Guild(id=G, name="W", owner_id=OWNER, plan="free"))
    db.flush()
    db.add(UserGuild(user_id=OWNER, guild_id=G, can_manage=True, is_owner=True))
    db.commit()
    db.close()
    c = appmod.app.test_client()
    c.set_cookie(Config.SESSION_COOKIE_NAME, auth._issue_session(OWNER))
    return c


def test_safe_post_pins_the_validated_address(monkeypatch):
    import urlguard
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert urlguard.resolve_public("https://hook.example/x") == ("hook.example", "93.184.216.34")
    seen = {}

    def fake_real(addr, *a, **k):
        seen["addr"] = addr
        raise OSError("stop")
    monkeypatch.setattr(urlguard, "_real_create_connection", fake_real)
    urlguard._pin.map = {"hook.example": "93.184.216.34"}
    with pytest.raises(OSError):
        urlguard._pinned_create_connection(("hook.example", 443))
    urlguard._pin.map = None
    # a re-resolve by the HTTP client would have been free to pick another address; we never let it
    assert seen["addr"] == ("93.184.216.34", 443)
    # an unpinned host is untouched
    with pytest.raises(OSError):
        urlguard._pinned_create_connection(("other.example", 80))
    assert seen["addr"] == ("other.example", 80)


def test_private_and_mixed_answers_are_refused(monkeypatch):
    import urlguard
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 80))])
    with pytest.raises(ValueError):
        urlguard.safe_post("http://internal.example/")
    # DNS-rebinding style answer: one public AND one private address -> refused
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 80)),
                                                                  (2, 1, 6, "", ("127.0.0.1", 80))])
    assert urlguard.resolve_public("http://rebind.example/") is None


def test_url_and_secret_are_editable_and_test_fire_works(owner, monkeypatch):
    import urlguard
    monkeypatch.setattr(urlguard, "is_public_url", lambda u: "evil" not in u)
    h = owner.post(B + "/outbound-webhooks", json={"url": "https://good.example/a", "events": []}).get_json()["webhook"]
    r = owner.put(B + "/outbound-webhooks/%d" % h["id"], json={"url": "https://good.example/b", "secret": "s3"})
    assert r.status_code == 200 and r.get_json()["webhook"]["url"] == "https://good.example/b"
    assert owner.put(B + "/outbound-webhooks/%d" % h["id"], json={"url": "https://evil.example/x"}).status_code == 400
    assert owner.put(B + "/outbound-webhooks/%d" % h["id"], json={"url": "ftp://x"}).status_code == 400
    sent = {}

    class Resp:
        status_code = 204
    monkeypatch.setattr(urlguard, "safe_post", lambda url, **kw: sent.update(url=url, **kw) or Resp())
    t = owner.post(B + "/outbound-webhooks/%d/test" % h["id"]).get_json()
    assert t["ok"] is True and sent["url"] == "https://good.example/b" and "X-Guildizer-Signature" in sent["headers"]
    monkeypatch.setattr(urlguard, "safe_post", lambda url, **kw: (_ for _ in ()).throw(ValueError("blocked")))
    assert owner.post(B + "/outbound-webhooks/%d/test" % h["id"]).get_json()["error"] == "url_not_public"


def test_mirror_source_must_be_in_this_server_and_rules_are_editable(owner):
    from database import SessionLocal
    from models import Channel, Guild
    db = SessionLocal()
    db.add(Guild(id=G + 1, name="Other", owner_id=None, plan="free"))
    db.flush()
    db.add_all([Channel(id=501, guild_id=G, name="a", type=0), Channel(id=502, guild_id=G, name="b", type=0),
                Channel(id=503, guild_id=G, name="c", type=0), Channel(id=599, guild_id=G + 1, name="secret", type=0)])
    db.commit()
    db.close()
    SessionLocal.remove()
    r = owner.post(B + "/mirrors", json={"source_channel_id": "599", "dest_channel_id": "502"})
    assert r.status_code == 400 and r.get_json()["error"] == "source_not_in_server"      # another server's channel
    m = owner.post(B + "/mirrors", json={"source_channel_id": "501", "dest_channel_id": "502"}).get_json()["mirror"]
    e = owner.put(B + "/mirrors/%d" % m["id"], json={"dest_channel_id": "503"})
    assert e.status_code == 200 and e.get_json()["mirror"]["dest_channel_id"] == "503"
    assert owner.put(B + "/mirrors/%d" % m["id"], json={"source_channel_id": "599"}).status_code == 400
    assert owner.put(B + "/mirrors/%d" % m["id"], json={"source_channel_id": "503"}).status_code == 400   # same as dest


def test_digest_timezone_catch_up_and_send_now(owner):
    from datetime import datetime
    import digest_runtime as dr
    # local time follows the zone; unknown zones fall back to UTC
    utc = datetime(2026, 11, 2, 23, 30)
    assert dr.local_now({"tz": "Asia/Karachi"}, utc).day == 3 and dr.local_now({"tz": "Asia/Karachi"}, utc).hour == 4
    assert dr.local_now({"tz": "Not/AZone"}, utc) == utc
    assert dr.valid_tz("Europe/London") and not dr.valid_tz("nope")
    # monthly: the 1st, or a catch-up inside days 2-3 when this month's digest is outstanding
    cfg = {"cadence": "monthly", "last_day": "2026-10-01"}
    assert dr._cadence_due(cfg, datetime(2026, 11, 1, 9))
    assert dr._cadence_due(cfg, datetime(2026, 11, 3, 9))                       # bot was down on the 1st
    assert not dr._cadence_due(cfg, datetime(2026, 11, 4, 9))                   # too late: skip, don't spam
    assert not dr._cadence_due({"cadence": "monthly", "last_day": "2026-11-01"}, datetime(2026, 11, 3, 9))   # already sent
    assert not dr._cadence_due({"cadence": "monthly"}, datetime(2026, 11, 3, 9))                       # never enabled mid-month
    # weekly: target weekday, or a catch-up when the last send is 8+ days old
    wk = {"cadence": "weekly", "weekday": 0, "last_day": "2026-10-19"}
    assert dr._cadence_due(wk, datetime(2026, 11, 4, 9))                        # a Wednesday, but 16 days since the last one
    assert not dr._cadence_due({**wk, "last_day": "2026-10-30"}, datetime(2026, 11, 4, 9))
    # API: timezone validated, send-now needs a channel then raises the one-shot flag
    assert owner.put(B + "/digest", json={"tz": "nope"}).status_code == 400
    assert owner.put(B + "/digest", json={"tz": "Asia/Karachi"}).get_json()["tz"] == "Asia/Karachi"
    assert owner.post(B + "/digest/send-now").status_code == 400
    owner.put(B + "/digest", json={"channel_id": "123"})
    assert owner.post(B + "/digest/send-now").status_code == 200
    due = dr.due_guilds([G])
    assert due and due[0]["manual"] is True and due[0]["channel_id"] == 123
    dr.mark_posted(G)
    assert dr.due_guilds([G]) == []                                             # one-shot: cleared after posting


def test_analytics_has_moderation_per_day_and_level_distribution(owner):
    import protection
    from database import SessionLocal
    from models import Member
    db = SessionLocal()
    protection.log_event(db, G, "spam", "deleted", user_id=1)
    protection.log_event(db, G, "role_policy", "level_grant", user_id=1)          # not a moderation action
    db.add_all([Member(guild_id=G, user_id=3001, level=2), Member(guild_id=G, user_id=3002, level=7),
                Member(guild_id=G, user_id=3003, level=7), Member(guild_id=G, user_id=3004, level=45)])
    db.commit()
    db.close()
    SessionLocal.remove()
    d = owner.get(B + "/analytics?days=3").get_json()
    assert d["totals"]["mod_actions"] == 1 and d["series"][-1]["mod_actions"] == 1
    dist = {b["label"]: b["members"] for b in d["level_distribution"]}
    assert dist["1-4"] == 1 and dist["5-9"] == 2 and dist["30+"] == 1


def test_escalation_learn_helpers_and_kb_save(owner):
    import escalation_learn as el
    alert = "🚨 **Attention needed**: <@5> in <#7> mentioned \"refund\" — https://discord.com/channels/9890/777/888"
    assert el.parse_jump(alert) == (9890, 777, 888) and el.parse_jump("no link here") is None
    assert el.qa_entry("How do I claim my refund?", "Open a ticket in #support and we will help.")[1].startswith("Q: How do I")
    assert el.qa_entry("hi", "ok") is None                                  # too short to be useful
    assert el.qa_entry("/ban someone please", "that is not how this works") is None   # commands are not questions
    assert el.qa_entry("Where is the roadmap posted?", "https://example.com/x") is None   # a bare link is not an answer
    title, content = el.qa_entry("How do I claim my refund?", "Open a ticket in #support.")
    assert el.save(G, title, content) == "saved"
    assert el.save(G, title.upper(), content) == "duplicate"                # same question, any case
    r = owner.get(B + "/knowledge").get_json()
    assert any(d["title"] == title for d in r.get("documents", r if isinstance(r, list) else []))
    assert owner.put(B + "/moderation", json={"escalation": {"learn_from_replies": True}}).status_code == 200
    assert owner.get(B + "/moderation").get_json()["escalation"]["learn_from_replies"] is True


def test_changing_the_digest_zone_keeps_last_day_consistent(owner):
    import digest_runtime as dr
    d = {"tz": "UTC", "last_posted_utc": "2026-11-02T21:30:00", "last_day": "2026-11-02"}
    d["tz"] = "Asia/Karachi"                 # UTC+5: that same moment is already Nov 3 locally
    dr.rezone_last_day(d)
    assert d["last_day"] == "2026-11-03"
    d2 = {"tz": "UTC", "last_day": "2026-11-02"}
    dr.rezone_last_day(d2)                   # no timestamp (older data): untouched
    assert d2["last_day"] == "2026-11-02"
