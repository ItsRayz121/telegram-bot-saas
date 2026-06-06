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
    MenuButtonWebApp,
    WebAppInfo,
)

_log = logging.getLogger("bot_ui")


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


async def apply_scoped_commands(bot):
    """Register role/scoped command menus for a bot. Best-effort; never raises.

    - DMs: setup/account commands
    - Group members: XP/info commands
    - Group admins: the above plus moderation commands
    """
    try:
        await bot.set_my_commands(_private_commands(), scope=BotCommandScopeAllPrivateChats())
        await bot.set_my_commands(_group_member_commands(), scope=BotCommandScopeAllGroupChats())
        await bot.set_my_commands(_group_admin_commands(), scope=BotCommandScopeAllChatAdministrators())
        # Fallback for any context not covered above.
        await bot.set_my_commands(_private_commands(), scope=BotCommandScopeDefault())
        return True
    except Exception as exc:
        _log.warning("apply_scoped_commands failed: %s", exc)
        return False


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
