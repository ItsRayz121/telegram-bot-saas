"""
Assistant Hub — Consent Flow & Group Connection handlers.

These are called from official_bot.py when:
  1. The bot is added to a group (on_my_chat_member with status member/admin)
  2. User responds to consent DM inline keyboard
  3. User responds to intro prompt inline keyboard

All Telegram I/O is async (PTB pattern). All DB writes use flask_app.app_context().

Consent callback_data prefixes:
  hub_consent:start:<telegram_group_id>      — user tapped [✓ Start]
  hub_consent:cancel:<telegram_group_id>     — user tapped [✗ Cancel]
  hub_consent:public_ok:<telegram_group_id>  — public-group warning: Continue
  hub_consent:public_cancel:<telegram_group_id> — public-group warning: Cancel
  hub_intro:send:<telegram_group_id>         — user tapped [✓ Send Brief Introduction]
  hub_intro:skip:<telegram_group_id>         — user tapped [Skip]

Disambiguation callback_data prefixes (custom bots, small private groups):
  hub_classify:hub:<telegram_group_id>:<bot_tag>    — user chose Assistant Hub
  hub_classify:mod:<telegram_group_id>:<bot_tag>    — user chose Community Moderation
  hub_classify:cancel:<telegram_group_id>:<bot_tag> — user chose Remove Me
"""
import logging
import uuid
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest

_log = logging.getLogger(__name__)

# Threshold above which public-group warning is shown
_PUBLIC_GROUP_MEMBER_THRESHOLD = 500


# ── Entry point: called when bot is added to any group ────────────────────────

async def handle_bot_added_to_group(
    bot, flask_app, chat, added_by_tg_id: str,
    hub_bot_id: str | None = None,
):
    """
    Runs when the official or a custom bot is added to a group.

    hub_bot_id: when set, the consent DM is issued for that specific custom
    HubBotIdentity instead of the user's official bot.
    """
    if not added_by_tg_id:
        return

    with flask_app.app_context():
        from ..assistant.hub_models import AssistantHubGlobal, HubBotIdentity, HubConnectedGroup
        from ..models import User, UserTelegramAccount

        # Look up Telegizer user by Telegram ID
        user = _user_by_tg_id(added_by_tg_id)
        if not user:
            _log.debug("Hub consent: no Telegizer account for tg_id=%s", added_by_tg_id)
            return

        telegram_group_id = chat.id
        group_name = chat.title or f"Group {telegram_group_id}"

        # Resolve the bot identity to check for an existing consent record
        if hub_bot_id:
            bot_identity = HubBotIdentity.query.filter_by(
                id=hub_bot_id, user_id=user.id, bot_type="custom"
            ).first()
        else:
            bot_identity = HubBotIdentity.query.filter_by(
                user_id=user.id, bot_type="official"
            ).first()

        if bot_identity:
            existing = HubConnectedGroup.query.filter_by(
                bot_id=bot_identity.id,
                telegram_group_id=telegram_group_id,
            ).first()
            if existing and existing.consent_confirmed_at:
                # Already consented. If the bot had been removed (and we flagged
                # the row 'bot_removed'), re-adding it should silently restore
                # the connection — no need to ask for consent again. A row the
                # user intentionally paused ('user_paused') is left untouched.
                if not existing.is_active and existing.pause_reason == "bot_removed":
                    from ..models import db
                    existing.is_active = True
                    existing.pause_reason = None
                    existing.group_name = group_name
                    db.session.commit()
                    _log.info("Hub: reactivated group %s on re-add", telegram_group_id)
                else:
                    _log.debug("Hub: group %s already consented, skipping DM", telegram_group_id)
                return

        # Detect public group
        is_public = bool(chat.username)
        member_count = 0
        try:
            member_count = await bot.get_chat_member_count(chat.id)
        except Exception:
            pass
        is_large = member_count > _PUBLIC_GROUP_MEMBER_THRESHOLD

        # Send consent DM to the user
        await _send_consent_dm(
            bot=bot,
            telegram_user_id=int(added_by_tg_id),
            telegram_group_id=telegram_group_id,
            group_name=group_name,
            is_public=is_public,
            is_large=is_large,
            member_count=member_count,
            hub_bot_id=hub_bot_id,
        )


async def _send_consent_dm(
    bot, telegram_user_id: int, telegram_group_id: int,
    group_name: str, is_public: bool, is_large: bool,
    member_count: int, hub_bot_id: str | None = None,
):
    """Send the consent DM to the user who added the bot."""

    # If public or large: prepend warning
    warning_text = ""
    if is_public or is_large:
        warning_text = (
            "⚠️ *Note: This looks like a public or large group.*\n"
            "Echo works best in private team groups. "
            "For public community management, use Group Management instead.\n\n"
        )

    text = (
        f"You've added me to *{_esc(group_name)}*.\n\n"
        f"{warning_text}"
        f"Before I start observing, here's what happens:\n"
        f"• I'll analyze messages to surface tasks, reminders, and meetings\n"
        f"• Raw messages are deleted after 72 hours\n"
        f"• Extracted items are stored in your Telegizer account\n"
        f"• Other group members won't be notified automatically\n\n"
        f"Do you want me to start observing this group?"
    )

    # Embed hub_bot_id in callback_data so the confirm handler knows which bot.
    # Format: hub_consent:<action>:<group_id>:<bot_tag>
    # bot_tag is "official" for the official bot (backwards-compatible default).
    bot_tag = hub_bot_id if hub_bot_id else "official"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✓ Start Observing", callback_data=f"hub_consent:start:{telegram_group_id}:{bot_tag}"),
            InlineKeyboardButton("✗ Cancel — Remove Me", callback_data=f"hub_consent:cancel:{telegram_group_id}:{bot_tag}"),
        ]
    ])

    try:
        await bot.send_message(
            chat_id=telegram_user_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    except (Forbidden, BadRequest) as e:
        _log.warning("Hub consent DM failed for tg_user=%s: %s", telegram_user_id, e)


# ── Consent callback handlers ──────────────────────────────────────────────────

async def handle_consent_callback(update, context, flask_app):
    """
    Handles hub_consent:* and hub_intro:* callback_data.
    Returns True if it consumed the callback, False otherwise.
    """
    query = update.callback_query
    if not query:
        return False

    data = query.data or ""
    if not (data.startswith("hub_consent:") or data.startswith("hub_intro:")):
        return False

    await query.answer()

    # Supports both old 3-part format (hub_consent:start:<gid>) and new
    # 4-part format (hub_consent:start:<gid>:<bot_tag>) for in-flight DMs.
    parts = data.split(":")
    if len(parts) < 3:
        return True

    telegram_group_id = int(parts[2])
    telegram_user_id = query.from_user.id
    bot_tag = parts[3] if len(parts) >= 4 else "official"
    hub_bot_id = None if bot_tag == "official" else bot_tag

    if data.startswith("hub_consent:start:"):
        await _confirm_consent(
            query, context.bot, flask_app,
            telegram_user_id, telegram_group_id,
            hub_bot_id=hub_bot_id,
        )

    elif data.startswith("hub_consent:cancel:"):
        await _cancel_consent(query, context.bot, flask_app, telegram_user_id, telegram_group_id)

    elif data.startswith("hub_intro:send:"):
        await _send_group_intro(query, context.bot, flask_app, telegram_user_id, telegram_group_id)

    elif data.startswith("hub_intro:skip:"):
        await _skip_intro(query, flask_app, telegram_user_id, telegram_group_id)

    return True


async def _confirm_consent(
    query, bot, flask_app,
    telegram_user_id: int, telegram_group_id: int,
    hub_bot_id: str | None = None,
):
    """User confirmed consent. Create connected_groups record."""
    with flask_app.app_context():
        from ..models import db
        from ..assistant.hub_models import (
            AssistantHubGlobal, HubBotIdentity, HubBotSettings, HubConnectedGroup
        )
        from ..models import User

        user = _user_by_tg_id(str(telegram_user_id))
        if not user:
            await query.edit_message_text("⚠️ Could not find your Telegizer account. Please connect your Telegram account at telegizer.com/settings.")
            return

        if hub_bot_id:
            # Custom bot path — identity must already exist
            bot_identity = HubBotIdentity.query.filter_by(
                id=hub_bot_id, user_id=user.id, bot_type="custom"
            ).first()
            if not bot_identity:
                await query.edit_message_text("⚠️ Custom bot not found. It may have been deleted.")
                return
        else:
            # Official (Echo) bot path — lazy-create if not exists
            bot_identity = HubBotIdentity.query.filter_by(
                user_id=user.id, bot_type="official"
            ).first()
            if not bot_identity:
                from ..config import Config as _Config
                _echo_username = _Config.ECHO_BOT_USERNAME or _Config.TELEGRAM_BOT_USERNAME or "telegizer_bot"
                bot_identity = HubBotIdentity(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    bot_type="official",
                    display_name="Telegizer Echo",
                    telegram_bot_username=_echo_username,
                    is_active=True,
                )
                db.session.add(bot_identity)
                db.session.flush()

                settings_row = HubBotSettings(
                    id=str(uuid.uuid4()),
                    bot_id=bot_identity.id,
                    user_id=user.id,
                )
                db.session.add(settings_row)

                # Lazy-create global record
                global_rec = AssistantHubGlobal.query.filter_by(user_id=user.id).first()
                if not global_rec:
                    global_rec = AssistantHubGlobal(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        is_enabled=True,
                        default_bot_id=bot_identity.id,
                    )
                    db.session.add(global_rec)
                else:
                    global_rec.is_enabled = True
                    global_rec.default_bot_id = global_rec.default_bot_id or bot_identity.id
                db.session.flush()

        # Get group metadata from Telegram
        group_name = f"Group {telegram_group_id}"
        is_public = False
        member_count = 0
        try:
            chat_obj = await bot.get_chat(telegram_group_id)
            group_name = chat_obj.title or group_name
            is_public = bool(chat_obj.username)
            member_count = await bot.get_chat_member_count(telegram_group_id)
        except Exception:
            pass

        # Check plan limits before creating record
        from ..assistant.hub_plan_limits import check_connected_groups, PlanLimitError
        try:
            check_connected_groups(
                user_id=user.id,
                bot_id=bot_identity.id,
                bot_type=bot_identity.bot_type,
                plan=user.subscription_tier or "free",
            )
        except PlanLimitError as e:
            await query.edit_message_text(
                f"⚠️ *Group limit reached*\n\n"
                f"Your {e.plan.capitalize()} plan allows {e.max_allowed} connected group(s).\n\n"
                f"Upgrade your plan or pause an existing group to connect this one.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Upsert connected_groups record
        existing = HubConnectedGroup.query.filter_by(
            bot_id=bot_identity.id,
            telegram_group_id=telegram_group_id,
        ).first()

        if existing:
            existing.consent_confirmed_at = datetime.utcnow()
            existing.is_active = True
            existing.pause_reason = None
            existing.group_name = group_name
            existing.is_public_group = is_public
            existing.member_count_at_join = member_count
        else:
            existing = HubConnectedGroup(
                id=str(uuid.uuid4()),
                bot_id=bot_identity.id,
                user_id=user.id,
                telegram_group_id=telegram_group_id,
                group_name=group_name,
                is_active=True,
                consent_confirmed_at=datetime.utcnow(),
                is_public_group=is_public,
                member_count_at_join=member_count,
            )
            db.session.add(existing)

        db.session.commit()

    # Edit the consent message
    await query.edit_message_text(
        f"✅ *{_esc(group_name)} connected.*\n\n"
        f"I'll silently observe this group and surface tasks, decisions, and meetings in your Hub.",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Send intro prompt as a follow-up message
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✓ Send Brief Introduction", callback_data=f"hub_intro:send:{telegram_group_id}"),
            InlineKeyboardButton("Skip", callback_data=f"hub_intro:skip:{telegram_group_id}"),
        ]
    ])
    try:
        await bot.send_message(
            chat_id=telegram_user_id,
            text=(
                "Do you want to let the group know I'm here?\n\n"
                "This is recommended — it lets other members know their messages are being analyzed."
            ),
            reply_markup=keyboard,
        )
    except Exception:
        pass


# ── Custom bot: small private group disambiguation ────────────────────────────

async def send_group_type_dm(
    bot, flask_app, chat, added_by_tg_id: str,
    hub_bot_id: str | None = None,
    member_count: int = 0,
):
    """
    Send a disambiguation DM when a custom bot is added to a small private group
    (< 10 members). Asks the owner to choose between Assistant Hub and Community
    Moderation so the group lands in the right section of the dashboard.
    """
    if not added_by_tg_id:
        return

    with flask_app.app_context():
        user = _user_by_tg_id(added_by_tg_id)
        if not user:
            _log.debug("Group classify DM: no Telegizer account for tg_id=%s", added_by_tg_id)
            return

        from ..assistant.hub_models import HubConnectedGroup
        from ..models import TelegramGroup

        telegram_group_id = chat.id
        group_name = chat.title or f"Group {telegram_group_id}"

        # Skip if already classified in either system
        existing_hub = HubConnectedGroup.query.filter_by(
            telegram_group_id=telegram_group_id,
            user_id=user.id,
        ).first()
        existing_mod = TelegramGroup.query.filter_by(
            telegram_group_id=str(telegram_group_id),
            owner_user_id=user.id,
            bot_status="active",
        ).first()
        if existing_hub or existing_mod:
            return

    member_str = f"{member_count} member{'s' if member_count != 1 else ''}"
    text = (
        f"You've added me to *{_esc(group_name)}* ({member_str}).\n\n"
        f"This is a small private group. How should I be used here?\n\n"
        f"🤖 *Echo* — I observe silently and surface tasks, reminders, and meetings "
        f"in your personal dashboard. No moderation.\n\n"
        f"🛡 *Community Moderation* — I manage the group with welcome messages, rules enforcement, "
        f"anti-spam, and member verification."
    )

    bot_tag_str = hub_bot_id if hub_bot_id else "official"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🤖 Echo",
                callback_data=f"hub_classify:hub:{telegram_group_id}:{bot_tag_str}",
            ),
            InlineKeyboardButton(
                "🛡 Community Moderation",
                callback_data=f"hub_classify:mod:{telegram_group_id}:{bot_tag_str}",
            ),
        ],
        [
            InlineKeyboardButton(
                "✗ Remove Me",
                callback_data=f"hub_classify:cancel:{telegram_group_id}:{bot_tag_str}",
            ),
        ],
    ])

    try:
        await bot.send_message(
            chat_id=int(added_by_tg_id),
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    except (Forbidden, BadRequest) as e:
        _log.warning("Group classify DM failed for tg_user=%s: %s", added_by_tg_id, e)


async def handle_classify_callback(update, context, flask_app):
    """
    Handles hub_classify:* callbacks from the group type disambiguation DM.
    Returns True if it consumed the callback, False otherwise.
    """
    query = update.callback_query
    if not query:
        return False

    data = query.data or ""
    if not data.startswith("hub_classify:"):
        return False

    await query.answer()

    parts = data.split(":")
    if len(parts) < 4:
        return True

    action = parts[1]           # "hub", "mod", or "cancel"
    telegram_group_id = int(parts[2])
    bot_tag = parts[3]
    hub_bot_id = None if bot_tag == "official" else bot_tag
    telegram_user_id = query.from_user.id

    if action == "hub":
        # User chose Assistant Hub — send the standard consent DM
        group_name = f"Group {telegram_group_id}"
        member_count = 0
        try:
            chat_obj = await context.bot.get_chat(telegram_group_id)
            group_name = chat_obj.title or group_name
            member_count = await context.bot.get_chat_member_count(telegram_group_id)
        except Exception:
            pass

        await query.edit_message_text(
            f"🤖 Setting up *{_esc(group_name)}* as an Echo group...",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_consent_dm(
            bot=context.bot,
            telegram_user_id=telegram_user_id,
            telegram_group_id=telegram_group_id,
            group_name=group_name,
            is_public=False,
            is_large=False,
            member_count=member_count,
            hub_bot_id=hub_bot_id,
        )

    elif action == "mod":
        await _create_group_management_record(
            query=query,
            bot=context.bot,
            flask_app=flask_app,
            telegram_user_id=telegram_user_id,
            telegram_group_id=telegram_group_id,
            hub_bot_id=hub_bot_id,
        )

    elif action == "cancel":
        await query.edit_message_text("Got it. I'll leave the group now. No data was collected.")
        try:
            await context.bot.leave_chat(telegram_group_id)
        except Exception as e:
            _log.debug("Hub classify: leave_chat failed for %s: %s", telegram_group_id, e)

    return True


async def _create_group_management_record(
    query, bot, flask_app,
    telegram_user_id: int, telegram_group_id: int,
    hub_bot_id: str | None = None,
):
    """Create a TelegramGroup record for the Community Moderation path."""
    group_name = f"Group {telegram_group_id}"
    try:
        chat_obj = await bot.get_chat(telegram_group_id)
        group_name = chat_obj.title or group_name
    except Exception:
        pass

    with flask_app.app_context():
        from ..models import db, TelegramGroup
        from datetime import datetime as _dt

        user = _user_by_tg_id(str(telegram_user_id))
        if not user:
            await query.edit_message_text(
                "⚠️ Could not find your Telegizer account. "
                "Please connect your Telegram account at telegizer.com/settings."
            )
            return

        group_id_str = str(telegram_group_id)
        tg = TelegramGroup.query.filter_by(telegram_group_id=group_id_str).first()
        if not tg:
            tg = TelegramGroup(
                telegram_group_id=group_id_str,
                title=group_name,
                bot_status="active",
                owner_user_id=user.id,
                linked_at=_dt.utcnow(),
                linked_via_bot_type="custom",
                group_context="group_management",
            )
            db.session.add(tg)
        elif not tg.owner_user_id or tg.bot_status != "active":
            tg.owner_user_id = user.id
            tg.bot_status = "active"
            tg.linked_at = _dt.utcnow()
            tg.linked_via_bot_type = "custom"
            tg.group_context = "group_management"

        db.session.commit()

        from ..config import Config as _Config
        frontend = getattr(_Config, "FRONTEND_URL", "https://telegizer.com")

    await query.edit_message_text(
        f"✅ *{_esc(group_name)}* added to Community Moderation.\n\n"
        f"Open your dashboard to configure moderation settings for this group.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "⚙️ Open Dashboard",
                url=f"{frontend}/group-management",
            )],
        ]),
    )


async def _cancel_consent(query, bot, flask_app, telegram_user_id: int, telegram_group_id: int):
    """User cancelled. Bot leaves the group. No DB record created."""
    await query.edit_message_text(
        "Got it. I'll leave the group now. No data was collected."
    )
    try:
        await bot.leave_chat(telegram_group_id)
    except Exception as e:
        _log.debug("Hub: leave_chat failed for %s: %s", telegram_group_id, e)


async def _send_group_intro(query, bot, flask_app, telegram_user_id: int, telegram_group_id: int):
    """Send an introduction message to the group (public groups only)."""
    with flask_app.app_context():
        from ..models import db
        from ..assistant.hub_models import HubConnectedGroup, HubBotIdentity

        user = _user_by_tg_id(str(telegram_user_id))
        if user:
            # Find the HubConnectedGroup for this group regardless of bot type
            group = HubConnectedGroup.query.filter(
                HubConnectedGroup.telegram_group_id == telegram_group_id,
                HubConnectedGroup.user_id == user.id,
            ).first()
            if group:
                # Private groups: observe silently, never send intro messages
                if not group.is_public_group:
                    await query.edit_message_text(
                        "✅ Group connected. I'll observe silently — no intro message sent to private groups."
                    )
                    return

                group.intro_sent = True
                db.session.commit()

                first_name = user.full_name.split()[0] if user.full_name else "the owner"
                try:
                    await bot.send_message(
                        chat_id=telegram_group_id,
                        text=(
                            f"👋 Hi, I'm Telegizer Assistant. I'll help {first_name} track "
                            f"tasks and meetings from this group. I won't respond to messages "
                            f"unless @mentioned."
                        ),
                    )
                except Exception as e:
                    _log.warning("Hub intro send failed for group %s: %s", telegram_group_id, e)

    await query.edit_message_text(
        "✅ Introduction sent to the group."
    )


async def _skip_intro(query, flask_app, telegram_user_id: int, telegram_group_id: int):
    """User skipped intro. intro_sent stays FALSE."""
    await query.edit_message_text(
        "Skipped. The group won't be notified. I'll start observing silently."
    )


# ── Helper ─────────────────────────────────────────────────────────────────────

def _user_by_tg_id(tg_id: str):
    from ..models import User, UserTelegramAccount
    user = User.query.filter_by(telegram_user_id=str(tg_id)).first()
    if not user:
        acct = UserTelegramAccount.query.filter_by(telegram_user_id=str(tg_id)).first()
        if acct:
            user = User.query.get(acct.user_id)
    return user


def _esc(text: str) -> str:
    """Minimal Markdown escaping for group names in PTB MarkdownV1."""
    return text.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")

