"""Shared bot UX: scoped command lists and the Mini App "Open App" entry point.

Both the official Telegizer bot and every custom/community bot call into here so they
stay in lockstep — when the command set or the app-open behavior improves, all bots
inherit it (per the product rule "custom bots inherit platform improvements").
"""
import logging

from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    WebAppInfo,
)

_log = logging.getLogger("bot_ui")


# ── Anonymous-admin detection (shared by official + custom bots) ──────────────
# When a group admin has "Remain Anonymous" on, Telegram routes their messages
# through @GroupAnonymousBot (user id 1087968824) and sets message.sender_chat to
# the group itself. The bot CANNOT resolve which real admin sent it — so an admin
# permission check via get_chat_member(chat, sender) fails and account linking /
# DMing a code is impossible. Detect this case and ask them to post visibly.
GROUP_ANONYMOUS_BOT_ID = 1087968824


def is_anonymous_admin(update) -> bool:
    """True when the message was sent by an anonymous admin of THIS group.

    Canonical signal: message.sender_chat is the group itself (sender_chat.id ==
    chat.id). Telegram only lets admins post anonymously, so this implies admin —
    but the real user id is unknowable. Falls back to the @GroupAnonymousBot id.
    """
    chat = getattr(update, "effective_chat", None)
    msg = getattr(update, "effective_message", None)
    sender_chat = getattr(msg, "sender_chat", None) if msg is not None else None
    if sender_chat is not None and chat is not None and sender_chat.id == chat.id:
        return True
    user = getattr(update, "effective_user", None)
    return bool(user and user.id == GROUP_ANONYMOUS_BOT_ID)


# HTML-formatted so both bots (official uses Markdown elsewhere, custom uses HTML)
# can send it with parse_mode=HTML.
ANON_ADMIN_LINKGROUP_HTML = (
    "🕵️ <b>Anonymous admin detected.</b>\n\n"
    "Please send /linkgroup as a <b>visible admin</b> so Telegizer can verify your "
    "permissions.\n\n"
    "Turn off <b>“Remain Anonymous”</b> in this group's admin settings, then try again.\n\n"
    "<i>After linking, you can switch anonymous admin mode back on.</i>"
)


# ── Command sets, by Telegram scope ──────────────────────────────────────────
# Telegram shows commands based on scope, so regular members and admins see
# different menus automatically.

def _private_commands():
    """Shown in DMs with the bot — setup + account actions."""
    return [
        BotCommand("start",     "Open the control center"),
        BotCommand("help",      "Setup guide & commands"),
        BotCommand("linkgroup", "Link a group (run inside the group)"),
        BotCommand("status",    "Check bot status (run inside the group)"),
        BotCommand("support",   "Get help"),
    ]


def _group_member_commands():
    """Shown to regular members inside groups — safe, read-only-ish commands."""
    return [
        BotCommand("rank",        "Check your XP and level"),
        BotCommand("leaderboard", "Top members by XP"),
        BotCommand("report",      "Report a message (reply to it)"),
    ]


def _group_admin_commands():
    """Shown to admins inside groups — members' commands plus moderation."""
    return _group_member_commands() + [
        BotCommand("warn",     "Warn a user"),
        BotCommand("ban",      "Ban a user"),
        BotCommand("kick",     "Kick a user"),
        BotCommand("mute",     "Mute a user"),
        BotCommand("unmute",   "Unmute a user"),
        BotCommand("tempban",  "Temp-ban a user"),
        BotCommand("purge",    "Delete the last N messages"),
        BotCommand("status",   "Check bot status"),
    ]


# ── Official bot command sets ────────────────────────────────────────────────
# The official bot has a slightly different handler set (e.g. /xp instead of /rank,
# /warnings check) so it gets its own lists — same role-scoping pattern.

def _official_private_commands():
    return [
        BotCommand("start",     "Open the companion hub"),
        BotCommand("help",      "Setup guide"),
        BotCommand("linkgroup", "Link this group (run inside the group)"),
        BotCommand("status",    "Check bot status (run inside the group)"),
    ]


def _official_group_member_commands():
    return [
        BotCommand("xp",          "Check your XP and level"),
        BotCommand("leaderboard", "Top members by XP"),
        BotCommand("warnings",    "Check a user's warnings"),
    ]


def _official_group_admin_commands():
    return _official_group_member_commands() + [
        BotCommand("warn",    "Warn a user"),
        BotCommand("ban",     "Ban a user"),
        BotCommand("kick",    "Kick a user"),
        BotCommand("mute",    "Mute a user"),
        BotCommand("unmute",  "Unmute a user"),
        BotCommand("tempban", "Temp-ban a user"),
        BotCommand("purge",   "Delete the last N messages"),
        BotCommand("status",  "Check bot status"),
    ]


async def _apply_scoped(bot, private, member, admin):
    """Set role/scoped command menus. Best-effort; never raises."""
    try:
        await bot.set_my_commands(private, scope=BotCommandScopeAllPrivateChats())
        await bot.set_my_commands(member, scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands(admin, scope=BotCommandScopeAllChatAdministrators())
        await bot.set_my_commands(private, scope=BotCommandScopeDefault())
        return True
    except Exception as exc:
        _log.warning("apply_scoped commands failed: %s", exc)
        return False


async def apply_scoped_commands(bot):
    """Custom/community bots — role-scoped command menus (members vs admins)."""
    return await _apply_scoped(
        bot, _private_commands(), _group_member_commands(), _group_admin_commands()
    )


async def apply_official_scoped_commands(bot):
    """Official Telegizer bot — role-scoped command menus (members vs admins)."""
    return await _apply_scoped(
        bot, _official_private_commands(),
        _official_group_member_commands(), _official_group_admin_commands(),
    )


async def ensure_menu_button(bot, frontend):
    """Set the persistent chat Menu Button to launch the Telegizer Mini App.

    This is the reliable per-bot "Open App" entry point (works without BotFather
    domain registration for the menu button). Best-effort; if Telegram rejects it
    the inline URL buttons still provide an app/dashboard link.
    """
    try:
        url = f"{frontend.rstrip('/')}/mini-app"
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Open App", web_app=WebAppInfo(url=url))
        )
        return True
    except Exception as exc:
        _log.warning("ensure_menu_button failed: %s", exc)
        return False


# ── Shared main-menu keyboard (official + custom bots) ────────────────────────
# Single source of truth for the DM "control center" menu so every bot — the
# official Telegizer bot and all derived custom group-management bots — stays in
# lockstep. Per the bot-lineage rule, NEW menu entries go here, not into one bot.
#
# Section buttons jump straight to the right Mini App page:
#   • official bot  → web_app=WebAppInfo(.../mini-app?start=<code>)  (in-Telegram,
#     authenticated directly against the official bot token).
#   • custom bot    → url=https://t.me/<official>?startapp=<code>    (custom bots
#     can't auth the Mini App themselves, so they route through the official bot).
# The Mini App reads the `start` query param / Telegram start_param and navigates
# (see frontend resolveStartDestination).

def _clean_username(raw, fallback):
    if not raw:
        return fallback
    return str(raw).strip().lstrip("@").split("/")[-1] or fallback


def build_main_menu(
    *,
    frontend,
    official_username,
    echo_username=None,
    is_official=False,
    is_linked=False,
    email_verified=False,
    pending_count=0,
):
    """Return the standard control-center InlineKeyboardMarkup for a DM /start menu.

    Shared by the official bot and every custom bot so the inbox menu never drifts.
    """
    frontend = (frontend or "https://telegizer.com").rstrip("/")
    official_username = _clean_username(official_username, "telegizer_bot")
    echo_username = _clean_username(echo_username, None)

    def section(label, code):
        """A button that opens a specific Mini App section."""
        if is_official:
            return InlineKeyboardButton(
                label, web_app=WebAppInfo(url=f"{frontend}/mini-app?start={code}")
            )
        return InlineKeyboardButton(
            label, url=f"https://t.me/{official_username}?startapp={code}"
        )

    # Row 0 — primary CTA: open the app home.
    if is_official:
        open_app = InlineKeyboardButton(
            "🚀 Open Telegizer App", web_app=WebAppInfo(url=f"{frontend}/mini-app")
        )
    else:
        open_app = InlineKeyboardButton(
            "🚀 Open Telegizer App", url=f"https://t.me/{official_username}?startapp=dashboard"
        )
    keyboard = [[open_app]]

    if pending_count:
        keyboard.append([InlineKeyboardButton(
            f"⚠️ {pending_count} Group(s) Awaiting Setup",
            callback_data="menu:pending_groups",
        )])

    # Core group actions
    keyboard.append([
        InlineKeyboardButton("➕ Add Group", callback_data="menu:add_group"),
        section("📋 My Groups", "mygroups"),
    ])
    # Bot management
    keyboard.append([
        section("🤖 My Bots", "mybots"),
        section("🔌 Connect Custom Bot", "connectbot"),
    ])
    # Echo (Lineage B) cross-navigation — links only, no assistant logic.
    echo_row = []
    if echo_username:
        echo_row.append(InlineKeyboardButton(
            "🧠 Telegizer Echo Bot", url=f"https://t.me/{echo_username}"
        ))
    echo_row.append(section("🧠 Telegizer Echo App", "echo"))
    keyboard.append(echo_row)
    # Referral (in-bot screen)
    keyboard.append([InlineKeyboardButton("🎁 Referral Link", callback_data="menu:referral")])
    # Email verification (replaces "Account Connected") — optional, additive.
    if email_verified:
        keyboard.append([InlineKeyboardButton("✅ Email Verified", callback_data="menu:email_verify")])
    else:
        keyboard.append([InlineKeyboardButton("📧 Email Verification", callback_data="menu:email_verify")])
    # Utility
    keyboard.append([
        InlineKeyboardButton("💬 Support", callback_data="menu:support"),
        InlineKeyboardButton("⚙️ Quick Settings", callback_data="qs:groups"),
    ])

    return InlineKeyboardMarkup(keyboard)
