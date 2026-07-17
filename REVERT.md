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

## `<pending>` — AI KB: professional no-answer handling + official-bot auto-reply
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
git revert <pending>
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
