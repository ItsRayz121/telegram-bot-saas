"""
GroupContext — unified group adapter for the Telegizer feature engine.

Both the official Telegizer bot (backed by TelegramGroup) and custom user bots
(backed by Group) construct a GroupContext before calling into bot_features/.
This decouples all feature code from any specific ORM model.

Usage:
    # Custom bot (bot_manager.py)
    ctx = GroupContext.from_group(group_orm_obj)

    # Official bot (official_bot.py — wired in Phase 2)
    ctx = GroupContext.from_telegram_group(tg_orm_obj)
"""


class GroupContext:
    """Normalized, read-only view of a Telegram group."""

    __slots__ = (
        "id",
        "telegram_chat_id",
        "group_name",
        "settings",
        "bot_type",
        "bot_id",
        "telegram_member_count",
    )

    def __init__(
        self,
        id,
        telegram_chat_id,
        group_name,
        settings,
        bot_type,
        bot_id=None,
        telegram_member_count=0,
    ):
        self.id = id
        self.telegram_chat_id = str(telegram_chat_id) if telegram_chat_id is not None else None
        self.group_name = group_name or ""
        self.settings = settings if settings is not None else {}
        self.bot_type = bot_type          # "custom" | "official"
        self.bot_id = bot_id              # DB id of the custom Bot row, or None for official bot
        self.telegram_member_count = telegram_member_count or 0

    # ── Factory methods ───────────────────────────────────────────────────────

    @classmethod
    def from_group(cls, group):
        """Build from a custom bot's Group ORM object (bot_manager.py path)."""
        return cls(
            id=group.id,
            telegram_chat_id=group.telegram_group_id,
            group_name=group.group_name or "",
            settings=dict(group.settings or {}),
            bot_type="custom",
            bot_id=group.bot_id,
            telegram_member_count=group.telegram_member_count or 0,
        )

    @classmethod
    def from_telegram_group(cls, tg):
        """Build from the official bot's TelegramGroup ORM object (official_bot.py path)."""
        return cls(
            id=tg.id,
            telegram_chat_id=tg.telegram_group_id,
            group_name=tg.title or "",
            settings=dict(tg.settings or {}),
            bot_type="official",
            bot_id=None,
            telegram_member_count=getattr(tg, "telegram_member_count", 0) or 0,
        )

    # ── Convenience accessors (avoids scattered .get() chains) ────────────────

    def get_feature(self, key: str, default=None):
        """Return settings[key] or default."""
        return self.settings.get(key, default if default is not None else {})

    def __repr__(self):
        return (
            f"<GroupContext id={self.id} type={self.bot_type!r} "
            f"name={self.group_name!r}>"
        )
