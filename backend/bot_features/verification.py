import asyncio
import random
import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions

logger = logging.getLogger(__name__)

MATH_OPS = [
    ("add", "+"),
    ("sub", "-"),
    ("mul", "×"),
]


class VerificationSystem:

    def __init__(self, app, bot_manager):
        self.app = app
        self.bot_manager = bot_manager
        self.pending = {}

    async def verify_new_member(self, bot, update, member_user, group, settings):
        method = settings.get("verification", {}).get("method", "button")
        timeout = settings.get("verification", {}).get("timeout_seconds", 60)
        chat_id = update.effective_chat.id
        user_id = member_user.id

        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
            )
        except Exception as e:
            logger.error(f"Failed to restrict member {user_id}: {e}")
            return

        if method == "button":
            await self.captcha_button_verification(bot, chat_id, user_id, member_user, group, timeout)
        elif method == "math":
            await self.math_verification(bot, chat_id, user_id, member_user, group, timeout)
        elif method == "word":
            await self.word_verification(bot, chat_id, user_id, member_user, group, settings, timeout)
        else:
            await self.captcha_button_verification(bot, chat_id, user_id, member_user, group, timeout)

    async def captcha_button_verification(self, bot, chat_id, user_id, user, group, timeout):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "✅ I am human - Click to verify",
                callback_data=f"verify:button:{group.id}:{user_id}",
            )]
        ])
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f"👋 Welcome {user.first_name}!\n\n"
                f"Please click the button below to verify you are human.\n"
                f"You have {timeout} seconds."
            ),
            reply_markup=keyboard,
        )
        self.pending[f"{chat_id}:{user_id}"] = {
            "method": "button",
            "message_id": msg.message_id,
            "expires_at": datetime.utcnow() + timedelta(seconds=timeout),
            "group_id": group.id,
        }
        asyncio.get_event_loop().call_later(
            timeout,
            lambda: asyncio.ensure_future(self._check_verification_timeout(bot, chat_id, user_id, group)),
        )

    async def math_verification(self, bot, chat_id, user_id, user, group, timeout):
        op_name, op_sym = random.choice(MATH_OPS)
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        if op_name == "add":
            answer = a + b
        elif op_name == "sub":
            answer = abs(a - b)
            a, b = max(a, b), min(a, b)
        else:
            a = random.randint(1, 10)
            b = random.randint(1, 10)
            answer = a * b

        wrong_answers = set()
        while len(wrong_answers) < 3:
            wrong = answer + random.randint(-5, 5)
            if wrong != answer and wrong >= 0:
                wrong_answers.add(wrong)
        wrong_answers = list(wrong_answers)[:3]

        options = [answer] + wrong_answers
        random.shuffle(options)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(str(opt), callback_data=f"verify:math:{group.id}:{user_id}:{opt}:{answer}") for opt in options[:2]],
            [InlineKeyboardButton(str(opt), callback_data=f"verify:math:{group.id}:{user_id}:{opt}:{answer}") for opt in options[2:]],
        ])

        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f"🔢 {user.first_name}, solve this to verify:\n\n"
                f"*{a} {op_sym} {b} = ?*\n\n"
                f"You have {timeout} seconds."
            ),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        self.pending[f"{chat_id}:{user_id}"] = {
            "method": "math",
            "message_id": msg.message_id,
            "answer": answer,
            "expires_at": datetime.utcnow() + timedelta(seconds=timeout),
            "group_id": group.id,
        }
        asyncio.get_event_loop().call_later(
            timeout,
            lambda: asyncio.ensure_future(self._check_verification_timeout(bot, chat_id, user_id, group)),
        )

    async def word_verification(self, bot, chat_id, user_id, user, group, settings, timeout):
        question = settings.get("verification", {}).get("custom_question", "What is the group's main topic?")
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f"❓ {user.first_name}, answer this question to verify:\n\n"
                f"*{question}*\n\n"
                f"Reply with the correct answer. You have {timeout} seconds."
            ),
            parse_mode="Markdown",
        )
        self.pending[f"{chat_id}:{user_id}"] = {
            "method": "word",
            "message_id": msg.message_id,
            "answer": settings.get("verification", {}).get("custom_answer", "").lower().strip(),
            "expires_at": datetime.utcnow() + timedelta(seconds=timeout),
            "group_id": group.id,
        }
        asyncio.get_event_loop().call_later(
            timeout,
            lambda: asyncio.ensure_future(self._check_verification_timeout(bot, chat_id, user_id, group)),
        )

    async def handle_verification_callback(self, bot, query, chat_id, user_id, group_id, method, extra_data):
        key = f"{chat_id}:{user_id}"
        pending = self.pending.get(key)

        if not pending:
            await query.answer("Verification already processed or expired.")
            return False

        if datetime.utcnow() > pending["expires_at"]:
            await query.answer("Verification expired!")
            await self.fail_verification(bot, chat_id, user_id, pending, group_id)
            return False

        verified = False
        if method == "button":
            verified = True
        elif method == "math":
            chosen, correct = extra_data
            verified = int(chosen) == int(correct)
        elif method == "word":
            verified = False

        if verified:
            await self._complete_verification(bot, query, chat_id, user_id, pending)
            return True
        else:
            await query.answer("❌ Wrong answer! Try again.")
            return False

    async def _complete_verification(self, bot, query, chat_id, user_id, pending):
        key = f"{chat_id}:{user_id}"
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
            await bot.delete_message(chat_id=chat_id, message_id=pending["message_id"])
            await query.answer("✅ Verified! Welcome to the group.")

            with self.app.app_context():
                from ..models import Member
                member = Member.query.filter_by(
                    group_id=pending["group_id"],
                    telegram_user_id=str(user_id),
                ).first()
                if member:
                    member.is_verified = True
                    from ..models import db
                    db.session.commit()
        except Exception as e:
            logger.error(f"Complete verification error: {e}")
        finally:
            self.pending.pop(key, None)

    async def fail_verification(self, bot, chat_id, user_id, pending, group_id):
        key = f"{chat_id}:{user_id}"
        try:
            with self.app.app_context():
                from ..models import Group
                group = Group.query.get(group_id)
                if group and group.settings.get("verification", {}).get("kick_on_fail", True):
                    await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                    await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            try:
                await bot.delete_message(chat_id=chat_id, message_id=pending["message_id"])
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Fail verification error: {e}")
        finally:
            self.pending.pop(key, None)

    async def _check_verification_timeout(self, bot, chat_id, user_id, group):
        key = f"{chat_id}:{user_id}"
        pending = self.pending.get(key)
        if pending and datetime.utcnow() > pending["expires_at"]:
            await self.fail_verification(bot, chat_id, user_id, pending, group.id)
