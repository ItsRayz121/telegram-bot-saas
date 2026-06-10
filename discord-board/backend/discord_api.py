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
