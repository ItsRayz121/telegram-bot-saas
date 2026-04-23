import re
import unicodedata
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
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.\w{2,}\b")

LANGUAGE_RANGES = {
    "cyrillic": re.compile(r"[Ѐ-ӿ]"),
    "chinese": re.compile(r"[一-鿿㐀-䶿]"),
    "korean": re.compile(r"[가-힯ᄀ-ᇿ]"),
    "arabic": re.compile(r"[؀-ۿ]"),
    "hindi": re.compile(r"[ऀ-ॿ]"),
    "japanese": re.compile(r"[぀-ヿㇰ-ㇿ]"),
}


def normalize_homoglyphs(text):
    return unicodedata.normalize("NFKD", text)


class ModerationSystem:

    def __init__(self, app):
        self.app = app
        self._spam_tracker = {}

    async def warn_user(self, bot, chat_id, target_user_id, target_username,
                        moderator_id, moderator_username, reason, group):
        with self.app.app_context():
            from ..database import DatabaseManager  # noqa: used below for escalation too
            total_warnings = DatabaseManager.add_warning(
                group_id=group.id,
                target_user_id=target_user_id,
                target_username=target_username,
                moderator_id=moderator_id,
                moderator_username=moderator_username,
                reason=reason,
            )

            mod_settings = group.settings.get("moderation", {})
            max_warnings = mod_settings.get("max_warnings", 3)
            warning_action = mod_settings.get("warning_action", "ban")
            auto_delete_warn = mod_settings.get("auto_delete_warn_seconds", 0)

            warn_msg = await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ {target_username or target_user_id} has been warned.\n"
                    f"Reason: {reason}\n"
                    f"Warnings: {total_warnings}/{max_warnings}"
                ),
            )
            if auto_delete_warn and warn_msg:
                import asyncio as _a
                _a.ensure_future(self._delayed_delete(bot, chat_id, warn_msg.message_id, auto_delete_warn))

            # Check escalation steps first
            if mod_settings.get("escalation_enabled"):
                steps = sorted(
                    mod_settings.get("escalation_steps", []),
                    key=lambda s: s["at_warning"],
                    reverse=True,
                )
                for step in steps:
                    threshold = step["at_warning"]
                    time_window_hours = step.get("time_window_hours")
                    if time_window_hours:
                        count = DatabaseManager.count_warnings_in_window(
                            group.id, target_user_id, time_window_hours
                        )
                    else:
                        count = total_warnings
                    if count >= threshold:
                        action = step.get("action", "warn")
                        duration_min = step.get("duration_minutes", 60)
                        duration_hr = step.get("duration_hours", 24)
                        auto_delete = mod_settings.get("auto_delete_action_seconds", 0)
                        label = f"in {time_window_hours}h window" if time_window_hours else "total"
                        if action == "mute":
                            until = datetime.utcnow() + timedelta(minutes=duration_min)
                            try:
                                await bot.restrict_chat_member(
                                    chat_id=chat_id,
                                    user_id=target_user_id,
                                    permissions=ChatPermissions(can_send_messages=False),
                                    until_date=until,
                                )
                                msg = await bot.send_message(
                                    chat_id=chat_id,
                                    text=f"🔇 {target_username or target_user_id} muted for {duration_min}m (escalation: {count} warnings {label}).",
                                )
                                if auto_delete and msg:
                                    import asyncio as _a
                                    _a.ensure_future(self._delayed_delete(bot, chat_id, msg.message_id, auto_delete))
                            except Exception as e:
                                logger.error(f"Escalation mute error: {e}")
                        elif action == "tempban":
                            until = datetime.utcnow() + timedelta(hours=duration_hr)
                            try:
                                await bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id, until_date=until)
                                msg = await bot.send_message(
                                    chat_id=chat_id,
                                    text=f"⛔ {target_username or target_user_id} temp-banned for {duration_hr}h (escalation: {count} warnings {label}).",
                                )
                                if auto_delete and msg:
                                    import asyncio as _a
                                    _a.ensure_future(self._delayed_delete(bot, chat_id, msg.message_id, auto_delete))
                            except Exception as e:
                                logger.error(f"Escalation tempban error: {e}")
                        elif action == "ban":
                            await self.check_automated_actions(
                                bot, chat_id, target_user_id, target_username, group, "ban"
                            )
                        break
            elif total_warnings >= max_warnings:
                await self.check_automated_actions(
                    bot, chat_id, target_user_id, target_username, group, warning_action
                )

        return total_warnings

    async def _delayed_delete(self, bot, chat_id, message_id, delay_seconds):
        import asyncio
        await asyncio.sleep(delay_seconds)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.debug(f"Auto-delete msg {message_id} in chat {chat_id}: {e}")

    async def check_automated_actions(self, bot, chat_id, user_id, username, group, action):
        import asyncio as _asyncio
        auto_delete = group.settings.get("moderation", {}).get("auto_delete_action_seconds", 0)
        try:
            if action == "ban":
                days = group.settings.get("moderation", {}).get("ban_delete_days", 1)
                await bot.ban_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    revoke_messages=days > 0,
                )
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 {username or user_id} has been banned after reaching max warnings.",
                )
                if auto_delete and msg:
                    _asyncio.ensure_future(self._delayed_delete(bot, chat_id, msg.message_id, auto_delete))
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
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=f"👢 {username or user_id} has been kicked after reaching max warnings.",
                )
                if auto_delete and msg:
                    _asyncio.ensure_future(self._delayed_delete(bot, chat_id, msg.message_id, auto_delete))

            elif action == "mute":
                duration = group.settings.get("moderation", {}).get("mute_duration_minutes", 60)
                until_date = datetime.utcnow() + timedelta(minutes=duration)
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date,
                )
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=f"🔇 {username or user_id} has been muted for {duration} minutes after reaching max warnings.",
                )
                if auto_delete and msg:
                    _asyncio.ensure_future(self._delayed_delete(bot, chat_id, msg.message_id, auto_delete))

        except Exception as e:
            logger.error(f"Automated action error: {e}")

    async def check_automod(self, bot, message, group):
        settings = group.settings.get("automod", {})
        if not settings.get("enabled", True):
            return False

        text = message.text or message.caption or ""
        user_id = message.from_user.id if message.from_user else None
        chat_id = message.chat.id

        if not user_id:
            return False

        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ("creator", "administrator"):
                return False
        except Exception:
            pass

        # Normalize homoglyphs before text checks
        normalized_text = normalize_homoglyphs(text) if settings.get("homoglyphs", {}).get("enabled") else text

        # Text-based checks
        text_checks = [
            self.check_bad_words,
            self.check_spam,
            self.check_external_links,
            self.check_telegram_links,
            self.check_excessive_emojis,
            self.check_caps_lock,
            self.check_forwarded,
            self.check_email_detection,
            self.check_language_filter,
            self.check_spoiler_content,
            self.check_bot_mentions,
        ]

        for check in text_checks:
            try:
                if await check(bot, message, normalized_text, group, settings):
                    return True
            except Exception as e:
                logger.error(f"Automod check {check.__name__} error: {e}")

        # Media/content type checks (don't need text)
        media_checks = [
            self.check_contact_sharing,
            self.check_location_sharing,
            self.check_voice_notes,
            self.check_video_notes,
            self.check_file_attachments,
            self.check_photos,
            self.check_videos,
            self.check_gifs,
            self.check_stickers,
            self.check_games,
        ]

        for check in media_checks:
            try:
                if await check(bot, message, group, settings):
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

    async def check_email_detection(self, bot, message, text, group, settings):
        cfg = settings.get("email_detection", {})
        if not cfg.get("enabled", False):
            return False
        if EMAIL_PATTERN.search(text):
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Email address detected",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_language_filter(self, bot, message, text, group, settings):
        cfg = settings.get("language_filter", {})
        if not cfg.get("enabled", False) or not text:
            return False
        for lang in cfg.get("languages", []):
            pattern = LANGUAGE_RANGES.get(lang)
            if pattern and pattern.search(text):
                await self.execute_automod_action(
                    bot, message, group, cfg.get("action", "delete"),
                    reason=f"Blocked language detected: {lang}",
                    warn=cfg.get("warn_user", False),
                )
                return True
        return False

    async def check_spoiler_content(self, bot, message, text, group, settings):
        cfg = settings.get("spoiler_content", {})
        if not cfg.get("enabled", False):
            return False
        entities = message.entities or message.caption_entities or []
        for entity in entities:
            if entity.type.name == "SPOILER" or str(entity.type) == "MessageEntityType.SPOILER":
                await self.execute_automod_action(
                    bot, message, group, cfg.get("action", "delete"),
                    reason="Spoiler content",
                    warn=cfg.get("warn_user", False),
                )
                return True
        return False

    async def check_bot_mentions(self, bot, message, text, group, settings):
        cfg = settings.get("bot_mentions", {})
        if not cfg.get("enabled", False):
            return False
        entities = message.entities or []
        for entity in entities:
            if str(entity.type) in ("MessageEntityType.MENTION", "mention"):
                # Extract the @username from text
                start = entity.offset
                end = entity.offset + entity.length
                mention = text[start:end].lstrip("@")
                if mention.lower().endswith("bot"):
                    await self.execute_automod_action(
                        bot, message, group, cfg.get("action", "delete"),
                        reason="Bot mention detected",
                        warn=cfg.get("warn_user", False),
                    )
                    return True
        return False

    async def check_contact_sharing(self, bot, message, group, settings):
        cfg = settings.get("contact_sharing", {})
        if not cfg.get("enabled", False):
            return False
        if message.contact is not None:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Contact sharing blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_location_sharing(self, bot, message, group, settings):
        cfg = settings.get("location_sharing", {})
        if not cfg.get("enabled", False):
            return False
        if message.location is not None:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Location sharing blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_voice_notes(self, bot, message, group, settings):
        cfg = settings.get("voice_notes", {})
        if not cfg.get("enabled", False):
            return False
        if message.voice is not None:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Voice notes blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_video_notes(self, bot, message, group, settings):
        cfg = settings.get("video_notes", {})
        if not cfg.get("enabled", False):
            return False
        if message.video_note is not None:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Video notes blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_file_attachments(self, bot, message, group, settings):
        cfg = settings.get("file_attachments", {})
        if not cfg.get("enabled", False):
            return False
        if message.document is not None:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="File attachments blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_photos(self, bot, message, group, settings):
        cfg = settings.get("photos", {})
        if not cfg.get("enabled", False):
            return False
        if message.photo:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Photos blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_videos(self, bot, message, group, settings):
        cfg = settings.get("videos", {})
        if not cfg.get("enabled", False):
            return False
        if message.video is not None:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Videos blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_gifs(self, bot, message, group, settings):
        cfg = settings.get("gifs", {})
        if not cfg.get("enabled", False):
            return False
        if message.animation is not None:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="GIFs/animations blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_stickers(self, bot, message, group, settings):
        cfg = settings.get("stickers", {})
        if not cfg.get("enabled", False):
            return False
        if message.sticker is not None:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Stickers blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def check_games(self, bot, message, group, settings):
        cfg = settings.get("games", {})
        if not cfg.get("enabled", False):
            return False
        if message.game is not None:
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason="Games blocked",
                warn=cfg.get("warn_user", False),
            )
            return True
        return False

    async def execute_automod_action(self, bot, message, group, action,
                                     reason="Automod", warn=False, mute_duration=10):
        import asyncio as _asyncio
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        username = message.from_user.username if message.from_user else None

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
        except Exception:
            pass

        if not user_id:
            return

        mod_settings = group.settings.get("moderation", {})
        auto_delete_warn = mod_settings.get("auto_delete_warn_seconds", 0)
        auto_delete_action = mod_settings.get("auto_delete_action_seconds", 0)

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
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ {username or user_id}: {reason} (Warning {total})",
                    )
                    if auto_delete_warn and msg:
                        _asyncio.ensure_future(self._delayed_delete(bot, chat_id, msg.message_id, auto_delete_warn))
                except Exception as e:
                    logger.error(f"AutoMod warn message error: {e}")

            elif action == "mute":
                until_date = datetime.utcnow() + timedelta(minutes=mute_duration)
                try:
                    await bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until_date,
                    )
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=f"🔇 {username or user_id} muted for {mute_duration}m: {reason}",
                    )
                    if auto_delete_action and msg:
                        _asyncio.ensure_future(self._delayed_delete(bot, chat_id, msg.message_id, auto_delete_action))
                except Exception as e:
                    logger.error(f"Mute error: {e}")

            elif action == "ban":
                try:
                    await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=f"🚫 {username or user_id} banned: {reason}",
                    )
                    if auto_delete_action and msg:
                        _asyncio.ensure_future(self._delayed_delete(bot, chat_id, msg.message_id, auto_delete_action))
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
