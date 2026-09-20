"""Tier-expiry lifecycle for custom bots: pause -> retain -> delete.

Custom bots require Pro/Enterprise to exist (Config.MAX_CUSTOM_BOTS['free'] == 0),
but historically nothing happened to a bot's dedicated polling thread when its
owner's subscription lapsed or trial expired -- it kept running at full cost,
indefinitely, until someone manually deleted the row.

This module runs the daily stage machine (see STAGES below) that:
  1. Warns the owner 2 and 1 days before their trial/subscription lapses.
  2. On the day it lapses, snapshots WHY (trial vs paid churn matters for both
     copy and timeline) and sends the full three-option message: move to the
     official bot for free, export settings, or reactivate at a discount.
  3. Sends grace-period reminders, then pauses the bot's poller.
  4. Sends a retention reminder, then permanently deletes the bot.

Every stage fires at most once per bot, via an exactly-once claim
(custom_bot_lifecycle_stages, same INSERT ... ON CONFLICT idiom as
scheduled_job_runs / _JOB_CLAIM_SQL in app.py) -- safe to re-run on every daily
tick and safe across restarts/redeploys.

Kill switches (see REVERT.md):
  CUSTOM_BOT_LIFECYCLE_ENABLED  (default "1") -- master switch, no deploy needed.
  CUSTOM_BOT_LIFECYCLE_DRY_RUN  (default "1") -- ship ON. Logs every stage's
      intended action (notify / pause / delete) without sending anything or
      touching a bot, mirroring the RETENTION_DRY_RUN precedent in retention.py.
      Flip to "0" only after reviewing a day or two of logs.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import text

from .models import db, CustomBot, User, Bot

logger = logging.getLogger(__name__)


def _env_flag(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


ENABLED = _env_flag("CUSTOM_BOT_LIFECYCLE_ENABLED", True)
DRY_RUN = _env_flag("CUSTOM_BOT_LIFECYCLE_DRY_RUN", True)

# reason -> ordered (stage, days, phase, action).
# phase 'grace'  measures from grace_started_at while status == 'active'.
# phase 'paused' measures from paused_at        while status == 'paused'.
STAGES = {
    "trial_expired": [
        ("day_1", 1, "grace", "remind"),
        ("day_3", 3, "grace", "pause"),
        ("day_8", 5, "paused", "remind"),
        ("day_10", 7, "paused", "delete"),
    ],
    "subscription_expired": [
        ("day_3", 3, "grace", "remind"),
        ("day_6", 6, "grace", "remind"),
        ("day_7", 7, "grace", "pause"),
        ("day_17", 10, "paused", "remind"),
        ("day_22", 15, "paused", "delete"),
    ],
}

DISCOUNT_CODE = {"trial_expired": "TRIAL20", "subscription_expired": "COMEBACK20"}
RETENTION_DAYS = {"trial_expired": 7, "subscription_expired": 15}

_CLAIM_SQL = text(
    "INSERT INTO custom_bot_lifecycle_stages (bot_id, stage, sent_at) VALUES (:bot_id, :stage, :now) "
    "ON CONFLICT (bot_id, stage) DO NOTHING RETURNING bot_id"
)


def claim_stage(bot_id: int, stage: str) -> bool:
    """True if this call wins the claim on *stage* for *bot_id* -- i.e. it has not
    fired before. Fails CLOSED: a DB error skips the tick rather than risk a
    duplicate DM, email, pause, or delete."""
    try:
        with db.engine.connect() as conn:
            won = conn.execute(_CLAIM_SQL, {"bot_id": bot_id, "stage": stage, "now": datetime.utcnow()}).fetchone()
            conn.commit()
            return won is not None
    except Exception as exc:
        logger.error("[custom_bot_lifecycle] claim failed bot=%s stage=%s: %s", bot_id, stage, exc)
        return False


def start_grace_period(bot: CustomBot, reason: str) -> None:
    """Called the instant a bot owner's tier flips to free (from inside
    downgrade_expired_subscriptions / expire_trials). Must run there and not in
    the daily tick, because by the time the tick runs, User.trial_ends_at /
    subscription_expires_at are already cleared -- this is the only moment we
    can still tell a trial lapse apart from a paid churn."""
    if not ENABLED:
        return
    if not bot.pause_reason:
        bot.pause_reason = reason
        bot.grace_started_at = datetime.utcnow()
        # Commit immediately rather than waiting for the caller's end-of-loop
        # commit: if a LATER user in the same batch throws before that commit,
        # this bot's grace-period state must not be lost while the day_0 claim
        # below (a separate connection) may already have gone through.
        db.session.commit()
    # Not gated on "did we just set pause_reason above" — if a previous run set
    # pause_reason but then failed before claiming/sending day_0 (transient DB
    # error), this retries the claim on every subsequent call until it wins,
    # instead of silently never notifying the owner.
    if claim_stage(bot.id, "day_0"):
        user = User.query.get(bot.owner_user_id)
        if user:
            _safe_fire_stage(bot, user, bot.pause_reason, "day_0", "remind")


def run_lifecycle_tick(app) -> None:
    if not ENABLED:
        logger.info("[custom_bot_lifecycle] disabled via CUSTOM_BOT_LIFECYCLE_ENABLED=0")
        return
    with app.app_context():
        now = datetime.utcnow()
        try:
            _run_pre_expiry_warnings(now)
            _run_grace_and_retention(now)
        except Exception:
            logger.error("[custom_bot_lifecycle] tick failed", exc_info=True)


def _run_pre_expiry_warnings(now: datetime) -> None:
    for offset, stage in ((2, "pre_2d"), (1, "pre_1d")):
        target_date = (now + timedelta(days=offset)).date()

        paid_users = User.query.filter(
            User.subscription_tier.in_(["pro", "enterprise"]),
            User.subscription_expires_at.isnot(None),
            db.func.date(User.subscription_expires_at) == target_date,
        ).all()
        for user in paid_users:
            for bot in CustomBot.query.filter_by(
                owner_user_id=user.id, status="active", pause_reason=None
            ).all():
                if claim_stage(bot.id, stage):
                    _safe_fire_stage(bot, user, "subscription_expired", stage, "remind")

        trial_users = User.query.filter(
            User.subscription_tier == "pro",
            User.trial_ends_at.isnot(None),
            User.subscription_expires.is_(None),
            db.func.date(User.trial_ends_at) == target_date,
        ).all()
        for user in trial_users:
            for bot in CustomBot.query.filter_by(
                owner_user_id=user.id, status="active", pause_reason=None
            ).all():
                if claim_stage(bot.id, stage):
                    _safe_fire_stage(bot, user, "trial_expired", stage, "remind")


def _run_grace_and_retention(now: datetime) -> None:
    bots = CustomBot.query.filter(
        CustomBot.pause_reason.isnot(None),
        CustomBot.status.in_(["active", "paused"]),
    ).all()
    for bot in bots:
        reason = bot.pause_reason
        user = User.query.get(bot.owner_user_id)
        if not user:
            continue
        for stage, days, phase, action in STAGES.get(reason, []):
            if phase == "grace":
                if bot.status != "active" or not bot.grace_started_at:
                    continue
                if now - bot.grace_started_at < timedelta(days=days):
                    continue
            else:
                if bot.status != "paused" or not bot.paused_at:
                    continue
                if now - bot.paused_at < timedelta(days=days):
                    continue
            if not claim_stage(bot.id, stage):
                continue
            _safe_fire_stage(bot, user, reason, stage, action)
        db.session.commit()


# ── Actions ──────────────────────────────────────────────────────────────────

def _find_twin_bot(bot: CustomBot):
    """The polling record BotManager actually keys off (see routes/custom_bots.py
    delete_custom_bot for the same lookup)."""
    return Bot.query.filter_by(user_id=bot.owner_user_id, bot_username=bot.bot_username).first()


def pause_custom_bot(bot: CustomBot) -> None:
    from .bot_manager import bot_manager

    twin = _find_twin_bot(bot)
    if twin:
        try:
            bot_manager.stop_bot(twin.id)
        except Exception as exc:
            logger.warning("[custom_bot_lifecycle] stop_bot failed bot=%s: %s", bot.id, exc)
        twin.is_active = False
    else:
        # No matching Bot (polling) record — nothing was actually stopped. Mark
        # status='paused' below anyway so the ledger stays in sync, but log loudly:
        # without this, the dashboard shows "Paused" while the poller (if it
        # exists at all under a mismatched username) keeps running at full cost.
        logger.error(
            "[custom_bot_lifecycle] no twin Bot row found for bot=%s (@%s) -- marking paused in the "
            "ledger, but could NOT confirm the poller was actually stopped. Check manually.",
            bot.id, bot.bot_username,
        )

    bot.status = "paused"
    bot.paused_at = datetime.utcnow()
    bot.retention_deadline_at = bot.paused_at + timedelta(days=RETENTION_DAYS.get(bot.pause_reason, 15))
    db.session.commit()


def reactivate_custom_bot(bot: CustomBot, app) -> bool:
    """Resume a paused bot after the owner upgrades. Does NOT go through
    add_custom_bot's MAX_CUSTOM_BOTS check -- this resumes an existing row, it
    does not create a new one."""
    from .bot_manager import bot_manager

    twin = _find_twin_bot(bot)
    if not twin:
        return False
    try:
        twin.is_active = True
        started = bot_manager.start_bot(twin.id, twin.get_token(), app)
    except Exception as exc:
        logger.error("[custom_bot_lifecycle] reactivate failed bot=%s: %s", bot.id, exc)
        return False
    if not started:
        return False

    bot.status = "active"
    bot.pause_reason = None
    bot.grace_started_at = None
    bot.paused_at = None
    bot.retention_deadline_at = None
    # Clear this cycle's claim rows so a FUTURE lapse can fire day_0/day_1/...
    # again — otherwise every stage's (bot_id, stage) claim from this cycle is
    # still sitting there and claim_stage() will refuse to fire any of them a
    # second time, silently disabling the whole lifecycle for this bot forever.
    from .models import CustomBotLifecycleStage
    CustomBotLifecycleStage.query.filter_by(bot_id=bot.id).delete()
    db.session.commit()
    return True


def delete_custom_bot(bot: CustomBot) -> None:
    """Permanently remove a bot whose retention window has run out. Mirrors
    routes/custom_bots.py delete_custom_bot's cleanup so both paths leave the
    same state behind."""
    from .models import purge_bot_dependents, TelegramGroup
    from .bot_manager import bot_manager

    bot_id = bot.id
    twin = _find_twin_bot(bot)
    if twin:
        try:
            bot_manager.stop_bot(twin.id)
        except Exception:
            pass
        try:
            purge_bot_dependents(twin)
            db.session.delete(twin)
        except Exception as exc:
            logger.warning("[custom_bot_lifecycle] purge twin failed bot=%s: %s", bot_id, exc)

    TelegramGroup.query.filter_by(linked_bot_id=bot_id).update({
        "linked_bot_id": None,
        "linked_via_bot_type": "official",
    })

    if bot.hub_bot_id:
        try:
            from .assistant.hub_models import HubBotIdentity as _HBI
            hub_bot = _HBI.query.filter_by(id=bot.hub_bot_id, user_id=bot.owner_user_id).first()
            if hub_bot:
                hub_bot.is_active = False
        except Exception:
            pass

    db.session.delete(bot)
    db.session.commit()
    logger.info("[custom_bot_lifecycle] deleted bot=%s (retention window elapsed)", bot_id)


# ── Messaging ────────────────────────────────────────────────────────────────

def _bot_stats(bot: CustomBot):
    try:
        from .bot_links import resolve_connected_groups
        groups = resolve_connected_groups(bot)
        return len(groups), sum(g.get("member_count") or 0 for g in groups)
    except Exception:
        return 0, 0


def _frontend_url() -> str:
    try:
        from flask import current_app
        return current_app.config.get("FRONTEND_URL", "https://telegizer.com")
    except Exception:
        return "https://telegizer.com"


def _safe_fire_stage(bot: CustomBot, user: User, reason: str, stage: str, action: str) -> None:
    """A stage's claim is already committed by the time this runs — if anything
    below throws, the stage stays marked as fired and will never retry. Isolating
    the failure here (instead of letting it propagate) at least keeps ONE bot's
    problem from aborting the whole tick and blocking every other bot still due
    that day. See REVERT.md for the residual risk this doesn't fully close."""
    try:
        _fire_stage(bot, user, reason, stage, action)
    except Exception:
        logger.error(
            "[custom_bot_lifecycle] stage processing failed bot=%s stage=%s action=%s "
            "-- claim already committed, this will NOT retry automatically",
            bot.id, stage, action, exc_info=True,
        )


def _fire_stage(bot: CustomBot, user: User, reason: str, stage: str, action: str) -> None:
    group_count, member_count = _bot_stats(bot)
    copy = _copy_for(reason, stage, bot, group_count, member_count)

    if DRY_RUN:
        logger.info(
            "[custom_bot_lifecycle][DRY_RUN] bot=%s user=%s reason=%s stage=%s action=%s dm=%r",
            bot.id, user.id, reason, stage, action, copy["dm"][:120],
        )
    else:
        if action != "delete":
            # No DM on the final deletion stage by design: the message says
            # "email/dashboard only" and we don't want the owner's last contact
            # with their own bot to be a DM that arrives seconds before it's gone.
            _send_dm(bot, user, copy["dm"])
        _send_email(user, copy)
        _send_inapp(user, copy, stage)

    if action == "pause":
        if DRY_RUN:
            logger.info("[custom_bot_lifecycle][DRY_RUN] would pause bot=%s", bot.id)
        else:
            try:
                pause_custom_bot(bot)
            except Exception:
                logger.error(
                    "[custom_bot_lifecycle] PAUSE FAILED bot=%s -- notification was sent but the "
                    "poller may still be running at full cost; check manually", bot.id, exc_info=True,
                )
    elif action == "delete":
        if DRY_RUN:
            logger.info("[custom_bot_lifecycle][DRY_RUN] would delete bot=%s", bot.id)
        else:
            try:
                delete_custom_bot(bot)
            except Exception:
                logger.error(
                    "[custom_bot_lifecycle] DELETE FAILED bot=%s -- notification was sent but the "
                    "bot row may still exist; check manually", bot.id, exc_info=True,
                )


def _send_dm(bot: CustomBot, user: User, text_: str) -> None:
    tg_id = getattr(user, "telegram_user_id", None)
    if not tg_id:
        return
    try:
        token = bot.get_token()
    except Exception as exc:
        logger.info("[custom_bot_lifecycle] could not decrypt token bot=%s: %s", bot.id, exc)
        return

    async def _send():
        import telegram
        b = telegram.Bot(token=token)
        await b.send_message(chat_id=int(tg_id), text=text_, disable_web_page_preview=True)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_send())
    except Exception as exc:
        # Best-effort: owner may have blocked or never started their own bot.
        logger.info("[custom_bot_lifecycle] bot DM failed bot=%s user=%s: %s", bot.id, user.id, exc)
    finally:
        loop.close()


def _send_email(user: User, copy: dict) -> None:
    if not user.email:
        return
    try:
        from .notifications import send_email, _base_template
        html = _base_template(copy["email_body_html"], copy["email_title"])
        send_email(user.email, copy["email_subject"], html, copy.get("email_body_text"))
    except Exception as exc:
        logger.info("[custom_bot_lifecycle] email failed user=%s: %s", user.id, exc)


def _send_inapp(user: User, copy: dict, stage: str) -> None:
    try:
        from .routes.notifications import create_notification
        create_notification(
            user.id,
            f"custom_bot_lifecycle_{stage}",
            copy["inapp_title"],
            copy["inapp_message"],
            metadata={"url": copy["lifecycle_url"]},
        )
    except Exception as exc:
        logger.info("[custom_bot_lifecycle] in-app notification failed user=%s: %s", user.id, exc)


def _copy_for(reason: str, stage: str, bot: CustomBot, group_count: int, member_count: int) -> dict:
    fe = _frontend_url()
    username = bot.bot_username
    code = DISCOUNT_CODE[reason]
    lifecycle_url = f"{fe}/dashboard/bots/{bot.id}/lifecycle"
    groups_txt = f"{group_count} group{'s' if group_count != 1 else ''}"
    members_txt = f"{member_count} member{'s' if member_count != 1 else ''}"
    is_trial = reason == "trial_expired"
    plan_word = "free trial" if is_trial else "Pro plan"
    is_final = stage in ("day_10", "day_22")

    def pkg(dm, subject, title, message, email_title=None, email_extra=None):
        email_html = f"<p>{dm}</p>"
        if email_extra:
            email_html += email_extra
        if not is_final:
            email_html += f'<a href="{lifecycle_url}" class="btn">See my options</a>'
        return {
            "dm": dm,
            "email_subject": subject,
            "email_title": email_title or title,
            "email_body_html": email_html,
            "email_body_text": dm,
            "inapp_title": title,
            "inapp_message": message,
            "lifecycle_url": lifecycle_url,
        }

    if stage == "pre_2d":
        if is_trial:
            return pkg(
                f"Your free trial on @{username} ends in 2 days. You've had Pro running "
                f"across {groups_txt} this whole time, mod rules, welcome flow, the AI "
                f"knowledge base. Once the trial's over the bot keeps working, but those "
                f"turn off. If you want to keep it as is, upgrading now gets you 20% off "
                f"your first month with {code}. Or switch to the official Telegizer bot "
                f"for free, or just export your settings before the trial ends.",
                f"Your trial on @{username} ends in 2 days",
                "Trial ending in 2 days",
                f"@{username}'s free trial ends in 2 days across {groups_txt}.",
            )
        return pkg(
            f"Your Pro plan on @{username} renews in 2 days. If your card's up to date, "
            f"nothing changes, {groups_txt} keep running exactly as they are. If you're "
            f"planning to cancel instead, you can export your settings now or move "
            f"everything to the official Telegizer bot for free before anything's at risk.",
            f"@{username}'s Pro plan renews in 2 days",
            "Pro plan renews in 2 days",
            f"@{username}'s Pro plan renews in 2 days across {groups_txt}.",
        )

    if stage == "pre_1d":
        if is_trial:
            return pkg(
                f"Trial ends tomorrow. Same three ways to handle it: upgrade with {code}, "
                f"move to the official bot for free, or grab your settings first. After "
                f"tomorrow the mod rules and AI knowledge base go quiet in {groups_txt}.",
                f"Your trial on @{username} ends tomorrow",
                "Trial ends tomorrow",
                f"@{username}'s trial ends tomorrow.",
            )
        return pkg(
            f"Last day before renewal. If your payment method's fine you don't need to do "
            f"anything. If you already know you're not renewing, now's the moment to "
            f"export or move to the free bot instead of losing setup time later.",
            f"@{username}'s Pro plan renews tomorrow",
            "Pro plan renews tomorrow",
            f"@{username}'s Pro plan renews tomorrow.",
        )

    if stage == "day_0":
        return pkg(
            f"Your {plan_word} on @{username} just ended, so I'm on borrowed time now. "
            f"{'Three' if is_trial else 'Seven'} days from today I go quiet in all "
            f"{groups_txt}. Your mod rules, your welcome flow, {members_txt} worth of "
            f"leaderboard history, none of it gets touched right now, but it's sitting "
            f"there unprotected once the window's up. You've got three ways to handle "
            f"this. Move everything to the official Telegizer bot and keep running for "
            f"free. Grab a backup of your settings if that's all you need. Or come back "
            f"for 20% off, code {code}.",
            f"@{username} goes quiet soon unless you act",
            f"Your {plan_word} on @{username} just ended",
            f"@{username}'s {plan_word} ended. Grace period started for {groups_txt}.",
        )

    if stage == "day_1":  # trial mid-grace reminder
        return pkg(
            f"Two days left. {groups_txt} still running on the trial setup, {members_txt} "
            f"still climbing the leaderboard. Still time to move things over, or come back "
            f"cheaper with {code}.",
            f"@{username} pauses in 2 days",
            "2 days left before pausing",
            f"@{username} pauses in 2 days.",
        )

    if stage == "day_3" and reason == "subscription_expired":
        return pkg(
            f"Four days left. {groups_txt} still running on the old plan, {members_txt} "
            f"still climbing that leaderboard. Still time to move things over, or come "
            f"back cheaper with {code}.",
            f"@{username} pauses in 4 days",
            "4 days left before pausing",
            f"@{username} pauses in 4 days.",
        )

    if stage == "day_3" and reason == "trial_expired":  # pause action, trial
        return pkg(
            f"I've gone quiet now, that's what the trial ending was building to. Nothing's "
            f"deleted. You've got 7 days to come back, and everything picks up exactly "
            f"where it left off, mod rules, XP, all of it. After those 7 days I can't get "
            f"any of it back for you.",
            f"@{username} has paused",
            f"@{username} paused, 7 days to restore",
            f"@{username} paused. 7-day window to restore {groups_txt}.",
        )

    if stage == "day_6":
        return pkg(
            f"Tomorrow's the day. After this I stop responding in every group you've added "
            f"me to, and {members_txt} lose the leaderboard they've been climbing. The 20% "
            f"off code dies with the grace period too, so this is the last call on both.",
            f"@{username} pauses tomorrow",
            "Pausing tomorrow",
            f"@{username} pauses tomorrow.",
        )

    if stage == "day_7":  # pause action, paid
        return pkg(
            f"I've gone quiet now, that's what today was building to. Nothing's deleted. "
            f"You've got 15 days to come back, and everything picks up exactly where it "
            f"left off, mod rules, XP, all of it. After those 15 days I can't get any of "
            f"it back for you.",
            f"@{username} has paused",
            f"@{username} paused, 15 days to restore",
            f"@{username} paused. 15-day window to restore {groups_txt}.",
        )

    if stage in ("day_8", "day_17"):  # retention reminder
        days_left = 2 if stage == "day_8" else 5
        return pkg(
            f"{days_left} days left before your settings get wiped for good, {groups_txt} "
            f"and everything attached to them. If any of that still matters, now's the time.",
            f"@{username}'s data is deleted in {days_left} days",
            f"{days_left} days left to restore @{username}",
            f"@{username}'s data is deleted in {days_left} days.",
        )

    if stage in ("day_10", "day_22"):  # delete action — fires just before deletion
        return pkg(
            f"@{username}'s data is being deleted now, the way this said it would be back "
            f"on day one. Rebuilding later means starting from zero.",
            f"@{username}'s data has been deleted",
            f"@{username} deleted",
            f"@{username}'s data has been permanently deleted.",
        )

    # Fallback (should not happen — every stage above is enumerated in STAGES).
    return pkg(
        f"@{username}: an update on your bot's plan.",
        f"Update on @{username}",
        "Bot plan update",
        f"An update on @{username}.",
    )
