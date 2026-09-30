"""Daily platform snapshot + live totals for the admin dashboard.

Managed members = everyone in a group our bots protect (TelegramGroup.member_count,
official + custom bots). Verified members = the subset our bot has verified
(OfficialMember.is_verified). Snapshotting once a day is the only way to get a
"members joined per day" curve, because those counts can't be rebuilt later.
"""
from datetime import datetime

from .models import db, User, TelegramGroup, CustomBot, OfficialMember, PlatformDailyStat

_COUNTED_GROUP = (TelegramGroup.bot_status == "active", TelegramGroup.is_disabled == False)  # noqa: E712


def compute_totals(now=None) -> dict:
    now = now or datetime.utcnow()
    F = db.func

    managed = db.session.query(F.coalesce(F.sum(TelegramGroup.member_count), 0)).filter(*_COUNTED_GROUP).scalar() or 0
    verified = (
        db.session.query(F.count(OfficialMember.id))
        .join(TelegramGroup, TelegramGroup.telegram_group_id == OfficialMember.telegram_group_id)
        .filter(*_COUNTED_GROUP, OfficialMember.is_verified == True)  # noqa: E712
        .scalar() or 0
    )
    groups = dict(
        db.session.query(TelegramGroup.linked_via_bot_type, F.count(TelegramGroup.id))
        .filter(*_COUNTED_GROUP).group_by(TelegramGroup.linked_via_bot_type).all()
    )
    users_total = db.session.query(F.count(User.id)).scalar() or 0
    # trial = Pro via signup trial with nothing paid (same rule as custom_bot_access)
    users_trial = db.session.query(F.count(User.id)).filter(
        User.subscription_tier == "pro", User.subscription_expires.is_(None),
        User.trial_ends_at.isnot(None), User.trial_ends_at > now,
    ).scalar() or 0
    users_paid_tier = db.session.query(F.count(User.id)).filter(User.subscription_tier.in_(("pro", "enterprise"))).scalar() or 0
    users_paid = max(users_paid_tier - users_trial, 0)
    users_free = max(users_total - users_paid - users_trial, 0)
    bots_total = db.session.query(F.count(CustomBot.id)).scalar() or 0
    bots_active = db.session.query(F.count(CustomBot.id)).filter(CustomBot.status == "active").scalar() or 0

    return {
        "managed_members": int(managed), "verified_members": int(verified),
        "groups_total": sum(groups.values()),
        "groups_official": groups.get("official", 0), "groups_custom": groups.get("custom", 0),
        "users_total": users_total, "users_free": users_free,
        "users_trial": users_trial, "users_paid": users_paid,
        "custom_bots_total": bots_total, "custom_bots_active": bots_active,
    }


def save_snapshot(now=None) -> dict:
    """Upsert today's (UTC) row. Safe to call repeatedly; the last call of the day wins."""
    now = now or datetime.utcnow()
    totals = compute_totals(now)
    row = PlatformDailyStat.query.get(now.date())
    if row is None:
        row = PlatformDailyStat(day=now.date())
        db.session.add(row)
    for k, v in totals.items():
        setattr(row, k, v)
    db.session.commit()
    return totals
