# Guildizer Campaigns <-> Telegizer Campaigns parity (2026-11-04)

Guildizer now uses **the same workspace pages as Telegizer** (`frontend/src/pages/campaigns/*`). Only the data layer and
the create / manage / edit forms are Discord-specific (`frontend/src/pages/guildizer/campaigns/GuildizerWorkspace.js`).
Raids are the `raid` campaign type in the one `campaigns` table, so there is a single system.

Routes: `/guildizer/servers/:guildId/campaigns` (Overview) · `/all` (Campaigns) · `/review` · `/new?type=` · `/:campaignId?tab=summary|submissions|results|activity|settings`

| Area | Telegizer | Guildizer | Status |
|---|---|---|---|
| Workspace tabs Overview / Campaigns / Review queue (+pending badge) | yes | same component | Done |
| Overview: stats, needs-attention, activity chart, running campaigns, 7/30/90d | yes | same component, fed by `campaign-workspace/overview` | Done |
| Campaigns list: search, status/type filters, sort, pagination, CSV export (all pages) | yes | same component | Done |
| Review queue: filters, search, flagged-only, detail, proof, Approve / Approve & next / Reject with reason | yes | same component | Done |
| Concurrent review (409 / stale) | yes | server guard `expected_status`; 409 mapped to the same toast | Done |
| Duplicate detection | flag + banner | flag + banner (`flagged`, `flag_reason`) | Done |
| Campaign page tabs Summary / Submissions / Results & rewards / Activity / Settings | yes | same page; Submissions/Results/Settings use the Discord forms in page mode | Done |
| Lifecycle: publish, pause, reopen, close, archive (confirm dialog) | yes | `PUT {action}` (now covered by tests) | Done |
| Create: type picker -> wizard -> draft or publish, unsaved-changes guard | 4 steps | 4 steps (Basics / Tasks & proof / Schedule & rewards / Review & preview) with real embed preview | Done |
| Multi-task, typed proof fields, raid goals, X auto-verify, Giveaway winner picker | yes | yes (already existed) | Done |
| Post to channel / retry / delete post | yes | yes (`PostStatusCell`) | Done |
| Rewards: XP once per approval | yes | `leveling.add_xp` once; re-approve / double approve tested | Done |
| Per-action XP for raids (`settings.action_xp`) | yes | `campaign_rewards.py`: pays passed actions once, tops up later, kill switch `CAMPAIGN_ACTION_XP_ENABLED`; form fields, announcement and summary show it | Done |
| Exports: campaigns CSV, submissions CSV, leaderboard | yes | yes | Done |
| Raids merged into Campaigns | n/a | Engagement > Raids keeps the quick launcher; its list links into the workspace | Done |
| Member participation | Mini App task page | Discord buttons / modals / DM panel (no web page) | Platform difference |
| Member profile link from the queue | CRM drawer | links to the Members table, searched by Discord user id | Done (equivalent) |
| Timezone | per group | the viewer's browser zone (servers have no zone setting), shown on every page | Done (equivalent) |
| Viewer (read-only) role | yes | team seat `viewer` from `/team`: controls hidden, backend refuses writes | Done |

## What changed
- Backend `discord-board/backend/campaign_workspace.py`: responses now also carry Telegizer's field names
  (`items`, flat `submitted/approved/pending`, `status_counts`, `people`, `rewards`, `oldest_pending_*`, `who`, `payload`, `field_labels`...).
  Existing keys are unchanged. Read-only; no schema change, no migration.
- Frontend: shared pages call `ws.api` / `ws.ui` (context) instead of Telegram clients; Telegram values are supplied by
  `WorkspaceProvider` and behave as before. `CampaignsTab.js` dialogs gained `page` mode (same technique as Telegizer's CampaignManager).
- `Engagement > Campaigns` is now an entry card linking to the workspace (the old in-tab list is no longer rendered; its code remains in `CampaignsTab.js`).

## Tests
- `discord-board/backend`: 188 passed (new: Telegizer-shaped fields, lifecycle actions + isolation).
- `frontend/e2e`: 31 passed (new `campaigns-parity.spec.js`: the same payloads through both platforms' pages; screenshots in `frontend/e2e/__parity__`).
- Not tested: a live Discord guild end to end (bot posting, member modal, DM on review).
