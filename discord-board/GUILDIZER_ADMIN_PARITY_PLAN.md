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

### Phase 1 — Admin shell foundation
- [ ] `config/guildizerAdminNav.js` — `GUILDIZER_ADMIN_CATEGORIES` (6 cats), helpers (`adminPath`, `findItem`, `DEFAULT_KEY`)
- [ ] `contexts/GuildizerAdminContext.js` — `{ me, role, can() }`
- [ ] `components/guildizer/GuildizerAdminSidebar.js` — collapsible sidebar (logo, profile card, categories, footer), localStorage collapse, mobile Drawer
- [ ] `layouts/GuildizerAdminLayout.js` — full-screen shell: glow bg, sticky AppBar ("Guildizer Admin Console" + role chip), sidebar, content `maxWidth 1400`, gate (guildizerApi `/auth/me` → `is_admin`), denial screen
- [ ] `components/guildizer/GuildizerAdminKit.js` — `StatCard, StatusChip, Field, SectionTitle, EmptyRow, fmtDate/fmtDateTime/fmtRelative/usd` (copied visual primitives)
- [ ] Routing: nested `/guildizer/admin` → layout with `<Outlet/>`, child routes per section + detail pages; `/guildizer/admin` redirects to `overview/dashboard`
- [ ] **Admin chooser**: `pages/AdminHub.js` (two product cards) + route `/admin-hub`; repoint `TopNav.js` + `Sidebar.js` entries to `/admin-hub`
- [ ] Migrate current single-page content into the new **Dashboard** section as a starting point
- [ ] Cross-check + commit + push

### Phase 2 — Overview category
- [ ] Backend: `GET /api/admin/revenue` (Subscription MRR/active/recent), `GET /api/admin/growth?days=` (GuildDailyStat series), `GET /api/admin/reports` (ModReport), `GET /api/admin/proof-metrics` (CampaignSubmission)
- [ ] Dashboard: KPI grids (Users / Bot Ecosystem / Revenue / Engagement) + recharts revenue line + growth area, clickable drill-downs
- [ ] Proof Metrics section; Reports section
- [ ] Cross-check + commit + push

### Phase 3 — Users & Access
- [ ] `GuildizerAdminUsers` (searchable/paginated table) + routed `GuildizerAdminUserDetail` (MUI Tabs: Overview, Memberships, AI Usage, Risk, Audit, Notes)
- [ ] Backend: enrich user detail (AI usage, warnings, submissions, audit) + admin notes write
- [ ] Roles & Access section; Referrals section **[api]**; Suspicious section **[api]**
- [ ] Cross-check + commit + push

### Phase 4 — Bots & Servers
- [ ] `GuildizerAdminServers` table + routed `GuildizerAdminServerDetail` (Tabs: Overview, Members, Protection, Campaigns, Settings, Actions: plan/disable)
- [ ] `GuildizerAdminCustomBots` table + routed `GuildizerAdminCustomBotDetail` (Tabs: Overview, Owner, Linked Servers, Health, Errors, Actions) — recharts
- [ ] Backend: `GET /api/admin/custom-bots/<id>` detail
- [ ] Bot Health section; Diagnostics section
- [ ] Cross-check + commit + push

### Phase 5 — Product Analytics
- [ ] Feature Usage, AI Usage (charts), Event Log, Audit Log sections
- [ ] Campaigns table + detail; Backend `GET /api/admin/campaigns/<id>`
- [ ] Cross-check + commit + push

### Phase 6 — Platform Settings
- [ ] AI Management (rich, from ai-health + ai-usage), Pricing (read config), Configuration `[api]`, Secrets booleans `[api]`, System health `[api]`
- [ ] Backend: `GET /api/admin/system`, `GET /api/admin/config`
- [ ] Cross-check + commit + push

### Phase 7 — Compliance & Comms
- [ ] Compliance (GDPR purge UI, super-only), Promo Codes, Announcements `[api/stub]` (+ model/endpoint if built)
- [ ] Cross-check + commit + push

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
