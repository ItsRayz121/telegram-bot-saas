"""Campaign DB helpers used by the bot (no discord.py here).

Covers posting coordination (needs_post flag), proof-submission creation with
one-per-user + honor auto-verify, and the data the announcement embed needs.
"""
from __future__ import annotations

from datetime import datetime

import leveling
from database import SessionLocal
from models import Campaign, CampaignSubmission, CampaignTask


def campaigns_to_post() -> list[int]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Campaign)
            .filter(Campaign.needs_post.is_(True), Campaign.status == "active")
            .all()
        )
        return [c.id for c in rows]
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
        if tid:
            t = db.get(CampaignTask, tid)
            if t is None or t.campaign_id != cid:
                return None
            return {"verification_mode": t.verification_mode, "title": t.title}
        return {"verification_mode": c.verification_mode, "title": c.title}
    finally:
        db.close()
        SessionLocal.remove()


def create_submission(cid: int, tid: int, user_id: int, username: str, value: str | None):
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

        sub = CampaignSubmission(
            campaign_id=cid, task_id=task_key, user_id=user_id,
            username=(username or "")[:120], proof={"value": value} if value else {},
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

        sub.status = "pending"
        db.add(sub)
        db.commit()
        return ("pending", 0)
    finally:
        db.close()
        SessionLocal.remove()
