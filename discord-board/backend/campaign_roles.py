"""Campaign-earned roles: a campaign can name a reward role (campaign.settings.reward_role_id);
every member whose submission is VERIFIED receives it once.

Deliberately a sweep over the database rather than a hook in each XP-payout site (there are
several): idempotent via CampaignSubmission.role_granted_at, so approvals from the dashboard,
the bot, auto-verify or a re-run all converge on the same result and nobody gets it twice.
A role with moderation/management permissions is never granted (same rule as every automatic
path), and a member who left / a deleted role is closed out instead of retried forever.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm.attributes import flag_modified

import role_policy
from models import Campaign, CampaignSubmission

BATCH = 25


def reward_role_id(campaign) -> int | None:
    raw = (campaign.settings or {}).get("reward_role_id")
    return int(raw) if str(raw or "").isdigit() else None


def set_reward_role(db, campaign, role_id) -> None:
    s = dict(campaign.settings or {})
    if role_id:
        s["reward_role_id"] = str(role_id)
    else:
        s.pop("reward_role_id", None)
    campaign.settings = s
    flag_modified(campaign, "settings")


def pending(db, guild_ids: list[int], limit: int = BATCH, skip=frozenset()) -> list[dict]:
    """Verified submissions on role-rewarding campaigns that haven't received the role yet."""
    if not guild_ids:
        return []
    out = []
    camps = db.query(Campaign).filter(Campaign.guild_id.in_(guild_ids)).all()
    roles = {c.id: reward_role_id(c) for c in camps if reward_role_id(c)}
    if not roles:
        return []
    subs = (db.query(CampaignSubmission)
            .filter(CampaignSubmission.campaign_id.in_(list(roles)),
                    CampaignSubmission.status == "verified",
                    CampaignSubmission.role_granted_at.is_(None))
            .order_by(CampaignSubmission.id).limit(limit * 8 + len(skip) * 4).all())
    seen = set()
    by_camp = {c.id: c for c in camps}
    for s in subs:
        key = (s.campaign_id, s.user_id)       # a multi-task campaign has many submissions per member
        if key in seen or key in skip:         # skip = members in retry back-off (don't starve the rest)
            continue
        seen.add(key)
        out.append({"sub_ids": [x.id for x in subs if (x.campaign_id, x.user_id) == key],
                    "guild_id": by_camp[s.campaign_id].guild_id, "campaign_id": s.campaign_id,
                    "campaign_title": by_camp[s.campaign_id].title, "user_id": s.user_id,
                    "username": s.username, "role_id": roles[s.campaign_id]})
        if len(out) >= limit:
            break
    return out


def mark_done(db, sub_ids: list[int], note: str | None = None) -> None:
    now = datetime.utcnow()
    for s in db.query(CampaignSubmission).filter(CampaignSubmission.id.in_(sub_ids)).all():
        s.role_granted_at = now
        s.role_note = note
