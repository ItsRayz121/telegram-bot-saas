"""Thin Discord REST client for Guildizer. Self-contained — no Telegizer imports.

Covers exactly what Phase 1 needs:
  - OAuth2 token exchange / refresh
  - fetch the logged-in user and their guild list (user token)
  - fetch a guild's channels / roles (bot token) as a REST fallback to the
    bot's gateway sync
"""
from __future__ import annotations

import requests

from config import Config

API_BASE = "https://discord.com/api/v10"
# User-facing OAuth2 consent screen (login + bot invite). Distinct from API_BASE,
# which is the REST endpoint used for token exchange and bot calls.
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
_TIMEOUT = 15


# --- Permission bit constants we care about (Discord permission bitfield) -----
PERM_MANAGE_GUILD = 1 << 5          # 32 — "Manage Server"
PERM_ADMINISTRATOR = 1 << 3         # 8

# Bot-invite permission set: enough to manage roles/channels, moderate, and
# post. Deliberately NOT Administrator. Override with DISCORD_BOT_PERMISSIONS.
_INVITE_BITS = (
    (1 << 0)   # Create Instant Invite
    | (1 << 1)   # Kick Members
    | (1 << 2)   # Ban Members
    | (1 << 4)   # Manage Channels
    | (1 << 5)   # Manage Guild
    | (1 << 6)   # Add Reactions
    | (1 << 10)  # View Channels
    | (1 << 11)  # Send Messages
    | (1 << 13)  # Manage Messages
    | (1 << 14)  # Embed Links
    | (1 << 15)  # Attach Files
    | (1 << 16)  # Read Message History
    | (1 << 27)  # Manage Nicknames
    | (1 << 28)  # Manage Roles
    | (1 << 29)  # Manage Webhooks
    | (1 << 40)  # Moderate Members (timeout)
)


def bot_invite_permissions() -> int:
    raw = Config.DISCORD_BOT_PERMISSIONS
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return _INVITE_BITS


def can_manage(permissions: int, *, is_owner: bool) -> bool:
    """True if the user owns the guild or has Manage Server / Administrator."""
    return (
        is_owner
        or bool(permissions & PERM_ADMINISTRATOR)
        or bool(permissions & PERM_MANAGE_GUILD)
    )


# --- OAuth2 -------------------------------------------------------------------
def exchange_code(code: str) -> dict:
    """Exchange an authorization code for an access/refresh token pair."""
    data = {
        "client_id": Config.DISCORD_CLIENT_ID,
        "client_secret": Config.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": Config.DISCORD_REDIRECT_URI,
    }
    resp = requests.post(
        f"{API_BASE}/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_token(refresh: str) -> dict:
    data = {
        "client_id": Config.DISCORD_CLIENT_ID,
        "client_secret": Config.DISCORD_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh,
    }
    resp = requests.post(
        f"{API_BASE}/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# --- User token calls ---------------------------------------------------------
def get_current_user(access_token: str) -> dict:
    resp = requests.get(
        f"{API_BASE}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def get_user_guilds(access_token: str) -> list[dict]:
    """The guilds the user is in, including their `permissions` and `owner`."""
    resp = requests.get(
        f"{API_BASE}/users/@me/guilds",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# --- Bot token calls (REST fallback to gateway sync) --------------------------
def _bot_headers() -> dict:
    return {"Authorization": f"Bot {Config.DISCORD_BOT_TOKEN}"}


def get_guild_channels(guild_id: int) -> list[dict]:
    resp = requests.get(
        f"{API_BASE}/guilds/{guild_id}/channels",
        headers=_bot_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def get_guild_roles(guild_id: int) -> list[dict]:
    resp = requests.get(
        f"{API_BASE}/guilds/{guild_id}/roles",
        headers=_bot_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# --- Moderation via REST (dashboard row actions; no gateway needed) -----------
def _mod_headers(reason: str | None = None) -> dict:
    h = _bot_headers()
    if reason:
        h["X-Audit-Log-Reason"] = reason[:400]
    return h


def kick_member(guild_id: int, user_id: int, reason: str | None = None) -> None:
    resp = requests.delete(
        f"{API_BASE}/guilds/{guild_id}/members/{user_id}",
        headers=_mod_headers(reason), timeout=_TIMEOUT,
    )
    resp.raise_for_status()


def ban_member(guild_id: int, user_id: int, reason: str | None = None,
               delete_message_seconds: int = 0) -> None:
    resp = requests.put(
        f"{API_BASE}/guilds/{guild_id}/bans/{user_id}",
        headers=_mod_headers(reason),
        json={"delete_message_seconds": max(0, min(604800, int(delete_message_seconds)))},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()


def timeout_member(guild_id: int, user_id: int, until_iso: str | None,
                   reason: str | None = None) -> None:
    """Set (or clear, when until_iso is None) a member's communication timeout."""
    resp = requests.patch(
        f"{API_BASE}/guilds/{guild_id}/members/{user_id}",
        headers=_mod_headers(reason),
        json={"communication_disabled_until": until_iso},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()


def unban_member(guild_id: int, user_id: int, reason: str | None = None) -> None:
    """Lift a ban. Treats an already-unbanned user (404) as success."""
    resp = requests.delete(
        f"{API_BASE}/guilds/{guild_id}/bans/{user_id}",
        headers=_mod_headers(reason), timeout=_TIMEOUT,
    )
    if resp.status_code == 404:
        return
    resp.raise_for_status()


# --- White-label custom bot validation (arbitrary bot token) -------------------
# Application flags that report whether the privileged-intent toggles are ON in
# the app owner's Developer Portal. The *_LIMITED variants are what unverified
# apps (<100 servers) get — they are fully functional, so both bits count.
APP_FLAG_GATEWAY_GUILD_MEMBERS = 1 << 14
APP_FLAG_GATEWAY_GUILD_MEMBERS_LIMITED = 1 << 15
APP_FLAG_GATEWAY_MESSAGE_CONTENT = 1 << 18
APP_FLAG_GATEWAY_MESSAGE_CONTENT_LIMITED = 1 << 19


class InvalidBotToken(Exception):
    """The supplied token was rejected by Discord (401)."""


def _custom_bot_headers(token: str) -> dict:
    return {"Authorization": f"Bot {token}"}


def validate_bot_token(token: str) -> dict:
    """Validate a customer-supplied bot token and describe the bot behind it.

    Returns {bot_user_id, bot_username, bot_avatar, application_id,
             intents_members, intents_message_content}.
    Raises InvalidBotToken on a 401; lets network errors bubble for a 502.
    """
    me = requests.get(
        f"{API_BASE}/users/@me",
        headers=_custom_bot_headers(token),
        timeout=_TIMEOUT,
    )
    if me.status_code == 401:
        raise InvalidBotToken("Discord rejected this token.")
    me.raise_for_status()
    bot_user = me.json()

    app_resp = requests.get(
        f"{API_BASE}/oauth2/applications/@me",
        headers=_custom_bot_headers(token),
        timeout=_TIMEOUT,
    )
    if app_resp.status_code == 401:
        raise InvalidBotToken("Discord rejected this token.")
    app_resp.raise_for_status()
    app = app_resp.json()
    flags = int(app.get("flags") or 0)

    return {
        "bot_user_id": int(bot_user["id"]),
        "bot_username": bot_user.get("username"),
        "bot_avatar": bot_user.get("avatar"),
        "application_id": int(app["id"]),
        "intents_members": bool(
            flags & (APP_FLAG_GATEWAY_GUILD_MEMBERS | APP_FLAG_GATEWAY_GUILD_MEMBERS_LIMITED)
        ),
        "intents_message_content": bool(
            flags & (APP_FLAG_GATEWAY_MESSAGE_CONTENT | APP_FLAG_GATEWAY_MESSAGE_CONTENT_LIMITED)
        ),
    }
