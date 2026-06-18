import asyncio
import logging
import threading
from datetime import datetime, timedelta
import re
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, filters, ContextTypes,
)
try:
    from telegram.ext import MessageReactionHandler as _MessageReactionHandler
    _REACTION_HANDLER_AVAILABLE = True
except ImportError:
    _REACTION_HANDLER_AVAILABLE = False

from .bot_features.group_context import GroupContext
from .bot_features.verification import VerificationSystem
from .bot_features.welcome import WelcomeSystem
from .bot_features.levels import LevelSystem
from .bot_features.moderation import ModerationSystem
from .bot_features.knowledge_base import KnowledgeBaseSystem

logger = logging.getLogger(__name__)

# Set during process shutdown (SIGTERM / atexit) so polling threads stop cleanly
# and shutdown-time crashes are NOT recorded as real failures. See Part 7/8:
# the "cannot schedule new futures after interpreter shutdown" RuntimeError is a
# teardown race, not an outage — once this is set we break out silently.
_SHUTTING_DOWN = threading.Event()


def signal_bots_shutting_down():
    """Mark the process as shutting down. Idempotent; called by stop_all()."""
    _SHUTTING_DOWN.set()


def is_shutting_down() -> bool:
    return _SHUTTING_DOWN.is_set()


# ── Shared display-name helpers ────────────────────────────────────────────────

def _display_name(tg_user) -> str:
    """Full display name from a python-telegram-bot User object."""
    first = (getattr(tg_user, "first_name", None) or "").strip()
    last = (getattr(tg_user, "last_name", None) or "").strip()
    username = (getattr(tg_user, "username", None) or "").strip()
    full = " ".join(x for x in [first, last] if x)
    if full:
        return full
    if username:
        return f"@{username}"
    return f"User {tg_user.id}"


def _display_name_member(member) -> str:
    """Full display name from a Member ORM row (has first_name/last_name/username)."""
    first = (member.first_name or "").strip()
    last = (getattr(member, "last_name", None) or "").strip()
    username = (member.username or "").strip()
    full = " ".join(x for x in [first, last] if x)
    if full:
        return full
    if username:
        return f"@{username}"
    return f"User {member.telegram_user_id}"


def _mask_wallet(addr: str) -> str:
    """Show first 6 and last 4 chars of a wallet address."""
    if len(addr) <= 12:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def _html_escape(text: str) -> str:
    """Minimal HTML escaping for safe use in parse_mode=HTML messages."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


# ── Command routing helpers ───────────────────────────────────────────────────

def _is_command_allowed(settings: dict, command: str, thread_id) -> bool:
    """Return True if `command` may be used in the given forum thread_id.

    Logic:
    - No command_routing config → always allowed (safe default).
    - scope "all_group" → allowed everywhere.
    - scope "disabled" → never allowed.
    - scope "specific_topics" → allowed only when thread_id is in topic_ids list.
    - General Chat messages have thread_id == None; a topic rule with no ids
      blocks them too.
    """
    routing = settings.get("command_routing") if settings else None
    if not routing:
        return True
    commands_cfg = routing.get("commands") or {}
    cmd_rule = commands_cfg.get(command) or commands_cfg.get(command.lstrip("/"))
    if not cmd_rule:
        return True
    scope = cmd_rule.get("scope", "all_group")
    if scope == "all_group":
        return True
    if scope == "disabled":
        return False
    # specific_topics
    allowed_ids = [str(t) for t in (cmd_rule.get("topic_ids") or [])]
    if not allowed_ids:
        return False
    return str(thread_id) in allowed_ids if thread_id is not None else False


async def _send_routing_rejection(update, settings: dict, command: str):
    """Send the configured rejection reply (or stay silent) for a blocked command."""
    routing = (settings or {}).get("command_routing", {})
    if routing.get("restricted_reply", "silent") == "message":
        msg_tpl = routing.get(
            "restricted_message",
            "⚠️ This command is only available in the {topic} topic.",
        )
        commands_cfg = routing.get("commands") or {}
        cmd_rule = commands_cfg.get(command) or commands_cfg.get(command.lstrip("/")) or {}
        topic_ids = cmd_rule.get("topic_ids") or []
        topics = routing.get("topics") or []
        topic_names = [
            t["name"] for t in topics if str(t.get("thread_id")) in [str(x) for x in topic_ids]
        ]
        topic_label = ", ".join(topic_names) if topic_names else "a specific topic"
        try:
            await update.message.reply_text(msg_tpl.format(topic=topic_label))
        except Exception:
            pass


def _capture_topic(group, thread_id, topic_name):
    """Upsert a topic entry in group.settings['command_routing']['topics'] and
    in the group_forum_topics DB table.

    Returns True if the settings dict was mutated (caller must flag_modified / commit).
    The DB upsert is best-effort and does not affect the return value.
    """
    if not group or thread_id is None:
        return False
    settings = group.settings or {}
    routing = settings.setdefault("command_routing", {
        "topics": [], "commands": {}, "restricted_reply": "silent",
        "restricted_message": "⚠️ This command is only available in the {topic} topic.",
    })
    topics = routing.setdefault("topics", [])
    tid = str(thread_id)
    name = topic_name or f"Topic {tid}"
    settings_mutated = False
    for t in topics:
        if str(t.get("thread_id")) == tid:
            if topic_name and t.get("name") != topic_name:
                t["name"] = topic_name
                settings_mutated = True
            break
    else:
        topics.append({"thread_id": tid, "name": name})
        settings_mutated = True

    # Persist to group_forum_topics table (best-effort — uses group.telegram_group_id)
    try:
        from .models import db as _db, GroupForumTopic
        from datetime import datetime as _dt
        tg_id = str(group.telegram_group_id)
        existing = GroupForumTopic.query.filter_by(
            telegram_group_id=tg_id, thread_id=int(thread_id)
        ).first()
        if existing:
            existing.last_seen_at = _dt.utcnow()
            if topic_name and existing.name != topic_name:
                existing.name = topic_name
        else:
            _db.session.add(GroupForumTopic(
                telegram_group_id=tg_id,
                thread_id=int(thread_id),
                name=name,
            ))
    except Exception:
        pass

    return settings_mutated


async def _auto_delete(bot, chat_id, message_id, delay):
    """Delete a message after `delay` seconds. Logs but does not raise on failure."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.debug(f"Auto-delete msg {message_id} in chat {chat_id}: {e}")


class BotInstance:

    def __init__(self, bot_id, token, app_context):
        self.bot_id = bot_id
        self.token = token
        self.app_context = app_context
        self.application = None
        self.thread = None
        self.loop = None
        self._stop_event = threading.Event()

        self.verification = VerificationSystem(app_context, self)
        self.welcome = WelcomeSystem(app_context)
        self.levels = LevelSystem(app_context)
        self.moderation = ModerationSystem(app_context)
        self.knowledge_base = KnowledgeBaseSystem(app_context)

    def _record_health_error(self, detail: str):
        """Record a polling failure for the admin Bot Health tab. Never raises."""
        try:
            from .health import record_bot_error
            with self.app_context.app_context():
                record_bot_error("custom", self.bot_id, "handler", detail)
        except Exception:
            pass

    def _get_group(self, chat_id):
        with self.app_context.app_context():
            from .models import Bot, Group
            bot = Bot.query.get(self.bot_id)
            if not bot:
                return None
            group = Group.query.filter_by(
                bot_id=self.bot_id,
                telegram_group_id=str(chat_id),
            ).first()
            if not group:
                return None
            return GroupContext.from_group(group)

    async def _get_or_create_group(self, chat_id, chat_title=None, bot=None, chat_type="group", chat_username=None):
        member_count = None
        if bot:
            try:
                member_count = await bot.get_chat_member_count(chat_id)
            except Exception:
                pass
        with self.app_context.app_context():
            from .database import DatabaseManager
            group = DatabaseManager.get_or_create_group(
                self.bot_id, chat_id, chat_title, member_count, chat_type=chat_type,
                chat_username=chat_username,
            )
            if not group:
                return None
            return GroupContext.from_group(group)

    # ── internal helpers ───────────────────────────────────────────────────────

    def _frontend(self):
        return self.app_context.config.get("FRONTEND_URL", "https://telegizer.com")

    def _official_bot_username(self):
        raw = self.app_context.config.get("TELEGRAM_BOT_USERNAME", "telegizer_bot")
        return raw.strip().lstrip("@").split("/")[-1]

    def _app_deeplink(self, start_param="dashboard"):
        """Telegram-authenticated entry point for a CUSTOM bot.

        Custom bots cannot launch the Mini App directly (it validates initData against
        the official bot token only). So we route through the OFFICIAL bot's Main Mini
        App via a t.me deep link: it authenticates the user with Telegram, then the Mini
        App reads `start_param` to land on the right page. This gives every bot —
        official or custom — a real Telegram-authenticated session.

        start_param must be [A-Za-z0-9_-], max 64 chars. Use "grp_<botId>_<groupId>" to
        open a specific group, or "dashboard" for the home view.
        """
        return f"https://t.me/{self._official_bot_username()}?startapp={start_param}"

    def _find_website_user(self, tg_user_id):
        """Safe wrapper: return User linked to Telegram ID or None."""
        try:
            from .models import User, UserTelegramAccount
            tg_id_str = str(tg_user_id)
            # Check primary column first
            u = User.query.filter_by(telegram_user_id=tg_id_str).first()
            if u:
                return u
            # Check junction table
            ta = UserTelegramAccount.query.filter_by(telegram_user_id=tg_id_str).first()
            if ta:
                return User.query.get(ta.user_id)
        except Exception as e:
            logger.debug("_find_website_user tg=%s: %s", tg_user_id, e)
        return None

    def _build_main_menu_keyboard(self, frontend, bot_username, is_linked,
                                  pending_count=0, email_verified=False):
        """Build the standard main menu via the shared lineage builder.

        Custom (Lineage A) bot — section buttons route through the official bot's
        Mini App deep link so the user gets a real Telegram-authenticated session.
        """
        from .bot_features.bot_ui import build_main_menu
        echo_un = self.app_context.config.get("ECHO_BOT_USERNAME")
        return build_main_menu(
            frontend=frontend,
            official_username=self._official_bot_username(),
            echo_username=echo_un,
            is_official=False,
            is_linked=is_linked,
            email_verified=email_verified,
            pending_count=pending_count,
        )

    # ── /start ─────────────────────────────────────────────────────────────────

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type != "private":
            await update.message.reply_text(
                "✅ I'm active here! Use /linkgroup to connect this group to your dashboard. "
                "DM me /start for the Quick Settings menu.",
            )
            return

        user = update.effective_user
        first = user.first_name or "there"
        frontend = self._frontend()
        official_un = self._official_bot_username()
        bot_username = context.bot.username or official_un

        is_linked = False
        owner_name = None
        pending_count = 0

        with self.app_context.app_context():
            from .models import Bot, TelegramGroupLinkCode, TelegramGroup
            from datetime import datetime as _dt
            bot_rec = Bot.query.get(self.bot_id)
            owner_name = bot_rec.owner.full_name if bot_rec and bot_rec.owner else None
            website_user = self._find_website_user(user.id)
            is_linked = website_user is not None
            email_verified = bool(website_user and getattr(website_user, "email_verified", False))

            if website_user:
                pending_count = TelegramGroupLinkCode.query.filter_by(
                    created_by_telegram_user_id=str(user.id),
                    used_at=None,
                ).filter(TelegramGroupLinkCode.expires_at > _dt.utcnow()).count()

        managed_by = f"\n👤 Managed by <b>{owner_name}</b>" if owner_name else ""
        text = (
            f"👋 <b>Welcome, {first}!</b>{managed_by}\n\n"
            f"⚡ Powered by <b>Telegizer</b> · @{official_un}\n\n"
            "<b>What I can do in your groups:</b>\n"
            "• 🛡 AutoMod — links, spam, bad words, caps filter\n"
            "• ✅ Verification — protect against bots &amp; raiders\n"
            "• 📊 XP &amp; Levels — reward active members\n"
            "• 🤖 AI Assistant — auto-answer from knowledge base\n"
            "• 📅 Scheduler — timed announcements\n"
            "• 📈 Analytics — member &amp; engagement tracking\n"
            "• ⚡ Automations — triggers, custom commands\n"
            "• 📣 Welcome Messages — greet new members\n\n"
            "<i>Add me to a group as admin, then run /linkgroup there.</i>"
        )

        keyboard = self._build_main_menu_keyboard(
            frontend, bot_username, is_linked, pending_count, email_verified
        )
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    # ── /help ──────────────────────────────────────────────────────────────────

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the same control center / feature overview as /start."""
        await self.handle_start(update, context)

    # ── /support ───────────────────────────────────────────────────────────────

    async def handle_support(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        frontend = self._frontend()
        official_un = self._official_bot_username()
        await update.message.reply_text(
            "💬 <b>Need help?</b>\n\n"
            f"• Open your dashboard: {frontend}/dashboard\n"
            f"• Message the Telegizer team: @{official_un}\n"
            f"• Help center: {frontend}/support",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    # ── /status ────────────────────────────────────────────────────────────────

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            # DM: show linked groups for this bot
            frontend = self._frontend()
            with self.app_context.app_context():
                from .models import Group
                groups = Group.query.filter_by(bot_id=self.bot_id).order_by(Group.created_at.desc()).all()
                group_data = [{"id": g.id, "name": g.group_name or "Unnamed Group"} for g in groups]

            if not group_data:
                await update.message.reply_text(
                    "📋 <b>No groups linked yet.</b>\n\n"
                    "Add this bot to a group as admin and run /linkgroup there.",
                    parse_mode="HTML",
                )
                return

            lines = [f"📋 <b>Linked Groups ({len(group_data)})</b>\n"]
            buttons = []
            for g in group_data[:10]:
                lines.append(f"• <b>{g['name']}</b>")
                buttons.append([InlineKeyboardButton(
                    f"⚙️ {g['name']}",
                    url=self._app_deeplink(f"grp_{self.bot_id}_{g['id']}"),
                )])

            await update.message.reply_text(
                "\n".join(lines),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        else:
            # Group: show group link status
            chat = update.effective_chat
            frontend = self._frontend()
            with self.app_context.app_context():
                from .models import Group
                grp = Group.query.filter_by(
                    bot_id=self.bot_id,
                    telegram_group_id=str(chat.id),
                ).first()
                linked = grp is not None

            if linked:
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚙️ Open Dashboard", url=self._app_deeplink(f"grp_{self.bot_id}_{grp.id}")),
                ]])
                await update.message.reply_text(
                    f"✅ <b>{chat.title}</b> is linked to Telegizer.\nUse the button to manage it.",
                    parse_mode="HTML", reply_markup=kb,
                )
            else:
                await update.message.reply_text(
                    "⏳ This group is not linked yet.\nRun /linkgroup to connect it to your dashboard.",
                )

    # ── /linkgroup ─────────────────────────────────────────────────────────────

    async def handle_linkgroup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Link this group to the user's Telegizer dashboard account."""
        chat = update.effective_chat
        user = update.effective_user
        frontend = self._frontend()
        official_un = self._official_bot_username()
        bot_username = context.bot.username or official_un

        if chat.type == "private":
            await update.message.reply_text(
                "⚠️ Use /linkgroup <b>inside your Telegram group</b>, not here.",
                parse_mode="HTML",
            )
            return

        # Anonymous admins post via @GroupAnonymousBot, so their real identity (and
        # admin rights) can't be verified and no code can be DMed — guide them to
        # post visibly instead of showing the generic "only admins" error.
        from .bot_features.bot_ui import is_anonymous_admin, ANON_ADMIN_LINKGROUP_HTML
        if is_anonymous_admin(update):
            await update.message.reply_text(ANON_ADMIN_LINKGROUP_HTML, parse_mode="HTML")
            return

        try:
            cm = await context.bot.get_chat_member(chat.id, user.id)
            if cm.status not in ("creator", "administrator"):
                await update.message.reply_text("❌ Only group admins can link this group.")
                return
        except Exception:
            pass

        group_id = str(chat.id)
        group_title = chat.title or "Untitled Group"

        already_linked = False
        linked_user_id = None
        code = None
        limit_hit = None
        redirect_to_hub = False

        # Private groups (no public username) connected via a custom bot belong in
        # Assistant Hub, not Group Management. Detect this before entering the DB block.
        is_private_group = not chat.username

        with self.app_context.app_context():
            from .models import db, Group, TelegramGroup, TelegramGroupLinkCode, Bot, CustomBot
            from datetime import datetime as _dt, timedelta as _td

            website_user = self._find_website_user(user.id)

            # Check if this polling instance belongs to a custom bot (match by username)
            bot_rec = Bot.query.get(self.bot_id)
            custom_bot_match = (
                CustomBot.query.filter_by(
                    bot_username=bot_rec.bot_username,
                    owner_user_id=bot_rec.user_id,
                ).first()
                if bot_rec and bot_rec.bot_username else None
            )
            is_custom_bot = bool(custom_bot_match)

            # Private group + custom bot → route to Assistant Hub only.
            # The Hub consent DM was already sent when the bot was added; skip creating
            # a Group Management record so the group doesn't appear in the wrong section.
            if is_custom_bot and is_private_group and website_user:
                redirect_to_hub = True
                db.session.commit()
            else:
                # Get or create the TelegramGroup record
                tg = TelegramGroup.query.filter_by(telegram_group_id=group_id).first()
                if not tg:
                    tg = TelegramGroup(
                        telegram_group_id=group_id,
                        title=group_title,
                        username=chat.username,
                        bot_status="pending",
                    )
                    db.session.add(tg)
                    db.session.flush()

                if tg.owner_user_id and tg.bot_status == "active":
                    already_linked = True
                    db.session.commit()
                elif website_user:
                    from .config import Config
                    max_groups = Config.MAX_OFFICIAL_GROUPS.get(website_user.subscription_tier, 3)
                    current_count = TelegramGroup.query.filter_by(
                        owner_user_id=website_user.id, is_disabled=False,
                    ).count()
                    if max_groups != -1 and current_count >= max_groups:
                        limit_hit = (max_groups, website_user.subscription_tier)
                        db.session.commit()
                    else:
                        tg.owner_user_id = website_user.id
                        tg.bot_status = "active"
                        tg.linked_at = _dt.utcnow()
                        tg.linked_via_bot_type = "custom"
                        # Stamp the owning CustomBot so admin views and member-sync
                        # can attribute the group to its real bot (was hard-coded
                        # None, which mis-labeled every legacy-linked group as official).
                        tg.linked_bot_id = custom_bot_match.id if custom_bot_match else None
                        tg.group_context = "group_management"
                        TelegramGroupLinkCode.query.filter_by(
                            telegram_group_id=group_id,
                            created_by_telegram_user_id=str(user.id),
                            used_at=None,
                        ).update({"expires_at": _dt.utcnow()})
                        db.session.commit()
                        linked_user_id = website_user.id
                else:
                    # Code flow — no website account linked yet
                    TelegramGroupLinkCode.query.filter_by(
                        telegram_group_id=group_id,
                        used_at=None,
                    ).filter(
                        TelegramGroupLinkCode.expires_at > _dt.utcnow()
                    ).update({"expires_at": _dt.utcnow()})

                    code = TelegramGroupLinkCode.generate_code()
                    while TelegramGroupLinkCode.query.filter_by(code=code).first():
                        code = TelegramGroupLinkCode.generate_code()

                    link_code = TelegramGroupLinkCode(
                        code=code,
                        telegram_group_id=group_id,
                        telegram_group_title=group_title,
                        created_by_telegram_user_id=str(user.id),
                        expires_at=_dt.utcnow() + _td(minutes=15),
                    )
                    db.session.add(link_code)
                    db.session.commit()

        if redirect_to_hub:
            await update.message.reply_text(
                "🤖 <b>Private groups use Echo.</b>\n\n"
                "Your bot is already active as an AI assistant for this group. "
                "Open your dashboard to confirm the connection and configure it.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Echo", url=self._app_deeplink("echo"))],
                ]),
            )
            return

        if limit_hit:
            max_n, tier = limit_hit
            await update.message.reply_text(
                f"⚠️ Your {tier.capitalize()} plan allows {max_n} linked group(s).\n\n"
                f"Upgrade to Pro for unlimited groups at {frontend}/billing",
            )
            return

        if already_linked:
            await update.message.reply_text(
                "✅ This group is already linked to a Telegizer account.\nUse /status to view details.",
            )
            return

        if linked_user_id:
            await update.message.reply_text(
                f"✅ <b>{group_title}</b> has been linked to your Telegizer account!\n\nView it in your dashboard.",
                parse_mode="HTML",
            )
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"✅ <b>Group linked!</b>\n\n<b>{group_title}</b> is now in your dashboard.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 My Groups", url=self._app_deeplink("mygroups"))],
                    ]),
                )
            except Exception:
                pass
            return

        # Code flow
        await update.message.reply_text(
            f"✅ Link request created.\n\nOpen @{bot_username} privately to get your secure code.",
        )
        private_text = (
            f"🔐 <b>Group Link Code</b>\n\n"
            f"Group: <b>{group_title}</b>\n\n"
            f"<code>{code}</code>\n\n"
            f"⏱ Expires in 15 minutes — single use only.\n\n"
            f"Paste at: {frontend}/my-groups\n\n"
            f"<i>Connect your Telegram account in Settings to skip codes in future.</i>"
        )
        try:
            await context.bot.send_message(
                chat_id=user.id, text=private_text, parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖥️ Open My Groups", url=self._app_deeplink("mygroups"))],
                ]),
            )
        except Exception:
            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"⚠️ @{user.username or user.first_name}, I couldn't DM you.\n"
                         f"Start a private chat with @{bot_username} first, then run /linkgroup again.",
                )
            except Exception:
                pass

    # ── menu callback dispatcher ────────────────────────────────────────────────

    async def _handle_menu_callback(self, query, user, data, own_username=None):
        """Handle all menu:* callback queries from the /start menu."""
        frontend = self._frontend()
        official_un = self._official_bot_username()
        # own_username: the username of THIS bot (may differ from official bot for custom bots)
        if not own_username:
            try:
                with self.app_context.app_context():
                    from .models import Bot as _BotM
                    _br = _BotM.query.get(self.bot_id)
                    own_username = (_br.bot_username if _br else None) or official_un
            except Exception:
                own_username = official_un

        # ── Back to main menu ─────────────────────────────────────────────────
        if data == "menu:main":
            is_linked = False
            pending_count = 0
            email_verified = False
            with self.app_context.app_context():
                from datetime import datetime as _dt
                from .models import TelegramGroupLinkCode
                website_user = self._find_website_user(user.id)
                is_linked = website_user is not None
                email_verified = bool(website_user and getattr(website_user, "email_verified", False))
                if website_user:
                    pending_count = TelegramGroupLinkCode.query.filter_by(
                        created_by_telegram_user_id=str(user.id), used_at=None,
                    ).filter(TelegramGroupLinkCode.expires_at > _dt.utcnow()).count()

            keyboard = self._build_main_menu_keyboard(
                frontend, own_username, is_linked, pending_count, email_verified
            )
            await query.edit_message_text(
                "👋 <b>Telegizer Hub</b>\n\nChoose an option below:",
                parse_mode="HTML", reply_markup=keyboard,
            )
            return

        # ── Account info ──────────────────────────────────────────────────────
        if data == "menu:account_info":
            email = None
            with self.app_context.app_context():
                u = self._find_website_user(user.id)
                if u:
                    email = u.email
            text = (
                f"✅ <b>Account Connected</b>\n\nLinked to: <code>{email}</code>\n\n"
                "Groups you add will appear in your dashboard automatically."
            ) if email else (
                f"ℹ️ No Telegizer account linked.\n\nVisit {frontend}/settings to connect."
            )
            await query.edit_message_text(
                text, parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖥️ Open Dashboard", url=self._app_deeplink("dashboard"))],
                    [InlineKeyboardButton("⚙️ Settings", url=self._app_deeplink("settings"))],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        # ── My Groups ─────────────────────────────────────────────────────────
        if data == "menu:my_groups":
            groups = []
            is_linked = False
            with self.app_context.app_context():
                from .models import TelegramGroup
                u = self._find_website_user(user.id)
                is_linked = u is not None
                if u:
                    gs = TelegramGroup.query.filter_by(
                        owner_user_id=u.id, is_disabled=False,
                    ).order_by(TelegramGroup.linked_at.desc()).limit(10).all()
                    groups = [{"title": g.title, "status": g.bot_status} for g in gs]

            if not is_linked:
                await query.edit_message_text(
                    "📋 <b>My Groups</b>\n\nConnect your Telegizer account to see your groups here.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔗 Connect Account", url=self._app_deeplink("settings"))],
                        [InlineKeyboardButton("« Back", callback_data="menu:main")],
                    ]),
                )
                return

            if not groups:
                text = "📋 <b>My Groups</b>\n\nNo linked groups yet.\nAdd me to a group and run /linkgroup."
                kb = [
                    [InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group")],
                    [InlineKeyboardButton("🖥️ Open Dashboard", url=self._app_deeplink("mygroups"))],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]
            else:
                icons = {"active": "🟢", "pending": "🟡", "removed": "🔴"}
                lines = ["📋 <b>My Linked Groups</b>\n"]
                for g in groups:
                    lines.append(f"{icons.get(g['status'], '⚪')} {g['title']}")
                text = "\n".join(lines)
                kb = [
                    [InlineKeyboardButton("🖥️ Manage on Dashboard", url=self._app_deeplink("mygroups"))],
                    [InlineKeyboardButton("➕ Add Another Group", callback_data="menu:add_group")],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]
            await query.edit_message_text(text, parse_mode="HTML",
                                          reply_markup=InlineKeyboardMarkup(kb))
            return

        # ── Add Group ─────────────────────────────────────────────────────────
        if data == "menu:add_group":
            add_url = f"https://t.me/{own_username}?startgroup=setup"
            await query.edit_message_text(
                "<b>Add Group to Telegizer</b>\n\n"
                "1️⃣ Add me to your group using the button below\n"
                "2️⃣ In the group, run /linkgroup\n"
                "3️⃣ If your account is connected, it links automatically\n"
                "   Otherwise paste the code from here into the dashboard",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add Bot to Group", url=add_url)],
                    [InlineKeyboardButton("🖥️ Dashboard → My Groups", url=self._app_deeplink("mygroups"))],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        # ── AI Assistant ──────────────────────────────────────────────────────
        if data == "menu:ai_assistant":
            await query.edit_message_text(
                "🧠 <b>Telegizer AI Assistant</b>\n\n"
                "I'm your AI co-pilot — type anything naturally in this chat!\n\n"
                "<b>Examples:</b>\n"
                "• \"Schedule a meeting Friday 3pm\"\n"
                "• \"Remind me tomorrow morning about the proposal\"\n"
                "• \"What's happening in my groups?\"\n"
                "• \"Create task: review analytics — high priority\"\n\n"
                "<b>Group Management:</b>\n"
                "• \"Any moderation issues today?\"\n"
                "• \"Show me top members this week\"\n"
                "• \"Analyze my group's activity\"\n\n"
                "<i>Just send me a message below to get started!</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖥️ Open AI Workspace", url=self._app_deeplink("workspace"))],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        # ── Support ───────────────────────────────────────────────────────────
        if data == "menu:support":
            await query.edit_message_text(
                "<b>Telegizer Support</b>\n\n"
                "📢 <b>Official Channel</b> — updates &amp; announcements\n"
                "👥 <b>Community Group</b> — help from other users\n"
                "✉️ <b>Email</b> — fazalelahi5577@gmail.com",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Official Channel", url="https://t.me/telegizer")],
                    [InlineKeyboardButton("👥 Community Group", url="https://t.me/telegizer_community")],
                    [InlineKeyboardButton("✉️ Email Support", url="mailto:fazalelahi5577@gmail.com")],
                    [InlineKeyboardButton("« Back", callback_data="menu:main")],
                ]),
            )
            return

        # ── Pending groups ────────────────────────────────────────────────────
        if data == "menu:pending_groups":
            pending = []
            with self.app_context.app_context():
                from datetime import datetime as _dt
                from .models import TelegramGroupLinkCode, TelegramGroup
                codes = TelegramGroupLinkCode.query.filter_by(
                    created_by_telegram_user_id=str(user.id), used_at=None,
                ).filter(TelegramGroupLinkCode.expires_at > _dt.utcnow()).all()
                for c in codes:
                    tg = TelegramGroup.query.filter_by(telegram_group_id=c.telegram_group_id).first()
                    if tg and not tg.owner_user_id:
                        pending.append({"title": tg.title or c.telegram_group_title, "code": c.code})

            if not pending:
                text = "✅ <b>No groups awaiting setup.</b>\n\nRun /linkgroup in a group to generate a code."
                kb = [[InlineKeyboardButton("« Back", callback_data="menu:main")]]
            else:
                lines = ["<b>Groups Awaiting Setup</b>\n"]
                for p in pending:
                    lines.append(f"• {p['title']}")
                text = "\n".join(lines)
                kb = (
                    [[InlineKeyboardButton(f"📋 {p['title']}", callback_data=f"show_code:{p['code']}")] for p in pending[:5]]
                    + [[InlineKeyboardButton("🖥️ Open Dashboard", url=self._app_deeplink("mygroups"))],
                       [InlineKeyboardButton("« Back", callback_data="menu:main")]]
                )
            await query.edit_message_text(text, parse_mode="HTML",
                                          reply_markup=InlineKeyboardMarkup(kb))
            return

        # ── Show individual link code ─────────────────────────────────────────
        if data.startswith("show_code:"):
            code = data.split(":", 1)[1]
            valid = False
            group_title = ""
            with self.app_context.app_context():
                from datetime import datetime as _dt
                from .models import TelegramGroupLinkCode
                lc = TelegramGroupLinkCode.query.filter_by(
                    code=code,
                    created_by_telegram_user_id=str(user.id),
                    used_at=None,
                ).filter(TelegramGroupLinkCode.expires_at > _dt.utcnow()).first()
                if lc:
                    valid = True
                    group_title = lc.telegram_group_title or ""

            if not valid:
                await query.edit_message_text(
                    "⚠️ This code has expired or already been used.\nRun /linkgroup in the group again.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("« Back", callback_data="menu:pending_groups")],
                    ]),
                )
                return

            frontend = self._frontend()
            await query.edit_message_text(
                f"🔐 <b>Link Code for {group_title}</b>\n\n"
                f"<code>{code}</code>\n\n"
                f"Paste at: {frontend}/my-groups\n\n"
                "<i>Single use · expires in 15 min</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🖥️ Open My Groups", url=self._app_deeplink("mygroups"))],
                    [InlineKeyboardButton("« Back", callback_data="menu:pending_groups")],
                ]),
            )
            return

    # ── Quick Settings inline toggle panel ────────────────────────────────────

    _QS_FEATURES = [
        ("automod",       "automod.enabled",               "🛡 AutoMod"),
        ("verification",  "verification.enabled",          "✅ Verification"),
        ("welcome",       "welcome.enabled",               "👋 Welcome Messages"),
        ("levels",        "levels.enabled",                "📊 XP / Levels"),
        ("ai_reply",      "knowledge_base.auto_reply_enabled", "🤖 AI Auto-Reply"),
    ]

    @staticmethod
    def _qs_get(settings: dict, dotkey: str) -> bool:
        keys = dotkey.split(".")
        val = settings
        for k in keys:
            val = val.get(k, {}) if isinstance(val, dict) else {}
        return bool(val)

    @staticmethod
    def _qs_set(settings: dict, dotkey: str, value: bool) -> dict:
        import copy
        s = copy.deepcopy(settings) if settings else {}
        keys = dotkey.split(".")
        node = s
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        return s

    def _qs_toggle_keyboard(self, group_id: int, settings: dict, frontend: str) -> InlineKeyboardMarkup:
        rows = []
        for feat_key, dotkey, label in self._QS_FEATURES:
            on = self._qs_get(settings, dotkey)
            state = "🟢 ON" if on else "🔴 OFF"
            rows.append([InlineKeyboardButton(
                f"{label}  {state}",
                callback_data=f"qs:toggle:{group_id}:{feat_key}",
            )])
        rows.append([InlineKeyboardButton("🌐 Full Settings on Web", url=self._app_deeplink(f"grp_{self.bot_id}_{group_id}"))])
        rows.append([InlineKeyboardButton("« Back", callback_data="menu:main")])
        return InlineKeyboardMarkup(rows)

    async def _handle_qs_callback(self, query, user, data: str):
        frontend = self._frontend()
        parts = data.split(":")

        # qs:groups — show group selector
        if data == "qs:groups":
            groups = []
            with self.app_context.app_context():
                from .models import Group
                gs = Group.query.filter_by(bot_id=self.bot_id).limit(10).all()
                groups = [{"id": g.id, "title": g.group_name or f"Group {g.id}"} for g in gs]

            if not groups:
                await query.edit_message_text(
                    "⚙️ <b>Quick Settings</b>\n\nNo groups linked to this bot yet.\n"
                    "Add me to a group and run /linkgroup first.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("« Back", callback_data="menu:main")],
                    ]),
                )
                return

            if len(groups) == 1:
                # Skip selector, go straight to toggle panel
                await self._handle_qs_callback(query, user, f"qs:group:{groups[0]['id']}")
                return

            rows = [[InlineKeyboardButton(g["title"], callback_data=f"qs:group:{g['id']}")] for g in groups]
            rows.append([InlineKeyboardButton("« Back", callback_data="menu:main")])
            await query.edit_message_text(
                "⚙️ <b>Quick Settings</b>\n\nChoose a group to configure:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(rows),
            )
            return

        # qs:group:{id} — show toggle panel
        if len(parts) == 3 and parts[1] == "group":
            group_id = int(parts[2])
            settings = {}
            title = ""
            with self.app_context.app_context():
                from .models import Group
                g = Group.query.get(group_id)
                if not g:
                    await query.edit_message_text("⚠️ Group not found.")
                    return
                settings = dict(g.settings or {})
                title = g.group_name or f"Group {group_id}"

            await query.edit_message_text(
                f"⚙️ <b>Quick Settings — {title}</b>\n\nTap any feature to toggle it on/off instantly:",
                parse_mode="HTML",
                reply_markup=self._qs_toggle_keyboard(group_id, settings, frontend),
            )
            return

        # qs:toggle:{group_id}:{feat_key} — flip setting, re-render
        if len(parts) == 4 and parts[1] == "toggle":
            group_id = int(parts[2])
            feat_key = parts[3]
            dotkey = next((d for k, d, _ in self._QS_FEATURES if k == feat_key), None)
            if not dotkey:
                await query.answer("Unknown feature.", show_alert=True)
                return

            new_val = False
            settings = {}
            title = ""
            with self.app_context.app_context():
                from .models import db, Group
                from sqlalchemy.orm.attributes import flag_modified
                g = Group.query.get(group_id)
                if not g:
                    await query.answer("Group not found.", show_alert=True)
                    return
                settings = dict(g.settings or {})
                current = self._qs_get(settings, dotkey)
                new_val = not current
                g.settings = self._qs_set(settings, dotkey, new_val)
                flag_modified(g, "settings")
                db.session.commit()
                settings = dict(g.settings)
                title = g.group_name or f"Group {group_id}"

            label = next((l for k, _, l in self._QS_FEATURES if k == feat_key), feat_key)
            await query.answer(f"{label} {'enabled' if new_val else 'disabled'}")
            await query.edit_message_text(
                f"⚙️ <b>Quick Settings — {title}</b>\n\nTap any feature to toggle it on/off instantly:",
                parse_mode="HTML",
                reply_markup=self._qs_toggle_keyboard(group_id, settings, frontend),
            )
            return

        await query.answer("Unknown action.", show_alert=True)

    async def handle_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            await update.message.reply_text("This command must be used in a group.")
            return

        try:
            chat_member = await context.bot.get_chat_member(
                update.effective_chat.id, update.effective_user.id
            )
            if chat_member.status not in ("creator", "administrator"):
                await update.message.reply_text("❌ Only admins can access settings.")
                return
        except Exception:
            return

        with self.app_context.app_context():
            frontend_url = self.app_context.config.get("FRONTEND_URL", "http://localhost:3000")

        try:
            group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
            if not group:
                await update.message.reply_text("❌ Could not load group data. Please try again.")
                return
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "⚙️ Open Dashboard",
                    url=f"{frontend_url}/bot/{self.bot_id}/group/{group.id}",
                )]
            ])
            await update.message.reply_text(
                "⚙️ Manage this group from the dashboard:",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"handle_settings error (bot={self.bot_id}, chat={update.effective_chat.id}): {e}", exc_info=True)
            await update.message.reply_text("❌ An error occurred loading settings. Please try again.")

    async def handle_rank(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return

        thread_id = getattr(update.message, "message_thread_id", None)
        user = update.effective_user
        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)

        if not _is_command_allowed(group.settings, "/rank", thread_id):
            await _send_routing_rejection(update, group.settings, "/rank")
            return

        with self.app_context.app_context():
            from .models import Member
            member = Member.query.filter_by(
                group_id=group.id,
                telegram_user_id=str(user.id),
            ).first()

            if not member:
                await update.message.reply_text("You have no rank yet. Start chatting!")
                return

            total = Member.query.filter_by(group_id=group.id).count()
            rank = Member.query.filter(
                Member.group_id == group.id,
                Member.xp > member.xp,
            ).count() + 1

        display = _display_name(user)
        rank_image = self.levels.generate_rank_card(member, rank, total, group.settings)
        if rank_image:
            await update.message.reply_photo(
                photo=rank_image,
                caption=f"🏆 Rank card for {display}",
            )
        else:
            await update.message.reply_text(
                f"📊 <b>{_html_escape(display)}'s Rank</b>\n"
                f"Level: {member.level}  |  XP: {member.xp:,}\n"
                f"Rank: #{rank} of {total}\n"
                f"Role: {member.role.replace('_', ' ').title()}",
                parse_mode="HTML",
            )

    async def handle_leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return

        thread_id = getattr(update.message, "message_thread_id", None)
        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)

        if not _is_command_allowed(group.settings, "/leaderboard", thread_id):
            await _send_routing_rejection(update, group.settings, "/leaderboard")
            return

        with self.app_context.app_context():
            from .models import Member
            top_members = (
                Member.query.filter_by(group_id=group.id)
                .order_by(Member.xp.desc())
                .limit(10)
                .all()
            )

        if not top_members:
            await update.message.reply_text("No members yet!")
            return

        medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        lines = ["🏆 <b>Leaderboard</b>\n"]
        for i, m in enumerate(top_members):
            name = _display_name_member(m)
            lines.append(f"{medals[i]} {_html_escape(name)} — Level {m.level} ({m.xp:,} XP)")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _deny_admin_command(self, update, context):
        """#7 — a non-admin used an admin-only command. Delete their message (if the
        group setting is on) and log it silently — never spam the group with a reply.

        No DM is sent: a custom bot cannot reliably confirm the user has started it,
        and the rule is to never DM users who haven't started the bot.
        """
        msg = update.message
        user = update.effective_user
        chat_id = update.effective_chat.id
        command = ""
        if msg and msg.text:
            command = msg.text.split()[0].lstrip("/").split("@")[0]

        delete_unauth = True
        try:
            with self.app_context.app_context():
                from .models import Group
                from .database import DatabaseManager
                grp = Group.query.filter_by(
                    bot_id=self.bot_id, telegram_group_id=str(chat_id)
                ).first()
                if grp:
                    delete_unauth = (grp.settings or {}).get("automod", {}).get(
                        "delete_unauthorized_commands", True
                    )
                    try:
                        DatabaseManager.log_action(
                            group_id=grp.id,
                            action_type="unauthorized_command",
                            target_user_id=str(user.id) if user else None,
                            target_username=(user.username if user else None),
                            reason=f"/{command} (non-admin)",
                        )
                    except Exception:
                        pass
        except Exception:
            pass

        if delete_unauth and msg:
            try:
                await msg.delete()
            except Exception:
                pass

    async def _require_admin_target(self, update, context):
        chat_id = update.effective_chat.id
        caller = update.effective_user

        try:
            caller_member = await context.bot.get_chat_member(chat_id, caller.id)
            if caller_member.status not in ("creator", "administrator"):
                await self._deny_admin_command(update, context)
                return None, None
        except Exception:
            return None, None

        target = None
        if update.message.reply_to_message:
            target = update.message.reply_to_message.from_user
        elif context.args:
            username = context.args[0].lstrip("@")
            try:
                chat_member = await context.bot.get_chat_member(chat_id, username)
                target = chat_member.user
            except Exception:
                await update.message.reply_text("❌ User not found.")
                return None, None

        if not target:
            await update.message.reply_text("❌ Reply to a message or provide a username.")
            return None, None

        return caller, target

    async def handle_warn(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return

        reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else "No reason provided"
        if update.message.reply_to_message:
            reason = " ".join(context.args) if context.args else "No reason provided"

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        await self.moderation.warn_user(
            context.bot,
            update.effective_chat.id,
            target.id,
            target.username or target.first_name,
            caller.id,
            caller.username or caller.first_name,
            reason,
            group,
        )
        with self.app_context.app_context():
            from .database import DatabaseManager
            penalty = group.settings.get("levels", {}).get("xp_penalty_warn", -10)
            if penalty < 0:
                DatabaseManager.apply_xp_penalty(group.id, target.id, penalty)

    async def handle_ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return

        reason = " ".join(context.args[1:]) if context.args else "No reason"
        if update.message.reply_to_message:
            reason = " ".join(context.args) if context.args else "No reason"

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)

        auto_delete = group.settings.get("moderation", {}).get("auto_delete_action_seconds", 0)
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, target.id)
            sent = await update.message.reply_text(
                f"🚫 {target.first_name} has been banned.\nReason: {reason}"
            )
            if auto_delete and sent:
                asyncio.ensure_future(_auto_delete(context.bot, update.effective_chat.id, sent.message_id, auto_delete))
            with self.app_context.app_context():
                from .database import DatabaseManager
                DatabaseManager.log_action(
                    group_id=group.id,
                    action_type="ban",
                    target_user_id=str(target.id),
                    target_username=target.username,
                    moderator_id=str(caller.id),
                    moderator_username=caller.username,
                    reason=reason,
                )
                penalty = group.settings.get("levels", {}).get("xp_penalty_ban", -50)
                if penalty < 0:
                    DatabaseManager.apply_xp_penalty(group.id, target.id, penalty)
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to ban: {e}")

    async def handle_kick(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return

        reason = " ".join(context.args) if context.args else "No reason"
        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)

        auto_delete = group.settings.get("moderation", {}).get("auto_delete_action_seconds", 0)
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, target.id)
            await context.bot.unban_chat_member(update.effective_chat.id, target.id)
            sent = await update.message.reply_text(
                f"👢 {target.first_name} has been kicked.\nReason: {reason}"
            )
            if auto_delete and sent:
                asyncio.ensure_future(_auto_delete(context.bot, update.effective_chat.id, sent.message_id, auto_delete))
            with self.app_context.app_context():
                from .database import DatabaseManager
                DatabaseManager.log_action(
                    group_id=group.id,
                    action_type="kick",
                    target_user_id=str(target.id),
                    target_username=target.username,
                    moderator_id=str(caller.id),
                    moderator_username=caller.username,
                    reason=reason,
                )
                penalty = group.settings.get("levels", {}).get("xp_penalty_kick", -30)
                if penalty < 0:
                    DatabaseManager.apply_xp_penalty(group.id, target.id, penalty)
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to kick: {e}")

    async def handle_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return

        duration = 60
        reason = "No reason"
        if context.args:
            try:
                duration = int(context.args[0] if not update.message.reply_to_message else context.args[0])
                reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason"
            except (ValueError, IndexError):
                reason = " ".join(context.args)

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        until_date = datetime.utcnow() + timedelta(minutes=duration)

        auto_delete = group.settings.get("moderation", {}).get("auto_delete_action_seconds", 0)
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=target.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date,
            )
            sent = await update.message.reply_text(
                f"🔇 {target.first_name} has been muted for {duration} minutes.\nReason: {reason}"
            )
            if auto_delete and sent:
                asyncio.ensure_future(_auto_delete(context.bot, update.effective_chat.id, sent.message_id, auto_delete))
            with self.app_context.app_context():
                from .database import DatabaseManager
                DatabaseManager.log_action(
                    group_id=group.id,
                    action_type="mute",
                    target_user_id=str(target.id),
                    target_username=target.username,
                    moderator_id=str(caller.id),
                    moderator_username=caller.username,
                    reason=reason,
                    extra_data={"duration_minutes": duration},
                )
                penalty = group.settings.get("levels", {}).get("xp_penalty_mute", -20)
                if penalty < 0:
                    DatabaseManager.apply_xp_penalty(group.id, target.id, penalty)
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to mute: {e}")

    async def handle_unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)

        auto_delete = group.settings.get("moderation", {}).get("auto_delete_action_seconds", 0)
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=target.id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
            sent = await update.message.reply_text(f"🔊 {target.first_name} has been unmuted.")
            if auto_delete and sent:
                asyncio.ensure_future(_auto_delete(context.bot, update.effective_chat.id, sent.message_id, auto_delete))
            with self.app_context.app_context():
                from .database import DatabaseManager
                DatabaseManager.log_action(
                    group_id=group.id,
                    action_type="unmute",
                    target_user_id=str(target.id),
                    target_username=target.username,
                    moderator_id=str(caller.id),
                    moderator_username=caller.username,
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to unmute: {e}")

    async def handle_tempban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return

        duration_hours = 24
        reason = "No reason"
        if context.args:
            try:
                duration_hours = int(context.args[0] if not update.message.reply_to_message else context.args[0])
                reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason"
            except (ValueError, IndexError):
                reason = " ".join(context.args)

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        until_date = datetime.utcnow() + timedelta(hours=duration_hours)

        auto_delete = group.settings.get("moderation", {}).get("auto_delete_action_seconds", 0)
        try:
            await context.bot.ban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=target.id,
                until_date=until_date,
            )
            sent = await update.message.reply_text(
                f"⏳ {target.first_name} banned for {duration_hours}h.\nReason: {reason}"
            )
            if auto_delete and sent:
                asyncio.ensure_future(_auto_delete(context.bot, update.effective_chat.id, sent.message_id, auto_delete))
            with self.app_context.app_context():
                from .database import DatabaseManager
                DatabaseManager.log_action(
                    group_id=group.id,
                    action_type="tempban",
                    target_user_id=str(target.id),
                    target_username=target.username,
                    moderator_id=str(caller.id),
                    moderator_username=caller.username,
                    reason=reason,
                    extra_data={"duration_hours": duration_hours},
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to tempban: {e}")

    async def handle_tempmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.handle_mute(update, context)

    async def handle_userinfo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return

        target = None
        if update.message.reply_to_message:
            target = update.message.reply_to_message.from_user
        else:
            target = update.effective_user

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)

        with self.app_context.app_context():
            from .models import Member
            member = Member.query.filter_by(
                group_id=group.id,
                telegram_user_id=str(target.id),
            ).first()

        if not member:
            await update.message.reply_text("No data found for this user.")
            return

        wallet_line = f"Wallet: `{member.wallet_address}`" if member.wallet_address else "Wallet: Not submitted"
        await update.message.reply_text(
            f"👤 *User Info*\n"
            f"Name: {member.first_name or 'Unknown'}\n"
            f"Username: @{member.username or 'none'}\n"
            f"Level: {member.level}\n"
            f"XP: {member.xp:,}\n"
            f"Role: {member.role.replace('_', ' ').title()}\n"
            f"Warnings: {member.warnings}\n"
            f"Verified: {'✅' if member.is_verified else '❌'}\n"
            f"Muted: {'🔇' if member.is_muted else '🔊'}\n"
            f"Joined: {member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown'}\n"
            f"{wallet_line}",
            parse_mode="Markdown",
        )

    async def handle_auditlog(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return

        try:
            chat_member = await context.bot.get_chat_member(
                update.effective_chat.id, update.effective_user.id
            )
            if chat_member.status not in ("creator", "administrator"):
                await update.message.reply_text("❌ Admins only.")
                return
        except Exception:
            return

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)

        with self.app_context.app_context():
            from .models import AuditLog
            logs = (
                AuditLog.query.filter_by(group_id=group.id)
                .order_by(AuditLog.timestamp.desc())
                .limit(10)
                .all()
            )

        if not logs:
            await update.message.reply_text("No audit logs yet.")
            return

        lines = ["📋 *Recent Audit Log*\n"]
        for log in logs:
            lines.append(
                f"• `{log.action_type}` — {log.target_username or log.target_user_id} "
                f"by {log.moderator_username or 'AutoMod'}\n"
                f"  {log.timestamp.strftime('%m/%d %H:%M')} — {log.reason or 'No reason'}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def handle_purge(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return

        try:
            chat_member = await context.bot.get_chat_member(
                update.effective_chat.id, update.effective_user.id
            )
            if chat_member.status not in ("creator", "administrator"):
                await update.message.reply_text("❌ Admins only.")
                return
        except Exception:
            return

        if not update.message.reply_to_message:
            await update.message.reply_text("Reply to the first message you want to delete.")
            return

        count = 0
        try:
            limit = int(context.args[0]) if context.args else 10
            limit = min(limit, 100)
        except ValueError:
            limit = 10

        from_msg_id = update.message.reply_to_message.message_id
        to_msg_id = update.message.message_id

        message_ids = list(range(from_msg_id, to_msg_id + 1))[:limit]
        for msg_id in message_ids:
            try:
                await context.bot.delete_message(update.effective_chat.id, msg_id)
                count += 1
            except Exception:
                pass

        notify = await update.message.reply_text(f"🗑 Purged {count} messages.")
        await asyncio.sleep(5)
        try:
            await notify.delete()
        except Exception:
            pass

    async def handle_me(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        user = update.effective_user
        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        with self.app_context.app_context():
            from .models import Member
            member = Member.query.filter_by(
                group_id=group.id,
                telegram_user_id=str(user.id),
            ).first()
        if not member:
            await update.message.reply_text("You have no stats yet. Start chatting!")
            return
        joined = member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "Unknown"
        await update.message.reply_text(
            f"👤 <b>Your Stats</b>\n"
            f"Level: {member.level}  |  XP: {member.xp:,}\n"
            f"Role: {member.role.replace('_', ' ').title()}\n"
            f"Warnings: {member.warnings}\n"
            f"Access: Active\n"
            f"Joined: {joined}",
            parse_mode="HTML",
        )

    async def handle_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        try:
            admins = await context.bot.get_chat_administrators(update.effective_chat.id)
            lines = ["👮 <b>Group Admins</b>\n"]
            for a in admins:
                name = _display_name(a.user)
                role = "Owner" if a.status == "creator" else "Admin"
                custom = f" · <i>{_html_escape(a.custom_title)}</i>" if getattr(a, "custom_title", None) else ""
                lines.append(f"• {_html_escape(name)} — {role}{custom}")
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(
                f"❌ Could not fetch admins.\nMake sure the bot is an admin with sufficient permissions.",
            )

    async def handle_roles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        roles_cfg = group.settings.get("levels", {}).get("roles", [])

        with self.app_context.app_context():
            from .models import Member
            top = (
                Member.query.filter_by(group_id=group.id)
                .order_by(Member.xp.desc())
                .limit(10)
                .all()
            )

        if not top:
            await update.message.reply_text("No members yet — start chatting to earn XP!")
            return

        def _role_for_level(lvl):
            best = "Member"
            for r in sorted(roles_cfg, key=lambda x: x["level"]):
                if lvl >= r["level"]:
                    best = r["name"]
            return best

        medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        lines = ["🏅 <b>Top Community Members</b>\n"]
        for i, m in enumerate(top):
            name = _display_name_member(m)
            role_name = _role_for_level(m.level)
            lines.append(f"{medals[i]} {_html_escape(name)} — {role_name} · Level {m.level}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def handle_whois(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        try:
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
            if chat_member.status not in ("creator", "administrator"):
                await update.message.reply_text("❌ Admins only.")
                return
        except Exception:
            return

        target = None
        if update.message.reply_to_message:
            target = update.message.reply_to_message.from_user
        elif context.args:
            username = context.args[0].lstrip("@")
            try:
                cm = await context.bot.get_chat_member(update.effective_chat.id, username)
                target = cm.user
            except Exception:
                await update.message.reply_text("❌ User not found.")
                return
        if not target:
            await update.message.reply_text("Reply to a message or provide @username.")
            return

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        with self.app_context.app_context():
            from .models import Member
            member = Member.query.filter_by(
                group_id=group.id,
                telegram_user_id=str(target.id),
            ).first()
        if not member:
            await update.message.reply_text("No data found for this user.")
            return
        name = _display_name_member(member)
        wallet_line = f"Wallet: <code>{_html_escape(_mask_wallet(member.wallet_address))}</code>" if member.wallet_address else "Wallet: Not submitted"
        joined = member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "Unknown"
        await update.message.reply_text(
            f"🔍 <b>Whois: {_html_escape(name)}</b>\n"
            f"Username: {('@' + member.username) if member.username else '—'}\n"
            f"ID: <code>{member.telegram_user_id}</code>\n"
            f"Level: {member.level}  |  XP: {member.xp:,}\n"
            f"Role: {member.role.replace('_', ' ').title()}\n"
            f"Warnings: {member.warnings}\n"
            f"Access: {'Active' if member.is_verified else 'Pending'}\n"
            f"Muted: {'🔇' if member.is_muted else '🔊'}\n"
            f"Joined: {joined}\n"
            f"{wallet_line}",
            parse_mode="HTML",
        )

    async def handle_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user
        in_group = chat.type != "private"

        if not context.args:
            hint = "For privacy, you can also DM this bot directly." if in_group else ""
            await update.message.reply_text(
                "💼 <b>Wallet Submission</b>\n"
                f"Usage: <code>/wallet &lt;your_wallet_address&gt;</code>\n"
                f"Example: <code>/wallet 0xAbC123...</code>\n"
                + (f"\n💡 {hint}" if hint else ""),
                parse_mode="HTML",
            )
            return

        wallet_address = context.args[0].strip()
        # Basic EVM address validation (starts with 0x, 42 chars) or generic min-length check
        import re as _re
        is_evm = bool(_re.fullmatch(r"0x[0-9a-fA-F]{40}", wallet_address))
        if len(wallet_address) < 10:
            await update.message.reply_text("❌ Invalid wallet address. Please provide a valid address.")
            return
        if len(wallet_address) > 500:
            await update.message.reply_text("❌ Wallet address too long.")
            return

        if in_group:
            group = await self._get_or_create_group(chat.id, chat.title, context.bot)
            group_id = group.id
        else:
            # DM — try to find any group this user is a member of for this bot
            group_id = None
            with self.app_context.app_context():
                from .models import Group, Member as _M
                bot_groups = Group.query.filter_by(bot_id=self.bot_id).all()
                for bg in bot_groups:
                    if _M.query.filter_by(group_id=bg.id, telegram_user_id=str(user.id)).first():
                        group_id = bg.id
                        break

            if not group_id:
                await update.message.reply_text(
                    "⚠️ You must be a member of a group managed by this bot before submitting a wallet."
                )
                return

        with self.app_context.app_context():
            from .models import Member, db
            from datetime import datetime as _dt
            member = Member.query.filter_by(
                group_id=group_id,
                telegram_user_id=str(user.id),
            ).first()
            if not member:
                member = Member(
                    group_id=group_id,
                    telegram_user_id=str(user.id),
                    username=user.username,
                    first_name=user.first_name,
                    last_name=getattr(user, "last_name", None),
                )
                db.session.add(member)
            member.wallet_address = wallet_address
            member.wallet_submitted_at = _dt.utcnow()
            db.session.commit()

        # Try to delete the original message in group (hides full address from chat)
        if in_group:
            try:
                await update.message.delete()
            except Exception:
                pass

        masked = _mask_wallet(wallet_address)
        privacy_note = "\n💡 For privacy, use bot DM next time." if in_group else ""
        await update.message.reply_text(
            f"✅ <b>Wallet saved successfully.</b>\n"
            f"Address: <code>{_html_escape(masked)}</code>{privacy_note}",
            parse_mode="HTML",
        )

    async def handle_mywallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        user = update.effective_user

        with self.app_context.app_context():
            from .models import Member
            member = Member.query.filter_by(
                group_id=group.id,
                telegram_user_id=str(user.id),
            ).first()

        if not member or not member.wallet_address:
            await update.message.reply_text(
                "You haven't submitted a wallet yet.\nUse <code>/wallet &lt;address&gt;</code> to submit.",
                parse_mode="HTML",
            )
            return

        submitted = member.wallet_submitted_at.strftime("%Y-%m-%d %H:%M UTC") if member.wallet_submitted_at else "Unknown"
        await update.message.reply_text(
            f"💼 <b>Your Wallet</b>\n<code>{_html_escape(_mask_wallet(member.wallet_address))}</code>\nSubmitted: {submitted}",
            parse_mode="HTML",
        )

    async def handle_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ Reply to the message you want to report.")
            return

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        rep_settings = group.settings.get("reports", {})
        if not rep_settings.get("enabled", False):
            await update.message.reply_text("❌ Reports are not enabled in this group.")
            return

        reporter = update.effective_user
        reported_msg = update.message.reply_to_message
        reported_user = reported_msg.from_user
        reason = " ".join(context.args) if context.args else "No reason provided"

        with self.app_context.app_context():
            from .models import db, ReportedMessage
            report = ReportedMessage(
                group_id=group.id,
                reporter_user_id=reporter.id,
                reporter_username=reporter.username,
                reported_message_id=reported_msg.message_id,
                reported_user_id=reported_user.id if reported_user else None,
                reported_username=reported_user.username if reported_user else None,
                reason=reason,
                status="open",
            )
            db.session.add(report)
            db.session.commit()
            # Dashboard alert for the bot owner (in-app bell + web push). Best-effort.
            try:
                from .models import Bot
                from .routes.notifications import create_notification
                bot_row = Bot.query.get(group.bot_id)
                if bot_row and bot_row.user_id:
                    create_notification(
                        bot_row.user_id, "report",
                        "🚩 New report filed",
                        f"A member reported a message in {group.group_name or 'your group'}. Reason: {reason[:120]}",
                    )
            except Exception:
                pass

        await update.message.reply_text("✅ Report submitted. Admins have been notified.")

        notify_mode = rep_settings.get("notify_admins", "all")
        notification = (
            f"🚨 *New Report*\n"
            f"Reporter: @{reporter.username or reporter.first_name}\n"
            f"Reported: @{reported_user.username or reported_user.first_name if reported_user else 'Unknown'}\n"
            f"Reason: {reason}"
        )
        try:
            if notify_mode == "all":
                admins = await context.bot.get_chat_administrators(update.effective_chat.id)
                for admin in admins:
                    if not admin.user.is_bot:
                        try:
                            await context.bot.send_message(
                                chat_id=admin.user.id,
                                text=notification,
                                parse_mode="Markdown",
                            )
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"Report notification error: {e}")

    async def handle_removewarning(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return
        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        with self.app_context.app_context():
            from .models import db, Member
            from .database import DatabaseManager
            member = Member.query.filter_by(
                group_id=group.id,
                telegram_user_id=str(target.id),
            ).first()
            if not member:
                await update.message.reply_text("No data found for this user.")
                return
            if member.warnings <= 0:
                await update.message.reply_text(f"{target.first_name} has no warnings to remove.")
                return
            member.warnings -= 1
            remaining_warnings = member.warnings  # capture before commit expires the attribute
            db.session.commit()
            DatabaseManager.log_action(
                group_id=group.id,
                action_type="removewarning",
                target_user_id=str(target.id),
                target_username=target.username,
                moderator_id=str(caller.id),
                moderator_username=caller.username,
                reason="Warning removed by admin",
                extra_data={"remaining_warnings": remaining_warnings},
            )
        await update.message.reply_text(
            f"✅ Removed 1 warning from {target.first_name}.\n"
            f"Remaining warnings: {remaining_warnings}"
        )

    async def handle_groupinfo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        chat = update.effective_chat
        group = await self._get_or_create_group(chat.id, chat.title, context.bot)
        with self.app_context.app_context():
            from .models import Member, AuditLog, db as _db
            from sqlalchemy import func as _func
            member_count = Member.query.filter_by(group_id=group.id).count()
            total_warnings = (
                _db.session.query(_func.sum(Member.warnings))
                .filter(Member.group_id == group.id)
                .scalar() or 0
            )
            bans = AuditLog.query.filter_by(group_id=group.id, action_type="ban").count()
            mutes = AuditLog.query.filter_by(group_id=group.id, action_type="mute").count()
        try:
            tg_count = await context.bot.get_chat_member_count(chat.id)
        except Exception:
            tg_count = group.telegram_member_count or member_count
        await update.message.reply_text(
            f"ℹ️ *Group Info*\n"
            f"Name: {chat.title}\n"
            f"ID: `{chat.id}`\n"
            f"Members: {tg_count:,}\n"
            f"Tracked members: {member_count:,}\n"
            f"Total warnings issued: {total_warnings}\n"
            f"Total bans: {bans}\n"
            f"Total mutes: {mutes}\n"
            f"Type: {chat.type}",
            parse_mode="Markdown",
        )

    async def handle_ask(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        chat = update.effective_chat
        question = " ".join(context.args) if context.args else ""
        if not question:
            await update.message.reply_text("Usage: /ask <your question>")
            return
        group = self._get_group(chat.id)
        if not group:
            return
        if not group.settings.get("knowledge_base", {}).get("enabled", True):
            return
        typing_msg = await update.message.reply_text("🔍 Searching knowledge base...")
        answer, confidence = await self.knowledge_base.answer_question(question, group.id)
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=typing_msg.message_id)
        except Exception:
            pass
        if answer:
            await update.message.reply_text(answer, parse_mode="Markdown")
        else:
            await update.message.reply_text("I couldn't find an answer in the knowledge base.")

    async def handle_invitelink(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        chat = update.effective_chat
        user = update.effective_user

        # Topic restriction: if admin configured an allowed topic, enforce it
        thread_id = getattr(update.message, "message_thread_id", None)
        group = self._get_group(chat.id)
        if group:
            allowed_topic = (group.settings or {}).get("invites", {}).get("allowed_topic_id")
            if allowed_topic and str(thread_id) != str(allowed_topic):
                routing = (group.settings or {}).get("command_routing", {})
                if routing.get("restricted_reply", "silent") == "message":
                    await update.message.reply_text("⚠️ Please use /invitelink in the designated topic.")
                return

        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in ("administrator", "creator"):
                await update.message.reply_text("⚠️ Only admins can create invite links.")
                return
        except Exception as e:
            logger.warning(f"handle_invitelink: could not verify admin status for user {user.id} in chat {chat.id}: {e}")
            await update.message.reply_text(
                "⚠️ Could not verify your admin status. "
                "Make sure the bot is an admin with 'Invite Users via Link' permission."
            )
            return
        creator_name = _display_name(user)
        name = " ".join(context.args) if context.args else f"Link by {creator_name}"
        try:
            link = await context.bot.create_chat_invite_link(chat_id=chat.id, name=name[:32])
            group = self._get_group(chat.id)
            if group:
                with self.app_context.app_context():
                    from .models import InviteLink, db
                    il = InviteLink(
                        group_id=group.id,
                        name=name,
                        telegram_invite_link=link.invite_link,
                        created_by_telegram_id=str(user.id),
                        created_by_username=user.username,
                    )
                    db.session.add(il)
                    db.session.commit()
            await update.message.reply_text(
                f"🔗 <b>Invite Link Created</b>\n"
                f"Created by: {_html_escape(creator_name)}\n"
                f"Link: {link.invite_link}",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to create invite link. Make sure the bot has the 'Invite Users via Link' admin permission.")

    async def handle_reaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        reaction = update.message_reaction
        if not reaction or not reaction.new_reaction:
            return
        chat_id = reaction.chat.id
        user_id = reaction.user.id if reaction.user else None
        if not user_id:
            return
        group = self._get_group(chat_id)
        if not group:
            return
        if not group.settings.get("levels", {}).get("enabled", True):
            return
        user = reaction.user
        await self.levels.add_reaction_xp(
            context.bot, chat_id, user_id,
            user.username if user else None,
            user.first_name if user else None,
            group,
        )

    async def handle_service_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return
        message = update.message
        chat_id = message.chat.id
        group = self._get_group(chat_id)
        if not group:
            return

        auto_clean = group.settings.get("auto_clean", {})
        if not auto_clean.get("enabled", False):
            return

        should_delete = False
        if auto_clean.get("delete_joins") and message.new_chat_members:
            should_delete = True
        elif auto_clean.get("delete_leaves") and message.left_chat_member:
            should_delete = True
        elif auto_clean.get("delete_photo_changes") and message.new_chat_photo:
            should_delete = True
        elif auto_clean.get("delete_pinned_messages") and message.pinned_message:
            should_delete = True
        elif auto_clean.get("delete_game_scores") and message.game_short_name:
            should_delete = True
        elif auto_clean.get("delete_voice_chat_events") and (
            message.video_chat_started or message.video_chat_ended or
            message.video_chat_scheduled or message.video_chat_participants_invited
        ):
            should_delete = True
        elif auto_clean.get("delete_forum_events") and (
            message.forum_topic_created or message.forum_topic_closed or
            message.forum_topic_reopened or message.forum_topic_edited
        ):
            should_delete = True

        # Capture/update topics so the dashboard topic selectors stay current.
        if message.forum_topic_created and message.message_thread_id:
            topic_name = getattr(message.forum_topic_created, "name", None)
            changed = _capture_topic(group, message.message_thread_id, topic_name)
            if changed:
                with self.app_context.app_context():
                    from .models import db
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(group, "settings")
                    db.session.commit()
        elif (message.forum_topic_closed or message.forum_topic_reopened) and message.message_thread_id:
            is_closed = bool(message.forum_topic_closed)
            try:
                with self.app_context.app_context():
                    from .models import db, GroupForumTopic
                    row = GroupForumTopic.query.filter_by(
                        telegram_group_id=str(group.telegram_group_id),
                        thread_id=int(message.message_thread_id),
                    ).first()
                    if row and row.is_closed != is_closed:
                        row.is_closed = is_closed
                        db.session.commit()
            except Exception:
                pass
        elif message.forum_topic_edited and message.message_thread_id:
            new_name = getattr(message.forum_topic_edited, "name", None)
            if new_name:
                changed = _capture_topic(group, message.message_thread_id, new_name)
                if changed:
                    with self.app_context.app_context():
                        from .models import db
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(group, "settings")
                        db.session.commit()

        if should_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            except Exception:
                pass

    async def handle_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.new_chat_members:
            return

        chat = update.effective_chat
        if chat.type not in ("group", "supergroup"):
            return  # never send welcome messages or create DB rows for private chats

        chat_id = chat.id
        group = await self._get_or_create_group(chat_id, chat.title, context.bot, chat_type=chat.type)

        for new_user in update.message.new_chat_members:
            if new_user.is_bot:
                # Telegram never delivers another bot's messages to us, so a bot
                # member's spam can't be caught at the message layer — apply the
                # group's Bot Policy at join time instead.
                added_by = update.message.from_user
                _is_adder = added_by and added_by.id != new_user.id
                added_by_name = added_by.first_name if _is_adder else None
                added_by_id = added_by.id if _is_adder else None
                try:
                    await self._handle_bot_join(context, chat, new_user, added_by_name, group, added_by_id)
                except Exception as exc:
                    logger.warning(f"bot-join handling failed (group {group.id}): {exc}")
                continue

            with self.app_context.app_context():
                from .database import DatabaseManager
                member = DatabaseManager.get_or_create_member(
                    group.id, new_user.id, new_user.username, new_user.first_name
                )

            settings = group.settings

            # Phase 3 raid mode — members who join while a raid is active are
            # auto-restricted (or kicked) so the flood can't grow. is_active() is
            # an in-memory check, so the common (no-raid) path stays free.
            try:
                from .bot_features import raid_guard
                if raid_guard.is_locked_down(chat_id, settings):
                    action = await raid_guard.lockdown_joiner(
                        context.bot, chat_id, new_user.id, settings
                    )
                    with self.app_context.app_context():
                        from .database import DatabaseManager
                        DatabaseManager.log_action(
                            group_id=group.id, action_type="raid_lockdown_join",
                            target_user_id=str(new_user.id),
                            target_username=new_user.username,
                            moderator_id="raid_guard", moderator_username="RaidGuard",
                            reason=f"{action} on join during active raid",
                        )
                    continue  # skip welcome/verification while locked down
            except Exception as exc:
                logger.debug(f"raid lockdown on join failed: {exc}")

            if settings.get("verification", {}).get("enabled", False):
                await self.verification.verify_new_member(
                    context.bot, update, new_user, group, settings
                )
            else:
                await self.welcome.send_welcome(context.bot, chat_id, new_user, group)

    async def _handle_bot_join(self, context, chat, bot_user, added_by_name, group, added_by_id=None):
        """Apply this group's Bot Policy to a newly added bot member (custom-bot runtime)."""
        from .bot_features import bot_guard
        from .database import DatabaseManager

        # Auto-trust: this bot itself + the Telegizer official bot.
        auto_trusted = set()
        try:
            if getattr(context.bot, "username", None):
                auto_trusted.add(context.bot.username.lower())
        except Exception:
            pass
        try:
            auto_trusted.add(self._official_bot_username().lower())
        except Exception:
            pass

        outcome = await bot_guard.enforce_bot_join(
            bot=context.bot,
            chat=chat,
            bot_user=bot_user,
            added_by_name=added_by_name,
            settings=group.settings or {},
            auto_trusted_usernames=auto_trusted,
        )

        policy = outcome["policy"]
        label = ("@" + bot_user.username) if bot_user.username else (bot_user.first_name or str(bot_user.id))

        if policy.get("log_events", True):
            try:
                with self.app_context.app_context():
                    DatabaseManager.log_action(
                        group_id=group.id,
                        action_type={"trusted": "bot_join_trusted", "restricted": "bot_restricted",
                                     "banned": "bot_banned", "alert_only": "bot_join_unhandled"}.get(
                                         outcome["outcome"], "bot_join"),
                        target_user_id=str(bot_user.id),
                        target_username=bot_user.username,
                        moderator_id="bot_guard",
                        moderator_username="BotGuard",
                        reason=outcome["reason"],
                    )
            except Exception as exc:
                logger.debug(f"bot-join log failed: {exc}")

        if not outcome.get("show_alert"):
            return

        group_id = str(chat.id)
        notify = policy.get("notify", "dm")
        timeout_min = int(policy.get("approval_timeout_minutes", 60) or 0)
        delivered_dm = False

        # 1) Private DM to the admin who added the bot, falling back to the owner.
        if notify in ("dm", "both"):
            text, keyboard = bot_guard.build_dm_alert(
                bot_user, chat.title or "", added_by_name, outcome["outcome"], group_id,
                timeout_minutes=(timeout_min if outcome["outcome"] == "restricted" else None),
            )
            delivered_dm = await self._dm_bot_join_alert(
                context.bot, group, added_by_id, text, keyboard,
            )

        # 2) Linkless in-group notice (never exposes the bot's @username).
        post_group = notify in ("group", "both") or (notify == "dm" and not delivered_dm)
        if post_group:
            try:
                with_buttons = (notify in ("group", "both")) or not delivered_dm
                text, keyboard = bot_guard.build_group_notice(
                    bot_user, outcome["outcome"], group_id, with_buttons=with_buttons,
                )
                await context.bot.send_message(
                    chat_id=chat.id, text=text, parse_mode="Markdown", reply_markup=keyboard,
                )
            except Exception as exc:
                logger.debug(f"bot-join group notice failed: {exc}")

        # 3) Schedule approval timeout (auto-action if no admin decides).
        if outcome["outcome"] == "restricted" and timeout_min > 0:
            on_timeout = policy.get("on_timeout", "ban")
            try:
                import asyncio as _aio
                _aio.get_running_loop().call_later(
                    timeout_min * 60,
                    lambda: _aio.ensure_future(
                        self._bot_approval_timeout(context.bot, group, bot_user.id, on_timeout)
                    ),
                )
            except Exception as exc:
                logger.debug(f"bot-join timeout schedule failed: {exc}")

    async def _dm_bot_join_alert(self, bot, group, added_by_id, text, keyboard) -> bool:
        """DM the bot-join alert to the adder, falling back to the group owner.
        Returns True if a DM was delivered."""
        candidates = []
        if added_by_id:
            candidates.append(str(added_by_id))
        try:
            with self.app_context.app_context():
                from .models import Bot, User
                if group and getattr(group, "bot_id", None):
                    bot_row = Bot.query.get(group.bot_id)
                    if bot_row:
                        owner = User.query.get(bot_row.user_id)
                        if owner and owner.telegram_user_id:
                            candidates.append(str(owner.telegram_user_id))
        except Exception:
            pass
        seen = set()
        for cid in candidates:
            if not cid or cid in seen:
                continue
            seen.add(cid)
            try:
                await bot.send_message(
                    chat_id=int(cid), text=text, parse_mode="Markdown", reply_markup=keyboard,
                )
                return True
            except Exception as exc:
                logger.debug(f"bot-join DM to {cid} failed: {exc}")
        return False

    async def _bot_approval_timeout(self, bot, group, bot_id, on_timeout):
        """Fires after the approval window. No-op if an admin already decided."""
        from .bot_features import bot_guard
        from .database import DatabaseManager
        try:
            group_id = str(group.telegram_group_id) if getattr(group, "telegram_group_id", None) else None
            chat_id = group.telegram_group_id if group_id else None
            if chat_id is None:
                return
            action = await bot_guard.apply_timeout_action(bot, chat_id, bot_id, on_timeout)
            if action == "ban" and group:
                with self.app_context.app_context():
                    DatabaseManager.log_action(
                        group_id=group.id, action_type="bot_banned",
                        target_user_id=str(bot_id), moderator_id="bot_guard",
                        moderator_username="BotGuard", reason="Auto-banned (approval timeout)",
                    )
        except Exception as exc:
            logger.debug(f"bot approval timeout failed: {exc}")

    async def _handle_bot_guard_callback(self, update, context):
        """Admin taps Approve / Ban / Keep on a bot-join alert (works in DM or group)."""
        from .bot_features import bot_guard
        from .database import DatabaseManager
        query = update.callback_query
        action, group_id, bot_id = bot_guard.parse_callback(query.data or "")
        if not action:
            await query.answer()
            return

        chat_id = int(group_id)
        presser = update.effective_user

        # Admin-gate against the GROUP the bot is in (the button may be in a DM).
        try:
            pm = await context.bot.get_chat_member(chat_id, presser.id)
            if pm.status not in ("creator", "administrator"):
                await query.answer("Only that group's admins can decide this.", show_alert=True)
                return
        except Exception:
            await query.answer("Couldn't verify your admin status for that group.", show_alert=True)
            return

        bot_guard.clear_pending(group_id, bot_id)
        group = self._get_group(chat_id)
        bot_username = await bot_guard.resolve_bot_username(context.bot, chat_id, bot_id)
        label = ("@" + bot_username) if bot_username else f"bot {bot_id}"
        decided_by = presser.first_name if presser else "an admin"

        if action == "approve":
            await bot_guard.lift_restriction(context.bot, chat_id, bot_id)
            if bot_username and group:
                try:
                    with self.app_context.app_context():
                        from .models import Group, db
                        g = Group.query.get(group.id)
                        if g:
                            s = dict(g.settings or {})
                            bp = dict(s.get("bot_policy", {}))
                            lst = list(bp.get("trusted_bot_usernames", []) or [])
                            uname = bot_username.strip().lstrip("@").lower()
                            if uname not in [u.lower() for u in lst]:
                                lst.append(uname)
                                bp["trusted_bot_usernames"] = lst
                                s["bot_policy"] = bp
                                g.settings = s
                                from sqlalchemy.orm.attributes import flag_modified
                                flag_modified(g, "settings")
                                db.session.commit()
                except Exception as exc:
                    logger.debug(f"approve allowlist persist failed: {exc}")
            action_type, verdict, toast = "bot_approved", f"✅ {label} approved by {decided_by}. It can now post.", "Bot approved."
        elif action == "ban":
            await bot_guard.ban_bot(context.bot, chat_id, bot_id)
            action_type, verdict, toast = "bot_banned", f"⛔ {label} banned by {decided_by}.", "Bot banned."
        else:
            action_type, verdict, toast = "bot_kept_restricted", f"🔇 {label} kept restricted by {decided_by}.", "Kept restricted."

        if group:
            try:
                with self.app_context.app_context():
                    DatabaseManager.log_action(
                        group_id=group.id, action_type=action_type,
                        target_user_id=str(bot_id), target_username=bot_username,
                        moderator_id=str(presser.id) if presser else "admin",
                        moderator_username=decided_by, reason=f"Bot-guard decision: {action}",
                    )
            except Exception:
                pass

        await query.answer(toast)
        try:
            await query.edit_message_text(verdict)
        except Exception:
            pass

    async def handle_private_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle DMs to the bot — primarily for admin escalation replies."""
        if not update.message or not update.effective_user:
            return
        if update.effective_chat.type != "private":
            return

        # ── Email verification flow (email → password → code) takes priority ──
        from .bot_features import email_verify
        if email_verify.is_active(context):
            if await email_verify.handle_text(update, context, self.app_context, self._find_website_user):
                return

        # Check if this is a reply to an escalation header
        replied_msg = update.message.reply_to_message
        if replied_msg and update.message.text:
            admin_id = str(update.effective_user.id)
            replied_id = replied_msg.message_id
            try:
                from .bot_features.escalation import handle_admin_reply
                matched = handle_admin_reply(
                    reply_text=update.message.text,
                    admin_telegram_id=admin_id,
                    replied_to_message_id=replied_id,
                    app=self.app_context,
                )
                if matched:
                    await update.message.reply_text(
                        "✅ Escalation resolved. The answer has been saved and will be used for future auto-replies.",
                        parse_mode="Markdown",
                    )
                    return
            except Exception as exc:
                logger.warning(f"handle_private_message: escalation reply error: {exc}")

    async def handle_channel_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Channel-as-source forwarding (Phase 2) for custom bots — a new channel
        post can be a forwarding source, mirroring the official bot."""
        msg = update.channel_post
        if not msg:
            return
        try:
            from .automation.forwarding_runtime import run_forwarding
            await run_forwarding(
                self.app_context, context.bot, str(msg.chat.id), msg,
                bot_type="custom", owner_bot_id=self.bot_id,
            )
        except Exception as exc:
            logger.debug(f"channel_post forward (custom) failed: {exc}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.effective_user:
            return
        if update.effective_chat.type == "private":
            return

        user = update.effective_user
        chat = update.effective_chat
        chat_id = chat.id
        group = await self._get_or_create_group(chat_id, chat.title, context.bot, chat_type=chat.type)
        if not group:
            return  # private chat or limit reached — skip all processing

        with self.app_context.app_context():
            from .database import DatabaseManager
            DatabaseManager.get_or_create_member(
                group.id, user.id, user.username, user.first_name, user.last_name
            )

        # Passively capture forum topics from any message so the dashboard has
        # routing options even if the bot was added after topic creation.
        thread_id = getattr(update.message, "message_thread_id", None)
        if thread_id:
            changed = _capture_topic(group, thread_id, None)
            if changed:
                with self.app_context.app_context():
                    from .models import db
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(group, "settings")
                    db.session.commit()

        # Custom command dispatch
        msg_text = (update.message.text or "").strip()
        if msg_text.startswith("/"):
            cmd_raw = msg_text.split()[0].lstrip("/").split("@")[0].lower()
            cmd_data = None
            try:
                with self.app_context.app_context():
                    from .models import BotGroupCommand
                    obj = BotGroupCommand.query.filter_by(
                        group_id=group.id,
                        command=cmd_raw,
                        enabled=True,
                    ).first()
                    if obj:
                        cmd_data = {
                            "text": obj.response_text,
                            "type": obj.response_type,
                            "buttons": obj.buttons,
                        }
            except Exception:
                pass

            if cmd_data:
                if not _is_command_allowed(group.settings, f"/{cmd_raw}", thread_id):
                    await _send_routing_rejection(update, group.settings, f"/{cmd_raw}")
                    return
                keyboard = None
                if cmd_data["buttons"]:
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    rows = [
                        [InlineKeyboardButton(b["text"], url=b["url"])
                         for b in row if b.get("url")]
                        for row in cmd_data["buttons"]
                    ]
                    rows = [r for r in rows if r]
                    if rows:
                        keyboard = InlineKeyboardMarkup(rows)
                try:
                    from telegram.constants import ParseMode
                    await update.message.reply_text(
                        cmd_data["text"],
                        parse_mode=ParseMode.MARKDOWN if cmd_data["type"] == "markdown" else None,
                        reply_markup=keyboard,
                    )
                except Exception as e:
                    logger.debug(f"Custom command reply failed: {e}")

        # Delete command messages if auto_clean.delete_commands is on
        if msg_text.startswith("/"):
            auto_clean = group.settings.get("auto_clean", {})
            if auto_clean.get("enabled") and auto_clean.get("delete_commands"):
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
                except Exception:
                    pass

        if await self.verification.handle_first_message(context.bot, update.message, group, group.settings):
            return
        if await self.verification.handle_word_answer(context.bot, update.message, group):
            return

        if group.settings.get("automod", {}).get("enabled", True):
            blocked = await self.moderation.check_automod(context.bot, update.message, group)
            if blocked:
                return

        if group.settings.get("levels", {}).get("enabled", True):
            await self.levels.add_message_xp(
                context.bot, chat_id, user.id, user.username, user.first_name, group
            )

        # Cross-bot forwarding + automation workflows — shared, bot-agnostic
        # runtime so custom bots have the SAME behavior as the official bot
        # (many→many, forum topics, anti-ban governor). Runs before the admin
        # early-return so admin messages forward too, matching the official bot.
        try:
            from .automation.forwarding_runtime import run_forwarding
            await run_forwarding(
                self.app_context, context.bot, str(chat_id), update.message,
                bot_type="custom", owner_bot_id=self.bot_id,
            )
        except Exception as _fwd_exc:
            logger.debug(f"run_forwarding (custom) failed: {_fwd_exc}")

        _auto_text = update.message.text or update.message.caption or ""
        if _auto_text:
            try:
                from .automation.engine import fire_trigger as _fire_trigger
                await _fire_trigger(
                    flask_app=self.app_context,
                    bot=context.bot,
                    trigger_type="message_received",
                    group_id=str(chat_id),
                    trigger_data={
                        "text": _auto_text,
                        "user_id": str(user.id),
                        "chat_id": str(chat_id),
                        "message_id": update.message.message_id,
                    },
                    bot_type="custom",
                )
            except Exception as _ae:
                logger.debug(f"fire_trigger (custom) failed: {_ae}")

        # Resolve sender admin status once — all reply features skip admins entirely
        sender_is_admin = False
        try:
            _cm = await context.bot.get_chat_member(chat_id, user.id)
            sender_is_admin = _cm.status in ("creator", "administrator")
        except Exception:
            pass

        if sender_is_admin:
            # React 👍 to admin messages then stop — never process admins as reply targets
            rxn_settings = group.settings.get("reactions", {})
            if rxn_settings.get("enabled") and rxn_settings.get("admin_thumbs_up", True):
                from .bot_features.reactions import send_reaction
                await send_reaction(context.bot, chat_id, update.message.message_id, "👍")
            return

        # Auto-response triggers
        if group.settings.get("auto_responses", {}).get("enabled", True):
            text = update.message.text or ""
            if text:
                with self.app_context.app_context():
                    from .models import AutoResponse
                    responses = AutoResponse.query.filter_by(group_id=group.id, is_enabled=True).all()
                    for ar in responses:
                        trigger = ar.trigger_text if ar.is_case_sensitive else ar.trigger_text.lower()
                        check = text if ar.is_case_sensitive else text.lower()
                        match = False
                        if ar.match_type == "exact":
                            match = check == trigger
                        elif ar.match_type == "contains":
                            match = trigger in check
                        elif ar.match_type == "starts_with":
                            match = check.startswith(trigger)
                        if match:
                            try:
                                await update.message.reply_text(ar.response_text)
                            except Exception as e:
                                logger.error(f"Auto-response error: {e}")
                            break

        # Multimodal image AI
        image_settings = group.settings.get("image_ai", {})
        if image_settings.get("enabled", False) and (update.message.photo or update.message.document):
            try:
                from .bot_features.image_ai import maybe_handle_image
                from .bot_features.knowledge_base import KnowledgeBaseSystem
                _kb_sys = KnowledgeBaseSystem(self.app_context)
                _key_cfg = _kb_sys._load_group_api_key(group.id)
                _api_key = _key_cfg["api_key"] if _key_cfg else None
                _base_url = _key_cfg.get("base_url") if _key_cfg else None
                _group_name = getattr(group, "group_name", None) or "this community"
                _kb_settings = group.settings.get("knowledge_base", {})
                _img_handled = await maybe_handle_image(
                    bot=context.bot,
                    message=update.message,
                    group_id=group.id,
                    telegram_group_id=None,
                    image_settings=image_settings,
                    kb_settings=_kb_settings,
                    group_name=_group_name,
                    app=self.app_context,
                    api_key=_api_key,
                    base_url=_base_url,
                )
                if _img_handled:
                    return  # image was answered/escalated — skip remaining handlers
            except Exception as _img_exc:
                logger.error(f"image_ai handler error: {_img_exc}")

        # Social / human-like appreciation replies
        social_settings = group.settings.get("social_replies", {})
        if social_settings.get("enabled", False):
            from .bot_features.social_reply import maybe_handle_social_reply
            kb_settings_for_social = group.settings.get("knowledge_base", {})
            handled = await maybe_handle_social_reply(
                bot=context.bot,
                message=update.message,
                group_id=group.id,
                user_id=user.id,
                social_settings=social_settings,
                kb_settings=kb_settings_for_social,
            )
            if handled:
                return  # appreciation handled — skip KB reply for this message

        # Automatic KB reply
        kb_settings = group.settings.get("knowledge_base", {})
        if kb_settings.get("enabled", True) and kb_settings.get("auto_reply_enabled", False):
            await self._handle_auto_kb_reply(update, context, group, kb_settings)

        # Sentiment-based emoji reactions for member messages
        rxn_settings = group.settings.get("reactions", {})
        if rxn_settings.get("enabled") and rxn_settings.get("sentiment_reactions", True):
            from .bot_features.reactions import detect_sentiment_reaction, should_react, mark_reacted, send_reaction
            msg_text = update.message.text or update.message.caption or ""
            reaction_emoji = detect_sentiment_reaction(msg_text)
            if reaction_emoji and should_react(group.id, user.id):
                sent = await send_reaction(context.bot, chat_id, update.message.message_id, reaction_emoji)
                if sent:
                    mark_reacted(group.id, user.id)

    def _is_kb_question(self, text: str, kb_settings: dict) -> bool:
        """Classify whether a message looks like a knowledge-base question worth answering."""
        if not text or not text.strip():
            return False

        # Skip commands
        if text.startswith("/"):
            return False

        words = text.split()
        min_words = kb_settings.get("min_message_words", 5)
        if len(words) < min_words:
            logger.debug(f"KB auto-reply: skipped (too short: {len(words)} words)")
            return False

        # Skip emoji-only or non-alphabetic messages
        stripped = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
        if not stripped.strip():
            logger.debug("KB auto-reply: skipped (no alphabetic content)")
            return False

        # Skip very common casual phrases (not exhaustive, just basic guard)
        casual_patterns = [
            r"^(hi|hello|hey|hiya|howdy|sup|yo|ok|okay|lol|lmao|haha|thanks|thank you|thx|np|yw|brb|gtg|bye|cya|gm|gn|gg)[\s!?.]*$",
        ]
        lower_text = text.lower().strip()
        for pattern in casual_patterns:
            if re.match(pattern, lower_text):
                logger.debug(f"KB auto-reply: skipped (casual phrase: {lower_text!r})")
                return False

        return True

    async def _handle_auto_kb_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE, group, kb_settings: dict):
        """Handle automatic knowledge-base replies for qualifying messages."""
        text = update.message.text or ""
        bot_username = context.bot.username or ""

        # Mention-only mode: only reply when bot is @mentioned or message is a reply to bot
        if kb_settings.get("auto_reply_mention_only", False):
            mentioned = f"@{bot_username}".lower() in text.lower() if bot_username else False
            replied_to_bot = (
                update.message.reply_to_message and
                update.message.reply_to_message.from_user and
                update.message.reply_to_message.from_user.username == bot_username
            )
            if not mentioned and not replied_to_bot:
                return

        # Group chat check
        if not kb_settings.get("auto_reply_in_groups", True):
            return

        if not self._is_kb_question(text, kb_settings):
            return

        threshold = float(kb_settings.get("confidence_threshold", 0.35))

        # Collect auto-reply triggers as optional AI knowledge
        auto_reply_triggers = []
        if kb_settings.get("use_auto_replies_as_knowledge", False):
            try:
                with self.app.app_context():
                    from .models import AutoResponse
                    triggers = AutoResponse.query.filter_by(
                        group_id=group.id,
                        is_enabled=True,
                        use_as_ai_knowledge=True,
                        response_type="auto_response",
                    ).all()
                    auto_reply_triggers = [
                        {"trigger": t.trigger_text, "response": t.response_text}
                        for t in triggers
                    ]
                    logger.debug(f"KB auto-reply: loaded {len(auto_reply_triggers)} AI-knowledge triggers")
            except Exception as exc:
                logger.warning(f"KB auto-reply: failed to load triggers: {exc}")

        logger.debug(f"KB auto-reply: querying KB for group {group.id}, question: {text[:80]!r}")
        answer, confidence = await self.knowledge_base.answer_question(
            text, group.id,
            group_name=getattr(group, "group_name", None) or "this community",
            kb_settings=kb_settings,
            auto_reply_triggers=auto_reply_triggers or None,
        )

        logger.debug(f"KB auto-reply: confidence={confidence:.3f}, threshold={threshold:.3f}")

        if answer and confidence >= threshold:
            logger.debug(f"KB auto-reply: replying (confidence={confidence:.3f})")
            try:
                await update.message.reply_text(answer, parse_mode="Markdown")
            except Exception:
                try:
                    await update.message.reply_text(answer)
                except Exception as e:
                    logger.error(f"KB auto-reply send error: {e}")
        else:
            # Low confidence or no answer — try global escalation before fallback
            esc_settings = group.settings.get("escalation", {})
            if esc_settings.get("enabled") and "ai_kb" in esc_settings.get("types", []):
                try:
                    from .bot_features.escalation import trigger_escalation
                    sender = update.message.from_user
                    uname = getattr(sender, "username", None) or ""
                    uid   = getattr(sender, "id", None)
                    await trigger_escalation(
                        bot=context.bot,
                        group_settings=group.settings,
                        issue_type="ai_kb",
                        original_content=text,
                        context_data={
                            "confidence": confidence,
                            "group_name": getattr(group, "group_name", None) or "this community",
                            "user_id": uid,
                            "username": uname,
                            "thread_id": getattr(update.message, "message_thread_id", None),
                        },
                        app=self.app,
                        group_id=group.id,
                        telegram_group_id=getattr(group, "telegram_group_id", None),
                        original_message=update.message,
                    )
                    logger.debug(f"KB auto-reply: escalated (confidence={confidence:.3f})")
                    return  # suppress public reply when escalating
                except Exception as exc:
                    logger.warning(f"KB auto-reply: escalation failed: {exc}")

            if kb_settings.get("fallback_enabled", False) and answer:
                logger.debug(f"KB auto-reply: low confidence fallback (confidence={confidence:.3f})")
                try:
                    fallback_text = f"I found some related information, but I'm not fully certain: {answer}"
                    await update.message.reply_text(fallback_text)
                except Exception as e:
                    logger.error(f"KB fallback reply error: {e}")
            else:
                logger.debug(f"KB auto-reply: no confident answer (confidence={confidence:.3f})")

    async def handle_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track when users join via a tracked invite link."""
        result = update.chat_member
        if not result:
            return

        old_status = result.old_chat_member.status
        new_status = result.new_chat_member.status

        # Detect a fresh join (not already a member)
        if old_status not in ("left", "kicked", "banned", "restricted") or new_status != "member":
            return

        chat_id = result.chat.id
        group = self._get_group(chat_id)
        if not group:
            return

        joined_user = result.new_chat_member.user
        invite_link_obj = result.invite_link  # ChatInviteLink or None

        if not invite_link_obj:
            return

        invite_link_url = invite_link_obj.invite_link
        if not invite_link_url:
            return

        with self.app_context.app_context():
            from .models import InviteLink, InviteLinkJoin, db
            # Match against stored invite links by URL
            link_record = InviteLink.query.filter_by(
                group_id=group.id,
                telegram_invite_link=invite_link_url,
                is_active=True,
            ).first()

            if link_record:
                join = InviteLinkJoin(
                    invite_link_id=link_record.id,
                    joined_user_id=str(joined_user.id),
                    joined_username=joined_user.username,
                )
                db.session.add(join)
                link_record.uses_count = (link_record.uses_count or 0) + 1
                db.session.commit()
                logger.debug(
                    f"Invite join tracked: user {joined_user.id} via link '{link_record.name}' "
                    f"(group {group.id})"
                )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return

        data = query.data or ""
        parts = data.split(":")
        user = query.from_user

        # Hub consent / intro buttons — handle before generic answer() so
        # handle_consent_callback can answer with its own alert if needed.
        if data.startswith("hub_consent:") or data.startswith("hub_intro:"):
            try:
                from .assistant.hub_consent import handle_consent_callback
                await handle_consent_callback(update, context, self.app_context)
            except Exception as _ce:
                logger.warning("Hub consent callback error: %s", _ce)
                try:
                    await query.answer()
                except Exception:
                    pass
            return

        # Hub group-type disambiguation (custom bots, small private groups).
        if data.startswith("hub_classify:"):
            try:
                from .assistant.hub_consent import handle_classify_callback
                await handle_classify_callback(update, context, self.app_context)
            except Exception as _ce:
                logger.warning("Hub classify callback error: %s", _ce)
                try:
                    await query.answer()
                except Exception:
                    pass
            return

        # Bot-guard approve/ban/keep — answered inside the handler (admin-gated).
        if data.startswith("botguard:"):
            try:
                await self._handle_bot_guard_callback(update, context)
            except Exception as _be:
                logger.warning("Bot-guard callback error: %s", _be)
                try:
                    await query.answer()
                except Exception:
                    pass
            return

        await query.answer()

        # Any menu navigation other than (re)entering verification aborts an in-progress
        # email flow, so a later unrelated message isn't mistaken for an email/code.
        if data != "menu:email_verify":
            from .bot_features import email_verify as _ev
            _ev.cancel(context)

        # Email verification (optional email+password setup) — needs update/context.
        if data == "menu:email_verify":
            from .bot_features import email_verify
            await email_verify.start(update, context, self.app_context, self._find_website_user)
            return

        # Referral screen.
        if data == "menu:referral":
            from .bot_features import referral_ui
            await referral_ui.render(
                query, context, self.app_context, self._find_website_user,
                self._frontend(), self._official_bot_username(),
            )
            return

        if parts[0] == "verify":
            method = parts[1]
            group_id = int(parts[2])
            user_id = int(parts[3])
            chat_id = query.message.chat.id

            if user.id != user_id:
                await query.answer("This verification is not for you.", show_alert=True)
                return

            extra_data = parts[4:] if len(parts) > 4 else []
            await self.verification.handle_verification_callback(
                context.bot, query, chat_id, user_id, group_id, method, extra_data
            )

        elif parts[0] == "rules":
            group_id = int(parts[1])
            with self.app_context.app_context():
                from .models import Group
                group = Group.query.get(group_id)
                if group:
                    rules = group.settings.get("welcome", {}).get("rules_text", "No rules set.")
                    await query.message.reply_text(f"📜 <b>Rules:</b>\n{rules}", parse_mode="HTML")

        elif data.startswith("menu:") or data.startswith("show_code:"):
            try:
                await self._handle_menu_callback(query, user, data,
                                                  own_username=getattr(context.bot, "username", None))
            except Exception as e:
                logger.error(f"Menu callback error bot={self.bot_id} data={data}: {e}", exc_info=True)
                try:
                    await query.edit_message_text("⚠️ Something went wrong. Please try again.")
                except Exception:
                    pass

        elif data.startswith("qs:"):
            try:
                await self._handle_qs_callback(query, user, data)
            except Exception as e:
                logger.error(f"QS callback error bot={self.bot_id} data={data}: {e}", exc_info=True)
                try:
                    await query.edit_message_text("⚠️ Something went wrong. Please try again.")
                except Exception:
                    pass

    async def handle_my_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fires when the bot is added to or removed from a group."""
        result = update.my_chat_member
        if not result:
            return
        chat = result.chat
        if chat.type not in ("group", "supergroup"):
            return
        new_status = result.new_chat_member.status
        added_by = result.from_user

        if new_status in ("member", "administrator"):
            is_custom_bot = False
            hub_bot_id = None

            if self.app_context:
                try:
                    with self.app_context.app_context():
                        from .models import db, Bot, CustomBot
                        from .assistant.hub_models import HubBotIdentity
                        bot_rec = Bot.query.get(self.bot_id)
                        if bot_rec and bot_rec.bot_username:
                            cb = CustomBot.query.filter_by(
                                bot_username=bot_rec.bot_username,
                                owner_user_id=bot_rec.user_id,
                            ).first()
                            if cb:
                                is_custom_bot = True
                                hub_bot_id = cb.hub_bot_id

                            # If CustomBot.hub_bot_id is NULL or no CustomBot row found,
                            # fall back to a direct HubBotIdentity lookup by username so the
                            # observer DM can still be sent and private groups never fall
                            # through to the Group Management path.
                            if not hub_bot_id and bot_rec.bot_username:
                                hub_ident = HubBotIdentity.query.filter_by(
                                    telegram_bot_username=bot_rec.bot_username,
                                    user_id=bot_rec.user_id,
                                    bot_type="custom",
                                    is_active=True,
                                ).first()
                                if hub_ident:
                                    is_custom_bot = True
                                    hub_bot_id = hub_ident.id
                                    if cb:
                                        cb.hub_bot_id = hub_ident.id
                                        db.session.commit()
                except Exception:
                    pass

            if is_custom_bot:
                # Custom bots NEVER auto-add to Group Management.
                # For private groups:
                #   < 10 members → disambiguation DM (Hub vs Community Moderation)
                #   ≥ 10 members → Hub consent DM directly (larger private groups lean Hub)
                # Public groups are ignored here; user runs /linkgroup explicitly.
                is_private = not chat.username
                # Warn the admin if the bot was added as a plain member (privacy mode may be on).
                # Bots with privacy mode enabled can't read messages unless they are admins.
                if new_status == "member" and added_by and is_private:
                    try:
                        bot_info = await context.bot.get_me()
                        if not getattr(bot_info, "can_read_all_group_messages", False):
                            await context.bot.send_message(
                                chat_id=added_by.id,
                                text=(
                                    f"⚠️ *Privacy mode is ON for @{bot_info.username}.*\n\n"
                                    "I was added as a regular member, so I *cannot read group messages* "
                                    "unless privacy mode is disabled on BotFather or I'm made an admin.\n\n"
                                    "To fix this:\n"
                                    "1. Open @BotFather → /mybots → select the bot\n"
                                    "2. Bot Settings → Group Privacy → Turn Off\n"
                                    "   — OR —\n"
                                    "3. Promote me to admin in the group\n\n"
                                    "Silent observation and task extraction will not work until this is resolved."
                                ),
                                parse_mode="Markdown",
                            )
                    except Exception as _pm_e:
                        logger.debug("Privacy mode check/warn failed for chat %s: %s", chat.id, _pm_e)

                if is_private and hub_bot_id and added_by:
                    member_count = 0
                    try:
                        member_count = await context.bot.get_chat_member_count(chat.id)
                    except Exception:
                        pass
                    try:
                        if member_count < 10:
                            from .assistant.hub_consent import send_group_type_dm
                            await send_group_type_dm(
                                bot=context.bot,
                                flask_app=self.app_context,
                                chat=chat,
                                added_by_tg_id=str(added_by.id),
                                hub_bot_id=hub_bot_id,
                                member_count=member_count,
                            )
                        else:
                            from .assistant.hub_consent import handle_bot_added_to_group
                            await handle_bot_added_to_group(
                                bot=context.bot,
                                flask_app=self.app_context,
                                chat=chat,
                                added_by_tg_id=str(added_by.id),
                                hub_bot_id=hub_bot_id,
                            )
                    except Exception as _hub_e:
                        logger.warning(
                            "Custom bot group flow failed for chat %s: %s", chat.id, _hub_e
                        )
            else:
                # Official bot — create Group Management record as before.
                # Pass chat.username directly (None = unresolved, will be resolved lazily).
                await self._get_or_create_group(
                    chat.id, chat.title, context.bot,
                    chat_type=chat.type,
                    chat_username=chat.username,
                )

    def _run_bot(self):
        import time
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        max_retries = 10
        # Capture the token once before the retry loop — _start_polling() clears
        # self.token to avoid holding it in a long-lived attribute, but that means
        # any retry attempt would see None.  We restore it at the top of each loop.
        _saved_token = self.token
        for attempt in range(max_retries):
            if self._stop_event.is_set():
                break
            self.token = _saved_token  # restore so _start_polling() can consume it
            try:
                self.loop.run_until_complete(self._start_polling())
                break  # clean / stop-event exit
            except Exception as e:
                # Graceful shutdown in progress (Railway deploy / worker restart):
                # the interpreter is tearing down, so any error here is teardown
                # noise (e.g. "cannot schedule new futures after interpreter
                # shutdown"). Do NOT record it as a failure or retry — just exit.
                if _SHUTTING_DOWN.is_set() or self._stop_event.is_set():
                    logger.info(
                        "Bot %s: exiting during shutdown (ignored: %s)",
                        self.bot_id, type(e).__name__,
                    )
                    break

                try:
                    from telegram.error import Conflict, Unauthorized, InvalidToken
                    _invalid = (Unauthorized, InvalidToken)
                except ImportError:
                    _invalid = ()
                    Conflict = type(None)

                if _invalid and isinstance(e, _invalid):
                    # Token is wrong — no point retrying, watchdog will surface this
                    logger.error(
                        f"Bot {self.bot_id}: invalid/unauthorized token — stopping permanently: {e}"
                    )
                    self._record_health_error("invalid token — stopped: %s" % e)
                    break
                elif isinstance(e, Conflict):
                    wait = 15 * (attempt + 1)
                    logger.warning(
                        f"Bot {self.bot_id}: Conflict (another instance polling). "
                        f"Retrying in {wait}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait)
                else:
                    # Transient network / API error — retry with capped backoff
                    wait = min(30 * (attempt + 1), 300)
                    logger.error(
                        f"Bot {self.bot_id}: polling crashed ({type(e).__name__}): {e}. "
                        f"Retrying in {wait}s (attempt {attempt + 1}/{max_retries})",
                        exc_info=True,
                    )
                    self._record_health_error(f"polling crashed ({type(e).__name__}): {e}")
                    time.sleep(wait)

    async def _start_polling(self):
        # Consume the token, then immediately clear it from memory so it is not
        # held in a long-lived attribute after the Application object owns it.
        _token = self.token
        self.token = None
        self.application = (
            Application.builder()
            .token(_token)
            .build()
        )
        del _token

        app = self.application

        # ── Engagement Campaigns (Phase 4) — additive, isolated in group -1 ──────
        # Mirrors the official bot. Only acts on `eng_*` payloads / an active flow.
        from telegram.ext import ApplicationHandlerStop as _EngStop
        from . import engagement_bot as _engbot
        _eng_app = self.app_context
        _eng_bot_id = self.bot_id

        async def _eng_start(update, context):
            args = context.args or []
            if args and await _engbot.on_start(update, context, args[0], flask_app=_eng_app, lineage="custom", bot_id=_eng_bot_id):
                raise _EngStop

        async def _eng_priv(update, context):
            if await _engbot.on_private(update, context, flask_app=_eng_app, lineage="custom", bot_id=_eng_bot_id):
                raise _EngStop

        async def _eng_cb(update, context):
            if await _engbot.on_callback(update, context, flask_app=_eng_app, lineage="custom", bot_id=_eng_bot_id):
                raise _EngStop

        app.add_handler(CommandHandler("start", _eng_start), group=-1)
        app.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
                _eng_priv,
            ),
            group=-1,
        )
        app.add_handler(CallbackQueryHandler(_eng_cb, pattern=r"^(eng_|engtask_)"), group=-1)

        app.add_handler(CommandHandler("start", self.handle_start))
        app.add_handler(CommandHandler("help", self.handle_help))
        app.add_handler(CommandHandler("support", self.handle_support))
        app.add_handler(CommandHandler("status", self.handle_status))
        app.add_handler(CommandHandler("linkgroup", self.handle_linkgroup))
        # /settings removed — Quick Settings is now accessible via the /start DM menu
        app.add_handler(CommandHandler("rank", self.handle_rank))
        app.add_handler(CommandHandler("leaderboard", self.handle_leaderboard))
        app.add_handler(CommandHandler("warn", self.handle_warn))
        app.add_handler(CommandHandler("ban", self.handle_ban))
        app.add_handler(CommandHandler("kick", self.handle_kick))
        app.add_handler(CommandHandler("mute", self.handle_mute))
        app.add_handler(CommandHandler("unmute", self.handle_unmute))
        app.add_handler(CommandHandler("tempban", self.handle_tempban))
        app.add_handler(CommandHandler("tempmute", self.handle_tempmute))
        app.add_handler(CommandHandler("userinfo", self.handle_userinfo))
        app.add_handler(CommandHandler("auditlog", self.handle_auditlog))
        app.add_handler(CommandHandler("purge", self.handle_purge))
        app.add_handler(CommandHandler("me", self.handle_me))
        app.add_handler(CommandHandler("admins", self.handle_admins))
        app.add_handler(CommandHandler("roles", self.handle_roles))
        app.add_handler(CommandHandler("whois", self.handle_whois))
        app.add_handler(CommandHandler("report", self.handle_report))
        app.add_handler(CommandHandler("removewarning", self.handle_removewarning))
        app.add_handler(CommandHandler("unwarn", self.handle_removewarning))
        app.add_handler(CommandHandler("groupinfo", self.handle_groupinfo))
        app.add_handler(CommandHandler("ask", self.handle_ask))
        app.add_handler(CommandHandler("invitelink", self.handle_invitelink))
        app.add_handler(CommandHandler("wallet", self.handle_wallet))
        app.add_handler(CommandHandler("mywallet", self.handle_mywallet))
        if _REACTION_HANDLER_AVAILABLE:
            app.add_handler(_MessageReactionHandler(self.handle_reaction))
        app.add_handler(ChatMemberHandler(self.handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
        app.add_handler(ChatMemberHandler(self.handle_chat_member, ChatMemberHandler.CHAT_MEMBER))
        # Restrict all group-level handlers to actual groups/supergroups only.
        # Private chats are handled exclusively by handle_private_message.
        _GROUP_TYPES = filters.ChatType.GROUP | filters.ChatType.SUPERGROUP

        # NEW_CHAT_MEMBERS must be in its own handler group so it runs even when
        # StatusUpdate.ALL (below, in group 1) also matches the same update.
        # python-telegram-bot runs ALL groups for each update; within a group only
        # the first matching handler runs.
        app.add_handler(
            MessageHandler(_GROUP_TYPES & filters.StatusUpdate.NEW_CHAT_MEMBERS, self.handle_new_member),
            group=0,
        )
        app.add_handler(
            MessageHandler(_GROUP_TYPES & filters.StatusUpdate.ALL, self.handle_service_message),
            group=1,
        )
        app.add_handler(MessageHandler(_GROUP_TYPES & ~filters.COMMAND, self.handle_message))
        app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, self.handle_private_message))
        app.add_handler(MessageHandler(filters.ChatType.CHANNEL & ~filters.COMMAND, self.handle_channel_post))
        app.add_handler(CallbackQueryHandler(self.handle_callback))

        await app.initialize()
        await app.start()

        # 1-E-02: Register bot identity. Use the SHARED scoped command set so custom
        # bots show the same role-aware command menus as the official Telegizer bot.
        #
        # NOTE: we deliberately do NOT set a Web App menu button here. The Mini App
        # validates Telegram initData against the OFFICIAL bot token only, so a Mini App
        # launched from a custom bot would fail auth (hmac_mismatch). Custom bots open
        # the dashboard via a normal URL button instead (web session auth), which works
        # for every bot. Seamless per-custom-bot Mini App auth is a separate feature.
        try:
            from .bot_features.bot_ui import apply_scoped_commands
            await apply_scoped_commands(app.bot)
        except Exception as _e:
            logger.warning(f"Bot {self.bot_id}: command registration failed: {_e}")

        try:
            with self.app_context.app_context():
                from .models import Bot, User
                bot_rec = Bot.query.get(self.bot_id)
                owner = User.query.get(bot_rec.user_id) if bot_rec else None
                tier = getattr(owner, "subscription_tier", "free") if owner else "free"
                if tier == "free":
                    await app.bot.set_my_description(
                        "This group is managed with Telegizer — the all-in-one Telegram community platform. "
                        "Visit telegizer.com to set up your own."
                    )
                    await app.bot.set_my_short_description("Powered by Telegizer")
                else:
                    custom_desc = (bot_rec.settings or {}).get("bot_description") if bot_rec else None
                    await app.bot.set_my_description(custom_desc or "Community Manager Bot")
        except Exception as _e:
            logger.warning(f"Bot {self.bot_id}: set_my_description failed: {_e}")

        from .config import Config
        webhook_base = (Config.CUSTOM_BOT_WEBHOOK_BASE_URL or "").rstrip("/")

        if webhook_base:
            # ── Webhook mode ──────────────────────────────────────────────────
            import secrets as _secrets
            webhook_secret = _secrets.token_urlsafe(32)

            # Persist secret so the Flask route can validate incoming requests
            try:
                with self.app_context.app_context():
                    from .models import db, Bot
                    bot_rec = Bot.query.get(self.bot_id)
                    if bot_rec:
                        bot_rec.webhook_secret = webhook_secret
                        db.session.commit()
            except Exception as _se:
                logger.warning(f"Bot {self.bot_id}: could not save webhook_secret: {_se}")

            webhook_url = f"{webhook_base}/api/telegram/custom/{self.bot_id}"
            try:
                await app.bot.set_webhook(
                    url=webhook_url,
                    secret_token=webhook_secret,
                    drop_pending_updates=True,
                )
                logger.info(f"Bot {self.bot_id}: webhook registered at {webhook_url}")
            except Exception as _whe:
                logger.error(f"Bot {self.bot_id}: set_webhook failed: {_whe}")

            # Keep the Application alive; updates arrive via Flask route
            try:
                while not self._stop_event.is_set():
                    await asyncio.sleep(1)
            finally:
                try:
                    await app.bot.delete_webhook()
                except Exception:
                    pass
                try:
                    await app.stop()
                except Exception:
                    pass
                try:
                    await app.shutdown()
                except Exception:
                    pass
        else:
            # ── Polling mode (default / local dev) ────────────────────────────
            # Delete any leftover webhook before polling — Telegram routes all
            # updates to the webhook and getUpdates returns nothing while set.
            try:
                await app.bot.delete_webhook(drop_pending_updates=False)
                logger.info(f"Bot {self.bot_id}: webhook deleted, starting polling")
            except Exception as _whe:
                logger.warning(f"Bot {self.bot_id}: delete_webhook failed (ok if none set): {_whe}")

            await app.updater.start_polling(drop_pending_updates=True)

            try:
                while not self._stop_event.is_set():
                    await asyncio.sleep(1)
            finally:
                # Shut down cleanly to avoid Telegram Conflict (409) on Railway deploys.
                try:
                    await app.updater.stop()
                except Exception:
                    pass
                try:
                    await app.stop()
                except Exception:
                    pass
                try:
                    await app.shutdown()
                except Exception:
                    pass


class BotManager:

    def __init__(self):
        self.active_bots: dict = {}
        self._lock = threading.Lock()  # guards all mutations of active_bots

    def start_bot(self, bot_id, token, app_context):
        with self._lock:
            if bot_id in self.active_bots:
                logger.info(f"Bot {bot_id} already running")
                return True

        try:
            instance = BotInstance(bot_id, token, app_context)
            thread = threading.Thread(target=instance._run_bot, daemon=True)
            instance.thread = thread
            thread.start()
            with self._lock:
                self.active_bots[bot_id] = instance
            logger.info(f"Bot {bot_id} started")
            return True
        except Exception as e:
            logger.error(f"Failed to start bot {bot_id}: {e}")
            return False

    def stop_bot(self, bot_id):
        with self._lock:
            instance = self.active_bots.get(bot_id)
        if not instance:
            return False

        try:
            instance._stop_event.set()
            if instance.thread:
                instance.thread.join(timeout=10)
            with self._lock:
                self.active_bots.pop(bot_id, None)
            logger.info(f"Bot {bot_id} stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop bot {bot_id}: {e}")
            return False

    def restart_bot(self, bot_id, token, app_context):
        self.stop_bot(bot_id)
        return self.start_bot(bot_id, token, app_context)

    def is_running(self, bot_id):
        with self._lock:
            instance = self.active_bots.get(bot_id)
            if not instance:
                return False
            if instance.thread and not instance.thread.is_alive():
                logger.warning(f"Bot {bot_id} thread has died — removing from active_bots")
                self.active_bots.pop(bot_id, None)
                return False
        return True

    def stop_all(self, timeout_per_bot: int = 8):
        """Gracefully stop every running bot. Called on process shutdown so
        Telegram releases the long-poll connection before the new container
        starts — prevents 409 Conflict errors on Railway rolling deploys."""
        # Flip the global flag first so any poller that crashes mid-teardown
        # exits silently instead of recording a bogus "polling crashed" failure.
        signal_bots_shutting_down()
        with self._lock:
            bot_ids = list(self.active_bots.keys())
        logger.info("[BotManager] Stopping %d bot(s) for graceful shutdown…", len(bot_ids))
        for bot_id in bot_ids:
            try:
                self.stop_bot(bot_id)
            except Exception as exc:
                logger.error("[BotManager] stop_all: error stopping bot %s: %s", bot_id, exc)

    def get_knowledge_base(self):
        with self._lock:
            instances = list(self.active_bots.values())
        for instance in instances:
            return instance.knowledge_base
        return None

    def heartbeat(self, app_context):
        """Update last_active for all running bots. Called by the scheduler loop."""
        with self._lock:
            running_ids = [
                bid for bid, inst in self.active_bots.items()
                if inst.thread and inst.thread.is_alive()
            ]
        if not running_ids:
            return
        try:
            from datetime import datetime as _dt
            with app_context.app_context():
                from .models import db, Bot
                Bot.query.filter(Bot.id.in_(running_ids)).update(
                    {Bot.last_active: _dt.utcnow()},
                    synchronize_session=False,
                )
                db.session.commit()
        except Exception as e:
            logger.error(f"Bot heartbeat failed: {e}")

    def start_all(self, app_context):
        with app_context.app_context():
            from .models import Bot
            bots = Bot.query.filter_by(is_active=True).all()
            for bot in bots:
                try:
                    self.start_bot(bot.id, bot.get_token(), app_context)
                except Exception as e:
                    logger.error(f"start_all: failed to start bot {bot.id}: {e}")
        with self._lock:
            count = len(self.active_bots)
        logger.info(f"Started {count} bots")

    def get_bot_runtime(self, bot_id: int):
        """Return (bot, loop) for a running custom bot, or (None, None).

        Lets Flask request handlers bridge into a custom bot's asyncio loop the
        same way the official lineage uses get_official_bot_loop().
        """
        with self._lock:
            instance = self.active_bots.get(bot_id)
        if instance and instance.application and instance.loop and instance.loop.is_running():
            return instance.application.bot, instance.loop
        return None, None

    def route_update(self, bot_id: int, update_data: dict) -> bool:
        """Dispatch a Telegram update JSON to the correct bot's Application.

        Called from the Flask webhook route. Uses run_coroutine_threadsafe to
        bridge the Flask thread into the bot's asyncio event loop.
        Returns True if routed, False if bot not found or loop unavailable.
        """
        with self._lock:
            instance = self.active_bots.get(bot_id)
        if not instance or not instance.application or not instance.loop:
            logger.warning(f"route_update: bot {bot_id} not found or not ready")
            return False
        try:
            from telegram import Update
            update = Update.de_json(update_data, instance.application.bot)
            future = asyncio.run_coroutine_threadsafe(
                instance.application.process_update(update),
                instance.loop,
            )
            future.result(timeout=30)
            return True
        except Exception as exc:
            logger.error(f"route_update: bot {bot_id} processing error: {exc}")
            return False


bot_manager = BotManager()

