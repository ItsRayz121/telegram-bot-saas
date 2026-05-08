# TELEGIZER — DEVELOPER IMPLEMENTATION PLAN
### Gap Closure Checklist · Version 1.1 · May 2026

> **Purpose:** This document is a complete handover to the development team.
> It lists every gap between the spec and the real application — exactly what is missing, exactly where to build it, and exactly how it must behave.
> Every item has a checkbox. The team works top to bottom. Nothing is shipped until the checkbox is ticked.

> **Architecture reminder:** Telegizer is a unified 3-component system:
> - **Bot** — `@TelegizerBot` (official) + Custom Bots (user-supplied tokens)
> - **Web** — React SPA on Vercel (`frontend/`)
> - **TMA** — Telegram Mini App (embedded in Telegram, same React build)
>
> Every feature must work uniformly across all three. Config lives in DB. Bot reads DB. Web writes DB. TMA reads DB.

---

## HOW TO USE THIS DOCUMENT

- Work through phases in order (Phase 1 → 2 → 3 → 4)
- Each item tells you: **what file to touch**, **what to build**, **what the correct behavior is**
- Check the box only when the feature is fully working end-to-end (bot + API + frontend all consistent)
- If a backend item has a matching frontend requirement, it is listed together under the same item

---

# PHASE 1 — CRITICAL (Build First, Nothing Else Matters Until These Are Done)

---

## BLOCK 1-A: SUBSCRIPTION LIFECYCLE (Revenue Safety)

These items directly affect whether users who pay get the right service, and whether expired users are downgraded.

---

### [ ] 1-A-01 — Add Subscription Expiry Fields to User Model

**File:** `backend/models.py` → `User` class

**Add these columns:**
```python
subscription_expires_at  = db.Column(db.DateTime(timezone=True), nullable=True)
subscription_grace_until = db.Column(db.DateTime(timezone=True), nullable=True)
subscription_interval    = db.Column(db.String(20), nullable=True)  # "monthly" | "yearly"
```

**Migrate:** Add to `backend/migrate.py`:
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_grace_until TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_interval VARCHAR(20);
```

**Set on payment:** In `backend/routes/billing.py`, when a NOWPayments IPN arrives with `payment_status = "finished"`:
- `subscription_expires_at = now() + 30 days` (monthly) or `now() + 365 days` (yearly)
- `subscription_grace_until = subscription_expires_at + 7 days`
- `subscription_interval = "monthly"` or `"yearly"` based on plan selected

---

### [ ] 1-A-02 — Add SubscriptionRenewal Model

**File:** `backend/models.py`

```python
class SubscriptionRenewal(db.Model):
    __tablename__ = "subscription_renewals"
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    plan             = db.Column(db.String(50))           # "pro" | "enterprise"
    interval         = db.Column(db.String(20))           # "monthly" | "yearly"
    amount_usd       = db.Column(db.Numeric(10,2))
    payment_id       = db.Column(db.String(200))          # NOWPayments payment_id
    renewed_at       = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at       = db.Column(db.DateTime)
```

**Migrate:** Add `CREATE TABLE IF NOT EXISTS subscription_renewals (...)` to `migrate.py`

**Write:** On every successful billing webhook, insert a `SubscriptionRenewal` record.

---

### [ ] 1-A-03 — Build Subscription Expiry Downgrade Cron

**File:** `backend/scheduler.py`

Add a daily job at 01:00 UTC:
```python
def downgrade_expired_subscriptions():
    """Run daily at 01:00 UTC. Downgrade users past grace period."""
    now = datetime.utcnow()
    expired = User.query.filter(
        User.subscription_tier != "free",
        User.subscription_grace_until != None,
        User.subscription_grace_until < now
    ).all()
    for user in expired:
        user.subscription_tier = "free"
        user.subscription_expires_at = None
        user.subscription_grace_until = None
        db.session.add(UserNotification(
            user_id=user.id,
            type="subscription_expired",
            title="Subscription Expired",
            body="Your Pro subscription has expired. Upgrade to restore access.",
            action_url="/billing"
        ))
    db.session.commit()
    logger.info(f"Downgraded {len(expired)} expired subscriptions")
```

---

### [ ] 1-A-04 — Build Renewal Reminder Email Jobs

**File:** `backend/scheduler.py`

Add three daily jobs:
```python
# Run daily at 09:00 UTC
def send_renewal_reminders():
    now = datetime.utcnow().date()
    for days_before in [7, 3, 1]:
        target_date = now + timedelta(days=days_before)
        users = User.query.filter(
            User.subscription_tier != "free",
            db.func.date(User.subscription_expires_at) == target_date
        ).all()
        for user in users:
            send_email(
                to=user.email,
                subject=f"Your Telegizer subscription expires in {days_before} day(s)",
                template="renewal_reminder",
                context={
                    "days_left": days_before,
                    "plan": user.subscription_tier,
                    "expires_at": user.subscription_expires_at,
                    "renew_url": f"{FRONTEND_URL}/billing"
                }
            )
```

**Email template:** Create `renewal_reminder` email template in your email system.

---

## BLOCK 1-B: BOT GROUP LINKING (Core Activation Flow)

These items are the single most important activation funnel. Without them, users cannot connect their groups.

---

### [ ] 1-B-01 — Add TelegramGroupLinkCode Model

**File:** `backend/models.py`

```python
class TelegramGroupLinkCode(db.Model):
    __tablename__ = "telegram_group_link_codes"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    code          = db.Column(db.String(12), unique=True, nullable=False)
                   # Format: TLG-XXXXXXXX (8 uppercase alphanumeric chars after prefix)
    bot_id        = db.Column(db.Integer, db.ForeignKey("bots.id"), nullable=True)
                   # NULL = official bot, set = custom bot
    expires_at    = db.Column(db.DateTime, nullable=False)
                   # 12 minutes from creation
    used          = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
```

**Migrate:** Add `CREATE TABLE IF NOT EXISTS telegram_group_link_codes (...)` to `migrate.py`

---

### [ ] 1-B-02 — Add Link Code Generation Endpoint

**File:** `backend/routes/telegram_groups.py`

```
POST /api/telegram-groups/generate-link-code
Auth: JWT required
Body: { "bot_id": null | int }

Response 200:
{
  "code": "TLG-A3FX9K2B",
  "expires_at": "2026-05-08T14:22:00Z",
  "instructions": "Run /linkgroup TLG-A3FX9K2B in your Telegram group"
}

Logic:
  1. Delete any existing unused codes for this user (max 1 active code per user)
  2. Generate random 8-char alphanumeric suffix
  3. Prefix with "TLG-"
  4. Store with expires_at = now + 12 minutes
  5. Return code + instructions
```

---

### [ ] 1-B-03 — Add `/linkgroup` Handler in Official Bot

**File:** `backend/official_bot.py`

```python
async def linkgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles /linkgroup TLG-XXXXXXXX in a group chat.
    Only works if sender is a group admin.
    """
    chat = update.effective_chat
    user = update.effective_user
    args = context.args

    # 1. Verify this is a group/supergroup (not private chat)
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ This command only works in groups.")
        return

    # 2. Verify sender is admin
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ Only group admins can link this group.")
        return

    # 3. Validate code format
    if not args or not args[0].startswith("TLG-"):
        await update.message.reply_text("❌ Usage: /linkgroup TLG-XXXXXXXX")
        return

    code = args[0].upper()

    # 4. Look up code in DB
    link_code = TelegramGroupLinkCode.query.filter_by(code=code, used=False).first()
    if not link_code:
        await update.message.reply_text("❌ Invalid or expired code. Generate a new one at telegizer.com")
        return

    if link_code.expires_at < datetime.utcnow():
        await update.message.reply_text("❌ This code has expired. Generate a new one at telegizer.com")
        return

    # 5. Check if group already linked to ANY user
    existing = TelegramGroup.query.filter_by(telegram_chat_id=str(chat.id)).first()
    if existing:
        await update.message.reply_text("⚠️ This group is already linked to a Telegizer account.")
        return

    # 6. Get bot permissions
    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    permissions = extract_bot_permissions(bot_member)

    # 7. Create TelegramGroup record
    group = TelegramGroup(
        user_id=link_code.user_id,
        telegram_chat_id=str(chat.id),
        title=chat.title,
        username=chat.username,
        member_count=await context.bot.get_chat_member_count(chat.id),
        is_forum=getattr(chat, "is_forum", False),
        bot_permissions=permissions,
        settings=DEFAULT_GROUP_SETTINGS.copy()
    )
    db.session.add(group)

    # 8. Mark code as used
    link_code.used = True
    db.session.commit()

    # 9. Write BotEvent
    log_bot_event(group.id, "group_linked", { "linked_by": user.id, "code": code })

    # 10. Notify user
    await update.message.reply_text(
        f"✅ *{chat.title}* is now linked to your Telegizer dashboard!\n\n"
        f"🔗 [Open Dashboard](https://telegizer.com/official-groups)\n\n"
        f"Your bot features are now active. Configure them at telegizer.com",
        parse_mode="HTML"
    )
```

**Also add to custom bot handlers (`backend/bot_manager.py`)** — identical logic but uses the `Bot.user_id` owner for linking.

---

### [ ] 1-B-04 — Add Link Status Polling Endpoint

**File:** `backend/routes/telegram_groups.py`

```
GET /api/telegram-groups/link-status?code=TLG-XXXXXXXX
Auth: JWT required

Response (pending):
{ "status": "pending", "expires_at": "..." }

Response (linked):
{ "status": "linked", "group": { "id": 42, "title": "Crypto Alpha", "member_count": 1204 } }

Response (expired):
{ "status": "expired" }
```

**Frontend use:** On the "Link Group" page, after generating a code, poll this endpoint every 3 seconds. On `status: "linked"`, redirect to `/official-groups/{group.id}/settings` with a success toast.

---

### [ ] 1-B-05 — Add Bot Permissions Extractor

**File:** `backend/official_bot.py` (utility function, reuse in custom bots too)

```python
def extract_bot_permissions(bot_member) -> dict:
    """Extract and score bot permissions from a ChatMember object."""
    perms = {
        "can_delete_messages":      getattr(bot_member, "can_delete_messages", False),
        "can_restrict_members":     getattr(bot_member, "can_restrict_members", False),
        "can_ban_users":            getattr(bot_member, "can_restrict_members", False),
        "can_pin_messages":         getattr(bot_member, "can_pin_messages", False),
        "can_invite_users":         getattr(bot_member, "can_invite_users", False),
        "can_change_info":          getattr(bot_member, "can_change_info", False),
        "can_manage_chat":          getattr(bot_member, "can_manage_chat", False),
        "can_send_messages":        True,  # Always true if bot is in group
    }
    score = sum(1 for v in perms.values() if v) / len(perms) * 100
    perms["permission_score"] = int(score)
    if score == 100:
        perms["access_tier"] = "Full Access"
    elif score >= 50:
        perms["access_tier"] = "Partial Access"
    else:
        perms["access_tier"] = "Limited Access"
    return perms
```

**Store on TelegramGroup:** `telegram_group.bot_permissions = extract_bot_permissions(bot_member)`

**Endpoint:**
```
GET /api/official-groups/:id/permissions
Returns: { permissions: {...}, permission_score: 75, access_tier: "Partial Access" }
```

**Frontend:** Show permission badge on the group card and group settings page. Yellow warning if score < 75. Red if < 50 with "Grant More Permissions" CTA.

---

### [ ] 1-B-06 — Add TelegramBotStarted Model

**File:** `backend/models.py`

```python
class TelegramBotStarted(db.Model):
    __tablename__ = "telegram_bot_started"
    id              = db.Column(db.Integer, primary_key=True)
    telegram_user_id= db.Column(db.BigInteger, unique=True, nullable=False)
    telegram_username = db.Column(db.String(100))
    first_name      = db.Column(db.String(100))
    linked_user_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    started_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

**Write:** In official bot's DM `/start` handler — upsert a `TelegramBotStarted` record.

---

## BLOCK 1-C: VERIFICATION SYSTEM COMPLETENESS

---

### [ ] 1-C-01 — Add PendingUnban Model

**File:** `backend/models.py`

```python
class PendingUnban(db.Model):
    __tablename__ = "pending_unbans"
    id              = db.Column(db.Integer, primary_key=True)
    telegram_chat_id= db.Column(db.BigInteger, nullable=False)
    telegram_user_id= db.Column(db.BigInteger, nullable=False)
    unban_at        = db.Column(db.DateTime, nullable=False)  # When the temp ban expires
    retry_count     = db.Column(db.Integer, default=0)
    last_attempt_at = db.Column(db.DateTime)
    success         = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

**Migrate:** Add to `migrate.py`

---

### [ ] 1-C-02 — Write PendingUnban on Verification Timeout

**File:** `backend/bot_features/verification.py`

When a user fails verification (timeout or wrong answer) and is banned:
```python
# After banning the user
pending = PendingUnban(
    telegram_chat_id=chat.id,
    telegram_user_id=user.id,
    unban_at=datetime.utcnow() + timedelta(hours=1)  # 1-hour temp ban
)
db.session.add(pending)
db.session.commit()
```

---

### [ ] 1-C-03 — Add Retry Pending Unbans Scheduler Job

**File:** `backend/scheduler.py`

```python
# Runs every 1 minute
async def retry_pending_unbans():
    now = datetime.utcnow()
    pending = PendingUnban.query.filter(
        PendingUnban.success == False,
        PendingUnban.unban_at <= now,
        PendingUnban.retry_count < 5
    ).all()
    for record in pending:
        try:
            await bot_app.bot.unban_chat_member(
                chat_id=record.telegram_chat_id,
                user_id=record.telegram_user_id,
                only_if_banned=True
            )
            record.success = True
        except Exception as e:
            record.retry_count += 1
            record.last_attempt_at = now
            logger.warning(f"Unban retry {record.retry_count} failed: {e}")
    db.session.commit()
```

---

## BLOCK 1-D: SECURITY HARDENING (Must be done before any public users)

---

### [ ] 1-D-01 — Move JWT from localStorage to httpOnly Cookies

**Files:**
- `backend/routes/auth.py` — change all JWT responses from JSON body to `set_cookie`
- `frontend/src/services/api.js` — remove `localStorage.setItem` calls, remove Bearer token header injection

**Backend change:**
```python
# In login and refresh endpoints, instead of:
return jsonify({"access_token": token})

# Do:
response = jsonify({"message": "ok", "user": user_data})
response.set_cookie(
    "access_token",
    token,
    httponly=True,
    secure=True,           # HTTPS only
    samesite="Strict",
    max_age=86400          # 1 day
)
response.set_cookie(
    "refresh_token",
    refresh_token,
    httponly=True,
    secure=True,
    samesite="Strict",
    path="/api/auth/refresh",   # Scope refresh token to refresh endpoint only
    max_age=2592000             # 30 days
)
return response
```

**Backend JWT loading:**
```python
# In JWT loader, read from cookie instead of Authorization header
@jwt.token_loader
def custom_token_loader(request):
    return request.cookies.get("access_token")
```

**Frontend change:**
```javascript
// Remove all localStorage JWT code from api.js
// Remove request interceptor that adds Authorization header
// Axios already sends cookies automatically with withCredentials: true
axios.defaults.withCredentials = true;
```

**CORS update:** In `backend/app.py`:
```python
CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS)
```

**TMA exception:** The Mini App cannot use cookies in all Telegram clients. TMA continues to use in-memory token (never localStorage). On TMA auth endpoint, return token in response body only and store in React state (not localStorage).

---

### [ ] 1-D-02 — Add CSRF Double-Submit Cookie Protection

**File:** `backend/middleware/csrf.py` (create this file)

```python
import secrets
import hmac
from flask import request, abort, g

def generate_csrf_token():
    return secrets.token_urlsafe(32)

def validate_csrf():
    """Call this in before_request for all state-changing endpoints."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token:
        abort(403, "CSRF token missing")
    if not hmac.compare_digest(cookie_token, header_token):
        abort(403, "CSRF token invalid")
```

**Set CSRF cookie on login** (alongside JWT cookie):
```python
response.set_cookie(
    "csrf_token",
    generate_csrf_token(),
    httponly=False,      # Must be readable by JS to add to header
    secure=True,
    samesite="Strict"
)
```

**Frontend:** In `api.js` request interceptor, add:
```javascript
const csrfToken = document.cookie.match(/csrf_token=([^;]+)/)?.[1];
if (csrfToken) config.headers['X-CSRF-Token'] = csrfToken;
```

---

### [ ] 1-D-03 — Add Security Response Headers

**File:** `frontend/vercel.json` (create if not exists)

```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {
          "key": "Content-Security-Policy",
          "value": "default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; connect-src 'self' https://api.telegizer.com; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; frame-src https://telegram.org;"
        },
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
        { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" }
      ]
    }
  ]
}
```

**Also add to Flask backend** (`backend/app.py`):
```python
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
```

---

### [ ] 1-D-04 — Add Request Size Limits

**File:** `backend/app.py`

```python
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024   # 10MB global limit

# Webhook endpoints: tighter limit
@app.before_request
def limit_webhook_size():
    webhook_paths = ["/api/billing/crypto/webhook", "/api/webhooks/"]
    if any(request.path.startswith(p) for p in webhook_paths):
        if request.content_length and request.content_length > 65536:  # 64KB
            abort(413, "Request too large")
```

---

### [ ] 1-D-05 — Add ToS Acceptance Tracking to User Model

**File:** `backend/models.py` → `User` class

```python
tos_version_accepted = db.Column(db.String(20), nullable=True)  # e.g. "2.0"
tos_accepted_at      = db.Column(db.DateTime, nullable=True)
```

**Migrate:** Add columns to `migrate.py`

**Registration endpoint** (`backend/routes/auth.py`): Accept `tos_accepted: bool` in body. If not true, return 400. Set `tos_version_accepted = "2.0"`, `tos_accepted_at = now()`.

**Frontend** (`frontend/src/pages/Register.js`): Add required checkbox:
```
☐ I agree to the Terms of Service and Privacy Policy *
```
Checkbox must be checked before form submission is allowed.

---

## BLOCK 1-E: BOT IDENTITY & TOKEN VALIDATION

---

### [ ] 1-E-01 — Add Bot Token Validation Endpoint

**File:** `backend/routes/custom_bots.py`

```
POST /api/bots/validate-token
Auth: JWT required
Body: { "token": "1234567890:AAAA..." }

Logic:
  1. Call https://api.telegram.org/bot{token}/getMe
  2. If HTTP error: return { valid: false, error: "Invalid token" }
  3. Hash the token (SHA256) and check no other Bot row has this hash
  4. If duplicate: return { valid: false, error: "This bot is already connected to another account" }
  5. Return { valid: true, username: "@BotName", first_name: "BotName" }

Response 200:
{ "valid": true, "username": "MyBot", "first_name": "My Bot", "bot_id": 123456 }

Response 400:
{ "valid": false, "error": "Invalid token — check it was copied correctly from @BotFather" }
```

---

### [ ] 1-E-02 — Register Bot Identity on Startup

**File:** `backend/bot_manager.py` — in `BotInstance.__init__` or `start()` method

After bot starts successfully, call:
```python
async def _register_bot_identity(bot):
    """Set bot commands, description, and short description."""
    commands = [
        BotCommand("start", "Link this group to your Telegizer dashboard"),
        BotCommand("help",  "Show available commands"),
        BotCommand("rules", "Show group rules"),
        BotCommand("stats", "Show group statistics"),
        BotCommand("leaderboard", "Show XP leaderboard"),
        BotCommand("report", "Report a message (use as reply)"),
    ]
    await bot.set_my_commands(commands)

    # Free tier bots get Telegizer branding
    if bot_record.user.subscription_tier == "free":
        await bot.set_my_description(
            "This group is managed with Telegizer — the all-in-one Telegram community platform. "
            "Visit telegizer.com to set up your own."
        )
        await bot.set_my_short_description("Powered by Telegizer")
    else:
        # Pro/Enterprise: use user-configured description if set
        desc = bot_record.settings.get("bot_description") or "Community Manager Bot"
        await bot.set_my_description(desc)
```

**Same implementation for official bot** in `backend/official_bot.py` on startup.

---

## BLOCK 1-F: FORUM GROUP SUPPORT

---

### [ ] 1-F-01 — Add `send_group_message()` Utility

**File:** `backend/bot_utils.py` (create or add to existing)

```python
async def send_group_message(bot, group, text: str, parse_mode: str = "HTML",
                              reply_markup=None, pin: bool = False) -> Message:
    """
    Sends a message to a group, automatically handling forum topic routing.
    For forum groups: sends to the General topic (thread_id=1) unless group.default_topic_id is set.
    """
    kwargs = {
        "chat_id": group.telegram_chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        kwargs["reply_markup"] = reply_markup

    # Forum group: must specify message_thread_id
    if group.is_forum:
        kwargs["message_thread_id"] = group.settings.get("default_topic_id") or 1

    msg = await bot.send_message(**kwargs)

    if pin:
        try:
            await bot.pin_chat_message(chat_id=group.telegram_chat_id, message_id=msg.message_id)
        except Exception:
            pass  # Pinning permission not available

    return msg
```

**Replace ALL direct `bot.send_message(chat_id=..., text=...)` calls** in bot handlers with `send_group_message()`.

---

### [ ] 1-F-02 — Add Group Topics Endpoint

**File:** `backend/routes/telegram_groups.py`

```
GET /api/official-groups/:id/topics
Auth: JWT required

Logic:
  1. Verify group.is_forum == True
  2. Call Telegram getForumTopics API (if available) or return cached topics
  3. Store in group.settings["topics"] JSONB

Response:
{ "topics": [{ "id": 1, "name": "General" }, { "id": 2, "name": "Announcements" }] }
```

**Frontend:** In Group Settings for forum groups, show a "Default Topic" selector dropdown. Selected topic ID is stored in `group.settings["default_topic_id"]`.

---

### [ ] 1-F-03 — Propagate thread_id Through All Handlers

**Files:** `backend/official_bot.py`, `backend/bot_manager.py`, all `backend/bot_features/*.py`

Every function that calls `bot.send_message`, `bot.send_poll`, `bot.forward_message` for a group context must pass `message_thread_id` if the group is a forum.

**Pattern to apply:**
```python
# Before:
await context.bot.send_message(chat_id=chat.id, text=welcome_text)

# After:
await send_group_message(context.bot, group_record, welcome_text)
```

---

## BLOCK 1-G: AI SYSTEM — PROMPTS & SAFETY

---

### [ ] 1-G-01 — Centralize AI Prompts in `_prompts.py`

**File:** `backend/assistant/handlers/_prompts.py`

Define all prompts as constants:

```python
DIGEST_PROMPT = """You are a community intelligence analyst for a Telegram group.

Group: {group_name}
Period: {period_start} to {period_end}
Messages analyzed: {message_count}
Top contributors: {top_contributors}

Messages sample:
{messages_sample}

Generate a structured digest with:
1. SUMMARY: 2-3 sentence overview of the main themes and activity level
2. KEY_TOPICS: List of 3-5 main topics discussed (bullet points)
3. HIGHLIGHTS: 2-3 notable moments, questions, or discussions
4. SENTIMENT: Overall community mood (positive/neutral/mixed/negative) with brief explanation
5. ACTION_ITEMS: Any open questions or items that need admin attention

Respond ONLY with valid JSON:
{
  "summary": "...",
  "key_topics": ["...", "..."],
  "highlights": ["...", "..."],
  "sentiment": "positive",
  "sentiment_explanation": "...",
  "action_items": ["..."]
}"""

NOTES_EXTRACTION_PROMPT = """Extract structured notes from the following conversation or text.

Text:
{content}

Extract:
- Key facts or decisions mentioned
- Action items or to-dos
- Important names, dates, or numbers
- Questions that were asked

Respond ONLY with valid JSON:
{
  "title": "Short descriptive title (max 60 chars)",
  "body": "Clean note content in markdown format",
  "tags": ["tag1", "tag2"],
  "action_items": ["item1", "item2"]
}"""

REMINDER_EXTRACTION_PROMPT = """Extract a reminder from this natural language request.

User said: "{text}"
Current time: {current_time}
User timezone: {timezone}

Respond ONLY with valid JSON:
{
  "what": "What to remind about (brief description)",
  "when_iso": "ISO 8601 datetime string in UTC",
  "confidence": 0.0-1.0
}
If you cannot determine a clear time, set confidence below 0.7."""

AUTO_REPLY_PROMPT = """You are a helpful community assistant for {group_name}.

Knowledge base context:
{knowledge_context}

Recent conversation:
{recent_messages}

User question: {question}

Rules:
- Only answer based on the knowledge base context provided
- If you don't know, say "I don't have that information — please ask an admin"
- Be concise (max 150 words)
- Never give medical, legal, or financial advice
- Confidence: rate your confidence 0.0-1.0 in your answer

Respond ONLY with valid JSON:
{
  "answer": "...",
  "confidence": 0.0-1.0,
  "source": "knowledge_base | general_knowledge | unknown"
}"""
```

---

### [ ] 1-G-02 — Add Content Safety Check Function

**File:** `backend/assistant/ai_client.py`

```python
UNSAFE_TOPICS = [
    r"(medical|health|diagnos|treatment|medication|dosage|prescri)",
    r"(legal|lawsuit|sue|court|attorney|lawyer)",
    r"(financial advice|invest|buy.*stock|portfolio|trading signal)",
    r"(how to (make|build|create) (a )?bomb|explosive|weapon)",
    r"(suicide|self.harm|kill (myself|yourself))",
]

DISCLAIMER_TOPICS = {
    "medical": "⚠️ This is general information only. Consult a healthcare professional.",
    "legal":   "⚠️ This is general information only. Consult a qualified lawyer.",
    "financial": "⚠️ This is general information only. Not financial advice.",
}

def content_safety_check(text: str) -> tuple[bool, str]:
    """
    Returns (is_safe, modified_text).
    is_safe=False means do not send this message at all.
    modified_text may have a disclaimer appended.
    """
    import re
    text_lower = text.lower()

    # Hard block: never send these
    hard_blocks = [
        r"(how to.*(harm|hurt|attack|kill))",
        r"(bomb|explosive|weapon).*(make|build|create)",
    ]
    for pattern in hard_blocks:
        if re.search(pattern, text_lower):
            return False, ""

    # Soft: add disclaimer for advice topics
    for topic, disclaimer in DISCLAIMER_TOPICS.items():
        if topic in text_lower:
            return True, text + f"\n\n{disclaimer}"

    return True, text
```

---

### [ ] 1-G-03 — Enforce Confidence Threshold on Auto-Replies

**File:** `backend/bot_features/knowledge_base.py` (or wherever auto-reply is triggered)

```python
CONFIDENCE_THRESHOLD = 0.85

async def handle_auto_reply(message, group, bot):
    response_json = await generate_auto_reply(message.text, group)
    if response_json["confidence"] < CONFIDENCE_THRESHOLD:
        return  # Do not reply — confidence too low

    is_safe, safe_text = content_safety_check(response_json["answer"])
    if not is_safe:
        return  # Never send unsafe content

    await send_group_message(bot, group, safe_text)
    log_auto_reply(group.id, message.text, safe_text, response_json["confidence"])
```

---

### [ ] 1-G-04 — Add AI Cost Tracking

**File:** `backend/models.py` → `User` class

```python
ai_cost_usd_today      = db.Column(db.Numeric(10,6), default=0)
ai_cost_reset_at       = db.Column(db.DateTime)
```

**File:** `backend/assistant/ai_client.py`

After every AI API call, calculate cost and increment:
```python
MODEL_COSTS_PER_1K_TOKENS = {
    "gpt-3.5-turbo":  {"input": 0.0005, "output": 0.0015},
    "gpt-4o":         {"input": 0.005,  "output": 0.015},
    "gemini-flash":   {"input": 0.00035, "output": 0.00105},
    "gemini-pro":     {"input": 0.00125, "output": 0.00375},
}

def track_ai_cost(user_id, model, input_tokens, output_tokens):
    costs = MODEL_COSTS_PER_1K_TOKENS.get(model, {"input": 0.001, "output": 0.002})
    cost = (input_tokens / 1000 * costs["input"]) + (output_tokens / 1000 * costs["output"])
    # Atomic update in Redis first, flush to DB in nightly job
    redis_client.incrbyfloat(f"ai_cost:{user_id}:today", cost)
```

**Daily alert job** (`backend/scheduler.py`): If platform-wide daily AI cost exceeds `DAILY_AI_BUDGET_USD` env var, send email alert to ADMIN_EMAILS.

---

## BLOCK 1-H: CARD PAYMENTS — LEMON SQUEEZY (Highest Revenue Impact)

> **Why Phase 1:** Crypto-only payments exclude 70–90% of potential paying users. Every day this is disabled is lost revenue. This is the single highest-impact item in the entire plan.

---

### [ ] 1-H-01 — Enable Lemon Squeezy Card Payment Integration

**File:** `backend/routes/billing.py`

Re-enable the Lemon Squeezy routes that exist in code but are disabled. Ensure each of these works correctly:

1. **Checkout creation:** `POST /api/billing/lemon-squeezy/checkout`
   - Creates a Lemon Squeezy checkout session for the selected plan
   - Returns `{ checkout_url: "https://..." }` — frontend redirects user to this URL

2. **Webhook handler:** `POST /api/billing/lemon-squeezy/webhook`
   - Verify HMAC-SHA256 signature using `LS_WEBHOOK_SECRET` env var:
     ```python
     expected = hmac.new(LS_WEBHOOK_SECRET.encode(), request.data, hashlib.sha256).hexdigest()
     if not hmac.compare_digest(expected, request.headers.get("X-Signature", "")):
         abort(400, "Invalid signature")
     ```
   - On `order_created` event with status `paid`:
     - Set `user.subscription_tier = plan`
     - Set `user.subscription_expires_at = now + 30d` (monthly) or `now + 365d` (yearly)
     - Set `user.subscription_interval = "monthly"` or `"yearly"`
     - Set `user.subscription_grace_until = subscription_expires_at + 7 days`
     - Insert `SubscriptionRenewal` record
     - Insert `PaymentHistory` record
     - Send confirmation email

3. **Required env vars:** `LS_API_KEY`, `LS_STORE_ID`, `LS_WEBHOOK_SECRET`, `LS_PRO_MONTHLY_VARIANT_ID`, `LS_PRO_YEARLY_VARIANT_ID`, `LS_ENTERPRISE_MONTHLY_VARIANT_ID`, `LS_ENTERPRISE_YEARLY_VARIANT_ID`

**File:** `frontend/src/pages/Billing.js`

Show card payment as the **primary** option and crypto as secondary:
```
[💳 Pay with Card]     ← Primary CTA, prominent
[₿ Pay with Crypto]   ← Secondary link, smaller
```

---

## BLOCK 1-I: PAYMENT RECOVERY

---

### [ ] 1-I-01 — Add Payment Recovery Job

**File:** `backend/scheduler.py`

```python
# Runs every 30 minutes
def recover_missed_payments():
    """
    Checks NOWPayments for finished payments that were not processed
    (e.g., due to IPN delivery failure during downtime).
    """
    # Get all PendingInvoices older than 5 minutes that are not marked finished
    stale = PendingInvoice.query.filter(
        PendingInvoice.status.notin_(["finished", "failed"]),
        PendingInvoice.created_at < datetime.utcnow() - timedelta(minutes=5)
    ).all()

    for invoice in stale:
        try:
            resp = requests.get(
                f"https://api.nowpayments.io/v1/payment/{invoice.payment_id}",
                headers={"x-api-key": NOWPAYMENTS_API_KEY},
                timeout=10
            )
            data = resp.json()
            if data.get("payment_status") == "finished":
                # Process it as if IPN just arrived
                process_successful_payment(invoice.user_id, invoice.plan, invoice.amount)
                invoice.status = "finished"
                db.session.commit()
                logger.info(f"Recovered missed payment: invoice {invoice.id}")
        except Exception as e:
            logger.error(f"Payment recovery check failed for invoice {invoice.id}: {e}")
```

---

### [ ] 1-I-02 — Add "Verify Payment" Button + Endpoint

**File:** `backend/routes/billing.py` — add endpoint:

```
POST /api/billing/verify-payment
Auth: JWT required
Body: {} (no body needed — looks up user's most recent PendingInvoice)

Logic:
  1. Find most recent PendingInvoice for current user where status != "finished"
  2. Call NOWPayments GET /v1/payment/{payment_id}
  3. If payment_status == "finished": run process_successful_payment(), return { upgraded: true }
  4. If not finished: return { upgraded: false, status: current_status }

Response 200:
{ "upgraded": true, "plan": "pro" }
{ "upgraded": false, "status": "waiting" }
```

**File:** `frontend/src/pages/Billing.js`

Add a button visible after any pending crypto payment (when `PendingInvoice` record exists):
```
[🔄 Verify Payment Status]
```
On click: call `POST /api/billing/verify-payment`. On `{ upgraded: true }`: show success toast, refresh user subscription state.

---

# PHASE 2 — HIGH PRIORITY (Ship Within 30 Days of Launch)

---

## BLOCK 2-A: PRODUCT ANALYTICS

### [ ] 2-A-01 — Integrate PostHog

**File:** `frontend/src/index.js`

```javascript
import posthog from 'posthog-js';
posthog.init('YOUR_POSTHOG_KEY', {
  api_host: 'https://app.posthog.com',
  loaded: (posthog) => {
    if (process.env.NODE_ENV === 'development') posthog.opt_out_capturing();
  }
});
```

**File:** `frontend/src/services/analytics.js` (create)

```javascript
export const track = (event, properties = {}) => {
  if (window.posthog) window.posthog.capture(event, properties);
};

export const identify = (userId, traits = {}) => {
  if (window.posthog) window.posthog.identify(userId, traits);
};
```

**Events to instrument (add these calls in the relevant components/pages):**

| Event | Where to add | Properties |
|---|---|---|
| `user_signed_up` | Register success | `{ referral_code, plan: "free" }` |
| `email_verified` | Email verify success | `{}` |
| `onboarding_step_completed` | Each checklist step | `{ step: 1-5, step_name }` |
| `bot_token_validated` | After validate-token success | `{ is_custom_bot: true }` |
| `group_linked` | After link-status polling returns "linked" | `{ method: "official\|custom" }` |
| `feature_configured` | Any settings save | `{ feature: "automod\|verification\|welcome\|digest" }` |
| `upgrade_cta_clicked` | Any PlanGate or upgrade button | `{ plan, source: "plan_gate\|billing\|banner" }` |
| `payment_started` | Checkout initiated | `{ plan, interval, method: "crypto\|card" }` |
| `payment_completed` | Billing webhook success | `{ plan, interval, amount_usd }` |
| `ai_feature_used` | Any AI call from frontend | `{ feature: "digest\|auto_reply\|notes\|chat" }` |
| `page_viewed` | React Router on route change | `{ page: pathname }` |

---

## BLOCK 2-B: ONBOARDING CHECKLIST

### [ ] 2-B-01 — Build Onboarding Checklist Component

**File:** `frontend/src/components/OnboardingChecklist.js` (create)

Renders a sticky card on the dashboard until all steps are complete.

**Steps:**
1. ✅ Email verified (auto-complete from user.email_verified)
2. Connect a bot (complete when user has at least 1 bot OR linked an official group)
3. Link a group (complete when user has at least 1 TelegramGroup or Group)
4. Configure moderation OR welcome (complete when any setting saved)
5. Enable an AI feature (complete when digest, auto-reply, or knowledge base enabled)

**Behavior:**
- Show progress: "3/5 steps complete"
- Each step has a CTA deep-link to the relevant page
- Show confetti animation on 5/5 complete
- Persist completion state via `user.onboarding_completed_steps` JSONB field
- `track("onboarding_step_completed", { step, step_name })` on each step completion

**Backend:** Add `onboarding_completed_steps` JSONB to `User` model. Endpoint `PATCH /api/settings/onboarding` to mark steps.

---

## BLOCK 2-C: EMAIL LIFECYCLE CAMPAIGNS

### [ ] 2-C-01 — Build Email Sequence Trigger Jobs

**File:** `backend/scheduler.py`

```python
# Runs daily at 10:00 UTC
def send_lifecycle_emails():
    now = datetime.utcnow()

    # Day 1: No bot connected
    day1_users = User.query.filter(
        User.email_verified == True,
        User.created_at >= now - timedelta(days=2),
        User.created_at < now - timedelta(days=1),
        ~User.bots.any()  # No bots added
    ).all()
    for user in day1_users:
        send_email(user.email, "day1_no_bot", {"name": user.display_name})

    # Day 3: No group linked
    day3_users = User.query.filter(
        User.created_at >= now - timedelta(days=4),
        User.created_at < now - timedelta(days=3),
        ~TelegramGroup.query.filter_by(user_id=User.id).exists()
    ).all()
    for user in day3_users:
        send_email(user.email, "day3_no_group", {"name": user.display_name})

    # Day 7: Weekly insights for active users (have a group linked)
    day7_users = User.query.filter(
        User.created_at >= now - timedelta(days=8),
        User.created_at < now - timedelta(days=7),
        TelegramGroup.query.filter_by(user_id=User.id).exists()
    ).all()
    for user in day7_users:
        # Build a simple summary: group count, member count
        groups = TelegramGroup.query.filter_by(user_id=user.id).all()
        total_members = sum(g.member_count or 0 for g in groups)
        send_email(user.email, "day7_insights", {
            "name": user.display_name,
            "group_count": len(groups),
            "total_members": total_members,
        })

    # Day 14: On free tier — Pro feature showcase
    day14_users = User.query.filter(
        User.subscription_tier == "free",
        User.created_at >= now - timedelta(days=15),
        User.created_at < now - timedelta(days=14),
    ).all()
    for user in day14_users:
        send_email(user.email, "day14_upgrade_showcase", {"name": user.display_name})

    # Day 30: Monthly retention report
    day30_users = User.query.filter(
        User.created_at >= now - timedelta(days=31),
        User.created_at < now - timedelta(days=30),
        TelegramGroup.query.filter_by(user_id=User.id).exists()
    ).all()
    for user in day30_users:
        send_email(user.email, "day30_retention", {"name": user.display_name})
```

**Email templates to create** (in your email system — Resend):
- `day1_no_bot` — "Don't forget to connect your bot"
- `day3_no_group` — "3 minutes to connect your first community"
- `day7_insights` — "Your community's first week: {group_count} groups, {total_members} members"
- `day14_upgrade_showcase` — "See what Pro users do differently"
- `day30_retention` — "Your community this month"
- `renewal_reminder` — "Your subscription expires in X days" (from 1-A-04)
- `trial_expiring` — "Your Pro trial ends in 3 days" (triggered from 2-D-01 scheduler)

---

## BLOCK 2-D: FREE TRIAL SYSTEM

### [ ] 2-D-01 — Implement 14-Day Pro Trial

**File:** `backend/models.py` → `User`

```python
trial_ends_at    = db.Column(db.DateTime, nullable=True)
trial_used       = db.Column(db.Boolean, default=False)
```

**File:** `backend/routes/auth.py` — on successful registration:
```python
user.trial_ends_at = datetime.utcnow() + timedelta(days=14)
user.subscription_tier = "pro"  # Trial counts as pro
user.trial_used = True
```

**File:** `backend/scheduler.py` — daily job at 00:30 UTC:
```python
def expire_trials():
    expired = User.query.filter(
        User.trial_ends_at != None,
        User.trial_ends_at < datetime.utcnow(),
        User.subscription_tier == "pro",
        User.subscription_expires_at == None  # Not a paid user
    ).all()
    for user in expired:
        user.subscription_tier = "free"
        user.trial_ends_at = None
        # Send "trial expired" email
```

**Frontend:** Show a trial countdown banner when `user.trial_ends_at` is set:
```
⏰ Your Pro trial ends in 6 days — Upgrade now to keep all features →
```

---

## BLOCK 2-E: GDPR & LEGAL COMPLIANCE

### [ ] 2-E-01 — Update Privacy Policy for Message Content Storage

**What to do:**

1. Update `frontend/src/pages/Privacy.js` (or the Privacy Policy content) to add an explicit section:

```
DATA COLLECTED BY AI FEATURES

When you enable AI digest or auto-reply features, Telegizer temporarily stores 
message content from your linked Telegram groups for up to 72 hours for the 
purpose of generating AI summaries and responses. This data is:
- Encrypted at rest using AES-128
- Automatically deleted after 72 hours
- Never shared with third parties
- Stored in EU/US servers (Railway infrastructure)

Legal basis: Legitimate interests (providing the contracted AI service).
You can disable message storage by turning off digest/auto-reply features in group settings.
For GDPR data deletion requests, contact: privacy@telegizer.com
```

2. Add a `Data Storage` toggle in group settings (official groups + custom bots):
   - Label: "Store messages for AI features (required for digest & auto-reply)"
   - Default: `false` — opt-in only
   - Stored in `group.settings["ai_message_storage_enabled"]`
   - If `false`: message handler does NOT write to `MessageBuffer`

3. **Enforce 72-hour cleanup** — add to `backend/scheduler.py` daily at 3am UTC:
   ```python
   def cleanup_message_buffer():
       cutoff = datetime.utcnow() - timedelta(hours=72)
       MessageBuffer.query.filter(MessageBuffer.created_at < cutoff).delete()
       db.session.commit()
   ```

---

## BLOCK 2-F: MOBILE & PWA EXPERIENCE

### [ ] 2-F-01 — Add Mobile Navigation Bar

**File:** `frontend/src/components/MobileNav.js` (create)

For screens < 768px, replace the sidebar with a bottom navigation bar:
```
[Dashboard] [Groups] [Assistant] [Analytics] [More]
```

Show in `App.js` conditionally:
```javascript
const isMobile = useMediaQuery(theme.breakpoints.down('md'));
{isMobile ? <MobileNav /> : <Sidebar />}
```

### [ ] 2-F-02 — Fix Table Overflow on Mobile

**All pages with data tables:** Wrap every `<Table>` with:
```javascript
<Box sx={{ overflowX: 'auto', width: '100%' }}>
  <Table>...</Table>
</Box>
```

---

## BLOCK 2-G: TELEGRAM MINI APP

### [ ] 2-G-01 — Implement Telegram.WebApp API in MiniApp.js

**File:** `frontend/src/pages/MiniApp.js`

```javascript
useEffect(() => {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  tg.ready();
  tg.expand();
  tg.setHeaderColor("#0f172a");
  tg.setBackgroundColor("#0f172a");
}, []);
```

### [ ] 2-G-02 — Implement TMA Authentication Backend

**File:** `backend/routes/telegram_webapp.py`

```python
@webapp_bp.route("/auth", methods=["POST"])
def webapp_auth():
    init_data = request.json.get("initData")
    # Validate HMAC-SHA256 signature using TELEGRAM_BOT_TOKEN
    if not validate_init_data(init_data, TELEGRAM_BOT_TOKEN):
        abort(401, "Invalid initData signature")
    user_data = parse_init_data(init_data)
    telegram_user_id = user_data["id"]
    # Find linked Telegizer user
    tg_account = UserTelegramAccount.query.filter_by(
        telegram_user_id=telegram_user_id
    ).first()
    if not tg_account:
        return jsonify({"linked": False, "message": "Link your Telegram account first"})
    user = tg_account.user
    token = create_access_token(identity=user.id)
    return jsonify({"linked": True, "token": token, "user": user.to_dict()})
```

### [ ] 2-G-03 — Add Mini App Entry Point in Bot

**File:** `backend/official_bot.py`

In the `/start` command DM handler, add an inline keyboard button:
```python
keyboard = InlineKeyboardMarkup([[
    InlineKeyboardButton("📊 Open Dashboard", web_app=WebAppInfo(url=f"{FRONTEND_URL}/mini-app"))
]])
await context.bot.send_message(
    chat_id=update.effective_chat.id,
    text="👋 Welcome to Telegizer! Open your community dashboard:",
    reply_markup=keyboard
)
```

---

## BLOCK 2-H: ADMIN PANEL HARDENING

### [ ] 2-H-01 — Admin Step-Up Authentication

**File:** `backend/routes/admin.py`

Before any admin action endpoint:
```python
def require_admin_totp(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        totp_token = request.headers.get("X-Admin-TOTP")
        current_user = get_current_user()
        if not current_user.is_admin:
            abort(403)
        if not current_user.totp_enabled:
            abort(403, "Admin access requires 2FA to be enabled")
        if not verify_totp(current_user.totp_secret, totp_token):
            abort(401, "Invalid 2FA code for admin access")
        return f(*args, **kwargs)
    return decorated
```

Apply `@require_admin_totp` to all state-changing admin endpoints.

### [ ] 2-H-02 — Admin Must Write Audit Log

Every admin action function must call:
```python
AdminAuditLog.write(
    admin_user_id=current_user.id,
    action="user_suspended",
    target_user_id=target_id,
    details={"reason": reason},
    ip_address=request.remote_addr
)
```

---

## BLOCK 2-I: STRUCTURED JSON LOGGING

### [ ] 2-I-01 — Configure pythonjsonlogger

**File:** `backend/app.py`

```python
from pythonjsonlogger import jsonlogger

def setup_logging():
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO if not DEBUG else logging.DEBUG)

setup_logging()
```

All `logger.info(...)` calls should include structured context where possible:
```python
logger.info("Group linked", extra={"user_id": user_id, "group_id": group.id, "code": code})
```

---

# PHASE 3 — GROWTH & SCALE (Ship Within 60 Days)

---

## BLOCK 3-A: SEO & DISCOVERABILITY

### [ ] 3-A-01 — Add react-helmet-async to All Public Pages

**Install:** `npm install react-helmet-async`

**File:** `frontend/src/index.js` — wrap App in `<HelmetProvider>`

**Pages to update:** Landing, Pricing, Directory, DirectoryListing, Terms, Privacy

**For each page:**
```javascript
import { Helmet } from 'react-helmet-async';
<Helmet>
  <title>Telegizer — Manage Your Telegram Community | Plan Name</title>
  <meta name="description" content="..." />
  <meta property="og:title" content="..." />
  <meta property="og:description" content="..." />
  <meta property="og:image" content="https://telegizer.com/og-image.png" />
  <meta property="og:type" content="website" />
  <meta name="twitter:card" content="summary_large_image" />
</Helmet>
```

### [ ] 3-A-02 — Create OG Image

Create a branded 1200×630px PNG at `frontend/public/og-image.png`.

---

## BLOCK 3-B: "POWERED BY TELEGIZER" PLG BRANDING

### [ ] 3-B-01 — Add Branding to Free Tier Bot Messages

**File:** `backend/tcs_engine.py` or wherever welcome/digest messages are sent

```python
def add_branding(text: str, user: User) -> str:
    if user.subscription_tier == "free":
        return text + "\n\n🤖 <i>Powered by <a href='https://telegizer.com'>Telegizer</a></i>"
    return text
```

Apply to: welcome messages, digest messages, scheduled posts, auto-replies — for free tier users only.

---

## BLOCK 3-C: REFERRAL SYSTEM HARDENING

### [ ] 3-C-01 — Add Meaningful Action Gate to Referral Rewards

**File:** `backend/routes/referrals.py`

A referral is only counted (reward granted to referrer) when:
1. Referred user has verified their email
2. Referred user has connected at least one group (not just registered)
3. At least 7 days have passed since the referred user signed up

**Add `referral_qualified_at` timestamp to `Referral` model.**

### [ ] 3-C-02 — Add Milestone Reward Execution

**File:** `backend/routes/referrals.py` — after marking a referral as qualified

```python
def check_referral_milestones(referrer: User):
    qualified_count = Referral.query.filter_by(
        referrer_id=referrer.id,
        status="qualified"
    ).count()

    MILESTONES = {3: 7, 10: 30}   # referral_count: free_days
    for threshold, free_days in MILESTONES.items():
        if qualified_count == threshold:
            if referrer.subscription_tier == "free":
                referrer.subscription_tier = "pro"
                referrer.subscription_expires_at = datetime.utcnow() + timedelta(days=free_days)
            else:
                # Already paid: extend current subscription
                referrer.subscription_expires_at += timedelta(days=free_days)
            db.session.commit()
            notify_user(referrer.id, f"🎉 {free_days} days of Pro added for reaching {threshold} referrals!")
```

---

## BLOCK 3-D: DIGEST LOG TABLE

### [ ] 3-D-01 — Add DigestLog Model

**File:** `backend/models.py`

```python
class DigestLog(db.Model):
    __tablename__ = "digest_logs"
    id              = db.Column(db.Integer, primary_key=True)
    group_id        = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    telegram_group_id = db.Column(db.Integer, db.ForeignKey("telegram_groups.id"), nullable=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    generated_at    = db.Column(db.DateTime, default=datetime.utcnow)
    period_start    = db.Column(db.DateTime)
    period_end      = db.Column(db.DateTime)
    message_count   = db.Column(db.Integer, default=0)
    model_used      = db.Column(db.String(100))
    tokens_used     = db.Column(db.Integer, default=0)
    success         = db.Column(db.Boolean, default=True)
    error_message   = db.Column(db.Text)
    digest_json     = db.Column(db.JSON)     # The generated digest content
```

**Write after every digest generation.** Read in assistant digest history page.

---

# PHASE 4 — FUTURE ADVANCED (Post Product-Market Fit)

---

## BLOCK 4-A: CELERY ASYNC WORKERS

### [ ] 4-A-01 — Wire Celery for Digest Generation

**File:** `backend/celery_app.py` (create)

```python
from celery import Celery

def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=app.config["CELERY_RESULT_BACKEND"],
        broker=app.config["CELERY_BROKER_URL"]
    )
    celery.conf.update(app.config)
    return celery
```

**Procfile:**
```
web: gunicorn backend.app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4
worker: celery -A backend.celery_app worker --loglevel=info --concurrency=4
```

**Move to Celery tasks:** `generate_digest`, `send_scheduled_message`, `send_reminders`, `retry_pending_unbans`

---

## BLOCK 4-B: ALEMBIC MIGRATIONS

### [ ] 4-B-01 — Replace migrate.py with Alembic

```bash
pip install Flask-Migrate
flask db init
flask db migrate -m "initial migration from models"
flask db upgrade
```

Update `Procfile` release command:
```
release: flask db upgrade
```

Remove `backend/migrate.py` after verified working.

---

## BLOCK 4-C: BOT WEBHOOK MODE

### [ ] 4-C-01 — Switch Official Bot to Webhook Mode

**File:** `backend/routes/telegram_updates.py` (already exists — wire it up fully)

```python
# In app.py startup, instead of starting long-polling thread:
# Set webhook URL with Telegram
bot.set_webhook(url=f"{BACKEND_URL}/api/telegram/webhook/{WEBHOOK_SECRET_PATH}")
```

**Procfile:** No separate bot daemon process needed — updates arrive via HTTP.

---

## BLOCK 4-D: PGVECTOR SEMANTIC SEARCH

### [ ] 4-D-01 — Enable pgvector for Knowledge Base

**File:** `backend/assistant/embeddings.py` (already exists — wire it up)

```python
from pgvector.sqlalchemy import Vector

# In KnowledgeDocument model:
embedding = db.Column(Vector(1536))  # OpenAI ada-002 dimensions

# On document upload: generate embedding and store
async def embed_document(doc: KnowledgeDocument):
    chunks = chunk_text(doc.content, max_tokens=500)
    for chunk in chunks:
        embedding = await openai_client.embeddings.create(input=chunk, model="text-embedding-ada-002")
        # Store chunk with embedding
```

---

# SUMMARY CHECKLIST COUNTS

| Phase | Blocks | Items | Est. Dev Days |
|---|---|---|---|
| Phase 1 — Critical | 1-A through 1-I | 31 items | ~22 days |
| Phase 2 — High Priority | 2-A through 2-I | 14 items | ~14 days |
| Phase 3 — Growth & Scale | 3-A through 3-D | 6 items | ~5 days |
| Phase 4 — Advanced | 4-A through 4-D | 4 items | ~10 days |
| **TOTAL** | **18 blocks** | **55 items** | **~51 days** |

> **Note on sequencing:** Items within a phase can be parallelised across team members (e.g., one dev on 1-A while another does 1-D). Items that share files (e.g., `backend/models.py`) must be coordinated to avoid merge conflicts — do all model additions in one PR.

---

# UNIFORMITY VERIFICATION CHECKLIST

After every feature is built, verify this matrix:

| Feature | Official Bot ✓ | Custom Bot ✓ | Web Dashboard ✓ | Mini App ✓ |
|---|---|---|---|---|
| Group Linking | | | | |
| Welcome Messages | | | | |
| Auto-Moderation | | | | |
| Verification System | | | | |
| Scheduled Posts | | | | |
| AI Auto-Reply | | | | |
| Knowledge Base | | | | |
| XP & Levels | | | | |
| Polls | | | | |
| Digest Generation | | | | |
| Custom Commands | | | | |
| Forum Group Support | | | | |
| Analytics (BotEvents) | | | | |
| Member Reports | | | | |

**A feature is NOT complete until every ✓ in its row is checked.**

---

*TELEGIZER DEVELOPER IMPLEMENTATION PLAN — v1.1 — May 2026*
*Cross-validated against TELEGIZER_ENTERPRISE_SPEC.md v2.3. No conflicts, no duplicates.*
*Hand this document to your development team. Work top to bottom. Check every box.*
*For architecture reference, see companion document: `docs/TELEGIZER_ENTERPRISE_SPEC.md`*
