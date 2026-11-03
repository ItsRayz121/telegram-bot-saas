# Telegizer ↔ Guildizer parity audit (Phase 1)

Date: 2026-11-04. Method: read from the code, not the marketing site.
Sources: `frontend/src/config/featureRegistry.js`, `frontend/src/pages/guildizer/*`,
`backend/billing_config.py`, `discord-board/backend/*`, `TELEGIZER_FEATURE_MAP.md`,
`discord-board/docs/TELEGIZER_FEATURE_AUDIT.md`, `discord-board/PARITY_CHECKLIST.md`.
No UI was run in a browser for this pass; "Present" means the code path exists, not that it was exercised live.

## Headline

The pasted review assumed Guildizer's navigation and resource layout were out of line with Telegizer.
The code says otherwise. Most of its "Phase 2/3" work is already done:

| Review claim | What the code shows |
|---|---|
| Shared shell and navigation | Guildizer UI is embedded in the same React app and reuses `GuildizerCollapsibleCard` plus the Telegizer tab/subtab layout (`GuildizerServerDetail.js:48-64`, comment says "match the Telegizer category pills 1:1"). |
| Same settings structure | Moderation, Members, Engagement, AI & Integrations, Automation, Analytics, Settings use the same names and order. Shared subtabs keep Telegizer's positions; Discord-only extras trail. |
| One bot-card system, Stop/Start, Add Server, Analytics, Delete, Unlink with confirms | Present in `GuildizerBots.js` (Stop/Start at L238, confirm dialog for Delete and Unlink at L144, Add Server at L316/L403). Shipped in 2868519 and eb38682. |
| Servers directly accessible | `GuildizerServers.js` plus `GuildizerManageServers.js`. |
| Separate connection / permission / sync status | Partly. Real bot status now drives server cards (eb38682). A dedicated permission/intent diagnostic is not confirmed; see gaps. |

## Subtab parity (Telegizer registry vs Guildizer `AREAS`)

| Area | Telegizer | Guildizer | Delta |
|---|---|---|---|
| Moderation | AutoMod, Behavior, Reports | same | none |
| Members | Verification, Welcome, XP & Roles | same + Self-roles | Discord extra |
| Engagement | Raids, Invite Links, Campaigns | same + Tickets, Starboard, Boosts, Events | Discord extras |
| AI & Integrations | Knowledge Base, Escalation | same | none |
| Automation | Scheduler, Auto Reply, Polls, Forwarding, Workflows, Webhooks | same + Threads | Discord extra |
| Analytics | Members, Leaderboard, Audit Log, Warnings, Digest, AI Activity | same + Overview | Discord extra |
| Settings | Team Access, Import & Export | Overview, Commands, Team, Billing, Import & Export | Discord has Billing/Commands inside Settings |

Result: no Telegizer subtab is missing from Guildizer.

## Slash commands (grep-extracted, so treat as a lead, not proof)

- Guildizer: ask, auditlog, ban, kick, leaderboard, mute, note(s), ping, purge, rank, remind(ers), removewarning, report, task(s)/done, tempban, unban, unmute, userinfo, warn, warnings.
- Telegizer handlers with no Guildizer counterpart found: `help`, `me`, `xp`, `roles`, `invitelink`, `groupinfo`, `admins`, `status`, `support`, `whois`, `unwarn`, `tempmute`, `assist`.
- Most are Telegram-specific (`start`, `linkgroup`, `wallet`/`mywallet`) or aliases (`unwarn` = `removewarning`, `tempmute` = `mute` with duration). Worth deciding on: `/help`, `/serverinfo` (groupinfo), `/xp`/`/me` (rank may already cover it), `/invite` stats.
- Per-guild custom commands exist (Settings › Commands), so the registry is not the whole command surface.

## Gaps and open items (ranked)

1. **Plan entitlements are inconsistent between marketing and enforcement (money-adjacent).**
   Enforcement is `_GATED_SECTIONS` in `backend/routes/settings.py` (mirrored by `PLAN_GATES.pro`): a free user cannot enable verification, levels, raids, knowledge_base, webhooks, scheduled_messages or assistant.
   - Webhooks: **fixed 2026-11-04.** `Landing.js` said Enterprise; enforcement, the pricing table and the gate list all say Pro. Landing card and Pro plan list now say Pro.
   - AI Knowledge Base: consistent (Pro) everywhere.
   - **Resolved 2026-11-04:** verification, XP & levels and scheduled messages were opened to Free (gate removed, kill switch `FREE_CORE_FEATURES_OPEN=0`, see REVERT.md `FREE-CORE`), so marketing and enforcement now agree. Not yet tested with a live free account.
   - Correction: an earlier draft cited "Free 3 / Pro 25" scheduling limits for Telegizer. Those numbers are from Guildizer's `discord-board/backend/plan_limits.py`, not Telegizer.
2. **Permission / gateway-intent diagnostics for Discord**: not confirmed as a dedicated screen. Telegizer has a permission checker; check whether Guildizer surfaces missing permissions, role hierarchy and privileged-intent state per server.
3. **Native Discord AutoMod rules**: PARITY_CHECKLIST 10.9 was a deferred stretch. `automod_sync.py` exists, so verify how far it got before building.
4. **Command inventory is not machine-generated.** The reviewer's "single inventory from source" does not exist yet. This file is the first manual cut.
5. **Open owner tasks from earlier work** (unchanged): `CUSTOM_BOT_LIFECYCLE_DRY_RUN=1` still silent until flipped; `YOUTUBE_API_KEY` unset on Discord services; prod `GROUP_TEAM_ACCESS_ENABLED=0`.

## What I would not do

- Rebuild the shared design system or navigation: it already exists in practice.
- Add a visual Trigger→Condition→Action rule builder as parity work. Telegizer has a Workflow builder; Guildizer has a Workflows subtab. Whether the Discord one reaches the same depth is unverified.
- Copy Telegizer pages into Guildizer. The existing approach (separate backend, shared UI shell) already avoids the divergence the review warns about.

## Recommended next steps

1. Decide the intended plan for scheduled messages and webhooks, then align `Landing.js`, `Pricing.js`, `PLAN_GATES` and `billing_config.py` (touches a live plan limit, so it needs a REVERT.md entry).
2. Audit Discord permission diagnostics and native AutoMod sync against the Telegizer permission checker.
3. Decide on the four missing slash commands (`/help`, `/serverinfo`, `/xp`, invite stats).
4. If you want the full command-by-command inventory, generate it with a script over handler registrations, jobs and `group_defaults.py` keys, then diff it against Guildizer's `settings.py` defaults.
