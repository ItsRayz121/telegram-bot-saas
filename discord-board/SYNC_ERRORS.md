# Guildizer sync problems — named codes

When a server's channels, roles or member count don't show up, the dashboard now says
**why**, with a code like `GS-300`. Quote the code when you report it. Codes live in
`backend/sync_errors.py`; keep this file in step with it.

## How to report a problem

1. Open the server in the dashboard. If a yellow banner is showing, press **Retry** once.
2. Still failing? Press **Copy report** on the banner and paste it into your message.
   It contains the code, status, server ID, last sync time and a technical detail line.
3. Add: what you did just before (added the bot, changed permissions, reset the token),
   whether the server uses the official bot or your own custom bot, and the time.

No banner but numbers look wrong? Send the server ID and a screenshot of the header.

## What "sync" does

The bot reads a server's details, channels and roles from Discord and saves them so the
dashboard can show them. It runs when the bot joins a server, when the worker starts, and
when you press the refresh icon (or Retry). Each part (server record, channels, roles) is
saved on its own: if one fails, the others are kept and the server is marked **partial**.

Status values: `ok` (all saved) · `partial` (some parts saved) · `failed` (nothing saved)
· `unknown` (never recorded, e.g. servers synced before this feature).

## Codes

| Code | Name | Typical cause | What to do |
|---|---|---|---|
| GS-100 | Server record not saved | Database rejected the server's basic details | Retry; report if it repeats |
| GS-200 | Channels not saved | Database rejected the channel list | Retry; report if it repeats |
| GS-300 | Roles not saved | Database rejected the role list | Retry; report if it repeats |
| GS-401 | Discord denied access (403) | Bot lacks permissions or cannot see the server | Re-invite with the requested permissions, check the bot's role isn't blocked |
| GS-402 | Bot token rejected (401) | Custom bot token was reset in the Developer Portal | Bots → enter the new token |
| GS-403 | Bot not in this server (404) | Bot was removed or never added | Add the bot again |
| GS-404 | Discord rate-limiting us (429) | Too many requests | Wait a minute, Retry |
| GS-405 | Discord unreachable | Timeout or Discord 5xx | Retry later; check discordstatus.com |
| GS-406 | Custom bot token unreadable | Stored token cannot be decrypted | Re-enter the token |
| GS-900 | Unexpected sync error | Anything not covered above | Retry; report with the time |

## Past incidents

### SYNC-2026-11-04 — server showed 0 members / 0 channels / 0 roles
- **Symptom:** a custom bot with full permissions joined a server; dashboard showed zeros
  and empty channel dropdowns.
- **Cause:** the sync saved the Discord server owner onto the server record. The owner had
  never logged into the dashboard, so the database rejected it (foreign key
  `guilds_owner_id_fkey`) and rolled back the whole sync. The failure was only logged.
- **Fix:** the owner is recorded only if they have a dashboard account (it is filled in
  when they first log in); each sync part is isolated; failures are now visible with a
  code and a Retry button; resync uses the custom bot's own token.
- **Would now show:** nothing, the sync succeeds. A genuine failure shows a GS code.

## For maintainers

- Logs: search the worker logs for `[GS-` (e.g. `[GS-300] sync step sync_roles failed`).
- Stored per server: `guilds.sync_status`, `sync_error_code`, `sync_error_detail`.
- Kill switch: `GUILD_SYNC_SAVEPOINTS=0` on the **Discord Bot (worker)** service restores
  the old all-or-nothing sync (status/codes still recorded).
- Adding a code: add it to `CODES` in `sync_errors.py`, add a row above, and make the
  failing path call `mark_sync(...)` with it.
