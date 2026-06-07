# Engagement Campaigns — Comprehensive Build Plan

> Status: **COMPLETE — ALL Phases 0–9 shipped to main, 2026-06-07.** Phase 10 verification done. Migrations auto-run on Railway deploy (Procfile `release: python -m backend.migrate`).
> Created: 2026-06-07
> Scope: Add a new "Engagement Campaigns" engine under the existing **Bot Settings → Group → Engagement** section, WITHOUT breaking existing Raids or Invite Links.

## Shipped commits
- Phase 0 `c5b06b1` — data model + migrations (3 tables)
- Phase 1 `10e9cdc` — admin backend (shared service + 14 routes, both lineages, gating)
- Phase 2 `bfb9752` — dashboard UI (Campaigns subtab, wizard, review queue, export, winner picker)
- Phase 3 `bb02d73` — Telegram publish (premium group post + deep-link buttons, both lineages)
- Phase 4 `65e6e1f` — bot DM proof flow + callbacks (additive, group -1)
- Phase 5 `543d384` — verification engine (Telegram-join auto + link-validity)
- Phase 6 `4cbf723` — anti-fraud (dedup, flags, cooldown, membership gate, suspicious log)
- Phase 7 `dfc1c0b` — lifecycle scheduler (auto-close + ending-soon + post close)
- Phase 8 `4e0394a` — subtle official-only growth promo (capped, referral-attributed)
- Phase 9 `e090cee` — Mini App participant pages + participant API (/task/:id, /tasks)

## DEPLOY
Migrations run automatically on Railway deploy (Procfile `release:` step). On the
next deploy the 3 tables + flag columns are created and the **Campaigns** tab
appears under Bot Settings → Group → Engagement. No manual step required.

## MANUAL TEST SCRIPT (Phase 10 — user to run)
1. **Migrate**: run `python -m backend.migrate` on Railway; confirm "engagement_*" lines.
2. **Dashboard (official + a custom bot)**: Engagement → Campaigns → Create Campaign.
   - Proof Collection w/ a UID field, 24h, activate now → confirm row appears, status Active.
3. **Group post**: confirm a premium announcement posts to the group with buttons
   (Open Task / Submit Proof / My Submission) and is pinned.
4. **DM proof flow**: as a normal member tap **Submit Proof** → bot DMs you → send a
   UID → "Submitted, pending review". Tap again → "already submitted".
5. **Review**: dashboard → Manage → approve the submission → submitter gets XP (check leaderboard).
6. **Telegram-join task**: make a `social_task`/auto campaign (set settings.verify_chat to a
   channel the bot admins) → Verify works only if you're a member.
7. **Anti-fraud**: submit the same UID from a 2nd account → flagged ⚠ in review queue.
8. **Lifecycle**: set a short deadline → after it passes, campaign auto-closes; new taps get
   "campaign is closed".
9. **Promo**: on the official bot, the DM success message shows a subtle Telegizer footer;
   on a **custom** bot it must NOT appear.
10. **Regression**: confirm Raids + Invite Links still work unchanged.

---

## 0. Decisions locked in (from full discussion)

These are the agreed principles. Every phase must respect them.

1. **Additive, not destructive.** Keep the Engagement section. Keep **Invite Links** untouched. Keep existing **Raid** / **OfficialRaid** tables and the Raids subtab. Add a new **Campaigns** subtab alongside them. Do NOT rewrite or migrate Raids in MVP (optional V2: a "Twitter Raid" campaign type that supersedes legacy raids only after the new engine is proven).
2. **One engine, many campaign types** (not 4 separate modules):
   - `proof_collection` — referral link / UID / wallet / username / screenshot / tx_hash / custom fields. **Centerpiece of MVP.**
   - `content_submission` — submit YouTube / X / Telegram / IG / blog link for admin review.
   - `social_task` — like/repost/comment/follow X; subscribe/comment YouTube; join TG channel; follow IG/FB; generic manual.
   - `giveaway` — a flavor of the above (entry on completion).
3. **Verification reality (no overpromising):**
   - ✅ **Telegram channel/group join** = reliable free auto-verify via `getChatMember` (bot must be admin). Flagship auto-verify.
   - ✅ **Link-validity checks** (does the tweet/video exist, right URL shape) = optional **premium**, config-guarded, degrades to manual if no API key.
   - ❌ **X likes/reposts/follows, YouTube subscribe/like/comment, IG/FB anything** = **manual proof or honor-based "Verify"** only. NEVER promise API verification of these.
   - ❌ **No scraping. Ever.** (ToS/ban/legal risk.)
   - Screenshots = admin-reviewed; optional premium dedup/OCR-flagging as a review *assist*, never auto-approve.
4. **Surfaces (where the user acts):**
   - **Group post** = announcement + advertising layer. Buttons: `[Open Link]` (URL), `[Verify]` (one-tap callback, honor/TG-join only), deep-links to DM, optional `[Leaderboard]`. NEVER collects typed/file proof in-group (privacy + spam + technical limit).
   - **Bot private DM** = **primary proof-collection surface.** Entered via deep-link `t.me/<bot>?start=campaign_<id>`. Step-by-step Q&A collects fields privately. No Mini App needed.
   - **Mini App** = optional **V2**, scoped to a single campaign screen (`/mini-app/campaign/:id`) or a grouped "My Tasks" hub. Never dumps the user into the full dashboard.
5. **Identity / multi-group:** the **campaign ID** (carried in every button payload) is the anchor — it pins exactly one group. Custom bots are isolated by their own bot identity. The shared official bot serves many groups unambiguously because the campaign ID disambiguates. Conversation state keyed to **(user, campaign)**.
6. **Lineage rule (governing):** build the engine as a **shared core** with thin **official** and **custom** adapters (mirror the `Raid`/`OfficialRaid` split, but prefer single-table dual-FK like `AutoResponse`). Both lineages must inherit. NOTE: the current custom-bot raid path does NOT post to Telegram — the new engine must post for BOTH lineages.
7. **Promotion (growth):**
   - **Official bot only.** Custom bots = 100% clean (white-label = what the client paid for).
   - Promote ONLY in the **end-user's private surfaces** (DM success message, My Tasks hub). NEVER in the group announcement (that's the paying admin's space).
   - Subtle **one-line footer**, frequency-capped (configurable; **default every 2–3 days**, on first completion then throttled), referral-attributed signup link.
   - Config flag `show_telegizer_branding` — default ON for official, OFF for custom. Must NOT feel like advertising.
8. **Reuse, don't reinvent:** XP ledger (`XpEvent`, `reason="campaign:<id>"`, idempotent) for rewards; `AuditLog` (new action types) for audit; `SuspiciousActivity` (hashed) for fraud; `rate_limit` decorator; Invite-Links analytics/table pattern; MUI dialog/table patterns; TMA auth bridge.
9. **Pricing:** generous free taste, premium = scale + automation + trust.
   - **Free:** manual-proof & link-submission campaigns; 1 active campaign; capped participants/submissions per month; TG channel-join auto-verify; basic announce + manual approve/reject; basic CSV.
   - **Premium (Pro/Enterprise):** multiple concurrent campaigns; high/unlimited caps; link-validity auto-checks; advanced custom fields & multi-task; XP/reward automation; leaderboards; winner picker; dedup/fraud detection; advanced analytics; bulk export; branded pages (Enterprise); API/webhook hooks.
10. **Migrations** run manually via `migrate.py` on Railway (idempotent, additive, safe coexistence period).
11. **Do NOT touch:** Invite Links + models; XP ledger mechanics; gating infra; sidebar/IA structure; existing Raid tables.

---

## Per-phase ritual (applies to EVERY phase)

1. Build the phase.
2. **Cross-check #1:** run relevant tests/checks, review changed files, confirm no existing feature (Raids, Invite Links, XP, etc.) is broken, confirm no secrets staged.
3. **Push to GitHub** (`main`, per project workflow) — only after cross-check passes and user confirms.
4. **Cross-check #2:** re-verify the pushed phase (deploy sanity on Railway/Vercel, quick smoke).
5. Proceed to next phase.

After ALL phases: full regression cross-check of every phase together → bug sweep → security review → final commit → **manual end-to-end testing** in real Telegram groups (official + custom).

---

## Phase 0 — Data model & migrations (backend only, no behavior)

Safest first; nothing user-visible.

- [ ] `engagement_campaigns` — id, `group_id` (FK nullable), `telegram_group_id` (nullable, indexed), `owner_user_id`, `type`, `platform`, `title`, `description`, `task_url`, `verification_mode` (`auto|manual|honor|screenshot|link`), `reward_xp`, `reward_label`, `status` (`draft|active|paused|closed|archived`), `starts_at`, `ends_at`, `max_participants`, `one_per_user`, `pin_message`, `telegram_message_id`, `settings` (JSON), `created_at`. Dual-FK pattern like `AutoResponse`. `to_dict()` + `to_dict(include_analytics=True)`.
- [ ] `engagement_custom_fields` — campaign_id, `key`, `label`, `field_type` (`text|url|uid|wallet|screenshot|tx_hash|username`), `required`, `order`.
- [ ] `engagement_submissions` — campaign_id, telegram_user_id, member_id, scope (`custom|official`), `status` (`pending|verified|rejected`), `payload` (JSON), `file_id`, `file_hash`, `reviewed_by`, `review_reason`, `created_at`, `reviewed_at`. **Unique constraint (campaign_id, telegram_user_id)** when one_per_user.
- [ ] (V2 placeholder, not built now) `engagement_tasks` for multi-task campaigns — MVP inlines a single task on the campaign row.
- [ ] Rewards → reuse `XpEvent` (`reason="campaign:<id>"`). No new reward table.
- [ ] Audit → reuse `AuditLog` with new `action_type` values (`campaign_create`, `campaign_status`, `submission_approve`, `submission_reject`).
- [ ] `migrate.py` additions — idempotent, additive, Railway-safe.
- Cross-check: migration runs clean locally; models import; existing app unaffected.

## Phase 1 — Admin backend (shared core + both lineages)

- [ ] Shared campaign service (create/list/get/update-lifecycle: pause/close/reopen/archive).
- [ ] Custom-bot routes in `routes/settings.py`; official routes in `routes/telegram_groups.py`; both delegate to the shared core. `@jwt_required` + `@rate_limit` + ownership checks (`_get_bot_and_group` / `_owns_group`).
- [ ] Submissions: list / approve / reject / export(CSV).
- [ ] Plan gating: free caps (1 active, monthly submission cap), premium feature flags. Mirror `_GATED_SECTIONS`.
- Cross-check: endpoints work locally; gating enforced; no auth holes; free vs premium correct.

## Phase 2 — Admin dashboard UI

- [ ] Add **Campaigns** subtab to `featureRegistry.js` `community` category + render block in `GroupSettings.js`. Raids & Invite Links untouched.
- [ ] Create-campaign **wizard** (MUI dialog): type → platform → details → proof fields → verification mode → schedule (24h/48h/7d/custom) → limits → reward → publish target (group/topic, pin).
- [ ] Campaign list table (status chips, like InviteLinks), campaign detail, participant table, **submission review queue** (approve/reject/bulk), lifecycle controls, CSV export, winner picker.
- [ ] `api.js` service additions; `ProBadge` / `UpsellModal` gating mirror; respect mobile-polish conventions.
- Cross-check: create → list → review loop works against backend; mobile renders; gating visible.

## Phase 3 — Telegram publish + premium group post (both lineages)

- [ ] Shared publish function: formatted premium post (title, short instructions, reward, deadline/timer, status label Active/Ending soon/Closed, optional participant count) + inline keyboard (`Participate`, `Submit Proof`, `Verify`, `View Task`, `My Submission`, optional `Leaderboard`), pin option, topic targeting.
- [ ] Wire BOTH lineages to post (custom-bot path currently does not — fix here).
- Cross-check: post renders correctly in test group for official AND custom; buttons present.

## Phase 4 — Bot participation handlers (DM deep-link + callbacks)

- [ ] Deep-link `start=campaign_<id>` → opens DM, loads campaign, starts flow.
- [ ] Conversation state keyed (user, campaign); clean switch if user taps a different campaign mid-flow (reuse `AssistantConversationState` pattern).
- [ ] Callbacks: `participate`, `verify_task`, `submit_proof` (DM Q&A collects typed/file fields), `view_details`, `my_submission`.
- [ ] Status messages: closed → "This campaign is closed. Submission window ended."; duplicate → "You have already submitted for this task."; manual → "Submitted successfully. Pending admin review."
- [ ] Reward on verify/approve via `XpEvent` (idempotent, keyed to submission id).
- [ ] Register in shared module so custom bots inherit; wire `bot_manager` + `official_bot`.
- Cross-check: full journey (group → DM submit → status); TG-join auto-verify works; rewards idempotent (no double-award).

## Phase 5 — Verification engine (realistic, limited)

- [ ] TG channel/group join auto-verify (`getChatMember`) — solidify (bot-admin check + clear error if missing perms, like invite links).
- [ ] Link-validity checks (PREMIUM, config-guarded): URL shape + platform match; optional YouTube Data API "video exists", X "tweet exists". Graceful degrade to manual if no API key.
- [ ] Honor-based + manual review wiring.
- Cross-check: each mode behaves; missing API keys degrade to manual, never crash.

## Phase 6 — Anti-fraud & integrity

- [ ] Unique (campaign_id, telegram_user_id); dedup of UID / wallet / referral-link (normalized) + screenshot `file_hash`; flag repeats within and across campaigns.
- [ ] Account-age / membership gate (must be a real group member; check join via `getChatMember` / `Member` records).
- [ ] Rate limits on submission endpoints + per-user bot cooldown.
- [ ] Suspicious flagging (reuse `SuspiciousActivity`, hashed); fraud/suspicious view in dashboard; ban/ignore abusive users; audit every state change.
- Cross-check: duplicates blocked/flagged; gates enforced; audit entries written.

## Phase 7 — Lifecycle scheduler

- [ ] Generalize `check_raid_reminders` → campaign lifecycle job: auto-close at `ends_at`, "ending soon" reminder, flip group-post status label, optional results summary on close.
- Cross-check: timed close works; labels update; reminders fire; raids still reminded.

## Phase 8 — Growth promo (official-only, subtle)

- [ ] Config flag `show_telegizer_branding` (default ON official / OFF custom).
- [ ] Frequency-capped one-line footer (configurable interval, **default 2–3 days**; on first completion then throttled) on **DM success message + My Tasks hub ONLY** — never the group post.
- [ ] Referral-attributed signup link; track tasks → signups.
- Cross-check: appears only on official, only in user surfaces, respects cap, fully absent on custom.

## Phase 9 — Mini App (optional / V2-lite)

- [ ] Scoped `/mini-app/campaign/:id` single-task screen.
- [ ] "My Tasks" hub grouped by group (handles one-user-many-groups cleanly).
- [ ] Reuse TMA auth bridge; deep-link entry; no full-dashboard dump.
- Cross-check: deep-link opens scoped task; multi-group hub distinguishes correctly.

## Phase 10 — Final integration cross-check + manual test

- [ ] Full regression across all phases, both lineages, one-user-many-groups scenario.
- [ ] Confirm Raids + Invite Links + XP untouched and working.
- [ ] Security review (`/security-review`); confirm no secrets committed.
- [ ] **Manual end-to-end testing** in real Telegram groups (official bot + a custom bot): create → publish → participate → submit (proof/content/social/TG-join) → verify/approve/reject → reward → export → winner pick → promo footer behavior → multi-group identity.
- [ ] Final commit + push.

---

## What we will AVOID (guardrails)

- No scraping; no promised auto-verification of X likes/follows, YouTube subscribe, or any IG/FB action.
- No OAuth in MVP (collect declared handles in submission payload).
- No breaking/rewriting Raids or Invite Links; no new reward currency (use XpEvent); no duplicate audit/fraud tables.
- No promo on custom bots; no promo in the group announcement; no aggressive/ad-like promo frequency.
- No sidebar/IA structure changes without explicit permission.

## MVP vs V2 quick map

- **MVP:** Phases 0–8 (proof_collection + content_submission + TG-join social_task; manual/honor + TG-join auto-verify; DM flow; review queue; anti-fraud; lifecycle; subtle official-only promo).
- **V2:** Phase 9 (Mini App), link-validity auto-checks at scale, OCR/screenshot-dedup assist, multi-task campaigns, per-campaign leaderboards, branded pages, "Twitter Raid as a campaign type", webhook/API hooks.
