"""Campaign DB helpers used by the bot (no discord.py here).

Covers posting coordination (needs_post / needs_unpost flags), proof-submission
creation with one-per-user + participant caps + honor auto-verify, the per-action
X verify flow (Telegizer's Engagement V3), and the data the announcement embed
needs.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta

from sqlalchemy.orm.attributes import flag_modified

import campaign_rewards
import social_handles
import leveling
import twitter_verify
from database import SessionLocal
from models import (
    Campaign,
    CampaignCustomField,
    CampaignSubmission,
    CampaignTask,
    Guild,
)

log = logging.getLogger(__name__)


# ── Per-action verify flow (Telegizer Engagement V3 parity) ───────────────────
# Campaign goal-key (plural) → twitter_verify canonical action (singular).
GOAL_ACTIONS = [
    ("likes", "like"), ("retweets", "retweet"), ("comments", "comment"),
    ("quotes", "quote"), ("follows", "follow"),
]
GOAL_TO_ACTION = dict(GOAL_ACTIONS)
ACTION_TO_GOAL = {a: g for g, a in GOAL_ACTIONS}
# X has no likers endpoint, so a like can never be proven by the API. Instead of
# blindly accepting we gate on behaviour: the member must OPEN the post (which
# stamps opened_at) and let it soak before Verify will accept it.
AUTO_ACCEPT_ACTIONS = {"like"}
ACTION_RETRY_COOLDOWN_DEFAULT = 30   # seconds between verify attempts per action
LIKE_SOAK_SECONDS = 30               # seconds after opening before a like counts

# Proof field types whose values must be unique across participants.
_DEDUP_FIELD_TYPES = {"uid", "wallet", "tx_hash", "username", "url"}


def _settings(c: Campaign) -> dict:
    return c.settings or {}


def campaign_action_goals(c: Campaign) -> list[tuple[str, str, int]]:
    """Ordered [(goal_key, action, target)] for the actions this campaign targets,
    reading raid_goals (raid) or social_targets (social_task)."""
    s = _settings(c)
    goals = s.get("raid_goals") if c.type == "raid" else s.get("social_targets")
    goals = goals or {}
    return [(gk, act, goals[gk]) for gk, act in GOAL_ACTIONS if goals.get(gk)]


def has_action_flow(c: Campaign) -> bool:
    """True if this campaign uses the per-action verify flow (an X raid, or an X
    social-task that targets at least one action)."""
    if c.type == "raid":
        return bool(campaign_action_goals(c))
    if c.type == "social_task":
        if (c.platform or "").lower() not in ("x", "twitter"):
            return False
        return bool(campaign_action_goals(c))
    return False


def _live_verify_allowed(db, c: Campaign) -> tuple[bool, int | None]:
    """(can we check X live?, owner_user_id) — Pro + auto_verify_x + a usable key."""
    try:
        guild = db.get(Guild, c.guild_id)
        if guild is None or not guild.is_pro:
            return False, None
        owner_id = guild.owner_id
        if not _settings(c).get("auto_verify_x"):
            return False, owner_id
        return bool(twitter_verify.enabled(owner_id)), owner_id
    except Exception:
        return False, None


def campaigns_to_post() -> list[tuple[int, int]]:
    """(campaign_id, guild_id) pairs so each bot identity posts only for the
    guilds it serves (official bot vs white-label custom bots)."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Campaign)
            .filter(Campaign.needs_post.is_(True), Campaign.status == "active")
            .all()
        )
        return [(c.id, c.guild_id) for c in rows]
    finally:
        db.close()
        SessionLocal.remove()


def campaigns_to_close() -> list[tuple[int, int]]:
    """Campaigns whose announcement must be switched to its "ended" form: active ones whose
    deadline has passed, and closed ones (ended or closed by hand) whose post was not updated yet."""
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        out = []
        for c in (db.query(Campaign)
                  .filter(Campaign.post_status == "posted", Campaign.message_id.isnot(None),
                          Campaign.status.in_(("active", "closed"))).all()):
            expired = c.status == "active" and c.ends_at is not None and c.ends_at <= now
            # Closed by hand (or ended) but the post was never updated. Only recent posts: this
            # must not sweep through every old campaign and edit months-old messages.
            recent = c.posted_at is not None and c.posted_at >= now - timedelta(days=14)
            unmarked = c.status == "closed" and recent and not (c.settings or {}).get("_post_closed")
            if expired or unmarked:
                out.append((c.id, c.guild_id))
        return out
    finally:
        db.close()
        SessionLocal.remove()


def mark_closed(cid: int, *, flag_post: bool = False) -> None:
    """Close an expired campaign (as Telegizer's lifecycle job does); optionally remember that
    its announcement now shows the ended form."""
    from sqlalchemy.orm.attributes import flag_modified
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is not None:
            if c.status == "active" and c.ends_at is not None and c.ends_at <= datetime.utcnow():
                c.status = "closed"
            if flag_post:
                c.settings = {**(c.settings or {}), "_post_closed": True}
                flag_modified(c, "settings")
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def my_submissions(cid: int, user_id: int) -> dict | None:
    """What this member has done in a campaign, for the "My submission" button. Works while the
    campaign is running and after it ended. {title, open, lines: [..]}"""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None:
            return None
        subs = (db.query(CampaignSubmission)
                .filter(CampaignSubmission.campaign_id == cid, CampaignSubmission.user_id == user_id)
                .order_by(CampaignSubmission.id.asc()).all())
        latest = {}
        for s in subs:
            latest[s.task_id] = s          # the newest submission per task wins

        def line(label, s):
            if s is None:
                return f"⬜ {label}: not done"
            if s.status == "verified":
                return f"✅ {label}: verified" + (f" (+{s.reward_granted} XP)" if s.reward_granted else "")
            if s.status == "rejected":
                return f"❌ {label}: rejected" + (f" - {s.review_reason}" if getattr(s, "review_reason", None) else "")
            return f"🕓 {label}: waiting for review"
        tasks = sorted(c.tasks, key=lambda t: t.order)
        if tasks:
            lines = [line(t.title[:60], latest.get(t.id)) for t in tasks]
        elif has_action_flow(c):
            acts = (((latest.get(None).proof or {}).get("actions")) if latest.get(None) else None) or {}
            lines = [line("Raid", latest.get(None))]
            for _gk, act, _t in campaign_action_goals(c):
                st = (acts.get(act) or {}).get("status")
                lines.append(f"   {'✅' if st == 'verified' else '🕓' if st == 'manual' else '❌' if st == 'failed' else '⬜'} {act.title()}")
        else:
            lines = [line("Your submission", latest.get(None))]
        return {"title": c.title, "open": c.is_open, "lines": lines}
    finally:
        db.close()
        SessionLocal.remove()


def campaigns_to_unpost() -> list[tuple[int, int]]:
    """Campaigns whose channel announcement the dashboard asked us to delete."""
    db = SessionLocal()
    try:
        rows = db.query(Campaign).filter(Campaign.needs_unpost.is_(True)).all()
        return [(c.id, c.guild_id) for c in rows]
    finally:
        db.close()
        SessionLocal.remove()


def load_for_post(cid: int) -> dict | None:
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None:
            return None
        goals = campaign_action_goals(c)
        return {
            "id": c.id,
            "guild_id": c.guild_id,
            "title": c.title,
            "description": c.description or "",
            "type": c.type,
            "platform": c.platform,
            "task_url": c.task_url,
            "raid_goals": _settings(c).get("raid_goals") or {},
            "social_targets": _settings(c).get("social_targets") or {},
            "show_targets": bool(_settings(c).get("show_targets")),
            "auto_verify_x": bool(_settings(c).get("auto_verify_x")),
            "action_goals": [list(t) for t in goals],
            "has_action_flow": has_action_flow(c),
            "reward_xp": campaign_rewards.effective_reward(c),
            "action_xp": campaign_rewards.action_xp_map(c),
            "reward_label": c.reward_label,
            "verification_mode": c.verification_mode,
            "is_open": c.is_open,
            "ends_at": c.ends_at,
            "pin_message": bool(c.pin_message),
            "channel_id": c.channel_id,
            "message_id": c.message_id,
            "posted_channel_id": c.posted_channel_id or c.channel_id,
            "proof_summary": _proof_summary(c),
            "progress": _action_progress(db, c) if goals else {},
            "tasks": [
                {"id": t.id, "title": t.title, "description": t.description or "",
                 "task_url": t.task_url, "reward_xp": t.reward_xp or 0,
                 "verification_mode": t.verification_mode, "platform": t.platform,
                 "type": t.type, "settings": t.settings or {}}
                for t in sorted(c.tasks, key=lambda x: x.order)
            ],
        }
    finally:
        db.close()
        SessionLocal.remove()


# One-line description of what a member submits, mirroring the bot's actual ask.
_PROOF_PHRASE = {
    "url": "a link", "screenshot": "a screenshot", "uid": "your UID",
    "wallet": "your wallet address", "tx_hash": "a transaction hash",
    "username": "your username", "text": "a short answer",
}


def _proof_summary(c: Campaign) -> str:
    """What the announcement should say members submit. Empty when there is
    nothing to submit up front (one-tap honor/auto, the per-action X flow) or
    when the campaign lists its own tasks."""
    if c.tasks:
        return ""
    if has_action_flow(c):
        return ""
    fields = [f for f in c.custom_fields if f.task_id is None]
    if fields:
        seen: list[str] = []
        for f in fields:
            phrase = _PROOF_PHRASE.get(f.field_type or "text", "a short answer")
            if phrase not in seen:
                seen.append(phrase)
        return ", ".join(seen)
    # No configured fields → mirror the bot's default proof prompt.
    if c.verification_mode in ("honor", "auto"):
        return ""
    return "a link" if c.verification_mode == "link" else "a screenshot"


def _action_progress(db, c: Campaign) -> dict:
    """{goal_key: verified_count} so the post can show a live quota countdown."""
    subs = (
        db.query(CampaignSubmission)
        .filter(CampaignSubmission.campaign_id == c.id)
        .all()
    )
    out: dict[str, int] = {}
    for gk, act, _tgt in campaign_action_goals(c):
        n = 0
        for s in subs:
            rec = ((s.proof or {}).get("actions") or {}).get(act) or {}
            if rec.get("status") == "verified":
                n += 1
        out[gk] = n
    return out


def mark_posted(cid: int, message_id: int) -> None:
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is not None:
            c.message_id = message_id
            c.posted_channel_id = c.channel_id
            c.post_status = "posted"
            c.post_error = None
            c.needs_post = False
            c.posted_at = datetime.utcnow()
            if (c.settings or {}).get("_post_closed"):       # a fresh live post replaces the ended one
                c.settings = {k: v for k, v in c.settings.items() if k != "_post_closed"}
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(c, "settings")
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def mark_post_failed(cid: int, error: str) -> None:
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is not None:
            c.post_status = "failed"
            c.post_error = (error or "")[:255]
            c.needs_post = False
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


def unpost_target(cid: int) -> tuple[int, int] | None:
    """(channel_id, message_id) of the announcement to delete, or None. Uses the
    channel the message was POSTED in, which may no longer be the announce channel."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.message_id:
            return None
        channel_id = c.posted_channel_id or c.channel_id
        if not channel_id:
            return None
        return (int(channel_id), int(c.message_id))
    finally:
        db.close()
        SessionLocal.remove()


def mark_unposted(cid: int, error: str | None = None) -> None:
    """Clear the post pointer after the bot deleted (or failed to delete) it."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is not None:
            c.needs_unpost = False
            if error:
                c.post_status = "failed"
                c.post_error = (error or "")[:255]
            else:
                c.message_id = None
                c.posted_channel_id = None
                c.posted_at = None
                c.post_status = "none"
                c.post_error = None
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


# ── Review-outcome DM outbox ─────────────────────────────────────────────────
def submissions_to_notify(limit: int = 25) -> list[dict]:
    """Reviewed submissions whose outcome hasn't reached the member yet. The web
    process has no gateway connection, so it queues and the bot delivers."""
    db = SessionLocal()
    try:
        rows = (
            db.query(CampaignSubmission)
            .filter(CampaignSubmission.notify_status == "pending")
            .order_by(CampaignSubmission.reviewed_at)
            .limit(limit)
            .all()
        )
        out = []
        for s in rows:
            c = db.get(Campaign, s.campaign_id)
            if c is None:
                continue
            out.append({
                "id": s.id, "guild_id": c.guild_id, "user_id": s.user_id,
                "status": s.status, "reason": s.review_reason,
                "title": c.title, "reward": s.reward_granted or 0,
                "allow_resubmit": bool(_settings(c).get("allow_resubmit")),
            })
        return out
    finally:
        db.close()
        SessionLocal.remove()


def mark_notified(sid: int, ok: bool, error: str | None = None) -> None:
    db = SessionLocal()
    try:
        s = db.get(CampaignSubmission, sid)
        if s is not None:
            s.notify_status = "sent" if ok else "failed"
            s.notify_error = (error or "")[:255] or None
        db.commit()
    finally:
        db.close()
        SessionLocal.remove()


# ── Proof submission ─────────────────────────────────────────────────────────
def _fields_for(db, cid: int, tid: int | None) -> list[CampaignCustomField]:
    """Task-level fields when submitting for a task, else campaign-level ones."""
    q = db.query(CampaignCustomField).filter(CampaignCustomField.campaign_id == cid)
    q = q.filter(CampaignCustomField.task_id == tid) if tid else q.filter(
        CampaignCustomField.task_id.is_(None))
    return q.order_by(CampaignCustomField.position).limit(4).all()


def _participants_full(db, c: Campaign) -> bool:
    """True once max_participants distinct members hold a non-rejected submission."""
    if not c.max_participants:
        return False
    n = (
        db.query(CampaignSubmission.user_id)
        .filter(CampaignSubmission.campaign_id == c.id,
                CampaignSubmission.status != "rejected")
        .distinct()
        .count()
    )
    return n >= c.max_participants


def submit_context(cid: int, tid: int) -> dict | None:
    """What the proof button needs to decide: open? honor or modal? title?"""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.is_open:
            return None
        fields = [f.to_dict() for f in _fields_for(db, cid, tid or None)]
        auto_verify_x = bool(_settings(c).get("auto_verify_x"))
        if tid:
            t = db.get(CampaignTask, tid)
            if t is None or t.campaign_id != cid:
                return None
            return {"verification_mode": t.verification_mode, "title": t.title, "fields": fields,
                    "type": c.type, "auto_verify_x": auto_verify_x,
                    "panel": task_panel_kind(db, c, t), "task_url": t.task_url or c.task_url,
                    "full": _participants_full(db, c)}
        return {"verification_mode": c.verification_mode, "title": c.title, "fields": fields,
                "type": c.type, "auto_verify_x": auto_verify_x,
                "full": _participants_full(db, c)}
    finally:
        db.close()
        SessionLocal.remove()


def _detect_duplicate(db, c: Campaign, answers: dict) -> tuple[bool, str | None]:
    """Has another participant in this guild already used one of these proof
    values? Anti-farming guard — flags for review, never auto-rejects."""
    if not answers:
        return False, None
    fields = {
        (f.key or f.label): f
        for f in db.query(CampaignCustomField)
        .filter(CampaignCustomField.campaign_id == c.id).all()
    }
    values = {
        str(v).strip().lower()
        for k, v in answers.items()
        if str(v or "").strip()
        and k in fields and (fields[k].field_type or "text") in _DEDUP_FIELD_TYPES
    }
    if not values:
        return False, None
    sibling_ids = [
        row[0] for row in db.query(Campaign.id).filter(Campaign.guild_id == c.guild_id).all()
    ]
    if not sibling_ids:
        return False, None
    rows = (
        db.query(CampaignSubmission)
        .filter(CampaignSubmission.campaign_id.in_(sibling_ids))
        .all()
    )
    for s in rows:
        existing = {
            str(v).strip().lower()
            for v in ((s.proof or {}).get("fields") or {}).values()
            if str(v or "").strip()
        }
        if values & existing:
            return True, "Duplicate proof value already submitted"
    return False, None


def create_submission(cid: int, tid: int, user_id: int, username: str, value: str | None,
                      extra_fields: dict | None = None, file_url: str | None = None,
                      force_verified: bool = False):
    """Create a proof submission. Returns (status, reward):
       verified | pending | duplicate | closed | full."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.is_open:
            return ("closed", 0)
        task = None
        if tid:
            task = db.get(CampaignTask, tid)
            if task is None or task.campaign_id != cid:
                return ("closed", 0)

        vmode = task.verification_mode if task else c.verification_mode
        reward = (task.reward_xp if task else c.reward_xp) or 0
        task_key = tid or None

        if c.one_per_user:
            existing = (
                db.query(CampaignSubmission)
                .filter(
                    CampaignSubmission.campaign_id == cid,
                    CampaignSubmission.task_id.is_(task_key) if task_key is None
                    else CampaignSubmission.task_id == task_key,
                    CampaignSubmission.user_id == user_id,
                    CampaignSubmission.status != "rejected",
                )
                .first()
            )
            if existing is not None:
                return ("duplicate", 0)

        # Participant cap. Checked after one-per-user so a returning member gets
        # the clearer "already submitted" message, and only blocks NEW members.
        if _participants_full(db, c):
            already = (
                db.query(CampaignSubmission)
                .filter(CampaignSubmission.campaign_id == cid,
                        CampaignSubmission.user_id == user_id,
                        CampaignSubmission.status != "rejected")
                .first()
            )
            if already is None:
                return ("full", 0)

        proof = {"value": value} if value else {}
        if extra_fields:
            proof["fields"] = {str(k)[:64]: str(v)[:300] for k, v in extra_fields.items()}
        if value:
            # annotate (never auto-reject): does the first proof URL resolve?
            import link_checks
            verdict = link_checks.check_proof_text(value)
            if verdict is not None:
                proof["link_check"] = verdict
        sub = CampaignSubmission(
            campaign_id=cid, task_id=task_key, user_id=user_id,
            username=(username or "")[:120], proof=proof, file_url=file_url,
        )
        is_dup, dup_reason = _detect_duplicate(db, c, proof.get("fields") or {})
        if is_dup:
            sub.flagged = True
            sub.flag_reason = dup_reason

        # honor is a one-tap accept; 'auto' verifies server membership, and a
        # member who can click the button in the guild's channel IS a member — so
        # both auto-verify on submission (mirrors Telegizer's Telegram-join 'auto').
        if vmode in ("honor", "auto") or force_verified:
            sub.status = "verified"
            sub.reviewed_at = datetime.utcnow()
            if campaign_rewards.per_action_applies(c, sub):
                reward = campaign_rewards.pay_action_xp(db, c, sub, user_id, username, assume_all=True)
            else:
                sub.reward_granted = reward
                if reward > 0:
                    leveling.add_xp(db, c.guild_id, user_id, reward, username, reason=f"campaign:{cid}")
            db.add(sub)
            db.commit()
            return ("verified", reward)

        # Twitter Raid X auto-verify (Pro): try to confirm the participant's actions
        # live before falling back to manual review. Purely additive — any
        # uncertainty/error leaves the submission pending (never auto-rejects).
        if c.type == "raid" and _settings(c).get("auto_verify_x"):
            if _raid_autoverifies(db, c, value, extra_fields, user_id):
                sub.status = "verified"
                sub.reviewed_at = datetime.utcnow()
                if campaign_rewards.per_action_applies(c, sub):
                    reward = campaign_rewards.pay_action_xp(db, c, sub, user_id, username, assume_all=True)
                else:
                    sub.reward_granted = reward
                    if reward > 0:
                        leveling.add_xp(db, c.guild_id, user_id, reward, username, reason=f"campaign:{cid}")
                db.add(sub)
                db.commit()
                return ("verified", reward)

        # Same upgrade-only X check for one TASK of a multi-task campaign that has
        # "Auto-verify on X" on. Kill switch: TASK_X_AUTOVERIFY_ENABLED=0.
        if task is not None and _task_autoverifies(db, c, task, value, extra_fields, user_id):
            sub.status = "verified"
            sub.reviewed_at = datetime.utcnow()
            sub.reward_granted = reward
            if reward > 0:
                leveling.add_xp(db, c.guild_id, user_id, reward, username, reason=f"campaign:{cid}")
            db.add(sub)
            db.commit()
            return ("verified", reward)

        sub.status = "pending"
        db.add(sub)
        db.commit()
        return ("pending", 0)
    finally:
        db.close()
        SessionLocal.remove()


def attach_screenshot(cid: int, user_id: int, url: str) -> bool:
    """Attach the Discord CDN url of an uploaded screenshot to the member's most
    recent submission for this campaign. Discord modals can't take files, so the
    bot collects the image in a follow-up message and calls this."""
    db = SessionLocal()
    try:
        sub = (
            db.query(CampaignSubmission)
            .filter(CampaignSubmission.campaign_id == cid,
                    CampaignSubmission.user_id == user_id)
            .order_by(CampaignSubmission.id.desc())
            .first()
        )
        if sub is None:
            return False
        sub.file_url = (url or "")[:500] or None
        db.commit()
        return True
    finally:
        db.close()
        SessionLocal.remove()


# ── Per-action panel ─────────────────────────────────────────────────────────
def action_context(cid: int) -> dict | None:
    """What the ephemeral action panel needs: title, targeted actions, tweet url,
    extra proof fields. None if the campaign is gone, closed, or not action-driven."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.is_open or not has_action_flow(c):
            return None
        return {
            "title": c.title,
            "type": c.type,
            "task_url": c.task_url,
            "actions": [act for _gk, act, _t in campaign_action_goals(c)],
            "auto_verify_x": bool(_settings(c).get("auto_verify_x")),
            "fields": [f.to_dict() for f in _fields_for(db, cid, None)],
            "full": _participants_full(db, c),
        }
    finally:
        db.close()
        SessionLocal.remove()


def raid_context(cid: int) -> dict | None:
    """Legacy shape kept for the older raid panel entry point."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.is_open:
            return None
        return {
            "title": c.title,
            "goals": _settings(c).get("raid_goals") or {},
            "auto_verify_x": bool(_settings(c).get("auto_verify_x")),
            "type": c.type,
        }
    finally:
        db.close()
        SessionLocal.remove()


def _action_submission(db, c: Campaign, user_id: int, username: str | None = None,
                       create: bool = False):
    """The single (campaign, user) submission holding the per-action map. The
    action flow is campaign-level, so task_id is always NULL here."""
    sub = (
        db.query(CampaignSubmission)
        .filter(CampaignSubmission.campaign_id == c.id,
                CampaignSubmission.task_id.is_(None),
                CampaignSubmission.user_id == user_id)
        .order_by(CampaignSubmission.id.desc())
        .first()
    )
    if sub is not None or not create:
        return sub
    sub = CampaignSubmission(
        campaign_id=c.id, task_id=None, user_id=user_id,
        username=(username or "")[:120], status="pending", proof={"actions": {}},
    )
    db.add(sub)
    db.commit()
    return sub


def action_status_map(cid: int, user_id: int) -> dict:
    """{action: status} for this user's submission, or {} if none yet."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None:
            return {}
        sub = _action_submission(db, c, user_id)
        if sub is None:
            return {}
        return {a: (v or {}).get("status")
                for a, v in ((sub.proof or {}).get("actions") or {}).items()}
    finally:
        db.close()
        SessionLocal.remove()


def action_retry_remaining(cid: int, user_id: int, action: str) -> int:
    """Seconds left in the golden-period cooldown for this action, else 0."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None:
            return 0
        sub = _action_submission(db, c, user_id)
        if sub is None:
            return 0
        rec = ((sub.proof or {}).get("actions") or {}).get(action) or {}
        last = rec.get("last_attempt")
        if not last:
            return 0
        cooldown = int(_settings(c).get("action_retry_cooldown", ACTION_RETRY_COOLDOWN_DEFAULT))
        try:
            elapsed = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
        except (TypeError, ValueError):
            return 0
        return max(0, int(cooldown - elapsed))
    finally:
        db.close()
        SessionLocal.remove()


def record_action_open(cid: int, user_id: int, username: str, action: str) -> str | None:
    """Record that the participant OPENED the post for `action`. Stamps opened_at
    once so the like soak-gate measures from the first real open. Idempotent."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.is_open:
            return None
        sub = _action_submission(db, c, user_id, username, create=True)
        proof = dict(sub.proof or {})
        actions = dict(proof.get("actions") or {})
        rec = dict(actions.get(action) or {})
        if not rec.get("opened_at"):
            rec["opened_at"] = datetime.utcnow().isoformat()
            actions[action] = rec
            proof["actions"] = actions
            sub.proof = proof
            sub.username = username or sub.username
            flag_modified(sub, "proof")
            db.commit()
        return rec["opened_at"]
    finally:
        db.close()
        SessionLocal.remove()


def verify_user_action(cid: int, user_id: int, username: str, action: str, handle: str | None):
    """Run/record one action verify for a participant.

    Returns {status, detail, completed, all_submitted} where status ∈
    {verified, failed, manual, cooldown, need_open, closed}.

    - like (and any AUTO_ACCEPT action) can't be API-checked, so we gate on real
      behaviour: the member must have OPENED the post and let it soak.
    - retweet/comment/quote/follow → live twitterapi.io check for Pro owners with
      auto-verify on; otherwise recorded "manual" for admin review.
    `completed` is True when this tap completed every targeted action.
    """
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.is_open:
            return {"status": "closed", "detail": "This campaign is closed.",
                    "completed": False, "all_submitted": False}
        sub = _action_submission(db, c, user_id, username, create=True)
        proof = dict(sub.proof or {})
        actions = dict(proof.get("actions") or {})
        rec = dict(actions.get(action) or {})
        now_iso = datetime.utcnow().isoformat()

        if action in AUTO_ACCEPT_ACTIONS:
            # Behavioural anti-fraud gate (no API can prove a like — X privatised them).
            opened = rec.get("opened_at")
            if not opened:
                return {"status": "need_open", "completed": False, "all_submitted": False,
                        "detail": "Tap the ❤️ Like button to open the post and like it "
                                  "first, then come back and tap Verify."}
            soak = int(_settings(c).get("like_soak_seconds", LIKE_SOAK_SECONDS))
            try:
                elapsed = (datetime.utcnow() - datetime.fromisoformat(opened)).total_seconds()
            except (TypeError, ValueError):
                elapsed = soak   # unparseable timestamp → don't trap the user forever
            if elapsed < soak:
                wait = max(1, int(soak - elapsed))
                return {"status": "cooldown", "completed": False, "all_submitted": False,
                        "wait": wait, "detail": f"Like the post, then tap Verify in {wait}s."}
            status, detail = "verified", "Accepted (post opened & liked)"
        else:
            # Stamp the attempt so the golden-period cooldown counts from each try.
            rec["last_attempt"] = now_iso
            live, owner_id = _live_verify_allowed(db, c)
            if not live:
                status, detail = "manual", "Submitted for manual review"
            elif not handle:
                status, detail = "manual", "No X username provided — sent for review"
            else:
                try:
                    tweet_id = twitter_verify.extract_tweet_id(c.task_url)
                    target = (_settings(c).get("raid_follow_target")
                              or twitter_verify.extract_author_handle(c.task_url))
                    vstatus, vdetail = twitter_verify.verify_action(
                        action, username=handle, tweet_id=tweet_id, target_handle=target,
                        key=twitter_verify._key(owner_id),
                    )
                    if vstatus == "verified":
                        status, detail = "verified", vdetail or "Verified on X"
                    elif vstatus == "failed":
                        status, detail = "failed", vdetail or "Not detected on X"
                    else:  # unknown / manual → couldn't confirm; let them retry
                        status, detail = "failed", "Couldn't detect it yet — try again shortly"
                except Exception:
                    status, detail = "failed", "Verification error — try again shortly"

        rec["status"] = status
        actions[action] = rec
        proof["actions"] = actions
        if handle:
            proof["x_handle"] = str(handle)[:120]
        sub.proof = proof
        sub.username = username or sub.username
        flag_modified(sub, "proof")

        # Completed when every targeted action is verified OR accepted-for-manual.
        targeted = [act for _gk, act, _t in campaign_action_goals(c)]
        done = all((actions.get(a) or {}).get("status") in ("verified", "manual") for a in targeted)
        all_verified = all((actions.get(a) or {}).get("status") == "verified" for a in targeted)
        reward = campaign_rewards.effective_reward(c)
        per_action = campaign_rewards.per_action_applies(c, sub)
        completed = False
        if done and all_verified:
            if sub.status != "verified":
                sub.status = "verified"
                sub.reviewed_at = datetime.utcnow()
                if per_action:
                    reward = campaign_rewards.pay_action_xp(db, c, sub, user_id, username)
                else:
                    sub.reward_granted = reward
                    if reward > 0:
                        leveling.add_xp(db, c.guild_id, user_id, reward, username,
                                        reason=f"campaign:{cid}")
            elif per_action:
                # Already approved earlier (e.g. by an admin with some actions pending):
                # top up the XP for actions finished since.
                reward = campaign_rewards.pay_action_xp(db, c, sub, user_id, username)
            completed = True
        elif done:
            if per_action and sub.status == "verified":
                # keep an approved submission approved; pay any newly passed actions
                reward = campaign_rewards.pay_action_xp(db, c, sub, user_id, username)
            else:
                sub.status = "pending"   # has manual actions awaiting admin review
        db.commit()

        # `all_submitted` is True once every action has a result, even if some are
        # awaiting manual review (free owner) — lets the bot post a clear summary.
        return {"status": status, "detail": detail, "completed": completed,
                "all_submitted": done, "reward": reward if completed else 0}
    finally:
        db.close()
        SessionLocal.remove()


def action_extra_collected(cid: int, user_id: int) -> bool:
    """True if the participant already answered the campaign's extra proof fields
    (wallet/UID/link the bot can't read from X) in the per-action flow."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None:
            return True
        keys = [f.key or f.label for f in _fields_for(db, cid, None)]
        if not keys:
            return True
        sub = _action_submission(db, c, user_id)
        answers = ((sub.proof or {}).get("fields") or {}) if sub else {}
        return all(k in answers for k in keys)
    finally:
        db.close()
        SessionLocal.remove()


def attach_action_extra_fields(cid: int, user_id: int, answers: dict,
                               username: str | None = None) -> bool:
    """Merge extra proof-field answers into the participant's per-action submission
    (no second submission row), so they show in the dashboard and CSV like any
    other field. Best-effort; returns True if stored."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None:
            return False
        sub = _action_submission(db, c, user_id, username, create=True)
        if sub is None:
            return False
        proof = dict(sub.proof or {})
        fields = dict(proof.get("fields") or {})
        fields.update({str(k)[:64]: str(v)[:300] for k, v in (answers or {}).items()})
        proof["fields"] = fields
        sub.proof = proof
        flag_modified(sub, "proof")
        is_dup, dup_reason = _detect_duplicate(db, c, fields)
        if is_dup and not sub.flagged:
            sub.flagged = True
            sub.flag_reason = dup_reason
        db.commit()
        return True
    finally:
        db.close()
        SessionLocal.remove()


def verify_raid_submission(cid: int, user_id: int, username: str, handle: str):
    """Run a raid's live X verification for one participant and record the result.

    Powers the ephemeral in-channel panel (no DM): returns
    (status, reward, results) where
      status  ∈ verified | pending | duplicate | closed | not_raid
      results = {goal: {status, detail}} from twitter_verify (for the checklist).

    one-per-user: an already-verified submission returns "duplicate"; a pending one
    is reused so the member can retry after X propagates (~30s golden period)."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.is_open:
            return ("closed", 0, {})
        if c.type != "raid":
            return ("not_raid", 0, {})
        guild = db.get(Guild, c.guild_id)
        pro = bool(guild and guild.is_pro)
        owner_id = guild.owner_id if guild else None
        goals = _settings(c).get("raid_goals") or {}
        reward = campaign_rewards.effective_reward(c)

        # A raid panel is inherently one-record-per-participant — ALWAYS reuse an
        # existing (non-rejected) submission so repeated Verify taps are idempotent
        # (no duplicate rows or XP farming, even when one_per_user is off).
        existing = (
            db.query(CampaignSubmission)
            .filter(
                CampaignSubmission.campaign_id == cid,
                CampaignSubmission.user_id == user_id,
                CampaignSubmission.status != "rejected",
            )
            .order_by(CampaignSubmission.id.desc())
            .first()
        )
        if existing is not None and existing.status == "verified":
            return ("duplicate", 0, existing.proof.get("results", {}) if existing.proof else {})

        # Live verification (Pro + key + auto-verify gated). Any uncertainty → pending.
        results = {}
        overall = "pending"
        if pro and _settings(c).get("auto_verify_x") and twitter_verify.enabled(owner_id):
            h = twitter_verify.normalize_handle(handle)
            if h:
                r = twitter_verify.verify_raid(
                    c.task_url, goals, h, owner_user_id=owner_id,
                    follow_target=_settings(c).get("raid_follow_target"),
                )
                results = r.get("results") or {}
                overall = r.get("overall") or "pending"

        sub = existing or CampaignSubmission(
            campaign_id=cid, task_id=None, user_id=user_id,
            username=(username or "")[:120], proof={},
        )
        sub.username = (username or "")[:120]
        proof = dict(sub.proof or {})
        proof["x_handle"] = (handle or "")[:120]
        proof["results"] = results
        sub.proof = proof
        flag_modified(sub, "proof")

        if overall == "verified":
            if sub.status != "verified":
                sub.status = "verified"
                sub.reviewed_at = datetime.utcnow()
                if campaign_rewards.per_action_applies(c, sub):
                    reward = campaign_rewards.pay_action_xp(db, c, sub, user_id, username, assume_all=True)
                else:
                    sub.reward_granted = reward
                    if reward > 0:
                        leveling.add_xp(db, c.guild_id, user_id, reward, username, reason=f"campaign:{cid}")
            status = "verified"
        else:
            sub.status = "pending"
            status = "pending"

        if existing is None:
            db.add(sub)
        db.commit()
        return (status, reward if status == "verified" else 0, results)
    finally:
        db.close()
        SessionLocal.remove()


def _extract_handle(value, extra_fields):
    """Best-effort X handle from the participant's modal input — the main value
    first (the raid modal asks for it directly), then any extra field."""
    h = twitter_verify.normalize_handle(value) if value else None
    if h:
        return h
    for v in (extra_fields or {}).values():
        h = twitter_verify.normalize_handle(v)
        if h:
            return h
    return None


RECHECK_MIN_AGE_S = 90        # give X a moment to show the action before the first re-check
RECHECK_WINDOW_MIN = 30       # then keep trying for this long (one try per run)


def recheck_pending_x_tasks(limit: int = 20) -> int:
    """Re-verify task submissions left pending because X had not shown the action yet.

    One try per run (every 5 min) for RECHECK_WINDOW_MIN, so at most ~6 X calls per
    submission; then a human decides. Upgrade-only: never rejects, skips flagged
    (duplicate) submissions, same Pro / key / kill-switch gates as the submit path
    (TASK_X_AUTOVERIFY_ENABLED=0). Returns how many were verified. Never raises."""
    if os.environ.get("TASK_X_AUTOVERIFY_ENABLED", "1").strip().lower() in ("0", "false", "no", "off"):
        return 0
    from datetime import timedelta
    now = datetime.utcnow()
    done = 0
    db = SessionLocal()
    try:
        subs = (
            db.query(CampaignSubmission)
            .filter(CampaignSubmission.status == "pending",
                    CampaignSubmission.task_id.isnot(None),
                    CampaignSubmission.flagged.isnot(True),
                    CampaignSubmission.created_at >= now - timedelta(minutes=RECHECK_WINDOW_MIN),
                    CampaignSubmission.created_at <= now - timedelta(seconds=RECHECK_MIN_AGE_S))
            .order_by(CampaignSubmission.created_at.asc()).limit(limit * 3).all()
        )
        deadline = time.monotonic() + 100   # stay inside the scheduler's 150 s job timeout
        checked = 0
        for sub in subs:
            if checked >= limit or time.monotonic() > deadline:
                break
            try:
                task = db.get(CampaignTask, sub.task_id)
                c = db.get(Campaign, sub.campaign_id)
                # A member who submitted while it was open still gets the automatic re-check after
                # it ended: not being able to confirm them is our limit, never theirs.
                if task is None or c is None or c.status in ("draft", "archived"):
                    continue
                keys = {(f.key or str(f.label)[:45]) for f in (task.custom_fields or [])
                        if (f.field_type or "") == "username"}
                fields = (sub.proof or {}).get("fields") or {}
                typed = next((_extract_handle(v, None) for k, v in fields.items()
                              if k in keys and str(v).strip()), None)
                if typed and social_handles.taken(db, sub.user_id, typed):
                    typed = None
                handle = typed or social_handles.get_handle(sub.user_id)
                if not handle:
                    continue
                checked += 1
                # Same gates + verdict as the submit path (Pro, key, goals, kill switch).
                if not _task_autoverifies(db, c, task, None, None, None, handle=handle):
                    continue
                reward = (task.reward_xp or 0)
                changed = (
                    db.query(CampaignSubmission)
                    .filter(CampaignSubmission.id == sub.id, CampaignSubmission.status == "pending")
                    .update({"status": "verified", "reviewed_at": datetime.utcnow(),
                             "reward_granted": reward}, synchronize_session=False)
                )
                if changed and reward > 0:
                    leveling.add_xp(db, c.guild_id, sub.user_id, reward, sub.username or "",
                                    reason=f"campaign:{c.id}")
                db.commit()
                done += changed
            except Exception:  # noqa: BLE001
                db.rollback()
                log.info("x task re-check failed for submission %s", sub.id, exc_info=True)
    finally:
        db.close()
        SessionLocal.remove()
    return done


def _resolve_handle(user_id, typed):
    """The X handle to verify: what the member typed, else the one they saved before.
    A typed handle is remembered for next time; one that belongs to another Discord
    account is never used. Never raises."""
    try:
        if user_id is None:
            return typed
        saved = social_handles.get_handle(user_id)
        if typed:
            if saved and saved.lower() == typed.lower():
                return saved
            res = social_handles.set_handle(user_id, typed) if not saved else None
            if res == social_handles.TAKEN:
                return None
            if saved:
                # a different typed handle never overrides the saved one silently
                return typed if not _handle_taken(user_id, typed) else None
            return res or typed
        return saved
    except Exception:  # noqa: BLE001
        return typed


def _handle_taken(user_id, handle) -> bool:
    db = SessionLocal()
    try:
        return social_handles.taken(db, user_id, handle)
    finally:
        db.close()
        SessionLocal.remove()


def _task_x_result(db, c, task, handle):
    """The live X verdict for one task and handle, or None when X auto-verify does not
    apply (switch off, no targets, not an X task, server not Pro, no key, kill switch).
    {"overall": "verified"|"pending", "results": {goal: {status, detail}}}. Never raises."""
    try:
        if os.environ.get("TASK_X_AUTOVERIFY_ENABLED", "1").strip().lower() in ("0", "false", "no", "off"):
            return None
        s_ = task.settings or {}
        platform = (task.platform or "").lower()
        if not (s_.get("auto_verify_x") and s_.get("raid_goals")
                and (task.type == "raid" or platform in ("x", "twitter"))):
            return None
        guild = db.get(Guild, c.guild_id)
        if guild is None or not guild.is_pro:
            return None
        owner_id = guild.owner_id
        if not twitter_verify.enabled(owner_id):
            return None
        if not handle:
            return None
        return twitter_verify.verify_raid(
            task.task_url or c.task_url, s_.get("raid_goals") or {}, handle, owner_user_id=owner_id,
        )
    except Exception:  # noqa: BLE001
        return None


def _task_autoverifies(db, c, task, value, extra_fields, user_id=None, handle=None) -> bool:
    """Per-task variant of _raid_autoverifies, driven by task.settings. Pro-gated and
    key-gated; any uncertainty/error returns False (stays pending). Never raises."""
    try:
        # Only the task's own username-type field counts as a typed handle: the main proof
        # value and other fields (UID, wallet, link) must never be mistaken for one - or
        # saved as the member's handle. Blank -> the handle they saved before.
        if handle is None:
            keys = {(f.key or str(f.label)[:45]) for f in (task.custom_fields or [])
                    if (f.field_type or "") == "username"}
            typed = next((_extract_handle(v, None) for k, v in (extra_fields or {}).items()
                          if k in keys and str(v).strip()), None)
            handle = _resolve_handle(user_id, typed)
        result = _task_x_result(db, c, task, handle)
        return bool(result) and result.get("overall") == "verified"
    except Exception:  # noqa: BLE001
        return False


# -- Member-facing task buttons (short label, link + Verify panel) ---------------

_GOAL_LABEL = {"follows": "🐦 Follow on X", "retweets": "🔁 Repost on X", "comments": "💬 Comment on X",
               "quotes": "🔁 Quote on X", "likes": "❤️ Like on X"}
_PLATFORM_NAME = {"x": "X", "twitter": "X", "telegram": "Telegram", "discord": "Discord", "youtube": "YouTube",
                  "instagram": "Instagram", "tiktok": "TikTok", "facebook": "Facebook", "reddit": "Reddit",
                  "linkedin": "LinkedIn", "medium": "Medium"}
_LABEL_MAX = 28
_GOAL_KEYS = ("likes", "retweets", "comments", "quotes", "follows")


def task_button_label(t) -> str:
    """Short button text for a task (a dict from load_for_post or a CampaignTask), with no
    XP and no long title. The owner's `settings.button_label` wins; otherwise it is derived
    from what the task checks, else from the title's first words."""
    g = (lambda k, d=None: t.get(k, d)) if isinstance(t, dict) else (lambda k, d=None: getattr(t, k, d))
    s_ = g("settings") or {}
    custom = str(s_.get("button_label") or "").strip()
    if custom:
        return custom[:_LABEL_MAX]
    platform = (g("platform") or "").lower()
    goals = [k for k in _GOAL_KEYS if (s_.get("raid_goals") or {}).get(k)]
    x_task = g("type") == "raid" or platform in ("x", "twitter")
    if x_task and len(goals) == 1:
        return _GOAL_LABEL[goals[0]]
    if x_task and goals:
        return "🐦 X task"
    title = (g("title") or "").strip()
    low = title.lower()
    pname = _PLATFORM_NAME.get(platform)
    word = "channel" if "channel" in low else "server" if "server" in low else "group" if "group" in low else ""
    if low.startswith("join") and pname:
        return f"Join {pname}{' ' + word if word else ''}"[:_LABEL_MAX]
    for verb, label in (("follow", "Follow"), ("subscribe", "Subscribe"), ("retweet", "Repost"),
                        ("repost", "Repost"), ("like", "Like"), ("comment", "Comment")):
        if low.startswith(verb) and pname:
            return f"{'🐦 ' if platform in ('x', 'twitter') else ''}{label} on {pname}"[:_LABEL_MAX]
    cut = title.split(":")[0].split(" – ")[0].split(" - ")[0].strip() or title or "Submit"
    return cut if len(cut) <= _LABEL_MAX else cut[:_LABEL_MAX - 1].rstrip() + "…"


def task_panel_kind(db, c, task):
    """"x" when the member can complete this task with buttons alone (open the link, then
    Verify, checked live on X); else None (the normal proof modal). Only tasks whose proof
    fields are at most an X username qualify, because the panel collects nothing else."""
    try:
        if any((f.field_type or "") != "username" for f in (task.custom_fields or [])):
            return None
        s_ = task.settings or {}
        platform = (task.platform or "").lower()
        if not (s_.get("auto_verify_x") and s_.get("raid_goals")
                and (task.type == "raid" or platform in ("x", "twitter"))):
            return None
        if os.environ.get("TASK_X_AUTOVERIFY_ENABLED", "1").strip().lower() in ("0", "false", "no", "off"):
            return None
        guild = db.get(Guild, c.guild_id)
        if guild is None or not guild.is_pro or not twitter_verify.enabled(guild.owner_id):
            return None
        return "x"
    except Exception:  # noqa: BLE001
        return None


def task_submission_status(cid: int, tid: int, user_id: int):
    """None | "verified" | "pending" for this member's (non-rejected) submission to a task."""
    db = SessionLocal()
    try:
        row = (db.query(CampaignSubmission)
               .filter(CampaignSubmission.campaign_id == cid, CampaignSubmission.task_id == tid,
                       CampaignSubmission.user_id == user_id, CampaignSubmission.status != "rejected")
               .order_by(CampaignSubmission.id.desc()).first())
        return row.status if row else None
    finally:
        db.close()
        SessionLocal.remove()


def check_task_x(cid: int, tid: int, handle: str) -> dict:
    """Live X check for one member and task, WITHOUT creating a submission.
    {"overall": "verified"|"pending"|"closed", "results": {...}}. Never raises."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        task = db.get(CampaignTask, tid)
        if c is None or not c.is_open or task is None or task.campaign_id != cid:
            return {"overall": "closed", "results": {}}
        return _task_x_result(db, c, task, handle) or {"overall": "pending", "results": {}}
    finally:
        db.close()
        SessionLocal.remove()


def _raid_autoverifies(db, c, value, extra_fields, user_id=None) -> bool:
    """True iff the raid's provable goals verify live for this participant. Pro-gated
    and key-gated; any uncertainty/error returns False (stays pending). Never raises."""
    try:
        guild = db.get(Guild, c.guild_id)
        if guild is None or not guild.is_pro:
            return False
        owner_id = guild.owner_id
        if not twitter_verify.enabled(owner_id):
            return False
        handle = _resolve_handle(user_id, _extract_handle(value, extra_fields))
        if not handle:
            return False
        goals = _settings(c).get("raid_goals") or {}
        follow_target = _settings(c).get("raid_follow_target")
        result = twitter_verify.verify_raid(
            c.task_url, goals, handle, owner_user_id=owner_id, follow_target=follow_target,
        )
        return result.get("overall") == "verified"
    except Exception:
        return False
