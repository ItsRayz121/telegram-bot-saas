import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class WelcomeSystem:

    def __init__(self, app):
        self.app = app

    async def send_welcome(self, bot, chat_id, new_user, group):
        settings = group.settings.get("welcome", {})
        if not settings.get("enabled", True):
            return

        template = settings.get(
            "message",
            "Welcome {first_name} to {group_name}! 👋",
        )

        with self.app.app_context():
            from ..models import Member
            member_count = Member.query.filter_by(group_id=group.id).count()

        message_text = template.format(
            first_name=new_user.first_name or "Unknown",
            last_name=new_user.last_name or "",
            username=f"@{new_user.username}" if new_user.username else new_user.first_name,
            full_name=new_user.full_name if hasattr(new_user, "full_name") else new_user.first_name,
            group_name=group.group_name or "the group",
            member_count=member_count,
            user_id=new_user.id,
        )

        if settings.get("show_rules") and settings.get("rules_text"):
            message_text += f"\n\n📜 *Rules:*\n{settings['rules_text']}"

        keyboard = None
        if settings.get("rules_text"):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 Read Rules", callback_data=f"rules:{group.id}")]
            ])

        try:
            media_url = settings.get("media_url", "")
            msg = None

            if media_url:
                try:
                    msg = await bot.send_photo(
                        chat_id=chat_id,
                        photo=media_url,
                        caption=message_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
                except Exception:
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
            else:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )

            delete_after = settings.get("delete_after_seconds", 0)
            if delete_after and delete_after > 0 and msg:
                import asyncio
                await asyncio.sleep(delete_after)
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Welcome message error: {e}")
