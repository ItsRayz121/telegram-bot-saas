"""Named sync problems (GS-xxx).

Every way the server<->Discord sync can go wrong has a stable code, a plain-English
message for the dashboard, and a suggested fix. Users/admins on any platform can quote
the code when they report an issue; discord-board/SYNC_ERRORS.md documents each one.
Keep this table and that doc in step.
"""
from __future__ import annotations

# code -> (title, what it means for the user, what to do)
CODES: dict[str, tuple[str, str, str]] = {
    "GS-100": ("Server record not saved",
               "Guildizer joined the server but could not save its basic details.",
               "Press Retry. If it repeats, report code GS-100."),
    "GS-200": ("Channels not saved",
               "The server's channel list could not be saved, so channel pickers may be empty.",
               "Press Retry. If it repeats, report code GS-200."),
    "GS-300": ("Roles not saved",
               "The server's role list could not be saved, so role pickers may be empty.",
               "Press Retry. If it repeats, report code GS-300."),
    "GS-401": ("Discord denied access",
               "Discord refused the bot's request. The bot is missing permissions or cannot see the server.",
               "Re-invite the bot with the permissions requested, make sure its role is not blocked, then Retry."),
    "GS-402": ("Bot token rejected",
               "Discord rejected the custom bot's token, usually because it was reset in the Developer Portal.",
               "Open Bots, enter the new token, then Retry."),
    "GS-403": ("Bot not in this server",
               "Discord says this server does not exist for the bot. It was removed or never added.",
               "Add the bot to the server again, then Retry."),
    "GS-404": ("Discord is rate-limiting us",
               "Too many requests in a short time.",
               "Wait a minute and press Retry."),
    "GS-405": ("Discord unreachable",
               "Discord did not answer in time or returned a server error.",
               "Try again in a minute. If it persists, check discordstatus.com."),
    "GS-406": ("Custom bot token unreadable",
               "The stored custom bot token could not be decrypted.",
               "Open Bots and re-enter the bot token, then Retry."),
    "GS-900": ("Unexpected sync error",
               "Something unexpected stopped the sync.",
               "Press Retry. If it repeats, report code GS-900 with the time it happened."),
}


def describe(code: str | None) -> dict:
    title, message, fix = CODES.get(code or "", ("", "", ""))
    return {"title": title, "message": message, "fix": fix}


def classify_rest_error(exc: BaseException) -> str:
    """Map a requests/Discord REST failure to a GS code."""
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    if status == 401:
        return "GS-402"
    if status == 403:
        return "GS-401"
    if status == 404:
        return "GS-403"
    if status == 429:
        return "GS-404"
    if status is not None and status >= 500:
        return "GS-405"
    if type(exc).__name__ in ("Timeout", "ReadTimeout", "ConnectTimeout", "ConnectionError"):
        return "GS-405"
    return "GS-900"
