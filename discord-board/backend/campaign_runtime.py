"""Campaign DB helpers used by the bot (no discord.py here).

Covers posting coordination (needs_post flag), proof-submission creation with
one-per-user + honor auto-verify, and the data the announcement embed needs.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm.attributes import flag_modified

import leveling
import twitter_verify
from database import SessionLocal
from models import Campaign, CampaignCustomField, CampaignSubmission, CampaignTask, Guild


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


def load_for_post(cid: int) -> dict | None:
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None:
            return None
        return {
            "id": c.id,
            "guild_id": c.guild_id,
            "title": c.title,
            "description": c.description or "",
            "type": c.type,
            "task_url": c.task_url,
            "raid_goals": (c.settings or {}).get("raid_goals") or {},
            "auto_verify_x": bool((c.settings or {}).get("auto_verify_x")),
            "reward_xp": c.reward_xp or 0,
            "reward_label": c.reward_label,
            "verification_mode": c.verification_mode,
            "channel_id": c.channel_id,
            "message_id": c.message_id,
            "tasks": [
                {"id": t.id, "title": t.title, "description": t.description or "",
                 "task_url": t.task_url, "reward_xp": t.reward_xp or 0,
                 "verification_mode": t.verification_mode}
                for t in sorted(c.tasks, key=lambda x: x.order)
            ],
        }
    finally:
        db.close()
        SessionLocal.remove()


def mark_posted(cid: int, message_id: int) -> None:
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is not None:
            c.message_id = message_id
            c.post_status = "posted"
            c.post_error = None
            c.needs_post = False
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


def submit_context(cid: int, tid: int) -> dict | None:
    """What the proof button needs to decide: open? honor or modal? title?"""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.is_open:
            return None
        fields = [
            f.to_dict() for f in (
                db.query(CampaignCustomField)
                .filter(CampaignCustomField.campaign_id == cid)
                .order_by(CampaignCustomField.position)
                .limit(4)
                .all()
            )
        ]
        auto_verify_x = bool((c.settings or {}).get("auto_verify_x"))
        if tid:
            t = db.get(CampaignTask, tid)
            if t is None or t.campaign_id != cid:
                return None
            return {"verification_mode": t.verification_mode, "title": t.title, "fields": fields,
                    "type": c.type, "auto_verify_x": auto_verify_x}
        return {"verification_mode": c.verification_mode, "title": c.title, "fields": fields,
                "type": c.type, "auto_verify_x": auto_verify_x}
    finally:
        db.close()
        SessionLocal.remove()


def create_submission(cid: int, tid: int, user_id: int, username: str, value: str | None,
                      extra_fields: dict | None = None):
    """Create a proof submission. Returns (status, reward):
       verified | pending | duplicate | closed."""
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

        proof = {"value": value} if value else {}
        if extra_fields:
            proof["fields"] = {str(k)[:45]: str(v)[:300] for k, v in extra_fields.items()}
        if value:
            # annotate (never auto-reject): does the first proof URL resolve?
            import link_checks
            verdict = link_checks.check_proof_text(value)
            if verdict is not None:
                proof["link_check"] = verdict
        sub = CampaignSubmission(
            campaign_id=cid, task_id=task_key, user_id=user_id,
            username=(username or "")[:120], proof=proof,
        )
        if vmode == "honor":
            sub.status = "verified"
            sub.reward_granted = reward
            sub.reviewed_at = datetime.utcnow()
            if reward > 0:
                leveling.add_xp(db, c.guild_id, user_id, reward, username, reason=f"campaign:{cid}")
            db.add(sub)
            db.commit()
            return ("verified", reward)

        # Twitter Raid X auto-verify (Pro): try to confirm the participant's actions
        # live before falling back to manual review. Purely additive — any
        # uncertainty/error leaves the submission pending (never auto-rejects).
        if c.type == "raid" and (c.settings or {}).get("auto_verify_x"):
            if _raid_autoverifies(db, c, value, extra_fields):
                sub.status = "verified"
                sub.reward_granted = reward
                sub.reviewed_at = datetime.utcnow()
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


def raid_context(cid: int) -> dict | None:
    """What the ephemeral raid panel needs: title, goals, open state, auto-verify flag.
    Returns None if the campaign is gone or closed."""
    db = SessionLocal()
    try:
        c = db.get(Campaign, cid)
        if c is None or not c.is_open:
            return None
        return {
            "title": c.title,
            "goals": (c.settings or {}).get("raid_goals") or {},
            "auto_verify_x": bool((c.settings or {}).get("auto_verify_x")),
            "type": c.type,
        }
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
        goals = (c.settings or {}).get("raid_goals") or {}
        reward = c.reward_xp or 0

        existing = None
        if c.one_per_user:
            existing = (
                db.query(CampaignSubmission)
                .filter(
                    CampaignSubmission.campaign_id == cid,
                    CampaignSubmission.user_id == user_id,
                    CampaignSubmission.status != "rejected",
                )
                .first()
            )
            if existing is not None and existing.status == "verified":
                return ("duplicate", 0, existing.proof.get("results", {}) if existing.proof else {})

        # Live verification (Pro + key + auto-verify gated). Any uncertainty → pending.
        results = {}
        overall = "pending"
        if pro and (c.settings or {}).get("auto_verify_x") and twitter_verify.enabled(owner_id):
            h = twitter_verify.normalize_handle(handle)
            if h:
                r = twitter_verify.verify_raid(
                    c.task_url, goals, h, owner_user_id=owner_id,
                    follow_target=(c.settings or {}).get("raid_follow_target"),
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
                sub.reward_granted = reward
                sub.reviewed_at = datetime.utcnow()
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


def _raid_autoverifies(db, c, value, extra_fields) -> bool:
    """True iff the raid's provable goals verify live for this participant. Pro-gated
    and key-gated; any uncertainty/error returns False (stays pending). Never raises."""
    try:
        guild = db.get(Guild, c.guild_id)
        if guild is None or not guild.is_pro:
            return False
        owner_id = guild.owner_id
        if not twitter_verify.enabled(owner_id):
            return False
        handle = _extract_handle(value, extra_fields)
        if not handle:
            return False
        goals = (c.settings or {}).get("raid_goals") or {}
        follow_target = (c.settings or {}).get("raid_follow_target")
        result = twitter_verify.verify_raid(
            c.task_url, goals, handle, owner_user_id=owner_id, follow_target=follow_target,
        )
        return result.get("overall") == "verified"
    except Exception:
        return False
