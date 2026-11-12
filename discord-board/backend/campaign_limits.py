"""Multiple submissions per member (Guildizer).

A campaign with `one_per_user` off can accept several submissions from the same member.
Optional settings (all in `campaign.settings`, so no schema change):

  min_submissions       how many a member needs to complete the campaign (default 1)
  max_submissions       the most a member may send per task (blank = unlimited)
  extra_submission_xp   XP for each approved submission beyond the required ones
                        (blank = same reward as the others)

One-per-person campaigns and raids ignore all of this. See REVERT.md.
"""
from __future__ import annotations

import os

from models import CampaignSubmission


def _enabled() -> bool:
    """Kill switch: MULTI_SUBMISSIONS_ENABLED=0 -> no cap and no extra-submission XP (the old behaviour)."""
    return os.getenv("MULTI_SUBMISSIONS_ENABLED", "1") != "0"


def limits(c):
    """(required, maximum) submissions per member per task; maximum None = unlimited."""
    if c.one_per_user or c.type == "raid":
        return 1, 1
    if not _enabled():
        return 1, None
    s = c.settings or {}
    try:
        mx = int(s.get("max_submissions") or 0) or None
    except (TypeError, ValueError):
        mx = None
    try:
        mn = max(1, int(s.get("min_submissions") or 1))
    except (TypeError, ValueError):
        mn = 1
    if mx:
        mn = min(mn, mx)
    return mn, mx


def clean_settings(settings: dict) -> dict:
    """Normalise the three keys (blank/invalid removed, clamped). Raises ValueError on min > max."""
    out = dict(settings or {})
    for key, lo, hi in (("min_submissions", 1, 50), ("max_submissions", 1, 1000),
                        ("extra_submission_xp", 0, 100000)):
        if key not in out:
            continue
        raw = out.get(key)
        if raw in (None, ""):
            out.pop(key, None)
            continue
        try:
            out[key] = max(lo, min(hi, int(raw)))
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number")
    if out.get("min_submissions") and out.get("max_submissions") and out["min_submissions"] > out["max_submissions"]:
        raise ValueError("Required submissions can't be more than the maximum.")
    import post_template
    post_template.clean_settings(out)
    return out


def count(db, cid, task_id, user_id, exclude_id=None) -> int:
    """Submissions that count toward the cap: everything not rejected."""
    q = db.query(CampaignSubmission).filter(
        CampaignSubmission.campaign_id == cid,
        CampaignSubmission.user_id == user_id,
        CampaignSubmission.status != "rejected",
        CampaignSubmission.task_id.is_(None) if not task_id else CampaignSubmission.task_id == task_id,
    )
    if exclude_id:
        q = q.filter(CampaignSubmission.id != exclude_id)
    return q.count()


def reward(db, c, task_id, user_id, base: int, exclude_id=None) -> int:
    """XP for one approved submission: the normal reward for the first `required`
    approvals, then `extra_submission_xp` (when set) for the rest."""
    if not base or c.one_per_user or c.type == "raid" or not _enabled():
        return base
    extra = (c.settings or {}).get("extra_submission_xp")
    if extra in (None, ""):
        return base
    mn, _mx = limits(c)
    q = db.query(CampaignSubmission).filter(
        CampaignSubmission.campaign_id == c.id,
        CampaignSubmission.user_id == user_id,
        CampaignSubmission.status == "verified",
        CampaignSubmission.task_id.is_(None) if not task_id else CampaignSubmission.task_id == task_id,
    )
    if exclude_id:
        q = q.filter(CampaignSubmission.id != exclude_id)
    return int(extra) if q.count() >= mn else base


def progress_text(db, c, task_id, user_id) -> str:
    """' (2/3 required, max 5)' for multi-submission campaigns, else ''."""
    mn, mx = limits(c)
    if c.one_per_user or (mn <= 1 and not mx):
        return ""
    n = count(db, c.id, task_id, user_id)
    t = f"\nSubmissions: {n}"
    if mn > 1:
        t += f" / {mn} required" + (" ✅" if n >= mn else "")
    if mx:
        t += f" (max {mx})"
    return t


def rule_text(c) -> str:
    """One line for the campaign post, e.g. '2 required, up to 5 · 3 XP per extra'; '' when not multi."""
    mn, mx = limits(c)
    if c.one_per_user or (mn <= 1 and not mx):
        return ""
    t = (f"{mn} required" if mn > 1 else "")
    t += (", " if t and mx else "") + (f"up to {mx}" if mx else "")
    extra = (c.settings or {}).get("extra_submission_xp")
    if extra not in (None, ""):
        t += f" · {int(extra)} XP per extra"
    return t
