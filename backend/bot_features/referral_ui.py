"""Shared in-bot referral screen (official and custom bots).

Renders the user's referral link, reward progress (7-day & 1-month Pro milestones),
their counts, and monthly standing — with Share / open-link buttons. Both bot runners
call this so the referral UX is identical everywhere.
"""
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_log = logging.getLogger("referral_ui")


def _gather(flask_app, resolve_user, tg_id):
    """Return referral data dict, or None if no account / on error."""
    if not flask_app:
        return None
    with flask_app.app_context():
        from ..models import db, User, Referral, REFERRAL_MILESTONES
        from sqlalchemy import func

        user = resolve_user(tg_id)
        if not user:
            return None

        user.get_or_create_referral_code()
        db.session.commit()

        total_all = Referral.query.filter_by(referrer_user_id=user.id).count()
        total_approved = Referral.query.filter_by(
            referrer_user_id=user.id, status="approved"
        ).count()

        rewarded = set()
        for (rg,) in Referral.query.filter_by(
            referrer_user_id=user.id
        ).with_entities(Referral.rewards_given).all():
            for m in (rg or []):
                rewarded.add(m)

        milestones = []
        for required, reward_days in REFERRAL_MILESTONES:
            milestones.append({
                "required": required,
                "reward_days": reward_days,
                "reached": total_approved >= required,
                "rewarded": required in rewarded,
            })

        # Monthly standing
        now = datetime.utcnow()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rows = (
            db.session.query(Referral.referrer_user_id, func.count(Referral.id).label("cnt"))
            .filter(Referral.created_at >= start_of_month, Referral.status == "approved")
            .group_by(Referral.referrer_user_id)
            .order_by(func.count(Referral.id).desc())
            .all()
        )
        rank = None
        monthly_count = 0
        for i, (rid, cnt) in enumerate(rows, start=1):
            if rid == user.id:
                rank = i
                monthly_count = cnt
                break

        return {
            "code": user.referral_code,
            "total_all": total_all,
            "total_approved": total_approved,
            "milestones": milestones,
            "rank": rank,
            "monthly_count": monthly_count,
        }


def _build_text(data, ref_link):
    lines = [
        "🎁 *Your Referral Program*",
        "",
        "Invite friends to Telegizer and earn *free Pro time*:",
    ]
    for m in data["milestones"]:
        label = f"{m['reward_days']}-day Pro" if m["reward_days"] < 30 else "1-month Pro"
        if m["rewarded"]:
            mark = "✅"
        elif m["reached"]:
            mark = "🎉"
        else:
            mark = "•"
        lines.append(f"{mark} {m['required']} referrals → {label}")

    # Progress toward the next unreached milestone
    next_m = next((m for m in data["milestones"] if not m["reached"]), None)
    lines.append("")
    if next_m:
        remaining = next_m["required"] - data["total_approved"]
        lines.append(
            f"📊 Progress: *{data['total_approved']}* approved "
            f"— *{remaining}* more to your next reward."
        )
    else:
        lines.append(f"📊 *{data['total_approved']}* approved referrals — all rewards unlocked! 🏆")

    if data["rank"]:
        lines.append(f"🏅 This month: *#{data['rank']}* with {data['monthly_count']} referral(s).")

    lines += [
        f"👥 Total referred: *{data['total_all']}*",
        "",
        "🔗 *Your link* (tap to copy):",
        f"`{ref_link}`",
    ]
    return "\n".join(lines)


async def render(query, context, flask_app, resolve_user, frontend, official_username):
    """Edit the menu message in place to show the referral screen."""
    tg_id = query.from_user.id
    data = None
    try:
        data = _gather(flask_app, resolve_user, tg_id)
    except Exception as exc:
        _log.error("referral render failed (tg %s): %s", tg_id, exc)

    frontend = (frontend or "https://telegizer.com").rstrip("/")
    back = InlineKeyboardButton("« Back to Menu", callback_data="menu:main")

    if not data:
        await query.edit_message_text(
            "🎁 *Referral Program*\n\n"
            "Connect your Telegizer account first to get your referral link.\n\n"
            f"Open the app, then come back here.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Open Telegizer App",
                                      url=f"https://t.me/{official_username}?startapp=referral")],
                [back],
            ]),
        )
        return

    code = data["code"]
    ref_link = f"{frontend}/join?ref={code}"
    share_url = (
        f"https://t.me/share/url?url={ref_link}"
        f"&text=Join%20me%20on%20Telegizer%20%E2%80%94%20Telegram%20group%20management%20%26%20AI."
    )

    await query.edit_message_text(
        _build_text(data, ref_link),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Share Link", url=share_url)],
            [InlineKeyboardButton("🔗 Open Referral Page", url=ref_link)],
            [back],
        ]),
    )
