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
| `MAX_DAILY_AI_SPEND_USD` | any number | Hard ceiling on platform AI spend per day. Set `0` to stop all platform AI. |
| `RETENTION_XP_DAYS` | e.g. `3650` | Effectively stops XP pruning without disabling the rest. |
| `ENGAGEMENT_PROMO` | `false` | Turns off the promo footer. |
| `USE_CELERY` | `1` | Re-enables Celery dispatch (see `railway.worker.toml` for the full 4 steps). |

---

# Change log — newest first

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

## `507db0f` — bot deletion failed with "unexpected error" (FK violation)
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
```bash
git revert 507db0f
git push origin main
```

### What revert restores, and what it does NOT
- ✅ Restores the previous code path. Bots that still have any of those four row types
  become undeletable again (the original bug) — nothing worse than that.
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
