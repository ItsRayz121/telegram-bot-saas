"""Continuous raids: a new ORIGINAL tweet from the owner's X account starts a raid by itself.

Rules (agreed with the product owner):
  * The X account is checked at most once every 12 hours. One fetch is shared by every group
    that follows the same handle, so the API cost is ~2 calls a day per account, not per group.
  * One X account per owner.
  * Only original posts: replies, retweets and (by default) quote posts are ignored.
  * The first check only records the newest tweet as a baseline; old tweets are never raided.
  * Pro / Enterprise only (it spends X API credits). Kill switch: RAID_AUTO_ENABLED=0.
  * Safety nets: at most MAX_PER_POLL new raids per check and `max_per_day` per automation per day;
    tweets older than MAX_TWEET_AGE_H are skipped (pinned / stale posts).
Nothing here ever deletes anything; spawned raids are ordinary campaigns the owner can close.
"""
import logging
import os
import random
import re
from collections import defaultdict
from datetime import datetime, timedelta

from .models import db, User, RaidAutomation

logger = logging.getLogger(__name__)

INTERVAL_HOURS = 12
ERROR_RETRY_HOURS = 1            # after a failed fetch (network / 5xx / rate limit)
MAX_TWEET_AGE_H = 36             # 12 h poll + slack; skips pinned / old posts
MAX_PER_POLL = 2
MAX_PER_DAY_DEFAULT = 2
MAX_PER_DAY_LIMIT = 5
MANUAL_CHECK_COOLDOWN_MIN = 60
ENDPOINT = "https://api.twitterapi.io/twitter/user/last_tweets"
GOAL_KEYS = ("likes", "retweets", "comments", "quotes")
ACTION_KEYS = ("like", "retweet", "comment", "quote")
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


class AutoError(Exception):
    """Client-facing validation error (routes turn it into a 400/403)."""

    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def enabled():
    return os.environ.get("RAID_AUTO_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


def normalize_handle(raw):
    from . import twitter_verify
    h = twitter_verify.normalize_handle(raw)
    h = (h or "").strip().lstrip("@")
    return h.lower() if _HANDLE_RE.match(h) else None


# ── template ──────────────────────────────────────────────────────────────────

def _int(v, lo, hi, default=0):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def validate_template(raw):
    """Normalise the owner's raid template. Goals are a fixed number or a {min, max} range
    (a random number in that range is drawn for every raid)."""
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
        "goals": goals,
        "action_xp": xp,
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
    """The concrete targets for ONE raid: a fixed number, or a random pick inside the range."""
    out = {}
    for k, g in (template.get("goals") or {}).items():
        lo, hi = int(g.get("min", 0)), int(g.get("max", 0))
        if hi > 0:
            out[k] = rng.randint(lo, hi) if hi > lo else hi
    return {k: v for k, v in out.items() if v > 0}


# ── tweets ────────────────────────────────────────────────────────────────────

def _tid(t):
    try:
        return int(str(t.get("id") or t.get("id_str") or ""))
    except ValueError:
        return None


def _created(t):
    """The tweet's creation time as naive UTC, or None when it can't be read."""
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
    """True for the account's own new post: not a reply, not a repost, (by default) not a quote."""
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
    """One provider call. -> (status, tweets, error) with status ok | retry | fatal."""
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


# ── per-automation work ───────────────────────────────────────────────────────

def _owner(auto):
    return User.query.get(auto.owner_user_id)


def _is_paid(user):
    from . import engagement as eng
    return eng._is_paid(user)


def _recent_24h(template, now):
    out = []
    for s in template.get("_recent") or []:
        try:
            if datetime.fromisoformat(s) > now - timedelta(hours=24):
                out.append(s)
        except ValueError:
            continue
    return out


def spawn(auto, tweet, now, rng=random):
    """Create + publish ONE raid campaign for a tweet (the normal create path, so posting,
    webhooks and plan rules all apply). Returns the campaign."""
    from . import engagement as eng
    owner = _owner(auto)
    tpl = auto.template or {}
    goals = resolve_goals(tpl, rng)
    xp = {k: v for k, v in (tpl.get("action_xp") or {}).items()}
    data = {
        "title": f"Raid: {_snippet(tweet.get('text'))}"[:200],
        "type": "raid", "platform": "x",
        "task_url": tweet_url(auto.x_handle, _tid(tweet)),
        "status": "active", "one_per_user": True,
        "duration_hours": int(tpl.get("duration_hours") or 24),
        "pin_message": bool(tpl.get("pin_message")),
        "reward_xp": sum(xp.values()),
        "settings": {
            "raid_goals": goals, "action_xp": xp,
            "auto_verify_x": bool(tpl.get("auto_verify_x", True)),
            "auto_raid": auto.id, "tweet_id": str(_tid(tweet)),
        },
    }
    if auto.lineage == "official":
        return eng.create_campaign(owner, data, scope="official", owner_user_id=owner.id,
                                   telegram_group_id=auto.telegram_group_id)
    return eng.create_campaign(owner, data, scope="custom", owner_user_id=owner.id, group_id=auto.group_id)


MIN_GRACE_HOURS = 1     # a raid shortened below the time it has already run ends this long from now


def apply_duration(auto, now=None):
    """Make the saved "raid lasts N hours" apply to this automation's RUNNING raids too: the
    new deadline is each raid's own start + N hours (so 24 h means 24 h from when it began).
    If that moment has already passed the raid ends MIN_GRACE_HOURS from now, so members are
    not cut off mid-action. Goes through the normal campaign edit, so the group post is
    refreshed. Returns how many raids changed."""
    from . import engagement as eng
    from .models import EngagementCampaign
    now = now or datetime.utcnow()
    hours = int((auto.template or {}).get("duration_hours") or 24)
    owner = _owner(auto)
    q = EngagementCampaign.query.filter(EngagementCampaign.status == "active")
    q = (q.filter(EngagementCampaign.telegram_group_id == auto.telegram_group_id) if auto.lineage == "official"
         else q.filter(EngagementCampaign.group_id == auto.group_id))
    changed = 0
    for c in q.all():
        if (c.settings or {}).get("auto_raid") != auto.id:
            continue
        end = (c.starts_at or c.created_at) + timedelta(hours=hours)
        if end <= now:
            end = now + timedelta(hours=MIN_GRACE_HOURS)
        if c.ends_at and abs((c.ends_at - end).total_seconds()) < 60:
            continue
        try:
            eng.update_campaign(c, {"ends_at": end.strftime("%Y-%m-%dT%H:%M:%S")}, user=owner)
            changed += 1
        except Exception:  # noqa: BLE001 - one raid failing must not block the rest
            db.session.rollback()
            logger.info("could not change the deadline of raid %s", c.id, exc_info=True)
    return changed


def _finish(auto, now, *, error=None, hours=INTERVAL_HOURS):
    auto.last_polled_at = now
    auto.next_poll_at = now + timedelta(hours=hours)
    auto.last_error = (error or None) and str(error)[:300]
    db.session.commit()


def process(auto, tweets, now=None, rng=random, spawner=None):
    """Apply one fetched batch to one automation. Returns the number of raids started."""
    now = now or datetime.utcnow()
    spawner = spawner or spawn
    owner = _owner(auto)
    if not owner or not _is_paid(owner):
        _finish(auto, now, error="Continuous raids need a Pro or Enterprise plan.")
        return 0
    ids = [_tid(t) for t in tweets]
    newest = max(ids) if ids else None
    if auto.last_tweet_id is None:
        # First check: remember where we are; never raid the account's old posts.
        if newest:
            auto.last_tweet_id = str(newest)
        _finish(auto, now)
        return 0
    last = int(auto.last_tweet_id)
    tpl = auto.template or {}
    fresh = sorted((t for t in tweets if _tid(t) > last), key=_tid)
    cutoff = now - timedelta(hours=MAX_TWEET_AGE_H)
    candidates = []
    for t in fresh:
        created = _created(t)
        if is_original(t, bool(tpl.get("include_quotes"))) and (created is None or created >= cutoff):
            candidates.append(t)
    recent = _recent_24h(tpl, now)
    room = max(0, int(tpl.get("max_per_day") or MAX_PER_DAY_DEFAULT) - len(recent))
    chosen = candidates[-min(MAX_PER_POLL, room):] if room else []
    started, err = 0, None
    for t in chosen:
        try:
            spawner(auto, t, now, rng)
            started += 1
            recent.append(now.isoformat())
        except Exception as e:  # noqa: BLE001 - a failed raid must not stop the others
            db.session.rollback()
            err = getattr(e, "message", None) or str(e)
            logger.info("raid automation %s could not start a raid: %s", auto.id, err, exc_info=True)
    if newest and newest > last:
        auto.last_tweet_id = str(newest)
    tpl = dict(auto.template or {})
    tpl["_recent"] = recent[-20:]
    auto.template = tpl
    auto.raids_started = (auto.raids_started or 0) + started
    _finish(auto, now, error=err)
    return started


def run_due(now=None, fetcher=fetch_latest, limit=50, rng=random, spawner=None):
    """Poll every due automation. ONE provider call per distinct handle, however many groups
    follow it. Never raises. Returns {"fetched": n, "started": n}."""
    if not enabled():
        return {"fetched": 0, "started": 0}
    now = now or datetime.utcnow()
    from . import twitter_verify
    try:
        due = (RaidAutomation.query
               .filter(RaidAutomation.enabled.is_(True),
                       db.or_(RaidAutomation.next_poll_at.is_(None), RaidAutomation.next_poll_at <= now))
               .order_by(RaidAutomation.next_poll_at.asc()).limit(limit).all())
    except Exception:
        db.session.rollback()
        logger.exception("raid automation query failed")
        return {"fetched": 0, "started": 0}
    groups = defaultdict(list)
    for a in due:
        groups[a.x_handle].append(a)
    fetched = started = 0
    for handle, autos in groups.items():
        try:
            key = twitter_verify._key(autos[0].owner_user_id)
            status, tweets, error = fetcher(handle, key)
            fetched += 1
        except Exception as e:  # noqa: BLE001
            status, tweets, error = "retry", [], str(e)[:150]
        for a in autos:
            try:
                if status == "ok":
                    started += process(a, tweets, now, rng, spawner)
                else:
                    _finish(a, now, error=error, hours=INTERVAL_HOURS if status == "fatal" else ERROR_RETRY_HOURS)
            except Exception:  # noqa: BLE001
                db.session.rollback()
                logger.exception("raid automation %s failed", a.id)
    return {"fetched": fetched, "started": started}


def check_now(auto, now=None, fetcher=fetch_latest, rng=random, spawner=None):
    """Owner pressed "Check now". Allowed once per hour (and not right after a scheduled check),
    so it can never be used to burn API credits."""
    now = now or datetime.utcnow()
    last = max([d for d in (auto.last_checked_manually_at, auto.last_polled_at) if d] or [datetime.min])
    wait = timedelta(minutes=MANUAL_CHECK_COOLDOWN_MIN) - (now - last)
    if wait > timedelta(0):
        raise AutoError(f"Checked recently. You can check again in {int(wait.total_seconds() // 60) + 1} min.", 429)
    from . import twitter_verify
    auto.last_checked_manually_at = now
    status, tweets, error = fetcher(auto.x_handle, twitter_verify._key(auto.owner_user_id))
    if status != "ok":
        _finish(auto, now, error=error, hours=ERROR_RETRY_HOURS)
        return {"status": status, "started": 0, "error": error}
    return {"status": "ok", "started": process(auto, tweets, now, rng, spawner), "error": None}


# ── saving ────────────────────────────────────────────────────────────────────

def upsert(owner, *, lineage, telegram_group_id=None, group_id=None, x_handle, template, enabled_flag=True):
    """Create or update the automation for one group. Pro only; one X account per owner."""
    if not _is_paid(owner):
        raise AutoError("Continuous raids need a Pro or Enterprise plan.", 403, "FEATURE_REQUIRES_PRO")
    handle = normalize_handle(x_handle)
    if not handle:
        raise AutoError("Enter the X username to follow, for example @YourProject.")
    tpl = validate_template(template)
    row = RaidAutomation.query.filter_by(lineage=lineage, telegram_group_id=telegram_group_id,
                                         group_id=group_id).first()
    old_hours = None
    # One X account per owner: other groups of this owner must already follow the same handle.
    # (The automation being edited does not count, so a lone automation can switch account.)
    others = RaidAutomation.query.filter(RaidAutomation.owner_user_id == owner.id,
                                         RaidAutomation.x_handle != handle)
    if row is not None:
        others = others.filter(RaidAutomation.id != row.id)
    other = others.first()
    if other:
        raise AutoError(f"One X account per owner: you already follow @{other.x_handle}. "
                        "Remove those automations first to use another account.", 409)
    if row is None:
        row = RaidAutomation(owner_user_id=owner.id, lineage=lineage, telegram_group_id=telegram_group_id,
                             group_id=group_id, x_handle=handle, template=tpl, enabled=bool(enabled_flag),
                             interval_hours=INTERVAL_HOURS)
        db.session.add(row)
    else:
        if row.owner_user_id != owner.id:
            raise AutoError("Only the group owner can change this.", 403)
        if row.x_handle != handle:
            row.last_tweet_id = None          # a different account: start from a fresh baseline
        old_hours = (row.template or {}).get("duration_hours")
        tpl["_recent"] = (row.template or {}).get("_recent", [])
        row.x_handle, row.template, row.enabled = handle, tpl, bool(enabled_flag)
    if row.next_poll_at is None or row.enabled:
        row.next_poll_at = row.next_poll_at or datetime.utcnow()
    db.session.commit()
    # A changed "raid lasts" also applies to raids that are running right now.
    row.updated_raids = apply_duration(row) if old_hours is not None and old_hours != tpl["duration_hours"] else 0
    return row


def get_for(lineage, telegram_group_id=None, group_id=None):
    return RaidAutomation.query.filter_by(lineage=lineage, telegram_group_id=telegram_group_id, group_id=group_id).first()
