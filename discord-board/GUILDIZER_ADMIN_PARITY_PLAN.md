# Guildizer Admin Panel — Telegizer Structural Parity Plan

**Goal:** Rebuild the Guildizer admin panel as a **1:1 structural + visual copy** of the
Telegizer admin shell (dedicated layout, sidebar of 6 categories, config-driven section
dispatch, routed detail pages, identical look-and-feel), while staying **100% isolated**:
all data via Guildizer's own `guildizerApi` + `discord-board/backend`, importing **zero**
Telegizer business logic. Copy patterns, never import them.

**Plus:** an **Admin chooser** — clicking the "Admin Panel" entry shows two options:
**Telegizer Admin** (`/admin`, untouched) or **Guildizer Admin** (new shell).

---

## Isolation rules (binding)

- New Guildizer admin frontend lives under `frontend/src/pages/guildizer/admin/` and
  `frontend/src/components/guildizer/`. It uses **only** `guildizerApi`.
- **Never** import a Telegizer admin component (AdminPanel, AdminLayout, AdminSidebar,
  AdminDetailKit, adminNav, AdminContext) into Guildizer code. Re-implement the equivalent.
- **Allowed shared import:** the app-wide design system `theme.js` (`PALETTE`, MUI theme) —
  it is the shared visual language, not product logic. Reusing it is what makes graphics match.
- Backend changes only in `discord-board/backend/`. No Telegram backend touched.
- The **only** shared-shell edits permitted (explicitly requested by user): repoint the two
  "Admin Panel" entry points (`TopNav.js`, `Sidebar.js`) from `/admin` → `/admin-hub`, and add
  the `/admin-hub` chooser route. Telegizer's admin pages themselves stay byte-for-byte unchanged.

---

## Target structure (mirrors Telegizer `adminNav.js`, Discord-adapted)

6 categories. Each item flagged: **[now]** data exists, **[api]** needs a new Guildizer endpoint,
**[stub]** placeholder section (structural parity, "no data yet" state), **[drop]** TG-only — omitted.

1. **Overview** (SpaceDashboard)
   - Dashboard — KPI stat grid + revenue/growth charts **[now+api]**
   - Proof Metrics — campaign submission proof stats **[api]** (CampaignSubmission)
   - Reports — moderation reports queue **[api]** (ModReport)
2. **Users & Access** (People)
   - Users — searchable table → routed **User Detail** (tabs) **[now]** (#5/#6)
   - Roles & Access — grant/revoke support/super **[now]** (#12/#13/#14)
   - Referrals — invite tracking + campaign referrals **[api]** (InviteLink/InviteJoin)
   - Suspicious — raid/abuse signals from ProtectionEvent **[api]**
   - Directory — *(merge into Users)* **[drop]**
3. **Bots & Servers** (SmartToy)  *(Telegizer "Bots & Groups")*
   - Servers — table → routed **Server Detail** (tabs) **[now]** (#2/#3)
   - Custom Bots — table → routed **Custom Bot Detail** (tabs) **[now+api]** (#16 + detail endpoint)
   - Bot Health — fleet health events **[now]** (#16)
   - Diagnostics — connectivity/intents check **[api/stub]**
4. **Product Analytics** (Insights)
   - Feature Usage **[now]** (#17)
   - Campaigns — table → detail **[now+api]** (#7 + detail)
   - AI Usage — tokens/cost charts **[now]** (#18)
   - Event Log — protection + feature events **[now]** (#8)
   - Audit Log **[now]** (#15)
5. **Platform Settings** (Settings)
   - Pricing — Pro price/period config (read) **[stub]**
   - AI Management — provider chain, health, ping, usage **[now]** (#19)
   - Configuration — non-secret config snapshot **[api]**
   - Secrets & Keys — booleans only (is-set, never values) **[api]**
   - System — web/worker health, DB, version **[api]**
6. **Compliance & Comms** (Gavel)
   - Compliance — GDPR purge UI **[now]** (#20, super-only)
   - Announcements — broadcast (new model) **[api/stub]**
   - Promo Codes **[now]** (#9/#10/#11)

**RBAC:** Guildizer has roles (`support`/`super`), not granular permissions. Nav config keeps a
`permission` field per item but resolves it against role (visible to any admin; `super`-only for
Roles, Compliance/Purge, Secrets). Backend already enforces super-only on those.

---

## Phases (build → self cross-check → commit+push → next, autonomously)

### Phase 0 — Plan ✅ (this file)
- [x] Map Telegizer admin + Guildizer routing/backend
- [x] Write this plan/checklist
- [x] Commit + push

### Phase 1 — Admin shell foundation ✅
- [x] `config/guildizerAdminNav.js` — `GUILDIZER_ADMIN_CATEGORIES` (6 cats), helpers (`guildizerAdminPath`, `findGuildizerAdminItem`, `DEFAULT_GUILDIZER_ADMIN_KEY`), `superOnly` gating
- [x] `contexts/GuildizerAdminContext.js` — `{ me, role, can() }`
- [x] `components/guildizer/GuildizerAdminSidebar.js` — collapsible sidebar (Guildizer logo, profile card, categories, footer Back/Switch Console), localStorage collapse, mobile Drawer
- [x] `layouts/GuildizerAdminLayout.js` — full-screen shell: glow bg, sticky AppBar ("Guildizer Admin" + role chip), sidebar, gate (guildizerApi `/auth/me` → `is_admin`), denial screen, provides context
- [x] `components/guildizer/GuildizerAdminKit.js` — `StatCard, StatusChip, Field, SectionTitle, EmptyRow, fmt*`
- [x] Routing: nested `/guildizer/admin` (GuildizerAdminRoute → layout `<Outlet/>`), index → `overview/dashboard`, `:category/:section` → panel
- [x] **Admin chooser**: `pages/AdminHub.js` (two product cards + access chips) + route `/admin-hub`; repointed `TopNav.js` + `Sidebar.js` to `/admin-hub`
- [x] Backend: `/auth/me` now returns `admin_role` (super/support/null)
- [x] Migrated current single-page content into shell sections (Dashboard, AI Management, Bot Health, Feature Usage, AI Usage, Roles, Promo, Audit); other sidebar items show parity placeholders
- [x] Build passes (CI=false), cross-checked, committed + pushed

### Phase 2 — Overview category ✅
- [x] Backend: `GET /api/admin/revenue` (Subscription MRR/ARR/this+last month/all-time + 6-mo trend), `GET /api/admin/growth?days=` (GuildDailyStat platform-wide series), `GET /api/admin/reports` (ModReport + per-status counts), `GET /api/admin/proof-metrics` (CampaignSubmission funnel)
- [x] Dashboard: stat grid w/ clickable drill-downs + Revenue KPI row + recharts revenue line + 7/30/90d growth area
- [x] Proof Metrics section (KPI grid, review funnel, recent submissions); Reports section (status counts + filterable queue)
- [x] Cross-check (py_compile + CI=false build) + commit (24b7b46) + push

### Phase 3 — Users & Access ✅
- [x] `UsersSection` (searchable table → row click) + routed `GuildizerAdminUserDetail` (Tabs: Overview, Memberships, AI Usage, Risk, Audit, Notes) at `access/users/:userId`
- [x] Backend: enriched `GET /api/admin/users/<id>` (AI usage rollup, warnings, protection events, submission counts, audit trail, admin_notes) + `POST .../notes`; `users.admin_notes` column self-healed
- [x] Roles & Access section (already shipped Phase 1); `GET /api/admin/referrals` (top inviters + recent joins) + Referrals section; `GET /api/admin/suspicious` (top offenders + category rollup) + Suspicious section
- [x] Cross-check (py_compile + CI=false build, no new warnings) + commit + push

### Phase 4 — Bots & Servers ✅
- [x] `ServersSection` (searchable table) + routed `GuildizerAdminServerDetail` (Tabs: Overview, Members, Protection, Campaigns, Settings/Actions: plan grant/free) at `bots/servers/:guildId`; enriched `GET /api/admin/guilds/<id>` (owner, top_members, campaign_list)
- [x] `CustomBotsSection` (fleet table) + routed `GuildizerAdminCustomBotDetail` (Tabs: Overview, Owner, Linked Servers, Health w/ recharts area, Errors, Actions: enable/disable) at `bots/bot/:botId`
- [x] Backend: `GET /api/admin/custom-bots/<id>` detail (owner, linked guilds, health events + 14d daily series, errors); `POST .../status` enable/disable; `GET /api/admin/diagnostics`
- [x] Bot Health section (already shipped Phase 1); Diagnostics section
- [x] Cross-check (py_compile + CI=false build, no new warnings) + commit + push

### Phase 5 — Product Analytics ✅
- [x] Feature Usage + Audit Log (shipped Phase 1); AI Usage now has a daily input/output token recharts area (extended `GET /api/admin/ai-usage` with `series`); new Event Log section over merged `GET /api/admin/event-log` (protection + feature-usage timeline)
- [x] Campaigns table + routed `GuildizerAdminCampaignDetail` (Overview / Tasks / Submissions) at `analytics/campaigns/:campaignId`; Backend `GET /api/admin/campaigns/<id>` (definition + funnel + recent submissions)
- [x] Cross-check (py_compile + CI=false build, no new warnings) + commit + push

### Phase 6 — Platform Settings ✅
- [x] AI Management already rich (shipped Phase 1, ai-health + ai-usage); Pricing section (Pro price/period read from config); Configuration section (AI / URLs+Discord / Session snapshot); Secrets section (is-set booleans only, super-only); System section (DB/AI/billing/bot health + counts + server time)
- [x] Backend: `GET /api/admin/config` (non-secret snapshot), `GET /api/admin/secrets` (booleans only, super-only), `GET /api/admin/system`
- [x] Cross-check (py_compile + CI=false build, no new warnings) + commit + push

### Phase 7 — Compliance & Comms ✅
- [x] Compliance section: GDPR purge UI (super-only, type-DELETE confirm, shows purged counts) over the existing `POST /api/admin/users/<id>/purge`; Promo Codes already shipped Phase 1
- [x] Announcements: new `AdminAnnouncement` model (auto-created by create_all, no migration) + `GET/POST/DELETE /api/admin/announcements` + `POST .../toggle`; Announcements section (compose w/ level, list, enable/disable, delete)
- [x] Cross-check (py_compile + CI=false build, no new warnings) + commit + push

### Phase 8 — Parity sweep & cleanup
- [ ] Visual parity pass vs Telegizer (spacing, glow, StatCard, chips, breadcrumbs)
- [ ] Mobile/responsive (Drawer, scrollable tabs), per-item permission gating
- [ ] Retire old `GuildizerAdmin.js` (redirect `/guildizer/admin` → shell) — keep `AiHealthCard` logic folded into AI Management
- [ ] Final cross-check + commit + push

---

## Definition of done
- Guildizer admin = dedicated shell with 6-category sidebar, routed sections + detail pages,
  matching Telegizer's layout/graphics, 100% on Guildizer's backend.
- Admin entry shows the Telegizer/Guildizer chooser.
- No Telegizer admin file imported; Telegizer admin pages unchanged.
- Every section either shows real data or a clean "no data yet" parity state.
</content>
