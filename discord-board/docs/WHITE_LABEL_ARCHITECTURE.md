# Guildizer White-Label (Custom Bot) Architecture Proposal

> Deliverable 3. Answers: can Guildizer replicate Telegizer's two-lineage model
> (official bot + bring-your-own-token custom bots, all powered centrally)?
>
> **Short answer: YES — the architecture ports cleanly, and in some ways works *better*
> on Discord.** There is real market precedent: MEE6 Premium, BotGhost, Double Counter
> and others all sell exactly this "your own branded bot, our engine" model on Discord.

---

## 1. Telegram vs Discord: what changes

| Aspect | Telegram (Telegizer today) | Discord (Guildizer plan) |
|---|---|---|
| Bot identity | Token from @BotFather | Token from a **Discord Application** the user creates in the Developer Portal |
| Receiving events | HTTP long-polling per token (cheap threads) | **Persistent Gateway WebSocket per token** (one `discord.Client` per custom bot) |
| Sending | HTTP per token | HTTP per token (each token gets its **own rate-limit buckets** — a scaling benefit) |
| Commands | Plain `/text` parsing | **Slash commands registered per application** via REST with that bot's token |
| Branding | Name, avatar, description | Name, avatar, banner, About Me — *richer* branding |
| Hard limits | None relevant | Unverified app: **max 100 servers** + privileged intents toggle freely under 100. Verification is per-application and must be done by the *app owner* (the customer). |
| ToS | Fine | Fine — bot hosting on behalf of the application owner is established practice. The customer owns the app; we operate it with their consent. |

The key conceptual difference: a Telegram custom bot is "a token we poll"; a Discord custom
bot is "a full gateway session we maintain". Heavier per bot, but discord.py runs many
clients on one asyncio event loop, so a single worker hosts a fleet.

## 2. Component architecture

```
discord-board/backend/
  bot.py                  # OFFICIAL bot — AutoShardedClient (exists)
  bot_core.py             # NEW: platform logic extracted to bot-agnostic handlers
                          #   handle_message(client, message), handle_member_join(...), etc.
                          #   Official client and custom clients BOTH call into this.
  custom_bot_manager.py   # NEW: fleet runner — one discord.Client per active CustomBot,
                          #   all on one loop; staggered connects; health reporting;
                          #   reload-on-change loop (polls custom_bots dirty flags)
  custom_bots_api.py      # NEW: dashboard CRUD — validate token, store encrypted,
                          #   build invite URL, link/unlink guilds
  crypto.py               # NEW: Fernet encrypt/decrypt for tokens (GUILDIZER_ENCRYPTION_KEY)
  command_registrar.py    # EXTENDED: register the command tree per custom application
```

**The lineage rule (BINDING, inherited from Telegizer):** all behavior lives in shared
modules (`bot_core.py`, `moderation.py`, `leveling.py`, `campaign_runtime.py`, …) keyed by
`guild_id`. The official client and every custom client are thin event adapters over the
same core. **Ship a feature once → every custom bot has it on next deploy.** That is how
updates propagate automatically — same answer as Telegizer.

### Data model

```python
class CustomBot(Base):                      # mirrors Telegizer's CustomBot
    id, owner_user_id -> users.id
    application_id    = BigInteger          # Discord app ID (client_id for invite URL)
    bot_user_id       = BigInteger          # the bot's own Discord user id
    bot_username, bot_avatar
    token_encrypted   = Text                # Fernet at rest, decrypted only in worker
    status            = active|inactive|error
    last_online_at, error_detail
    needs_restart     = Boolean             # dirty flag: API -> worker coordination

class Guild(Base):
    custom_bot_id     = FK(custom_bots.id, nullable=True)   # NEW
    # NULL -> served by the official bot (default)
```

**Per-guild bot resolution** (copies `automation/bot_resolver.py`): every guild is served by
exactly one identity. If a guild has `custom_bot_id` set and that bot is online, the official
bot **ignores** that guild's events (it may even leave, or stay as dormant backup — configurable).
This prevents double-handling, the same problem Telegizer solved.

## 3. User connection flow (dashboard wizard)

1. **Create app** — guided steps: Developer Portal → New Application → Bot tab → Reset Token →
   copy. Screenshots + deep links (`discord.com/developers/applications`).
2. **Paste token** — backend validates immediately:
   - `GET /users/@me` with `Bot <token>` → confirms valid, captures bot user id/username/avatar.
   - `GET /oauth2/applications/@me` → captures `application_id` and **flags** (tells us whether
     Message Content / Members intents are enabled — `GATEWAY_MESSAGE_CONTENT`, `GATEWAY_GUILD_MEMBERS`).
3. **Intent check** — if privileged intents are off, show exact toggle instructions and a
   "Re-check" button (read flags again). Block activation until both are on.
4. **Activate** — token encrypted → row saved → worker picks it up (≤30 s reload loop),
   gateway session starts, slash commands registered on *their* application.
5. **Invite their bot** — generate
   `https://discord.com/oauth2/authorize?client_id=<their_app_id>&scope=bot+applications.commands&permissions=<N>`.
   User invites their own branded bot to their server.
6. **Link** — `on_guild_join` on the custom client sets `guild.custom_bot_id`; official bot
   stands down for that guild. Dashboard shows the guild as "served by @TheirBot".

## 4. Security model

- **Tokens encrypted at rest** (Fernet, key in Railway env — same `encrypt_value` pattern and
  key-rotation re-encrypt callback as Telegizer). Never returned to the frontend after save;
  never logged.
- **Scope discipline**: token grants only what the user's app has; we request a minimal
  permission integer in the invite URL (same baseline as the official bot).
- **Validation on every connect**: 401 → mark `status=error` + surface in dashboard + DM owner
  via official bot; disable after N consecutive failures (no retry storms).
- **Per-customer blast radius**: a leaked/revoked customer token affects only their bot.
  Customers can reset the token in the Dev Portal at any time (kill switch on their side);
  we detect the 401 and prompt for the new token.
- **No cross-tenant leakage**: every handler is keyed by `guild_id`; a custom client only ever
  receives events for guilds it's actually in (Discord guarantees this at the gateway level —
  stronger isolation than Telegram polling).

## 5. Update propagation (the central promise)

| Change type | How it reaches custom bots |
|---|---|
| Behavior/logic (moderation rule, XP tweak, new campaign type) | Automatic on deploy — shared `bot_core` modules, zero per-bot work. |
| New/changed slash command | `command_registrar` re-syncs the tree to **every active custom application** at worker boot (and via dirty flag). Registration is REST per token; a fleet of hundreds syncs in minutes within rate limits. |
| New privileged intent requirement | The only manual customer step: they toggle it in their portal. Dashboard shows a "needs attention" badge driven by the app-flags check. Avoid designing features that need *new* intents where possible. |

## 6. Scaling & operations

- **Fleet worker**: one Railway worker process hosts N `discord.Client` instances on one loop.
  Memory ≈ 20–50 MB per client (guild/member caches) — tune `chunk_guilds_at_startup=False`,
  member cache flags off except where needed. A 1 GB worker comfortably runs ~15–25 custom
  bots; partition by `custom_bot.id % WORKER_COUNT` (env var) to scale horizontally. Start
  simple: one worker, partitioning ready.
- **Identify rate limits**: 1 session start/5 s per token, 1000/day per token — irrelevant per
  bot; stagger fleet boot by ~1–2 s per client to be polite.
- **Sharding**: custom bots serve 1–5 guilds each — single shard forever. Only the official
  bot needs `AutoShardedClient` (already done).
- **Health**: per-client connect/disconnect/error events → `BotHealthEvent` rows → admin Bot
  Health tab (copy of Telegizer's).

## 7. Limitations (honest list)

1. **100-server cap per unverified app** — fine for white-label (each customer's bot serves
   *their* servers), but a customer growing past ~75 servers must complete Discord's
   per-application verification themselves (ID check, takes weeks). Surface this in the UI;
   position it as "your bot, your verification" — Telegizer has no analog but it's rare.
2. **Privileged intents are per-application toggles** — onboarding friction (two switches in
   their portal). Mitigated by the flags-check wizard step.
3. **One extra persistent connection per customer bot** — compute cost scales linearly with
   fleet size; price it into the plan (white-label = Agency-tier feature, exactly like
   Telegizer prices custom bots).
4. **Slash-command sync latency** — global commands can take up to ~1 h to propagate on
   Discord's side after registration (guild-scoped are instant; we use guild-scoped for
   custom commands already, global for the built-in set).
5. **User App / "user-install" modes** — out of scope; we use classic guild-install bots only.

## 8. Recommendation

Build it as **Phase 9** (first parity phase) because the assistant lineage (Phase 17) and the
admin Bot Health/fleet pages depend on its runtime. Implementation order inside the phase:

1. `crypto.py` + `CustomBot` model + `Guild.custom_bot_id` (DB)
2. `custom_bots_api.py` (validate/CRUD/invite URL/flags check)
3. Extract `bot_core.py` from `bot.py` (pure refactor of the official bot — behavior-identical;
   this is the riskiest step, do it with the official bot only and verify before adding the fleet)
4. `custom_bot_manager.py` fleet worker + bot resolution rule
5. `command_registrar` per-application sync
6. Dashboard "My Bots" panel + connect wizard
7. Health events + admin fleet view

Pricing note (product, not code): keep parity with Telegizer — custom bots gated to the top
plan. It is the single strongest differentiator vs MEE6-style competitors at our price point.
