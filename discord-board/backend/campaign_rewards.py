"""Per-action XP for raids (Telegizer parity: `settings.action_xp`).

A raid owner may set XP for each targeted action ({like, retweet, comment, quote,
follow}). A participant then earns the XP of each action that actually passed, only once
the submission is verified, and may be topped up later when they finish more actions.

Exactly-once guarantee: every payout is recorded in `proof["xp_awarded"]` ({action: xp})
on the submission, read under a row lock, so approving twice, double-tapping Verify or a
review racing the bot can never pay the same action twice.

Kill switch: set CAMPAIGN_ACTION_XP_ENABLED=0 on the Guildizer service. Per-action XP is
then ignored and campaigns pay their flat `reward_xp` exactly as before. See REVERT.md.
"""
from __future__ import annotations

import os

from sqlalchemy.orm.attributes import flag_modified

import leveling

MAX_ACTION_XP = 100000


def enabled() -> bool:
    return os.environ.get("CAMPAIGN_ACTION_XP_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def action_xp_map(c) -> dict:
    """{action: xp} for the actions this campaign targets, values > 0 only. Empty when
    unset, when the campaign targets no actions, or when the kill switch is off."""
    if not enabled():
        return {}
    raw = (c.settings or {}).get("action_xp")
    if not isinstance(raw, dict):
        return {}
    from campaign_runtime import campaign_action_goals   # lazy: runtime imports this module
    out = {}
    for _gk, act, _target in campaign_action_goals(c):
        try:
            v = int(raw.get(act) or 0)
        except (TypeError, ValueError):
            v = 0
        if v > 0:
            out[act] = min(v, MAX_ACTION_XP)
    return out


def per_action_applies(c, sub=None) -> bool:
    """Multi-task submissions keep their per-task reward; everything else uses per-action
    XP whenever the campaign defines it."""
    if sub is not None and sub.task_id:
        return False
    return bool(action_xp_map(c))


def effective_reward(c) -> int:
    """XP a participant can earn in total: the sum of per-action XP when set, else the flat reward."""
    m = action_xp_map(c)
    return sum(m.values()) if m else (c.reward_xp or 0)


def unpaid_action_xp(c, sub, assume_all=False) -> dict:
    """{action: xp} not yet paid. Only for verified submissions; an action counts when it is
    'verified' or 'manual' (an admin accepted it by approving). `assume_all` treats every
    targeted action as passed (flows that only report an overall verdict)."""
    if sub.status != "verified":
        return {}
    proof = sub.proof or {}
    if (sub.reward_granted or 0) > 0 and "xp_awarded" not in proof:
        return {}   # paid in full under the flat rule before per-action tracking existed
    acts = proof.get("actions") or {}
    paid = proof.get("xp_awarded") or {}
    out = {}
    for action, xp in action_xp_map(c).items():
        if action in paid:
            continue
        if assume_all or (acts.get(action) or {}).get("status") in ("verified", "manual"):
            out[action] = xp
    return out


def pay_action_xp(db, c, sub, user_id, username, assume_all=False) -> int:
    """Pay what is unpaid for this submission and record it. Returns the XP granted now."""
    if not per_action_applies(c, sub):
        return 0
    db.add(sub)
    db.flush()
    try:
        db.refresh(sub, with_for_update=True)      # serialise concurrent payers (no-op on SQLite)
    except Exception:  # noqa: BLE001 - backend without row locks
        pass
    unpaid = unpaid_action_xp(c, sub, assume_all=assume_all)
    total = sum(unpaid.values())
    if total <= 0:
        return 0
    leveling.add_xp(db, c.guild_id, user_id, total, username, reason=f"campaign:{c.id}")
    proof = dict(sub.proof or {})
    paid = dict(proof.get("xp_awarded") or {})
    paid.update(unpaid)
    proof["xp_awarded"] = paid
    sub.proof = proof
    flag_modified(sub, "proof")
    sub.reward_granted = (sub.reward_granted or 0) + total
    return total
