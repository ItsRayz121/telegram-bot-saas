"""
Centralized default settings for all new TelegramGroup records.

Applied automatically when a group is first linked via the official Telegizer bot
or a custom bot token. Existing groups with non-empty settings are never touched.

Edit _DEFAULTS here to change what every future group starts with.
"""

import copy


def get_group_default_settings() -> dict:
    """Return a fresh deep copy of the canonical group defaults."""
    return copy.deepcopy(_DEFAULTS)


def apply_group_defaults(tg) -> bool:
    """
    Write defaults into a TelegramGroup that has no settings yet.

    Returns True if defaults were applied, False if the group already had settings
    (so existing customisations are never overwritten).
    """
    if tg.settings:
        return False
    tg.settings = get_group_default_settings()
    return True


# ── Canonical defaults ────────────────────────────────────────────────────────

_DEFAULTS: dict = {

    # ── Verification ──────────────────────────────────────────────────────────
    # timeout_seconds=120 gives mobile users enough time to read and tap.
    "verification": {
        "enabled": True,
        "method": "button",          # "button" | "math" | "word"
        "timeout_seconds": 120,
        "max_attempts": 3,
        "on_failure": "restrict",    # restrict until verified (matches official-bot behaviour)
        "kick_on_fail": True,
        "trigger": "join",
        "destination": "same_group",
        "destination_topic_id": None,
        "destination_chat_id": None,
    },

    # ── Welcome ───────────────────────────────────────────────────────────────
    # Placeholders supported by WelcomeSystem: {first_name} {last_name}
    # {username} {full_name} {group_name} {member_count} {user_id}
    "welcome": {
        "enabled": True,
        "message": (
            "🎉 Welcome {first_name}!\n"
            "Glad to have you in {group_name} 🚀"
        ),
        "show_rules": True,
        "rules_text": (
            "1. Be respectful to all members\n"
            "2. No spam, scams, or self-promotion without permission"
        ),
        "media_url": "",
        "delete_after_seconds": 0,
        "topic_id": None,
        "ai_welcome_enabled": False,
    },

    # ── XP / Levelling ────────────────────────────────────────────────────────
    # Level formula (levels.py _xp_for_level): cumulative, each tier * 1.5
    # Level-up message placeholders: {first_name} {level}
    "levels": {
        "enabled": True,
        "xp_per_message": 10,
        "xp_cooldown_seconds": 60,
        "xp_per_reaction": 10,
        "xp_reaction_cooldown_seconds": 30,
        "announce_level_up": True,
        "level_up_message": (
            "🎉 Level Up! Congrats {first_name} — you've reached Level {level}"
        ),
        "xp_penalty_warn": -10,
        "xp_penalty_mute": -20,
        "xp_penalty_kick": -30,
        "xp_penalty_ban": -50,
        "roles": [
            {"level": 1,   "name": "Newcomer"},
            {"level": 10,  "name": "Member"},
            {"level": 20,  "name": "Active Member"},
            {"level": 30,  "name": "Contributor"},
            {"level": 40,  "name": "Regular"},
            {"level": 50,  "name": "Core Member"},
            {"level": 60,  "name": "Veteran"},
            {"level": 70,  "name": "Elite"},
            {"level": 80,  "name": "Legend"},
            {"level": 100, "name": "OG"},
        ],
        "rank_card": {
            "bg_color_start": "#1a1a2e",
            "bg_color_end": "#16213e",
            "accent_color": "#2196f3",
        },
        "levelup_topic_id": None,
        "ai_levelup_enabled": False,
        "delete_levelup_after_seconds": 0,
    },

    # ── AutoMod ───────────────────────────────────────────────────────────────
    # ENABLED by default: spam (7 msg / 15 s), bad_words (empty list = no-op),
    #                     excessive_emojis, caps_lock, homoglyphs
    # DISABLED by default: external_links, telegram_links, all media/contact rules
    #
    # homoglyphs is only active in bot_manager.py (official-bot Phase-3 item).
    # bad_words requires a non-empty words list to have any effect.
    "automod": {
        "enabled": True,

        # Enabled
        "spam": {
            "enabled": True,
            "max_messages": 7,
            "time_window_seconds": 15,
            "action": "mute",
            "mute_duration_minutes": 10,
        },
        "bad_words": {
            "enabled": True,
            "words": [],           # add words in group settings; empty = no-op
            "action": "delete",
            "warn_user": True,
        },
        "external_links": {
            "enabled": False,
            "whitelist": [],
            "action": "delete",
        },
        "telegram_links": {
            "enabled": False,
            "action": "delete",
            "warn_user": True,
        },
        "excessive_emojis": {
            "enabled": True,
            "max_emojis": 10,
            "action": "delete",
        },
        "caps_lock": {
            "enabled": True,
            "threshold_percent": 70,
            "min_length": 10,
            "action": "delete",
        },
        "homoglyphs": {"enabled": True},

        # Disabled
        "forwarded_messages": {"enabled": False, "action": "delete"},
        "contact_sharing":    {"enabled": False, "action": "delete", "warn_user": False},
        "location_sharing":   {"enabled": False, "action": "delete", "warn_user": False},
        "email_detection":    {"enabled": False, "action": "delete", "warn_user": False},
        "voice_notes":        {"enabled": False, "action": "delete", "warn_user": False},
        "video_notes":        {"enabled": False, "action": "delete", "warn_user": False},
        "file_attachments":   {"enabled": False, "action": "delete", "warn_user": False},
        "photos":             {"enabled": False, "action": "delete", "warn_user": False},
        "videos":             {"enabled": False, "action": "delete", "warn_user": False},
        "gifs":               {"enabled": False, "action": "delete", "warn_user": False},
        "stickers":           {"enabled": False, "action": "delete", "warn_user": False},
        "games":              {"enabled": False, "action": "delete", "warn_user": False},
        "bot_mentions":       {"enabled": False, "action": "delete", "warn_user": False},
        "spoiler_content":    {"enabled": False, "action": "delete", "warn_user": False},
        "language_filter": {
            "enabled": False,
            "languages": ["cyrillic", "chinese", "korean", "arabic"],
            "action": "delete",
            "warn_user": False,
        },
    },

    # ── Warning / moderation system ───────────────────────────────────────────
    # warning_action: "mute" | "ban" | "kick"
    # auto_delete_*_seconds: 0 = don't auto-delete; only active in bot_manager.py
    "moderation": {
        "max_warnings": 3,
        "warning_action": "mute",
        "mute_duration_minutes": 60,
        "ban_delete_days": 1,
        "notify_on_action": True,
        "log_to_channel": False,
        "log_channel_id": "",
        "escalation_enabled": False,
        "escalation_steps": [
            {"at_warning": 3, "time_window_hours": None, "action": "mute", "duration_minutes": 60},
        ],
        "auto_delete_warn_seconds": 10,
        "auto_delete_action_seconds": 10,
    },

    # ── Auto-clean service messages ───────────────────────────────────────────
    # Currently only applied by bot_manager.py (custom bots).
    # Official-bot support is a Phase-3 item.
    "auto_clean": {
        "enabled": True,
        "delete_joins": True,
        "delete_leaves": True,
        "delete_photo_changes": True,
        "delete_pinned_messages": True,
        "delete_forum_events": True,
        "delete_voice_chat_events": True,
        "delete_game_scores": False,
        "delete_commands": False,
    },

    # ── Reports / digest ──────────────────────────────────────────────────────
    "reports": {
        "enabled": False,
        "notify_admins": "all",
        "selected_admin_ids": [],
    },

    # ── Knowledge base ────────────────────────────────────────────────────────
    "knowledge_base": {
        "enabled": True,
        "auto_reply_enabled": False,
        "auto_reply_mention_only": False,
        "auto_reply_in_groups": True,
        "confidence_threshold": 0.35,
        "fallback_enabled": False,
        "min_message_words": 5,
    },

    # ── Auto-responses ────────────────────────────────────────────────────────
    "auto_responses": {
        "enabled": True,
    },
}
