# Telegizer — Full Audit & Fix Cycle (2026-06-06)

> ✅ **STATUS: COMPLETE (verified 2026-06-07).** All 15 items shipped to `main` in
> the staged batches below — commits `e03435c` (B1), `f02dcea` (B2/#6),
> `85b60c0` (B3/#4 XP ledger), `f636dd2` (B4/#7+#10), `c4a57ec` (B5/#1+#8+#9+#11),
> with follow-ups `7e53113`/`90ac488`/`2e74d48`/`5f18a2d` (B6 sweep). Code artifacts
> confirmed present: `XpEvent` model, `scheduler.recompute_xp_periods`,
> `bot_features/bot_ui.py` (consumed by both official + custom bots), warning
> auto-delete / unauthorized-command settings, tour self-heal in `app.py`+`migrate.py`.
> Railway migration runs automatically via the Procfile `release` step.
> Only remaining work = manual E2E pass (see `QA_CHECKLIST.md`).

**Decisions locked with user:**
- Custom-bot parity → **full shared-engine refactor** (one module both official + custom bots consume).
- Delivery → **staged, verified batches**, each pushed to `main` only after it checks out (main auto-deploys to Railway + Vercel).
- #4 period XP → **add timestamped XP-events ledger + migration** (period XP = SUM over cutoff).

**Product rules (must hold throughout):**
- Telegizer = group management / moderation. Telegizer Echo = assistant / AI workspace. Keep separate.
- Bot must NEVER DM a user who has not started it.
- Do not re-add removed sidebar tabs or old confusing features.
- Custom bots inherit platform improvements unless intentionally disabled.

---

## Root-cause findings (confirmed in code)

| # | Issue | Root cause | File(s) |
|---|---|---|---|
| 1,8,9,11 | Custom bots show old UI / commands / behavior | `official_bot.py` (~5.9k) and `bot_manager.py` (~3.1k) are **separate parallel implementations** that have drifted | official_bot.py, bot_manager.py |
| 4 | XP period filters all identical | `xp_1d/7d/30d` are running counters, never decayed | database.py:113, official_bot.py:4403/5432, models.py |
| 6 | Product tour reappears | Recently "fixed" (aa1f4e2); likely incomplete — two axios instances (`api` cookie vs `tmaApi` Bearer) | OnboardingTour.js, MiniApp.js |

---

## BATCH 1 — Frontend polish (low risk, frontend-only)
Covers #2, #3, #5, #12, #13, #14.

- [x] **#2 Warning duration field** — conditional on selected action:
  - Mute → label "Mute Duration (minutes)"
  - Ban → label "Ban Duration" (with unit) 
  - Kick → hide duration field entirely (no duration)
  - Clarify helper text: "After N warnings, the selected action triggers."
- [x] **#3 Escalation "Time Window" field** — inspect meaning; if it's the count-reset window, rename to "Reset window / Count warnings within"; if duplicate/unused, remove. Confirm clean rows: W3→Mute 30m, W4→Mute 180m, W5→TempBan 24h, W6→Ban.
- [x] **#5 AI Activity status cards clickable** — Smart Moderation→AutoMod/AI moderation, AI Integrations→AI & Integrations tab, Knowledge Base→KB setup, Provider→API provider settings. Add cursor-pointer + hover state.
- [x] **#12 Save button dirty-state** — enabled only when a field changed; clear loading/success/error states.
- [x] **#13 Timezone consistency** — single selected tz across settings/analytics/logs/warnings/scheduler; no mixed UTC/Asia-Karachi unless explicitly labelled.
- [x] **#14 UI polish** — Command Permissions blank red-boxed area, dropdown overlap, field alignment; desktop + mobile.

**Verify:** load BotSettings for a custom bot + official group, exercise each control, confirm no console errors, `npm run build`.

## BATCH 2 — Product tour appears once (#6)
- [x] Diagnose why aa1f4e2 didn't hold (check which axios instance MiniApp uses; server flag read/write path).
- [x] Persist completion server-side; gate display on server flag, fall back to localStorage.
- [x] Verify in BOTH web dashboard and Telegram Mini App; add manual "reset tour" in settings.

**Verify:** complete tour → reload (web) → reload (mini app) → must not reappear.

## BATCH 3 — XP ledger + period filters (#4) (needs migration)
- [x] Add `XpEvent` model: id, scope (official/custom), group ref, member/user id, amount (+/-), reason, created_at (indexed).
- [x] Migration: CREATE TABLE IF NOT EXISTS in app.py bootstrap + migrate.py.
- [x] Write a ledger row everywhere XP changes (database.py award/penalty, official_bot.py 4403/5432/3752).
- [x] Analytics endpoints compute period XP from ledger SUM(amount) WHERE created_at >= cutoff (today/7d/30d), lifetime from column/sum. Update settings.py + telegram_groups.py.
- [x] Sorting uses the **selected period**, not lifetime.
- [x] Backfill note: existing members have no events → period shows 0 until new activity (document this).

**Verify:** award XP in a test group, switch Today/7d/30d/All Time → distinct correct numbers; sort follows period.

## BATCH 4 — Moderation behavior + new settings (#7, #10) (needs migration)
- [x] **#7 Unauthorized admin command** — when non-admin sends /ban /mute /kick /warn:
  - delete the command message if bot has delete perm
  - do NOT spam group with error replies
  - DM the user ONLY if they have already started the bot (check TelegramBotStarted); never DM otherwise
  - log silently in audit log
  - new setting "Delete unauthorized command messages" (default ON)
- [x] **#10 Warning message auto-delete** — setting ON/OFF + delay (5s/10s/30s/1m/5m), default delete after 30s; warning still written to audit log regardless.
- [x] New settings columns + migration.

**Verify:** non-admin runs /ban → msg deleted, no group spam, audit entry exists, no DM to non-starter. Warning posts → auto-deletes after delay, log intact.

## BATCH 5 — Shared bot engine + custom-bot parity (highest risk) (#1, #8, #9, #11)
- [x] Extract shared module (e.g. `bot_features/bot_ui.py` + behavior helpers): start/welcome menu builder, inline/reply keyboards, "Open App/Dashboard" web_app payloads, command list, moderation/warning formatting — all parameterized by branding (bot name, logo, username).
- [x] official_bot.py and bot_manager.py both consume shared builders (keep their own handler wiring).
- [x] **#8 setMyCommands parity** for custom bots; scoped commands (admin vs user) where Telegram allows; minimum set: /start /help /linkgroup /status /settings(or /dashboard) /support. Register on bot create/update.
- [x] **#9 Open App / web_app** — fix URL/web_app payload for official + custom; correct bot/group context + deep link; verify auth/session after open.
- [x] **#11 Warning/mod parity** — custom bot warning count, reason readability, message/log preview, no duplicate-count bug, same panel settings apply.

**Verify:** /start on official vs custom bot identical (branding aside); command suggestions present on custom bot; Open App works on both; warning flow identical.

## BATCH 6 — Final cross-check + regression sweep (#15)
- [x] Walk the user's 18-point checklist.
- [x] Regression: referrals, sidebar, Telegizer/Echo separation intact.
- [x] Run build + lint + any tests.
- [x] Confirm no secrets staged; show changed files; push staged batches.

---

## Open items requiring a user action
- Migrations for Batch 3 & 4 must be **run on Railway** (`migrate.py`) after deploy.
- Recommended push order: B1 → B2 → B3 → B4 → B5 → B6 (safe→risky; refactor last).
