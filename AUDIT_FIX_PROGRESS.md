# TELEGIZER AUDIT FIX PROGRESS TRACKER
**Living document — single source of truth until 100/100 launch readiness**  
**Full audit report:** `TELEGIZER_MASTER_AUDIT_ROADMAP.md`  
**Rule:** Read this file FIRST at the start of every session. Fix highest-priority PENDING item. Update status after every fix.

---

## CURRENT LAUNCH READINESS SCORE

| Surface | Initial | Current | Target |
|---------|---------|---------|--------|
| Acquisition readiness | 42 | 42 | 85 |
| UX / Onboarding | 51 | 51 | 85 |
| Mobile responsiveness | 68 | 68 | 85 |
| Frontend architecture | 72 | 75 | 90 |
| Backend architecture | 78 | 85 | 92 |
| Security | 74 | 80 | 92 |
| Payment readiness | 81 | 88 | 95 |
| Telegram bot reliability | 80 | 80 | 90 |
| Feature completeness | 76 | 76 | 88 |
| **OVERALL** | **61** | **69** | **100** |

_Score last updated: 2026-04-29 after Session 1 fixes_

---

## ▶ NEXT RECOMMENDED FIX

**[P0-05] Add axios request timeout** — `frontend/src/services/api.js`  
Single 3-line change. Zero risk. Prevents entire UI from hanging on slow API calls.  
After that: **[P0-01] Landing page overhaul** — biggest impact on launch readiness.

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ACTIVE ISSUES — P0 (Must Fix Before Any Public Launch)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P0-01] [PENDING] Landing page doesn't explain the product in 10 seconds
- **File:** `frontend/src/pages/Landing.js`
- **Issue:** No product screenshot, no demo video, no "How it works" section, no trust stats, no crypto-only disclosure, no pricing preview, no secondary CTA
- **Fix needed:**
  - Add hero screenshot or animated GIF of the dashboard
  - Add "How it works" section (3 steps: Sign up → Add bot → Manage from dashboard)
  - Add inline pricing preview (Free/Pro/Enterprise cards)
  - Add "Pay with crypto (USDT/BTC/ETH)" label near CTA
  - Add one live stat ("X groups protected", "Y messages moderated")
  - Add secondary CTA to /pricing alongside primary "Get Started"
  - Link to /directory for organic SEO
- **Expected impact:** +15 points acquisition score

---

### [P0-02] [PENDING] No step-by-step onboarding after signup
- **File:** `frontend/src/pages/Dashboard.js`, `frontend/src/pages/MyGroups.js`
- **Issue:** Users reach empty dashboard with collapsed onboarding card, no Telegram deep link, no guided bot-add flow, no activation moment
- **Fix needed:**
  - Make OnboardingCard expanded by default for new users (first 24h of account)
  - Add Telegram deep link: `https://t.me/telegizer_bot?start=link` in "Add your first group" step
  - Add step-by-step guide in MyGroups.js empty state: (1) Add @telegizer_bot to your group → (2) Make it admin → (3) Type /linkgroup → (4) Enter code here
  - Track step completion in backend (`User.onboarding_step` column or similar)
  - Add success celebration modal after first group linked
- **Expected impact:** +15 points onboarding score

---

### [P0-03] [PENDING] Knowledge Base RAG is advertised but has zero backend implementation
- **File:** `backend/routes/knowledge.py`, `frontend/src/components/KnowledgeBase.js`
- **Issue:** Upload UI exists, `KnowledgeDocument` model has `chunks` column, but zero embedding, search, or query endpoint exists anywhere in backend
- **Fix needed (Option A — Build it):**
  - Add OpenAI `text-embedding-3-small` embedding on document upload
  - Store embeddings in `pgvector` extension or as serialized numpy arrays
  - Add `POST /api/knowledge/query` endpoint: embed query, cosine-similarity search, return top-k chunks
  - Wire query response to bot: when member asks question, search KB first
- **Fix needed (Option B — Hide it):**
  - Add "Coming Soon" badge to Knowledge Base tab in GroupManagement.js
  - Remove search/query UI from KnowledgeBase.js (keep upload only)
  - Show clear message: "AI search coming in next update — documents are saved for when it launches"
- **Recommended:** Option B for launch speed; Option A in P2 sprint
- **Expected impact:** Removes false advertising risk

---

### [P0-04] [PENDING] Marketplace escrow payment flow unverified end-to-end
- **File:** `backend/routes/marketplace.py`, `frontend/src/pages/MarketplaceDeal.js`
- **Issue:** `PartnershipDeal` table and routes exist (`create`, `accept`, `pay`, `deliver`, `dispute`), but escrow payment release and reconciliation logic has not been tested end-to-end. Funds could get stuck.
- **Fix needed:**
  - Trace full escrow flow: buyer pays → NOWPayments IPN fires → `payment_status` updated → seller delivers → admin/buyer marks complete → funds released
  - Verify each step has a route and is wired to IPN correctly
  - If any step is missing, implement or disable marketplace temporarily
  - Add integration test: create deal → pay → mark delivered → verify seller_payout triggered
- **Expected impact:** Removes high-risk stuck-funds scenario

---

### [P0-05] [PENDING] No axios request timeout — UI hangs indefinitely on slow calls
- **File:** `frontend/src/services/api.js`
- **Issue:** axios instance created with no `timeout` option. Any slow Railway API call hangs the UI forever — spinner never stops.
- **Fix needed:** Add `timeout: 30000` to axios instance creation (3-line change)
- **Exact change:**
  ```js
  const api = axios.create({
    baseURL: API_URL,
    timeout: 30000,   // ← add this line
    headers: { 'Content-Type': 'application/json' },
  });
  ```
- **Expected impact:** +3 frontend architecture score, prevents UI hangs

---

### [P0-06] [PENDING] Pricing page doesn't disclose crypto-only payments
- **File:** `frontend/src/pages/Pricing.js`
- **Issue:** Zero mention of "crypto only", "USDT", "BTC", or "ETH" anywhere on pricing page. Users expecting card payment will rage-quit at checkout.
- **Fix needed:**
  - Add "💳 Pay with crypto (USDT, BTC, ETH)" label under each paid plan's CTA button
  - Add small FAQ section at bottom: "What payment methods do you accept?", "Do you offer refunds?", "What happens if I cancel?"
  - Add "Annual billing — save 17%" badge to Pro and Enterprise annual toggle
- **Expected impact:** Reduces checkout abandonment significantly

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ACTIVE ISSUES — P1 (Fix Before First Paid Users)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P1-01] [PENDING] TOTP backup codes not revoked on regeneration
- **File:** `backend/routes/totp.py`
- **Issue:** When user regenerates backup codes, new codes are generated but old bcrypt-hashed codes are NOT deleted from `User.totp_backup_codes`. Old codes remain valid indefinitely.
- **Fix needed:** On regeneration, replace `totp_backup_codes` list entirely with newly hashed codes (not append)
- **Security impact:** P1 — old leaked codes remain working

---

### [P1-02] [PENDING] IP hash and device fingerprint hash are unsalted
- **File:** `backend/routes/auth.py:121-123`
- **Issue:** `SHA-256(IP_address)` with no salt — IPv4 space is only ~4 billion addresses, fully rainbow-table-reversible. Same for device fingerprint hash.
- **Fix needed:** Use `HMAC-SHA256(secret_key, IP_address)` where secret_key is a dedicated env var (`HASH_PEPPER` or reuse `SECRET_KEY`)
  ```python
  import hmac, hashlib
  def _hash_identifier(value: str) -> str:
      return hmac.new(Config.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
  ```
- **Security impact:** P1 — prevents rainbow table reversal of stored IP hashes

---

### [P1-03] [PENDING] Bot token SHA-256 hash unsalted
- **File:** `backend/models.py:122-124`
- **Issue:** Bot token stored encrypted (good) but also hashed for search/dedup purposes using plain SHA-256 with no salt — rainbow table reversal possible
- **Fix needed:** Same HMAC approach as P1-02, use `HMAC-SHA256(SECRET_KEY, token)` for the hash column
- **Security impact:** P1

---

### [P1-04] [PENDING] No SSRF protection on user-provided webhook URLs
- **File:** `backend/routes/webhooks.py`
- **Issue:** Users can register any URL as a webhook destination. Attacker could set `http://169.254.169.254/latest/meta-data/` (AWS metadata) or internal Railway service URLs to exfiltrate environment.
- **Fix needed:** Before saving webhook URL, validate it resolves to a public IP:
  ```python
  import ipaddress, socket
  def _is_safe_url(url: str) -> bool:
      host = urllib.parse.urlparse(url).hostname
      ip = socket.gethostbyname(host)
      addr = ipaddress.ip_address(ip)
      return not (addr.is_private or addr.is_loopback or addr.is_link_local)
  ```
- **Security impact:** P1 — SSRF could expose Railway internal metadata

---

### [P1-05] [PENDING] No MIME type validation on knowledge base uploads
- **File:** `backend/routes/knowledge.py`
- **Issue:** Knowledge base upload accepts any file type. Attacker could upload .exe, .php, or oversized binary files.
- **Fix needed:** Whitelist MIME types: `application/pdf`, `text/plain`, `text/markdown`. Check both Content-Type header and file magic bytes. Enforce 10MB max per document.
- **Security impact:** P1

---

### [P1-06] [PENDING] `revoked_tokens` DB table grows forever — no TTL cleanup
- **File:** `backend/routes/auth.py`, `backend/app.py:_scheduler_loop`
- **Issue:** Every logout writes a row to `revoked_tokens`. No cleanup job exists. Table will grow unbounded in production.
- **Fix needed:** Add to scheduler (runs daily):
  ```python
  def _cleanup_revoked_tokens():
      from .models import db
      db.session.execute(text("DELETE FROM revoked_tokens WHERE expires_at < NOW()"))
      db.session.commit()
  ```
- **Impact:** DB bloat, eventual query slowdown on token blocklist checks

---

### [P1-07] [PENDING] No self-service subscription cancellation endpoint
- **File:** `backend/routes/billing.py`, `frontend/src/pages/Billing.js`
- **Issue:** Users cannot cancel their subscription themselves — must contact support. No cancellation endpoint exists.
- **Fix needed:**
  - Add `DELETE /api/billing/subscription` endpoint — sets `subscription_expires = now()` (access ends immediately) or `subscription_expires = current_period_end` (access until period end)
  - Add "Cancel subscription" button in Billing.js with confirmation dialog
  - Send cancellation confirmation email
- **Impact:** Legal requirement in many jurisdictions; also reduces chargeback risk

---

### [P1-08] [PENDING] No request size limit explicitly configured
- **File:** `backend/app.py`
- **Issue:** Flask default is 16MB but not explicitly set. Knowledge base uploads + webhook payloads could be abused.
- **Fix needed:**
  ```python
  app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB hard cap
  ```
  Add handler for `413 Request Entity Too Large`:
  ```python
  @app.errorhandler(413)
  def request_too_large(e):
      return jsonify({"error": "File too large. Maximum size is 16MB.", "code": "FILE_TOO_LARGE"}), 413
  ```
- **Impact:** Prevents memory exhaustion and disk abuse

---

### [P1-09] [PENDING] Referral link not surfaced on Dashboard
- **File:** `frontend/src/pages/Dashboard.js`, `frontend/src/pages/Settings.js`
- **Issue:** Referral share link is buried in Settings page. Users who want to refer others won't find it organically. This is a key growth mechanic being wasted.
- **Fix needed:**
  - Add "Refer & Earn" card to Dashboard sidebar or main area
  - Show: referral link (copy button), current count, next milestone progress bar
  - Example: "2/3 referrals → 1 month Pro free"
- **Impact:** Growth mechanic currently invisible

---

### [P1-10] [PENDING] Scheduler tasks have no per-task timeout — one hung task blocks all
- **File:** `backend/app.py:_scheduler_loop`
- **Issue:** `_run_scheduled_messages()`, `_deliver_reminders()` etc. run sequentially with no timeout. If any task blocks (DB timeout, Telegram API hang), all subsequent tasks in that 60s tick are skipped.
- **Fix needed:** Wrap each task in a thread with timeout:
  ```python
  import concurrent.futures
  with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
      future = ex.submit(_run_scheduled_messages)
      try:
          future.result(timeout=30)
      except concurrent.futures.TimeoutError:
          _scheduler_log.error("_run_scheduled_messages timed out after 30s")
  ```
- **Impact:** Prevents cascade failure in scheduler

---

### [P1-11] [PENDING] No Content-Security-Policy header
- **File:** `backend/app.py`
- **Issue:** No CSP header sent with any response. Increases XSS exploitability.
- **Fix needed:** Add `after_request` hook:
  ```python
  @app.after_request
  def _add_security_headers(response):
      response.headers['Content-Security-Policy'] = (
          "default-src 'self'; "
          "script-src 'self' 'unsafe-inline'; "
          "style-src 'self' 'unsafe-inline'; "
          "img-src 'self' data: https:; "
          "connect-src 'self' https://api.nowpayments.io https://t.me;"
      )
      response.headers['X-Content-Type-Options'] = 'nosniff'
      response.headers['X-Frame-Options'] = 'DENY'
      return response
  ```
- **Impact:** P1 security hardening

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ACTIVE ISSUES — P2 (Improve After Launch)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P2-01] [PENDING] No mobile bottom navigation bar
- **File:** `frontend/src/layouts/AppLayout.js`
- **Issue:** Mobile users must open drawer sidebar to navigate. Bottom nav (Home/Groups/Channels/Workspace/Account) is the standard SaaS mobile pattern.
- **Fix needed:** Add `<BottomNavigation>` MUI component shown only on `xs`/`sm` breakpoints

---

### [P2-02] [PENDING] Group settings tab bar overflows on mobile
- **File:** `frontend/src/pages/GroupManagement.js`
- **Issue:** 14-tab tab bar overflows and clips on mobile screens. No scroll indicator.
- **Fix needed:** Wrap in `<Box sx={{ overflowX: 'auto' }}>` with `scrollbarWidth: 'none'` and add gradient fade on right edge to indicate scroll

---

### [P2-03] [PENDING] Dense tables overflow on mobile (Settings, Billing, AdminPanel)
- **File:** `frontend/src/pages/Settings.js`, `frontend/src/pages/Billing.js`, `frontend/src/pages/AdminPanel.js`
- **Fix needed:** Wrap all `<Table>` in `<Box sx={{ overflowX: 'auto' }}>`. On `xs` breakpoint, switch payment history and member tables to card-based list view.

---

### [P2-04] [PENDING] Telegram Mini App SDK wiring unverified
- **File:** `frontend/src/pages/MiniApp.js`, `frontend/src/layouts/MiniAppLayout.js`
- **Fix needed:**
  - Verify `window.Telegram.WebApp.ready()` called on mount
  - Wire `Telegram.WebApp.BackButton.show()` on nested pages
  - Sync `colorScheme` with `Telegram.WebApp.colorScheme`
  - Add `env(safe-area-inset-bottom)` padding to bottom nav
  - Test on real Telegram client (Android + iOS)

---

### [P2-05] [PENDING] PWA manifest needs audit
- **File:** `frontend/public/manifest.json`
- **Fix needed:**
  - Verify 512x512 maskable icon exists and is correct format
  - `theme_color` and `background_color` must match dark theme (`#0f0f0f` / `#1a1a2e`)
  - Add `"display": "standalone"` if not present
  - Create offline fallback page (`/offline.html`) and register in service worker

---

### [P2-06] [PENDING] No centralized PlanGate component for consistent upgrade UX
- **File:** `frontend/src/App.js`, multiple page files
- **Issue:** Every page implements its own upgrade wall differently — some show alerts, some redirect, some silently fail.
- **Fix needed:** Create `frontend/src/components/PlanGate.js`:
  ```jsx
  // Usage: <PlanGate plan="pro" feature="AI Digest">…content…</PlanGate>
  // Shows consistent upgrade modal when user.subscription_tier < required plan
  ```

---

### [P2-07] [PENDING] No payment reversal/refund handling
- **File:** `backend/routes/billing.py`
- **Issue:** If NOWPayments reverses a payment (chargeback), subscription is never revoked.
- **Fix needed:** Handle `payment_status: "refunded"` / `"partially_refunded"` in IPN handler. Set `subscription_tier = "free"` and `subscription_expires = null` on reversal. Send notification email.

---

### [P2-08] [PENDING] Sentry not capturing API client errors
- **File:** `frontend/src/services/api.js`
- **Issue:** API errors are caught and handled but never sent to Sentry. Production errors from the frontend are invisible.
- **Fix needed:**
  ```js
  import * as Sentry from '@sentry/react';
  // In response interceptor error handler:
  if (error.response?.status >= 500) {
    Sentry.captureException(error);
  }
  ```

---

### [P2-09] [PENDING] Missing DB indexes for scheduler performance
- **File:** `backend/app.py` migration functions
- **Issues:**
  - `workspace_reminders`: missing composite index on `(is_delivered, remind_at)` — full table scan every 60s
  - `scheduled_messages`: missing index on `(is_sent, send_at)` — full scan on scheduler tick
  - `telegram_groups`: no UNIQUE on `(telegram_group_id, owner_user_id)` — same group linkable twice
- **Fix needed:** Add to a new `_run_performance_migrations()` function called at startup

---

### [P2-10] [PENDING] AI Digest delivery fails silently if user hasn't DM'd bot
- **File:** `backend/app.py:_scheduler_loop` (digest section)
- **Issue:** `TelegramBotStarted.has_started()` check causes silent failure — digest never delivered. No notification to admin.
- **Fix needed:** Email fallback for digest delivery (same pattern as reminders fix) + log as WARNING not DEBUG

---

### [P2-11] [PENDING] No subscription grace period or UX for expired accounts
- **File:** `frontend/src/pages/Dashboard.js`, `backend/routes/billing.py`
- **Issue:** Subscription expires → features immediately stop → user confused with no clear path to renew. No grace period.
- **Fix needed:**
  - 3-day grace period: user retains access but sees prominent "Your plan expired X days ago" banner
  - After grace period, soft-downgrade to free tier with clear "Renew to restore" CTA
  - Send day-of-expiry email (separate from 5d/1d warnings already fixed)

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ACTIVE ISSUES — P3 (Polish)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P3-01] [PENDING] `polls.options` JSON has no array-length cap
- **File:** `backend/models.py` (Poll model) + poll creation route
- **Fix needed:** Validate `len(options) <= 10` in poll creation endpoint

### [P3-02] [PENDING] `scheduled_messages.repeat_interval` has no upper bound
- **File:** `backend/models.py` (ScheduledMessage) + creation route
- **Fix needed:** Validate `repeat_interval is None or 60 <= repeat_interval <= 10080` (1min to 1 week in minutes)

### [P3-03] [PENDING] Referral code entropy reduced by truncation
- **File:** `backend/models.py:54`
- **Current:** `secrets.token_urlsafe(8)[:10]` — truncating reduces entropy
- **Fix needed:** `secrets.token_urlsafe(12)` — no truncation, full entropy

### [P3-04] [PENDING] `DEBUG` mode not explicitly forced False in production
- **File:** `backend/app.py`
- **Fix needed:** Add `app.config['DEBUG'] = False` explicitly, or ensure `FLASK_ENV=production` in Railway

### [P3-05] [PENDING] Custom bot parity — Verification system missing from BYOB
- **File:** `backend/bot_manager.py`
- **Fix needed:** Port verification handlers (button challenge, text answer) from `official_bot.py` to custom bot handler framework

### [P3-06] [PENDING] Custom bot parity — XP system missing from BYOB
- **File:** `backend/bot_manager.py`
- **Fix needed:** Port XP earn/level-up logic from `official_bot.py`. Requires either creating `OfficialMember` rows for custom bot groups or a separate XP table

### [P3-07] [PENDING] Custom bot parity — Smart Links missing from BYOB
- **File:** `backend/bot_manager.py`
- **Fix needed:** On new message in custom bot group, query `AutoResponse` table for smart link triggers (same as official bot does)

### [P3-08] [PENDING] Expired `pending_verifications` rows never cleaned up
- **File:** `backend/app.py:_scheduler_loop`
- **Fix needed:** Add daily cleanup task:
  ```python
  db.session.execute(text("DELETE FROM pending_verifications WHERE expires_at < NOW()"))
  ```

### [P3-09] [PENDING] No bot removal detection when bot is kicked from group
- **File:** `backend/official_bot.py`
- **Fix needed:** Handle `chat_member` update where `new_chat_member.status == "left"` for the bot itself → set `TelegramGroup.bot_status = "removed"`

### [P3-10] [PENDING] Directory not linked from landing page — zero SEO value
- **File:** `frontend/src/pages/Landing.js`
- **Fix needed:** Add "Discover Communities" section on landing that links to `/directory` with 3-4 featured listings

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## RESOLVED ISSUES (Completed — Archive)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### [P0-DONE-01] [COMPLETED] Remove localhost:5000 proxy from frontend/package.json
- **Date fixed:** 2026-04-29
- **Files changed:** `frontend/package.json`
- **Summary:** Removed `"proxy": "http://localhost:5000"` line. All API calls now use `REACT_APP_API_URL` env var exclusively. Without this fix, every production user's browser was sending API calls to their own machine.
- **Commit:** 15468b4

---

### [P0-DONE-02] [COMPLETED] CORS adds localhost to allowed origins in production
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/app.py:103-131`
- **Summary:** Fixed CORS logic to strip localhost/127.0.0.1 origins when `DATABASE_URL` contains PostgreSQL. Previously only logged a warning but still added localhost to the allow-list. Now actively removes them and logs an ERROR. Never goes to an empty allow-list (keeps non-localhost origins).
- **Commit:** 15468b4

---

### [P0-DONE-03] [COMPLETED] `_deferred_bot_start()` had no exception handler — crashed silently
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/app.py:343-403`
- **Summary:** Replaced bare thread launch with full try/except + exponential backoff retry (5 attempts: 5s→10s→20s→40s→60s for custom bots; 10s→20s→40s→80s→120s for official bot). Each failure logged with ERROR level and captured to Sentry. On permanent failure, CRITICAL log emitted. Health check can now return 200 while this is retrying — intended behavior so Gunicorn stays alive.
- **Commit:** 15468b4

---

### [P0-DONE-04] [COMPLETED] Hard-fail at startup if EMAIL_PROVIDER empty in production
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/config.py:82-95`
- **Summary:** Added `RuntimeError` at startup when `DATABASE_URL` contains PostgreSQL and `EMAIL_PROVIDER` is empty. Also added startup fail when `FRONTEND_URL` defaults to localhost in production. Both checks prevent the app from booting with broken email/link configuration.
- **Commit:** 15468b4

---

### [P1-DONE-01] [COMPLETED] ADMIN_EMAILS empty logged warning only — no enforcement
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/config.py:104-113`
- **Summary:** Changed ADMIN_EMAILS validation from a log.warning to a `RuntimeError` when `_is_prod=True`. App now refuses to start in production without admin emails configured. Dev environments still warn and continue.
- **Commit:** 15468b4

---

### [P1-DONE-02] [COMPLETED] NOWPayments webhook bypasses dedup when payment_id is NULL
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/routes/billing.py:250-260`
- **Summary:** Added explicit rejection (HTTP 400) when `payment_id` is missing from webhook payload. Previously the code checked `if payment_id:` and skipped dedup entirely when null, allowing the same payment to activate a subscription multiple times via repeated webhooks. Now `payment_id` is required at the entry point before any processing occurs.
- **Commit:** 15468b4

---

### [P1-DONE-03] [COMPLETED] No server-side price validation in billing webhook
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/routes/billing.py:302-316`
- **Summary:** Added server-side price validation against `_TIER_PRICES_USD[tier][billing_period]`. Allows up to 5% underpayment for exchange rate slippage but rejects anything more. Returns HTTP 400 with clear error message. Prevents plan upgrade via manipulated invoice amounts.
- **Commit:** 15468b4

---

### [P1-DONE-04] [COMPLETED] Suspicious users not blocked from initiating payment
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/routes/billing.py:168-176`
- **Summary:** Added `is_suspicious` check at crypto checkout entry point. Users flagged for referral abuse or other suspicious activity receive HTTP 403 with message directing them to support. Previously the flag was set but never enforced at payment time.
- **Commit:** 15468b4

---

### [P1-DONE-05] [COMPLETED] Reminder delivery silently marks undeliverable reminders as delivered
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/app.py:_deliver_reminders` (~1395-1486)
- **Summary:** Complete rewrite of reminder delivery logic. Now: (1) Attempt Telegram DM if user has connected Telegram AND has previously DM'd the bot. (2) If Telegram delivery fails or not possible, attempt email fallback via `send_email()`. (3) If email also fails, keep `is_delivered=False` and retry on next scheduler tick. (4) Force-expire reminders older than 24 hours to prevent infinite loops. Previously all reminders where user hadn't DM'd the bot were immediately marked delivered without any delivery attempt.
- **Commit:** 15468b4

---

### [P1-DONE-06] [COMPLETED] Subscription expiry: only in-app notification, no email warning
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/notifications.py` (added `send_subscription_expiry_warning()`), `backend/app.py:_run_expiry_notifications`
- **Summary:** Extended `_run_expiry_notifications()` to send actual warning emails at 5-day and 1-day marks (previously only created in-app notifications). Added `send_subscription_expiry_warning()` HTML email template to notifications.py. Deduplication: uses the existing 12-hour cooldown check on `UserNotification` records. Dashboard and Billing page already had expiry banners — both verified present.
- **Commit:** 15468b4

---

### [P1-DONE-07] [COMPLETED] Rate limiting falls back to in-process counter in production
- **Date fixed:** 2026-04-29
- **Files changed:** `backend/middleware/rate_limit.py`
- **Summary:** Added `_is_production()` helper that detects PostgreSQL in DATABASE_URL. When Redis is unavailable in production, rate limiter now returns HTTP 503 instead of falling back to per-process in-memory counter. In-memory fallback is meaningless in production: it resets on every deploy and is not shared across Gunicorn workers. The 503 makes the problem visible and alertable. Dev environments still use in-process fallback.
- **Commit:** 15468b4

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## SUMMARY COUNTERS
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| Priority | Total | Completed | Pending | Partial | Deferred |
|----------|-------|-----------|---------|---------|----------|
| P0 | 10 | 4 | 6 | 0 | 0 |
| P1 | 18 | 7 | 11 | 0 | 0 |
| P2 | 11 | 0 | 11 | 0 | 0 |
| P3 | 10 | 0 | 10 | 0 | 0 |
| **Total** | **49** | **11** | **38** | **0** | **0** |

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
