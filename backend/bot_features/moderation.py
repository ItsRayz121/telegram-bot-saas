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

# Hidden URL obfuscation normalization rules (applied sequentially)
HIDDEN_URL_RULES = [
    (re.compile(r'hxxps?://', re.I),                   'https://'),
    (re.compile(r'(\w)\(\.\)(\w)'),                    r'\1.\2'),       # t(.)me → t.me
    (re.compile(r'\b(\w+)_me/', re.I),                 r'\1.me/'),      # t_me/ → t.me/
    (re.compile(r'\bbit\s+ly\b', re.I),                'bit.ly'),
    (re.compile(r'\b(\w+)\s+dot\s+(\w+)\b', re.I),    r'\1.\2'),       # site dot com
    (re.compile(r'\b(\w+)_com\b', re.I),               r'\1.com'),      # example_com
    (re.compile(r'\bwww\s+(\w+)\s+(\w+)\b', re.I),    r'www.\1.\2'),   # www example com
    (re.compile(r'\b(\w+)\s+\.\s+(\w{2,6})\b'),       r'\1.\2'),       # example . com
]

# Promotional / ad / referral / fake-earnings patterns
PROMO_PATTERNS = re.compile(
    r'\bdm\s+me\b'
    r'|\bprivate\s+message\s+me\b'
    r'|\bchat\s+me\b'
    r'|\bjoin\s+(my|our)\s+(channel|group|community)\b'
    r'|\bsubscribe\s+to\b'
    r'|\bcheck\s+out\s+my\b'
    r'|\bfollow\s+me\b'
    r'|\bref(erral)?\s+code\b'
    r'|\buse\s+my\s+(code|link|referral)\b'
    r'|\bsign\s+up\s+(using|with)\b'
    r'|\binvite\s+code\b'
    r'|\bearn\s+\$[\d,]+\s+(daily|per\s+day|a\s+day)\b'
    r'|\b(guaranteed|100\s*%)\s+(profit|returns?|roi)\b'
    r'|\bpassive\s+income\b'
    r'|\bdouble\s+your\s+(money|investment)\b'
    r'|\b(presale|pre[\s\-]sale)\b'
    r'|\b\d{2,}x\s+(potential|gem|gains?)\b'
    r'|\b(moonshot|100x|next\s+100x)\b'
    r'|\binvest\s+(in|with|today|now)\b'
    r'|\bget\s+paid\s+(daily|weekly)\b'
    r'|\btrading\s+(signals?|tips?)\s+free\b',
    re.IGNORECASE,
)

LANGUAGE_RANGES = {
    "cyrillic": re.compile(r"[Ѐ-ӿ]"),
    "chinese": re.compile(r"[一-鿿㐀-䶿]"),
    "korean": re.compile(r"[가-힯ᄀ-ᇿ]"),
    "arabic": re.compile(r"[؀-ۿ]"),
    "hindi": re.compile(r"[ऀ-ॿ]"),
    "japanese": re.compile(r"[぀-ヿㇰ-ㇿ]"),
}


def _extract_message_text(message, max_len=500):
    """Return a best-effort text preview of a Telegram message.
    Call BEFORE delete_message so the message object is guaranteed fresh.
    """
    # 1. Plain text or caption
    text = (message.text or message.caption or "").strip()

    # 2. Fallback: URLs embedded in TextLink entities (hyperlinked text like "Click here")
    if not text:
        entities = list(message.entities or []) + list(message.caption_entities or [])
        urls = [getattr(e, "url", None) for e in entities if getattr(e, "url", None)]
        if urls:
            text = "  ".join(urls[:3])

    # 3. Fallback: descriptive media-type label for non-text messages
    if not text:
        if getattr(message, "photo", None):
            text = "📷 Photo"
        elif getattr(message, "video", None):
            text = "🎥 Video"
        elif getattr(message, "voice", None):
            text = "🎤 Voice message"
        elif getattr(message, "audio", None):
            text = "🎵 Audio"
        elif getattr(message, "document", None):
            text = "📄 Document"
        elif getattr(message, "sticker", None):
            emoji = getattr(message.sticker, "emoji", "") or ""
            text = f"🎴 Sticker {emoji}".strip()
        elif getattr(message, "animation", None):
            text = "🎞️ GIF/Animation"
        elif getattr(message, "video_note", None):
            text = "📹 Video note"
        elif getattr(message, "contact", None):
            text = "📞 Contact"
        elif getattr(message, "location", None):
            text = "📍 Location"
        elif getattr(message, "poll", None):
            text = "📊 Poll"
        else:
            return None

    if len(text) >= max_len:
        text = text[: max_len - 1] + "…"
    return text or None


def normalize_homoglyphs(text):
    return unicodedata.normalize("NFKD", text)


def normalize_hidden_urls(text: str) -> str:
    for pattern, replacement in HIDDEN_URL_RULES:
        text = pattern.sub(replacement, text)
    return text


def format_violation_message(username: str, reason: str, group_topic: str = "") -> str:
    topic_clause = f" Please keep discussion relevant to {group_topic}." if group_topic else ""
    return f"@{username}, your message was removed — {reason}.{topic_clause}"


class ModerationSystem:

    def __init__(self, app):
        self.app = app
        self._spam_tracker = {}
        self._ai_cooldown: dict = {}  # (chat_id, user_id) → last AI call datetime

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
            # #10 — honor the auto-delete toggle; default to 30s when unset (old groups).
            auto_delete_warn = (
                0 if mod_settings.get("auto_delete_warnings", True) is False
                else int(mod_settings.get("auto_delete_warn_seconds", 30) or 0)
            )

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

    async def _apply_escalation(self, bot, chat_id, user_id, username, first_name, warn_count, mod_settings, auto_delete_seconds):
        import asyncio as _aio
        display = ('@' + username) if username else (first_name or str(user_id))
        steps = sorted(mod_settings.get("escalation_steps", []),
                       key=lambda s: s.get("at_warning", 99), reverse=True)
        for step in steps:
            if warn_count >= step.get("at_warning", 99):
                action = step.get("action", "mute")
                notif = None
                try:
                    if action == "mute":
                        mins = step.get("duration_minutes", 60)
                        until = datetime.utcnow() + timedelta(minutes=mins)
                        await bot.restrict_chat_member(
                            chat_id=chat_id, user_id=user_id,
                            permissions=ChatPermissions(can_send_messages=False),
                            until_date=until,
                        )
                        hrs = mins // 60
                        dur_str = f"{hrs}h" if hrs >= 1 else f"{mins}m"
                        notif = await bot.send_message(
                            chat_id=chat_id,
                            text=f"🔇 {display} muted {dur_str} — reached Warning #{warn_count}.",
                        )
                    elif action == "tempban":
                        hours = step.get("duration_hours", 24)
                        until = datetime.utcnow() + timedelta(hours=hours)
                        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=until)
                        days = hours // 24
                        dur_str = f"{days}d" if days >= 1 else f"{hours}h"
                        notif = await bot.send_message(
                            chat_id=chat_id,
                            text=f"🚫 {display} banned for {dur_str} — reached Warning #{warn_count}.",
                        )
                    elif action in ("ban", "kick"):
                        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                        if action == "kick":
                            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
                        icon = "🚫" if action == "ban" else "👢"
                        verb = "banned" if action == "ban" else "kicked"
                        notif = await bot.send_message(
                            chat_id=chat_id,
                            text=f"{icon} {display} {verb} — reached Warning #{warn_count}.",
                        )
                    if notif and auto_delete_seconds:
                        _aio.ensure_future(self._delayed_delete(bot, chat_id, notif.message_id, auto_delete_seconds))
                except Exception as e:
                    logger.error(f"Escalation action '{action}' failed for {user_id}: {e}")
                return  # only first matching step fires

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
        except Exception as e:
            # Can't verify admin status — fail open so we never accidentally
            # block an admin's message due to a permission or network error.
            logger.debug(f"Admin check failed for user {user_id} in {chat_id}: {e}")
            return False

        # Trusted user bypass (smart_mod whitelist)
        smart_cfg = settings.get("smart_mod", {})
        if user_id in smart_cfg.get("trusted_users", []):
            return False

        # Phase 3 raid mode — duplicate-flood detection (many distinct accounts
        # posting the same text). Behaviour-based, never join-rate. Detection only;
        # the lockdown response runs at join time in handle_new_member.
        try:
            from . import raid_guard
            if raid_guard.note_message(chat_id, user_id, text, group.settings):
                await self._announce_raid(bot, chat_id, group)
        except Exception as e:
            logger.debug(f"raid_guard message note failed: {e}")

        # Normalize homoglyphs before text checks
        normalized_text = normalize_homoglyphs(text) if settings.get("homoglyphs", {}).get("enabled") else text

        # Text-based checks — NSFW/adult + inline-button scanning runs FIRST so
        # obvious adult spam is killed before any softer rule or the AI layer.
        text_checks = [
            self.check_nsfw_and_buttons,
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

        # Layer 2: hidden URL normalization + promotional pattern detection
        for check in [self.check_hidden_urls, self.check_promotional_content]:
            try:
                if await check(bot, message, normalized_text, group, settings):
                    return True
            except Exception as e:
                logger.error(f"Smart mod check {check.__name__} error: {e}")

        # Layer 3: AI relevance check (only when L1+L2 passed)
        try:
            if await self.check_ai_relevance(bot, message, normalized_text, group, settings):
                return True
        except Exception as e:
            logger.error(f"AI relevance check error: {e}")

        return False

    async def check_nsfw_and_buttons(self, bot, message, text, group, settings):
        """NSFW/adult content + inline-button spam, via the shared content_filter
        module so both bot lineages behave identically (bot-lineage rule).

        Two surfaces with very different false-positive risk:
          • plain text/caption — a real person might quote/curse, so this is
            conservative (delete + warn by default);
          • inline button text/URLs — ordinary Telegram clients CANNOT attach
            inline keyboards, so NSFW or scam links riding on them are almost
            never legitimate → harsher action (ban by default).
        CSAM is always treated as the hardest action regardless of where it
        appears.
        """
        from . import content_filter as cf

        nsfw_cfg = settings.get("nsfw_filter", {})
        btn_cfg = settings.get("inline_button_scan", {})
        nsfw_on = nsfw_cfg.get("enabled", False)
        btn_on = btn_cfg.get("enabled", False)
        if not nsfw_on and not btn_on:
            return False

        btn_texts, btn_urls = cf.extract_buttons(message)
        entity_urls = cf.extract_entity_urls(message)

        # ── NSFW / CSAM ──────────────────────────────────────────────────────
        if nsfw_on:
            extra = nsfw_cfg.get("extra_words", [])
            term, is_csam = cf.nsfw_match(text, extra)
            on_button = False
            if not term:
                for bt in btn_texts:
                    t, c = cf.nsfw_match(bt, extra)
                    if t:
                        term, is_csam, on_button = t, c, True
                        break
            if term:
                if is_csam:
                    action = nsfw_cfg.get("csam_action", "ban")
                    reason = "Prohibited content (CSAM)"
                elif on_button:
                    action = nsfw_cfg.get("button_action", "ban")
                    reason = f"Adult/NSFW content on inline button: {term}"
                else:
                    action = nsfw_cfg.get("action", "delete")
                    reason = f"Adult/NSFW content: {term}"
                await self.execute_automod_action(
                    bot, message, group, action,
                    reason=reason, warn=nsfw_cfg.get("warn_user", True),
                )
                self._log_content_filter(group, message, reason)
                return True

        # ── Inline-button spam ───────────────────────────────────────────────
        if btn_on and cf.has_inline_buttons(message):
            # A non-admin message carrying an inline keyboard came via an inline
            # bot/userbot — a strong spam signal on its own. A shortener/scam-TLD
            # link behind it escalates to the harsher action.
            suspicious = any(cf.is_suspicious_link(u) for u in (btn_urls + entity_urls))
            action = (btn_cfg.get("suspicious_action", "ban") if suspicious
                      else btn_cfg.get("action", "delete"))
            reason = ("Inline buttons with suspicious link" if suspicious
                      else "Inline buttons are not allowed from members")
            await self.execute_automod_action(
                bot, message, group, action,
                reason=reason, warn=btn_cfg.get("warn_user", False),
            )
            self._log_content_filter(group, message, reason)
            return True

        return False

    def _log_content_filter(self, group, message, reason):
        """Record a Content Filter feature event (custom lineage, best-effort).

        The enforcement is also logged via execute_automod_action (as nsfw/automod);
        this gives the Content Filter module its own queryable count so it isn't
        invisible behind the generic automod bucket.
        """
        try:
            from ..feature_usage import log_feature_usage
            uid = message.from_user.id if getattr(message, "from_user", None) else None
            log_feature_usage(
                "custom", "content_filter", group_ref=str(group.id),
                user_ref=(str(uid) if uid else None), action=reason, commit=True,
            )
        except Exception:
            pass

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

        # Never block platform-generated invite links for this group
        if self._is_platform_invite_link(group.id, text):
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

    def _is_platform_invite_link(self, group_id, text: str) -> bool:
        """Return True if text contains a platform-generated invite link stored for this group."""
        try:
            with self.app.app_context():
                from ..models import InviteLink
                links = InviteLink.query.filter_by(group_id=group_id, is_active=True).all()
                for link in links:
                    if link.telegram_invite_link and link.telegram_invite_link in text:
                        return True
        except Exception as e:
            logger.debug(f"Invite link lookup failed: {e}")
        return False

    async def check_telegram_links(self, bot, message, text, group, settings):
        cfg = settings.get("telegram_links", {})
        if not cfg.get("enabled", False):
            return False

        if TELEGRAM_LINK_PATTERN.search(text):
            # Never block platform-generated invite links for this group
            if self._is_platform_invite_link(group.id, text):
                return False
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

        # PTB 21.x replaced forward_date/forward_from/forward_from_chat with
        # forward_origin; use getattr so this works across versions without
        # raising AttributeError ("Message object has no attribute forward_date").
        if (getattr(message, "forward_origin", None)
                or getattr(message, "forward_date", None)
                or getattr(message, "forward_from", None)
                or getattr(message, "forward_from_chat", None)):
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                    warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                    warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                        warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
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
                warn_delete_seconds=cfg.get("warn_delete_seconds"),
            )
            return True
        return False

    async def execute_automod_action(self, bot, message, group, action,
                                     reason="Automod", warn=False, mute_duration=10,
                                     warn_delete_seconds=None):
        """
        warn_delete_seconds: per-rule override for how long to keep the warning
        message before auto-deleting it. None means fall back to the global
        moderation.auto_delete_warn_seconds setting. 0 means never delete.
        """
        import asyncio as _asyncio
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        username = message.from_user.username if message.from_user else None
        first_name = message.from_user.first_name if message.from_user else None

        # Capture message content BEFORE deletion — while the object is guaranteed fresh
        msg_text = _extract_message_text(message)

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
        except Exception:
            pass

        if not user_id:
            return

        mod_settings = group.settings.get("moderation", {})
        # #10 — honor the auto-delete toggle; default to 30s when unset (old groups).
        if mod_settings.get("auto_delete_warnings", True) is False:
            auto_delete_warn = 0
        else:
            global_delete_warn = int(mod_settings.get("auto_delete_warn_seconds", 30) or 0)
            # Per-rule setting takes precedence when explicitly set; None means use global.
            auto_delete_warn = warn_delete_seconds if warn_delete_seconds is not None else global_delete_warn
        auto_delete_action = int(mod_settings.get("auto_delete_action_seconds", 30) or 0)

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
                    message_text=msg_text,
                )
                try:
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ {('@' + username) if username else (first_name or str(user_id))}: {reason} (Warning {total})",
                    )
                    if auto_delete_warn and msg:
                        _asyncio.ensure_future(self._delayed_delete(bot, chat_id, msg.message_id, auto_delete_warn))
                except Exception as e:
                    logger.error(f"AutoMod warn message error: {e}")

                # Escalation: check if this warning count triggers a step
                mod_s = group.settings.get("moderation", {})
                if mod_s.get("escalation_enabled"):
                    import asyncio as _aio
                    _aio.ensure_future(self._apply_escalation(
                        bot, chat_id, user_id, username, first_name, total, mod_s, auto_delete_action
                    ))

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
                        text=f"🔇 {('@' + username) if username else (first_name or str(user_id))} muted for {mute_duration}m: {reason}",
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
                        text=f"🚫 {('@' + username) if username else (first_name or str(user_id))} banned: {reason}",
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
                extra_data={"message_text": msg_text} if msg_text else None,
            )

            # Feature-usage spine (best-effort, never raises). Custom-bot lineage.
            # feature = what was DETECTED (so Spam/Link protection get their own
            # counts); the enforcement action (warn/mute/ban) is kept in meta.
            try:
                from ..feature_usage import log_feature_usage, automod_feature
                _act = "warn" if (warn or action == "warn") else action
                log_feature_usage(
                    "custom", automod_feature(reason), group_ref=str(group.id), user_ref=str(user_id),
                    action=reason, meta={"automod_action": _act}, commit=True,
                )
                # Enforcement actions also get their own feature row (rare events)
                # so Muting/Bans/Kicks have clean, queryable counts.
                if _act in ("warn", "mute", "ban", "kick"):
                    log_feature_usage(
                        "custom", _act, group_ref=str(group.id), user_ref=str(user_id),
                        action=reason, commit=True,
                    )
            except Exception:
                pass

        # Phase 3 raid mode — a burst of DISTINCT violators is a coordinated-raid
        # signature. Feed the detector; on activation lock down + alert once.
        try:
            from . import raid_guard
            if raid_guard.note_violation(chat_id, user_id, group.settings):
                await self._announce_raid(bot, chat_id, group)
        except Exception as e:
            logger.debug(f"raid_guard violation note failed: {e}")

    async def _announce_raid(self, bot, chat_id, group):
        """Post the one-time in-group raid-mode alert (best-effort)."""
        from . import raid_guard
        # Raid Guard feature event — logged before the notify gate so silent
        # (notify=off) activations still count. Custom lineage, best-effort.
        try:
            from ..feature_usage import log_feature_usage
            log_feature_usage("custom", "raid", group_ref=str(group.id),
                              action="raid_mode_activated", commit=True)
        except Exception:
            pass
        if not raid_guard.get_config(group.settings).get("notify", True):
            return
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=raid_guard.activation_notice(raid_guard.seconds_remaining(chat_id)),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.debug(f"raid announce failed: {e}")
        try:
            with self.app.app_context():
                from ..database import DatabaseManager
                DatabaseManager.log_action(
                    group_id=group.id, action_type="raid_mode_activated",
                    target_user_id="", target_username=None,
                    moderator_id="raid_guard", moderator_username="RaidGuard",
                    reason="Coordinated spam detected — new joins restricted",
                )
        except Exception:
            pass

    # ── Smart Moderation: Layer 2 ─────────────────────────────────────────────

    async def check_hidden_urls(self, bot, message, text, group, settings):
        cfg = settings.get("smart_mod", {})
        if not cfg.get("enabled") or not cfg.get("hidden_url_detection", True):
            return False

        normalized = normalize_hidden_urls(text)
        if normalized == text:
            return False  # nothing was obfuscated

        username = ('@' + message.from_user.username) if (message.from_user and message.from_user.username) else ((message.from_user.first_name if message.from_user else None) or "user")
        topic = group.group_name or ""

        # Re-check external links on normalized text
        ext_cfg = settings.get("external_links", {})
        if ext_cfg.get("enabled") and URL_PATTERN.search(normalized) and not self._is_platform_invite_link(group.id, normalized):
            whitelist = ext_cfg.get("whitelist", [])
            for url in URL_PATTERN.findall(normalized):
                if not any(w in url for w in whitelist):
                    msg = format_violation_message(username, "hidden or obfuscated external links are not allowed", topic)
                    await self.execute_automod_action(
                        bot, message, group, cfg.get("action", "delete"),
                        reason=msg, warn=cfg.get("warn_user", True),
                    )
                    return True

        # Re-check Telegram links on normalized text
        tg_cfg = settings.get("telegram_links", {})
        if tg_cfg.get("enabled") and TELEGRAM_LINK_PATTERN.search(normalized):
            # Never block platform-generated invite links for this group
            if not self._is_platform_invite_link(group.id, normalized):
                msg = format_violation_message(username, "hidden Telegram links or invites are not allowed", topic)
                await self.execute_automod_action(
                    bot, message, group, cfg.get("action", "delete"),
                    reason=msg, warn=cfg.get("warn_user", True),
                )
                return True

        return False

    async def check_promotional_content(self, bot, message, text, group, settings):
        cfg = settings.get("smart_mod", {})
        if not cfg.get("enabled") or not cfg.get("promotional_detection", True):
            return False

        # Exempt referral codes if explicitly allowed
        if cfg.get("allow_referral_codes") and re.search(
            r'\bref(erral)?\s+code\b|\buse\s+my\s+code\b', text, re.I
        ):
            return False

        if PROMO_PATTERNS.search(text):
            username = ('@' + message.from_user.username) if (message.from_user and message.from_user.username) else ((message.from_user.first_name if message.from_user else None) or "user")
            topic = group.group_name or ""
            msg = format_violation_message(
                username,
                "promotional content, advertisements, and referral solicitation are not allowed in this group",
                topic,
            )
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason=msg, warn=cfg.get("warn_user", True),
            )
            return True
        return False

    # ── Smart Moderation: Layer 3 (AI) ────────────────────────────────────────

    @staticmethod
    def _call_ai_moderation(text, group_topic, group_name, key_info):
        import requests as _r, json as _json
        prompt = (
            f"You are a content moderator for a Telegram group.\n"
            f"Group name: {group_name}\n"
            f"Group topic: {group_topic}\n\n"
            f"Message: \"{text[:500]}\"\n\n"
            "Classify this message. Reply with JSON only, no markdown:\n"
            "{\"verdict\": \"ok\" or \"promotional\" or \"irrelevant\", "
            "\"reason\": \"one professional sentence explaining the removal\"}"
        )
        provider = key_info.get("provider", "openrouter")
        api_key = key_info.get("api_key", "")
        model = key_info.get("model", "gpt-4o-mini")

        try:
            if provider == "gemini":
                resp = _r.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=8,
                )
                resp.raise_for_status()
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            elif provider == "anthropic":
                resp = _r.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    json={"model": model, "max_tokens": 80,
                          "messages": [{"role": "user", "content": prompt}]},
                    timeout=8,
                )
                resp.raise_for_status()
                raw = resp.json()["content"][0]["text"].strip()
            else:
                base = key_info.get("base_url", "https://api.openai.com/v1")
                resp = _r.post(
                    f"{base.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "max_tokens": 80,
                          "messages": [{"role": "user", "content": prompt}]},
                    timeout=8,
                )
                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"].strip()

            # Strip markdown code fences if model wrapped the JSON
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = _json.loads(raw)
            return data.get("verdict", "ok"), data.get("reason", "off-topic content")
        except Exception as e:
            logger.debug(f"AI moderation call failed: {e}")
            return "ok", ""

    @staticmethod
    def _resolve_group_owner(group, Bot, CustomBot, TelegramGroup, User):
        """Resolve the human owner of a group across BOTH bot models.

        Legacy bots store groups in the `groups` table (Group.bot_id → Bot).
        Custom (bring-your-own) bots store them in `telegram_groups`
        (TelegramGroup.linked_bot_id → CustomBot) and have NO legacy Bot row.
        The original lookup only checked `Bot`, so AI moderation silently
        disabled itself for every custom-bot group. We now try the legacy path
        first, then fall back to the TelegramGroup → CustomBot path.
        """
        # Legacy path: Group.bot_id → Bot → owner.
        legacy_bot_id = getattr(group, "bot_id", None)
        if legacy_bot_id is not None:
            bot_obj = Bot.query.get(legacy_bot_id)
            if bot_obj:
                owner = User.query.get(bot_obj.user_id)
                if owner:
                    return owner

        # Custom-bot path: resolve via the TelegramGroup record.
        tgid = getattr(group, "telegram_group_id", None)
        if tgid is not None:
            tg = TelegramGroup.query.filter_by(telegram_group_id=str(tgid)).first()
            if tg:
                if tg.owner_user_id:
                    owner = User.query.get(tg.owner_user_id)
                    if owner:
                        return owner
                if tg.linked_bot_id:
                    cb = CustomBot.query.get(tg.linked_bot_id)
                    if cb and cb.owner_user_id:
                        return User.query.get(cb.owner_user_id)
        return None

    async def check_ai_relevance(self, bot, message, text, group, settings):
        cfg = settings.get("smart_mod", {})
        if not cfg.get("enabled") or not cfg.get("ai_enabled"):
            return False
        group_topic = cfg.get("group_topic", "").strip()
        if not group_topic or not text:
            return False
        if len(text.split()) < 10:
            return False  # too short for AI to make a fair judgement

        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return False
        chat_id = message.chat.id
        key = (chat_id, user_id)
        rate_secs = cfg.get("ai_rate_limit_seconds", 30)
        now = datetime.utcnow()
        last = self._ai_cooldown.get(key)
        if last and (now - last).total_seconds() < rate_secs:
            return False
        self._ai_cooldown[key] = now

        with self.app.app_context():
            from ..models import Bot, CustomBot, TelegramGroup, User
            from ..assistant.ai_key_resolver import get_workspace_ai_key

            owner = self._resolve_group_owner(group, Bot, CustomBot, TelegramGroup, User)
            if not owner:
                return False
            key_info = get_workspace_ai_key(owner)
            if not key_info.get("api_key"):
                return False

        import asyncio as _asyncio
        loop = _asyncio.get_running_loop()
        verdict, reason = await loop.run_in_executor(
            None, self._call_ai_moderation,
            text, group_topic, message.chat.title or "", key_info,
        )

        # AI usage ledger (best-effort) — one row per moderation completion.
        try:
            from ..ai_usage import record_from_key_info
            from ..ai_activity import derive_scope_ref as _dsr
            with self.app.app_context():
                _scope, _ref = _dsr(group)
                # bot_ref enables direct per-bot attribution in the admin detail.
                # TelegramGroup.linked_bot_id is the CustomBot id; official → 'official'.
                _bot_ref = (str(getattr(group, "linked_bot_id", None))
                            if getattr(group, "linked_bot_id", None)
                            else ("official" if _scope == "official" else None))
                record_from_key_info(
                    _scope or "official", "ai_mod", key_info,
                    user_ref=user_id, group_ref=_ref, bot_ref=_bot_ref,
                    input_text=f"{group_topic}\n{text}", output_text=f"{verdict} {reason or ''}",
                )
        except Exception:
            pass

        if verdict in ("promotional", "irrelevant"):
            username = message.from_user.username or str(user_id)
            fallback = "off-topic content" if verdict == "irrelevant" else "promotional content"
            msg = format_violation_message(username, reason or fallback, group_topic)
            await self.execute_automod_action(
                bot, message, group, cfg.get("action", "delete"),
                reason=msg, warn=cfg.get("warn_user", True),
            )
            # AI Activity (reporting only — best-effort, never raises)
            try:
                from ..ai_activity import log_ai_activity, derive_scope_ref
                action_label = {
                    "promotional": "Promotional content removed",
                    "irrelevant": "Off-topic content removed",
                }.get(verdict, "Content removed")
                with self.app.app_context():
                    scope, ref = derive_scope_ref(group)
                    log_ai_activity(
                        scope, ref, "moderation", action_label,
                        detail=reason or fallback,
                        target=("@" + username) if username and not username.isdigit() else str(user_id),
                        source="ai_automod",
                    )
            except Exception:
                pass
            return True
        return False
