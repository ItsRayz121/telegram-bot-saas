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

from .bot_features.verification import VerificationSystem
from .bot_features.welcome import WelcomeSystem
from .bot_features.levels import LevelSystem
from .bot_features.moderation import ModerationSystem
from .bot_features.knowledge_base import KnowledgeBaseSystem

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
        self.knowledge_base = KnowledgeBaseSystem(app_context)

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

    async def _get_or_create_group(self, chat_id, chat_title=None, bot=None):
        member_count = None
        if bot:
            try:
                member_count = await bot.get_chat_member_count(chat_id)
            except Exception:
                pass
        with self.app_context.app_context():
            from .database import DatabaseManager
            return DatabaseManager.get_or_create_group(self.bot_id, chat_id, chat_title, member_count)

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

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
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
        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)

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

        rank_image = self.levels.generate_rank_card(member, rank, total, group.settings)
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

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)

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

        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
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
        await update.message.reply_text(
            f"👤 *Your Stats*\n"
            f"Level: {member.level} | XP: {member.xp:,}\n"
            f"Role: {member.role.replace('_', ' ').title()}\n"
            f"Warnings: {member.warnings}\n"
            f"Verified: {'✅' if member.is_verified else '❌'}\n"
            f"Joined: {member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown'}",
            parse_mode="Markdown",
        )

    async def handle_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        try:
            admins = await context.bot.get_chat_administrators(update.effective_chat.id)
            lines = ["👮 *Group Admins*\n"]
            for a in admins:
                name = a.user.first_name or a.user.username or str(a.user.id)
                title = f" ({a.custom_title})" if getattr(a, "custom_title", None) else ""
                lines.append(f"• {name}{title}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Could not fetch admins: {e}")

    async def handle_roles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        group = await self._get_or_create_group(update.effective_chat.id, update.effective_chat.title, context.bot)
        roles = group.settings.get("levels", {}).get("roles", [])
        if not roles:
            await update.message.reply_text("No roles configured.")
            return
        lines = ["🎖 *Roles*\n"]
        for r in sorted(roles, key=lambda x: x["level"]):
            lines.append(f"Level {r['level']}+ → {r['name']}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

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
        await update.message.reply_text(
            f"🔍 *Whois: {member.first_name or 'Unknown'}*\n"
            f"Username: @{member.username or 'none'}\n"
            f"ID: `{member.telegram_user_id}`\n"
            f"Level: {member.level} | XP: {member.xp:,}\n"
            f"Role: {member.role.replace('_', ' ').title()}\n"
            f"Warnings: {member.warnings}\n"
            f"Verified: {'✅' if member.is_verified else '❌'}\n"
            f"Muted: {'🔇' if member.is_muted else '🔊'}\n"
            f"Joined: {member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown'}",
            parse_mode="Markdown",
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
            db.session.commit()
            DatabaseManager.log_action(
                group_id=group.id,
                action_type="removewarning",
                target_user_id=str(target.id),
                target_username=target.username,
                moderator_id=str(caller.id),
                moderator_username=caller.username,
                reason="Warning removed by admin",
                extra_data={"remaining_warnings": member.warnings},
            )
        await update.message.reply_text(
            f"✅ Removed 1 warning from {target.first_name}.\n"
            f"Remaining warnings: {member.warnings}"
        )

    async def handle_groupinfo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            return
        chat = update.effective_chat
        group = await self._get_or_create_group(chat.id, chat.title, context.bot)
        with self.app_context.app_context():
            from .models import Member, AuditLog
            member_count = Member.query.filter_by(group_id=group.id).count()
            total_warnings = sum(m.warnings for m in Member.query.filter_by(group_id=group.id).all())
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
        name = " ".join(context.args) if context.args else f"Link by {user.first_name}"
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
                f"🔗 *Invite Link Created*\nName: {name}\nLink: {link.invite_link}",
                parse_mode="Markdown",
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to create invite link: {e}")

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

        if should_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            except Exception:
                pass

    async def handle_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.new_chat_members:
            return

        chat_id = update.effective_chat.id
        group = await self._get_or_create_group(chat_id, update.effective_chat.title, context.bot)

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
        group = await self._get_or_create_group(chat_id, update.effective_chat.title, context.bot)

        with self.app_context.app_context():
            from .database import DatabaseManager
            DatabaseManager.get_or_create_member(
                group.id, user.id, user.username, user.first_name
            )

        # Delete command messages if auto_clean.delete_commands is on
        if (update.message.text or "").startswith("/"):
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

        # Automatic KB reply
        kb_settings = group.settings.get("knowledge_base", {})
        if kb_settings.get("enabled", True) and kb_settings.get("auto_reply_enabled", False):
            await self._handle_auto_kb_reply(update, context, group, kb_settings)

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

        logger.debug(f"KB auto-reply: querying KB for group {group.id}, question: {text[:80]!r}")
        answer, confidence = await self.knowledge_base.answer_question(text, group.id)

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
        elif kb_settings.get("fallback_enabled", False) and answer:
            # Fallback: reply with a softer phrasing when confidence is low
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

    async def handle_my_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fires when the bot is added to or removed from a group."""
        result = update.my_chat_member
        if not result:
            return
        chat = result.chat
        if chat.type not in ("group", "supergroup"):
            return
        new_status = result.new_chat_member.status
        if new_status in ("member", "administrator"):
            await self._get_or_create_group(chat.id, chat.title, context.bot)

    def _run_bot(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        # Retry loop so a Conflict error (two instances) recovers automatically
        max_retries = 5
        for attempt in range(max_retries):
            if self._stop_event.is_set():
                break
            try:
                self.loop.run_until_complete(self._start_polling())
                break  # clean exit
            except Exception as e:
                from telegram.error import Conflict
                if isinstance(e, Conflict):
                    wait = 15 * (attempt + 1)
                    logger.warning(
                        f"Bot {self.bot_id}: Conflict error (another instance is polling). "
                        f"Retrying in {wait}s (attempt {attempt + 1}/{max_retries})"
                    )
                    import time
                    time.sleep(wait)
                else:
                    logger.error(f"Bot {self.bot_id}: polling crashed: {e}", exc_info=True)
                    break

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
        if _REACTION_HANDLER_AVAILABLE:
            app.add_handler(_MessageReactionHandler(self.handle_reaction))
        app.add_handler(ChatMemberHandler(self.handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
        app.add_handler(ChatMemberHandler(self.handle_chat_member, ChatMemberHandler.CHAT_MEMBER))
        app.add_handler(MessageHandler(filters.StatusUpdate.ALL, self.handle_service_message))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.handle_new_member))
        app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, self.handle_message))
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
        instance = self.active_bots.get(bot_id)
        if not instance:
            return False
        if instance.thread and not instance.thread.is_alive():
            logger.warning(f"Bot {bot_id} thread has died — removing from active_bots")
            del self.active_bots[bot_id]
            return False
        return True

    def get_knowledge_base(self):
        # Return KB system from any active bot instance (they all share the same app context logic)
        for instance in self.active_bots.values():
            return instance.knowledge_base
        # Fallback: create one without app context (will fail gracefully)
        return None

    def start_all(self, app_context):
        with app_context.app_context():
            from .models import Bot
            bots = Bot.query.filter_by(is_active=True).all()
            for bot in bots:
                self.start_bot(bot.id, bot.bot_token, app_context)
        logger.info(f"Started {len(self.active_bots)} bots")


bot_manager = BotManager()
