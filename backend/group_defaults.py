"""
Centralized default settings for all new TelegramGroup records.

Applied automatically when a group is first linked via the official Telegizer bot
or a custom bot token. Existing groups with non-empty settings are never touched
by apply_group_defaults(), but fill_missing_defaults() will add any top-level
section that is absent — safe to call on every group creation / link event.

Edit _DEFAULTS here to change what every future group starts with.

Name placeholder convention
────────────────────────────
Use {name} in message templates wherever a user's display name is needed.
The runtime resolves it as:
  • both first + last name present  →  "First Last"
  • only first name, has @username  →  "@username"
  • only first name, no username    →  "First"
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
    For groups that already have some settings, use fill_missing_defaults() instead.
    """
    if tg.settings:
        return False
    tg.settings = get_group_default_settings()
    return True


def fill_missing_defaults(tg) -> bool:
    """
    Ensure every top-level section in _DEFAULTS exists on tg.settings.

    - If settings is empty/None: writes the full defaults (same as apply_group_defaults).
    - If settings already exist: adds only the top-level keys that are absent.
      Existing values are NEVER overwritten.

    Returns True if any change was made, False if nothing was missing.
    """
    if not tg.settings:
        tg.settings = get_group_default_settings()
        return True

    defaults = get_group_default_settings()
    changed = False
    current = dict(tg.settings)
    for key, value in defaults.items():
        if key not in current:
            current[key] = value
            changed = True
    if changed:
        tg.settings = current
    return changed


# ── Canonical defaults ────────────────────────────────────────────────────────

_DEFAULTS: dict = {

    # ── Verification ──────────────────────────────────────────────────────────
    # Disabled by default — most new groups don't have a bot-join problem yet.
    # Admins who need it enable it deliberately.
    "verification": {
        "enabled": False,
        "method": "button",          # "button" | "math" | "word"
        "timeout_seconds": 300,      # 5 min — matches the user-facing default
        "max_attempts": 3,
        "on_failure": "restrict",
        "kick_on_fail": True,
        "trigger": "join",
        "destination": "same_group",
        "destination_topic_id": None,
        "destination_chat_id": None,
        "auto_delete_on_timeout": True,  # delete the challenge message when timeout fires
    },

    # ── Welcome ───────────────────────────────────────────────────────────────
    # {name} = full name if both names present, @username if available, else first name.
    # Other placeholders: {first_name} {last_name} {username} {full_name}
    #                     {group_name} {member_count} {user_id}
    "welcome": {
        "enabled": True,
        "message": (
            "👋 Welcome, {name}! Great to have you in {group_name}.\n"
            "Check the rules below and enjoy the community 🚀"
        ),
        "show_rules": True,
        "rules_text": (
            "1. Be respectful to all members\n"
            "2. No spam, scams, or self-promotion without permission\n"
            "3. Follow admin instructions and keep content relevant to the group"
        ),
        "media_url": "",
        "delete_after_seconds": 0,
        "topic_id": None,
        "ai_welcome_enabled": False,
    },

    # ── XP / Levelling ────────────────────────────────────────────────────────
    # Level formula (levels.py): linear — level = xp // 100 + 1 (100 XP per level)
    # Level-up message placeholders: {name} {first_name} {username} {level} {user_id}
    "levels": {
        "enabled": True,
        "xp_per_message": 10,
        "xp_cooldown_seconds": 60,
        "xp_per_reaction": 5,        # reactions are single-tap; lower than message XP
        "xp_reaction_cooldown_seconds": 60,
        "xp_per_raid": 50,
        "announce_level_up": True,
        "level_up_message": (
            "🎉 {name} just reached Level {level}! Keep it up 🚀"
        ),
        "xp_penalty_warn": -10,
        "xp_penalty_mute": -20,
        "xp_penalty_kick": -30,
        "xp_penalty_ban": -50,
        # Rebalanced: early milestones are reachable, OG reserved for dedicated members.
        "roles": [
            {"level": 1,   "name": "Newcomer"},
            {"level": 5,   "name": "Member"},
            {"level": 10,  "name": "Active Member"},
            {"level": 20,  "name": "Contributor"},
            {"level": 30,  "name": "Regular"},
            {"level": 40,  "name": "Core Member"},
            {"level": 50,  "name": "Veteran"},
            {"level": 60,  "name": "Elite"},
            {"level": 75,  "name": "Legend"},
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
    # ENABLED: spam (5 msg / 10 s), bad_words (empty = no-op), excessive_emojis,
    #          caps_lock, homoglyphs
    # DISABLED: external_links, telegram_links, all media/contact rules
    "automod": {
        "enabled": True,

        "spam": {
            "enabled": True,
            "max_messages": 5,           # tightened from 7
            "time_window_seconds": 10,   # tightened from 15
            "action": "mute",
            "mute_duration_minutes": 10,
        },
        "bad_words": {
            "enabled": True,
            "words": [],                 # no-op until admin adds words
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
            "max_emojis": 15,            # raised from 10 — allows normal enthusiasm
            "action": "delete",
        },
        "caps_lock": {
            "enabled": True,
            "threshold_percent": 80,     # raised from 70
            "min_length": 15,            # raised from 10 — avoids short celebratory caps
            "action": "delete",
        },
        "homoglyphs": {"enabled": True},

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
    "moderation": {
        "max_warnings": 3,
        "warning_action": "mute",
        "mute_duration_minutes": 30,     # reduced from 60 — less punitive default
        "ban_delete_days": 1,
        "notify_on_action": True,
        "log_to_channel": False,
        "log_channel_id": "",
        "escalation_enabled": False,
        # Pre-configured 4-step ladder — activates when escalation_enabled = True.
        "escalation_steps": [
            {"at_warning": 3,  "time_window_hours": None, "action": "mute",    "duration_minutes": 30},
            {"at_warning": 5,  "time_window_hours": None, "action": "mute",    "duration_minutes": 180},
            {"at_warning": 7,  "time_window_hours": None, "action": "kick",    "duration_minutes": 0},
            {"at_warning": 10, "time_window_hours": None, "action": "ban",     "duration_minutes": 0},
        ],
        "auto_delete_warn_seconds": 30,   # raised from 10 — visible for 30 s
        "auto_delete_action_seconds": 30, # raised from 10
    },

    # ── Auto-clean service messages ───────────────────────────────────────────
    # Disabled by default — admins should consciously opt in to silent joins/leaves.
    "auto_clean": {
        "enabled": False,
        "delete_joins": False,
        "delete_leaves": False,
        "delete_photo_changes": False,
        "delete_pinned_messages": True,  # pin notifications are almost always noise
        "delete_forum_events": False,
        "delete_voice_chat_events": False,
        "delete_game_scores": False,
        "delete_commands": False,
    },

    # ── Reports ───────────────────────────────────────────────────────────────
    "reports": {
        "enabled": False,
        "notify_admins": "all",
        "selected_admin_ids": [],
    },

    # ── Knowledge base ────────────────────────────────────────────────────────
    "knowledge_base": {
        "enabled": True,
        "auto_reply_enabled": False,
        "auto_reply_mention_only": True,  # require @mention — intentional interaction
        "auto_reply_in_groups": True,
        "confidence_threshold": 0.65,     # raised from 0.35 — only reply when confident
        "fallback_enabled": False,
        "min_message_words": 5,
        # AI personality & reply behavior (new — all have safe defaults)
        "personality": "professional_support",
        "custom_instructions": "",
        "reply_length": "balanced",       # concise | balanced | detailed
        "emoji_level": "minimal",         # none | minimal | moderate
        "formality_level": "neutral",     # casual | neutral | formal
        "use_auto_replies_as_knowledge": False,
    },

    # ── Auto-responses ────────────────────────────────────────────────────────
    "auto_responses": {
        "enabled": True,
    },

    # ── Multimodal image AI ───────────────────────────────────────────────────
    # Uses GPT-4o mini vision by default (~$0.0003–0.0008/image).
    # 5-gate smart routing: most images never reach the API.
    # Disabled by default — admins opt in and supply their own AI key.
    "image_ai": {
        "enabled": False,
        "confidence_threshold": 0.65,
        "mention_only": True,         # only analyze if bot is @mentioned
        "require_caption": True,      # skip images with no caption/question
        "max_image_size_mb": 5,
        "escalation_enabled": True,
        "escalation_admin_ids": [],   # Telegram user IDs to DM on escalation
        "cost_mode": "balanced",      # balanced | aggressive_savings | quality
    },

    # ── Social / human-like community interaction ─────────────────────────────
    # Detects appreciation messages ("thanks", "helpful", etc.) and responds
    # naturally. No AI cost — static personality-aware response pools.
    # cooldown_minutes: min gap between replies to the same user.
    # mode: minimal | professional | friendly | community_manager
    "social_replies": {
        "enabled": False,                # opt-in: admins enable deliberately
        "react_to_appreciation": True,
        "reply_to_appreciation": True,
        "cooldown_minutes": 5,
        "mode": "friendly",
    },

    # ── Raids (Twitter/X engagement campaigns) ────────────────────────────────
    "raids": {
        "enabled": True,
        "default_duration_hours": 24,
        "default_xp_reward": 50,         # reduced from 100 — keeps level system meaningful
        "pin_announcement": True,
        "reminders_enabled": True,
    },

    # ── Digest / activity reports ─────────────────────────────────────────────
    "digest": {
        "daily": False,
        "weekly": False,
        "monthly": False,
        "send_to_group": True,
    },

    # ── Admin alerts ──────────────────────────────────────────────────────────
    "admin_alerts": {
        "enabled": False,
        "on_ban": False,
        "on_raid_start": False,
        "on_report": True,    # pre-wired: fires when master switch enabled
        "on_spam_burst": False,
    },

    # ── Command routing / topic access control ────────────────────────────────
    # Applies to forum groups (supergroups with topics enabled).
    # topics: list of known forum topics discovered from incoming messages.
    # commands: per-command access rules. scope = "all_group" | "specific_topics" | "disabled"
    # Default scope "all_group" means commands work everywhere — existing groups unaffected.
    "command_routing": {
        "topics": [],
        # {"/leaderboard": {"scope": "all_group", "topic_ids": []}, ...}
        "commands": {},
        # "silent" = ignore the command; "message" = send restricted_message text
        "restricted_reply": "silent",
        "restricted_message": "⚠️ This command is only available in the {topic} topic.",
    },
}
