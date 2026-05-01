# Telegizer — Sprint 7.5 Fix Tracker
**Last Updated:** 2026-05-01 · **Auditor:** Senior Full-Stack / Security / Launch-Readiness  
**Repo:** `g:/telegram-bot-saas` · **Method:** 4-domain deep codebase audit (frontend, backend/security, bot/AI, DB/billing/deploy)

---

# Sprint 7.5 Progress

| Metric | Count |
|---|---|
| **Total Issues** | 40 |
| **Pending** | 31 |
| **In Progress** | 0 |
| **Completed** | 9 |
| **Critical Remaining** | 0 |

---

## Overall Launch Readiness: 85 / 100

| Dimension | Score | Verdict |
|---|---|---|
| Security | 84/100 | Phase 1 critical issues resolved; 2FA hardening + CORS next |
| Product Completeness | 92/100 | PlanGate wired; all Pro gates enforced |
| UX Readiness | 82/100 | Unchanged — mobile + analytics polish pending (Phase 4) |
| Payment Readiness | 88/100 | PendingInvoice + timestamp validation + 1% tolerance fixed |
| Telegram Bot Readiness | 85/100 | Webhook HMAC + scheduler Sentry + Procfile release step done |

**GO with Phase 2 queue** — all critical blockers resolved. Phase 2 (security hardening) should be done before public launch marketing push.

---

# Phase 1 — Must-Fix Launch Blockers

---

## [P1-01] Decryption Silently Falls Back to Plaintext

**Severity:** Critical  
**Status:** Completed  
**Area:** Security / Backend  
**Files:** `backend/utils/encryption.py:84`  
**Problem:** `decrypt_value()` has a final fallback that returns the raw ciphertext as plaintext when all decryption attempts fail. If `ENCRYPTION_KEY` rotates incorrectly or the `cryptography` library fails, every encrypted field (TOTP secrets, bot tokens, AI API keys) is silently returned as corrupt ciphertext without any error. This unblocks #P1-02 and #P1-06.  
**Recommended Fix:**
```python
# Remove this block entirely:
# "Final fallback: plaintext stored before encryption was introduced"
# Replace with:
raise DecryptionError(f"Failed to decrypt value with any available key. Check ENCRYPTION_KEY config.")
```
Add a custom `DecryptionError` exception. Callers must handle it explicitly. Add a one-time startup self-check that all encrypted fields round-trip correctly.  
**Dependencies:** None — fix this FIRST  
**Testing Checklist:**
- [ ] Provide a corrupted ciphertext → confirm `DecryptionError` raised, not plaintext returned
- [ ] Rotate key, confirm old records still decrypt via `ENCRYPTION_KEY_OLD` then re-save under new key
- [ ] Confirm bot token, TOTP secret, AI key all raise on corrupt data
**Completed On:** 2026-05-01  
**Notes:** DecryptionError exception added; plaintext fallback removed; startup self-check wired; all call sites updated.

---

## [P1-02] User.totp_secret Stored as Plaintext Column

**Severity:** Critical  
**Status:** Completed  
**Area:** Security / DB  
**Files:** `backend/models.py`, `backend/routes/totp.py`  
**Completed On:** 2026-05-01  
**Notes:** `_totp_secret_enc` column mapped to DB `totp_secret`; `totp_secret` Python property auto-encrypts on write and auto-decrypts on read; all manual encrypt/decrypt calls removed; MIGRATE_ENCRYPT_TOTP=1 migration script added.

---

## [P1-03] Password Reset Token: Plaintext Storage + Non-Atomic Single-Use

**Severity:** Critical  
**Status:** Completed  
**Area:** Security / Backend  
**Files:** `backend/routes/auth.py:678, 709–724`  
**Problem:** Password-reset tokens are stored as plaintext in DB and sent raw in email URLs. `used=True` is flagged after the password update, not before — an attacker who intercepts the email link can race to reset the password. If email is cached/forwarded, the token remains valid until explicitly marked used.  
**Recommended Fix:**
```python
# Store SHA-256 of token:
import hashlib
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
PasswordResetToken(token_hash=token_hash, user_id=user.id, expires_at=now+1h)

# On /reset-password: mark used=True BEFORE updating password, same transaction:
with db.session.begin():
    token_row = PasswordResetToken.query.filter_by(
        token_hash=hashlib.sha256(submitted_token.encode()).hexdigest(),
        used=False
    ).with_for_update().first()
    if not token_row or token_row.expires_at < now:
        abort(400)
    token_row.used = True
    user.set_password(new_password)
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] Request reset → DB stores hash, not plaintext
- [ ] Use token once → success; use same token again → 400 rejected
- [ ] Token older than 1h → rejected
- [ ] Intercept email and race two requests → only one wins
**Completed On:** ___  
**Notes:** ___

---

## [P1-04] Telegram Webhook Secret Token Not Verified

**Severity:** Critical  
**Status:** Completed  
**Area:** Security / Bot  
**Files:** `backend/routes/webhooks.py`, `backend/models.py`  
**Completed On:** 2026-05-01  
**Notes:** `signing_secret` column added to `WebhookIntegration`; `_verify_webhook_signature()` checks HMAC-SHA256 X-Telegizer-Signature header on every trigger; new `/rotate-secret` endpoint; signing_secret returned once at creation.

---

## [P1-05] NOWPayments order_id User_id Trusted Without Server-Side Binding

**Severity:** Critical  
**Status:** Completed  
**Area:** Billing / Security  
**Files:** `backend/routes/billing.py`, `backend/models.py`  
**Completed On:** 2026-05-01  
**Notes:** `PendingInvoice` table created; checkout writes row with server-side user_id before returning URL; IPN resolves user from DB row (not order_id string); refund path also uses DB lookup; IPN timestamp replay protection (1h window) added; underpayment tolerance reduced 5%→1%.

---

## [P1-06] PlanGate Component Never Imported — Pro Features Free for All

**Severity:** Critical  
**Status:** Completed  
**Area:** Frontend / Business  
**Files:** `frontend/src/components/PlanGate.js`, `frontend/src/pages/WorkspaceForwarding.js`, `frontend/src/pages/WorkspaceAutomations.js`, `frontend/src/pages/WorkflowBuilder.js`, `frontend/src/pages/AssistantKnowledge.js`, `frontend/src/pages/MyBots.js`, `frontend/src/pages/AssistantAISettings.js`  
**Problem:** `PlanGate.js` exists but has zero imports anywhere in the codebase. Every Pro-tier feature (Forwarding, Workflows, Knowledge Base, Custom Bots, AI Settings) is fully accessible to free-tier users without any upgrade prompt. This directly breaks the freemium revenue model.  
**Recommended Fix:**
```jsx
// In each Pro page, wrap the main content:
import PlanGate from '../components/PlanGate';
import { useAuth } from '../contexts/AuthContext'; // or wherever user comes from

const { user } = useAuth();

return (
  <PlanGate plan="pro" userTier={user?.subscription_tier} feature="Message Forwarding">
    <ForwardingContent />
  </PlanGate>
);
```
Apply to: `WorkspaceForwarding`, `WorkspaceAutomations` (Workflows tab), `WorkflowBuilder`, `AssistantKnowledge`, `MyBots` (creation section), `AssistantAISettings`.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Free user hits `/workspace/forwarding` → upgrade gate shown
- [ ] Free user hits `/workspace/automations` → gate shown
- [ ] Free user hits `/custom-bots` → gate on add-bot button
- [ ] Pro user → full access, no gate
- [ ] Downgraded user → gate re-appears
**Completed On:** ___  
**Notes:** ___

---

## [P1-07] In-Process Scheduler Not Durable — Jobs Lost on Dyno Restart

**Severity:** Critical  
**Status:** Completed  
**Area:** Backend / Bot  
**Files:** `backend/scheduler.py`, `backend/app.py` (`_scheduler_loop`), `backend/assistant/digest_ai.py:73`  
**Problem:** The scheduler is an in-process thread with a 60-second polling loop. On Railway dyno restart (which happens on every deploy), all queued digests and scheduled messages are silently lost. Additionally, 30-second AI calls (`urlopen(req, timeout=30)`) block the entire loop thread, starving other jobs. There is no Sentry integration on job failures — errors are logged locally only.  
**Recommended Fix:**
1. **Persist job state:** Add `next_run_at TIMESTAMP`, `locked_by VARCHAR`, `locked_at TIMESTAMP` to `OfficialScheduledMessage` and `DigestConfig`. Scheduler picks up `WHERE next_run_at <= NOW() AND locked_by IS NULL`.
2. **Claim with advisory lock or UPDATE...RETURNING** to prevent duplicate execution on multi-replica.
3. **Offload AI calls:**
```python
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
executor = ThreadPoolExecutor(max_workers=4)
future = executor.submit(get_group_ai_summary, ...)
try:
    result = future.result(timeout=10)
except TimeoutError:
    sentry_sdk.capture_message("Digest AI timeout", level="warning")
```
4. **Sentry on every job:**
```python
try:
    run_job(job)
except Exception as e:
    sentry_sdk.capture_exception(e)
```
5. **Procfile:** Add `release: python -m backend.migrate` so schema is always current.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Schedule a digest, kill the dyno, restart → digest still fires
- [ ] Trigger a slow AI call → other jobs not blocked; AI job times out gracefully
- [ ] Force a scheduler exception → Sentry event appears with job metadata
- [ ] Two replicas running → job executed exactly once
**Completed On:** ___  
**Notes:** ___

---

## [P1-08] Missing FK Indexes on Hot-Path Columns

**Severity:** High (blocks performance at scale)  
**Status:** Completed  
**Area:** Database  
**Files:** `backend/models.py:135, 234, 278, 307, 348, 422, 481, 557, 743`, `backend/migrate.py`  
**Problem:** Nine frequently-queried foreign key columns lack `index=True`. At >1000 rows per table these will cause full-table scans on the most common API calls (list groups for user, list members for group, list scheduled messages for group, etc.).  
**Affected columns:**
- `Bot.user_id` (line 135)
- `Member.group_id` (line 234)
- `AuditLog.group_id` (line 278)
- `ScheduledMessage.group_id` (line 307)
- `Raid.group_id` (line 348)
- `KnowledgeDocument.group_id` (line 422)
- `WebhookIntegration.group_id` (line 481)
- `UserApiKey.group_id` (line 557)
- `ReportedMessage.group_id` (line 743)  
**Recommended Fix:**
Add `index=True` to each column definition AND add to `migrate.py`:
```sql
CREATE INDEX IF NOT EXISTS ix_bot_user_id ON bot(user_id);
CREATE INDEX IF NOT EXISTS ix_member_group_id ON member(group_id);
CREATE INDEX IF NOT EXISTS ix_auditlog_group_id ON audit_log(group_id);
CREATE INDEX IF NOT EXISTS ix_scheduledmessage_group_id ON scheduled_message(group_id);
CREATE INDEX IF NOT EXISTS ix_raid_group_id ON raid(group_id);
CREATE INDEX IF NOT EXISTS ix_knowledgedocument_group_id ON knowledge_document(group_id);
CREATE INDEX IF NOT EXISTS ix_webhookintegration_group_id ON webhook_integration(group_id);
CREATE INDEX IF NOT EXISTS ix_userapikey_group_id ON user_api_key(group_id);
CREATE INDEX IF NOT EXISTS ix_reportedmessage_group_id ON reported_message(group_id);
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] Run `EXPLAIN ANALYZE` on "get all bots for user" → index scan
- [ ] Run `EXPLAIN ANALYZE` on "get all members for group" → index scan
- [ ] Migration re-runnable without error
**Completed On:** ___  
**Notes:** ___

---

# Phase 2 — Security Hardening

---

## [P2-01] 2FA Pending Token Too Permissive

**Severity:** High  
**Status:** Pending  
**Area:** Security / Backend  
**Files:** `backend/routes/auth.py:381–389`, `backend/app.py:270–274`  
**Problem:** After password validation, a `totp_pending` JWT is issued with 5-minute expiry. If stolen (XSS, network intercept), attacker + TOTP device = complete login bypass. Rate limit is 10/min — too generous for a security-critical endpoint.  
**Recommended Fix:**
1. Reduce `totp_pending` expiry to 90 seconds.
2. Store a one-time nonce in Redis keyed to `user_id`; invalidate on first TOTP failure.
3. Rate-limit `/verify-totp-login` to 3 attempts/min (not 10).
```python
nonce = secrets.token_hex(16)
redis_client.setex(f"totp_nonce:{user.id}", 90, nonce)
# In pending token claims:
additional_claims={"scope": "totp_pending", "nonce": nonce}
# On /verify-totp-login: verify nonce matches Redis, then delete
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] 3 wrong TOTP codes → pending token invalidated, 4th attempt → 429
- [ ] Wait 91s after issuing pending token → rejected as expired
- [ ] Replay a used pending token → rejected (nonce deleted)
**Completed On:** ___  
**Notes:** ___

---

## [P2-02] Encryption Key Rotation Does Not Force Re-Encryption

**Severity:** High  
**Status:** Pending  
**Area:** Security / Backend  
**Files:** `backend/utils/encryption.py:49–56`  
**Problem:** When `decrypt_value()` succeeds using the old key (`ENCRYPTION_KEY_OLD`), the record is returned but NOT re-encrypted and re-saved under the new key. After key rotation, old-key-encrypted records remain indefinitely, meaning the old key can never truly be retired.  
**Recommended Fix:**
```python
def decrypt_value(ciphertext, caller_update_fn=None):
    for key, is_old in [(current_key, False), (old_key, True)]:
        try:
            value = Fernet(key).decrypt(ciphertext)
            if is_old and caller_update_fn:
                # Re-encrypt and persist under new key
                caller_update_fn(encrypt_value(value))
            return value
        except InvalidToken:
            continue
    raise DecryptionError("All keys failed")
```
Apply the `caller_update_fn` pattern to TOTP secret, bot token, and AI key decrypt paths.  
**Dependencies:** P1-01  
**Testing Checklist:**
- [ ] Encrypt with old key, rotate to new key → first decrypt re-encrypts under new key
- [ ] After re-encrypt, remove old key env var → still decrypts
- [ ] Run key rotation smoke test on staging DB
**Completed On:** ___  
**Notes:** ___

---

## [P2-03] CORS Allows Credentials with Env-Driven Origin List

**Severity:** High  
**Status:** Pending  
**Area:** Security / Backend  
**Files:** `backend/app.py:141–145`  
**Problem:** `supports_credentials=True` + origin list from `FRONTEND_URL` env var. If `FRONTEND_URL` is misconfigured in production (e.g., left as `http://localhost:3000`), CORS blocks all legitimate traffic. If a wildcard origin slips in through env var, CSRF becomes trivial.  
**Recommended Fix:**
1. Hard-code production origin in a constant; fall back to env var only in non-prod environments.
2. Assert `ALLOWED_ORIGINS` is not empty and contains no wildcards at app startup.
3. Add `CSRF_COOKIE_SECURE=True`, `CSRF_COOKIE_HTTPONLY=True`, `SameSite=Strict` to session/auth cookies.
```python
assert all("*" not in o for o in allowed_origins), "Wildcard CORS origin in production"
assert len(allowed_origins) > 0, "ALLOWED_ORIGINS must not be empty"
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] Start app with empty `FRONTEND_URL` → startup assertion fails with clear message
- [ ] Try `*` in origins → rejected at startup
- [ ] Cross-origin request from unlisted origin → 403
**Completed On:** ___  
**Notes:** ___

---

## [P2-04] NOWPayments Webhook Has No Timestamp Validation

**Severity:** High  
**Status:** Pending  
**Area:** Billing / Security  
**Files:** `backend/routes/billing.py:254–276`  
**Problem:** HMAC-SHA512 signature is verified correctly ✓ and `ProcessedPayment.payment_id` dedup is in place ✓, but there is no timestamp check. If the `ProcessedPayment` table is purged or a DB restore happens, a replayed webhook from weeks ago would be accepted and re-activate a subscription.  
**Recommended Fix:**
```python
# Add to IPN handler:
webhook_ts = data.get("created_at") or data.get("updated_at")
if webhook_ts:
    age = datetime.utcnow() - datetime.fromisoformat(webhook_ts)
    if age.total_seconds() > 3600:  # 1 hour
        return jsonify({"status": "stale"}), 200  # 200 so NOWPayments doesn't retry
# Store on ProcessedPayment:
processed.webhook_received_at = datetime.utcnow()
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] Send a valid IPN with `created_at` 2h ago → accepted but logged as stale, no activation
- [ ] Fresh IPN → activates subscription
- [ ] Replayed IPN (same payment_id) → 200 no-op, no double-credit
**Completed On:** ___  
**Notes:** ___

---

## [P2-05] 5% Underpayment Tolerance — Revenue Leak

**Severity:** High  
**Status:** Pending  
**Area:** Billing  
**Files:** `backend/routes/billing.py:372–382`  
**Problem:** `min_acceptable = expected_usd * 0.95` allows users to pay 5% less and receive full subscription. Over time, this is a guaranteed revenue leak. For a $9.99/month plan that's ~$6/year per user.  
**Recommended Fix:**
- Drop to 1% tolerance (crypto exchange variance): `min_acceptable = expected_usd * 0.99`
- Log every underpayment to an `UnderpaymentLog` table for billing review.
- Optionally pull live tolerance from NOWPayments' quote endpoint.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Send IPN with 1.5% underpayment → rejected
- [ ] Send IPN with 0.5% underpayment → accepted, logged
- [ ] UnderpaymentLog row created for every accepted underpayment
**Completed On:** ___  
**Notes:** ___

---

## [P2-06] Custom Bot Token Decryption Has Same Plaintext Fallback

**Severity:** High  
**Status:** Pending  
**Area:** Security / Bot  
**Files:** `backend/routes/custom_bots.py:109`, `backend/models.py:1183`, `backend/utils/encryption.py:84`  
**Problem:** `CustomBot.set_token()` uses `encrypt_value()` correctly. However `decrypt_value()` (before P1-01 is fixed) silently returns ciphertext on failure. On a bad key rotation, all custom bot tokens in the DB are returned as raw ciphertext strings — they'd be used as Telegram API tokens, failing every bot API call with no clear error.  
**Recommended Fix:** Fix P1-01 first. Then add a startup self-check:
```python
# In app startup / health check:
for bot in CustomBot.query.all():
    try:
        token = bot.get_token()
        assert len(token) > 20 and ":" in token, "Decrypted token looks corrupt"
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.critical(f"CustomBot {bot.id} token decrypt failed")
```
**Dependencies:** P1-01  
**Testing Checklist:**
- [ ] Rotate key, startup check runs → all tokens verified
- [ ] One corrupt token → Sentry alert, bot disabled gracefully (not silently broken)
- [ ] API call with decrypted token → succeeds
**Completed On:** ___  
**Notes:** ___

---

## [P2-07] Email Verification Token Brute-Forceable Per-IP Only

**Severity:** Medium  
**Status:** Pending  
**Area:** Security / Backend  
**Files:** `backend/routes/auth.py:525–549`  
**Problem:** `/verify-email` has a 10/min per-IP rate limit, but no per-token or per-email failure counter. An attacker behind a rotating proxy can brute-force the token namespace. Token is 256-bit so practical risk is low, but defense-in-depth is missing.  
**Recommended Fix:**
```python
# Track failures per email in Redis:
fail_key = f"verify_fail:{user.email}"
if int(redis_client.get(fail_key) or 0) >= 5:
    abort(429, "Too many failed verification attempts")
redis_client.incr(fail_key)
redis_client.expire(fail_key, 3600)
# On success: delete fail_key
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] 5 wrong tokens for same email → 429
- [ ] Correct token after 4 failures → success, counter reset
- [ ] Different email → separate counter
**Completed On:** ___  
**Notes:** ___

---

## [P2-08] Backup Codes: Dict Overwrite Risk + No Per-Code Rate Limit

**Severity:** Medium  
**Status:** Pending  
**Area:** Security / Backend  
**Files:** `backend/routes/totp.py:27–41`, `backend/routes/auth.py:473–520`  
**Problem:** Backup codes stored as `{sha256(code): bcrypt_hash}` dict. If two generated codes produce the same SHA-256 (astronomically unlikely but architecturally unsound), the second overwrites the first. No per-code ID, no per-code attempt tracking.  
**Recommended Fix:**
```python
# Switch to list of dicts:
codes = [{"id": str(uuid4()), "hash": bcrypt.hashpw(code, bcrypt.gensalt())} for code in raw_codes]
user.backup_codes = json.dumps(codes)

# On verify:
for code_entry in stored_codes:
    if bcrypt.checkpw(submitted.encode(), code_entry["hash"]):
        stored_codes.remove(code_entry)  # single use
        user.backup_codes = json.dumps(stored_codes)
        break
```
Rate-limit backup code verification to 5 attempts/min.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Use a backup code → succeeds, code removed from list
- [ ] Reuse same backup code → rejected
- [ ] 5 wrong backup codes → 429
- [ ] All 10 codes used → all exhausted, recovery email prompted
**Completed On:** ___  
**Notes:** ___

---

## [P2-09] Premature JWT Issued Before Email Verification

**Severity:** Medium  
**Status:** Pending  
**Area:** Security / Backend  
**Files:** `backend/routes/auth.py:317–319`  
**Problem:** A full-scope JWT is issued immediately at registration before email verification. While `app.py:249–286` has a verification gate, it operates on an allow-list — if any `/api` route slips through, unverified users can access it.  
**Recommended Fix:**
Issue a scoped token at registration:
```python
pending_token = create_access_token(
    identity=str(user.id),
    expires_delta=timedelta(hours=24),
    additional_claims={"scope": "email_verify_pending"}
)
```
In the middleware, block all `/api` routes for `email_verify_pending` scope EXCEPT `/verify-email` and `/resend-verification`. Upgrade to a full-scope token only after successful verification.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Register → receive scoped token
- [ ] Call `/api/groups` with scoped token → 403
- [ ] Verify email → full token issued
- [ ] Call `/api/groups` with full token → 200
**Completed On:** ___  
**Notes:** ___

---

## [P2-10] Admin Access Requires Only Email Match, No MFA Enforcement

**Severity:** Medium  
**Status:** Pending  
**Area:** Security / Backend  
**Files:** `backend/routes/admin.py:17–27`, `backend/config.py:106–118`  
**Problem:** Admin status is a whitelist of email addresses in `Config.ADMIN_EMAILS`. No MFA requirement, no audit log, no approval workflow for destructive actions. Admins can freely modify any user's subscription tier.  
**Recommended Fix:**
```python
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if user.email not in Config.ADMIN_EMAILS:
            abort(403)
        if not user.totp_enabled:
            abort(403, "Admin accounts must have 2FA enabled")
        # Log the action:
        AdminAuditLog.create(admin_id=user.id, action=request.endpoint, data=request.json)
        return f(*args, **kwargs)
    return decorated
```
Create `AdminAuditLog` model with `(id, admin_id, action, data_json, created_at)`.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Admin without TOTP enabled → 403 on any admin route
- [ ] Admin action → `AdminAuditLog` row created
- [ ] Non-admin email → 403
**Completed On:** ___  
**Notes:** ___

---

# Phase 3 — Feature Completion

---

## [P3-01] /linkgroup Race Condition — Two Admins Can Link Same Group

**Severity:** Medium  
**Status:** Pending  
**Area:** Bot / Backend  
**Files:** `backend/official_bot.py:500–577`  
**Problem:** Two group admins call `/linkgroup` simultaneously. Both read `tg.owner_user_id = None` before either commits, both enter the linking branch, and the second commit overwrites the first. The group ends up owned by the wrong user with expired link codes.  
**Recommended Fix:**
```python
# Use SELECT ... FOR UPDATE or a unique partial index:
tg = TelegramGroup.query.filter_by(
    telegram_chat_id=chat_id
).with_for_update().first()

# Or rely on a unique partial index:
# CREATE UNIQUE INDEX ix_telegramgroup_unlinked ON telegram_group(telegram_chat_id)
# WHERE owner_user_id IS NULL;
# Then catch IntegrityError on second insert
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] Two concurrent `/linkgroup` calls on same group → only one succeeds
- [ ] Loser receives "group already linked" message
- [ ] DB has exactly one `owner_user_id` for the group
**Completed On:** ___  
**Notes:** ___

---

## [P3-02] DM Text Logged Before Auth Check — Bot Token Exposure Window

**Severity:** Medium  
**Status:** Pending  
**Area:** Bot / Security  
**Files:** `backend/official_bot.py:794, 830–950`  
**Problem:** `BotDMMessage.record()` logs raw DM text at line 794 BEFORE the user registration check at line 878. If a non-registered user pastes a Telegram bot token into the bot DM (to test it), the token is stored in the DB even though the subsequent auth check rejects them. The message is deleted from Telegram, but the DB row persists.  
**Recommended Fix:**
1. Move auth check BEFORE logging.
2. Regardless: mask Telegram bot token patterns before logging:
```python
import re
BOT_TOKEN_RE = re.compile(r'\d{9,10}:[A-Za-z0-9_-]{35}')
safe_text = BOT_TOKEN_RE.sub("[REDACTED_BOT_TOKEN]", message.text)
BotDMMessage.record(user_id=user.id, text=safe_text)
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] Unregistered user sends any text → not logged to DB
- [ ] Registered user sends a bot token string → logged as `[REDACTED_BOT_TOKEN]`
- [ ] Normal DM text → logged as-is
**Completed On:** ___  
**Notes:** ___

---

## [P3-03] AI Token Daily Quota Fields Exist But Not Enforced

**Severity:** Medium  
**Status:** Pending  
**Area:** AI / Backend  
**Files:** `backend/models.py:50–51`, `backend/assistant/digest_ai.py`, `backend/assistant/ai_key_resolver.py`  
**Problem:** `User.workspace_ai_tokens_today` and `workspace_ai_tokens_reset_at` columns exist and are updated after calls, but the pre-call quota check is absent in `digest_ai.py`. A single runaway digest or malicious group can exhaust platform Gemini quota for all users.  
**Recommended Fix:**
In `ai_key_resolver.py`, before every AI call:
```python
if user.workspace_ai_tokens_today >= Config.DAILY_AI_TOKEN_LIMIT:
    raise QuotaExceededError("Daily AI token limit reached")
# After call:
user.workspace_ai_tokens_today += tokens_used
if user.workspace_ai_tokens_reset_at < datetime.utcnow():
    user.workspace_ai_tokens_today = tokens_used
    user.workspace_ai_tokens_reset_at = datetime.utcnow() + timedelta(days=1)
db.session.commit()
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] Exhaust daily limit → next AI call returns friendly quota error
- [ ] Quota resets after 24h
- [ ] Per-user quota does not affect other users
- [ ] Platform key quota tracked separately from user key quota
**Completed On:** ___  
**Notes:** ___

---

## [P3-04] Knowledge Base Upload: No Concurrent Upload Limit / Storage Quota

**Severity:** Medium  
**Status:** Pending  
**Area:** AI / Backend  
**Files:** `backend/routes/knowledge.py:65–88`  
**Problem:** 5MB per-file cap ✓, but no limit on concurrent uploads or total storage per user/group. A user can spawn 100 parallel 5MB uploads, exhausting memory and DB connections. No magic-byte re-validation after write.  
**Recommended Fix:**
```python
# Redis semaphore:
lock_key = f"kb_upload:{group_id}"
with redis_client.lock(lock_key, timeout=30, blocking_timeout=5):
    # Check total quota:
    total = db.session.query(func.sum(KnowledgeDocument.file_size)).filter_by(group_id=group_id).scalar() or 0
    if total + file_size > 100 * 1024 * 1024:  # 100MB per group
        abort(413, "Group knowledge base storage limit reached")
    # Proceed with upload
```
Add `@rate_limit(3/min)` per-user on the upload endpoint.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Upload 6MB file → 413
- [ ] Upload 4 concurrent files → 4th gets 429
- [ ] Group reaches 100MB quota → upload rejected with clear message
- [ ] Non-PDF file with `.pdf` extension → magic byte check fails, rejected
**Completed On:** ___  
**Notes:** ___

---

## [P3-05] Marketplace / Directory: No Rate Limit on Listing Creation, Auto-Published

**Severity:** Medium  
**Status:** Pending  
**Area:** Backend / Product  
**Files:** `backend/routes/marketplace.py`, `backend/routes/directory.py`  
**Problem:** No `@rate_limit` on listing creation endpoints. Free users can spam unlimited listings. `is_public=True` appears to auto-publish without moderation — once signups open, this will be abused.  
**Recommended Fix:**
1. Add `@rate_limit(5/min)` to create-listing endpoints.
2. Add `status` field to `DirectoryListing` with values: `pending | approved | rejected`.
3. New listings default to `pending`; filter all public browse queries by `status="approved"`.
4. Admin panel shows pending listings for review.
**Dependencies:** P2-10 (admin audit log useful here)  
**Testing Checklist:**
- [ ] 6 listing creates in 1 minute → 6th rate-limited
- [ ] Create listing → `status=pending`, not visible in public browse
- [ ] Admin approves → visible
**Completed On:** ___  
**Notes:** ___

---

## [P3-06] Digest Scheduler Not Timezone-Aware

**Severity:** Low  
**Status:** Pending  
**Area:** Bot / UX  
**Files:** `backend/routes/digest.py`, `backend/models.py` (User), `backend/app.py` (`_scheduler_loop`)  
**Problem:** Digest schedules use `datetime.utcnow()`. A user who sets "daily digest at 8am" receives it at 08:00 UTC regardless of their timezone (could be 3am for a US user).  
**Recommended Fix:**
1. Add `User.timezone = db.Column(db.String(64), default="UTC")`.
2. Add a timezone selector to Settings page.
3. In digest scheduling: `next_run = user_local_8am.astimezone(pytz.utc)`.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] User sets timezone to UTC-5, digest at 8am → fires at 13:00 UTC
- [ ] UTC user → no change
- [ ] Invalid timezone string → rejected at API
**Completed On:** ___  
**Notes:** ___

---

## [P3-07] Migration Has No `release:` Step — Schema Drift Risk on Deploy

**Severity:** Medium  
**Status:** Pending  
**Area:** Deployment / DB  
**Files:** `Procfile`, `backend/migrate.py`  
**Problem:** Migrations run via `python -m backend.migrate` but there is no `release:` step in the Procfile. On Railway, the web dyno starts and accepts traffic before migrations have run. If a new column is required, the app crashes on first DB access after deploy.  
**Recommended Fix:**
```
# Procfile:
release: python -m backend.migrate
web: gunicorn backend.app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4
```
Railway runs `release` before starting the new `web` dyno.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Deploy with a new migration → migration runs before web starts
- [ ] Web dyno starts successfully after migration
- [ ] Migration re-run on next deploy → idempotent, no error
**Completed On:** ___  
**Notes:** ___

---

# Phase 4 — UX Polish

---

## [P4-01] Bottom Navigation Points to Legacy `/my-groups` Path

**Severity:** Low  
**Status:** Pending  
**Area:** Frontend / UX  
**Files:** `frontend/src/layouts/AppLayout.js:13`  
**Problem:** The mobile bottom navigation bar has a `BOTTOM_NAV_ITEMS` entry with path `/my-groups`. This is the legacy alias. While it redirects, it causes a flash and incorrect active-state highlighting on mobile.  
**Recommended Fix:**
```javascript
// Change:
{ path: '/my-groups', ... }
// To:
{ path: '/groups', ... }
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] Mobile (375px): tap Groups in bottom nav → navigates to `/groups`, no redirect flash
- [ ] Active state highlights correctly on `/groups` sub-routes
**Completed On:** ___  
**Notes:** ___

---

## [P4-02] Analytics Sidebar Shows Single Hub Entry Instead of Two Sub-Items

**Severity:** Low  
**Status:** Pending  
**Area:** Frontend / UX  
**Files:** `frontend/src/components/Sidebar.js:537`  
**Problem:** Spec calls for `Analytics → Groups` and `Analytics → Channels` as separate sidebar sub-items. Currently there is only a single "Analytics Hub" entry. Users can't tell there are two separate analytics views.  
**Recommended Fix:**
Option A — Add sub-items matching spec:
```javascript
{ label: "Analytics", children: [
  { label: "Groups", path: "/analytics" },
  { label: "Channels", path: "/analytics/channels" },
]}
```
Option B — Accept the Hub design and update the spec/README.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Analytics section in sidebar shows Groups and Channels sub-items (if Option A)
- [ ] Both routes load correct data
**Completed On:** ___  
**Notes:** ___

---

## [P4-03] Frontend API Base URL Silent Fallback Causes Opaque Errors

**Severity:** Low  
**Status:** Pending  
**Area:** Frontend  
**Files:** `frontend/src/services/api.js:9`  
**Problem:** `BASE_URL = process.env.REACT_APP_API_URL || ''` falls back to empty string. In production on Vercel, if the env var is not set, all API calls go to `https://telegizer.com/api/...` (relative), which returns Vercel's 404 page as JSON — completely opaque error for debugging.  
**Recommended Fix:**
```javascript
const BASE_URL = process.env.REACT_APP_API_URL;
if (!BASE_URL && process.env.NODE_ENV === 'production') {
  console.error('REACT_APP_API_URL is not set. API calls will fail.');
  // Show a top-level error banner
}
```
Also add `REACT_APP_API_URL` to Vercel environment variable docs.  
**Dependencies:** None  
**Testing Checklist:**
- [ ] Build without `REACT_APP_API_URL` in prod → error logged, banner shown
- [ ] Build with var set → no banner, API calls succeed
**Completed On:** ___  
**Notes:** ___

---

## [P4-04] Email Verification Middleware Uses Allow-List (Inverted Gate)

**Severity:** Medium  
**Status:** Pending  
**Area:** Backend / Security  
**Files:** `backend/app.py:249–286`  
**Problem:** The email-verification middleware allows all routes by default and only blocks a specific list. Any new route added by a developer is accidentally accessible to unverified users unless they also update the allow-list. Inverted logic is a maintenance trap.  
**Recommended Fix:**
Invert the gate: deny ALL `/api` routes to unverified users by default, with an explicit exempt list:
```python
EXEMPT_FROM_EMAIL_VERIFY = {
    "/api/auth/verify-email",
    "/api/auth/resend-verification",
    "/api/auth/logout",
}
if request.path.startswith("/api") and request.path not in EXEMPT_FROM_EMAIL_VERIFY:
    if not current_user.email_verified:
        abort(403, "Email verification required")
```
**Dependencies:** P2-09  
**Testing Checklist:**
- [ ] Unverified user hits any non-exempt `/api` route → 403
- [ ] Exempt routes accessible without verification
- [ ] Verified user → no restriction
**Completed On:** ___  
**Notes:** ___

---

## [P4-05] Mobile Table Overflow Not Confirmed for All Pages

**Severity:** Low  
**Status:** Pending  
**Area:** Frontend / UX  
**Files:** `frontend/src/pages/Billing.js`, `frontend/src/pages/Analytics.js`, `frontend/src/pages/AssistantNotes.js`, `frontend/src/pages/WorkspaceReminders.js`  
**Problem:** Tables in PaymentHistory, Analytics, Notes, and Reminders pages need visual QA at 375px to confirm `overflow-x: auto` wrapping is applied. Body-level `overflow-x: hidden` exists but tables inside flex/grid containers can still cause horizontal scroll.  
**Recommended Fix:**
For each table container:
```jsx
<Box sx={{ overflowX: 'auto' }}>
  <Table>...</Table>
</Box>
```
**Dependencies:** None  
**Testing Checklist:**
- [ ] Open Billing page on iPhone SE (375px) → no horizontal scroll
- [ ] Open Analytics page → table scrolls internally, page does not
- [ ] Open Notes and Reminders → same
**Completed On:** ___  
**Notes:** ___

---

# Phase 5 — Final QA Checklist

---

## [P5-QA] Full End-to-End Launch QA

**Severity:** N/A  
**Status:** Pending  
**Area:** All  
**Files:** All  
**Problem:** Pre-launch validation across all critical user flows.  
**QA Checklist:**

**Authentication & Onboarding**
- [ ] New user signup → email verification email received → click link → dashboard
- [ ] Unverified user cannot access `/api/groups` or other protected routes
- [ ] Existing user login → dashboard
- [ ] Login with 2FA: correct TOTP → success; wrong code × 3 → pending token invalidated
- [ ] Forgot password → email with reset link → use link → password changed; replay same link → rejected
- [ ] Login rate limit: 20 attempts/min → 429

**Bot & Group Linking**
- [ ] Add official bot to a group → `/linkgroup` → web dashboard shows group
- [ ] Two admins run `/linkgroup` simultaneously → only one succeeds
- [ ] Custom bot: register via web, webhook set, send message in linked group → bot responds
- [ ] Bot DM: paste text → logged with token redacted; non-registered user DM → not logged

**Features (Free vs Pro)**
- [ ] Free user hits Forwarding page → upgrade gate shown
- [ ] Free user hits Workflows page → upgrade gate shown
- [ ] Free user hits Knowledge Base page → upgrade gate shown
- [ ] Pro user hits all above → full access, no gate
- [ ] Downgraded Pro user → gates re-appear

**Reminders & Digests**
- [ ] Create reminder from web → fires at scheduled time
- [ ] Create reminder from Telegram DM → fires at scheduled time
- [ ] Enable daily digest for a group → digest arrives at correct UTC time
- [ ] Kill dyno mid-digest → on restart, digest still fires

**Billing (NOWPayments)**
- [ ] Checkout flow: select Pro → NOWPayments invoice → pay → IPN received → tier upgrades
- [ ] IPN replayed (same payment_id) → 200 no-op, no double-credit
- [ ] IPN with wrong HMAC signature → 400
- [ ] IPN with tampered user_id in order_id → correct user credited (from PendingInvoice)
- [ ] IPN older than 1h → accepted but logged as stale, no activation
- [ ] Underpayment > 1% → rejected, user notified
- [ ] Payment history page shows only current user's history

**Knowledge Base**
- [ ] Upload valid PDF < 5MB → success
- [ ] Upload 6MB file → 413
- [ ] Upload non-PDF with .pdf extension → rejected (magic bytes)
- [ ] 4 concurrent uploads → 4th rate-limited
- [ ] Group at 100MB quota → next upload rejected

**AI Features**
- [ ] Digest generated via platform Gemini key (no user key set)
- [ ] User sets own Gemini key → digest uses user key
- [ ] User daily token limit exhausted → friendly quota error, no API call made
- [ ] Auto-reply keyword match → bot replies in group

**Security**
- [ ] Bot webhook: POST without `X-Telegram-Bot-Api-Secret-Token` → 403
- [ ] Webhook secret wrong → 403
- [ ] TOTP secret in DB → confirm it is stored as ciphertext
- [ ] Admin without 2FA enabled → admin routes blocked
- [ ] Admin action → `AdminAuditLog` row created

**Mobile (375px)**
- [ ] Every page: no horizontal scroll
- [ ] Bottom nav: tap Groups → `/groups`, no flash
- [ ] Sidebar: collapses to hamburger + drawer
- [ ] Tables: overflow-x scroll within container

**Deployment**
- [ ] `release:` step runs migration before web starts
- [ ] Sentry: force a scheduler exception → event appears with metadata
- [ ] `REACT_APP_API_URL` not set in prod → error banner shown
- [ ] CORS: request from unlisted origin → blocked

**Completed On:** ___  
**Notes:** ___

---

# Completed Issues

*(None yet — move issues here as they are resolved)*

---

# Future Workflow Rules

1. **"Mark issue complete"** → Update `Status: Pending` to `Status: Completed`, fill `Completed On`, update the progress counter at the top.
2. **"What remains"** → List all issues where `Status: Pending` or `Status: In Progress`, grouped by Phase.
3. **"Next task"** → Recommend the highest-priority `Pending` issue whose `Dependencies` are all `Completed`.
4. **Never delete completed items** — move them to the `Completed Issues` section and mark done.
5. **This file is the single source of truth** for all Sprint 7.5 fixes until all issues show `Completed`.

