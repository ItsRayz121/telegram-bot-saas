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
        # Track users waiting for first-message verification (not yet restricted)
        self.first_message_pending = {}

    async def verify_new_member(self, bot, update, member_user, group, settings):
        v_cfg = settings.get("verification", {})
        method = v_cfg.get("method", "button")
        timeout = v_cfg.get("timeout_seconds", 300)
        verify_on = v_cfg.get("verify_on", "join")
        chat_id = update.effective_chat.id
        user_id = member_user.id
        group_name = group.group_name or "the group"

        if verify_on == "first_message":
            # Store user as pending — restrict + challenge on their first message
            self.first_message_pending[f"{chat_id}:{user_id}"] = {
                "method": method,
                "timeout": timeout,
                "group": group,
                "settings": settings,
                "user": member_user,
            }
            return

        # Restrict immediately on join
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
            )
        except Exception as e:
            logger.error(f"Failed to restrict member {user_id}: {e}")
            return

        await self._send_challenge(bot, chat_id, user_id, member_user, group, method, timeout, settings, group_name)

    async def handle_first_message(self, bot, message, group, settings):
        """Called from bot_manager on every message — triggers challenge if user is first_message pending."""
        chat_id = message.chat.id
        user_id = message.from_user.id
        key = f"{chat_id}:{user_id}"

        info = self.first_message_pending.get(key)
        if not info:
            return False

        self.first_message_pending.pop(key)

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
        except Exception:
            pass

        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
            )
        except Exception as e:
            logger.error(f"Failed to restrict on first message {user_id}: {e}")

        await self._send_challenge(
            bot, chat_id, user_id, info["user"], info["group"],
            info["method"], info["timeout"], info["settings"],
            info["group"].group_name or "the group",
        )
        return True

    async def _send_challenge(self, bot, chat_id, user_id, user, group, method, timeout, settings, group_name):
        if method == "button":
            await self.captcha_button_verification(bot, chat_id, user_id, user, group, timeout, group_name)
        elif method == "math":
            await self.math_verification(bot, chat_id, user_id, user, group, timeout, group_name)
        elif method == "word":
            await self.word_verification(bot, chat_id, user_id, user, group, settings, timeout, group_name)
        else:
            await self.captcha_button_verification(bot, chat_id, user_id, user, group, timeout, group_name)

    async def captcha_button_verification(self, bot, chat_id, user_id, user, group, timeout, group_name):
        v_cfg = group.settings.get("verification", {})
        max_attempts = v_cfg.get("max_attempts", 3)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "✅ I am human — Click to verify",
                callback_data=f"verify:button:{group.id}:{user_id}",
            )]
        ])
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f"👋 Welcome to *{group_name}*, {user.first_name}!\n\n"
                f"Please click the button below to verify you're human.\n"
                f"You have {timeout} seconds."
            ),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        self.pending[f"{chat_id}:{user_id}"] = {
            "method": "button",
            "message_id": msg.message_id,
            "expires_at": datetime.utcnow() + timedelta(seconds=timeout),
            "group_id": group.id,
            "bot_type": getattr(group, "bot_type", "custom"),
            "telegram_group_id": getattr(group, "telegram_chat_id", None),
            "attempts": 0,
            "max_attempts": max_attempts,
            "kick_on_fail": v_cfg.get("kick_on_fail", True),
        }
        asyncio.get_event_loop().call_later(
            timeout,
            lambda: asyncio.ensure_future(self._check_verification_timeout(bot, chat_id, user_id, group)),
        )

    async def math_verification(self, bot, chat_id, user_id, user, group, timeout, group_name):
        v_cfg = group.settings.get("verification", {})
        max_attempts = v_cfg.get("max_attempts", 3)
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
                f"🔢 Welcome to *{group_name}*! {user.first_name}, solve this to verify:\n\n"
                f"*{a} {op_sym} {b} = ?*\n\n"
                f"You have {timeout} seconds. Attempts: 0/{max_attempts}"
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
            "bot_type": getattr(group, "bot_type", "custom"),
            "telegram_group_id": getattr(group, "telegram_chat_id", None),
            "attempts": 0,
            "max_attempts": max_attempts,
            "a": a, "b": b, "op_sym": op_sym, "options": options,
            "kick_on_fail": v_cfg.get("kick_on_fail", True),
        }
        asyncio.get_event_loop().call_later(
            timeout,
            lambda: asyncio.ensure_future(self._check_verification_timeout(bot, chat_id, user_id, group)),
        )

    async def word_verification(self, bot, chat_id, user_id, user, group, settings, timeout, group_name):
        v_cfg = group.settings.get("verification", {})
        max_attempts = v_cfg.get("max_attempts", 3)
        question = settings.get("verification", {}).get("custom_question", "What is the group's main topic?")
        msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f"❓ Welcome to *{group_name}*! {user.first_name}, answer this to verify:\n\n"
                f"*{question}*\n\n"
                f"Reply with the correct answer. You have {timeout} seconds. Max attempts: {max_attempts}"
            ),
            parse_mode="Markdown",
        )
        self.pending[f"{chat_id}:{user_id}"] = {
            "method": "word",
            "message_id": msg.message_id,
            "answer": settings.get("verification", {}).get("custom_answer", "").lower().strip(),
            "expires_at": datetime.utcnow() + timedelta(seconds=timeout),
            "group_id": group.id,
            "bot_type": getattr(group, "bot_type", "custom"),
            "telegram_group_id": getattr(group, "telegram_chat_id", None),
            "attempts": 0,
            "max_attempts": max_attempts,
            "kick_on_fail": v_cfg.get("kick_on_fail", True),
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
            pending["attempts"] = pending.get("attempts", 0) + 1
            max_attempts = pending.get("max_attempts", 3)

            if pending["attempts"] >= max_attempts:
                await query.answer(f"❌ Too many wrong attempts ({max_attempts}/{max_attempts}). Removed.")
                await self.fail_verification(bot, chat_id, user_id, pending, group_id)
                return False

            remaining = max_attempts - pending["attempts"]
            await query.answer(f"❌ Wrong answer! {remaining} attempt(s) left.")
            return False

    async def handle_word_answer(self, bot, message, group):
        """Called from message handler when a user in pending state sends a text reply."""
        chat_id = message.chat.id
        user_id = message.from_user.id
        key = f"{chat_id}:{user_id}"
        pending = self.pending.get(key)

        if not pending or pending.get("method") != "word":
            return False

        if datetime.utcnow() > pending["expires_at"]:
            await self.fail_verification(bot, chat_id, user_id, pending, group.id)
            return True

        answer = (message.text or "").lower().strip()
        correct = pending.get("answer", "")

        if answer == correct:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            except Exception:
                pass

            class FakeQuery:
                async def answer(self, text): pass

            await self._complete_verification(bot, FakeQuery(), chat_id, user_id, pending)
            try:
                await bot.send_message(chat_id=chat_id, text=f"✅ {message.from_user.first_name} verified successfully!")
            except Exception:
                pass
            return True
        else:
            pending["attempts"] = pending.get("attempts", 0) + 1
            max_attempts = pending.get("max_attempts", 3)
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            except Exception:
                pass
            if pending["attempts"] >= max_attempts:
                await self.fail_verification(bot, chat_id, user_id, pending, group.id)
                try:
                    await bot.send_message(chat_id=chat_id, text=f"❌ {message.from_user.first_name} failed verification.")
                except Exception:
                    pass
            else:
                remaining = max_attempts - pending["attempts"]
                try:
                    await bot.send_message(chat_id=chat_id, text=f"❌ Wrong answer. {remaining} attempt(s) left.")
                except Exception:
                    pass
            return True

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
                from ..models import db
                bot_type = pending.get("bot_type", "custom")
                if bot_type == "official":
                    from ..models import OfficialMember
                    tg_group_id = pending.get("telegram_group_id")
                    member = OfficialMember.query.filter_by(
                        telegram_group_id=tg_group_id,
                        telegram_user_id=str(user_id),
                    ).first() if tg_group_id else None
                else:
                    from ..models import Member
                    member = Member.query.filter_by(
                        group_id=pending["group_id"],
                        telegram_user_id=str(user_id),
                    ).first()
                if member:
                    member.is_verified = True
                    db.session.commit()
        except Exception as e:
            logger.error(f"Complete verification error: {e}")
        finally:
            self.pending.pop(key, None)

    async def fail_verification(self, bot, chat_id, user_id, pending, group_id):
        # kick_on_fail is stored in pending at challenge time so we avoid
        # a hardcoded Group model query here (supports both official and custom bots).
        key = f"{chat_id}:{user_id}"
        try:
            if pending.get("kick_on_fail", True):
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
