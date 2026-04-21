import re
import logging
from datetime import datetime, timedelta
from telegram import ChatPermissions

logger = logging.getLogger(__name__)

TELEGRAM_LINK_PATTERN = re.compile(
    r"(t\.me/|telegram\.me/|@[a-zA-Z0-9_]{5,})", re.IGNORECASE
)
URL_PATTERN = re.compile(
    r"https?://[^\s]+|www\.[^\s]+", re.IGNORECASE
)
EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0\U000024C2-\U0001F251]+",
    flags=re.UNICODE,
)


class ModerationSystem:

    def __init__(self, app):
        self.app = app
        self._spam_tracker = {}

    async def warn_user(self, bot, chat_id, target_user_id, target_username,
                        moderator_id, moderator_username, reason, group):
        with self.app.app_context():
            from ..database import DatabaseManager
            total_warnings = DatabaseManager.add_warning(
                group_id=group.id,
                target_user_id=target_user_id,
                target_username=target_username,
                moderator_id=moderator_id,
                moderator_username=moderator_username,
                reason=reason,
            )

            max_warnings = group.settings.get("moderation", {}).get("max_warnings", 3)
            warning_action = group.settings.get("moderation", {}).get("warning_action", "ban")

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ {target_username or target_user_id} has been warned.\n"
                    f"Reason: {reason}\n"
                    f"Warnings: {total_warnings}/{max_warnings}"
                ),
            )

            if total_warnings >= max_warnings:
                await self.check_automated_actions(
                    bot, chat_id, target_user_id, target_username, group, warning_action
                )

        return total_warnings

    async def check_automated_actions(self, bot, chat_id, user_id, username, group, action):
        try:
            if action == "ban":
                days = group.settings.get("moderation", {}).get("ban_delete_days", 1)
                await bot.ban_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    revoke_messages=days > 0,
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 {username or user_id} has been banned after reaching max warnings.",
                )
                with self.app.app_context():
                    from ..database import DatabaseManager
                    DatabaseManager.log_action(
                        group_id=group.id,
                        action_type="auto_ban",
                        target_user_id=str(user_id),
                        target_username=username,
                        reason="Reached maximum warnings",
                    )

            elif action == "kick":
                await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"👢 {username or user_id} has been kicked after reaching max warnings.",
                )

            elif action == "mute":
                duration = group.settings.get("moderation", {}).get("mute_duration_minutes", 60)
                until_date = datetime.utcnow() + timedelta(minutes=duration)
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date,
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🔇 {username or user_id} has been muted for {duration} minutes after reaching max warnings.",
                )

        except Exception as e:
            logger.error(f"Automated action error: {e}")

    async def check_automod(self, bot, message, group):
        settings = group.settings.get("automod", {})
        if not settings.get("enabled", True):
            return False

        text = message.text or message.caption or ""
        user_id = message.from_user.id if message.from_user else None
        chat_id = message.chat.id

        if not user_id or not text:
            return False

        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ("creator", "administrator"):
                return False
        except Exception:
            pass

        checks = [
            self.check_bad_words,
            self.check_spam,
            self.check_external_links,
            self.check_telegram_links,
            self.check_excessive_emojis,
            self.check_caps_lock,
            self.check_forwarded,
        ]

        for check in checks:
            try:
                if await check(bot, message, text, group, settings):
                    return True
            except Exception as e:
                logger.error(f"Automod check {check.__name__} error: {e}")

        return False

    async def check_bad_words(self, bot, message, text, group, settings):
        cfg = settings.get("bad_words", {})
        if not cfg.get("enabled", False):
            return False

        words = cfg.get("words", [])
        text_lower = text.lower()

        for word in words:
            if word.lower() in text_lower:
                action = cfg.get("action", "delete")
                await self.execute_automod_action(
                    bot, message, group, action,
                    reason=f"Bad word detected: {word}",
                    warn=cfg.get("warn_user", True),
                )
                return True
        return False

    async def check_spam(self, bot, message, text, group, settings):
        cfg = settings.get("spam", {})
        if not cfg.get("enabled", True):
            return False

        user_id = message.from_user.id
        chat_id = message.chat.id
        key = f"{chat_id}:{user_id}"
        now = datetime.utcnow()
        window = cfg.get("time_window_seconds", 10)
        max_messages = cfg.get("max_messages", 5)

        if key not in self._spam_tracker:
            self._spam_tracker[key] = []

        self._spam_tracker[key] = [
            t for t in self._spam_tracker[key]
            if (now - t).total_seconds() < window
        ]
        self._spam_tracker[key].append(now)

        if len(self._spam_tracker[key]) > max_messages:
            action = cfg.get("action", "mute")
            duration = cfg.get("mute_duration_minutes", 10)
            await self.execute_automod_action(
                bot, message, group, action,
                reason="Spamming",
                mute_duration=duration,
            )
            self._spam_tracker[key] = []
            return True

        return False

    async def check_external_links(self, bot, message, text, group, settings):
        cfg = settings.get("external_links", {})
        if not cfg.get("enabled", False):
            return False

        if not URL_PATTERN.search(text):
            return False

        whitelist = cfg.get("whitelist", [])
        urls = URL_PATTERN.findall(text)
        for url in urls:
            if not any(allowed in url for allowed in whitelist):
                await self.execute_automod_action(
                    bot, message, group, cfg.get("action", "delete"),
                    reason="External link not in whitelist",
                )
                return True
        return False

    async def check_telegram_links(self, bot, message, text, group, settings):
        cfg = settings.get("telegram_links", {})
        if not cfg.get("enabled", False):
            return False

        if TELEGRAM_LINK_PATTERN.search(text):
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Telegram link/invite",
                warn=cfg.get("warn_user", True),
            )
            return True
        return False

    async def check_excessive_emojis(self, bot, message, text, group, settings):
        cfg = settings.get("excessive_emojis", {})
        if not cfg.get("enabled", False):
            return False

        emoji_count = len(EMOJI_PATTERN.findall(text))
        if emoji_count > cfg.get("max_emojis", 10):
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason=f"Too many emojis ({emoji_count})",
            )
            return True
        return False

    async def check_caps_lock(self, bot, message, text, group, settings):
        cfg = settings.get("caps_lock", {})
        if not cfg.get("enabled", False):
            return False

        min_len = cfg.get("min_length", 10)
        threshold = cfg.get("threshold_percent", 70)

        letters = [c for c in text if c.isalpha()]
        if len(letters) < min_len:
            return False

        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters) * 100
        if caps_ratio >= threshold:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Excessive caps lock",
            )
            return True
        return False

    async def check_forwarded(self, bot, message, text, group, settings):
        cfg = settings.get("forwarded_messages", {})
        if not cfg.get("enabled", False):
            return False

        if message.forward_date or message.forward_from or message.forward_from_chat:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Forwarded message",
            )
            return True
        return False

    async def execute_automod_action(self, bot, message, group, action,
                                     reason="Automod", warn=False, mute_duration=10):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        username = message.from_user.username if message.from_user else None

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
        except Exception:
            pass

        if not user_id:
            return

        with self.app.app_context():
            from ..database import DatabaseManager

            if warn or action == "warn":
                total = DatabaseManager.add_warning(
                    group_id=group.id,
                    target_user_id=user_id,
                    target_username=username,
                    moderator_id="automod",
                    moderator_username="AutoMod",
                    reason=reason,
                )
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ {username or user_id}: {reason} (Warning {total})",
                    )
                except Exception:
                    pass

            elif action == "mute":
                until_date = datetime.utcnow() + timedelta(minutes=mute_duration)
                try:
                    await bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until_date,
                    )
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"🔇 {username or user_id} muted for {mute_duration}m: {reason}",
                    )
                except Exception as e:
                    logger.error(f"Mute error: {e}")

            elif action == "ban":
                try:
                    await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"🚫 {username or user_id} banned: {reason}",
                    )
                except Exception as e:
                    logger.error(f"Ban error: {e}")

            DatabaseManager.log_action(
                group_id=group.id,
                action_type=f"automod_{action}",
                target_user_id=str(user_id),
                target_username=username,
                moderator_id="automod",
                moderator_username="AutoMod",
                reason=reason,
            )
