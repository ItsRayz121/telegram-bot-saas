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


def _deep_fill(current: dict, defaults: dict) -> bool:
    """Recursively add any default key missing from `current`, including nested dicts.

    Existing values are NEVER overwritten — only absent keys are added. Returns True if
    anything changed. This is what lets pre-existing groups inherit new default settings
    (e.g. auto_delete_warnings, delete_unauthorized_commands) added in later releases.
    """
    changed = False
    for key, value in defaults.items():
        if key not in current:
            current[key] = copy.deepcopy(value)
            changed = True
        elif isinstance(value, dict) and isinstance(current.get(key), dict):
            if _deep_fill(current[key], value):
                changed = True
    return changed


def fill_missing_defaults(tg) -> bool:
    """
    Ensure every section AND nested key in _DEFAULTS exists on tg.settings.

    - If settings is empty/None: writes the full defaults (same as apply_group_defaults).
    - If settings already exist: recursively adds only the keys that are absent
      (top-level sections and nested keys). Existing values are NEVER overwritten.

    Returns True if any change was made, False if nothing was missing.
    """
    if not tg.settings:
        tg.settings = get_group_default_settings()
        return True

    defaults = get_group_default_settings()
    current = copy.deepcopy(dict(tg.settings))
    changed = _deep_fill(current, defaults)
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
        # When a non-admin uses an admin-only command (/warn /ban /mute /kick),
        # delete their command message instead of replying in the group. #7
        "delete_unauthorized_commands": True,

        "spam": {
            "enabled": True,
            "max_messages": 5,           # tightened from 7
            "time_window_seconds": 10,   # tightened from 15
            "action": "mute",
            "mute_duration_minutes": 10,
        },
        # Slow mode — a per-user MINIMUM gap between messages (a smarter version
        # of Telegram's native slow mode). Distinct from `spam` above, which is
        # burst detection (N msgs in a short window). This enforces a steady pace:
        # a member's message that arrives sooner than seconds_between_messages
        # after their previous accepted one is removed. Admins and trusted users
        # (automod.smart_mod.trusted_users) are always exempt; members at/above
        # exempt_min_level (0 = off) also bypass it. OFF by default — opt-in, since
        # it changes how a group fundamentally feels. action "delete" is silent and
        # the safest for anti-ban; "warn" sends a notice throttled to at most once
        # per gap per user; "mute" temporarily restricts repeat offenders;
        # "restrict" emulates a Telegram-native cooldown — it removes the too-fast
        # message and restricts the member ONLY until their next allowed time (the
        # remaining gap), so Telegram shows them a "you can write again in …"
        # countdown that auto-lifts. A single throttled "please wait Ns" notice
        # accompanies it when `notify` is on. Bots cannot set Telegram's native
        # per-group slow-mode timer (not in the Bot API) — this is the closest.
        "slow_mode": {
            "enabled": False,
            "seconds_between_messages": 60,
            "action": "delete",          # "delete" | "warn" | "mute" | "restrict"
            "mute_duration_minutes": 5,  # used when action == "mute"
            "notify": True,              # send the throttled "please wait Ns" notice (warn/restrict)
            "exempt_min_level": 0,       # members at/above this XP level bypass (0 = no level exemption)
        },
        "bad_words": {
            "enabled": True,
            "words": [],                 # no-op until admin adds words
            "action": "delete",
            "warn_user": True,
        },
        # Adult/NSFW content + CSAM (shared content_filter module). ON by default
        # — adult spam is the single most common attack and the word list is
        # conservative + boundary-matched to avoid false bans. NSFW riding on an
        # inline button (which ordinary clients can't attach) is almost never
        # legit → harsher action. CSAM is always banned.
        "nsfw_filter": {
            "enabled": True,
            "action": "delete",          # plain text/caption — humans may quote
            "button_action": "ban",      # NSFW on an inline button → near-zero FP
            "csam_action": "ban",        # zero tolerance
            "extra_words": [],           # admin-supplied additions
            "warn_user": True,
        },
        # Inline keyboards can only be attached by bots/userbots/inline mode,
        # never by an ordinary member's client — so a non-admin message carrying
        # one is a strong spam signal. OFF by default because some communities
        # legitimately use inline-bot tools (polls, games); turn on for
        # locked-down groups. A shortener/scam-TLD link behind a button escalates
        # to suspicious_action.
        "inline_button_scan": {
            "enabled": False,
            "action": "delete",
            "suspicious_action": "ban",
            "warn_user": False,
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

        # ── Smart Moderation (3-layer: rules → hidden URL → AI) ──────────────
        "smart_mod": {
            "enabled": False,
            "group_topic": "",           # e.g. "CreatorX — creator economy tools"
            "promotional_detection": True,
            "hidden_url_detection": True,
            "allow_referral_codes": False,
            "ai_enabled": False,         # Layer 3 — uses workspace AI key
            "ai_rate_limit_seconds": 30, # min seconds between AI calls per user
            "trusted_users": [],         # list of int telegram user IDs
            "action": "delete",
            "warn_user": True,
        },
    },

    # ── Bot policy (Phase 1: bot-spam protection) ─────────────────────────────
    # Telegram NEVER delivers another bot's messages to us, so bot-posted spam
    # can't be caught at the message layer — it must be controlled at JOIN time.
    # When an unapproved bot is added we restrict it (mute) and ask admins to
    # approve or ban via inline buttons posted in the group.
    #
    # policy:
    #   "allow_all"               — never act on bot joins (legacy behaviour)
    #   "restrict_until_approval" — DEFAULT: mute new bots, alert admins to decide
    #   "block_unapproved"        — ban any non-trusted bot on join
    #   "allowlist_only"          — only trusted bots may operate; ban the rest
    "bot_policy": {
        "enabled": True,
        "policy": "restrict_until_approval",
        # Lowercased usernames WITHOUT the leading @. The Telegizer official bot
        # and the group's own linked custom bot are trusted automatically when
        # auto_trust_own_bots is True, so they never need listing here.
        "trusted_bot_usernames": [],
        "auto_trust_own_bots": True,
        # Where admins are notified when an unapproved bot is added:
        #   "dm"    — DEFAULT: private DM to the admin who added it / the owner.
        #             The bot is muted the instant it joins, so no spam reaches
        #             the group even before anyone responds. The in-group fallback
        #             notice (only if DM can't be delivered) NEVER shows the bot's
        #             @username, so members can't tap a scam link.
        #   "group" — post the alert in the group (linkless notice + buttons).
        #   "both"  — DM and post a linkless group notice.
        "notify": "dm",
        "delete_alert_after_decision": True,    # remove the alert once an admin decides
        "log_events": True,                     # write bot_join / bot_approved / bot_banned events
        # Auto-decision if no admin acts in time. The bot stays muted the whole
        # time, so this is cleanup, not exposure control.
        "approval_timeout_minutes": 60,
        "on_timeout": "ban",                    # "ban" | "keep_restricted"
    },

    # ── Raid mode (Phase 3: bot-spam protection) ──────────────────────────────
    # BEHAVIOUR-based, NOT join-rate. Join-rate locking trips on healthy spikes
    # (shout-outs, launches, a timezone waking up), so we never lock on raw join
    # count. Instead a raid is detected from coordinated-attack signatures:
    #   • trigger_violators  — N DISTINCT users trip automod within window_seconds
    #   • duplicate_threshold — N DISTINCT users post the SAME text within the window
    # On detection the group enters a temporary lockdown: members who join WHILE
    # the raid is active are auto-restricted (or kicked). Lockdown auto-expires
    # after lockdown_minutes. OFF by default — opt-in, since a false activation
    # would restrict genuine newcomers.
    "raid_guard": {
        "enabled": False,
        "window_seconds": 60,
        "trigger_violators": 5,
        "duplicate_threshold": 5,
        "min_text_len": 8,
        "lockdown_minutes": 10,
        "lockdown_action": "mute",              # "mute" | "kick" joiners during a raid
        # Who gets restricted from MESSAGING while a raid is active:
        #   "recent_joiners" → only members who join during the raid (default)
        #   "all"            → every non-admin who posts is muted (group read-only)
        "lockdown_scope": "recent_joiners",
        "notify": True,
        # Phase 4b: admin "emergency lockdown" panic button. ISO-8601 UTC expiry
        # set from the dashboard; join handlers restrict newcomers until it passes.
        # Works even when enabled=False (manual override). null = no manual lockdown.
        "manual_lockdown_until": None,
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
        "escalation_enabled": True,
        # 3-strike ladder: warn freely → mute → mute hard → ban.
        "escalation_steps": [
            {"at_warning": 3, "time_window_hours": None, "action": "mute",    "duration_minutes": 60},
            {"at_warning": 4, "time_window_hours": None, "action": "mute",    "duration_minutes": 1440},
            {"at_warning": 5, "time_window_hours": None, "action": "tempban", "duration_hours": 720},
        ],
        "auto_delete_warnings": True,     # #10 — auto-remove warning/action notices from chat
        "auto_delete_warn_seconds": 30,   # raised from 10 — visible for 30 s
        "auto_delete_action_seconds": 30, # raised from 10
    },

    # ── Warning escalation (FOUNDATION — disabled, NOT enforced) ───────────────
    # A clean, owner-configurable auto-escalation policy scaffold. Intentionally
    # separate from moderation.escalation_steps (which is the live 3-strike
    # ladder) so the owner can design the final auto-mute rules here without any
    # of these values taking effect yet. No handler reads `warning_escalation`;
    # `enabled` stays False until the owner decides the final rules. Both bot
    # lineages inherit this block automatically via the shared defaults.
    "warning_escalation": {
        "enabled": False,                 # master switch — keep False until finalised
        "warning_threshold": 3,           # warnings before the action triggers
        "time_window_hours": 24,          # only count warnings within this window (null = all-time)
        "action_type": "mute",            # mute | kick | ban | none
        "mute_duration_minutes": 60,      # used when action_type == "mute"
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

    # ── Global escalation ─────────────────────────────────────────────────────
    # Applies to ALL AI & Automation issues: KB low-confidence, image AI,
    # command failures, automation errors, and hub reply no-match.
    "escalation": {
        "enabled": False,
        "admin_ids": [],              # Telegram user IDs to DM on any escalation
        "types": ["ai_kb", "ai_image", "automation", "command"],
        "auto_learn": True,           # auto-store admin replies back into KB
        "notify_group_on_resolve": False,
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
        "cost_mode": "balanced",      # balanced | aggressive_savings | quality
        # Legacy per-feature escalation kept for backward compat; global wins if set
        "escalation_enabled": True,
        "escalation_admin_ids": [],
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

    # ── Emoji reactions ───────────────────────────────────────────────────────
    # Sentiment-based reactions to member messages + 👍 on admin messages.
    # admin_thumbs_up fires whenever an admin/creator sends any message.
    # sentiment_reactions fires for members based on detected tone.
    "reactions": {
        "enabled": False,
        "admin_thumbs_up": True,       # 👍 every admin message
        "sentiment_reactions": True,   # ❤️ 🔥 😂 👍 🎉 🫂 based on tone
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
