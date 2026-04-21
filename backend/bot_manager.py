import asyncio
import logging
import threading
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes,
)

from .bot_features.verification import VerificationSystem
from .bot_features.welcome import WelcomeSystem
from .bot_features.levels import LevelSystem
from .bot_features.moderation import ModerationSystem

logger = logging.getLogger(__name__)


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

    def _get_group(self, chat_id):
        with self.app_context.app_context():
            from .models import Bot, Group
            bot = Bot.query.get(self.bot_id)
            if not bot:
                return None
            return Group.query.filter_by(
                bot_id=self.bot_id,
                telegram_group_id=str(chat_id),
            ).first()

    def _get_or_create_group(self, chat_id, chat_title=None):
        with self.app_context.app_context():
            from .database import DatabaseManager
            return DatabaseManager.get_or_create_group(self.bot_id, chat_id, chat_title)

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            await update.message.reply_text(
                "👋 Hello! I'm a Telegram Group Manager Bot.\n\n"
                "Add me to your group and I'll help you manage it!\n\n"
                "Use /settings in a group to configure me.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "✅ I'm active in this group! Use /settings to configure me.",
            )

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
            from .app import create_app
            cfg = self.app_context.config
            frontend_url = cfg.get("FRONTEND_URL", "http://localhost:3000")

        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "⚙️ Open Dashboard",
                url=f"{self.app_context.config['FRONTEND_URL']}/bot/{self.bot_id}/group/{group.id}",
            )]
        ])
        await update.message.reply_text(
            "⚙️ Manage this group from the dashboard:",
            reply_markup=keyboard,
        )

    async def handle_rank(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return

        user = update.effective_user
        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)

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

        rank_image = self.levels.generate_rank_card(member, rank, total)
        if rank_image:
            await update.message.reply_photo(
                photo=rank_image,
                caption=f"🏆 Rank card for {user.first_name}",
            )
        else:
            await update.message.reply_text(
                f"📊 *{user.first_name}'s Rank*\n"
                f"Level: {member.level}\n"
                f"XP: {member.xp:,}\n"
                f"Rank: #{rank} of {total}\n"
                f"Role: {member.role.replace('_', ' ').title()}",
                parse_mode="Markdown",
            )

    async def handle_leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return

        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)

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
        lines = ["🏆 *Leaderboard*\n"]
        for i, m in enumerate(top_members):
            name = m.first_name or m.username or f"User {m.telegram_user_id}"
            lines.append(f"{medals[i]} {name} — Level {m.level} ({m.xp:,} XP)")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _require_admin_target(self, update, context):
        chat_id = update.effective_chat.id
        caller = update.effective_user

        try:
            caller_member = await context.bot.get_chat_member(chat_id, caller.id)
            if caller_member.status not in ("creator", "administrator"):
                await update.message.reply_text("❌ You must be an admin to use this command.")
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

        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)
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

    async def handle_ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return

        reason = " ".join(context.args[1:]) if context.args else "No reason"
        if update.message.reply_to_message:
            reason = " ".join(context.args) if context.args else "No reason"

        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)

        try:
            await context.bot.ban_chat_member(update.effective_chat.id, target.id)
            await update.message.reply_text(
                f"🚫 {target.first_name} has been banned.\nReason: {reason}"
            )
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
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to ban: {e}")

    async def handle_kick(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return

        reason = " ".join(context.args) if context.args else "No reason"
        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)

        try:
            await context.bot.ban_chat_member(update.effective_chat.id, target.id)
            await context.bot.unban_chat_member(update.effective_chat.id, target.id)
            await update.message.reply_text(
                f"👢 {target.first_name} has been kicked.\nReason: {reason}"
            )
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

        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)
        until_date = datetime.utcnow() + timedelta(minutes=duration)

        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=target.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date,
            )
            await update.message.reply_text(
                f"🔇 {target.first_name} has been muted for {duration} minutes.\nReason: {reason}"
            )
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
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to mute: {e}")

    async def handle_unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        caller, target = await self._require_admin_target(update, context)
        if not target:
            return

        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)

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
            await update.message.reply_text(f"🔊 {target.first_name} has been unmuted.")
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

        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)
        until_date = datetime.utcnow() + timedelta(hours=duration_hours)

        try:
            await context.bot.ban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=target.id,
                until_date=until_date,
            )
            await update.message.reply_text(
                f"⏳ {target.first_name} banned for {duration_hours}h.\nReason: {reason}"
            )
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

        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)

        with self.app_context.app_context():
            from .models import Member
            member = Member.query.filter_by(
                group_id=group.id,
                telegram_user_id=str(target.id),
            ).first()

        if not member:
            await update.message.reply_text("No data found for this user.")
            return

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
            f"Joined: {member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown'}",
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

        group = self._get_or_create_group(update.effective_chat.id, update.effective_chat.title)

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

    async def handle_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.new_chat_members:
            return

        chat_id = update.effective_chat.id
        group = self._get_or_create_group(chat_id, update.effective_chat.title)

        for new_user in update.message.new_chat_members:
            if new_user.is_bot:
                continue

            with self.app_context.app_context():
                from .database import DatabaseManager
                member = DatabaseManager.get_or_create_member(
                    group.id, new_user.id, new_user.username, new_user.first_name
                )

            settings = group.settings

            if settings.get("verification", {}).get("enabled", False):
                await self.verification.verify_new_member(
                    context.bot, update, new_user, group, settings
                )
            else:
                await self.welcome.send_welcome(context.bot, chat_id, new_user, group)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.effective_user:
            return
        if update.effective_chat.type == "private":
            return

        user = update.effective_user
        chat_id = update.effective_chat.id
        group = self._get_or_create_group(chat_id, update.effective_chat.title)

        with self.app_context.app_context():
            from .database import DatabaseManager
            DatabaseManager.get_or_create_member(
                group.id, user.id, user.username, user.first_name
            )

        if group.settings.get("automod", {}).get("enabled", True):
            blocked = await self.moderation.check_automod(context.bot, update.message, group)
            if blocked:
                return

        if group.settings.get("levels", {}).get("enabled", True):
            await self.levels.add_message_xp(
                context.bot, chat_id, user.id, user.username, user.first_name, group
            )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return

        data = query.data or ""
        parts = data.split(":")

        if parts[0] == "verify":
            method = parts[1]
            group_id = int(parts[2])
            user_id = int(parts[3])
            chat_id = query.message.chat.id

            if query.from_user.id != user_id:
                await query.answer("This verification is not for you.")
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
                    await query.answer()
                    await query.message.reply_text(f"📜 *Rules:*\n{rules}", parse_mode="Markdown")

        else:
            await query.answer()

    def _run_bot(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start_polling())

    async def _start_polling(self):
        self.application = (
            Application.builder()
            .token(self.token)
            .build()
        )

        app = self.application
        app.add_handler(CommandHandler("start", self.handle_start))
        app.add_handler(CommandHandler("settings", self.handle_settings))
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
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.handle_new_member))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        app.add_handler(CallbackQueryHandler(self.handle_callback))

        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        while not self._stop_event.is_set():
            await asyncio.sleep(1)

        await app.updater.stop()
        await app.stop()
        await app.shutdown()


class BotManager:

    def __init__(self):
        self.active_bots = {}

    def start_bot(self, bot_id, token, app_context):
        if bot_id in self.active_bots:
            logger.info(f"Bot {bot_id} already running")
            return True

        try:
            instance = BotInstance(bot_id, token, app_context)
            thread = threading.Thread(target=instance._run_bot, daemon=True)
            instance.thread = thread
            thread.start()
            self.active_bots[bot_id] = instance
            logger.info(f"Bot {bot_id} started")
            return True
        except Exception as e:
            logger.error(f"Failed to start bot {bot_id}: {e}")
            return False

    def stop_bot(self, bot_id):
        instance = self.active_bots.get(bot_id)
        if not instance:
            return False

        try:
            instance._stop_event.set()
            if instance.thread:
                instance.thread.join(timeout=10)
            del self.active_bots[bot_id]
            logger.info(f"Bot {bot_id} stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop bot {bot_id}: {e}")
            return False

    def restart_bot(self, bot_id, token, app_context):
        self.stop_bot(bot_id)
        return self.start_bot(bot_id, token, app_context)

    def is_running(self, bot_id):
        return bot_id in self.active_bots

    def start_all(self, app_context):
        with app_context.app_context():
            from .models import Bot
            bots = Bot.query.filter_by(is_active=True).all()
            for bot in bots:
                self.start_bot(bot.id, bot.bot_token, app_context)
        logger.info(f"Started {len(self.active_bots)} bots")


bot_manager = BotManager()
