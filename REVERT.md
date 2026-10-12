# REVERT — how to undo anything we ship

**Purpose.** Every risky change gets an entry here **before** it ships, with the exact
command to undo it. If something breaks in production at 3am, you should not have to
read code or think — you should be able to open this file, find the change, and run one
line.

**Rule for future work:** any commit that touches money, data deletion, the bot hot
path, or a live plan limit **must** add a section here in the same commit.

## Two ways to undo, and when to use each

| | Speed | Use when |
|---|---|---|
| **Kill switch** (env var) | **~30 seconds**, no deploy, no code | Something is misbehaving *right now*. Always try this first. |
| **Git revert** | ~3 min (rebuild + deploy) | The change is fundamentally wrong and must go. |

**Kill switches beat git reverts.** They are instant and reversible. Reach for the git
revert only when a kill switch cannot fix it.

## Emergency kill switches (no deploy needed)

Set these in **Railway → service → Variables**. The service restarts and picks them up.

| Variable | Set to | Effect |
|---|---|---|
| `RETENTION_ENABLED` | `0` | **Stops all data deletion instantly.** Nothing is pruned or archived. |
| `RETENTION_DRY_RUN` | `1` | Sweep still runs and reports, but **deletes nothing**. This is the default. |
| `CUSTOM_BOT_LIFECYCLE_ENABLED` | `0` | (Telegizer web service and, separately, the Guildizer **Discord Bot (worker)**.) Stops the custom-bot pause/retain/delete lifecycle instantly. Nothing gets warned, paused, or deleted. |
| `CUSTOM_BOT_LIFECYCLE_DRY_RUN` | `1` | Lifecycle tick still runs and logs what it would do, but **sends nothing and pauses/deletes nothing**. This is the default. |
| `CUSTOM_BOT_TRIAL_GATE_ENABLED` | `0` | Restores the old rule: anyone on Pro (including the free 14-day signup trial) can create custom bots again. Only affects NEW bot creation. |
| `MAX_DAILY_AI_SPEND_USD` | any number | Hard ceiling on platform AI spend per day. Set `0` to stop all platform AI. |
| Admin panel flag `group_team_access_enabled` (or env `GROUP_TEAM_ACCESS_ENABLED`) | off / `0` | Locks out everyone who was given access to someone else's group; owners unaffected. Flag applies in ~30s with no deploy; the env var is the fallback and wins. |
| `GROUP_TEAM_DIRECT_INVITES_ENABLED` | `0` | Stops direct Telegram-DM team invitations: no new ones can be sent and pending Accept buttons answer "paused". Access codes and already-accepted access are unaffected. Env var only, needs the ~30s restart. |
| Admin panel flag `bot_slow_mode_enabled` | on | **Re-enables** the old bot-enforced slow mode for groups that still have it saved. It ships OFF and hidden; turning it on does not bring the settings UI back. |
| `BOT_TOKEN_AUTO_OFFLINE` | `0` | Stops a bot with a rejected Telegram token from being flagged offline in the database. It still stops polling after 6 rejections in a row (waits 10s, 1m, 5m, 30m, 12h), but the watchdog may restart it, as before. Env var only, needs the ~30s restart. |
| `MODERATION_PROMO_CONTEXT_GUARD` | `0` | **Discord Bot (worker) only for Guildizer; also Telegizer's web service.** Smart Moderation Layer 2 goes back to removing on any matching promo phrase (no question/warning/link checks). |
| `KNOWLEDGE_SOURCES_ENABLED` / `KNOWLEDGE_SCHEDULED_SYNC_ENABLED` / `KNOWLEDGE_X_SYNC_ENABLED` | `0` | Guildizer (set on both Discord services) as well as Telegizer: stops all source syncing / only scheduled syncs / only X syncs. See the Guildizer phase 2 entry. |
| `RETENTION_XP_DAYS` | e.g. `3650` | Effectively stops XP pruning without disabling the rest. |
| `ENGAGEMENT_PROMO` | `false` | Turns off the promo footer. |
| `USE_CELERY` | `1` | Re-enables Celery dispatch (see `railway.worker.toml` for the full 4 steps). |
| `GUNICORN_MAX_REQUESTS` | `0` | Stops the web worker from recycling itself. |
| `SCHEDULER_SHARED_POOL` | `0` | Scheduler goes back to a fresh thread pool per job per tick. |
| `MALLOC_ARENA_MAX` | `8` | Restores glibc's default per-thread malloc arenas. |
| `DATABASE_URL` (telegram-bot-saas) | `${{Postgres.DATABASE_URL}}` | Reverts Telegizer's DB from Neon back to Railway Postgres. Requires a redeploy (~1-2 min). Loses anything written to Neon after the revert — see the migration entry below before using this on live data. |

---

# Change log — newest first

---

## Guildizer parity, phase 5b — level roles follow the level, long AI answers are not cut off, rank card hardened (Discord)
**Date:** 2026-10-12 · **Risk:** low-medium · **Touches:** live member data (Discord roles are added), the bot hot path (AI answer delivery, `/rank`)
**Commit:** find it with `git log --oneline --grep="guildizer parity phase 5b"`. Ported from Telegizer `12200cc`, `a0d3e97`, `7171105`/`b4c51c7` and `c257f45` (reply sender). Checked and left alone because they already match: the dashboard role column (already derived from level and the current ladder), mobile text/touch-target CSS (one shared stylesheet), and bot deletion (nothing references `custom_bots`).

### What changed
- **Level roles follow the level.** Reward roles used to be granted only at the moment of a message or voice level-up. XP from campaign rewards (approved in the dashboard), invite bonuses and boosts never produced the role, and neither did a reward added to the ladder after members already had the level. A sweep (`level_role_loop`, every 5 minutes on the official bot) now grants any reward a member has reached but does not hold. It checks members changed since the last sweep, plus a **full resync** whenever the ladder is edited or "Sync roles for existing members" is pressed (one page of 100 per server per tick).
- **Grant-only, on purpose.** It never removes a role, so a level lost to a moderation penalty keeps the roles already earned and a role an admin gave by hand is never taken away.
- **AI answers are no longer truncated.** Replies over Discord's limit were cut at 1950 characters (sometimes mid-sentence). They are now split at paragraph, line or sentence boundaries into up to 3 messages, with a "…" marker if an answer is longer than that. Applies to the knowledge-base auto-reply and `/ask`.
- **`/rank` card:** the level is derived from XP (it can no longer disagree with it), long names and huge numbers shrink to fit or end with "…" instead of running off the card, and at most 2 cards render at once; if the renderer is busy for 4 seconds `/rank` answers in plain text.

### To revert
```bash
git revert <the commit found with the grep above>
git push origin main
```

### What a revert does NOT undo
Roles the sweep already granted stay on the members (nothing removes them). Messages already split stay sent. The `roles_resync_at` flag may remain in a server's saved leveling settings (ignored by the old code).

### Kill switch
No variable. To stop the sweep without a deploy, empty the server's role ladder in Levels, or turn Levels off for that server. Reverting the commit removes it everywhere.

### Safety properties (verified, not assumed)
- `discord-board/backend/tests/test_level_roles_and_replies.py` (16 tests): ladder cleaning and cumulative maths, candidate query (this server only, level, recency, cursor), sweep grants only what is missing, never removes a role, incremental window ignores old rows while a full resync covers everyone and then clears its flag, servers with no ladder are skipped, editing the ladder flags one resync and an identical save does not, the manual endpoint (403 for someone else's server), reply splitting (paragraphs kept whole, nothing lost, sentence-end cuts, over-long marked), rank card renders extreme values at the fixed size, text fitting, busy renderer returns None.
- Not verified: real Discord role hierarchy errors (handled by the existing safe-call wrapper, which logs and skips), a real rank card in Discord.
- Known limit: the sweep only sees members the bot has cached (`guild.get_member`); members not in cache are picked up the next time they are active.

---

## Guildizer parity, phase 5 — custom bots pause and are removed after Pro lapses (Discord)
**Date:** 2026-10-12 · **Risk:** high · **Touches:** data deletion (a custom bot row and its token), the bot fleet (a bot is stopped), a plan limit (custom bots need a Pro server)
**Commit:** find it with `git log --oneline --grep="guildizer parity phase 5"`. Ported from Telegizer `31769de`.

### SHIPS IN DRY RUN. Nothing is sent, paused or deleted until you flip it.
`CUSTOM_BOT_LIFECYCLE_DRY_RUN` defaults to **1**: every day the worker logs `[custom_bot_lifecycle][DRY_RUN]` lines saying what it WOULD do and changes nothing. Read a day or two of those lines on the **Discord Bot (worker)** service, check the bots listed really are ones whose owners have no Pro server, then set `CUSTOM_BOT_LIFECYCLE_DRY_RUN=0`. Forgetting this step means the feature silently does nothing (same gotcha as `RETENTION_DRY_RUN`).

### What changed
- Until now, when the owner's Pro ended, the custom bot kept running forever. White-label bots need the owner to manage at least one Pro server to be connected; this enforces the same rule afterwards.
- **Timeline** (days after the lapse is first seen, each stage at most once per bot): notice 0, reminder 5, **pause 7**, retention reminder 17, **delete 22**. Notices go to the owner's dashboard notifications (and web push if opted in). Set `CUSTOM_BOT_WINBACK_PROMO=<code>` (a promo code that already exists in the admin panel) to mention a discount in them; nothing is seeded.
- **Pause** sets the bot to `paused` (the fleet manager stops its Discord client; nothing is deleted). **Delete** removes the custom-bot row and its stored token and moves its servers back to the official Guildizer bot (`custom_bot_id = NULL`). Server settings, members and XP are not touched.
- **Never skips ahead:** one stage per bot per tick, and each stage waits a minimum gap after the previous one (2 / 2 / 5 / 5 days), so re-enabling after a long outage cannot jump from notice to delete.
- **Pro coming back cancels it:** an owner with a Pro server is never touched; regaining Pro clears the lapse and the stages. A PAUSED bot stays paused until the owner presses **Reactivate** (new `POST /api/custom-bots/<id>/reactivate`, refused with 402 unless Pro is active; resuming does not count as creating a new bot). Replacing the token on a paused bot does not start it.
- New columns `custom_bots.lapse_started_at / paused_at / pause_reason` (self-healed) and table `custom_bot_lifecycle_stages` (created at start). My Bots shows "Paused: Pro ended" with a Reactivate button and a heads-up when a lapse has started.
- Checked, no change needed: a rejected Discord token already stops that bot (status `error`, not retried), and nothing has a foreign key to `custom_bots`, so deletes cannot fail the way they did on Telegizer. Guildizer has no signup trial, so the trial gate does not apply.

### To revert
```bash
git revert <the commit found with the grep above>
git push origin main
```
The new columns and table stay (additive, unused by old code).

### What revert restores, and what it does NOT
- ✅ Stops the daily job; bots mid-grace simply stay as they are, as before this feature.
- ⚠️ A revert does NOT undo anything that already happened: bots already **paused** stay paused (a revert does not restart them; use Reactivate or set the row back to `active`), bots already **deleted are gone** (row and encrypted token; the owner must connect the bot again and servers must be re-linked), and notifications already sent were sent.
- ⚠️ With the code reverted, a paused bot has no Reactivate button (the endpoint goes away); set `custom_bots.status='active'` and `needs_restart=true` for it by hand.

### Kill switches (Railway variables on **Discord Bot (worker)**, ~30 s)
| Variable | Set to | Effect |
|---|---|---|
| `CUSTOM_BOT_LIFECYCLE_ENABLED` | `0` | Stops the whole daily tick. Nothing is warned, paused or deleted. Bots already paused stay paused. |
| `CUSTOM_BOT_LIFECYCLE_DRY_RUN` | `1` (default) | Evaluates and logs only. Set `0` to go live. |

### Safety properties (verified, not assumed)
- `discord-board/backend/tests/test_custom_bot_lifecycle.py` (13 tests): the schedule, a 40-day outage cannot jump to delete (each stage waits its gap), defaults are dry-run and enabled, dry run changes nothing and sends nothing, the kill switch stops the tick, a live run walks notice, reminder, pause, retention reminder, delete exactly once each and moves the server back to the official bot, an owner with Pro is never touched, regaining Pro cancels and clears the stages, a paused bot whose owner regains Pro stays paused, Reactivate needs Pro and a paused bot and is owner-only, replacing the token does not unpause.
- Not verified: a real Discord client being stopped by the fleet manager on pause, real web-push delivery, the dashboard in a browser.
- Known limits: entitlement is Guildizer-native Pro (a managed server on a Pro plan), the same rule used when connecting a bot. A Telegizer website subscription only counts inside a browser request, so it is not seen by the daily job; an owner who pays only through Telegizer would be treated as lapsed. Keep dry run on until you have checked who is listed.

---

## Guildizer parity, phase 4 — analytics summaries, digest preview, fuller lists (Discord)
**Date:** 2026-10-12 · **Risk:** low · **Touches:** read-only analytics endpoints, list filters / paging, CSV exports
**Commit:** find it with `git log --oneline --grep="guildizer parity phase 4"`. Ported from Telegizer `3b1078b`. Not ported because Guildizer already had them: UTC timestamps (all Guildizer dates already carry a `Z`) and `/warn` and timeout events in the audit log (they were already logged).

### What changed
- **New read-only endpoints** `/api/guilds/<id>/insights/{members,audit,warnings,ai,digest-preview}`. Summaries are computed on the server over the WHOLE server (not just the rows on screen) and are limited to the one server in the URL. They never write, never send a Discord message and never call AI.
- **Digest preview** builds the text the real digest would post (`digest_runtime.build_stats_text`) and shows it in the Digest tab. Nothing is posted.
- **Members list:** new `offset` paging, `has_warnings` filter, `total_matching`, and per-row `has_active_warnings` / `active_warnings`. Ties on XP / messages / last seen are broken by user id so equal rows keep one order across pages. **Export CSV now exports every matching member** (it walks the list page by page); it used to export only the rows loaded on screen.
- **Audit events:** `days`, `category` and `offset` filters and a `total`.
- **Leaderboard:** returns `total_ranked`; equal XP is ordered by user id (never reorders different XP).
- **Dashboard:** summary strips on Members, Audit log, Warnings and AI activity; "With warnings" switch on Members.

### To revert
```bash
git revert <the commit found with the grep above>
git push origin main
```

### What a revert does NOT undo
Nothing is stored by this change, so there is nothing to restore. CSV files already downloaded stay on people's machines.

### Kill switch
None needed: nothing here sends, deletes or charges anything.

### Safety properties (verified, not assumed)
- `discord-board/backend/tests/test_analytics_insights.py` (9 tests): access (401 / 403), every summary counts only this server, level buckets, active windows, AI vs rule events, warnings per member counted once, AI ledger totals, digest preview text and no "Report Report", members paging / tie order / warnings filter / walking every page, audit filters and total, leaderboard `total_ranked` and stable ties.
- Not verified: the dashboard in a browser.

---

## Guildizer parity, phase 3 — campaign workspace and a guarded review decision (Discord)
**Date:** 2026-10-12 · **Risk:** medium · **Touches:** the review decision path (XP is granted on approve), CSV exports, new read-only campaign endpoints
**Commit:** find it with `git log --oneline --grep="guildizer parity phase 3"`. Ported from Telegizer `e091639` / `ba16c03`.

### What changed
- **Review guard (`campaigns_api.review_submission`).** The review queue and the Manage dialog now send `expected_status`. The decision is applied only if the submission is still in that state, as one atomic UPDATE; otherwise the server answers 409 `STALE_SUBMISSION` and changes nothing, rewards nothing and queues no DM. XP is granted only by the request that wins the update, and never again when an already-approved row is approved once more. Callers that do NOT send `expected_status` behave exactly as before (including the old `verify` verb).
- **New read-only endpoints** under `/api/guilds/<id>/campaign-workspace/`: `overview`, `campaigns` (directory with search / status / type / sort / pages; campaigns without a deadline always sort last), `queue` (cross-campaign review queue with campaign / flagged / member filters), `campaigns/<id>/summary` and `campaigns/<id>/activity`. Every query is limited to the one server in the URL; a campaign or submission id from another server returns 404 or nothing. They never write, post to Discord or call AI.
- **Honest numbers:** "approved" counts submissions (each once) and the number of different people is shown separately; submissions are counted by sent time and review decisions by review time and never mixed; verification source is derived from what is stored (reviewer set = admin; otherwise the campaign's X auto-verify or verification mode).
- **Dashboard:** Campaigns tab gets a "Workspace: overview and review queue" card (needs-attention list, activity chart, running campaigns with participant progress, filterable queue with Approve / Reject).
- **CSV exports** from the Guildizer dashboard (members, leaderboard, campaigns) now neutralise spreadsheet formulas (cells starting with = + - @ are prefixed with an apostrophe; plain numbers are left alone) and are written with a UTF-8 BOM.

### To revert
```bash
git revert <the commit found with the grep above>
git push origin main
```

### What a revert does NOT undo
Submissions approved or rejected, XP already granted, DMs already queued or sent, and files already downloaded stay as they are. Nothing new is stored, so there is nothing to restore.

### Kill switch
None needed for the read-only pages. The guard only ever refuses a decision that would have overwritten someone else's; if it misbehaves, revert the commit.

### Safety properties (verified, not assumed)
- `discord-board/backend/tests/test_campaign_workspace.py` (13 tests): login and server access, honest overview totals and attention items, series kept apart, directory filters / sorts / pages, queue ordering and filters, summary and activity, other server's campaign is 404, guarded approve pays once and a second reviewer gets 409 with nothing changed, guarded reject records reason and queues the DM, re-approve does not pay again, bad `expected_status`, legacy callers unchanged.
- Not verified: the dashboard in a browser, real Discord DMs.

---

## Guildizer parity, phase 2 — knowledge sources: website / X / YouTube, versions, opt-in schedules (Discord)
**Date:** 2026-10-12 · **Risk:** medium-high · **Touches:** money (paid twitterapi.io usage, embedding spend), a new background job on the Discord bot worker, data deletion (removing a source), the AI answer prompt
**Commit:** find it with `git log --oneline --grep="guildizer parity phase 2"`. Ported from Telegizer `ff584f2` / `3d28b51` / `c257f45`. Telegram-channel sources are not ported (no Discord equivalent).

### What changed
- **New Pro feature** in Knowledge base → External sources: add a website, X handle or YouTube channel (max 10 per server). Nothing is fetched until an admin presses **Sync now** or picks **Daily / Every 3 days / Weekly**. Manual is the default; opting in never fetches immediately.
- **New tables** `knowledge_sources`, `knowledge_source_versions`, `knowledge_sync_ledger`, `knowledge_sync_cooldowns` (created at app start) and one additive column `knowledge_documents.source_id` (self-healed). Existing documents are untouched.
- **Safe sync:** fetch, validate, chunk and embed first; only then swap the new version in with ONE commit. A failed fetch, login/bot-check page, empty extract or failed embedding keeps the old version. Unchanged content (hash) is not re-embedded. The last 5 versions keep their text; only the active one is searchable. Restoring a version re-indexes it (costs embeddings, no provider fetch).
- **X sync (twitterapi.io, the existing `TWITTERAPI_IO_KEY`):** shared 24h cooldown per owner + handle claimed atomically before any fetch; page budgets reserved BEFORE the fetch at source (60 / 30 d), server-owner (15 / day) and shared-credential (100 / day) level; at most 3 pages per run; bounded first import (60 posts); incremental stop at the last seen post; resumable cursor; 429 honours Retry-After (capped 48 h); 401/402/403 stop and pause the schedule; 3 failures in a row pause the schedule. A failed attempt still counts.
- **Scheduler:** bot-worker loop `knowledge_sync_loop` every 10 minutes, at most 3 due sources per tick. Pro is re-checked per run; a lapsed plan pushes the source out a day instead of retrying every tick.
- **Answers:** each retrieved chunk is labelled with its source type and the dates actually known (published vs fetched vs uploaded). The prompt treats the context as data, never as instructions, and adds a `CONFLICT` verdict: when sources disagree and cannot be reconciled the bot escalates to the moderators (same path as NO_ANSWER) instead of guessing.
- **Source documents** no longer appear in (or can be edited from) the normal document list; they are managed through their source. They do not count against the 5/50 document cap.
- **Fixed on the way:** a link with no handle in it (e.g. `https://x.com/`) used to be accepted as an X handle.
- Needs `beautifulsoup4` (added to `discord-board/backend/requirements.txt`).

### Not configured (by design)
`YOUTUBE_API_KEY` is not set on the Discord services. A YouTube source shows "No YouTube Data API key is configured on this platform yet" until it is added to **Discord Board (web API)**. Websites and X work now.

### To revert
```bash
git revert <the commit found with the grep above>
git push origin main
```

### What revert restores, and what it does NOT
- ✅ The previous prompt, manual-only knowledge base, and the document list/caps.
- ⚠️ The new tables and the `source_id` column STAY (additive, unused by old code). Nothing is dropped.
- ⚠️ Source documents already indexed stay in `knowledge_documents` and, after a revert, show in the normal document list where they can be deleted. Schedules already saved simply stop running. Version history and ledger rows are not deleted.
- ⚠️ twitterapi.io credits and embedding tokens already spent are not refunded.
- ⚠️ A source removed while this was live is gone together with its stored versions.

### Kill switches (Railway variables, ~30 s, no deploy)
On **both** Discord services (web API for manual syncs, bot worker for schedules):
- `KNOWLEDGE_SCHEDULED_SYNC_ENABLED=0` stops every scheduled run (manual sync still works).
- `KNOWLEDGE_X_SYNC_ENABLED=0` stops all X syncing, manual and scheduled.
- `KNOWLEDGE_SOURCES_ENABLED=0` stops all external source syncing and adding.
- Budgets can be tightened without a deploy: `X_SYNC_COOLDOWN_HOURS`, `X_SYNC_MAX_PAGES_PER_RUN`, `X_SYNC_SOURCE_PAGES_PER_30D`, `X_SYNC_WORKSPACE_PAGES_PER_DAY`, `X_SYNC_CREDENTIAL_PAGES_PER_DAY`, `X_SYNC_MAX_CONSECUTIVE_FAILURES`. The credential figure is only this feature's slice of the shared key; X raid verification uses the same key.

### Safety properties (verified, not assumed)
- `discord-board/backend/tests/test_knowledge_sources.py` (44 tests, provider calls mocked): SSRF guard, X first import / incremental / page cap with resume / deletion reconcile / 429 / bad credentials, first sync, unchanged content not re-embedded, failed fetch and failed embedding keep the old version, version swap and rollback, history bounded to 5, double-click busy, Free server refused, all three kill switches, disable/enable, removal deletes everything, partial flag, shared X cooldown across servers of one owner, atomic claim, budget exhaustion hands the window back, failed attempts still counted, rate limit extends window and schedule, bad credentials and repeated failures pause only the schedule, opt-in never fetches immediately, scheduler runs only due opt-in sources and honours the kill switch and plan lapse, preview never calls a provider, labelled retrieval, disabled sources excluded, prompt contract, HTTP isolation between servers.
- Known limits: the scheduled run honours Guildizer's own Pro (server or account), not a Telegizer website token forwarded in a browser request; X edits/deletions are reconciled only inside the newest page; a second server of the same owner pointing at the same X handle waits for the same cooldown window and has no text until its own first sync.
- Not verified: a real twitterapi.io account (field names follow its documentation and the Telegizer connector), real Postgres locking (the advisory lock only runs on Postgres), a real Discord server, the dashboard in a browser.

---

## Guildizer parity, phase 1 — fewer wrongful removals in Smart Moderation (Discord)
**Date:** 2026-10-12 · **Risk:** medium · **Touches:** bot hot path (Discord `on_message`: Smart Moderation Layers 2 and 3)
**Commit:** find it with `git log --oneline --grep="guildizer parity phase 1"`. Ported from Telegizer `c257f45`. Only `discord-board/` and the Guildizer Moderation tab changed; Telegizer is untouched.

### What changed
- **Layer 2 (rule-based promo detection).** Phrases are split into strong solicitation ("DM me", "guaranteed profit", "link in bio") that always match, and topic phrases ("promo code", "referral", "crypto signals") that now need an untrusted link and must not be a question or a scam warning. A call to action ("use my code", "sign up using") plus an untrusted link still matches even when phrased as a warning. Links on the guild's external-links whitelist never count. Before, a bare "referral" or "what is the promo code?" was removed.
- **Layer 3 (AI check), prompt v2.** The message and the replied-to text are wrapped as untrusted data; "when in doubt answer ok". Verdicts are now ok / promotional / irrelevant / uncertain / unavailable. Only a confident promotional (or irrelevant, when a topic is set) verdict removes anything. A low-confidence removal becomes `uncertain` and a malformed or missing answer becomes `unavailable`: both are logged and never act.
- **New per-guild setting** `automod.smart_mod.ai_mode`: `enforce` (default, unchanged behaviour for confident verdicts) or `observe` (log what would be removed, never act). Dashboard: Moderation → Smart Moderation → "AI verdict handling".
- **The live config is re-read after the AI call.** If Smart Moderation was switched off, the member was trusted, review mode was turned on, or the member became staff while the model was running, nothing is removed. A config that cannot be re-read removes nothing.
- **Duplicate-event guard.** A re-delivered gateway event for the same message is skipped, so it cannot warn, punish or award XP twice (in-process, 10-minute memory, bounded).
- **Audit.** Protection Activity detail now carries the rule that fired (`promo_cta`, `[L3:ai_promotional v2026-10-v2]`, `[L3:promotional:review]`, ...).

### What changes for existing guilds
Saved settings are kept as they are; nothing is migrated and `ai_mode` defaults to `enforce`. Moderation DECISIONS do change: some messages that were removed before are now allowed (questions and scam warnings that mention a promo phrase, bare "referral"), and `earn/make N` without a `$` and a period no longer matches on its own.

### To revert
```bash
git revert <the commit found with the grep above>
git push origin main
```

### What revert restores, and what it does NOT
- ✅ The previous Layer 2 phrase matching, one-word Layer 3 prompt, and no duplicate guard.
- ⚠️ Messages deleted, warnings issued and members timed out or banned while this was live are NOT restored.
- ⚠️ Messages this let through, that you would have removed, stay posted.
- ⚠️ `ai_mode` values already saved stay in the guild's settings (ignored by the old code).

### Kill switch
`MODERATION_PROMO_CONTEXT_GUARD=0` on the **Discord Bot (worker)** service (~30 s, no deploy): Layer 2 goes back to removing on any matching phrase. Layer 3 review mode is the per-guild "AI verdict handling" setting.

### Safety properties (verified, not assumed)
- `discord-board/backend/tests/test_moderation_accuracy.py` (37 tests): labelled promo matrix (removals and allowed cases), whitelist, referral exemption, kill switch, classifier output parsing, trusted ids as strings, config re-validation, duplicate events, and the bot flow with a fake message (confident removal, uncertain / unavailable / ok never act, review mode, setting changed mid-call, member promoted mid-call, irrelevant needs a topic).
- Not verified: a real Discord server, a real AI provider, the dashboard in a browser.

---

## `5517a8e` — Bots with a rejected Telegram token stop retrying and go offline
**Date:** 2026-10-12 · **Risk:** low · **Touches:** bot hot path (custom-bot polling loop)

### What changed
- A custom bot whose token Telegram rejects (revoked, regenerated, typo) is retried after 10 s, 1 min,
  5 min, 30 min and finally 12 h (6 rejections in a row in all), then stopped and set offline: `bots.is_active = false`, and its
  `custom_bots` twin set to `error`. The boot-time restart and the watchdog skip inactive bots, so it no
  longer retries forever (before, it burned 10 attempts, died, and the watchdog restarted it).
- Bug fix behind it: the old "invalid token, stop permanently" branch never ran, because it imported
  `telegram.error.Unauthorized`, which does not exist in python-telegram-bot 21. That import failure also
  disabled the `Conflict` (two pollers) handling. Both now work.
- Only *consecutive* rejections count; any other error resets the counter.

### To revert
```bash
git revert 5517a8e
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Restores the previous polling loop (the broken invalid-token branch and endless watchdog restarts).
- ⚠️ Bots already taken offline stay offline: their `is_active` / twin `status` are database values, not
  code. Re-enable one with the bot's on/off toggle in the dashboard (or `UPDATE bots SET is_active = true`
  and set the `custom_bots` row back to `active`).
- ⚠️ If an owner's token was rejected only transiently, nothing is lost; they just toggle the bot back on.

### Kill switch (if any)
`BOT_TOKEN_AUTO_OFFLINE=0` in Railway: bots are no longer flagged offline in the database (the 6-attempt
stop in the poller stays). A deploy or restart resets the schedule, and a bot waiting out the 12 h step
shows as active until the final attempt.

### Safety properties (verified, not assumed)
- `telegram.error.Unauthorized` is absent and `InvalidToken` present in python-telegram-bot 21.3.
- Tests (`backend/tests/test_bot_token_guard.py`): waits 10s/1m/5m/30m/12h then goes offline on the 6th rejection, stop during a wait exits, a transient blip does not
  disable the bot, only consecutive rejections count, kill switch, Conflict retried quietly.
- Not verified: behaviour against the real Telegram API for a revoked token in production.

---

## `8e11569`..`3db03f2` — Direct team invites: invite a Telegram admin, they Accept/Reject in the bot DM (official AND custom bots)
**Date:** 2026-10-12 · **Risk:** medium · **Touches:** bot hot path (new callback handler), live plan limit (10 team members per group), account creation

### What changed
- Owner can pick an admin of the group (Settings → Team Access → "Invite a Telegram admin") and the official bot DMs them Accept / Reject buttons. Accepting creates the same per-group grant an access code does; it still counts toward the 10-member limit.
- Accepting a DM invite auto-creates a Telegram-only Telegizer account if that Telegram user has none (same shape the Mini App creates), then they open the group from the Mini App or by signing in with Telegram.
- New columns on `telegram_group_invites`: `invitee_telegram_id`, `invitee_name`, `declined_at` (added by `migrate.py`, all nullable). Direct invites never expose or accept a code.
- Works for groups managed by the official bot and by the owner's custom bots (both systems). The invitation is sent by, and the Accept/Reject press is handled by, the bot that manages the group. New callback handler `gti:` in the official bot and in custom bots (`BotInstance.handle_callback`).
- Rule enforced in code: a bot only DMs someone who already pressed Start on that same bot. Custom bots now record Start presses in a new table `custom_bot_started` (written by the custom bots' /start handler, in `bot_manager.py`). People who started a custom bot before this release show as "not started" until they press Start again.

### To revert
```bash
git revert --no-edit 8e11569^..3db03f2
git push origin main
```
(Three commits: the feature, the custom-bot extension, one small fix. Reverting the range removes all of it.)

### What revert restores, and what it does NOT
- ✅ Access codes only; no DM invitations, no Accept/Reject handler.
- ⚠️ Invitation DMs already sent stay in people's Telegram (their buttons then do nothing).
- ⚠️ Grants already accepted STAY (they are normal `telegram_group_access` rows). Remove a person from the group's Team Access list to end it.
- ⚠️ Telegizer accounts auto-created on Accept are NOT deleted.
- ⚠️ The three new columns and the `custom_bot_started` table stay in the database (harmless).

### Kill switch (if any)
`GROUP_TEAM_DIRECT_INVITES_ENABLED=0` in Railway (backend and bot service). Also off when `GROUP_TEAM_ACCESS_ENABLED=0` / the admin flag `group_team_access_enabled` is off.

### Safety properties (verified, not assumed)
- 13 SQLite tests (`backend/tests/test_group_direct_invites.py`): official, custom-bot and legacy-bot groups each use their own bot token and started-list; nobody who has not started the bot is messaged; banned accounts cannot accept; the owner is only notified through a bot they started; Accept only by the invited Telegram id; refused if they stopped being a group admin; one use; Reject/expiry/kill switch grant nothing; non-admins, people who never started the bot, duplicates and custom-bot groups are refused; a direct invite's code cannot be redeemed.
- Existing Team Access tests still pass (34 passed across both files).
- Not tested: the real Telegram DM and button press (faked at the API call), and the frontend panel in a browser.

---

## Group batch release — scheduled-message editing, Team Access in Settings, back-navigation, slow mode retired, wider tables, member charts, message previews + AI samples
**Date:** 2026-10-11 · **Risk:** medium-high · **Touches:** the bot hot path (slow mode gated off), scheduled-message data (edit), paid AI calls (preview samples), group access UI, Discord campaign DM text builder
**Commit:** `8a272e4` (also findable with `git log --oneline --grep="^feat(groups): previews"`). Deployed to Railway `telegram-bot-saas` as `5b56b19d-7ea5-4fc9-ac23-8818de565ef8` (SUCCESS, 2026-10-11). **Pre-release state:** `699ce62` (Railway `telegram-bot-saas` deployment `d5538ae9-77e4-4cb3-99f8-d79b1a4ec318`, SUCCESS).

### What changed (each bullet is independent; see "Partial undo")
- **Scheduled messages can be edited** (`PUT .../scheduled-messages/<id>`, both group types): one row update under a row lock, so there is never an old and a new job. A *changed* send time must be in the future; a sent one-off is refused (409). Editing only the text never re-converts the stored time. **Also fixed:** official-bot schedules now honour the timezone the form sends (previously the typed time was stored as UTC). Existing rows are NOT rewritten. Read-only review helpers: `needs_tz_review()`, the "Check time" chip, and `GET /api/admin/schedules/tz-review`.
- **Slow mode retired.** `check_slow_mode` (custom bots) and the slow-mode block in `official_bot.py` run only if platform flag `bot_slow_mode_enabled` is on. It ships OFF. Saved settings are kept untouched; the Moderation card is now a "Telegram Slow Mode" setup guide. Telegram's own slow mode is unaffected.
- **Team Access** lives in each group's Settings → Team Access (the My Groups "Team" button links there). Whole-bot sharing stays on My Groups. Backend authorization is unchanged.
- **Back navigation:** the group page keeps tab, sub-tab and Members/Leaderboard filters in the URL; CRM Back returns to where you came from.
- **Layout:** analytics/automation tabs use full width; Members, Leaderboard, AI Activity and Campaign tables use fixed column widths; campaign Summary is four KPI cards over two 50/50 rows.
- **Admin Users charts:** new read-only `GET /api/admin/managed-members-series`; "Members gained per day" is now signed "Net member change"; separate axes for Managed and Verified.
- **Previews:** local rendering (lazy-loaded) for scheduled messages, welcome/DM, auto-reply, forwarding, verification, moderation notices, polls, campaign reminder/approved/rejected notices (Telegram) and Discord welcome/DM/leave, level-up, auto-response, scheduled posts, campaign announcement. Three **AI sample** endpoints make one real provider call per click: `POST /api/telegram-groups/<id>/ai-reply-sample`, `POST /api/bots/<bot>/groups/<id>/ai-reply-sample`, `POST /api/hub/bots/<id>/ai-reply-sample`. They write nothing (no AI-activity row, memory, knowledge, XP or analytics) and send nothing.
- **Discord service** (`discord-board/backend`): new `POST /api/guilds/<id>/campaigns/preview`; the DM wording moved into `campaign_views.review_notice_text()` (same text).

### Kill switches (no deploy)
- AI samples: Admin-panel flag `ai_features_enabled` off (all three endpoints answer 503), or `MAX_DAILY_AI_SPEND_USD=0`.
- Slow mode: already off; flag `bot_slow_mode_enabled` re-enables the OLD behaviour (the settings UI does not come back).
- Team Access: unchanged (`GROUP_TEAM_ACCESS_ENABLED` / flag `group_team_access_enabled`). It is currently `1` in production.

### To revert
```bash
git revert 8a272e4
git push origin main
```
Railway redeploys the bot/API; Vercel redeploys the dashboard; the Discord web API and worker redeploy because their folder changed.

### Partial undo
- Only previews: remove the `<PreviewPanel>` blocks (everything lives in `frontend/src/components/preview/`; nothing else depends on it).
- Only the official-schedule timezone fix: in `telegram_groups.py` `create_official_scheduled_message`, replace `to_naive_utc(send_at_raw, tz_name)` with `datetime.fromisoformat(send_at_raw.replace("Z", "+00:00")).replace(tzinfo=None)`.

### What revert restores, and what it does NOT
- ✅ Old slow-mode behaviour (only for groups whose saved setting is still enabled), old tab/back behaviour, old tables and charts.
- ⚠️ Edited scheduled messages keep their edits. Schedules created while the timezone fix was live keep the (correct) UTC times they were saved with.
- ⚠️ Paid AI sample calls already made are not refunded; samples are never stored.
- ⚠️ Access codes created/redeemed and people already given access stay.

### Known deploy noise
**Update 2026-10-12: resolved.** `Postgres-Discord` was redeployed, both Discord services redeployed successfully from this commit, `guild-api.telegizer.com/health` answers healthy and the bot is online in 3 servers. The text below is the state at the time of writing.

The Railway services `Discord Board (web API)` and `Discord Bot (worker)` have had no successful deployment since July (last real deploy of the web API: 2026-07-17; `Postgres-Discord` has no deployment, so `postgres-u73i.railway.internal` does not resolve and `guild-api.telegizer.com` answers "Application not found"). This commit touched `discord-board/`, so both tried to build and failed with that DNS error. Nothing was taken down by this release; any future commit touching `discord-board/` will do the same until that database service is brought back.

### Safety properties (verified, not assumed)
- Backend: `backend/tests/` (50 tests incl. `test_group_features_batch.py`) and `discord-board/backend/tests/test_campaign_preview.py` (4). They cover: schedule edit (same row, no send, past time rejected, sent refused, due/recurring/legacy-tz cases, failed save changes nothing); team access (single-use, expiry, revoke, cross-group isolation, viewer 403, kill switch 503); AI samples write nothing and refuse viewers/strangers/duplicate clicks; the OFFICIAL async automod handler with the cooldown flag off (no delete/restrict/notice; an email-rule violation still fires) plus an ON-control; the custom-bot path; member-series maths.
- Frontend: Jest `previewText.test.js` (formats, limits, HTML/Markdown parsing; the welcome template is compared with Python `str.format` through one shared fixture) and `MessagePreview.test.js` (nothing clickable, closed panel does no work).
- Browser audit on an isolated local database (see the release notes): routes, roles, Back/Forward, schedule edit/cancel, previews, charts, 1366 layouts and 390 px emulation.
- **Not verified:** real Telegram/Discord/AI-provider delivery; Discord dashboard screens in a browser (needs Discord OAuth); a real phone.

---

## `e091639` — Campaign workspace: overview, directory, review queue, campaign pages, safer review + exports
**Date:** 2026-10-10 · **Risk:** medium · **Touches:** the review decision path (XP is granted on approve), CSV exports, new read-only campaign endpoints, campaign pages

### What changed
- New read-only endpoints under `/engagement/` (overview, directory, review queue, per-campaign summary/activity, message preview). Every query is limited to the one group in the URL; a campaign or submission id from another group returns 404.
- **Review guard (`engagement.review_submission`)**: the queue and the campaign page now send `expected_status`. The change is applied only if the submission is still in that state (one atomic UPDATE); otherwise the server answers 409 `STALE_SUBMISSION` and changes nothing, rewards nothing and notifies nobody. Callers that do not send `expected_status` behave exactly as before.
- Submissions CSV: formula-injection neutralised, ids written as text (leading zeros kept), UTF-8 BOM, UTC timestamps, descriptive file name, optional `status` / `from` / `to` filters.
- Campaigns moved from dialogs to pages (`/groups/<id>/campaigns...`). The old forms are reused unchanged; the wizard now has 4 steps with an explicit "Save as draft" / "Publish now" instead of an "Activate now" switch.

### Kill switch
None needed for the read-only pages. If reviewing misbehaves, the old behaviour is available instantly by reverting the commit; there is no flag.

### To revert
```bash
git revert <sha>
```

### What a revert does NOT undo
- Submissions approved or rejected, XP already granted, DMs already sent to members, and group posts already published stay as they are.
- Drafts or campaigns created through the new pages remain.
- CSV files already downloaded stay on people's machines.

---

## `3b1078b` — Analytics redesign: member/audit/warning/AI summaries, digest preview, profile links
**Date:** 2026-10-10 · **Risk:** low-medium · **Touches:** read-only analytics endpoints, scheduled digest text builder, report wording, member/audit list filters, CSV exports

### What changed
- New read-only endpoints (`/insights/...` for official and custom-bot groups). They never write, send Telegram messages or call AI.
- `official_bot.py`: the scheduled digest text was moved out of `_send_official_digest` into `_build_official_digest_text` (same text, same sending). If a scheduled digest ever looks wrong, this is the place.
- Report wording: the heading used to read "Weekly Report Report"; it now reads "Weekly Report".
- Official Audit Log now also lists `/warn` (`mod_warn`) and temp-mute events, which the bot wrote but the log hid.
- Leaderboards use `id` as a tie-break (never changes order between different XP) and now return `total_ranked`.
- Member lists gained `has_active_warnings` and `active_warnings`; audit lists gained `days` / `action_type`.
- Members CSV export now exports every matching member (was only the 20 on screen).
- UTC timestamps without a zone suffix are now read as UTC (they were shifted by the viewer's offset).

### Kill switch
None needed - nothing here sends, deletes or charges anything.

### To revert
```bash
git revert <sha>
```

### What a revert does NOT undo
Nothing is written by this change, so there is nothing stored to restore. Previously exported CSV files stay on people's machines.

---

## `fd8d8c4` — fixes from the browser audit: shared people follow the owner's plan in the UI, view-only banner, mobile/desktop layout
**Date:** 2026-10-10 · **Risk:** low · **Touches:** plan gating shown in the group page (display only; the server already enforced the owner's plan)

### What changed
- **Plan gate bug (disconnection):** on a group shared with you, the Forwarding and Workflows tabs said "requires Pro" because the page checked the signed-in person's own plan. The server already used the group owner's plan, so a free manager of a Pro owner's group was blocked in the UI but allowed by the API. The settings endpoints now return `owner_plan`, and the page (and its embedded forwarding/workflow panels, and the "enable a Pro section" check) uses the owner's plan for shared groups. Owners are unaffected.
- **View-only banner:** the group pages now return `access_role`; a Viewer sees a clear "view-only" banner and the Save button is disabled. (The server already refused their writes with a 403.)
- **Back button:** a shared person on an older custom-bot group went "back" to a bot page they cannot open; it now goes to My Groups.
- **Layout bugs found in the browser:** (1) with the sidebar open, the four buttons on a group card overlapped (Settings ran into Analytics) - the row now wraps; (2) on a phone the My Groups toolbar was crushed into narrow columns - it now wraps onto lines; (3) the "Shared" chip squeezed group titles - it now sits under the ID; (4) the role picker in the Team dialog now clearly shows the selected role.
- Shared older-custom-bot cards now show the bot's name instead of a generic "Custom Bot". The "Share a whole bot" list no longer offers an empty official bot.

### To revert
```bash
git revert <sha>
git push origin main
```

### What revert restores, and what it does NOT
- ✅ The previous screens (including the overlapping buttons and the "requires Pro" wall for shared people).
- ⚠️ Nothing is stored or deleted by this change, so there is nothing to recover. Access and plan limits on the server are unchanged by it.

### Kill switch (if any)
None needed (display and layout only). The sharing kill switch (`group_team_access_enabled`) is unchanged.

### Safety properties (verified, not assumed)
- Checked in real Chrome against a local copy of the app (seeded owner / manager / viewer / admin): owner, manager and viewer My Groups pages; the Share-a-bot, Team and Join dialogs; the Join flow with a pasted code (a stray space and dash were accepted); the legacy custom-bot settings page as a view-only person; Forwarding and Workflows as a free person on a Pro owner's group (now open); the admin Configuration flag row. Phone width was checked in a 390px frame.
- All backend suites re-run (48 + 74 + 57 + the first 27), all passing.

---

## `41e558c` — share a whole bot in one step (every group a bot manages, now and later) + two fixes from the audit
**Date:** 2026-10-10 · **Risk:** medium · **Touches:** access control (who can open a group and everything tied to it)

### What changed
- New tables `telegram_bot_access` and `telegram_bot_invites` (created automatically on boot). An owner can give someone access to **every group one bot manages** with one access code: the official Telegizer bot, or any custom bot (matched by bot username, so the old `Bot` records and the new `CustomBot` records of the same bot count as one). Manager = full control, Viewer = read-only.
- It is **dynamic**: a group linked to that bot later is covered with no new grant, and a group unlinked/disconnected, or handed to another owner, drops out by itself. A grant only ever covers groups owned by the person who issued it, so another owner who happens to use the same bot username is never exposed.
- A **per-group grant overrides** the whole-bot role for that one group, in both directions (e.g. bot-wide Manager but Viewer on one group).
- UI: **Share a whole bot** on My Groups (pick the bot, get a code); the group Team dialog shows who also has access through the whole bot. The same **Join with access code** box accepts both kinds of code and says "All groups of @bot (N groups)".
- All access decisions now go through one function (`grant_for`), used by the group routes, the older custom-bot routes, the central guard, and the forwarding / workflow / link / task / note sharing.
- Fixes found in the audit: a Viewer could not **leave** an official group because the central guard blocked the leave call; and an access code could in theory be **redeemed twice** by two simultaneous requests (now claimed atomically).

### To revert
```bash
git revert <sha>
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Back to per-group sharing only (access codes for single groups still work).
- ⚠️ The two new tables and their rows stay (harmless, unused after a revert). People who only had whole-bot access lose it; their per-group access is unaffected.
- ⚠️ A revert also brings back the two audit bugs (viewer cannot leave an official group; a code can race-redeem).
- ⚠️ Anything a whole-bot manager already changed is not undone.

### Kill switch (if any)
Same flag as before: **Admin panel -> Configuration -> Feature flags -> `group_team_access_enabled` -> off** (about 30 seconds, no deploy). It also cuts off every whole-bot grant. Owners are unaffected. Fallback: env `GROUP_TEAM_ACCESS_ENABLED=0`.

### Safety properties (verified, not assumed)
- Real Flask app on SQLite, 57 new checks (scopes across both bot systems, dynamic add/remove, per-group overrides in both directions, cross-owner same-username isolation, resources following bot grants, atomic single-use codes, leave, owner edit/remove, kill switch, ownership change) plus the earlier 48 + 75 suites re-run, all passing.
- Not tested: the new buttons in a real browser (the production build compiles).
- Not covered (owner-only on purpose): Assistant Hub groups, personal reminders/meetings/knowledge, the directory listing, bots themselves, billing, the Telegram mini app.

---

## `4cec4d9` — shared access now covers everything tied to the group (forwarding, workflows, smart links, tasks, notes)
**Date:** 2026-10-10 · **Risk:** medium · **Touches:** access control (who can read/change forwarding rules, workflows, group links, tasks, notes); plan limits (shared rules/workflows count against the owner)

### What changed
- A person given access to ONE group now also reaches the things tied to that group: its **forwarding rules**, **automation workflows**, **group smart links**, and **tasks and notes** tagged to it. Manager = change them, Viewer = read only.
- Strictly that group only. A forwarding rule or workflow is reachable only if EVERY chat it touches (source and every destination) was shared with that person by the same owner. Rules/workflows that touch the owner's other groups, and account-wide workflows, stay owner-only and invisible.
- Things a manager creates belong to the group OWNER (owner_user_id) and count against the owner's plan limits; the manager's own plan never matters.
- Tasks/notes can only be tagged to a group the person owns or manages. Previously anyone could tag any group id; now tagging another owner's group is refused (403), so nobody can inject tasks into a group they have no access to.
- Unlinking a group (or disconnecting it from a custom bot) now deletes its team grants and open access codes, so a later relink never revives old access.
- Still owner-only on purpose: Assistant Hub groups, personal reminders/meetings/knowledge, the directory listing, bots, billing, the Telegram mini app.

### To revert
```bash
git revert <sha>
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Shared people go back to group settings/moderation/analytics only (the first access-code version); rules, workflows, links, tasks and notes are owner-only again.
- ⚠️ Rules, workflows, links, tasks and notes a manager already created stay in the database under the owner's name; they are not removed.
- ⚠️ Grants/codes deleted by an unlink while this was live do not come back.
- ⚠️ Anything a forwarding rule or workflow already forwarded/posted is not undone.

### Kill switch (if any)
Same one as before: **Admin panel -> Configuration -> Feature flags -> `group_team_access_enabled` -> off** (about 30 seconds, no deploy). It cuts off all of the above at once, because every one of these checks goes through the same grants. Owners are unaffected. Fallback: env `GROUP_TEAM_ACCESS_ENABLED=0`.

### Safety properties (verified, not assumed)
- Real Flask app on SQLite (74 new checks + the earlier 48 still pass). A manager of groups A+B sees only forwarding rules/workflows/links/tasks/notes fully inside A+B, never ones touching the owner's private groups; cannot create, edit, toggle, delete or re-point anything into a group that was not shared (404); cannot make an account-wide workflow; viewers get 403 on every write but can read; a stranger cannot tag or inject into a group.
- Shared rules count against the owner's free limit (403 LIMIT_REACHED) and work after the owner upgrades.
- Unlink and disconnect remove the grants (checked in the database).
- Not tested: live Telegram delivery of a shared person's rule/workflow (the delivery code is unchanged; only who may create/edit it changed).

---

## `8c8627c` — per-group team access (Telegram groups: official AND custom-bot), shared by access code
**Date:** 2026-10-10 · **Risk:** medium · **Touches:** access control on every per-group dashboard route; plan gating for shared groups

### What changed
- New tables `telegram_group_access` and `telegram_group_invites` (created automatically on boot).
- The group owner creates a one-use **access code** (24 letters/digits, expires in 7 days) with a role: **manager** (read + write) or **viewer** (read-only). The friend pastes it under **My Groups → Join with access code**. Max 10 people per group.
- One shared check, `backend/group_access.py`, now decides access for: official-bot groups (`telegram_groups`, `official_settings`, `crm`, `tasks`, `custom_commands`) AND the older custom-bot routes `/api/bots/<bot_id>/groups/<group_id>/...` (`settings`, `polls`, `knowledge`, `webhooks`, `invites`, `digest`, `analytics`, `custom_bot_crm`, `bot_group_commands`, `api_keys`). Owners behave exactly as before.
- Shared people see only the groups they were given. Unlinking/disconnecting a group, AI API keys, the bot itself and managing the team stay owner-only. Viewers get 403 on any write.
- A grant only counts while the person who issued it still owns the group; a code or grant from a previous owner stops working.
- Paid features and plan limits on a shared group follow the **group owner's** plan, not the shared person's.
- Bonus fix: the escalation list/update routes used a column that does not exist on `Bot` (`owner_user_id`) and returned 500 for everyone; they now work.

### To revert
```bash
git revert <sha>
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Only the owner can open a group again; the Team button, join dialog and new endpoints disappear.
- ⚠️ The two new tables and their rows stay in the database (harmless and unused after a revert).
- ⚠️ Anything a shared manager already changed (settings, moderation, sent messages) is NOT undone.
- ⚠️ Access codes already handed out stop working but are not recalled from wherever they were pasted.
- ⚠️ A revert also puts the escalation routes back to returning 500.

### Kill switch (if any)
**Admin panel → Configuration → Feature flags → `group_team_access_enabled` → off.** Applies within ~30 seconds, no deploy. Every shared person is locked out, the shared groups vanish from their list, new codes and redemptions return 503, owners are unaffected. Turn it back on and the same grants work again. Emergency fallback if the admin panel is unreachable: set `GROUP_TEAM_ACCESS_ENABLED=0` in Railway (this wins over the flag).

### Safety properties (verified, not assumed)
- Run on the real Flask app (SQLite) with owner / manager / viewer / stranger / second owner: a stranger gets 404; a manager reads and edits the shared group but gets 404 on the owner's other groups and on another owner's bot that sits in the same chat; manager gets 403 on unlink, API keys and team management; viewer gets 403 on every write, in both official and legacy routes; codes are single use and reject garbage; ownership change kills old grants and old codes; the DB flag locks out managers (official and legacy), hides shared groups, refuses new codes, and leaves owners untouched; turning it back on restores access.
- A Pro friend on a free owner's group is refused paid features (plan follows the owner).
- Not covered (stay owner-only): automations, forwarding, meetings, workspace reminders, Assistant Hub groups, the Telegram mini app.

---

## `61b1e92` — per-group team access, first version (official-bot groups only, invite link)
**Date:** 2026-10-10 · **Risk:** medium · **Touches:** access control on the group dashboard API (who may read/change a group)

### What changed
- New tables `telegram_group_access` and `telegram_group_invites` (created automatically on boot).
- The group owner can create a one-use, 7-day invite link with a role: **manager** (read + write) or **viewer** (read-only). Max 10 people per group.
- One shared check, `backend/group_access.py`, now decides group access for the Telegram group API, official group settings, CRM and task extraction. Owners behave exactly as before.
- Shared people only see the groups they were invited to. Unlinking a group, the AI API key endpoints and managing the team stay owner-only. Viewers get 403 on any write.
- Frontend: **Team** button on each group card, `/group-team/join/:code` page, "Shared" chip, and no Unlink button for shared people.

### To revert
```bash
git revert <sha>
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Only the owner can open a group again; the new endpoints, Team button and join page disappear.
- ⚠️ The two new tables and any rows in them stay in the database (harmless and unused after a revert).
- ⚠️ Anything a shared manager already changed (settings, moderation, sent messages) is NOT undone.
- ⚠️ Invite links already handed out stop working but are not recalled from wherever they were pasted.

### Kill switch (if any)
Set `GROUP_TEAM_ACCESS_ENABLED=0` in Railway → backend service → Variables. Every shared person is locked out on the next request, new invites and redemptions return 503, and owners are unaffected. Set it back to `1` (or remove it) and the same access rows work again. No deploy.

### Safety properties (verified, not assumed)
- Tested on the real Flask app (SQLite, 4 users): a stranger gets 404; a manager can read/edit the shared group but gets 404 on the owner's other group; manager gets 403 on unlink, API key and team management; viewer gets 403 on PUT/POST; invite codes are single-use; role changes and removal take effect immediately; the kill switch locks out the manager while the owner is unaffected, and turning it back on restores access.
- Not tested: custom-bot (legacy `Group`) groups are not covered by this feature; other routes that still check `owner_user_id` directly (automations, forwarding, meetings, workspace) remain owner-only.

---

## `062a455` — audit fixes: bot tokens out of logs, meeting-link capture, admin bot AI usage, webhook 413
**Date:** 2026-10-10 · **Risk:** low · **Touches:** bot hot path (official message handler), logging

### What changed
- `app.py`: httpx/httpcore loggers set to WARNING. They logged every Telegram API URL at INFO, and those URLs contain the full bot token, so tokens were sitting in Railway logs.
- `app.py`: `abort` was used but never imported, so an oversized webhook body raised a 500 instead of a clean 413.
- `official_bot.py`: meeting-link capture referenced an undefined `group_title`, so every detected Zoom/Meet/Teams link silently failed to save. Now uses the group's title.
- `routes/admin.py`: admin custom-bot detail read an undefined `groups`, so "AI usage" was always empty. Now uses the bot's connected groups.

### To revert
```bash
git revert 062a455
git push origin main
```

### What revert restores, and what it does NOT
- Restores the four bugs above (including tokens in logs). No schema or data change.
- Does NOT remove tokens already written to past Railway logs; rotate any bot token you consider exposed.

### Kill switch (if any)
- None; each is a straight bug fix.

---

## `12200cc` — member role follows level everywhere (official bot never set it)
**Date:** 2026-10-10 · **Risk:** low-medium · **Touches:** bot hot path (XP award), settings save

### What changed
- One shared rule `role_for_level` / `resync_roles` in `bot_features/levels.py` (highest configured level threshold reached wins; "member" if none).
- Official bot never wrote `role` on XP gain, so the dashboard showed a stale role. It now sets it on message XP, XP penalty and campaign XP rewards. Custom bot `add_xp` / `apply_xp_penalty` use the same helper (behaviour unchanged).
- Saving `levels.roles` in group settings (official and custom) now re-derives every member's role from their stored level with one bulk UPDATE per tier, so editing the ladder takes effect for existing members.
- Members list (official and custom dashboards) now shows the role derived from current level + current ladder, so rows saved before this fix are not stale. Display only; the stored role (used by the role filter) catches up on next XP change or ladder save.
- Note: levels 1-4 showing "newcomer" is correct when the next role starts at level 5.

### To revert
```bash
git revert 12200cc
git push origin main
```

### What revert restores, and what it does NOT
- Restores stale official roles and no re-sync on ladder edits. No schema change.
- Roles already rewritten in the database stay as written; they do not roll back.

### Kill switch (if any)
- None. Roles are display/filter data only; a wrong role is fixed by re-saving the role ladder.

---

## `d48f2a3` — retire Telegram "word" verification; math answer no longer in button data
**Date:** 2026-10-10 · **Risk:** low-medium · **Touches:** bot hot path (join verification)

### What changed
- Word captcha could never pass: the joiner is muted (`can_send_messages=False`) so they cannot type the answer; they just timed out and got kicked. Removed on both bot lineages (`official_bot.py`, `bot_features/verification.py`) and from the group settings dropdown. Groups already set to `word` now get the button challenge.
- Math buttons no longer carry the correct answer in `callback_data` (it was readable by scripts). The answer is read from the server-side pending record. Old math buttons already in a chat still work.
- Telegram only. Discord-board word verification is untouched.

### To revert
```bash
git revert d48f2a3
git push origin main
```

### What revert restores, and what it does NOT
- Restores the unusable word option and answer-in-button-data. No data/schema changes.
- Does not undo members already verified, kicked or unmuted.

### Kill switch (if any)
- None. The removed path could not succeed before, so a flag would only re-enable a guaranteed failure.

---

## `5b0b531` — Signup trials can no longer create custom bots; trial visibility + managed-members charts in admin
**Date:** 2026-09-30 · **Risk:** medium · **Touches:** plan limits (custom-bot creation), bot hot path (scheduler jobs)

### What changed
- Every signup gets a 14-day Pro trial, and Pro allowed 3 custom bots, so any new account could spin up
  dedicated bot pollers at our cost. Custom-bot **creation and reactivation** now need a paid Pro/Enterprise
  plan, or an admin-granted custom-bot trial (7 days by default, 1 bot). Existing bots and existing trial
  users are untouched: only *new* bot creation is gated.
- New column `users.custom_bot_trial_ends_at`; new table `platform_daily_stats` (one row per UTC day: managed
  members, verified members, groups, users by plan, custom bots). Both are created by `backend.migrate`.
- New scheduler jobs: `snapshot_platform_stats` (daily 00:45 UTC) and, inside `expire_trials`, expiry of
  granted custom-bot trials (hands unpaid owners' bots to the normal pause -> retain -> delete lifecycle).
- Admin: plan badge (Free / TRIAL Nd left / Pro / Enterprise) on every user, trial start/end on the user page,
  "Trial" filter, grant/revoke custom-bot trial, managed-members panel and plan/trial/custom-bot charts.
- Setting a paid plan from the admin panel now clears `trial_ends_at` (otherwise the user still read as a
  trial and would be downgraded by `expire_trials`).

### To revert
```bash
git revert 5b0b531
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Restores the old tier-only custom-bot rule and removes the new admin UI/endpoints.
- ⚠️ Does **not** drop `users.custom_bot_trial_ends_at` or `platform_daily_stats` (harmless when unused).
- ⚠️ Does **not** undo custom-bot trials an admin already granted, or bots created under them.
- ⚠️ Does **not** restore `trial_ends_at` for users an admin set to a paid plan after this shipped.

### Kill switch
`CUSTOM_BOT_TRIAL_GATE_ENABLED=0` in Railway -> Variables restores the old creation rule in ~30 seconds, no deploy.

### Safety properties (verified, not assumed)
- Gate matrix tested: free, signup trial, trial + granted, paid Pro, admin-set Pro, Enterprise, expired grant,
  paid-during-trial, kill switch off — all return the expected limit.
- Overview, user-list `tier=trial` filter, grant/revoke, day-limit validation and granted-trial expiry run
  against a SQLite database built from the real models; frontend builds clean.

---

## `31769de` — Custom bots now auto-pause and auto-delete after tier expiry
**Date:** 2026-09-20 · **Risk:** high · **Touches:** money, data deletion, bot hot path, plan limits

### What changed
- Custom bots require Pro/Enterprise to exist (`Config.MAX_CUSTOM_BOTS['free'] == 0`), but until now,
  when an owner's subscription lapsed or trial expired, the bot's dedicated poller thread kept running
  forever at full cost — confirmed live in prod (a FREE-tier custom bot active in the admin console).
  This ships an automatic lifecycle: warn 2 and 1 days before expiry → on expiry, snapshot whether it
  was a trial or paid churn (`CustomBot.pause_reason`) and send a 3-option message (switch to the
  official bot for free, export settings, or reactivate at a discount) → grace-period reminders →
  **pause** the poller (`BotManager.stop_bot` + `Bot.is_active = False`) → retention reminder →
  **permanently delete** the bot and unlink its groups.
- Timelines: paid churn = 7-day grace + 15-day retention (22 days total). Trial expiry = 3-day grace +
  7-day retention (10 days total, tighter because these accounts never generated revenue).
- Every notification/pause/delete stage fires **exactly once per bot**, via an insert-or-skip claim
  table (`custom_bot_lifecycle_stages`), the same idiom as the existing `scheduled_job_runs` gate —
  safe to re-run daily and safe across redeploys.
- Two new promo codes seeded: `TRIAL20` (trial→paid conversion) and `COMEBACK20` (paid win-back), both
  20% off first cycle, tracked separately. Checkout support for `promo_code` already existed
  (`routes/billing.py`) — nothing new added there beyond wiring `Pricing.js` to read `?promo=` from
  the URL and pre-validate it.
- New route `POST /api/custom-bots/<id>/reactivate` resumes a paused bot after the owner upgrades,
  bypassing the `MAX_CUSTOM_BOTS` creation-limit check (it resumes an existing row, not a new one).
- Files: `backend/models.py` (new `CustomBot` columns + `CustomBotLifecycleStage` table),
  `backend/custom_bot_lifecycle.py` (new — the whole stage machine), `backend/scheduler.py` (hooks in
  `downgrade_expired_subscriptions` / `expire_trials`, new `run_custom_bot_lifecycle` daily job),
  `backend/app.py` (migration + job registration), `backend/routes/custom_bots.py` (reactivate +
  status routes), plus a frontend banner/lifecycle page and `Pricing.js` promo handling.

### To revert
```bash
git revert 31769de
git push origin main
```
The new columns/table are additive (`ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS`) and a
code revert does not drop them — harmless to leave in place.

### What revert restores, and what it does NOT
- ✅ Reverting stops the pause/delete cron from running at all (the job function goes away with the
  code) — any bot still mid-grace or mid-retention at that point simply stays as-is indefinitely again,
  same as before this feature existed.
- ⚠️ **A revert does NOT undo anything that already happened**: bots already paused stay paused (their
  poller was actually stopped — `git revert` does not restart a thread), bots already **permanently
  deleted are gone** (the `CustomBot` row, its group links, and its Assistant Hub mirror are dropped,
  not soft-deleted), DMs/emails/in-app notifications already sent were actually sent, and any
  `PromoCodeUsage` rows already recorded from `TRIAL20`/`COMEBACK20` redemptions stay recorded (the
  discount was actually applied to that checkout).
- ⚠️ The two promo codes themselves are NOT removed by a revert (the seed uses
  `ON CONFLICT DO NOTHING`, and a revert doesn't run a corresponding delete) — deactivate them by hand
  in the admin promo-codes panel if a revert should also stop them from being redeemable.

### Kill switch (env vars, no deploy needed)
| Variable | Set to | Effect |
|---|---|---|
| `CUSTOM_BOT_LIFECYCLE_ENABLED` | `0` | Stops the entire daily tick instantly — no bot gets warned, paused, or deleted. Bots already paused stay paused; nothing auto-resumes. |
| `CUSTOM_BOT_LIFECYCLE_DRY_RUN` | `1` (**default on this ship**) | Every stage still evaluates and logs what it *would* do — notify / pause / delete — but sends nothing and touches no bot. **Flip to `0` only after reading a day or two of `[custom_bot_lifecycle][DRY_RUN]` logs and confirming the numbers look right** — this is the same gotcha as `RETENTION_DRY_RUN`: forgetting this step means the feature silently does nothing in production. |

### Safety properties (verified, not assumed)
- Exactly-once per (bot, stage): verified by reading the `INSERT ... ON CONFLICT (bot_id, stage) DO
  NOTHING RETURNING bot_id` claim — a stage's notification and any pause/delete action only run when
  this insert wins, so re-running the daily tick (redeploys, retries) cannot double-send or double-act.
- Pausing does not get silently undone: `bot_links.reconcile_custom_bots` (the self-healing startup
  reconciliation) only iterates `Bot.query.filter_by(is_active=True)` and never re-activates an existing
  row or flips an existing `CustomBot.status` back to `active` — confirmed by reading `bot_links.py`
  Pass 1. The boot-time bot restarter and the watchdog (`app.py: _restart_active_bots`,
  `_watchdog_bots`) both also gate on `Bot.is_active`, so a paused bot cannot be auto-resumed by any of
  the three restart paths this codebase has.
- Trial vs. paid churn is captured at the one moment it's still knowable: `pause_reason` is stamped
  synchronously inside `downgrade_expired_subscriptions` / `expire_trials`, before those functions clear
  the very `User` fields (`subscription_expires_at`, `trial_ends_at`) that distinguish the two paths.

### Update 2026-09-20: first deploy attempt failed healthcheck, unrelated to this feature
This commit's first deploy (bundled with the docs commit `d6aa912`) failed Railway's `/health`
healthcheck — **not a bug in this feature**: total startup (migrate.py release step + gunicorn's
own `create_app()` re-running every migration on import, against Neon's higher per-round-trip
latency than the old Railway Postgres) exceeded the 5-minute healthcheck window. Production kept
serving the prior successful deploy throughout; no outage.

While tracing it, found and fixed a real ordering bug it exposed: `reconcile_custom_bots()` in
`backend/app.py` ran *before* `_run_custom_bot_lifecycle_migration()`, so on this feature's very
first boot in any environment, the ORM's `CustomBot.pause_reason` column reference threw
`UndefinedColumn` (caught, logged as a warning, harmless — see `bot_links.py:212`) until the
migration below it added the column. Moved the reconciliation block to run after all migrations
instead. Pure reorder, no behavior change — does not affect the revert command or safety
properties above; a `git revert 31769de` still removes this feature cleanly either way.

---

## `infra-2026-09-20` — Telegizer production database migrated: Railway Postgres → Neon
**Date:** 2026-09-20 · **Risk:** high · **Touches:** data, bot hot path

### What changed
- `telegram-bot-saas`'s `DATABASE_URL` now points to a Neon Postgres project ("Telegizer",
  project id `wandering-bread-61933881`) instead of the Railway-hosted Postgres service.
  Motivation: cost reduction (Railway bills RAM per always-on service; Neon's free tier
  absorbs this database at ~$0 *if* the compute can scale to zero between requests).
  ⚠️ **That assumption doesn't fully hold**: `backend/app.py`'s `_scheduler_loop` polls the
  DB every 60s, 24/7, for scheduled messages/reminders/automations — by design, for
  near-real-time delivery. That keeps the Neon compute at its 0.25 CU floor continuously
  instead of suspending, i.e. a small but genuinely recurring compute-hour cost (~180
  CU-hours/month), not the ~$0 originally assumed. Not a leak — a known, flat baseline.
  Check it against the Neon plan's included compute-hours before relying on "~$0" again.
- Data was dumped from the Railway Postgres (`pg_dump --no-owner --no-privileges -Fc`) and
  restored into Neon (`pg_restore --clean --if-exists`) — 128 tables, ~64k rows, verified by
  table/row count before cutover.
- Start command was split because mixing this up caused two failed deployments first:
  ```
  DATABASE_URL=$DATABASE_URL_UNPOOLED python -m backend.migrate && gunicorn backend.app:app --timeout 120
  ```
  Migrations run against Neon's **direct/unpooled** connection (DDL needs a stable
  `search_path`, which Neon's pooled/PgBouncer connection doesn't reliably preserve — first
  attempt hit `no schema has been selected to create in`). The running app uses the
  **pooled** connection (`DATABASE_URL`) — running the app itself on the unpooled
  connection was the second failed attempt: BotManager startup got slow enough over
  per-connection overhead to blow gunicorn's 30s worker timeout (`WORKER TIMEOUT` →
  `SIGKILL`, repeatedly, until the healthcheck window expired). `--timeout 120` added as
  a safety margin regardless of DB backend.
- The old Railway Postgres service (`vigilant-integrity` project, service `Postgres`) is
  left running untouched — not deleted, not even paused yet — as an instant fallback.

### To revert
No code revert — this was a Railway-config-only change (env vars + start command), no
application code was touched.
1. Railway → `telegram-bot-saas` → Variables → set `DATABASE_URL` back to
   `${{Postgres.DATABASE_URL}}`.
2. Settings → Deploy → Start Command back to:
   `python -m backend.migrate && gunicorn backend.app:app`
3. Deploy.

### What revert restores, and what it does NOT
- ✅ The old Railway Postgres still has every row exactly as it was at the moment of
  cutover (2026-09-20 ~09:00 UTC) — nothing was deleted or altered on it.
- ⚠️ **Anything written to Neon after cutover is NOT in the old Railway Postgres.**
  Reverting after any real usage on Neon means losing every message/record/subscription
  change written in between. If reverting after the app has been live on Neon for a
  while, dump Neon and restore into the Railway Postgres first, then swap the variable
  back — do not flip the variable onto stale data.
- ⚠️ The two failed intermediate deployments (schema error, then worker timeout) never
  took production traffic — Railway kept serving the last successful deployment
  throughout both failures, so there was no live outage from either attempt. The false
  "all clear" that happened mid-migration was from pinging `/health` during that window,
  which was still answering from the old (still-active) deployment — not proof the new
  one was healthy. Verify the actual deployment `status` field, not just the URL, when
  checking a rollout like this in the future.

### Kill switch (if any)
The `DATABASE_URL` variable itself is the kill switch (see the emergency table above) —
not instant (requires a redeploy), but no code changes needed.

Added 2026-09-20: a Neon project-level usage quota (Console → Telegizer project →
Settings → Quota; `compute_time_seconds` 1,980,000/mo, `active_time_seconds`
2,988,000/mo, `data_transfer_bytes` 50GB/mo, `written_data_bytes` 20GB/mo) as a tripwire
against a *real* leak (e.g. a duplicate-bot-fleet bug like the past Railway/Celery
incident) — generous headroom above the known ~180 CU-hr/month baseline above, so it
should never trip under normal traffic. If it ever does trip, Neon suspends the compute
until the quota is raised or the billing period resets — that itself becomes an outage,
so raise the quota in the Neon console rather than waiting for the reset if it fires.

### Safety properties (verified, not assumed)
- Pre-cutover: verified 128/128 tables and matching row counts between the Railway dump
  and the Neon restore.
- Post-cutover: verified via the actual Railway deployment `status: SUCCESS` (not just an
  HTTP ping), and confirmed steady-state operation — `getUpdates` polling succeeding
  continuously in deploy logs for several minutes post-boot, no crash/restart loop.
- `[startup] Encryption self-check passed.` and `[startup] CustomBot token spot-check
  passed (4 bots checked).` confirm `ENCRYPTION_KEY`/`ENCRYPTION_KEY_OLD` still decrypt
  correctly against the migrated data.

---

## `2b6c0be` — audit pass: fix a real cross-lineage verification bug + SSRF + sync races
**Date:** 2026-09-15 · **Risk:** medium · **Touches:** money, bot hot path, security

### What changed
An in-depth cross-check of the last 4 commits (requested after they shipped), using an
independent 8-angle automated review plus manual verification against real
models/SQLite. Found and fixed real bugs, not just style:

1. **Cross-lineage collision in `pending_verifications` (real, serious).** `ff584f2`'s
   own predecessor made custom bots write into the same table the official bot already
   used, but never scoped either side by lineage. A group running BOTH the official bot
   and a custom bot (this platform explicitly supports that — see `507db0f`'s notes)
   could have one bot's challenge silently overwritten, or its DB row deleted out from
   under it, by the other. Fixed: `bot_type` is now part of the unique constraint
   (`chat_id, user_id, bot_type`) and every read/write in both `official_bot.py` and
   `bot_features/verification.py` filters by it. Also removed a column default that
   would have silently mislabeled official-bot rows as `"custom"` (official_bot.py never
   set the column itself), and backfills any pre-existing rows.
2. **`telegram_group_id` was silently always NULL for custom bots.** Three call sites in
   `verification.py` read `group.telegram_chat_id` — `Group` has no such attribute
   (it's `telegram_group_id`) — so `getattr(..., None)` always fell through. Fixed the
   typo, and corrected the column's type (was `BigInteger`, should be `String(255)` to
   match `Group`/`TelegramGroup.telegram_group_id`).
3. **SSRF in the new website/"any URL" scraper (security).** `knowledge_sources.py`
   fetched an admin-supplied URL server-side with no host validation — a Pro user could
   point a source at `169.254.169.254` (cloud metadata), localhost, or an internal
   Railway service and have the response reflected back through the dashboard. Fixed:
   every hostname (including each hop of a redirect chain, checked individually — not
   just the initial URL) is resolved and rejected if it's private/loopback/link-local/
   reserved/multicast. Response bodies are also now capped at 5MB via streaming instead
   of buffered in full before truncation.
4. **Sync could double-fire (real, costs money).** The 60s cooldown was a Python-level
   check-then-act in the route handler — two near-simultaneous "Sync now" clicks (or a
   double-click) both read the same `last_synced_at` and both ran, double-spending
   embeddings/YouTube/twitterapi.io calls for one click. Fixed with an atomic
   `UPDATE ... WHERE` claim inside `process_external_source` itself (so both routes get
   the fix from one place) — timestamp-only, deliberately no separate "syncing" status,
   so a crash mid-sync self-heals after the cooldown instead of locking the source out
   forever.
5. **The 100MB/group storage quota that `ff584f2`'s own writeup claimed was automatic,
   wasn't** — `process_external_source` never actually checked it. Now does, for
   custom-bot (group_id) sources; official-bot sources have no aggregate quota today
   either way (matching that lineage's existing file-upload route).
6. **Official bot's restrict-only verification-timeout branch never removed its DB row**
   (only the in-memory dict) — inconsistent with the exact same fix already applied to
   the custom-bot side in `df8da28`. Now calls `_remove_pending_verification` there too.
7. **YouTube API errors were swallowed** — a bad/quota-exhausted API key returned a 4xx
   with no `items` key, and the code reported "channel has no public uploads" instead of
   the real cause. Now checks `status_code` first, like the other fetchers already did.
8. **Consolidated the `ChatPermissions` "restore full member" block**, which was
   copy-pasted at 6 call sites platform-wide (4 touched by the verification fix, 1 in
   `routes/telegram_groups.py`, 1 more found in `routes/settings.py`) — 4 of the 6 were
   missing `can_send_polls`, meaning a "fully unmuted" member still couldn't send polls.
   Now one shared `telegram_permissions.full_member_permissions()`.
9. **Consolidated the two new `_require_paid` copies** (`routes/knowledge.py`,
   `routes/telegram_groups.py`) into `backend/utils/plan_gating.py`. Three older,
   independent copies (`polls.py`, `settings.py`, `totp.py`) are left alone — out of
   scope, higher risk to touch for a pure dedup with no bug attached to them.

### To revert
```bash
git revert 2b6c0be
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Mostly reversible — no data is deleted by reverting. The unique-constraint change
  and `bot_type` backfill are additive/corrective; reverting just stops enforcing them.
- ⚠️ Reverting brings back all 9 issues above, including the SSRF path (#3) and the
  cross-lineage collision (#1) — treat a revert of this commit as re-opening a real
  security gap, not just an inconvenience.
- ⚠️ Sync attempts already correctly blocked by the double-fire fix, or already correctly
  rejected by the SSRF guard, are not "undone" by a revert — there was nothing to undo.

### Kill switch (if any)
- `VERIFICATION_DB_PERSIST=0` — still disables the whole custom-bot DB-persistence path
  from `df8da28`/this commit at once, including the lineage-scoping fix; only use this if
  the persistence path itself is the problem, not the SSRF/race fixes.
- `KNOWLEDGE_SOURCES_ENABLED=0` — still disables sync-now on both lineages.
- No standalone kill switch for the SSRF guard or the ChatPermissions/plan-gating
  consolidation — these are corrections to code that was never safe/correct; a flag that
  disabled them would just be a flag that reintroduced the vulnerability or the bug.

### Safety properties (verified, not assumed)
No test suite in this repo. Extended the throwaway harnesses from the prior two entries:
- **Cross-lineage isolation (7 checks):** an official-bot row and a custom-bot row for
  the identical `(chat_id, user_id)` both persist independently with no collision; each
  lineage's loader restores only its own row after a simulated restart; deleting one
  lineage's row leaves the other's intact.
- **KB sources (28 checks, up from 13):** all prior checks still pass, plus new ones —
  an immediate re-sync attempt and a post-success double-click are both rejected by the
  atomic claim without creating a second document; the SSRF guard blocks 127.0.0.1,
  localhost, 169.254.169.254, two private ranges, and a non-http(s) scheme, while still
  allowing a normal public URL and following a real redirect (tested live against
  `http://github.com` → `https://github.com`); a source aimed at the metadata endpoint
  fails cleanly end-to-end with no raw exception text leaked.
- All touched Python files compile; every touched module (including the new
  `telegram_permissions.py` and `utils/plan_gating.py`) imports cleanly standalone.
- `full_member_permissions()` was confirmed to build a valid `ChatPermissions` with all
  10 fields, returning an independent object on each call (no shared-mutable-state risk).

---

## `3d28b51` — KB external sources: official-bot parity
**Date:** 2026-09-15 · **Risk:** low · **Touches:** money (AI/API spend), plan limits

### What changed
Follow-up to `ff584f2`. That commit only wired external knowledge sources up for
custom bots; a check confirmed `subscription_tier` (the Pro gate) is independent of
bot lineage — a Pro/Enterprise user can have groups on the shared official bot
instead of a custom bot, and nothing about that makes them less entitled to a paid
feature. Extended the same feature to the official-bot lineage:
- `KnowledgeSource` now dual-scoped like `KnowledgeDocument` already was:
  `group_id` is nullable, new nullable `telegram_group_id` column added. A
  custom-bot source sets one, an official-bot source sets the other — never both.
- `KnowledgeBaseSystem.process_external_source` threads `telegram_group_id`
  through to `_embed` (AI key resolution) and the upserted `KnowledgeDocument`.
- New mirrored routes in `routes/telegram_groups.py` (list/create/sync/delete),
  same Pro gate, same `KNOWLEDGE_SOURCES_ENABLED` kill switch, same 20-source cap
  and 60s sync cooldown — scoped to `telegram_group_id` instead of `group_id`.
- Frontend: `api.js` branches the 4 source calls on `botId === 'official'` (same
  pattern the existing upload/list/delete calls already used); `KnowledgeBase.js`'s
  "External Knowledge Sources" section is no longer custom-bot-only.

### To revert
```bash
git revert 3d28b51
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Fully reversible — `telegram_group_id` is a new nullable column, nothing is
  dropped. Reverting removes official-bot access to this feature; custom bots
  (shipped in `ff584f2`) are untouched.
- ⚠️ Any official-bot-lineage sources/documents already synced while this was
  live stay in the DB (harmless, just unreachable through the UI after a revert).

### Kill switch (if any)
Same as `ff584f2`: `KNOWLEDGE_SOURCES_ENABLED=0` disables sync-now on **both**
lineages at once (it's one env var checked in both route files).

### Safety properties (verified, not assumed)
Extended the same throwaway harness used for `ff584f2`: a `KnowledgeSource` with
`group_id=None, telegram_group_id=<a chat id>` syncs successfully end-to-end and
produces a `KnowledgeDocument` with `group_id IS NULL` / `telegram_group_id` set —
confirming the dual-scoping doesn't cross-contaminate the two lineages. All
touched Python files compile; the frontend changes pass this project's own
ESLint config with zero errors or warnings.

---

## `ff584f2` — AI Knowledge Base: external sources (website / Telegram / X / YouTube)
**Date:** 2026-09-15 · **Risk:** low-medium · **Touches:** money (AI/API spend), plan limits

### What changed
New opt-in capability, additive only — no existing behavior changed for anyone not using it:
- **New table `knowledge_sources`** (`backend/models.py`, migration in `app.py`) — an admin
  registers a URL (website, official Telegram channel, X/Twitter handle, YouTube channel, or
  literally any other page); a new `source_id` column on `knowledge_documents` links the
  ingested content back to it so a re-sync replaces rather than duplicates.
- **`backend/bot_features/knowledge_sources.py` (new)** — fetches a source's current content:
  a plain page scrape (new `beautifulsoup4` dependency) for websites/"any other URL", the
  public `t.me/s/<channel>` HTML preview for Telegram (public channels only — no MTProto user
  session, deliberately, per this project's Anti-Ban Rule), twitterapi.io for X (same provider
  already used for engagement verification), and the YouTube Data API for a channel's recent
  uploads. Every fetcher degrades to `(False, reason)` on any error — never raises.
- **`KnowledgeBaseSystem.process_external_source`** (`knowledge_base.py`) reuses the exact same
  chunk+embed pipeline as an uploaded file, so it shares the existing 100MB/group storage quota
  automatically (both write into `knowledge_documents`).
- **New routes** in `routes/knowledge.py`: list/create/sync-now/delete for a group's sources.
  **Gated Pro-only** (stricter than plain file upload, which has no plan gate) because a sync
  makes outbound calls to a third party or a site we don't control, and can call a paid API
  (YouTube Data API / twitterapi.io) — a materially bigger cost and abuse surface than accepting
  a file the admin already has on disk. Capped at 20 sources/group and a 60s per-source sync
  cooldown.
- **Sync is on-demand only** (an explicit "Sync now" click) — no new Celery/scheduler job, no
  new recurring load on the scheduler pool this file already flags as saturation-prone.
- Frontend: new "External Knowledge Sources" section in `KnowledgeBase.js`, custom bots only —
  there is no official-bot route for this yet (the official bot has its own separate
  `/api/telegram-groups/<id>/knowledge` file-upload routes in `telegram_groups.py`; this feature
  does not touch or extend that path).

### To revert
```bash
git revert ff584f2
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Fully reversible. `knowledge_sources` is a new table and `source_id` is a new nullable
  column — a revert just stops the code paths that read/write them; nothing is dropped.
- ⚠️ Sources and documents already synced while this was live are not deleted by a revert —
  they simply stop being reachable through the UI. Harmless; an unused table/column costs
  nothing and holds real content if this ships again later.
- ⚠️ Any AI-embedding or third-party API spend already incurred by syncs that already ran is
  not undone (it's a real API call, not a reversible write).

### Kill switch (if any)
`KNOWLEDGE_SOURCES_ENABLED=0` — disables the one endpoint that actually spends money (sync-now)
in ~30 seconds with no deploy. Adding/listing/deleting sources still works; only fetching new
content is stopped. Per-group: nothing stops it from a plan downgrade below Pro other than the
existing Pro gate itself.

### Safety properties (verified, not assumed)
No test suite in this repo, so a throwaway harness was built against a real Flask app +
in-memory SQLite using the actual models and the actual `KnowledgeBaseSystem`:
- A live fetch against a real URL (`example.com`) correctly extracts text end-to-end.
- With no AI key configured, a sync fails cleanly (`ok=False`, a clear reason, source marked
  `error`) and creates **no** `KnowledgeDocument` row — never raises.
- With a (mocked) working embedding call, a sync creates exactly one `KnowledgeDocument`
  linked by `source_id`; a **second** sync of the same source still leaves exactly one
  document (upsert, not duplicate).
- An unreachable/invalid URL fails cleanly with a specific error message, not a crash.
- `detect_source_type` correctly classifies youtube.com / t.me / x.com / everything-else URLs.
- All 5 touched/new Python files compile; the new frontend section passes this project's own
  ESLint config with zero errors or warnings.
- ⚠️ Not verified against the live YouTube Data API, twitterapi.io, or a real Telegram public
  channel — this sandbox's network blocks Telegram's domains outright, and no YouTube/X API key
  was available to test against. Each fetcher's error handling was verified via injected
  failures (missing key, bad URL, unreachable host), but the first real sync against each of
  those three providers in production is still the real proof.

---

## `df8da28` — fix join-verification: users stuck muted, "expired" on click
**Date:** 2026-09-15 · **Risk:** medium · **Touches:** bot hot path

### What changed
Reported symptom: clicking a join-verification challenge (button/math/word, either bot
lineage) says "verification completed" or "verification expired" and the user is left
unable to post — this was actively costing real members. Two independent bugs, found by
tracing the full flow end to end:

1. **`ChatPermissions(can_send_media_messages=True, ...)` — this kwarg was removed from
   python-telegram-bot in v20.5; the pinned version here is 21.3 (`requirements.txt`).
   Every call **raised `TypeError` before the user was ever unmuted**, in all 4 places that
   build this object: verification success on both bot lineages
   (`bot_features/verification.py`, `official_bot.py`) and the `/unmute` command on both
   lineages (`bot_manager.py`, `official_bot.py`). The exception was swallowed by an
   existing `except Exception` — so `query.answer(...)` was sometimes never reached, and
   Telegram's own client shows a generic "expired" toast for an unanswered callback query.
   This matches the reported symptom directly and is the more likely primary cause.
   Replaced with the 6 granular flags PTB has used since 20.5 (`can_send_audios`,
   `can_send_documents`, `can_send_photos`, `can_send_videos`, `can_send_video_notes`,
   `can_send_voice_notes`) at all 4 call sites.
2. **Custom-bot verification state was in-process-only.** `VerificationSystem.pending`
   (`bot_features/verification.py`) is a plain dict with no persistence, unlike the
   official bot's `PendingVerification` DB table. The `Procfile` recycles the single
   gunicorn worker every ~500 requests (`--max-requests`), which rebuilds every
   `BotInstance`/`VerificationSystem` with an **empty** dict. A challenge sent moments
   before a recycle reads as "already processed or expired" to a real user clicking
   within the original timeout. Custom bots now write-through to the same
   `pending_verifications` table (new columns: `bot_id`, `group_id`, `bot_type`,
   `telegram_group_id`) and reload their own rows on every (re)start, re-arming the
   timeout timer for each restored challenge — mirroring what the official bot already did.
3. **Adjacent bug in the same code, not the reported symptom:** the official bot's
   in-process timeout handler called `_fail_verification(bot, chat_id, user_id, pending,
   None)` — `None` is the `flask_app` param, not `group_id`. With no `flask_app`, the
   1-hour scheduled `PendingUnban` row was never written, so the independent 5-minute
   `expire_pending_verifications` Celery sweep found the still-present DB row and
   immediately banned+unbanned the user — undoing a temp-ban within ~5 minutes instead of
   the intended 1 hour. Fixed by threading the real `flask_app` through both call sites.

### To revert
```bash
git revert df8da28
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Fully reversible. New columns are additive (`ADD COLUMN IF NOT EXISTS`, all nullable)
  and are simply left unused by a revert — no data loss, no destructive migration.
- ⚠️ Reverting brings back all 3 bugs above: unmute crashing silently, custom-bot
  verification state lost on every worker recycle, and the official bot's temp-ban
  duration collapsing to ~5 minutes.
- ⚠️ Members already correctly unmuted or verified while this was live stay that way — a
  revert does not re-mute them.

### Kill switch (if any)
- `VERIFICATION_DB_PERSIST=0` — instantly reverts custom bots to the old in-memory-only
  behavior (bug #2 above) without touching the `ChatPermissions` fix, no deploy needed.
- `GUNICORN_MAX_REQUESTS=0` — stops the worker recycle that triggers bug #2 at all, without
  code changes, if the DB write-through itself needs to be avoided under load.
- No kill switch for the `ChatPermissions` fix or the `flask_app` threading fix — both are
  straightforward corrections to code that could not possibly have worked before; a flag
  that reintroduced them would just be a flag that reintroduced the crash.

### Safety properties (verified, not assumed)
No test suite in this repo, so a throwaway harness was built against a real Flask app +
in-memory SQLite using the actual models and the actual `VerificationSystem` class (no
mocks of the logic under test):
- A challenge write-through produces a DB row with the correct `bot_id`/`group_id` and a
  future `expires_at`.
- A brand-new `VerificationSystem` (simulating the post-recycle process) starts with an
  empty `pending` dict — reproducing the bug — and `load_pending_from_db()` restores it.
- A button click on the **restored** instance completes successfully end-to-end (was: the
  `ChatPermissions` crash prevented this even pre-recycle) and removes the DB row.
- Math-method wrong-answer attempt counts persist to the DB and survive a simulated
  restart; a correct answer on the restored instance still succeeds.
- All 5 touched Python files compile.
- ⚠️ Verified against SQLite with a hand-built minimal schema (only `pending_verifications`
  created), not the full Postgres schema — the FK/column types are plain and additive, but
  the first real verification click in production is still the real proof.

---

## `051fb13` — cut web-service RAM: one bot manager, one scheduler pool, bounded per-user caches
**Date:** 2026-09-10 · **Risk:** medium · **Touches:** bot hot path

### What changed
- **`backend/app.py` no longer constructs its own `BotManager`.** There were two
  instances: `app.py` started every bot, while every `from ..bot_manager import
  bot_manager` call site (`routes/bots.py`, `custom_bots.py`, `settings.py`, `digest.py`,
  `hub.py`, `auth.py`, `scheduler.py`) talked to a permanently empty one. Consequences
  that are now fixed: `stop_bot()` from the dashboard or bot deletion silently no-op'd,
  leaving a poller running forever with no DB row behind it; `GET /api/bots/<id>/status`
  saw `is_running()==False` and "auto-restarted" an already-running bot, giving one token
  two pollers (409 Conflict) and double its RAM; `thread_alive` was always `False`.
- **One shared scheduler thread pool** instead of a new `ThreadPoolExecutor` per job per
  tick (~15 jobs/minute, ~20k thread creations/day). Also fixes the timeout: `with
  ThreadPoolExecutor()` called `shutdown(wait=True)` on exit, so after a job "timed out"
  the loop blocked until it actually finished — one hung Telegram/OpenAI call stalled all
  19 jobs while the log claimed a timeout.
- **`MALLOC_ARENA_MAX=2`** in the `Procfile`. glibc hands each new thread its own 64 MB
  arena and does not really give it back, so thread churn grows RSS with no Python leak.
- **Per-`(chat, user)` maps are now pruned** every 10 minutes: `official_bot`'s five
  trackers, `ModerationSystem`'s four, and `VerificationSystem.pending` /
  `first_message_pending`. None of them ever shrank — one entry per member who had ever
  sent a message, for the life of the process. `first_message_pending` was the worst: it
  held a detached ORM group row, its settings JSON and a Telegram User object for every
  member who joined and never posted.
- **`knowledge_base` ranking** keeps only the top 3 chunk texts (`heapq.nlargest`) instead
  of full-sorting every chunk and holding every 1536-float embedding live across the LLM
  call, and hoists the query norm out of the per-chunk cosine (a third of the arithmetic).
- **New `GET /api/admin/memory`** (`health.view`) reports live RSS, threads by name prefix,
  pollers-vs-DB-rows, cache sizes, DB pool state and whether the retention sweep is armed
  (`retention.dry_run_effective`). Read-only; `?deep=1` adds a heap census.

### To revert
```bash
git revert 051fb13
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Fully reversible. No schema change, no migration, no deletion, no writes to user data.
- ⚠️ Reverting brings back the two-`BotManager` split — including `stop_bot()` silently
  failing and deleted bots continuing to poll Telegram. Prefer the kill switches.
- ⚠️ Cache entries already evicted by a prune are not restored. They were entries older
  than 24h that every call site already read as absent (`now - last < window`), so nothing
  depended on them, but they do not come back.
- ⚠️ A revert does **not** stop an orphan poller that is already running in the live
  process — only a restart does. Redeploy after reverting.

### Kill switch (if any)
- `SCHEDULER_SHARED_POOL=0` — back to a per-job executor, no deploy.
- `MALLOC_ARENA_MAX=8` — back to glibc defaults.
- `SCHEDULER_POOL_WORKERS=<n>` — resize the pool (floor 2, default 4).
- The cache prune and the single `BotManager` have **no** kill switch: both are corrections
  to bookkeeping, and a flag that re-enabled the split brain would be a flag that
  re-enabled duplicate pollers. Use `git revert` if they must go.

### Safety properties (verified, not assumed)
No test suite in this repo, so two harnesses were written and run:
- **Prune + ranking (30 checks).** Live cooldowns kept, stale dropped; a spam entry mixing
  stale and live timestamps survives on its newest stamp; an in-flight challenge and one
  just past expiry are both kept (10-minute grace) while a long-orphaned one goes; prune is
  idempotent and safe on empty state. For KB ranking: the hoisted-norm cosine is
  arithmetically identical to the original (max delta < 1e-12) and the new top-3 matches
  the old `sorted()` top-3 in both membership and order — including exact ties, which the
  negated index preserves in original order the way the old stable sort did.
- **Scheduler pool (14 checks), run against the real function source extracted from
  `app.py`.** The pool is a singleton; a job that overruns its timeout returns control in
  ~1s instead of blocking until it finishes; a later job still runs while that one hangs;
  errors are swallowed; `flask_app` context is pushed inside the worker thread; args are
  forwarded; and the kill-switch path also no longer blocks on a runaway job.
- All six changed Python files compile.

### Known failure mode: a saturated scheduler pool
The shared pool has **4 workers** (`SCHEDULER_POOL_WORKERS`, floor 2). A job that overruns
its timeout keeps its worker until it actually finishes — that is the whole point, it is
what stops one hung job freezing the loop. But it means four jobs hung *at the same time*
occupy every worker, and then every later job just sits in the queue until its own timeout
expires and is skipped.

**Symptom:** `[SCHEDULER] <job> timed out after 30s` for many different jobs, in a steady
drumbeat, for jobs that normally finish instantly. The log line is misleading — those jobs
did not run slowly, they **never started**. Digests, watchdog restarts and the retention
sweep all silently stop happening. Nothing crashes and health checks stay green.

**Confirm it:** `GET /api/admin/memory` → `threads.by_prefix`. Four or more live `sched`
threads with the scheduler still logging timeouts means the pool is full, not busy.

**Fix:** `SCHEDULER_POOL_WORKERS=8` (restart, ~30 s, no deploy) buys headroom and gets the
skipped jobs running again; a restart clears the hung workers outright. Then find the job
that hangs — it is a network call with no timeout, and raising the worker count only widens
the margin before it fills up again.

**This is not a regression.** Before this commit a *single* hung job blocked the loop on
`shutdown(wait=True)` and froze all 19 jobs indefinitely. It now takes four simultaneous
hangs to reach a worse-behaved version of the same state, and it self-heals the moment any
of them returns — measured, both before and after.

### Note for whoever reads this next
`GUNICORN_MAX_REQUESTS` (default 500) recycles the web worker — and because the bots run
in threads *inside* that worker, every recycle restarts the whole bot fleet and re-runs
every migration in `create_app()`. It was added to cap the RAM creep this change removes at
the source. Once `/api/admin/memory` shows RSS flat over a few hours, raise it (or set `0`)
so the fleet stops restarting; do not raise it before checking that.

---

## `3ad8dde` — recycle gunicorn worker periodically to cap memory creep
**Date:** 2026-08-12 · **Risk:** low · **Touches:** hot path

### What changed
- `Procfile`: web dyno now restarts its worker every ~500 (±50) requests via
  `gunicorn --max-requests` / `--max-requests-jitter`, so any slow RSS growth
  or allocator fragmentation gets returned to the OS instead of accumulating
  for the life of the deploy.
- Both numbers are env-overridable (`GUNICORN_MAX_REQUESTS`,
  `GUNICORN_MAX_REQUESTS_JITTER`); the Procfile values are just defaults.
- Purely a Railway memory-cost optimization — no application behavior change.

### To revert
​```bash
git revert 3ad8dde
git push origin main
​```

### What revert restores, and what it does NOT
- ✅ Web worker runs for the life of the deploy again, never self-restarting.
- ⚠️ Nothing is deleted, sent, or charged by this change either way — it only
  affects when the single worker process recycles itself.

### Kill switch (if any)
Set `GUNICORN_MAX_REQUESTS=0` in Railway → web service → Variables. Gunicorn
treats `0` as "disabled." Takes effect on the next restart (~30s), no deploy.

### Safety properties (verified, not assumed)
- `--workers 1`, so a recycle briefly drops the listener while the old worker
  finishes its in-flight request and the new one boots; `--graceful-timeout 20`
  already governs that window. Telegram retries webhook deliveries on
  failure, so a missed update is redelivered, not lost.
- 500 requests is a request-count trigger, not a timer — low-traffic periods
  won't force restarts.

---

## `7b62337` — escalations always reach a human; silent-in-group default; Guildizer sentinel
**Date:** 2026-07-17 · **Risk:** medium · **Touches:** bot hot path (both boards)

### What changed
1. **Escalations can no longer vanish.** `trigger_escalation` used to silently no-op when
   `escalation.enabled` was off or no admin_ids were set (the default!) — this is why
   "it never went to the admin". Now every unanswered question of an active type records
   an EscalationEvent AND sends an in-app dashboard notification (bell + web push) to the
   group owner. Telegram admin DMs remain the extra channel when enabled + admins picked.
   DM failures (admin never /start-ed the bot) now log at warning, not debug.
2. **Silent in the group by default** — `escalation.public_ack` default flipped to False
   per the owner's explicit preference; the professional ack is opt-in.
3. **Guildizer got the same NO_ANSWER sentinel fix** (copied, not imported): model
   escalates to the mod alert channel instead of saying "that's not covered" in-channel;
   /ask and auto-reply both covered; fallback copy professionalised.
4. Fixed stale `escalation.admins` key in settings.py (DM-eligibility indicator read the
   wrong key, so the UI could never show whether admins had started the bot).

### To revert
```bash
git revert 7b62337
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Restores the old gating (escalations skipped unless fully configured).
- ⚠️ Dashboard notifications and EscalationEvent rows already created stay (data).

### Kill switch (if any)
Per-group: turn off the escalation types in dashboard AI › Escalation, or disable AI
Auto-Reply. Global: `OFFICIAL_KB_AUTO_REPLY=0` still kills the official auto-reply path
(escalations only fire from AI paths, so this silences the main source too).

### Safety properties (verified, not assumed)
- Escalation volume is bounded: 60s per (group, user) cooldown on both TG lineages
  (TTLMap — no unbounded dict), 10-min per (guild, user, type) on Guildizer, and the
  in-app notification layer coalesces bursts within 90s into one bell item.
- In-app notification is best-effort inside try/except — a notifications failure can
  never break the escalation DM path or the message handler.

---

## `e475f2f` — AI KB: professional no-answer handling + official-bot auto-reply
**Date:** 2026-07-17 · **Risk:** medium · **Touches:** bot hot path (`on_message`, both lineages)

### What changed
1. **The AI no longer says "I don't know" in the group.** The prompt now makes the model
   return a `NO_ANSWER` sentinel when the PDFs/KB don't contain the answer; the code turns
   that into: ping the configured admins' DMs (existing Escalation system) + a professional
   "I've passed your question to the admins — you'll get an answer shortly" ack in the group
   (`escalation.public_ack`, default on; set it false for full silence). If escalation is
   not configured, the bot stays quiet (auto-reply) or gives a professional one-liner (/ask).
2. **KB answers are no longer rejected by the cosine-similarity gate.** The old
   `confidence_threshold` default (0.65) was above what real embedding matches score
   (~0.4–0.6), so correct PDF answers were being thrown away — this is why "the AI can't
   fetch answers from the PDFs". The threshold is now only a pre-LLM retrieval floor,
   capped at 0.25; the model itself decides answerability.
3. **The official (shared) bot now actually has AI Auto-Reply.** The
   `knowledge_base.auto_reply_enabled` toggle existed in Quick Settings/dashboard but no
   code read it — only `/ask` worked. Implemented in `official_bot.py` (mention-only by
   default, off by default, per-group opt-in).

### To revert
```bash
git revert e475f2f
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Restores the old behaviour (public "I don't know" replies, 0.65 gate, no official auto-reply).
- ⚠️ Escalation DMs already sent to admins are not unsent (they're just messages).
- ⚠️ Auto-learned Q&A rows (`AutoResponse` with `use_as_ai_knowledge`) created by admin
  replies stay — they're data the admin authored, keep them.

### Kill switch (if any)
`OFFICIAL_KB_AUTO_REPLY=0` — instantly disables the new official-bot auto-reply globally
(the rest of the change is prompt/copy behaviour with no switch; per-group, the dashboard
"AI Auto-Reply" toggle turns it off in seconds).

### Safety properties (verified, not assumed)
- Auto-reply is **default OFF** and **mention-only by default** — no group gets new AI
  replies without opting in. On a settings-lookup failure it does NOT run (fails closed,
  because it costs money; the paid-feature gates around it still fail open).
- Escalation DMs are throttled 60s per user per group (existing `_kb_escalation_cooldown`).
- A real answer starting with the words "No answer…" is not misclassified as the sentinel
  (underscore-token match only; unit-smoke-tested).

---

## `d098eec` — fix paid custom-bot profile description crash
**Date:** 2026-07-13 · **Risk:** low · **Touches:** custom-bot startup (cosmetic profile text)

### What changed
`bot_manager.py:3328` read `bot_rec.settings`, but the `Bot` model has no `settings` column,
so the paid-tier branch raised AttributeError on every paid custom-bot start (seen in prod as
`Bot 9/11: set_my_description failed`). Effect: paid/white-label bots never got their profile
description set, AND — because the crash skipped both calls — a bot upgraded from free kept its
"Powered by Telegizer" short description stuck forever. Fixed with a `getattr` guard; paid bots
now get a neutral default and their short description is cleared of Telegizer branding. Reads an
optional `bot_description` / `bot_short_description` if a settings dict is ever added later.

### To revert
```bash
git revert d098eec
git push origin main
```
Pure cosmetic (bot profile text). No data, billing, or deletion impact. No kill switch needed.

---

## `9af3685` — retention: make the dry-run preview visible on every deploy
**Date:** 2026-07-13 · **Risk:** low · **Touches:** scheduling only (no deletion behaviour change)

### What changed
The first deploy of `26f201e` ran the dry-run once and claimed the daily `scheduled_job_runs`
slot, so the next deploy skipped it and the preview numbers were locked out for 24h. Now,
**while in dry-run** the sweep reports on the first scheduler tick after every deploy and then
hourly (in-memory counter, read-only). **Real deletion is unchanged** — still gated to once per
day via the DB claim so a redeploy can't re-fire it.

### To revert
```bash
git revert 9af3685
git push origin main
```
Reverting only restores the buried-preview behaviour; it does not affect what gets deleted.
Kill switch is unchanged: `RETENTION_ENABLED=0`.

---

## `957dedb` — Guildizer: retention sweep + XP roll-up
**Date:** 2026-07-13 · **Risk:** medium · **Touches:** data deletion (Guildizer only)

### What changed
The same sweep as `26f201e`, ported to Guildizer (`discord-board/backend/retention.py`).
Logic **copied, not imported** — it touches only Guildizer's engine and models. Runs as a
24-hour loop on the Discord bot. Prunes `xp_events` (with roll-up into a new `xp_monthly`),
`admin_audit_logs` (365d), `protection_events`, `feature_usage_events`, `bot_health_events`.

### To revert
```bash
# INSTANT, no deploy — Railway → Guildizer bot service → Variables:
#   RETENTION_ENABLED=0

git revert 957dedb
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Removes the sweep. No further rows are deleted.
- ⚠️ Does NOT restore already-deleted rows — but XP is preserved in `Member.xp` (never
  touched) and archived in `xp_monthly`. **No member's XP or level changes.**
- ⚠️ Leaves the `xp_monthly` table in place. Harmless; it holds your archived history.
  Do not drop it.

### Two traps found while building this — do not undo these
- **`guild_events` is NOT a log.** Despite the name it's the Discord *scheduled events*
  feature (`start_at`/`end_at`) — real user content. It is deliberately **excluded** from
  the sweep. **Never add it.**
- **`member_stats.xp_by_user()` sums the WHOLE ledger when `since=None`.** That would
  under-report once the table is pruned. It is safe *only* because `crm_api.py:58` and
  `leveling_api.py:173` both guard with `period != "all"` (all-time reads `Member.xp`
  instead). **That guard is now load-bearing — do not remove it.**

---

## `26f201e` — cost audit: retention, AI limits, per-message query storm, TTL leaks
**Date:** 2026-07-13 · **Risk:** medium · **Touches:** money, data deletion, bot hot path

### What changed
1. **AI token limits** — Pro was advertised at 500k/day but *enforced* at 200k. Now 200k
   in all three places. Platform spend cap $50/day → $5/day.
2. **`backend/retention.py` (new)** — daily sweep. Rolls expiring `xp_events` into a new
   `xp_monthly` table, then prunes it plus six other append-only tables.
3. **`official_bot.on_message`** — was opening 8 Flask app contexts and re-querying the
   same group row 4+ times per message. Now reads settings once and gates on them.
4. **`backend/utils/ttl_map.py` (new)** — three module dicts leaked one entry per user
   forever; swapped for a self-pruning `TTLMap`.

### To revert
```bash
# FIRST, if the problem is data deletion — this is instant, do it before anything else:
#   Railway → web service → Variables → RETENTION_ENABLED=0

# Full revert of the commit:
git revert 26f201e
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Restores Pro to advertising 500k/day (and back to enforcing 200k — i.e. **it puts the
  customer-facing bug back**). Prefer changing the numbers over reverting this part.
- ✅ Restores the $50/day AI spend cap.
- ✅ Removes the retention sweep. **No further rows are deleted.**
- ✅ Restores the old per-message query behaviour and the plain dicts.
- ⚠️ **Does NOT bring back rows already deleted.** If the sweep already ran with
  `RETENTION_DRY_RUN=0`, those `xp_events` rows are gone — but their **XP is preserved**
  in two places: the `Member.xp` / `OfficialMember.xp` lifetime columns (never touched)
  and the `xp_monthly` archive. **Nobody's XP or level changes either way.**
- ⚠️ The `xp_monthly` and `xp_events` tables are left in place by a revert. Harmless —
  an unused table costs nothing. Do not drop them; they hold your archived history.

### Partial reverts (safer than the whole thing)
| To undo just… | Do this |
|---|---|
| the data deletion | `RETENTION_ENABLED=0` (instant, no deploy) |
| the AI limit change | edit `AI_TOKEN_LIMITS`, `PLANS['pro']`, `ai_config.AI_DEFAULTS`, `Pricing.js` — **all four, or they drift apart again** |
| the spend cap | `MAX_DAILY_AI_SPEND_USD=50` |
| the hot-path change only | `git revert 26f201e -- backend/official_bot.py` |

### Safety properties (verified, not assumed)
- Nothing in the codebase reads an `xp_event` older than **30 days**; we prune at **180**.
- The delete feeds the archive **in one transaction** — a crash rolls back both, so a
  re-run can neither double-count nor drop an unarchived row. Tested.
- Deletes are **batched at 5,000**. A single large `DELETE` would lock the table and stall
  the bots — that is the real danger here, and it is handled.
- The hot-path feature gate **fails open**: if settings can't be read, the feature still
  runs. A database blip can never silently disable something a customer paid for. Tested.

---

## `f496071` + `e972d53` + `79647f3` — Railway cost leak / celery-worker idled
**Date:** 2026-07-10 → 2026-07-12 · **Risk:** medium · **Touches:** infrastructure

### What changed
`celery-worker` was idled. Every Celery task was calling `create_app()`, which started a
duplicate set of bots and a second scheduler loop — up to 200× per worker child. All 19
jobs moved into the web service's in-process scheduler (`_scheduler_loop` in
`backend/app.py`). Bill went $34 → ~$11.

### To revert
```bash
git revert f496071    # GDPR sweep back to daily
git revert e972d53    # celery-worker back on
git push origin main
```
**Order matters** — revert `f496071` first.

### Notes
- The Celery task bodies in `backend/scheduler.py` were **never changed** and are still
  decorated. Celery can be switched back on without a revert: see the 4-step re-enable
  path written in `railway.worker.toml`.
- ⚠️ The `scheduled_job_runs` table is what stops a redeploy from re-firing daily jobs.
  If you revert and daily emails go out twice, that table is why.

---

## `507db0f` + `4963903` — bot deletion failed with "unexpected error" (FK violation)
**Date:** 2026-07-20 · **Risk:** medium · **Touches:** data deletion

### What changed
- Deleting a custom bot from the dashboard returned a 500 for any bot that had ever been
  used. `DELETE /api/bots/<id>` relied entirely on the `Bot.groups` ORM cascade, but four
  foreign keys have neither an ORM cascade nor a DB-level `ondelete`:
  `telegram_group_link_codes.bot_id`, `auto_responses.group_id`,
  `reported_messages.group_id`, `engagement_campaigns.group_id`. Postgres rejected the
  DELETE, and the generic 500 handler hid the reason.
- The cleanup lives in `purge_bot_dependents(bot)` in `backend/models.py`, mirroring the
  existing `_purge_user_data()` in `routes/auth.py`. Campaigns are removed one at a time
  through the ORM so their own cascade takes their tasks, custom fields and submissions
  with them — a bulk delete would have orphaned those.
- The whole delete is now wrapped in `try/except` with a rollback, so a failure leaves the
  bot intact instead of leaving a half-torn-down session, and the real exception is logged.
- **A follow-up cross-check found the same wall on three more paths**, all now calling the
  same helper:
  - `routes/custom_bots.py` `delete_custom_bot` — deletes the mirrored `Bot` row.
  - `routes/auth.py` `_purge_user_data` — self-serve account deletion. `User.bots` cascades
    into groups, so **GDPR right-to-erasure was broken** for any user who had ever used a
    bot. This is the most serious of the four.
  - `scheduler.py` GDPR purge job — same loop, same failure.

### To revert
This fix landed as **two commits**, and `507db0f` alone is not revertable — `4963903`
rewrote the same hunk in `bots.py` and moved the cleanup into `purge_bot_dependents()` in
`models.py`. Reverting only `507db0f` conflicts in `bots.py`; forcing that resolution
leaves `routes/bots.py` importing a helper that no longer exists, which is an ImportError
at startup for the whole bots blueprint — a worse outage than the bug.

Revert both, newest first. `REVERT.md` conflicts (both commits edited it) and is restored
untouched, since docs do not need to roll back to fix production:

```bash
git revert --no-commit 4963903 507db0f
git checkout HEAD -- REVERT.md
git commit -m "revert: bot-delete FK fix (507db0f + 4963903)"
git push origin main
```

Verified 2026-07-20: this sequence applies with **zero conflicts** in the code, and the
resulting tree compiles with no dangling `purge_bot_dependents` references.

### What revert restores, and what it does NOT
- ✅ Restores the previous code path. Bots that still have any of those four row types
  become undeletable again (the original bug) — nothing worse than that.
- ⚠️ Reverting brings back the **broken GDPR erasure path** in `routes/auth.py` and
  `scheduler.py`: account deletion fails for any user who has ever used a bot. If you
  revert for a bot-deletion problem, you have re-broken right-to-erasure — treat that as
  a live compliance issue, not a dormant one.
- ⚠️ Bots already deleted under this commit are **gone**, along with their groups, members,
  auto-responses, reported messages and engagement campaigns (including campaign
  submissions and any XP already spent proving them). A revert does not bring back a
  single row.
- ⚠️ There is no soft-delete or archive on this path. It was destructive before this
  commit and it is destructive after.

### Kill switch (if any)
None, and none is warranted — this is a bug fix on an admin-initiated, explicitly
confirmed action, not a background job. To stop deletions entirely you would have to
revert. The blast radius is one bot per deliberate click.

### Safety properties (verified, not assumed)
Verified by building a throwaway SQLite DB from the real models with `PRAGMA
foreign_keys=ON` and driving the actual endpoint through a Flask test client:
- The bug reproduces on the old code path — `sqlite3.IntegrityError: FOREIGN KEY
  constraint failed` — and the fixed endpoint returns 200 with all six row types gone.
- The four FKs are the **complete** set, established by walking the delete closure over
  `db.metadata` (every table reachable from `bots`, and every FK pointing into them),
  not by grep. That audit now reports zero unhandled FKs.
- All five delete paths pass — helper, dashboard endpoint, custom-bot delete,
  `_purge_user_data` + `delete(user)`, and the scheduler loop — leaving zero orphan rows.
- The DB-level `ondelete` clauses the closure relies on (`bot_group_commands`,
  `escalation_events`, `engagement_submissions.task_id`, `auto_reply_logs`) were checked
  against git history and `migrate.py`: each was present when its table/column was first
  created, so production's constraints match the models. `db.create_all()` never alters
  an existing table, which is what made this worth checking.
- Campaign **tasks** are removed too, confirming the per-campaign ORM delete keeps the
  campaign's own cascade working (a bulk `.delete()` here would have orphaned them).
- Deleting bot A leaves bot B fully intact — row, group, auto-response, reported message,
  campaign and link code — even under the same owner.
- Official-bot-lineage rows (`group_id IS NULL`, anchored on `telegram_group_id`) survive
  deletion of a custom bot sharing the same Telegram group. Scoping is by `group_id IN
  (this bot's groups)`, never by `telegram_group_id`.
- Ownership is still checked first (`Bot.query.filter_by(id=bot_id, user_id=user.id)`), so
  the cleanup can only ever reach the caller's own groups.
- Single commit at the end; any exception rolls the whole thing back, so a partial
  teardown cannot be left behind.

⚠️ Verified on SQLite, not Postgres. The FK topology is identical, but production is
Postgres — the first real delete is still the real proof.

### Known adjacent bug, NOT fixed here
`routes/admin.py delete_user` (`DELETE /api/admin/users/<id>`) calls `db.session.delete(user)`
without ever calling `_purge_user_data()`. It will fail on dozens of `users.id` FKs, not just
the bot ones — a broader pre-existing bug, deliberately left alone to keep this commit
scoped. Fix is likely one line (call `_purge_user_data(user)` first) but needs its own
verification pass.

---

## `8738c9b` — groups the bot is in but that never linked were invisible
**Date:** 2026-07-20 · **Risk:** low · **Touches:** bot hot path (logging only)

### What changed
- Reported symptom: a group was added to the official bot, the bot worked in it, but
  the group appeared nowhere on the website.
- Auto-link on join only fires when whoever added the bot has their Telegram connected
  to a website account (`_user_by_tg_id`). When it doesn't fire, the group is left with
  `owner_user_id = NULL` — and was then invisible in **both** places that could show it:
  - `GET /api/telegram-groups` filters on `owner_user_id == you` → no match.
  - `GET /api/telegram-groups/pending` filtered on `bot_status == "pending"`, but
    `on_my_chat_member` calls `_refresh_permissions` right after `_upsert_group`, which
    sets the status to `"active"` before linking is attempted. So the pending list could
    only ever show groups where *fetching permissions failed* — exactly backwards.
  - It wouldn't have helped anyway: `getPending()` existed in `api.js` but was never
    called anywhere in the frontend.
- `get_pending_groups` now keys off `owner_user_id IS NULL` + `bot_status != "removed"`,
  and `MyGroups.js` shows a banner listing those groups with the `/linkgroup` instruction.
- **Security fix in the same endpoint:** it previously returned *every* unlinked group on
  the platform to *any* logged-in user (titles, usernames, member counts). Harmless while
  nothing called it, a live leak the moment it was wired into the UI. Now scoped to groups
  the caller personally added the bot to, proven by the `bot_added` event in `bot_events`.
- The auto-link failure was logged at `debug`, which is why this was invisible in the
  logs. Raised to `warning` with a traceback, plus an `info` line for the common case
  (adder has no linked website account).

### To revert
```bash
git revert 8738c9b
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Fully reversible. No schema change, no data migration, no writes to existing rows —
  this only changes which rows a read endpoint returns, plus log levels and one banner.
- ⚠️ Reverting restores the information leak described above. If you revert this, do not
  wire `getPending()` into the UI.
- ⚠️ Groups linked while this was live stay linked. Reverting does not unlink them.

### Kill switch (if any)
None needed — nothing here runs in the background or touches money or data. To hide the
banner without a deploy, the endpoint can be made to return `{"groups": []}`.

### Safety properties (verified, not assumed)
Verified against a throwaway SQLite DB with the real models, driving the endpoint through
a Flask test client:
- The old filter finds **nothing** for a group in the reported state (bug reproduced), and
  the new endpoint surfaces exactly that group.
- A second user does **not** see the first user's unlinked group, and vice versa —
  each sees only their own.
- An already-linked group does **not** appear in the pending list.
- Claiming still requires a valid `/linkgroup` code; this change only makes the group
  visible. No new way to take ownership of a group was added.
- Frontend builds clean; the banner reuses the existing link dialog.

### Note for whoever reads this next
The real root cause is that `_refresh_permissions` sets `bot_status = "active"` before
linking is attempted, so `"pending"` never means what its name suggests. This commit works
around that rather than fixing it, because other code reads `bot_status`. If you touch that
field's lifecycle, revisit this endpoint.

---

## `e74dbc3` — unlinked-groups banner resurfaced groups the user had removed
**Date:** 2026-07-20 · **Risk:** low · **Touches:** dashboard reads only

### What changed
Two bugs found immediately after `8738c9b` shipped, one of them caused by it.

1. **The banner showed groups the user had deliberately removed.** `unlink_group` does not
   delete the row — it sets `owner_user_id = NULL` and `bot_status = "pending"`. That makes
   a deliberately removed group indistinguishable from one that never linked, so the new
   banner offered all 9 of them back as "waiting to be linked". `get_pending_groups` now
   compares the newest `bot_added` event against the newest `group_unlinked` event and
   suppresses the group when the removal is the more recent of the two. A group whose bot
   is added *again* after a removal still surfaces — that is a real new join.

2. **Official-bot view was missing groups (pre-existing, not from `8738c9b`).**
   `link_group` set `linked_via_bot_type = "official"` but never cleared `linked_bot_id`.
   A group re-linked to the official bot kept its stale custom-bot pointer, so it showed
   the "Official Telegizer" badge in the all-groups list (which reads `linked_via_bot_type`)
   yet was filtered out of the official view (which also required `!linked_bot_id`). Fixed
   at the source — `link_group` now clears `linked_bot_id` — and the frontend filter was
   aligned with the badge so **existing** rows display correctly with no data migration.

### To revert
```bash
git revert e74dbc3
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Fully reversible. Read-path and one write of `linked_bot_id = None` on link; no schema
  change, no migration, no deletion.
- ⚠️ Reverting brings back the banner offering removed groups, and re-hides official groups
  that carry a stale `linked_bot_id`.
- ⚠️ `linked_bot_id` values cleared by a link performed while this was live are not
  restored by a revert. They were stale pointers to a bot no longer managing the group, so
  losing them is the intended outcome, but it is not undone.

### Kill switch (if any)
None needed. To hide the banner without a deploy, make the endpoint return
`{"groups": []}`.

### Safety properties (verified, not assumed)
Driven through a Flask test client against SQLite built from the real models:
- never-linked group → shown; deliberately unlinked → hidden; unlinked-then-re-added →
  shown again; another user's group → hidden; currently linked → hidden.
- The earlier `8738c9b` test suite still passes unchanged (no regression to the privacy
  scoping).
- Frontend builds clean.

### Note for whoever reads this next
`unlink_group` deliberately keeps the row and nulls the owner. Any future "is this group
orphaned?" logic has the same trap: absence of an owner does **not** mean the user wants
the group back. Check the `group_unlinked` event before assuming.

---

## `7171105` — /rank card: 960x640 readable template, avatar, render cache
**Date:** 2026-10-10 · **Risk:** low · **Touches:** hot path (`/rank` in the official bot and custom bots)

### What changed
- `/rank` in custom bots and in the official bot (`official_bot.py::_show_rank`) now sends a 960x640 card (`backend/bot_features/rank_card.py`) with
  the caption `{name} · Rank #{rank} · Level {level}` / `{n} XP to Level {next}`.
- Fetches the member's Telegram profile photo (3s timeout, cached 1h); initials if unavailable.
- Renders off the event loop and caches PNGs in memory (key = every displayed value).
- Bundled fonts `backend/assets/fonts/` (Noto Sans + Noto Sans Arabic, SIL OFL); new deps
  `arabic-reshaper`, `python-bidi` (pure Python, used to shape Urdu/Arabic names).
- Names the bundled fonts can't draw correctly (CJK, Indic, ...) show `@username`, else
  `Member`, on the image; the caption always has the full name. Emoji are dropped from the image.

### To revert
```bash
git revert <sha>
git push origin main
```

### What revert restores, and what it does NOT
- ✅ The previous 600x160 card.
- ⚠️ Cards already posted in chats stay as they are. The official bot goes back to its
  text-only `/rank` reply; the role line is not shown on the card.

### Kill switch (if any)
Set `RANK_CARD_IMAGE=off` in the Railway env of every service running bots: `/rank` then replies with
the plain-text summary (also the automatic fallback if rendering or sendPhoto fails). Restart
is automatic on variable change; no deploy needed.

### Safety properties (verified, not assumed)
- Level thresholds match `DatabaseManager._calculate_level` for XP 0..20,000 and 10^7, 10^9.
- Cache keys differ for any change in rank, XP, level, name or avatar.
- Not yet checked: rendering inside a real Telegram client.

---

## `a0d3e97` — Keep level/role in step with XP (penalties, campaign rewards, rank card)
**Date:** 2026-10-10 · **Risk:** low · **Touches:** live member data (level, role)

### What changed
- Official bot XP penalty and official campaign reward now recompute `OfficialMember.level`
  from XP (they used to change XP only, leaving a stale level).
- Custom-bot XP penalty now also recomputes `Member.role` using the same level-to-role rule
  as `add_xp`, but only when the level actually changed.
- `/rank` (text and card, both bots) now derives the level from XP instead of reading the
  stored level column.

### To revert
```bash
git revert <sha>
git push origin main
```

### What revert restores, and what it does NOT
- ✅ The previous behaviour (level and role only change when XP is added).
- ⚠️ Levels and roles already changed by a penalty or reward while this was live are NOT
  restored. A custom-bot member who lost a level-based role keeps that loss until the next
  XP gain recalculates it. No existing rows were bulk-updated by this change.

### Kill switch (if any)
None. The change is three one-line recalculations; use the git revert above.

### Safety properties (verified, not assumed)
- SQLite run on the real models: a custom penalty of -200 from 250 XP moved level 3 to 1 and
  role `veteran` to `member`; a penalty that did not change the level left a manual role alone;
  an official campaign reward of +250 moved XP 90 to 340 and level 1 to 4.
- Card level and "XP to next level" are correct for a stale stored level under both rules.
- Not tested: the official-bot penalty line itself (it is async inside the message handler);
  it is the same one-line call as the tested reward path.

---

## `c257f45` — moderation accuracy, review-only AI mode, duplicate-event protection, safe AI reply sender
**Date:** 2026-10-12 · **Risk:** medium · **Touches:** bot hot path (automod Layers 2 and 3, AI answer delivery)

**Frontend for the same work:** `53be474` (UI only; reverting it hides the new controls but does not
change bot behaviour). Revert it first if only the screens misbehave:
```bash
git revert 53be474
git push origin main
```

**What changes for existing groups.** Saved configuration is kept as it is (nothing is migrated, no
threshold or punishment is reset, `ai_mode` defaults to `enforce`). Moderation DECISIONS do change: some
messages that were removed before are now allowed (questions and scam warnings that merely mention a
promo phrase), and a saved smart-moderation bypass list now actually matches (see below).

### What changed
- Layer 2 promo detection is split into strong solicitation phrases (unchanged, always a match, even
  when quoted) and ambiguous topic phrases. A call to action ("sign up using", "invest now", "use my
  code") counts as soon as the message points at an untrusted link or @handle, even if phrased as a
  question or introduced as a "scam warning". A bare topic phrase ("referral code", "presale") needs an
  untrusted link/@handle and must not be a question or warning. Links on the group's external-links
  whitelist never count. Bare "presale"/"100x" are NOT removed on their own. One shared function
  (`promo_rule_match`) serves the custom-bot and official-bot lineages.
- Layer 3 AI prompt v2 (message wrapped as data, replied-to text as context, "when in doubt answer ok").
  The model's own high/low label is the only "confidence" and it is NOT a calibrated probability: a
  low-confidence removal verdict becomes `uncertain` (logged, no action). Malformed output or a provider
  error is `unavailable` (logged as failed, no action). A confirmed-acceptable verdict is recorded as
  `acceptable` only in review mode.
- New opt-in per-group setting `automod.smart_mod.ai_mode` (`enforce` default, `observe` = log only).
- Before a delayed AI verdict is applied the live config is re-read: still enabled, observe vs enforce,
  current action and warn flag, trusted list, and whether the sender became an admin meanwhile. If the
  config cannot be re-read nothing is punished.
- Retried or re-delivered updates (same chat + message id + edit date) are moderated once; the retry
  gets the first delivery's result and sends no second warning, punishment or notice.
- Bug fix: `smart_mod.trusted_users` is saved as strings (admins API) but the bot compared an integer
  id, so a saved bypass never matched. It now compares as strings. Stored values are unchanged. The
  official bot now honours the list too (the custom bot already tried to).
- Audit rows record layer, rule, intended action, executed action and prompt version.
- AI answers are sent through one helper that keeps paragraphs, splits on paragraph boundaries and falls
  back to plain text ONLY when Telegram confirms it rejected the Markdown (never after a timeout).

### To revert
```bash
git revert c257f45
git push origin main
```

### What revert restores, and what it does NOT
- ✅ The previous Layer 2 phrase matching, Layer 3 prompt, string-vs-int comparison, and reply sender.
- ⚠️ Messages deleted, warnings issued and members muted or banned while this was live are NOT restored.
- ⚠️ Messages that this let through, and that you would have removed, stay posted.
- ⚠️ `ai_mode` values already saved stay in group settings (ignored by the old code).

### Kill switch (if any)
- `MODERATION_PROMO_CONTEXT_GUARD=0` (Railway variable, ~30 s): Layer 2 goes back to removing on any
  matching phrase. Layer 3 review mode is the per-group "AI verdict handling" setting.

### Safety properties (verified, not assumed)
- `test_moderation_accuracy.py`, `test_moderation_hardening.py`: labelled promo matrix including
  promotional questions, misleading warnings and quoted solicitations; verdict taxonomy; stale-config
  re-validation; duplicate events; Markdown fallback; string/int trusted ids.
- Not verified: real Telegram delivery, a real AI provider, multi-process duplicate delivery (the
  de-duplication is in-process; the bots run inside the single web process).

---

## `c257f45` — knowledge sources: extracted-text preview, versions, opt-in schedules, controlled X sync
**Date:** 2026-10-12 · **Risk:** medium-high · **Touches:** money (paid X/twitterapi.io usage), a new background job, data deletion (source removal), the AI answer prompt

**One commit carries both this entry and the one above** (they share prompt and test code), so `git revert` undoes both together. To switch off only one part without a deploy, use that entry's kill switches.

**What changes for existing groups.** Every existing source stays on Manual and enabled. Nothing is
fetched automatically until an owner picks Daily / Every 3 days / Weekly. Sync of an existing source now
also records a version row; answers still come from the same KnowledgeDocument chunks. The AI answer
prompt now labels retrieved chunks with their source type and the dates actually known.

### What changed
- New columns on `knowledge_sources` (all nullable or defaulted) and new tables
  `knowledge_source_versions`, `knowledge_sync_ledger`, `knowledge_sync_cooldowns`. Added both to
  `backend/migrate.py` and to the app-start `knowledge_sources` migration; new tables come from
  `db.create_all()`.
- Sync (`KnowledgeBaseSystem.sync_external_source`): fetch, validate, chunk, embed, and only then swap
  in one commit. Failed fetch, login page, empty extract or failed embedding keep the old version.
  Unchanged content (hash) is not re-embedded. Last 5 versions keep their text; only the active one is
  searchable. Rollback re-indexes the chosen version (explicit button, costs embeddings).
- X sync (twitterapi.io, existing `TWITTERAPI_IO_KEY` credential): shared rolling 24h cooldown per
  credential + workspace + handle, claimed atomically before any fetch; budgets reserved before the
  fetch at source (60 pages / 30 d), workspace (15 pages / day) and shared credential (100 pages / day)
  level; at most 3 pages per run; bounded first import (60 posts); incremental stop at the high-water
  post id; resumable cursor when the page cap ends a run early; edits and deletions reconciled inside
  the newest page; 429 honours Retry-After (capped at 48 h); 401/402/403 stop and pause the schedule;
  3 consecutive failures pause the schedule. A failed attempt still counts.
- Schedules are opt-in per source and run from the in-process scheduler job `knowledge_source_sync`
  (every 10 min, at most 3 sources per tick). Pro is re-checked at run time.
- "View extracted text" drawer and version list read stored rows only (no provider call, no AI call).
- Retrieval: a disabled source is excluded; chunks carry a label with source type, publication date or
  "publication date unknown", and fetch/upload date. The prompt says a fetch/upload date is NOT a fact
  date and adds a `CONFLICT` verdict that takes the existing no-answer / escalation path and logs the
  conflicting sources in AI Activity.

### To revert
```bash
git revert c257f45
git push origin main
```

### What revert restores, and what it does NOT
- ✅ The previous manual-only sync, previous prompt, previous source routes.
- ⚠️ The new columns and tables STAY (they are additive and unused by the old code). Nothing is dropped.
- ⚠️ Stored version history, ledger rows and cooldown rows are not deleted. Schedules already saved
  simply stop running. Text already indexed from a sync stays indexed.
- ⚠️ Provider usage already spent (twitterapi.io credits, embedding tokens) cannot be refunded.
- ⚠️ A source removed while this was live is gone together with its stored versions.

### Kill switch (if any)
Railway variables, ~30 s, no deploy:
- `KNOWLEDGE_SCHEDULED_SYNC_ENABLED=0` stops every scheduled run (manual sync still works).
- `KNOWLEDGE_X_SYNC_ENABLED=0` stops all X syncing, manual and scheduled.
- `KNOWLEDGE_SOURCES_ENABLED=0` stops all external source syncing (existing switch, now honoured by
  the scheduler too).
- Budgets can be tightened without a deploy: `X_SYNC_COOLDOWN_HOURS`, `X_SYNC_MAX_PAGES_PER_RUN`,
  `X_SYNC_SOURCE_PAGES_PER_30D`, `X_SYNC_WORKSPACE_PAGES_PER_DAY`, `X_SYNC_CREDENTIAL_PAGES_PER_DAY`,
  `X_SYNC_MAX_CONSECUTIVE_FAILURES`. The credential figure is only the knowledge feature's slice of the
  shared platform key; the rest stays for Campaign verification.

### Safety properties (verified, not assumed)
- `test_knowledge_sources.py` and `test_knowledge_sources_wiring.py` (provider calls mocked): fact
  replacement retires the old chunks, unchanged fetch, login page / empty extract / failed embedding
  keep the active version, rollback, disable/remove, atomic cooldown, shared window across sources,
  workspace and shared-credential budgets, failed attempts still counted, 429, invalid credentials,
  partial pagination resume, edit/delete reconciliation, Pro enforced server-side on both lineages,
  group isolation, scheduler only runs due opt-in sources, kill switch, plan lapse.
- Not verified: a real twitterapi.io account (response field names follow its documentation and
  existing connector code), real Postgres locking (the advisory lock is only exercised on Postgres),
  and how a second web worker behaves (production runs one worker; the cooldown claim is atomic in the
  database either way).
- Known limits: X edits/deletions are reconciled only inside the newest page of posts (the connector
  has no edit feed); expired-campaign claims in a feed are not auto-expired; cooldown is per workspace +
  handle, so a second group of the same owner pointing at the same handle waits for the same window
  and has no text until the first sync of its own.

---

## Template — copy this for the next change

```markdown
## `<sha>` — <one-line summary>
**Date:** · **Risk:** low/medium/high · **Touches:** money / data deletion / hot path / plan limits

### What changed
<plain English, 2–4 bullets>

### To revert
​```bash
git revert <sha>
git push origin main
​```

### What revert restores, and what it does NOT
- ✅ …
- ⚠️ … (especially: anything deleted, sent, or charged is NOT undone by a revert)

### Kill switch (if any)
<env var that disables it in 30s without a deploy>

### Safety properties (verified, not assumed)
- …
```
