import asyncio
import os
import random
import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions

logger = logging.getLogger(__name__)

# Kill switch: set VERIFICATION_DB_PERSIST=0 to fall back to the old in-memory-only
# behavior (no write-through, no reload-on-restart) without a deploy.
def _db_persist_enabled() -> bool:
    return os.environ.get("VERIFICATION_DB_PERSIST", "1") != "0"

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

    def _save_pending(self, chat_id, user_id):
        """Write-through: persist a pending challenge to pending_verifications so
        it survives a gunicorn worker recycle (Procfile: --max-requests), which
        tears down this process and rebuilds a fresh, empty `self.pending`."""
        if not _db_persist_enabled():
            return
        key = f"{chat_id}:{user_id}"
        data = self.pending.get(key)
        if not data:
            return
        try:
            with self.app.app_context():
                from ..models import db, PendingVerification
                row = PendingVerification.query.filter_by(chat_id=chat_id, user_id=user_id).first()
                if not row:
                    row = PendingVerification(chat_id=chat_id, user_id=user_id)
                    db.session.add(row)
                row.method = data.get("method", "button")
                row.msg_id = data.get("message_id")
                row.message_thread_id = data.get("message_thread_id")
                row.answer = str(data["answer"]) if data.get("answer") is not None else None
                row.expires_at = data["expires_at"]
                row.kick_on_fail = bool(data.get("kick_on_fail", True))
                row.auto_delete_on_timeout = bool(data.get("auto_delete_on_timeout", True))
                row.max_attempts = int(data.get("max_attempts", 3))
                row.attempts = int(data.get("attempts", 0))
                row.bot_id = self.bot_manager.bot_id
                row.group_id = data.get("group_id")
                row.bot_type = data.get("bot_type", "custom")
                row.telegram_group_id = data.get("telegram_group_id")
                db.session.commit()
        except Exception as exc:
            logger.debug("Verification _save_pending failed: %s", exc)

    def _remove_pending(self, chat_id, user_id):
        if not _db_persist_enabled():
            return
        try:
            with self.app.app_context():
                from ..models import db, PendingVerification
                PendingVerification.query.filter_by(chat_id=chat_id, user_id=user_id).delete()
                db.session.commit()
        except Exception as exc:
            logger.debug("Verification _remove_pending failed: %s", exc)

    def load_pending_from_db(self, bot):
        """Restore this bot's in-flight challenges from the DB on (re)start.

        Without this, a gunicorn worker recycle (or any process restart) wipes
        `self.pending` and a user clicking a challenge sent moments earlier gets
        "Verification already processed or expired" even though they're well
        within the original timeout. Also re-arms the timeout timer for each
        restored challenge, since the original `call_later` died with the old
        process/event loop.
        """
        if not _db_persist_enabled():
            return
        restored = []
        try:
            with self.app.app_context():
                from ..models import PendingVerification
                rows = PendingVerification.query.filter(
                    PendingVerification.bot_id == self.bot_manager.bot_id,
                    PendingVerification.expires_at > datetime.utcnow(),
                ).all()
                for row in rows:
                    key = f"{row.chat_id}:{row.user_id}"
                    self.pending[key] = {
                        "method": row.method,
                        "message_id": row.msg_id,
                        "message_thread_id": row.message_thread_id,
                        "answer": row.answer,
                        "expires_at": row.expires_at,
                        "group_id": row.group_id,
                        "bot_type": row.bot_type or "custom",
                        "telegram_group_id": row.telegram_group_id,
                        "attempts": row.attempts or 0,
                        "max_attempts": row.max_attempts or 3,
                        "kick_on_fail": row.kick_on_fail,
                        "auto_delete_on_timeout": row.auto_delete_on_timeout,
                    }
                    restored.append((row.chat_id, row.user_id, row.group_id, row.expires_at))
        except Exception as exc:
            logger.warning("Bot %s: load_pending_from_db failed: %s", self.bot_manager.bot_id, exc)
            return

        for chat_id, user_id, group_id, expires_at in restored:
            remaining = max(1.0, (expires_at - datetime.utcnow()).total_seconds())
            asyncio.get_event_loop().call_later(
                remaining,
                lambda c=chat_id, u=user_id, g=group_id: asyncio.ensure_future(
                    self._check_verification_timeout(bot, c, u, g)
                ),
            )
        if restored:
            logger.info(
                "Bot %s: restored %d pending verification(s) from DB",
                self.bot_manager.bot_id, len(restored),
            )

    async def verify_new_member(self, bot, update, member_user, group, settings):
        v_cfg = settings.get("verification", {})
        method = v_cfg.get("method", "button")
        timeout = v_cfg.get("timeout_seconds", 300)
        verify_on = v_cfg.get("verify_on", "join")
        chat_id = update.effective_chat.id
        user_id = member_user.id
        group_name = group.group_name or "the group"
        # Preserve forum topic context so challenge lands in the right topic
        message_thread_id = getattr(update.message, "message_thread_id", None) if update.message else None

        if verify_on == "first_message":
            self.first_message_pending[f"{chat_id}:{user_id}"] = {
                "method": method,
                "timeout": timeout,
                "group": group,
                "settings": settings,
                "user": member_user,
                "message_thread_id": message_thread_id,
                # Only read by prune(). An entry is dropped when the joiner is
                # popped on their first message — a joiner who never speaks used
                # to keep this dict entry (and with it a detached ORM group row,
                # its settings JSON and a Telegram User object) for the life of
                # the process.
                "queued_at": datetime.utcnow(),
            }
            return

        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
            )
        except Exception as e:
            logger.error(f"Failed to restrict member {user_id}: {e}")
            return

        await self._send_challenge(
            bot, chat_id, user_id, member_user, group, method, timeout, settings, group_name,
            message_thread_id=message_thread_id,
        )

    # Retention for the two in-process pending maps. Both are keyed per
    # (chat, user) and neither shrank on its own: `pending` leaked whenever a
    # challenge timeout handler was lost (bot restart, event-loop teardown), and
    # `first_message_pending` leaked one entry — holding a detached ORM group,
    # its settings dict and a Telegram User — for every member who joined and
    # never posted. Only a redeploy ever reclaimed them.
    #
    # Dropping an expired entry cannot change a decision: `pending` is always
    # read past an `expires_at` check that already treats it as gone, and a
    # `first_message_pending` entry older than the cutoff would today be wiped
    # by any redeploy anyway (which happens far more often than every 7 days).
    _FIRST_MESSAGE_TTL = timedelta(days=7)

    def prune(self) -> dict:
        """Drop expired entries. Returns the sizes after pruning, for diagnostics."""
        now = datetime.utcnow()
        for key, val in list(self.pending.items()):
            exp = (val or {}).get("expires_at")
            # Grace period past expiry so an in-flight answer is never dropped
            # out from under the handler that is about to read it.
            if exp is None or now > exp + timedelta(minutes=10):
                self.pending.pop(key, None)
        cutoff = now - self._FIRST_MESSAGE_TTL
        for key, val in list(self.first_message_pending.items()):
            queued = (val or {}).get("queued_at")
            if queued is None or queued < cutoff:
                self.first_message_pending.pop(key, None)
        return {
            "pending": len(self.pending),
            "first_message_pending": len(self.first_message_pending),
        }

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
            message_thread_id=info.get("message_thread_id"),
        )
        return True

    async def _send_challenge(self, bot, chat_id, user_id, user, group, method, timeout, settings, group_name,
                              message_thread_id=None):
        if method == "button":
            await self.captcha_button_verification(
                bot, chat_id, user_id, user, group, timeout, group_name, message_thread_id)
        elif method == "math":
            await self.math_verification(
                bot, chat_id, user_id, user, group, timeout, group_name, message_thread_id)
        elif method == "word":
            await self.word_verification(
                bot, chat_id, user_id, user, group, settings, timeout, group_name, message_thread_id)
        else:
            await self.captcha_button_verification(
                bot, chat_id, user_id, user, group, timeout, group_name, message_thread_id)

    async def captcha_button_verification(self, bot, chat_id, user_id, user, group, timeout, group_name,
                                          message_thread_id=None):
        v_cfg = group.settings.get("verification", {})
        max_attempts = v_cfg.get("max_attempts", 3)
        auto_delete = v_cfg.get("auto_delete_on_timeout", True)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "✅ I am human — Click to verify",
                callback_data=f"verify:button:{group.id}:{user_id}",
            )]
        ])
        send_kwargs = dict(
            chat_id=chat_id,
            text=(
                f"👋 Welcome to <b>{group_name}</b>, {user.first_name}!\n\n"
                f"Please click the button below to verify you're human.\n"
                f"You have {timeout} seconds."
            ),
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        if message_thread_id:
            send_kwargs["message_thread_id"] = message_thread_id
        msg = await bot.send_message(**send_kwargs)
        self.pending[f"{chat_id}:{user_id}"] = {
            "method": "button",
            "message_id": msg.message_id,
            "message_thread_id": message_thread_id,
            "expires_at": datetime.utcnow() + timedelta(seconds=timeout),
            "group_id": group.id,
            "bot_type": getattr(group, "bot_type", "custom"),
            "telegram_group_id": getattr(group, "telegram_chat_id", None),
            "attempts": 0,
            "max_attempts": max_attempts,
            "kick_on_fail": v_cfg.get("kick_on_fail", True),
            "auto_delete_on_timeout": auto_delete,
        }
        self._save_pending(chat_id, user_id)
        asyncio.get_event_loop().call_later(
            timeout,
            lambda: asyncio.ensure_future(self._check_verification_timeout(bot, chat_id, user_id, group.id)),
        )

    async def math_verification(self, bot, chat_id, user_id, user, group, timeout, group_name,
                               message_thread_id=None):
        v_cfg = group.settings.get("verification", {})
        max_attempts = v_cfg.get("max_attempts", 3)
        auto_delete = v_cfg.get("auto_delete_on_timeout", True)
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

        send_kwargs = dict(
            chat_id=chat_id,
            text=(
                f"🔢 Welcome to <b>{group_name}</b>! {user.first_name}, solve this to verify:\n\n"
                f"<b>{a} {op_sym} {b} = ?</b>\n\n"
                f"You have {timeout} seconds. Attempts: 0/{max_attempts}"
            ),
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        if message_thread_id:
            send_kwargs["message_thread_id"] = message_thread_id
        msg = await bot.send_message(**send_kwargs)
        self.pending[f"{chat_id}:{user_id}"] = {
            "method": "math",
            "message_id": msg.message_id,
            "message_thread_id": message_thread_id,
            "answer": answer,
            "expires_at": datetime.utcnow() + timedelta(seconds=timeout),
            "group_id": group.id,
            "bot_type": getattr(group, "bot_type", "custom"),
            "telegram_group_id": getattr(group, "telegram_chat_id", None),
            "attempts": 0,
            "max_attempts": max_attempts,
            "a": a, "b": b, "op_sym": op_sym, "options": options,
            "kick_on_fail": v_cfg.get("kick_on_fail", True),
            "auto_delete_on_timeout": auto_delete,
        }
        self._save_pending(chat_id, user_id)
        asyncio.get_event_loop().call_later(
            timeout,
            lambda: asyncio.ensure_future(self._check_verification_timeout(bot, chat_id, user_id, group.id)),
        )

    async def word_verification(self, bot, chat_id, user_id, user, group, settings, timeout, group_name,
                               message_thread_id=None):
        v_cfg = group.settings.get("verification", {})
        max_attempts = v_cfg.get("max_attempts", 3)
        auto_delete = v_cfg.get("auto_delete_on_timeout", True)
        question = settings.get("verification", {}).get("custom_question", "What is the group's main topic?")
        send_kwargs = dict(
            chat_id=chat_id,
            text=(
                f"❓ Welcome to <b>{group_name}</b>! {user.first_name}, answer this to verify:\n\n"
                f"<b>{question}</b>\n\n"
                f"Reply with the correct answer. You have {timeout} seconds. Max attempts: {max_attempts}"
            ),
            parse_mode="HTML",
        )
        if message_thread_id:
            send_kwargs["message_thread_id"] = message_thread_id
        msg = await bot.send_message(**send_kwargs)
        self.pending[f"{chat_id}:{user_id}"] = {
            "method": "word",
            "message_id": msg.message_id,
            "message_thread_id": message_thread_id,
            "answer": settings.get("verification", {}).get("custom_answer", "").lower().strip(),
            "expires_at": datetime.utcnow() + timedelta(seconds=timeout),
            "group_id": group.id,
            "bot_type": getattr(group, "bot_type", "custom"),
            "telegram_group_id": getattr(group, "telegram_chat_id", None),
            "attempts": 0,
            "max_attempts": max_attempts,
            "kick_on_fail": v_cfg.get("kick_on_fail", True),
            "auto_delete_on_timeout": auto_delete,
        }
        self._save_pending(chat_id, user_id)
        asyncio.get_event_loop().call_later(
            timeout,
            lambda: asyncio.ensure_future(self._check_verification_timeout(bot, chat_id, user_id, group.id)),
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
            self._save_pending(chat_id, user_id)
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
                self._save_pending(chat_id, user_id)
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
                    can_send_audios=True,
                    can_send_documents=True,
                    can_send_photos=True,
                    can_send_videos=True,
                    can_send_video_notes=True,
                    can_send_voice_notes=True,
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
            self._remove_pending(chat_id, user_id)

    async def fail_verification(self, bot, chat_id, user_id, pending, group_id):
        # kick_on_fail is stored in pending at challenge time so we avoid
        # a hardcoded Group model query here (supports both official and custom bots).
        key = f"{chat_id}:{user_id}"
        try:
            if pending.get("kick_on_fail", True):
                # 1-C-02: temp ban + write PendingUnban; scheduler retries unban after 1h
                await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                try:
                    with self.app.app_context():
                        from ..models import db, PendingUnban
                        db.session.add(PendingUnban(
                            telegram_chat_id=chat_id,
                            telegram_user_id=user_id,
                            unban_at=datetime.utcnow() + timedelta(hours=1),
                        ))
                        db.session.commit()
                except Exception as db_exc:
                    logger.warning("PendingUnban write failed: %s", db_exc)
            # Always delete the challenge message to keep the group clean
            try:
                await bot.delete_message(chat_id=chat_id, message_id=pending["message_id"])
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Fail verification error: {e}")
        finally:
            self.pending.pop(key, None)
            self._remove_pending(chat_id, user_id)

    async def _check_verification_timeout(self, bot, chat_id, user_id, group_id):
        """Called when the timeout timer fires. Kicks/restricts and auto-deletes the challenge message."""
        key = f"{chat_id}:{user_id}"
        pending = self.pending.get(key)
        if not pending:
            return
        if datetime.utcnow() <= pending["expires_at"]:
            # Timer fired early (e.g. clock drift) — ignore
            return

        auto_delete = pending.get("auto_delete_on_timeout", True)

        if pending.get("kick_on_fail", True):
            # Full fail path: kick + delete message
            await self.fail_verification(bot, chat_id, user_id, pending, group_id)
        else:
            # Restrict-only path: user stays restricted but message is auto-deleted if enabled
            if auto_delete:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=pending["message_id"])
                except Exception:
                    pass
            # Send a quiet notice so group admins know who timed out
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⏰ Verification timed out for user {user_id}. They remain restricted until manually verified.",
                )
            except Exception:
                pass
            self.pending.pop(key, None)
            self._remove_pending(chat_id, user_id)
