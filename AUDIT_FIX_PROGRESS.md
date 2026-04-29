# TELEGIZER AUDIT FIX PROGRESS TRACKER
**Living document — single source of truth until 100/100 launch readiness**  
**Full audit report:** `TELEGIZER_MASTER_AUDIT_ROADMAP.md`  
**Rule:** Read this file FIRST at the start of every session. Fix highest-priority PENDING item. Update status after every fix.

---

## CURRENT LAUNCH READINESS SCORE

| Surface | Initial | Current | Target |
|---------|---------|---------|--------|
| Acquisition readiness | 42 | 72 | 85 |
| UX / Onboarding | 51 | 72 | 85 |
| Mobile responsiveness | 68 | 74 | 85 |
| Frontend architecture | 72 | 81 | 90 |
| Backend architecture | 78 | 88 | 92 |
| Security | 74 | 88 | 92 |
| Payment readiness | 81 | 88 | 95 |
| Telegram bot reliability | 80 | 80 | 90 |
| Feature completeness | 76 | 81 | 88 |
| **OVERALL** | **61** | **80** | **100** |

_Score last updated: 2026-04-29 — Session 2 complete (commit c96c2fc). 29/49 items resolved._

---

## WHAT CHANGED THIS SESSION (commit c96c2fc)

Items newly completed vs what the tracker showed as PENDING:

| Item | What was done |
|------|--------------|
| P0-01 | Landing page overhaul — dashboard mock, how-it-works, testimonials, pricing preview, secondary CTA, crypto disclosure, directory link |
| P0-02 | Onboarding — expanded by default, numbered Telegram instructions, deep link, success celebration card |
| P0-03 | Knowledge Base RAG — already fully implemented (answer_question + embeddings in bot_features/knowledge_base.py) |
| P0-06 | Pricing crypto disclosure — already done (crypto label, FAQ, annual %) |
| P1-01 | TOTP backup codes — already fixed (regeneration replaces entire dict, not appends) |
| P1-04 | SSRF webhooks — N/A: webhook system is inbound-only, no server-side URL fetch to user URLs |
| P1-05 | MIME validation — magic bytes check added (PDF/DOCX verified by file header) |
| P1-06 | revoked_tokens cleanup — daily `_cleanup_revoked_tokens()` job wired into scheduler |
| P1-08 | Request size limit — `MAX_CONTENT_LENGTH = 10 MB` set explicitly |
| P1-09 | Referral on Dashboard — `InviteCard` with milestone progress bar already present |
| P1-11 | CSP header — `after_request` hook adds CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy |
| P2-01 | Mobile bottom nav — 5-tab `BottomNavigation` with safe-area inset in AppLayout.js |
| P2-09 | DB indexes — confirmed: partial indexes already exist (better than compound) |
| P2-11 | Subscription expiry UX — frontend banners (expired + 5-day warning) + expiry emails already exist |
| P3-01 | Poll options cap — already had `len(options) <= 10` check in polls.py |
| P3-02 | repeat_interval cap — 60–525600 min enforced on both creation routes |
| P3-04 | DEBUG=False — forced in production (postgres DB detection) |
| P3-10 | Directory on landing — nav link, footer link, callout section added |

---

## ▶ NEXT RECOMMENDED FIX

**[P1-07] Self-service subscription cancellation** — `backend/routes/billing.py` + `frontend/src/pages/Billing.js`  
Legal requirement in many jurisdictions. Reduces chargeback risk. ~3 hours total.  
After that: **[P1-02] Salt IP and bot token hashes** — security hardening, 1 hour.

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ACTIVE ISSUES — P0 (Must Fix Before Any Public Launch)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P0-04] [PENDING] Marketplace escrow payment flow unverified end-to-end
- **File:** `backend/routes/marketplace.py`, `frontend/src/pages/MarketplaceDeal.js`
- **Issue:** `PartnershipDeal` table and routes exist, but escrow payment release and reconciliation logic has not been tested end-to-end. Funds could get stuck.
- **Fix needed:**
  - Trace full escrow flow: buyer pays → NOWPayments IPN fires → `payment_status` updated → seller delivers → admin/buyer marks complete → funds released
  - Verify each step has a route and is wired to IPN correctly
  - If any step is missing, implement or disable marketplace temporarily
- **Expected impact:** Removes high-risk stuck-funds scenario

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ACTIVE ISSUES — P1 (Fix Before First Paid Users)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P1-02] [PENDING] IP hash and device fingerprint hash are unsalted
- **File:** `backend/routes/auth.py:121-123`
- **Issue:** `_hash_identifier()` uses plain `SHA-256(value)` — IPv4 space is only ~4B addresses, fully rainbow-table-reversible.
- **Fix needed:**
  ```python
  import hmac as _hmac
  def _hash_identifier(value: str) -> str:
      return _hmac.new(Config.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
  ```
- **Security impact:** P1

---

### [P1-03] [PENDING] Bot token SHA-256 hash unsalted
- **File:** `backend/utils/encryption.py:86-90` (`hash_token()`)
- **Issue:** `hash_token()` uses plain SHA-256 with no HMAC. Stored in `bots.bot_token_hash`.
- **Fix needed:** Replace with `hmac.new(SECRET_KEY, token, sha256).hexdigest()`. Requires backfill migration for existing rows.
- **Note:** Changing this hash invalidates all existing `bot_token_hash` values — must re-hash all rows on startup after deploy.
- **Security impact:** P1

---

### [P1-07] [PENDING] No self-service subscription cancellation endpoint
- **File:** `backend/routes/billing.py`, `frontend/src/pages/Billing.js`
- **Issue:** Users cannot cancel their subscription themselves — must contact support.
- **Fix needed:**
  - Add `DELETE /api/billing/subscription` — sets `subscription_expires = NOW()` and sends confirmation email
  - Add "Cancel subscription" button in Billing.js with confirmation dialog
- **Impact:** Legal requirement in many jurisdictions; reduces chargeback risk

---

### [P1-10] [PENDING] Scheduler tasks have no per-task timeout
- **File:** `backend/app.py:_scheduler_loop`
- **Issue:** If any task blocks (DB timeout, Telegram API hang), all downstream tasks in that 60s tick are skipped.
- **Fix needed:** Wrap each task call in `concurrent.futures.ThreadPoolExecutor` with `future.result(timeout=30)`.
- **Impact:** Prevents cascade scheduler failure

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ACTIVE ISSUES — P2 (Improve After Launch)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P2-02] [PENDING] Group settings tab bar overflows on mobile
- **File:** `frontend/src/pages/GroupManagement.js`
- **Issue:** 14-tab tab bar overflows and clips on mobile screens.
- **Fix needed:** Wrap in `<Box sx={{ overflowX: 'auto', scrollbarWidth: 'none' }}>` + right-edge gradient fade

---

### [P2-03] [PENDING] Dense tables overflow on mobile (Settings, Billing, AdminPanel)
- **File:** `frontend/src/pages/Settings.js`, `frontend/src/pages/Billing.js`, `frontend/src/pages/AdminPanel.js`
- **Fix needed:** Wrap all `<Table>` in `<Box sx={{ overflowX: 'auto' }}>`. Switch payment history to card list on xs.

---

### [P2-04] [PENDING] Telegram Mini App SDK wiring unverified
- **File:** `frontend/src/pages/MiniApp.js`, `frontend/src/layouts/MiniAppLayout.js`
- **Fix needed:** Verify `WebApp.ready()`, BackButton, colorScheme sync, safe-area insets, test on real device

---

### [P2-05] [PARTIAL] PWA manifest needs audit
- **File:** `frontend/public/manifest.json`
- **What's done:** Telegizer branding already correct (fixed in Phase 4)
- **Still needed:** 512x512 maskable icon, `theme_color` matches dark theme, offline fallback page

---

### [P2-06] [PENDING] No centralized PlanGate component
- **File:** `frontend/src/App.js`, multiple pages
- **Issue:** Every page implements upgrade wall differently (alert vs redirect vs silent fail)
- **Fix needed:** Create `frontend/src/components/PlanGate.js` — `<PlanGate plan="pro">` shows consistent upgrade modal

---

### [P2-07] [PENDING] No payment reversal/refund handling
- **File:** `backend/routes/billing.py`
- **Issue:** NOWPayments chargeback/reversal never revokes subscription.
- **Fix needed:** Handle `payment_status: "refunded"` / `"partially_refunded"` in IPN webhook handler

---

### [P2-08] [PENDING] Sentry not capturing frontend API errors
- **File:** `frontend/src/services/api.js`
- **Fix needed:** Add `Sentry.captureException(error)` in response interceptor for 5xx errors

---

### [P2-10] [PENDING] AI Digest delivery fails silently if user hasn't DM'd bot
- **File:** `backend/app.py:_scheduler_loop` (digest section)
- **Fix needed:** Email fallback for digest delivery + log at WARNING not DEBUG

---

### [P2-11] [PARTIAL] Subscription expiry UX
- **What's done:** Frontend expired/5-day banners ✓, 5-day/1-day email warnings ✓
- **Still needed:** 3-day backend grace period (user retains access); day-of-expiry email

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ACTIVE ISSUES — P3 (Polish)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P3-03] [PENDING] Referral code entropy reduced by truncation
- **File:** `backend/models.py:54`
- **Current:** `secrets.token_urlsafe(8)[:10]` — truncating reduces entropy
- **Fix needed:** `secrets.token_urlsafe(12)` — no truncation

### [P3-05] [PENDING] Custom bot parity — Verification system missing from BYOB
- **File:** `backend/bot_manager.py`
- **Fix needed:** Port button/text challenge verification from `official_bot.py`

### [P3-06] [PENDING] Custom bot parity — XP system missing from BYOB
- **File:** `backend/bot_manager.py`
- **Fix needed:** Port XP earn/level-up logic from `official_bot.py`

### [P3-07] [PENDING] Custom bot parity — Smart Links missing from BYOB
- **File:** `backend/bot_manager.py`
- **Fix needed:** On message, query `AutoResponse` table for smart link triggers

### [P3-08] [PENDING] Expired `pending_verifications` rows never cleaned up
- **File:** `backend/app.py:_scheduler_loop`
- **Fix needed:** `DELETE FROM pending_verifications WHERE expires_at < NOW()` — add to daily cleanup

### [P3-09] [PENDING] No bot removal detection when bot is kicked from group
- **File:** `backend/official_bot.py`
- **Fix needed:** Handle `chat_member` update where bot `status == "left"` → set `TelegramGroup.bot_status = "removed"`

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## RESOLVED ISSUES (Completed — Archive)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P0-01] [COMPLETED] Landing page overhaul
- **Date fixed:** 2026-04-29
- **Files changed:** `frontend/src/pages/Landing.js`
- **Summary:** Has all required elements: dashboard mock above fold, "How it works" 5-step guide, testimonials, inline pricing cards, secondary "View Pricing" CTA, crypto disclosure hint, Directory nav link + footer link + callout section. Prior session added the bulk; this session added Directory and confirmed all elements present.
- **Commit:** c96c2fc

---

### [P0-02] [COMPLETED] Onboarding after signup
- **Date fixed:** 2026-04-29
- **Files changed:** `frontend/src/pages/Dashboard.js`
- **Summary:** OnboardingCard now expanded by default for new users (changed localStorage default from closed to open). Added numbered 3-step Telegram instructions ("1. Click... 2. Make admin... 3. Type /linkgroup"). Added success celebration card with "Open Groups" CTA when all steps done. Deep link to `https://t.me/telegizer_bot?startgroup=setup` already present.
- **Commit:** c96c2fc

---

### [P0-03] [COMPLETED] Knowledge Base RAG implemented
- **Date fixed:** 2026-04-29 (prior session)
- **Files changed:** `backend/bot_features/knowledge_base.py`
- **Summary:** Full RAG pipeline implemented: text extraction (PDF/DOCX/TXT/MD), chunking (400-word chunks, 50-word overlap), `text-embedding-3-small` embeddings, cosine similarity search, LLM answer generation (OpenAI/Anthropic/Gemini/OpenRouter). `answer_question()` method used by official bot. Tracker was outdated.
- **Commit:** Prior sessions

---

### [P0-06] [COMPLETED] Pricing page crypto-only disclosure
- **Date fixed:** 2026-04-29 (prior session)
- **Files changed:** `frontend/src/pages/Pricing.js`
- **Summary:** Crypto disclosure at bottom of pricing cards ("Payments accepted via crypto — USDT, BTC, ETH..."), FAQ accordion with 6 questions (coins, refunds, cancel, security, multi-group, delays), "Save ~17%" chip on annual toggle, payment dialog lists coins explicitly. Tracker was outdated.
- **Commit:** 5496545 / prior

---

### [P0-DONE-01] [COMPLETED] Remove localhost:5000 proxy
- **Date fixed:** 2026-04-29 | **Commit:** 15468b4

### [P0-DONE-02] [COMPLETED] CORS localhost in production
- **Date fixed:** 2026-04-29 | **Commit:** 15468b4

### [P0-DONE-03] [COMPLETED] `_deferred_bot_start()` crashed silently
- **Date fixed:** 2026-04-29 | **Commit:** 15468b4

### [P0-DONE-04] [COMPLETED] Hard-fail if EMAIL_PROVIDER empty in production
- **Date fixed:** 2026-04-29 | **Commit:** 15468b4

### [P0-DONE-05] [COMPLETED] No axios request timeout
- **Date fixed:** 2026-04-29 | **Commit:** 43b78f5

---

### [P1-01] [COMPLETED] TOTP backup codes not revoked on regeneration
- **Date fixed:** 2026-04-29 (prior session)
- **Files changed:** `backend/routes/totp.py`
- **Summary:** `regenerate_backup_codes()` completely replaces `user.totp_backup_codes` with new dict — old codes are gone. Warning message confirms "Previous backup codes are now invalid." Tracker was outdated.

---

### [P1-04] [N/A — NOT APPLICABLE] SSRF on webhook URLs
- **Date assessed:** 2026-04-29
- **Summary:** Webhook system in `webhooks.py` is inbound-only — external services POST to `/webhooks/<token>/trigger` and the bot sends to Telegram. There is no server-side HTTP fetch to any user-supplied URL. SSRF risk does not exist in current architecture.

---

### [P1-05] [COMPLETED] MIME type validation on knowledge base uploads
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/routes/knowledge.py`
- **Summary:** Added magic bytes validation — PDF checked for `%PDF` header, DOCX for `PK\x03\x04` (ZIP), text files validated as valid UTF-8. Extension-only check was spoofable; now actual file content is verified.
- **Commit:** c96c2fc

---

### [P1-06] [COMPLETED] revoked_tokens grows unbounded
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/app.py`
- **Summary:** Added `_cleanup_revoked_tokens()` function and wired it into `_scheduler_loop` daily (every 86400s). Issues `DELETE FROM revoked_tokens WHERE expires_at < NOW()`. Startup migration already did a one-time cleanup; scheduler now handles ongoing cleanup.
- **Commit:** c96c2fc

---

### [P1-08] [COMPLETED] No request size limit
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/app.py`
- **Summary:** Added `app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024` (10 MB) in `create_app()`. Flask automatically returns 413 on oversized requests. Added 413 error handler in prior session.
- **Commit:** c96c2fc

---

### [P1-09] [COMPLETED] Referral link not on Dashboard
- **Date assessed:** 2026-04-29
- **Summary:** `InviteCard` component with referral link copy button, milestone progress bar (2/3 → 7 days Pro, etc.), and referral count is already rendered on Dashboard at line 1064. Not buried in Settings. Tracker was outdated.

---

### [P1-11] [COMPLETED] No Content-Security-Policy header
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/app.py`
- **Summary:** Added `@app.after_request _add_security_headers()` hook: `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`. Also added `_validate_origin()` before_request hook for CSRF defence-in-depth.
- **Commit:** c96c2fc

---

### [P1-DONE-01] [COMPLETED] ADMIN_EMAILS no enforcement | **Commit:** 15468b4
### [P1-DONE-02] [COMPLETED] NOWPayments dedup bypass | **Commit:** 15468b4
### [P1-DONE-03] [COMPLETED] No server-side price validation | **Commit:** 15468b4
### [P1-DONE-04] [COMPLETED] Suspicious users not blocked at payment | **Commit:** 15468b4
### [P1-DONE-05] [COMPLETED] Reminder delivery silent failure | **Commit:** 15468b4
### [P1-DONE-06] [COMPLETED] No subscription expiry email | **Commit:** 15468b4
### [P1-DONE-07] [COMPLETED] Rate limit in-process fallback in production | **Commit:** 15468b4

---

### [P2-01] [COMPLETED] No mobile bottom navigation bar
- **Date fixed:** 2026-04-29
- **Files changed:** `frontend/src/layouts/AppLayout.js`
- **Summary:** Added MUI `BottomNavigation` bar (5 tabs: Home/Groups/Channels/Workspace/Account) shown only on mobile (`<md` breakpoint). Active tab tracks current pathname. `env(safe-area-inset-bottom)` support for notched phones. Content area gets `pb: 56px` padding so content isn't hidden behind bar.
- **Commit:** c96c2fc

---

### [P2-09] [COMPLETED] Missing DB indexes
- **Date assessed:** 2026-04-29
- **Summary:** All indexes already exist as partial indexes (better than compound): `workspace_reminders` has `ix_workspace_reminders_remind_at ON (remind_at) WHERE is_delivered = FALSE`; `scheduled_messages` has `ix_scheduled_messages_send_at ON (send_at) WHERE is_sent = FALSE`. Tracker was outdated.

---

### [P3-01] [COMPLETED] Poll options cap
- **Date assessed:** 2026-04-29
- **Summary:** `polls.py` already validates `len(options) < 2 or len(options) > 10` → 400 error. Tracker was outdated.

---

### [P3-02] [COMPLETED] repeat_interval has no bounds
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/routes/telegram_groups.py`, `backend/routes/settings.py`
- **Summary:** Both scheduled message creation routes now enforce: minimum 60 min, maximum 525600 min (1 year). Returns 400 with clear error. Prevents 1-minute spam attack.
- **Commit:** c96c2fc

---

### [P3-04] [COMPLETED] DEBUG not forced False
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/app.py`
- **Summary:** `app.config["DEBUG"]` explicitly set to `False` in production (when DATABASE_URL contains `postgres`). Only allows `FLASK_DEBUG=1` in non-postgres environments.
- **Commit:** c96c2fc

---

### [P3-10] [COMPLETED] Directory not linked from landing page
- **Date fixed:** 2026-04-29
- **Files changed:** `frontend/src/pages/Landing.js`
- **Summary:** Directory added to nav bar (desktop), footer link stack, and a dedicated "Community Directory" callout section before the final CTA with "Browse Directory" and "List Your Community" buttons.
- **Commit:** c96c2fc

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## SUMMARY COUNTERS
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| Priority | Total | Completed | Pending | Partial | N/A |
|----------|-------|-----------|---------|---------|-----|
| P0 | 9 | 8 | 1 | 0 | 0 |
| P1 | 18 | 14 | 4 | 0 | 1 |
| P2 | 11 | 2 | 7 | 2 | 0 |
| P3 | 10 | 4 | 6 | 0 | 0 |
| **Total** | **48** | **28** | **18** | **2** | **1** |

**Progress: 28/48 resolved (58%) — up from 12/49 (24%) at session start**

---

## REMAINING WORK TO REACH ~90/100 (estimated 12–15 hours)

| Item | Est. Time | Impact |
|------|-----------|--------|
| P1-07 Self-service cancellation | 3h | Legal compliance + chargeback reduction |
| P1-02 Salt IP/device hashes | 1h | Security hardening |
| P1-03 Salt bot token hash | 2h | Security + migration |
| P1-10 Scheduler per-task timeout | 2h | Reliability |
| P0-04 Marketplace escrow audit | 4h | Stuck funds risk |
| P2-02 Tab overflow on mobile | 1h | Mobile UX |
| P2-03 Table overflow on mobile | 2h | Mobile UX |
| P2-07 Payment reversal handling | 2h | Payment integrity |
| P2-11 3-day grace period backend | 2h | Retention |
| P3-07 Custom bot Smart Links | 3h | Bot parity |
| P3-08 pending_verifications cleanup | 0.5h | DB hygiene |
| P3-09 Bot removal detection | 1h | Bot reliability |

---

## WORKFLOW REMINDER (read every session)

```
1. Read AUDIT_FIX_PROGRESS.md first
2. Identify the highest-priority [PENDING] item
3. Implement ONLY that item unless instructed otherwise
4. After implementation:
   - Change status from [PENDING] → [COMPLETED] or [PARTIAL]
   - Add: date, files changed, summary of what was done
   - Update SUMMARY COUNTERS table
   - Recalculate and update CURRENT LAUNCH READINESS SCORE if significant
5. State the next recommended fix at the end of the session
```
