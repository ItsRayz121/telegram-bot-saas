"""Engagement Campaigns — Telegram publishing (Phase 3).

Posts a premium-looking campaign announcement with inline buttons into the
group, for BOTH bot lineages:
  - official bot → get_official_bot_loop(), chat = telegram_group_id
  - custom bot   → bot_manager.active_bots[group.bot_id], chat = group.telegram_group_id

Best-effort: a failed post never breaks campaign create/update (callers wrap
this, and we also guard internally). Participation buttons are Telegram
deep-links (`?start=eng_<id>`) that open the user's private chat with the bot;
the DM handler that makes them functional is added in Phase 4.
"""

import asyncio
import html
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def _primary_label(campaign):
    """Label for the primary "do it" button, reflecting the ACTUAL action so the
    member is never told something will be "verified" when nothing is checked:
      • multi-task        → opens a task picker
      • giveaway / raid   → type-specific entry label
      • one-tap verify    → honor/auto mode with no proof to collect
      • everything else   → proof gets collected, so "Submit Proof"
    """
    try:
        if campaign.tasks.count() > 0:
            return "🚀 Take Part"
    except Exception:
        pass
    if campaign.type == "giveaway":
        return "🎉 Enter Giveaway"
    if campaign.type == "raid":
        return "🔁 Join Raid"
    try:
        has_fields = campaign.custom_fields.count() > 0
    except Exception:
        has_fields = False
    if not has_fields and campaign.verification_mode in ("auto", "honor"):
        return "✅ Tap to Verify"
    return "📤 Submit Proof"

_TYPE_EMOJI = {
    "proof_collection": "📝",
    "content_submission": "🎥",
    "social_task": "🔥",
    "giveaway": "🎁",
    "raid": "🐦",
}

# Human labels for raid/social goal keys, in display order.
_RAID_GOALS = [("likes", "Likes"), ("retweets", "Retweets"), ("comments", "Comments"), ("quotes", "Quotes"), ("follows", "Follows")]


def _campaign_targets(campaign):
    """Return (goals_dict, show_publicly) for the action-quota block.

    Raids always advertise their goals; social tasks only show targets when the
    owner opted in (settings.show_targets). Everything else has no quota block."""
    s = campaign.settings or {}
    if campaign.type == "raid":
        return (s.get("raid_goals") or {}), True
    if campaign.type == "social_task":
        return (s.get("social_targets") or {}), bool(s.get("show_targets"))
    return {}, False


def _verified_count(campaign):
    """Count verified submissions for a campaign — the live progress number behind
    the quota countdown. Honor-based tasks verify one submission per participant,
    so this doubles as "how many people have completed the actions". Best-effort:
    any error yields 0 so the post still renders."""
    try:
        from .models import EngagementSubmission
        return EngagementSubmission.query.filter_by(
            campaign_id=campaign.id, status="verified",
        ).count()
    except Exception:
        logger.debug("verified_count failed for %s", getattr(campaign, "id", "?"), exc_info=True)
        return 0


def _targets_line(goals, done):
    """Render the per-action quota with live progress, e.g.
    "🎯 Goals: ✅ 8/50 Likes · ✅ 8/20 Retweets". `done` is the verified count,
    clamped per goal so it never shows more done than the target."""
    parts = []
    for key, label in _RAID_GOALS:
        target = goals.get(key)
        if not target:
            continue
        d = min(int(done), int(target))
        parts.append(f"{d}/{target} {label}")
    return "🎯 <b>Goals:</b> " + " · ".join(parts) if parts else None


def _status_label(campaign):
    """Human status line for the post."""
    if campaign.status != "active":
        return "🔴 Closed"
    if campaign.ends_at:
        remaining = (campaign.ends_at - datetime.utcnow()).total_seconds()
        if remaining <= 0:
            return "🔴 Closed"
        if remaining <= 6 * 3600:
            return "🟠 Ending soon"
    return "🟢 Active"


def _deadline_text(campaign):
    if not campaign.ends_at:
        return None
    now = datetime.utcnow()
    secs = (campaign.ends_at - now).total_seconds()
    if secs <= 0:
        return "ended"
    hours = secs / 3600
    if hours >= 48:
        return f"{int(hours // 24)} days left"
    if hours >= 1:
        return f"{int(hours)}h left"
    return f"{int(secs // 60)}m left"


_PROOF_PHRASE = {
    "url": "a link", "screenshot": "a screenshot", "uid": "your UID",
    "wallet": "your wallet address", "tx_hash": "a transaction hash",
    "username": "your username", "text": "a short answer",
}


def _proof_summary(campaign):
    """One-line description of what a member submits, so the group post sets
    expectations up front. Empty for flows where there's nothing to submit
    (one-tap honor/auto, or the per-action X flow that verifies actions directly;
    multi-task campaigns list their own tasks already)."""
    try:
        if campaign.tasks.count() > 0:
            return ""
    except Exception:
        pass
    try:
        from . import engagement as eng
        if eng.has_action_flow(campaign):
            return ""
    except Exception:
        pass
    try:
        fields = campaign.custom_fields.all()
    except Exception:
        fields = []
    if fields:
        seen = []
        for f in fields:
            phrase = _PROOF_PHRASE.get(getattr(f, "field_type", "text"), "a short answer")
            if phrase not in seen:
                seen.append(phrase)
        return ", ".join(seen)
    # No configured fields → mirror the bot's default proof (see
    # engagement_bot._default_proof_field): honor/auto are one-tap (nothing to
    # show); link mode asks for a link; everything else asks for a screenshot.
    mode = getattr(campaign, "verification_mode", None)
    if mode in ("honor", "auto"):
        return ""
    return "a link" if mode == "link" else "a screenshot"


def build_campaign_message(campaign, bot_username):
    """Return (html_text, InlineKeyboardMarkup) for the group announcement."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    emoji = _TYPE_EMOJI.get(campaign.type, "🚀")
    lines = [f"{emoji} <b>{html.escape(campaign.title or 'New Task')}</b>", ""]

    if campaign.description:
        lines.append(html.escape(campaign.description))
        lines.append("")

    # Multi-task: list the tasks so the group post is self-explanatory (members
    # still complete each one via the picker in their private chat).
    try:
        tasks = campaign.tasks.all()
    except Exception:
        tasks = []
    if tasks:
        lines.append(f"📋 <b>{len(tasks)} tasks:</b>")
        for t in tasks:
            xp = f" — {t.reward_xp} XP" if t.reward_xp else ""
            lines.append(f"• {html.escape(t.title or '')}{xp}")
        lines.append("")

    # Action-quota checklist with live progress (raids always; social tasks when
    # the owner opted to show targets), e.g. "🎯 Goals: ✅ 8/50 Likes · 8/20 Retweets".
    goals, show_targets = _campaign_targets(campaign)
    if show_targets and goals:
        line = _targets_line(goals, _verified_count(campaign))
        if line:
            lines.append(line)

    if campaign.reward_label:
        lines.append(f"🎁 <b>Reward:</b> {html.escape(campaign.reward_label)}")
    if campaign.reward_xp:
        lines.append(f"⭐ <b>XP:</b> {campaign.reward_xp}")

    proof = _proof_summary(campaign)
    if proof:
        lines.append(f"📝 <b>Proof:</b> {proof}")

    deadline = _deadline_text(campaign)
    if deadline:
        lines.append(f"⏳ <b>Deadline:</b> {deadline}")

    lines.append(f"📊 <b>Status:</b> {_status_label(campaign)}")
    lines.append("")
    lines.append("Tap below to take part 👇")

    text = "\n".join(lines)

    # ── Buttons ──────────────────────────────────────────────────────────────
    # Deep-links open the user's PRIVATE chat with the bot (proof stays private).
    # Phase 4 wires the `/start eng_<id>` handler that makes these functional.
    rows = []
    if campaign.task_url:
        open_label = "🐦 Open Tweet" if campaign.type == "raid" else "🔎 Open Task"
        rows.append([InlineKeyboardButton(open_label, url=campaign.task_url)])

    primary = _primary_label(campaign)
    deep = f"https://t.me/{bot_username}?start=eng_{campaign.id}"
    deep_my = f"https://t.me/{bot_username}?start=engmy_{campaign.id}"
    rows.append([
        InlineKeyboardButton(primary, url=deep),
        InlineKeyboardButton("📋 My Submission", url=deep_my),
    ])

    # Leaderboard (Pro owners only) — deep-link renders the board in the user's DM.
    try:
        from . import engagement as eng
        if eng.leaderboard_visible(campaign):
            rows.append([InlineKeyboardButton(
                "🏆 Leaderboard",
                url=f"https://t.me/{bot_username}?start=englb_{campaign.id}",
            )])
    except Exception:
        logger.debug("leaderboard button check failed", exc_info=True)

    # Opt-in: a richer Mini App task page (always via the OFFICIAL bot, since the
    # Mini App validates initData against the official token only). Action-flow
    # campaigns (per-action verify) run entirely in the DM, so for them this button
    # routes to the DM flow instead of the Mini App — one consistent verify path.
    if (campaign.settings or {}).get("enable_miniapp"):
        action_flow = False
        try:
            from . import engagement as eng
            action_flow = eng.has_action_flow(campaign)
        except Exception:
            action_flow = False
        if action_flow:
            rows.append([InlineKeyboardButton(
                "🚀 Open in App", url=f"https://t.me/{bot_username}?start=eng_{campaign.id}")])
        else:
            from .config import Config
            official = (Config.TELEGRAM_BOT_USERNAME or "telegizer_bot").lstrip("@")
            rows.append([InlineKeyboardButton(
                "🚀 Open in App", url=f"https://t.me/{official}?startapp=engtask_{campaign.id}")])

    return text, InlineKeyboardMarkup(rows)


def _resolve_target(campaign):
    """Return (bot, loop, chat_id, bot_username) for the campaign's lineage, or
    (None, None, None, None) if the bot isn't available."""
    if campaign.telegram_group_id:  # official lineage
        from .official_bot import get_official_bot_loop
        from .config import Config
        bot, loop = get_official_bot_loop()
        username = (Config.TELEGRAM_BOT_USERNAME or "telegizer_bot").lstrip("@")
        try:
            chat_id = int(campaign.telegram_group_id)
        except (TypeError, ValueError):
            chat_id = campaign.telegram_group_id
        return bot, loop, chat_id, username

    # custom lineage
    from .models import Group, Bot
    group = Group.query.get(campaign.group_id)
    if not group:
        return None, None, None, None
    from .app import bot_manager
    instance = bot_manager.active_bots.get(group.bot_id)
    if not (instance and instance.application and instance.loop and instance.loop.is_running()):
        return None, None, None, None
    bot_rec = Bot.query.get(group.bot_id)
    username = (bot_rec.bot_username if bot_rec and bot_rec.bot_username else "").lstrip("@")
    try:
        chat_id = int(group.telegram_group_id)
    except (TypeError, ValueError):
        chat_id = group.telegram_group_id
    return instance.application.bot, instance.loop, chat_id, username


def _record_post_result(campaign, *, ok, error=None, message_id=None):
    """Persist the group-post outcome so the dashboard can show Posted / Failed
    and offer a retry. Best-effort; never raises."""
    from .models import db
    from datetime import datetime as _dt
    try:
        if ok:
            campaign.post_status = "posted"
            campaign.post_error = None
            campaign.posted_at = _dt.utcnow()
            if message_id is not None:
                campaign.telegram_message_id = message_id
        else:
            campaign.post_status = "failed"
            campaign.post_error = (str(error) or "Unknown error")[:1000]
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def publish_campaign(campaign):
    """Post the campaign to its Telegram group and store telegram_message_id.
    Returns True on success. Never raises (best-effort). Records post_status so
    the admin can see Posted / Failed and retry from the dashboard."""
    from .models import db

    try:
        bot, loop, chat_id, username = _resolve_target(campaign)
        if not bot or not loop:
            logger.info("publish_campaign: bot offline for campaign %s", campaign.id)
            _record_post_result(
                campaign, ok=False,
                error="Bot is offline — the group post will be retried automatically, "
                      "or use “Post to group” to retry now.",
            )
            return False

        text, keyboard = build_campaign_message(campaign, username)
        kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
            "disable_web_page_preview": True,
        }
        if campaign.message_thread_id:
            kwargs["message_thread_id"] = campaign.message_thread_id

        sent = asyncio.run_coroutine_threadsafe(
            bot.send_message(**kwargs), loop
        ).result(timeout=15)

        _record_post_result(campaign, ok=True, message_id=sent.message_id)

        if campaign.pin_message:
            try:
                asyncio.run_coroutine_threadsafe(
                    bot.pin_chat_message(
                        chat_id=chat_id, message_id=sent.message_id,
                        disable_notification=True,
                    ),
                    loop,
                ).result(timeout=10)
            except Exception as e:
                logger.warning("publish_campaign pin failed for %s: %s", campaign.id, e)

        return True
    except Exception as exc:
        logger.exception("publish_campaign failed for campaign %s", getattr(campaign, "id", "?"))
        try:
            db.session.rollback()
        except Exception:
            pass
        _record_post_result(campaign, ok=False, error=exc)
        return False


def fetch_submission_file(campaign, file_id):
    """Download a submission's screenshot/photo from Telegram and return
    (bytes, content_type), or None if it can't be fetched.

    Uses the campaign's own lineage bot (official or custom) via _resolve_target,
    so the same code serves both boards and we never juggle raw tokens. The file
    lives on Telegram's servers and is only reachable with the bot token, which is
    why the dashboard couldn't show it before. Best-effort: never raises.
    """
    if not file_id:
        return None
    try:
        bot, loop, _chat_id, _username = _resolve_target(campaign)
        if not bot or not loop:
            logger.info("fetch_submission_file: bot offline for campaign %s", getattr(campaign, "id", "?"))
            return None

        tg_file = asyncio.run_coroutine_threadsafe(
            bot.get_file(file_id), loop
        ).result(timeout=15)
        data = asyncio.run_coroutine_threadsafe(
            tg_file.download_as_bytearray(), loop
        ).result(timeout=20)

        # Infer a content type from the file path extension (Telegram photos are
        # JPEG); default to image/jpeg which every browser renders inline.
        path = (getattr(tg_file, "file_path", "") or "").lower()
        if path.endswith(".png"):
            ctype = "image/png"
        elif path.endswith(".webp"):
            ctype = "image/webp"
        elif path.endswith(".gif"):
            ctype = "image/gif"
        elif path.endswith(".pdf"):
            ctype = "application/pdf"
        else:
            ctype = "image/jpeg"
        return bytes(data), ctype
    except Exception:
        logger.info("fetch_submission_file failed for campaign %s file %s",
                    getattr(campaign, "id", "?"), file_id, exc_info=True)
        return None


def edit_campaign_post(campaign):
    """Re-render the already-posted group announcement in place after a content
    edit — new title / reward / deadline / tasks / leaderboard button all refresh.
    Also reconciles the pin state with the (possibly edited) pin_message setting.
    Best-effort: never raises, and only acts on an active, already-posted campaign.
    """
    if campaign.status != "active" or not campaign.telegram_message_id:
        return False
    try:
        bot, loop, chat_id, username = _resolve_target(campaign)
        if not bot or not loop:
            return False
        text, keyboard = build_campaign_message(campaign, username)
        try:
            asyncio.run_coroutine_threadsafe(
                bot.edit_message_text(
                    chat_id=chat_id, message_id=campaign.telegram_message_id,
                    text=text, parse_mode="HTML", reply_markup=keyboard,
                    disable_web_page_preview=True,
                ),
                loop,
            ).result(timeout=15)
        except Exception as e:
            # "message is not modified" → nothing visible changed; treat as success.
            if "not modified" not in str(e).lower():
                raise

        # Reconcile pin state with the (possibly edited) preference.
        try:
            if campaign.pin_message:
                coro = bot.pin_chat_message(
                    chat_id=chat_id, message_id=campaign.telegram_message_id,
                    disable_notification=True,
                )
            else:
                coro = bot.unpin_chat_message(
                    chat_id=chat_id, message_id=campaign.telegram_message_id,
                )
            asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=10)
        except Exception:
            pass
        return True
    except Exception:
        logger.info("edit_campaign_post failed for %s", getattr(campaign, "id", "?"), exc_info=True)
        return False


# In-process throttle for the live progress refresh — Telegram rate-limits edits
# and re-editing on every single verification would risk a 429 (anti-ban rule).
# A dropped edit is harmless: the next verification re-renders the true count.
import time as _time
from .utils.ttl_map import TTLMap
_PROGRESS_MIN_INTERVAL = 4.0   # seconds between progress edits per campaign
_last_progress_edit = TTLMap(_PROGRESS_MIN_INTERVAL)


def refresh_post_progress(campaign):
    """Re-render the group post to update the live action-quota countdown after a
    submission verifies. No-op unless the campaign actually shows a target block,
    so we never edit posts that have no countdown. Throttled per-campaign and
    pin-preserving (unlike edit_campaign_post, it never re-pins). Best-effort."""
    try:
        if campaign.status != "active" or not campaign.telegram_message_id:
            return False
        goals, show_targets = _campaign_targets(campaign)
        if not (show_targets and goals):
            return False
        now = _time.monotonic()
        if now - _last_progress_edit.get(campaign.id, 0) < _PROGRESS_MIN_INTERVAL:
            return False
        _last_progress_edit[campaign.id] = now

        bot, loop, chat_id, username = _resolve_target(campaign)
        if not bot or not loop:
            return False
        text, keyboard = build_campaign_message(campaign, username)
        try:
            asyncio.run_coroutine_threadsafe(
                bot.edit_message_text(
                    chat_id=chat_id, message_id=campaign.telegram_message_id,
                    text=text, parse_mode="HTML", reply_markup=keyboard,
                    disable_web_page_preview=True,
                ),
                loop,
            ).result(timeout=15)
        except Exception as e:
            if "not modified" not in str(e).lower():
                raise
        return True
    except Exception:
        logger.info("refresh_post_progress failed for %s", getattr(campaign, "id", "?"), exc_info=True)
        return False


def close_campaign_post(campaign):
    """On close: strip the participate buttons, unpin, and post a short results
    summary. All best-effort (bot may be offline in this process)."""
    try:
        bot, loop, chat_id, _ = _resolve_target(campaign)
        if not bot or not loop:
            return False
        if campaign.telegram_message_id:
            for coro in (
                bot.edit_message_reply_markup(chat_id=chat_id, message_id=campaign.telegram_message_id, reply_markup=None),
                bot.unpin_chat_message(chat_id=chat_id, message_id=campaign.telegram_message_id),
            ):
                try:
                    asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=10)
                except Exception:
                    pass
        verified = campaign.submissions.filter_by(status="verified").count()
        total = campaign.submissions.count()
        text = (
            f"🏁 <b>{html.escape(campaign.title or 'Campaign')}</b> has closed.\n"
            f"Submissions: {total}  •  Verified: {verified}"
        )
        kwargs = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if campaign.message_thread_id:
            kwargs["message_thread_id"] = campaign.message_thread_id
        try:
            asyncio.run_coroutine_threadsafe(bot.send_message(**kwargs), loop).result(timeout=10)
        except Exception:
            pass
        return True
    except Exception:
        logger.exception("close_campaign_post failed for %s", getattr(campaign, "id", "?"))
        return False


def delete_campaign_post(campaign):
    """Delete the published group announcement from Telegram (unpin first, then
    delete). Returns (ok, error_message). Never raises.

    Telegram only lets a bot delete its own messages within ~48h (and needs delete
    permission in the chat); older / already-gone messages are handled gracefully.
    The caller clears the post-tracking columns on success so the admin can repost.
    """
    if not campaign.telegram_message_id:
        return False, "This campaign hasn't been posted to the group."
    try:
        bot, loop, chat_id, _ = _resolve_target(campaign)
        if not bot or not loop:
            return False, "The bot is offline — try again once it reconnects."
        # Best-effort unpin (ignore failure), then delete.
        try:
            asyncio.run_coroutine_threadsafe(
                bot.unpin_chat_message(chat_id=chat_id, message_id=campaign.telegram_message_id),
                loop,
            ).result(timeout=10)
        except Exception:
            pass
        asyncio.run_coroutine_threadsafe(
            bot.delete_message(chat_id=chat_id, message_id=campaign.telegram_message_id),
            loop,
        ).result(timeout=10)
        return True, None
    except Exception as exc:
        logger.info("delete_campaign_post failed for %s: %s",
                    getattr(campaign, "id", "?"), exc)
        m = str(exc).lower()
        if "message to delete not found" in m or "message can't be found" in m:
            return True, None  # already gone — treat as deleted
        if "message can't be deleted" in m or "can't be deleted" in m:
            return False, ("Telegram won't let the bot delete this message — it may be "
                           "older than 48 hours. You can remove it manually in the group.")
        if "not enough rights" in m or "delete messages" in m:
            return False, "The bot lacks permission to delete messages in this group."
        return False, "Couldn't delete the group post. Please remove it manually if needed."


def notify_submission_review(campaign, submission, *, approved, reason=None, allow_resubmit=False):
    """DM the participant the outcome of an admin review. Records the result on
    the submission (notify_status / notify_error). Best-effort: never raises.

    The user must have started the relevant bot in private for the DM to land;
    if they blocked it or never started it, we store the failure so the admin can
    see it in the panel."""
    from .models import db

    def _persist(status, error=None):
        try:
            submission.notify_status = status
            submission.notify_error = (str(error)[:255] if error else None)
            db.session.commit()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass

    try:
        bot, loop, _chat_id, _username = _resolve_target(campaign)
        if not bot or not loop:
            _persist("failed", "Bot offline")
            return False

        if approved:
            # Credited reward is the task's (multi-task) or the campaign's.
            reward = campaign.reward_xp
            if getattr(submission, "task_id", None):
                from .models import EngagementTask
                _t = EngagementTask.query.get(submission.task_id)
                reward = _t.reward_xp if _t else 0
            credited = reward and getattr(submission, "rewarded", False)
            xp_line = f"\n+{reward} XP has been credited to your account." if credited else ""
            giveaway_line = ""
            if (campaign.reward_label or campaign.type == "giveaway"):
                giveaway_line = "\nYour entry has been submitted for the giveaway."
            text = (
                f"✅ Your task <b>{html.escape(campaign.title or 'submission')}</b> has been approved."
                f"{xp_line}{giveaway_line}"
            )
        else:
            reason_line = f"\nReason: {html.escape(str(reason))}" if reason else ""
            retry_line = "\nPlease submit the correct proof to try again." if allow_resubmit else ""
            text = (
                f"❌ Your submission for <b>{html.escape(campaign.title or 'this task')}</b> was rejected."
                f"{reason_line}{retry_line}"
            )

        try:
            user_chat_id = int(submission.telegram_user_id)
        except (TypeError, ValueError):
            user_chat_id = submission.telegram_user_id

        asyncio.run_coroutine_threadsafe(
            bot.send_message(
                chat_id=user_chat_id, text=text,
                parse_mode="HTML", disable_web_page_preview=True,
            ),
            loop,
        ).result(timeout=10)
        _persist("sent")
        return True
    except Exception as exc:
        # Most common: "bot can't initiate conversation with a user" / "blocked".
        logger.info("notify_submission_review DM failed for sub %s: %s",
                    getattr(submission, "id", "?"), exc)
        _persist("failed", exc)
        return False


def send_campaign_reminder(campaign):
    """Post a short 'ending soon' nudge into the group. Best-effort."""
    try:
        bot, loop, chat_id, _ = _resolve_target(campaign)
        if not bot or not loop:
            return False
        deadline = _deadline_text(campaign) or "soon"
        text = f"⏳ <b>{html.escape(campaign.title or 'Campaign')}</b> ends {deadline} — last chance to take part!"
        kwargs = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if campaign.message_thread_id:
            kwargs["message_thread_id"] = campaign.message_thread_id
        asyncio.run_coroutine_threadsafe(bot.send_message(**kwargs), loop).result(timeout=10)
        return True
    except Exception:
        logger.exception("send_campaign_reminder failed for %s", getattr(campaign, "id", "?"))
        return False
