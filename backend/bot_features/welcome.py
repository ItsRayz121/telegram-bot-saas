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

        if settings.get("ai_welcome_enabled"):
            ai_text = await self._generate_ai_welcome(
                new_user.first_name or "User",
                group.group_name or "the group",
            )
            if ai_text:
                template = ai_text

        with self.app.app_context():
            if getattr(group, "bot_type", "custom") == "official":
                from ..models import OfficialMember
                member_count = (
                    OfficialMember.query.filter_by(telegram_group_id=group.telegram_chat_id).count()
                    or group.telegram_member_count
                )
            else:
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

        topic_id = settings.get("topic_id")
        send_kwargs = {}
        if topic_id:
            send_kwargs["message_thread_id"] = int(topic_id)

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
                        **send_kwargs,
                    )
                except Exception:
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                        **send_kwargs,
                    )
            else:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                    **send_kwargs,
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

        # Send DM if enabled
        dm_settings = settings.get("welcome", {})
        if dm_settings.get("dm_enabled") and dm_settings.get("dm_message"):
            dm_text = dm_settings["dm_message"].format(
                first_name=new_user.first_name or "Unknown",
                last_name=new_user.last_name or "",
                username=f"@{new_user.username}" if new_user.username else new_user.first_name,
                group_name=group.group_name or "the group",
            )
            try:
                await bot.send_message(
                    chat_id=new_user.id,
                    text=dm_text,
                    parse_mode="Markdown",
                )
            except Exception:
                pass  # User may have DMs blocked

    async def _generate_ai_welcome(self, first_name, group_name):
        try:
            from ..config import Config
            if not Config.OPENAI_API_KEY:
                return None
            from openai import OpenAI
            client = OpenAI(api_key=Config.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{
                    "role": "user",
                    "content": f"Write a short friendly welcome message for {first_name} joining the Telegram group '{group_name}'. Max 2 sentences. Include an emoji. Do not use placeholders."
                }],
                max_tokens=80,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"AI welcome generation error: {e}")
            return None
