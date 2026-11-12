"""Continuous raids (Guildizer): a new ORIGINAL tweet from the owner's X account starts a raid
in the chosen channel by itself. Same rules as Telegizer's backend/raid_auto.py (logic copied,
not imported):

  * the X account is checked at most once every 12 hours, and one provider call is shared by
    every server that follows the same handle (~2 calls a day per account);
  * one X account per owner (the person who sets it up);
  * original posts only: replies, reposts and (by default) quote posts are ignored;
  * the first check only records a baseline, old tweets are never raided;
  * Pro servers only (it spends X API credits). Kill switch: RAID_AUTO_ENABLED=0;
  * caps: MAX_PER_POLL raids per check, `max_per_day` per server per day, tweets older than
    MAX_TWEET_AGE_H are skipped.
Spawned raids are ordinary campaigns (posted by the bot loop through needs_post).
"""
from __future__ import annotations

import logging
import os
import random
import re
from collections import defaultdict
from datetime import datetime, timedelta

import twitter_verify
from database import SessionLocal
from models import Campaign, Guild, RaidAutomation

log = logging.getLogger(__name__)

INTERVAL_HOURS = 12
ERROR_RETRY_HOURS = 1
MAX_TWEET_AGE_H = 36
MAX_PER_POLL = 2
MAX_PER_DAY_DEFAULT = 2
MAX_PER_DAY_LIMIT = 5
MANUAL_CHECK_COOLDOWN_MIN = 60
ENDPOINT = "https://api.twitterapi.io/twitter/user/last_tweets"
GOAL_KEYS = ("likes", "retweets", "comments", "quotes")
ACTION_KEYS = ("like", "retweet", "comment", "quote")
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


class AutoError(Exception):
    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def enabled() -> bool:
    return os.environ.get("RAID_AUTO_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


def normalize_handle(raw):
    h = (twitter_verify.normalize_handle(raw) or "").strip().lstrip("@")
    return h.lower() if _HANDLE_RE.match(h) else None


def _int(v, lo, hi, default=0):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def validate_template(raw):
    raw = raw if isinstance(raw, dict) else {}
    goals = {}
    for k in GOAL_KEYS:
        g = (raw.get("goals") or {}).get(k)
        if isinstance(g, dict):
            lo, hi = _int(g.get("min"), 0, 1_000_000), _int(g.get("max"), 0, 1_000_000)
            if hi < lo:
                lo, hi = hi, lo
        else:
            lo = hi = _int(g, 0, 1_000_000)
        if hi > 0:
            goals[k] = {"min": lo, "max": hi}
    if not goals:
        raise AutoError("Set a target for at least one action (likes, reposts, comments or quotes).")
    xp = {}
    for k in ACTION_KEYS:
        n = _int((raw.get("action_xp") or {}).get(k), 0, 100_000)
        if n:
            xp[k] = n
    return {
        "goals": goals, "action_xp": xp,
        "duration_hours": _int(raw.get("duration_hours"), 1, 168, 24),
        "pin_message": bool(raw.get("pin_message")),
        "auto_verify_x": bool(raw.get("auto_verify_x", True)),
        "include_quotes": bool(raw.get("include_quotes")),
        "max_per_day": _int(raw.get("max_per_day"), 1, MAX_PER_DAY_LIMIT, MAX_PER_DAY_DEFAULT),
        "_recent": [s for s in (raw.get("_recent") or []) if isinstance(s, str)][-20:],
    }


def public_template(template):
    return {k: v for k, v in (template or {}).items() if not k.startswith("_")}


def resolve_goals(template, rng=random):
    out = {}
    for k, g in (template.get("goals") or {}).items():
        lo, hi = int(g.get("min", 0)), int(g.get("max", 0))
        if hi > 0:
            out[k] = rng.randint(lo, hi) if hi > lo else hi
    return {k: v for k, v in out.items() if v > 0}


def _tid(t):
    try:
        return int(str(t.get("id") or t.get("id_str") or ""))
    except ValueError:
        return None


def _created(t):
    raw = t.get("createdAt") or t.get("created_at")
    if not raw:
        return None
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            d = datetime.strptime(str(raw), fmt)
        except ValueError:
            continue
        return (d - d.utcoffset()).replace(tzinfo=None) if d.tzinfo else d
    return None


def is_original(t, include_quotes=False):
    if t.get("isReply") or t.get("inReplyToId") or t.get("in_reply_to_status_id"):
        return False
    if t.get("retweeted_tweet") or t.get("retweetedTweet") or str(t.get("text") or "").startswith("RT @"):
        return False
    if (t.get("quoted_tweet") or t.get("quotedTweet") or t.get("is_quote_status")) and not include_quotes:
        return False
    return True


def tweet_url(handle, tid):
    return f"https://x.com/{handle}/status/{tid}"


def _snippet(text):
    s = re.sub(r"https?://\S+", "", str(text or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:57] + "...") if len(s) > 60 else (s or "new post")


def fetch_latest(handle, key):
    """One provider call -> (status, tweets, error); status is ok | retry | fatal."""
    import requests
    if not key:
        return "fatal", [], "No twitterapi.io key is configured for this account."
    try:
        resp = requests.get(ENDPOINT, params={"userName": handle}, headers={"X-API-Key": key}, timeout=15)
    except Exception as e:  # noqa: BLE001
        return "retry", [], f"Could not reach X: {str(e)[:120]}"
    if resp.status_code in (401, 402, 403):
        return "fatal", [], f"The X API key was rejected (HTTP {resp.status_code}). Check the key and its credits."
    if resp.status_code != 200:
        return "retry", [], f"The X data provider returned HTTP {resp.status_code}."
    try:
        body = resp.json() or {}
    except ValueError:
        return "retry", [], "The X data provider sent an unreadable answer."
    tweets = body.get("tweets") or (body.get("data") or {}).get("tweets") or []
    return "ok", [t for t in tweets if isinstance(t, dict) and _tid(t)], None


def _recent_24h(template, now):
    out = []
    for s in template.get("_recent") or []:
        try:
            if datetime.fromisoformat(s) > now - timedelta(hours=24):
                out.append(s)
        except ValueError:
            continue
    return out


def spawn(db, auto, tweet, now, rng=random):
    """Create ONE raid campaign for a tweet; the bot loop posts it (needs_post)."""
    tpl = auto.template or {}
    goals = resolve_goals(tpl, rng)
    xp = dict(tpl.get("action_xp") or {})
    c = Campaign(
        guild_id=auto.guild_id, type="raid", platform="x",
        title=f"Raid: {_snippet(tweet.get('text'))}"[:200],
        task_url=tweet_url(auto.x_handle, _tid(tweet)),
        verification_mode="manual", reward_xp=sum(xp.values()), one_per_user=True,
        pin_message=bool(tpl.get("pin_message")), channel_id=auto.channel_id, status="active",
        ends_at=now + timedelta(hours=int(tpl.get("duration_hours") or 24)),
        settings={"raid_goals": goals, "action_xp": xp, "auto_verify_x": bool(tpl.get("auto_verify_x", True)),
                  "auto_raid": auto.id, "tweet_id": str(_tid(tweet))},
    )
    c.needs_post = True
    db.add(c)
    db.flush()
    return c


def _finish(db, auto, now, *, error=None, hours=INTERVAL_HOURS):
    auto.last_polled_at = now
    auto.next_poll_at = now + timedelta(hours=hours)
    auto.last_error = (str(error)[:300] if error else None)
    db.commit()


def process(db, auto, tweets, now=None, rng=random, spawner=None):
    """Apply one fetched batch to one automation. Returns the number of raids started."""
    from sqlalchemy.orm.attributes import flag_modified
    now = now or datetime.utcnow()
    spawner = spawner or spawn
    guild = db.get(Guild, auto.guild_id)
    if guild is None or not guild.is_pro:
        _finish(db, auto, now, error="Continuous raids need a Pro server.")
        return 0
    ids = [_tid(t) for t in tweets]
    newest = max(ids) if ids else None
    if auto.last_tweet_id is None:
        if newest:
            auto.last_tweet_id = str(newest)
        _finish(db, auto, now)
        return 0
    last = int(auto.last_tweet_id)
    tpl = dict(auto.template or {})
    cutoff = now - timedelta(hours=MAX_TWEET_AGE_H)
    candidates = []
    for t in sorted((t for t in tweets if _tid(t) > last), key=_tid):
        created = _created(t)
        if is_original(t, bool(tpl.get("include_quotes"))) and (created is None or created >= cutoff):
            candidates.append(t)
    recent = _recent_24h(tpl, now)
    room = max(0, int(tpl.get("max_per_day") or MAX_PER_DAY_DEFAULT) - len(recent))
    chosen = candidates[-min(MAX_PER_POLL, room):] if room else []
    started, err = 0, None
    for t in chosen:
        try:
            spawner(db, auto, t, now, rng)
            db.commit()
            started += 1
            recent.append(now.isoformat())
        except Exception as e:  # noqa: BLE001
            db.rollback()
            err = getattr(e, "message", None) or str(e)
            log.info("raid automation %s could not start a raid: %s", auto.id, err, exc_info=True)
    if newest and newest > last:
        auto.last_tweet_id = str(newest)
    tpl["_recent"] = recent[-20:]
    auto.template = tpl
    flag_modified(auto, "template")
    auto.raids_started = (auto.raids_started or 0) + started
    _finish(db, auto, now, error=err)
    return started


def run_due(now=None, fetcher=fetch_latest, limit=50, rng=random, spawner=None):
    """Poll every due automation: ONE provider call per distinct handle. Never raises."""
    if not enabled():
        return {"fetched": 0, "started": 0}
    now = now or datetime.utcnow()
    db = SessionLocal()
    fetched = started = 0
    try:
        due = (db.query(RaidAutomation)
               .filter(RaidAutomation.enabled.is_(True),
                       (RaidAutomation.next_poll_at.is_(None)) | (RaidAutomation.next_poll_at <= now))
               .order_by(RaidAutomation.next_poll_at.asc()).limit(limit).all())
        groups = defaultdict(list)
        for a in due:
            groups[a.x_handle].append(a)
        for handle, autos in groups.items():
            try:
                guild = db.get(Guild, autos[0].guild_id)
                key = twitter_verify._key(guild.owner_id if guild else None)
                status, tweets, error = fetcher(handle, key)
                fetched += 1
            except Exception as e:  # noqa: BLE001
                status, tweets, error = "retry", [], str(e)[:150]
            for a in autos:
                try:
                    if status == "ok":
                        started += process(db, a, tweets, now, rng, spawner)
                    else:
                        _finish(db, a, now, error=error, hours=INTERVAL_HOURS if status == "fatal" else ERROR_RETRY_HOURS)
                except Exception:  # noqa: BLE001
                    db.rollback()
                    log.exception("raid automation %s failed", a.id)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("raid automation run failed")
    finally:
        db.close()
        SessionLocal.remove()
    return {"fetched": fetched, "started": started}


def check_now(db, auto, now=None, fetcher=fetch_latest, rng=random, spawner=None):
    """Owner pressed "Check now": at most once an hour, so it can never burn API credits."""
    now = now or datetime.utcnow()
    last = max([d for d in (auto.last_checked_manually_at, auto.last_polled_at) if d] or [datetime.min])
    wait = timedelta(minutes=MANUAL_CHECK_COOLDOWN_MIN) - (now - last)
    if wait > timedelta(0):
        raise AutoError(f"Checked recently. You can check again in {int(wait.total_seconds() // 60) + 1} min.", 429)
    guild = db.get(Guild, auto.guild_id)
    auto.last_checked_manually_at = now
    status, tweets, error = fetcher(auto.x_handle, twitter_verify._key(guild.owner_id if guild else None))
    if status != "ok":
        _finish(db, auto, now, error=error, hours=ERROR_RETRY_HOURS)
        return {"status": status, "started": 0, "error": error}
    return {"status": "ok", "started": process(db, auto, tweets, now, rng, spawner), "error": None}


def upsert(db, guild, user_id, *, channel_id, x_handle, template, enabled_flag=True):
    """Create or update this server's automation. Pro only; one X account per person."""
    if not guild.is_pro:
        raise AutoError("Continuous raids need a Pro server.", 403, "FEATURE_REQUIRES_PRO")
    handle = normalize_handle(x_handle)
    if not handle:
        raise AutoError("Enter the X username to follow, for example @YourProject.")
    if not str(channel_id or "").isdigit():
        raise AutoError("Choose the channel where the raids should be posted.")
    tpl = validate_template(template)
    row = db.query(RaidAutomation).filter(RaidAutomation.guild_id == guild.id).first()
    others = db.query(RaidAutomation).filter(RaidAutomation.user_id == user_id, RaidAutomation.x_handle != handle)
    if row is not None:
        others = others.filter(RaidAutomation.id != row.id)
    other = others.first()
    if other:
        raise AutoError(f"One X account per owner: you already follow @{other.x_handle}. "
                        "Remove those automations first to use another account.", 409)
    if row is None:
        row = RaidAutomation(guild_id=guild.id, user_id=user_id, channel_id=int(channel_id), x_handle=handle,
                             template=tpl, enabled=bool(enabled_flag))
        db.add(row)
    else:
        if row.x_handle != handle:
            row.last_tweet_id = None
        tpl["_recent"] = (row.template or {}).get("_recent", [])
        row.user_id, row.channel_id, row.x_handle = user_id, int(channel_id), handle
        row.template, row.enabled = tpl, bool(enabled_flag)
    row.next_poll_at = row.next_poll_at or datetime.utcnow()
    db.commit()
    return row


def to_dict(row):
    iso = lambda d: d.isoformat() + "Z" if d else None
    return {
        "id": row.id, "enabled": bool(row.enabled), "x_handle": row.x_handle, "channel_id": str(row.channel_id),
        "template": public_template(row.template), "interval_hours": INTERVAL_HOURS,
        "last_tweet_id": row.last_tweet_id, "last_polled_at": iso(row.last_polled_at),
        "next_poll_at": iso(row.next_poll_at), "last_error": row.last_error, "raids_started": row.raids_started or 0,
    }
