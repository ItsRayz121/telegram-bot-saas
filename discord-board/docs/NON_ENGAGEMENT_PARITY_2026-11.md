# Guildizer — moderation, roles, XP, self-roles & non-engagement parity (Nov 2026)

Scope: the "FINAL Claude Code Master Prompt" brief. The Engagement → Campaigns / Raids mirroring
project is **excluded and was not touched**. Everything below was checked against the code in this
repository; "not verified live" means no test Discord server / production run was available.

## 1. Requirement table

| # | Requirement | Status | Code | Proof |
|---|---|---|---|---|
| 1A | Channel Slow Mode: multi-select, bulk apply, live read, per-channel rows, Turn Off never deletes | **Implemented** | `protection_api.py` (native-slowmode GET/POST), `NativeSlowmode.js` | `tests/test_native_slowmode.py` (5) |
| 1B | Server-wide Protection (bot-managed) clarified, advanced collapsed, enforcement unchanged | **Implemented (UI)**; excluded channels/roles & logging toggles **not added** (backend has none; would change enforcement) | `ProtectionTab.js`, `slow_mode.py` (untouched) | build + lint |
| 2 | Trusted Bots — Option A compact rows, search/add by name or ID, remove one, legacy IDs flattened | **Implemented** | `protection_api.py` (trusted-bots), `TrustedBots.js` | `tests/test_trusted_bots.py` (3) |
| 3 | Warning Escalation — Option A compact ladder, once per step, lookback window, preview | **Implemented**; reorder is meaningless (steps sort by warning #); "staff approval before ban" **not built** | `moderation_runtime.py`, `ProtectionTab.js` | `tests/test_warn_ladder_once.py` (3) |
| 4 | Role Hub — Option A compact rows, usage chips, create role, applications + approval queue, staff grant/revoke | **Implemented**; per-role "what it unlocks" is the existing wiring (self-select / auto / level) only — no custom Guildizer-feature mapping exists to show; award-source/audit history per member **not built** (audit events are written to `protection_events`, no viewer yet) | `RoleHub.js`, `roles_api.py`, `role_apps*.py` | `tests/test_roles_api.py`, `tests/test_role_applications.py` |
| 5 | Level → role milestones: level, required XP, create/choose role, stack/replace policy, privileged roles refused | **Implemented**; "staff approval for a rank" **not built** | `LevelingTab.js`, `level_roles.py`, `bot_core.py` | `tests/test_xp_penalty_modes.py`, `tests/test_roles_api.py` |
| 6 | XP penalties matrix: none / fixed / % of current / reset, preview, ledger, one debit per event | **Implemented** | `leveling.py`, `leveling_api.py`, `LevelingTab.js` | `tests/test_xp_penalty_modes.py` |
| 7 | Self-roles lifecycle: status badge, publish, update in place, unpublish (roles kept), cancel schedule, duplicate, server-side privilege block | **Implemented**; worker-crash-between-send-and-record can still double-post once (no distributed lock) | `self_roles.py`, `self_roles_api.py`, `SelfRolesSubtab.js` | `tests/test_roles_api.py::test_self_role_status_lifecycle`; **in-place edit not verified live** |
| 8 | Private reports/logs: one staff channel selector (already existed), public-visibility warning, test message | **Implemented**; weekly/monthly role reports and role-change event routing **do not exist** — separate gap, not faked | `protection_api.py` (log-channel/check), `LogChannelCheck.js` | `tests/test_native_slowmode.py::test_log_channel_check_flags_public_channels` |
| 9 | Settings → Overview → Roles: Option B Role Cards, count sort, search/type filter, member drawer | **Implemented** (counts from Discord's paginated member list; `unavailable`/`partial` shown honestly, bots excluded by default, @everyone separate) | `RoleDirectory.js`, `roles_api.py` | `tests/test_roles_api.py` (counts, unavailable≠0, drill-down, 403) |
| 10 | Non-engagement parity audit | See §3 | — | — |

## 2. Real defects found and fixed while doing the above

| Severity | Defect | Fix |
|---|---|---|
| **High (security)** | `POST /native-slowmode` never checked the channel belonged to the server — any manager could change a channel in **another** server the bot is in | every id is checked against the server's live channel list |
| **High (security)** | Self-role menus and level rewards could point at Admin/mod roles; only the click-time check stopped self-roles, and **level rewards had no check at all** | save-time guard (`role_policy.py`) + bot grant-time guard (kill switch `LEVEL_REWARD_SAFE_ONLY=0`) |
| Medium | Warning ladder re-fired the lower step on every later warning (#4 repeated #3's timeout) | steps fire once, on the crossing warning (kill switch `WARN_LADDER_ONCE=0`) |
| Medium | A warning that escalated cost two XP debits (warn + action) | one debit per event |
| Medium | Per-step "Within hrs, 0=all" silently ignored the global lookback | steps inherit the lookback unless they carry their own window |
| Medium | Custom-bot servers' native slowmode used the official bot's token | uses the serving bot's token |
| Low | Trusted-bot list accepted comma-joined/int legacy entries inconsistently | normalised on read |
| Low | Role list cache could hold 200 × 10k full member objects | compact cache, 50-guild cap, refresh throttled to 1 per 10 s |

## 3. Non-engagement parity matrix (evidence-based, not a fresh line-by-line re-audit)

The Oct 2026 port (`guildizer-parity-2026-10`, see `PARITY_CHECKLIST.md` phases 9–20) already
mirrored the Telegizer dashboard structure (6 category pills + Settings). This session did **not**
re-test those modules end to end; rows marked "not re-verified" rely on that earlier work.

| Module | Telegizer | Guildizer now | Gap type | Constraint | Priority | Status |
|---|---|---|---|---|---|---|
| Moderation → AutoMod / Behavior / Reports | present | present, improved this session | — | — | — | verified in code + tests |
| Warnings ladder | per-step ladder | per-step, once-per-step | fixed | — | P1 | done |
| Slow mode | native retired, smart only | native (per channel) + smart (server) | Discord-specific | Discord has native per-channel slowmode; Telegram doesn't | — | done |
| Verification / Welcome / Auto-roles | present | present | not re-verified | — | — | — |
| XP & Roles | levels, penalties | levels, penalties (now richer than Telegizer), milestones | Guildizer ahead | — | — | done |
| Self-roles | n/a (Telegram has no role menus) | Guildizer-only | Discord-specific | — | — | done |
| Roles directory / hub | n/a | Guildizer-only | Discord-specific | needs Server Members intent | — | done |
| Analytics / Digest / Audit log | present | present | not re-verified | — | — | — |
| Knowledge base, Automation | present | present (Oct port) | not re-verified | — | — | — |
| Team access | present | present (seats); prod flag `GROUP_TEAM_ACCESS_ENABLED=0` was the "temporarily disabled" cause | config | — | P1 (owner) | needs owner |
| Connection monitor / offline screen | main app only | Guildizer API calls don't feed the monitor | gap | — | P2 | open |
| Session revocation on logout | server-side | Guildizer session is stateless (cookie only) | gap | — | P2 | open |
| Weekly/monthly staff reports | n/a | none | gap | — | P3 | open (scoped plan: scheduled digest to the staff log channel; `digest_runtime.py` already exists for members' digest) |

## 4. Migration, deployment and rollback

* One new table, `role_applications` — additive, created by `init_db()`; no data migration, no existing row rewritten.
* New settings keys (`penalty_<kind>_mode`, `role_reward_mode`, `role_apps`) are optional; a missing key means the old behaviour, so every saved server behaves as before until an admin changes it.
* Deploy order: Guildizer API and the Discord Bot worker can go out together; the new `/applyrole` command registers on the bot's next start.
* Rollback: `REVERT.md` entries (4) list `git revert`, what it does not undo, and the kill switches `WARN_LADDER_ONCE`, `LEVEL_REWARD_SAFE_ONLY`, and the empty "roles open for application" list.
* **Owner action after deploy**: confirm the bot has the **Server Members intent** (Developer Portal) — without it role counts show "unavailable" and the trusted-bot picker lists nothing (add-by-ID still works).

## 5. Discord vs Telegram differences that are real

* Telegram has no roles, role menus, native per-channel slowmode set by bots, or a member list API — role features and the Role Directory are Discord-only by nature.
* Discord timeout (max 28 days) is the "temporary mute"; no separate mute was added.
* Role grants need Manage Roles and the bot's role above the target role; hierarchy failures are reported, not hidden.

## 6. Left unresolved (with reasons)

* Live Discord verification of in-place self-role edits, role creation, approval grants and bulk slowmode — no test guild available to this session.
* Staff-approval gate before severe ladder actions and before level ranks — would need a new pending-action queue; not built.
* Per-member role award history / audit viewer — events are recorded, no UI.
* Weekly/monthly reports, Guildizer API ↔ connection monitor, server-side session revocation (above).
