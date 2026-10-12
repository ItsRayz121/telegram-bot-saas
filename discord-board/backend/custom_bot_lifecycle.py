"""Custom-bot lifecycle for Guildizer: warn, pause, then delete after Pro lapses.

Ported from Telegizer's custom_bot_lifecycle (logic copied, not imported).

White-label bots need the owner to manage at least one Pro server (custom_bots_api
enforces this when a bot is connected). Until now, when that Pro lapsed the bot's
gateway client kept running forever. This is the stage machine that ends that:

    detected lapse -> notice -> reminder -> PAUSE -> retention reminder -> DELETE

Timeline (days after the lapse was first detected), each stage at most once per bot:
    notice 0 · reminder 5 · pause 7 · retention reminder 17 · delete 22

Safety:
  * DRY RUN is the default (CUSTOM_BOT_LIFECYCLE_DRY_RUN=1): every stage is evaluated
    and logged, but nothing is sent, paused or deleted. Flip to 0 only after reading
    the [custom_bot_lifecycle][DRY_RUN] lines for a day or two.
  * CUSTOM_BOT_LIFECYCLE_ENABLED=0 stops the whole tick instantly.
  * Exactly once per (bot, stage): a stage is claimed by inserting a row into
    custom_bot_lifecycle_stages (primary key bot_id + stage) before acting. Safe to
    re-run, safe across redeploys and a second worker.
  * Never skips ahead: only ONE stage runs per bot per tick, and every stage waits
    a minimum gap after the previous one (so re-enabling the switch after a long
    pause cannot jump from "notice" to "delete" in a few days).
  * Re-gaining Pro at any point before deletion cancels everything and clears the
    stages, so a later lapse starts again from the notice.
  * Only a bot whose owner has NO managed Pro server is touched. A bot whose owner
    still has Pro is never paused or deleted.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import CustomBot, CustomBotLifecycleStage, Guild, UserGuild

log = logging.getLogger("guildizer.custom_bot_lifecycle")

# stage -> (days after lapse detection, minimum days after the previous stage)
STAGES = (
    ("notice", 0, 0),
    ("reminder", 5, 2),
    ("pause", 7, 2),
    ("retention_reminder", 17, 5),
    ("delete", 22, 5),
)


def enabled() -> bool:
    return os.environ.get("CUSTOM_BOT_LIFECYCLE_ENABLED", "1") != "0"


def dry_run() -> bool:
    return os.environ.get("CUSTOM_BOT_LIFECYCLE_DRY_RUN", "1") != "0"


def owner_entitled(db, owner_user_id: int) -> bool:
    """Same rule custom_bots_api uses to allow connecting a bot: the owner manages
    at least one Pro server whose plan has not expired."""
    rows = (db.query(Guild)
            .join(UserGuild, UserGuild.guild_id == Guild.id)
            .filter(UserGuild.user_id == owner_user_id, UserGuild.can_manage.is_(True), Guild.plan == "pro")
            .all())
    return any(g.is_pro for g in rows)


def _stage_times(db, bot_id: int) -> dict:
    return {r.stage: r.at for r in db.query(CustomBotLifecycleStage).filter(CustomBotLifecycleStage.bot_id == bot_id).all()}


def next_stage(lapse_started_at, done: dict, now):
    """The one stage that is due now, or None. Pure, for tests.

    ``done`` maps stage -> when it ran. Stages run strictly in order; a stage is due
    when its offset after the lapse has passed AND its minimum gap after the
    previous stage has passed."""
    prev_at = None
    for name, offset_days, gap_days in STAGES:
        if name in done:
            prev_at = done[name]
            continue
        due = lapse_started_at + timedelta(days=offset_days)
        if prev_at is not None:
            due = max(due, prev_at + timedelta(days=gap_days))
        return name if now >= due else None
    return None


def _claim(db, bot_id: int, stage: str, now) -> bool:
    """Insert-or-skip: True only for the one caller that wins the stage."""
    try:
        db.add(CustomBotLifecycleStage(bot_id=bot_id, stage=stage, at=now))
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _winback_line() -> str:
    code = (os.environ.get("CUSTOM_BOT_WINBACK_PROMO") or "").strip()
    return f" Use code {code} at checkout for a discount." if code else ""


def _message(stage: str, bot, days_left: int) -> tuple[str, str, str]:
    name = f"@{bot.bot_username}" if bot.bot_username else "your custom bot"
    tail = (" You can also keep your server running for free on the official Guildizer bot: "
            "disconnect this bot under Custom bots and your server switches back to it.")
    if stage == "notice":
        return (f"Pro ended: {name} will pause in {days_left} days",
                "Custom bots need a Pro server. Renew Pro to keep it running; your settings are kept either way." + _winback_line() + tail,
                "warning")
    if stage == "reminder":
        return (f"{name} pauses in {days_left} days",
                "Renew Pro to keep your custom bot online." + _winback_line() + tail, "warning")
    if stage == "pause":
        return (f"{name} is paused",
                "Pro has ended, so your custom bot was switched off. Nothing was deleted. Renew Pro and press Reactivate to bring it back, "
                f"or it will be removed in {days_left} days." + _winback_line() + tail, "error")
    if stage == "retention_reminder":
        return (f"{name} will be removed in {days_left} days",
                "It has been paused since Pro ended. Renew Pro and reactivate it to keep it." + _winback_line() + tail, "error")
    return (f"{name} was removed",
            "Its Pro server stayed unpaid for 22 days, so the custom bot was disconnected and its servers moved back to the "
            "official Guildizer bot. Your server settings were not touched." + _winback_line(), "error")


def _days_left(stage: str, lapse_started_at, now) -> int:
    target = {"notice": 7, "reminder": 7, "pause": 22, "retention_reminder": 22, "delete": 22}[stage]
    return max(0, target - int((now - lapse_started_at).total_seconds() // 86400))


def run_tick(now=None) -> dict:
    """One daily pass over every custom bot. Returns counters (also logged)."""
    stats = {"checked": 0, "entitled": 0, "reset": 0, "notice": 0, "reminder": 0, "pause": 0,
             "retention_reminder": 0, "delete": 0, "dry_run": dry_run()}
    if not enabled():
        log.info("[custom_bot_lifecycle] disabled (CUSTOM_BOT_LIFECYCLE_ENABLED=0)")
        return stats
    now = now or datetime.utcnow()
    db = SessionLocal()
    try:
        for bot in db.query(CustomBot).order_by(CustomBot.id).all():
            stats["checked"] += 1
            try:
                _process_bot(db, bot, now, stats)
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("[custom_bot_lifecycle] bot %s failed", bot.id)
    finally:
        db.close()
        SessionLocal.remove()
    log.info("[custom_bot_lifecycle]%s %s", "[DRY_RUN]" if stats["dry_run"] else "", stats)
    return stats


def _process_bot(db, bot, now, stats) -> None:
    import access

    if owner_entitled(db, bot.owner_user_id):
        stats["entitled"] += 1
        stale_stages = db.query(CustomBotLifecycleStage).filter(CustomBotLifecycleStage.bot_id == bot.id).count()
        if bot.lapse_started_at is not None or stale_stages:
            if dry_run():
                log.info("[custom_bot_lifecycle][DRY_RUN] bot %s owner has Pro again: would clear the lapse", bot.id)
                return
            # Pro came back before deletion: cancel everything. A PAUSED bot stays
            # paused until its owner presses Reactivate (so a bot never starts
            # running without them knowing).
            db.query(CustomBotLifecycleStage).filter(CustomBotLifecycleStage.bot_id == bot.id).delete(synchronize_session=False)
            bot.lapse_started_at = None
            db.commit()
            stats["reset"] += 1
        return

    if bot.lapse_started_at is None:
        if dry_run():
            log.info("[custom_bot_lifecycle][DRY_RUN] bot %s owner has no Pro server: lapse would start now", bot.id)
            started = now
        else:
            bot.lapse_started_at = now
            db.commit()
            started = now
    else:
        started = bot.lapse_started_at

    done = _stage_times(db, bot.id)
    stage = next_stage(started, done, now)
    if stage is None:
        return
    title, body, kind = _message(stage, bot, _days_left(stage, started, now))

    if dry_run():
        log.info("[custom_bot_lifecycle][DRY_RUN] bot %s (@%s): would run stage '%s': %s", bot.id, bot.bot_username, stage, title)
        stats[stage] += 1
        return

    if not _claim(db, bot.id, stage, now):
        return                      # another worker won this stage
    stats[stage] += 1
    if stage == "pause":
        bot.status = "paused"
        bot.paused_at = now
        bot.pause_reason = "pro_lapsed"
        bot.error_detail = "Paused because Pro ended. Renew Pro, then press Reactivate."
        bot.needs_restart = False
    if stage == "delete":
        owner, bot_id, uname = bot.owner_user_id, bot.id, bot.bot_username
        try:
            db.query(Guild).filter(Guild.custom_bot_id == bot_id).update({"custom_bot_id": None})
            db.query(CustomBotLifecycleStage).filter(CustomBotLifecycleStage.bot_id == bot_id).delete(synchronize_session=False)
            db.delete(bot)
            access.notify(db, owner, title, body, kind)
            db.commit()
        except Exception:
            # Nothing was deleted: give the stage back so the next tick can retry.
            db.rollback()
            db.query(CustomBotLifecycleStage).filter(
                CustomBotLifecycleStage.bot_id == bot_id, CustomBotLifecycleStage.stage == "delete"
            ).delete(synchronize_session=False)
            db.commit()
            raise
        log.warning("[custom_bot_lifecycle] deleted bot %s (@%s)", bot_id, uname)
        return
    access.notify(db, bot.owner_user_id, title, body, kind)
    db.commit()
    log.info("[custom_bot_lifecycle] bot %s stage '%s' done", bot.id, stage)
