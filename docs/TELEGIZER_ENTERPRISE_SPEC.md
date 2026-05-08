# TELEGIZER — ENTERPRISE SYSTEM SPECIFICATION
### Master Technical Blueprint · Version 2.3 · May 2026

> **Document Status:** COMPLETE AND SYNCHRONIZED. All 4 original phases + 10 new sections (§19–§28) added to document real implementation features. Cross-validated against `DEVELOPER_IMPLEMENTATION_PLAN.md`. Version 2.3 final.
> **Audience:** Developers, architects, UI/UX teams, AI coding systems, technical agencies.
> **Purpose:** Complete implementation guide from zero to production. A developer who has never seen the codebase must be able to build the entire product from this document alone.
> **Companion document:** `docs/DEVELOPER_IMPLEMENTATION_PLAN.md` — actionable checklist of every gap between this spec and the real codebase. Work that document top-to-bottom to reach full spec compliance.

---

## TABLE OF CONTENTS

### Phase 1 (This Document)
- [1. Executive Overview](#1-executive-overview)
- [2. Full System Architecture](#2-full-system-architecture)
- [3. Complete Frontend & UX System](#3-complete-frontend--ux-system)

### Phase 2 (Next)
- [4. Full Telegram Bot System](#4-full-telegram-bot-system)
- [5. AI Assistant System](#5-ai-assistant-system)
- [6. Database Specification](#6-database-specification)

### Phase 3 (Next)
- [7. Backend & API Specification](#7-backend--api-specification)
- [8. Security Architecture](#8-security-architecture)
- [9. Deployment Architecture](#9-deployment-architecture)
- [10. Analytics & Reporting](#10-analytics--reporting)

### Phase 4 (Next)
- [11. Monetization Architecture](#11-monetization-architecture)
- [12. Full User Flows](#12-full-user-flows)
- [13. UI Component System](#13-ui-component-system)
- [14. Performance Optimization](#14-performance-optimization)
- [15. Production Readiness Checklist](#15-production-readiness-checklist)

### Version 2.3 Additions (Real Implementation — May 2026)
- [19. Unified Three-Component Architecture](#19-unified-three-component-architecture)
- [20. Meetings System](#20-meetings-system)
- [21. Partnership Deals System](#21-partnership-deals-system)
- [22. Custom Assistant Bots](#22-custom-assistant-bots)
- [23. Automation Engine](#23-automation-engine)
- [24. Polls System](#24-polls-system)
- [25. Undocumented Models — Canonical Reference](#25-undocumented-models--canonical-reference)
- [26. Assistant System — Full Module Architecture](#26-assistant-system--full-module-architecture)
- [27. TCS Engine (Template Content System)](#27-tcs-engine-template-content-system)
- [28. Group Defaults System](#28-group-defaults-system)

---

# 1. EXECUTIVE OVERVIEW

## 1.1 What Is Telegizer

Telegizer is a **premium Telegram community management and AI assistant SaaS platform**. It gives Telegram group and channel administrators a professional web dashboard to manage, automate, analyze, and grow their communities — without needing to write code or run bots manually.

The platform operates on a **shared-bot model**: one central Telegizer bot (`@TelegizerBot`) serves all users out of the box. Advanced users can bring their own bot tokens for white-label deployments. An intelligent AI assistant mirrors the user's Telegram conversations into the dashboard, surfaces insights, generates digests, creates reminders, extracts notes, and operates as a proactive community co-pilot.

---

## 1.2 The Problem Telegizer Solves

Managing a large Telegram community is painful. The native Telegram interface offers:
- No analytics on member growth, engagement, or message volume
- No automated moderation beyond basic admin controls
- No scheduled posting without third-party bots
- No AI summaries of long conversations
- No CRM for tracking member relationships
- No unified dashboard across multiple groups

Community builders resort to patching together 5–10 different bots, none of which talk to each other, none of which provide a professional interface, and none of which learn from the community's context.

Telegizer replaces all of that with a **single unified platform**.

---

## 1.3 Target Users

| Persona | Description | Core Need |
|---|---|---|
| **Community Manager** | Runs 1–10 Telegram groups (crypto, gaming, creator, professional) | Moderation, analytics, scheduled posts |
| **Creator / Influencer** | Channel + community group combo | Digest summaries, member growth, broadcast scheduling |
| **Agency / Operator** | Manages communities on behalf of clients | Multi-group dashboard, white-label bots, CRM |
| **Developer / Power User** | Wants API access, custom automation, webhooks | Full API, custom bots, workflow builder |
| **Enterprise / Brand** | Multiple communities, compliance needs, team access | Enterprise tier, dedicated support, audit logs |

---

## 1.4 Core Product Vision

> **"The Notion for Telegram communities."**

Every community that uses Telegram should have a professional operating system behind it — a single place to see what is happening, automate the routine, understand the members, and run the AI assistant that makes the admin look superhuman.

The UX philosophy draws from **Linear** (speed, keyboard-first, minimal friction), **Notion** (flexible workspace, personal + team intelligence), **Vercel** (clean deployment dashboard, great empty states), and **Stripe** (trust through polish and data transparency).

---

## 1.5 Product Positioning

```
┌─────────────────────────────────────────────────────────────────────┐
│                     TELEGIZER POSITIONING                           │
│                                                                     │
│   Simple Bot Tools          Telegizer              Enterprise CMS   │
│   (Combot, Rose)     ◄──────────────────────►     (Custom builds)  │
│                                                                     │
│   Low feature depth         SWEET SPOT            High complexity   │
│   Low price                 Pro UX + AI            Very expensive   │
│   No analytics              Affordable             Requires devs    │
│   No AI                     SaaS model                              │
└─────────────────────────────────────────────────────────────────────┘
```

Telegizer is priced and positioned to convert the millions of Telegram community operators who have outgrown free bots but cannot justify (or build) a custom enterprise solution.

---

## 1.6 SaaS Model Summary

| Tier | Price | Target | Key Limits |
|---|---|---|---|
| **Free** | $0 | Individuals, small groups | 1 bot, 1 group, 10k AI tokens/day |
| **Pro** | $19/mo or $152/yr | Active community managers | 3 bots, unlimited groups, 500k AI tokens/day, all AI features |
| **Enterprise** | $49/mo or $392/yr | Agencies, brands, operators | 50 bots, white-label, full API, bulk ops, marketplace |

Revenue streams:
1. Subscription payments via **NOWPayments** (crypto) — primary, live
2. Card payments via **Lemon Squeezy** — disabled pending review
3. **Marketplace** transaction fees — planned (escrow model, not yet built)
4. **Referral program** — user growth, milestone rewards

---

## 1.7 How Value Flows (End-to-End)

```
1. User discovers Telegizer → Landing page → Registers (Free)
2. Email verified → Dashboard
3. User adds @TelegizerBot to their Telegram group
4. User links group via one-time code (TLG-XXXXXXXX) in dashboard
5. Bot starts listening → events flow into platform DB
6. User configures: moderation, digests, auto-replies, verification
7. AI Digests summarize group activity every morning
8. User upgrades to Pro → more bots, more groups, AI features unlocked
9. Platform earns recurring subscription revenue
10. Advanced users use API + Webhooks → stickiness increases
```

---

# 2. FULL SYSTEM ARCHITECTURE

## 2.1 High-Level Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          TELEGIZER PLATFORM                              │
│                                                                          │
│  ┌──────────────┐    ┌─────────────────────────────────────────────┐    │
│  │   TELEGRAM   │    │              FRONTEND (Vercel)              │    │
│  │              │    │         React 18 SPA + MUI Dark Theme        │    │
│  │  Users in    │    │  /dashboard /groups /workspace /analytics    │    │
│  │  Groups &    │◄───┤  Axios + JWT Auth + Sentry + PWA            │    │
│  │  Channels    │    │  52 pages, lazy-loaded, mobile responsive    │    │
│  │              │    └──────────────────┬──────────────────────────┘    │
│  │  @Telegizer  │                       │ HTTPS REST + SSE               │
│  │  Bot (long   │    ┌──────────────────▼──────────────────────────┐    │
│  │  polling)    │◄───┤           BACKEND API (Railway)             │    │
│  │              │    │    Flask 3 + SQLAlchemy + JWT-Extended       │    │
│  │  Custom Bots │◄───┤    38 route modules · 28 blueprints         │    │
│  │  (per user)  │    │    APScheduler · python-telegram-bot 20.x   │    │
│  └──────────────┘    └──────┬──────────┬────────────┬─────────────┘    │
│                             │          │            │                    │
│                   ┌─────────▼──┐  ┌────▼─────┐ ┌──▼────────────┐      │
│                   │ PostgreSQL │  │  Redis   │ │  AI Providers  │      │
│                   │ (Railway)  │  │ (Railway)│ │ Gemini/OpenAI  │      │
│                   │ 30+ tables │  │ Rate lim │ │ Anthropic      │      │
│                   │ JSONB sets │  │ JWT BL   │ │ OpenRouter     │      │
│                   │ pgvector*  │  │ Sessions │ │ Custom endpoint│      │
│                   └────────────┘  └──────────┘ └───────────────┘      │
│                                                  * Phase 3              │
│   External:  NOWPayments · Resend · Sentry · Telegram Bot API           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2.2 Frontend Architecture

```
frontend/
├── public/
│   ├── index.html          # OG/Twitter/canonical meta tags, PWA manifest
│   ├── manifest.json       # PWA: name, icons, theme_color, display
│   └── robots.txt
├── src/
│   ├── App.js              # React Router v6, 60+ routes, lazy imports
│   ├── index.js            # Sentry.init, React.render
│   ├── theme.js            # MUI createTheme — dark palette, typography, components
│   ├── pages/              # 52 page components (lazy-loaded where heavy)
│   ├── components/         # 18 shared components
│   ├── services/
│   │   └── api.js          # Axios client, interceptors, all API call functions
│   ├── contexts/           # Auth context, theme context
│   └── utils/              # Helpers, formatters, constants
```

**Key architectural rules:**
- Every API call goes through `services/api.js` — no direct `fetch` or inline `axios` in pages
- No hardcoded values in components — plans, limits, usernames come from API
- `React.lazy` + `Suspense` wraps all heavy pages (analytics, notes, digests)
- `PlanGate` component wraps every Pro/Enterprise-gated feature — never gate with `if` statements inline
- `ErrorBoundary` wraps the root to prevent white screens on JS crashes

---

## 2.3 Backend Architecture

```
backend/
├── app.py                  # Flask factory: CORS, JWT, blueprints, bot start, health routes
├── config.py               # All env vars, plan limits, JWT config
├── models.py               # All SQLAlchemy models (single file, 30+ classes)
├── database.py             # SQLAlchemy engine, session factory
├── migrate.py              # Schema migration runner (CREATE TABLE IF NOT EXISTS + ALTER TABLE)
├── scheduler.py            # APScheduler jobs: reminders, digests, cleanup, health
├── official_bot.py         # Telegizer bot runner (daemon thread, long-polling)
├── bot_manager.py          # Custom bot lifecycle (start/stop per token)
├── notifications.py        # In-app notification creation helpers
├── routes/                 # 38 Blueprint modules
│   ├── auth.py             # Registration, login, 2FA, email verification, JWT
│   ├── billing.py          # NOWPayments checkout, webhook, history
│   ├── telegram_groups.py  # Official bot group management
│   ├── assistant.py        # Hub summary, DM stream (SSE), send DM
│   ├── notes.py            # Notes CRUD + AI generation
│   ├── tasks.py            # Tasks CRUD
│   ├── automations.py      # Workflow automation rules
│   └── ...                 # 31 more modules
├── assistant/
│   ├── ai_key_resolver.py  # Two-tier key logic: group → workspace → platform
│   ├── digest_ai.py        # Digest generation via Gemini
│   ├── personal_assistant.py
│   ├── handlers/           # Intent handlers: reminder, note, schedule, analyze
│   └── ...
├── bot_features/           # Modular bot feature handlers
│   ├── moderation.py
│   ├── verification.py
│   ├── welcome.py
│   ├── levels.py
│   └── knowledge_base.py
├── automation/
│   └── engine.py           # Workflow execution engine
├── middleware/
│   └── rate_limit.py       # Redis-backed Flask-Limiter integration
└── utils/
    └── encryption.py       # Fernet encrypt/decrypt helpers
```

**Blueprint registration order matters** — auth and health routes registered first so pre-request middleware whitelist works correctly.

---

## 2.4 Telegram Bot Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  TELEGIZER BOT ARCHITECTURE                  │
│                                                             │
│  official_bot.py (daemon thread, started in app.py)         │
│                                                             │
│  Application (python-telegram-bot 20.x)                     │
│    │                                                        │
│    ├── CommandHandlers                                      │
│    │   ├── /start    → welcome DM, record TelegramBotStarted│
│    │   ├── /help     → feature list                         │
│    │   ├── /linkgroup TLG-XXXXXXXX → link group to user    │
│    │   └── /status   → bot permissions summary             │
│    │                                                        │
│    ├── MessageHandler (private chats)                       │
│    │   └── personal_assistant.py → intent detection        │
│    │       ├── reminder intent → PendingReminderState flow  │
│    │       ├── note intent     → create Note record         │
│    │       ├── digest intent   → summarize on demand        │
│    │       └── general chat    → AI response (if key set)   │
│    │                                                        │
│    ├── MessageHandler (groups)                              │
│    │   ├── automod (link_filter, caps_filter)               │
│    │   ├── custom command dispatch (/cmd → response)        │
│    │   ├── auto-reply trigger matching                      │
│    │   ├── message buffering (MessageBuffer for digests)    │
│    │   └── XP/level tracking                               │
│    │                                                        │
│    ├── ChatMemberHandler                                    │
│    │   ├── on_bot_added   → DM owner, check quota          │
│    │   ├── on_bot_removed → mark group inactive            │
│    │   └── on_member_join → verification challenge         │
│    │                                                        │
│    └── CallbackQueryHandler                                 │
│        ├── v: prefix → verification responses              │
│        ├── r: prefix → reminder time/frequency selection   │
│        └── menu: prefix → inline menu navigation          │
│                                                             │
│  Custom Bots (bot_manager.py)                               │
│    └── Per-user bot instances, same handler structure       │
│        but scoped to that bot's groups                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 2.5 API Architecture

All API responses follow a **standard envelope**:

```json
{
  "success": true,
  "data": { },
  "error": null,
  "pagination": { "page": 1, "per_page": 20, "total": 142, "pages": 8 }
}
```

Error responses:
```json
{
  "success": false,
  "data": null,
  "error": { "code": "PLAN_LIMIT_REACHED", "message": "Upgrade to Pro to add more groups." }
}
```

**API versioning:** No versioning in URL for MVP. When breaking changes are needed, prefix with `/api/v2/`. Current routes are implicitly `/api/v1/`.

**Authentication:** All protected endpoints require `Authorization: Bearer <jwt_access_token>`. Token lifetime: 1 day. Refresh token: 30 days.

---

## 2.6 Database Architecture

```
PostgreSQL 15 on Railway
  ├── Connection pooling: SQLAlchemy pool_pre_ping=True, pool_recycle=300s
  ├── 30+ tables, all created via migrate.py (no Alembic for MVP)
  ├── JSONB columns for flexible settings (group settings, bot permissions, tags)
  ├── FK indexes on all foreign key columns (P1-08 fix — 10 indexes)
  ├── Soft delete: users only (deleted_at field — TODO: implement)
  └── pgvector extension: ready for Phase 3 semantic search (embeddings.py exists)
```

---

## 2.7 Redis Architecture

```
Redis on Railway (or localhost for dev)
  ├── JWT blocklist: key=jti, TTL=token_expiry
  ├── Rate limiting: flask-limiter storage backend
  ├── TOTP nonces: key=totp_nonce:{user_id}, TTL=90s (one-use for 2FA)
  ├── Login fail counters: key=login_fail:{email}, TTL=15min
  └── Email verify fail counters: key=verify_fail:{email}, TTL=1hr

Fallback: If Redis unavailable:
  - JWT blocklist → falls back to DB revoked_tokens table
  - Rate limiting on auth endpoints → **fails CLOSED (returns 503)** — never fails open on security-critical endpoints
  - Rate limiting on non-auth endpoints → fails open (allows request, logs WARNING)
  - TOTP nonces → Redis required; 2FA login fails gracefully with clear error
  - Group settings cache → falls back to DB read (correct behavior, slightly slower)
  - AI quota counter → falls back to approximate DB counter (non-atomic, acceptable degradation)
  - SSE nonce validation → SSE unavailable (503) — safer than skipping auth
```

---

## 2.8 Async Jobs & Scheduling

All background jobs run in `scheduler.py` using **APScheduler** (in-process, not Celery). Runs inside the same Railway dyno as Flask.

```
Every 1 minute:
  - send_pending_reminders()     → fire due WorkspaceReminder rows
  - send_scheduled_messages()    → fire due ScheduledMessage rows

Every 10 minutes:
  - check_bot_health()           → ping Telegram getMe for all active custom bots
  - expire_pending_reminder_states() → delete PendingReminderState rows past expires_at

Every 15 minutes:
  - expire_link_codes()          → mark expired TelegramGroupLinkCode rows as used
  - retry_pending_unbans()       → retry failed unban attempts (up to 5 retries, exp backoff)

Daily at configured time per group:
  - send_daily_digests()         → digest_ai.py for each enabled group
                                   ⚠️ MUST check check_feature_access(user, 'digests') before
                                   generating — free users must not receive digests even if
                                   settings are saved (e.g. after downgrade from Pro)

Weekly on configured day:
  - send_weekly_digests()        → digest_ai.py for weekly groups

Daily at midnight UTC:
  - reset_daily_ai_tokens()      → set workspace_ai_tokens_today=0 for all users
  - downgrade_expired_subscriptions()  → users WHERE subscription_expires_at < NOW()
                                         AND subscription_grace_until < NOW()
                                         SET subscription_tier='free',
                                             subscription_expires_at=NULL
                                         AND send "subscription expired" email

Daily at 1am UTC:
  - send_subscription_reminders() → email users WHERE subscription_expires_at
                                    BETWEEN NOW() AND NOW() + 7 days
                                    (reminder at 7d, 3d, 1d before expiry)

Daily at 3am UTC:
  - _run_bot_event_cleanup()     → DELETE bot_events WHERE created_at < NOW() - 90 days

Daily at 4am UTC:
  - purge_deleted_accounts()     → hard-delete users WHERE deleted_at < NOW() - 14 days

⚠️ Scheduler Scaling Warning: APScheduler runs in-process alongside Gunicorn workers and
the bot daemon. This is acceptable for MVP but digest generation is synchronous and AI calls
(5–30s) will block Gunicorn workers during the daily digest run. Phase 2 target: move all
AI generation jobs to a dedicated Celery worker process (see Section 16).
```

---

## 2.9 Webhook Architecture

```
Inbound webhooks (POST endpoints, all HMAC-verified):
  /api/billing/nowpayments-webhook
    → Verify: HMAC-SHA256 of payload with NOWPAYMENTS_IPN_SECRET
    → Idempotency: check ProcessedPayment for payment_id before acting
    → Action: upgrade user plan if payment_status == "finished"

  /api/webhooks/:integration_id/inbound
    → Verify: HMAC-SHA256 of payload with per-integration signing_secret
    → Action: trigger automation rules matching the webhook payload

  /api/telegram-updates (optional webhook mode)
    → Currently: long-polling via daemon thread
    → Future: switch to webhook for horizontal scaling

Outbound webhooks (user-configured):
  → WebhookIntegration model stores URL + signing_secret
  → On events: POST JSON payload, sign with HMAC-SHA256
  → Retry: 3 attempts with exponential backoff
```

---

## 2.10 Analytics Pipeline

```
Data collection:
  Telegram bot → BotEvent records (member_joined, automod_action, command_triggered, etc.)
  Web dashboard actions → direct DB writes
  Payment events → PaymentHistory records
  AI usage → workspace_ai_tokens_today counter

Aggregation:
  /api/official-groups/:id/analytics
    → COUNT BotEvents by type, GROUP BY date
    → member growth chart (member_joined events)
    → verification pass/fail rates
    → automod action breakdown

  /api/official-groups/analytics/overview
    → Aggregate across ALL user's groups
    → Total messages, total members, total joins this period

  /api/analytics/:botId/:groupId (custom bots)
    → Same structure, scoped to custom bot group

Frontend:
  → Recharts library for all charts
  → Date range picker: last 7d / 30d / 90d / custom
  → Export: CSV download of raw data
```

---

## 2.11 Notification System

```
In-App Notifications (push from backend → frontend poll):
  Trigger: backend calls notifications.create(user_id, type, title, message, data)
  Storage: notifications table
  Frontend: bell icon polls /api/notifications/unread-count every 60s
  Display: dropdown on click, shows last 20, mark read on click

Email Notifications (Resend API / SMTP):
  Trigger: async background thread from within route handlers
  Templates: plain HTML, from noreply@telegizer.com
  Types: email verification, password reset, payment confirmation, group events

Bot DM Notifications (via Telegram):
  Trigger: scheduler jobs, payment events, group events
  Delivery: bot.send_message(chat_id=user.telegram_id, text=...)
  Requires: user to have started @TelegizerBot (TelegramBotStarted table)
  Fallback: in-app notification if telegram_id not linked

SSE Stream (Live Chat mirror):
  GET /api/assistant/dm-stream
  → Server polls BotDMMessage every 2s, streams new rows
  → Frontend: EventSource API, auto-reconnect on disconnect
```

---

# 3. COMPLETE FRONTEND & UX SYSTEM

## 3.1 Design Philosophy

Telegizer's interface is built on four principles drawn from the best SaaS products:

| Principle | Reference | Application |
|---|---|---|
| **Speed is a feature** | Linear | Actions feel instant; optimistic UI; no spinners on fast ops |
| **Information density without clutter** | Stripe Dashboard | Data-rich cards that don't feel overwhelming |
| **Personal workspace energy** | Notion | The dashboard feels like *your* control center, not a generic admin panel |
| **Trust through polish** | Vercel | Empty states are helpful, not embarrassing; errors are human |

The interface is **dark-mode first**, using a deep navy/charcoal base that feels premium and reduces eye strain during long management sessions. The accent color is electric indigo (`#6C63FF`) — distinctive, modern, not another blue SaaS.

---

## 3.2 Design Token System

### Color Palette

```javascript
// theme.js — MUI createTheme dark palette
const palette = {
  mode: 'dark',
  primary: {
    main:    '#6C63FF',   // electric indigo — buttons, links, active states
    light:   '#8B85FF',   // hover states, subtle highlights
    dark:    '#5A52D5',   // pressed states
    contrastText: '#FFFFFF',
  },
  secondary: {
    main:    '#FF6B6B',   // coral red — destructive, alerts
    light:   '#FF8E8E',
    dark:    '#E85555',
  },
  success: {
    main:    '#4ADE80',   // emerald green
    light:   '#6EEB98',
    dark:    '#22C55E',
  },
  warning: {
    main:    '#FBBF24',   // amber
    light:   '#FCD34D',
    dark:    '#F59E0B',
  },
  error: {
    main:    '#F87171',   // soft red
    dark:    '#EF4444',
  },
  background: {
    default: '#0D0D14',   // deep space black — page background
    paper:   '#16161F',   // card/panel surface
    elevated:'#1E1E2E',   // modals, dropdowns, elevated surfaces
    subtle:  '#12121A',   // sidebar, low-contrast areas
  },
  text: {
    primary:   '#F1F0FF', // near-white with slight purple tint
    secondary: '#8B8FA8', // muted — labels, captions
    disabled:  '#4A4A5A', // truly inactive
  },
  divider: '#2A2A3D',
};
```

### Typography Scale

```javascript
const typography = {
  fontFamily: '"Inter", "SF Pro Display", -apple-system, sans-serif',
  h1: { fontSize: '2rem',    fontWeight: 700, letterSpacing: '-0.025em', lineHeight: 1.2 },
  h2: { fontSize: '1.5rem',  fontWeight: 700, letterSpacing: '-0.02em',  lineHeight: 1.3 },
  h3: { fontSize: '1.25rem', fontWeight: 600, letterSpacing: '-0.015em', lineHeight: 1.35 },
  h4: { fontSize: '1.1rem',  fontWeight: 600, letterSpacing: '-0.01em',  lineHeight: 1.4 },
  body1: { fontSize: '0.9375rem', fontWeight: 400, lineHeight: 1.6 },  // 15px
  body2: { fontSize: '0.875rem',  fontWeight: 400, lineHeight: 1.55 }, // 14px
  caption: { fontSize: '0.75rem', fontWeight: 400, lineHeight: 1.5, color: '#8B8FA8' },
  overline: { fontSize: '0.6875rem', fontWeight: 600, letterSpacing: '0.08em',
              textTransform: 'uppercase', color: '#8B8FA8' },
  code: { fontFamily: '"JetBrains Mono", "Fira Code", monospace', fontSize: '0.875rem' },
};
```

### Spacing System

```
Base unit: 8px
  spacing(0.5) = 4px   — micro gaps
  spacing(1)   = 8px   — tight inline spacing
  spacing(2)   = 16px  — standard element padding
  spacing(3)   = 24px  — card padding, section gaps
  spacing(4)   = 32px  — large section padding
  spacing(6)   = 48px  — page-level vertical spacing
  spacing(8)   = 64px  — hero sections
```

### Border Radius

```
xs:   4px   — chips, small badges
sm:   8px   — buttons, inputs, small cards
md:   12px  — standard cards, panels
lg:   16px  — modals, large feature cards
xl:   24px  — hero cards, onboarding elements
full: 9999px — pills, avatars
```

### Elevation / Shadow System

```css
/* Cards (resting) */
box-shadow: 0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.05);

/* Cards (hover/interactive) */
box-shadow: 0 4px 16px rgba(108,99,255,0.15), 0 0 0 1px rgba(108,99,255,0.2);

/* Modals */
box-shadow: 0 24px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.06);

/* Dropdowns */
box-shadow: 0 8px 24px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05);
```

---

## 3.3 Motion System

Telegizer uses **purposeful, minimal animation** — motion that communicates state, not decoration.

```javascript
// MUI transitions
const transitions = {
  duration: {
    shortest:  100,  // micro interactions (checkbox, toggle)
    shorter:   150,  // button hover effects
    short:     200,  // sidebar collapse, dropdown open
    standard:  250,  // page transitions, modal open
    complex:   350,  // multi-step animations
  },
  easing: {
    // Fast start, soft landing — feels responsive
    easeOut: 'cubic-bezier(0.0, 0, 0.2, 1)',
    // Standard motion
    easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
    // Springy — for success states, confirmations
    spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
  },
};

// CSS keyframes
@keyframes pulseGreen {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.7; transform: scale(1.15); }
}
// Used for: online status dots, digest sent confirmation, payment success

@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position:  200% 0; }
}
// Used for: skeleton loaders

@keyframes slideInUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
// Used for: cards loading in, notification toasts
```

**Rules:**
- Never animate layout shifts (no `width`/`height` transitions on content containers)
- Loading skeletons must shimmer — static grey blocks feel broken
- Success confirmations get a brief spring animation (scale 1→1.05→1)
- Page transitions: fade + 8px up slide, 250ms

---

## 3.4 Responsive System

```
Breakpoints (MUI defaults, augmented):
  xs: 0px      — mobile portrait (320–480px)
  sm: 600px    — mobile landscape / small tablet
  md: 900px    — tablet / small laptop
  lg: 1200px   — desktop
  xl: 1536px   — wide desktop

Layout behaviour:
  xs/sm:
    - Sidebar hidden; bottom navigation bar (5 items)
    - Single-column card layout
    - Tables: horizontal scroll inside TableContainer
    - Modals: full-screen (fullScreen prop on Dialog)
    - Floating action button for primary action

  md:
    - Sidebar collapsible (icon-only when collapsed, 64px wide)
    - 2-column card grids
    - Condensed analytics charts

  lg/xl:
    - Full sidebar (240px)
    - 3-column card grids where appropriate
    - Side-by-side detail panels
    - Inline expansion (no separate page for minor details)
```

**Mobile-first standards:**
- Minimum tap target: 44×44px (Apple HIG)
- Minimum font size for readability: 14px (never smaller in interactive UI)
- Bottom nav uses icons + labels for all 5 items — no icon-only mobile nav
- Long lists use virtual scrolling (react-window) for 100+ items

---

## 3.5 Telegram In-App Browser Handling

Telegram has a built-in browser (TMA/WebView) that renders web pages when users click links. Telegizer should gracefully handle this environment.

```javascript
// Detect Telegram WebView
const isTelegramWebView = () =>
  /Telegram|TelegramBot/i.test(navigator.userAgent);

// Detect Telegram Mini App
const isMiniApp = () =>
  typeof window.Telegram !== 'undefined' &&
  typeof window.Telegram.WebApp !== 'undefined';

// Behaviour rules:
// 1. Telegram WebView: show "Open in browser" banner for dashboard pages
// 2. Mini App (/mini-app routes): use Telegram.WebApp.ready(), expand, use MainButton
// 3. Never use window.open() — it doesn't work in TMA; use Telegram.WebApp.openLink()
// 4. Back button: in TMA, wire Telegram.WebApp.BackButton.show() / .onClick()
// 5. Theme: read Telegram.WebApp.colorScheme to match Telegram's theme if in TMA
```

---

## 3.6 Sidebar Architecture

```
Sidebar width: 240px (expanded), 64px (collapsed icon-only)
Background: background.subtle (#12121A)
Border-right: 1px solid divider

HEADER:
  [Telegizer Logo] [Collapse button]
  User avatar + name + plan badge (mini: avatar only)

NAVIGATION SECTIONS:

  COMMUNITIES
  ├── Groups              /groups         (GroupsIcon)
  └── Channels            /channels       (CampaignIcon)

  ASSISTANT
  ├── Hub                 /workspace      (PsychologyIcon) ← landing
  ├── Auto-Replies        /workspace/smart-links  (ReplyIcon)
  ├── Reminders           /workspace/reminders    (AccessTimeIcon)
  ├── Notes               /workspace/notes        (EditNoteIcon)
  ├── Digests             /workspace/digests      (SummarizeIcon)
  ├── Tasks               /workspace/tasks        (TaskAltIcon)
  ├── Knowledge           /workspace/knowledge    (MenuBookIcon)
  └── AI Settings         /workspace/ai-settings  (TuneIcon)

  AUTOMATION
  ├── Forwarding          /workspace/forwarding   (SendIcon)
  └── Workflows           /workspace/automations  (AutoModeIcon)

  ANALYTICS
  ├── Overview            /analytics              (InsightsIcon)
  ├── Groups              /analytics?tab=groups   (GroupsIcon)
  └── Channels            /analytics?tab=channels (CampaignIcon)

  GROW
  ├── Directory           /directory              (ExploreIcon)
  └── Marketplace         /marketplace            (StorefrontIcon)

  ACCOUNT
  ├── Custom Bots         /custom-bots            (SmartToyIcon)
  ├── Billing             /billing                (CreditCardIcon)
  └── Settings            /settings               (SettingsIcon)

FOOTER:
  [Admin Panel] (only if is_admin === true)
  App version: v2.x.x
```

**Active state:** Left border 3px `primary.main`, background `rgba(108,99,255,0.08)`, text `primary.main`

**Hover state:** Background `rgba(255,255,255,0.04)`, text `text.primary`

**Section labels:** `overline` typography, `text.secondary` color, not clickable

---

## 3.7 Dashboard UX

The Dashboard (`/dashboard`) is the **30-second health check**. The user opens it, glances, and immediately knows if anything needs attention.

```
┌─────────────────────────────────────────────────────────────────┐
│  Good morning, [Name] 👋          Today: Thursday, May 8 2026   │
│  Plan: PRO  ·  Billing: Active  ·  [Upgrade to Enterprise]      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────┐ │
│  │  3 Groups   │ │  2 Custom   │ │  127 Members│ │  2 Tasks │ │
│  │  All Active │ │  Bots ✓     │ │  +12 today  │ │  Due     │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────┘ │
│                                                                 │
│  ┌────────────────────────────────┐ ┌────────────────────────┐ │
│  │  Recent Bot Activity           │ │  Reminders Today       │ │
│  │  ─────────────────────         │ │  ───────────────────── │ │
│  │  ● member_joined — Crypto Hub  │ │  □ 3:00pm — Call John  │ │
│  │    2 mins ago                  │ │  □ 5:00pm — Review     │ │
│  │  ● automod_action — Spam Det.  │ │    contracts           │ │
│  │    15 mins ago                 │ │  ✓ 9:00am — Standup    │ │
│  │  ● command_triggered — /rules  │ │                        │ │
│  │    1 hour ago                  │ │  [View All Reminders]  │ │
│  │  [View All Events]             │ │                        │ │
│  └────────────────────────────────┘ └────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Quick Actions                                           │  │
│  │  [+ Link Group]  [+ Add Bot]  [View Digests]  [Billing]  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Data loaded (Promise.all on mount):**
```javascript
const [me, bots, groups, notifications, reminders] = await Promise.all([
  auth.getMe(),
  bots.getAll(),
  telegramGroups.getAll(),
  notifications.unreadCount(),
  workspace.getReminders({ limit: 3, due_today: true }),
]);
```

---

## 3.8 Assistant Hub UX

The Hub (`/workspace`) is the **AI co-pilot dashboard**. It shows the user what the assistant has been doing and what needs attention.

```
┌─────────────────────────────────────────────────────────────────┐
│  ╔═══════════════════════════════════════════════════════════╗  │
│  ║  Connect Bot Banner (dismissible)                        ║  │
│  ║  Add @TelegizerBot to a group to unlock all features.    ║  │
│  ║  [Add to Group]  [Copy Link]              [Dismiss ×]    ║  │
│  ╚═══════════════════════════════════════════════════════════╝  │
│                                                                 │
│  Today — Thursday, May 8                                        │
│                                                                 │
│  ┌──────────────────────────┐ ┌──────────────────────────────┐ │
│  │  Reminders — 2 due       │ │  Recent Notes                │ │
│  │  ─────────────────────── │ │  ─────────────────────────── │ │
│  │  □ 3:00pm · Call John    │ │  [AI] Crypto Hub · 2h ago    │ │
│  │  □ 5:00pm · Review docs  │ │    "Decided: launch Q3..."   │ │
│  │                          │ │  [Bot] Personal · 1d ago     │ │
│  │  [View All →]            │ │    "Meeting notes saved"     │ │
│  └──────────────────────────┘ └──────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────┐ ┌──────────────────────────────┐ │
│  │  Digest Status           │ │  Automation Activity         │ │
│  │  ─────────────────────── │ │  ─────────────────────────── │ │
│  │  ✓ Crypto Hub · sent 9am │ │  Auto-replies fired: 14      │ │
│  │  ⟳ Dev Group · pending  │ │  Workflows ran: 3            │ │
│  │  — Gaming · disabled     │ │  Messages forwarded: 7       │ │
│  │                          │ │                              │ │
│  │  [Configure Digests →]   │ │  [View Workflows →]          │ │
│  └──────────────────────────┘ └──────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Onboarding Checklist (hidden after all complete)        │  │
│  │  ✓ Add bot to a group                                    │  │
│  │  ✓ Configure first Auto-Reply                            │  │
│  │  □ Set up Daily Digest                                   │  │
│  │  □ Create your first Note                                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Connect Bot banner logic:**
```javascript
const shouldShowBanner = (groups, user) => {
  if (groups.length === 0) return true;
  const dismissedAt = localStorage.getItem('botBannerDismissedAt');
  if (dismissedAt) return false;
  const daysSinceFirstGroup = daysSince(groups[0].linked_at);
  return daysSinceFirstGroup < 3;
};
```

---

## 3.9 Onboarding UX

New users experience a **zero-to-value onboarding** designed to get them from registration to first bot activity in under 5 minutes.

### Post-Registration Journey

```
Step 1: Email Verification
  ┌────────────────────────────────────────────────────────┐
  │  Check your inbox                                      │
  │  We sent a verification link to user@email.com         │
  │  [Open Gmail]  [Resend email]                          │
  │  ← Wrong email? Start over                             │
  └────────────────────────────────────────────────────────┘
  UX notes:
  - "Open Gmail" button if email contains gmail
  - "Open Outlook" if outlook/hotmail/live
  - Resend available after 60 seconds (countdown shown)
  - No /dashboard access until verified

Step 2: Dashboard (first visit)
  - Welcome modal: "Welcome to Telegizer, [Name]!"
  - 3-step onboarding card visible (not modal — doesn't block)
  - Checklist: Add bot → Link group → Configure first feature

Step 3: Add Bot Prompt (persistent until done)
  ┌────────────────────────────────────────────────────────┐
  │  Start managing your first group                       │
  │  1. Add @TelegizerBot to your Telegram group           │
  │     [Copy Bot Link]  [@TelegizerBot]                   │
  │  2. Get your link code in the dashboard                │
  │     [Generate Link Code]                               │
  │  3. Send /linkgroup TLG-XXXXXXXX in your group         │
  └────────────────────────────────────────────────────────┘

Step 4: Group Linked
  - Confetti animation (subtle, 1.5s)
  - Toast: "🎉 Your group 'GroupName' is now connected!"
  - Redirect to group settings page
  - Checklist item ✓ checked
```

---

## 3.10 Empty States Specification

Every empty state follows the pattern: **Illustration → Headline → Supporting text → Primary CTA → Secondary CTA**

```
/groups (no groups):
  Icon: GroupsOutlined (64px, primary.main, 0.3 opacity)
  Headline: "No groups connected yet"
  Body: "Add @TelegizerBot to a Telegram group, then use a link code to connect it here."
  CTA: [Generate Link Code]
  Secondary: [Learn how it works →]

/workspace/notes (no notes):
  Icon: EditNoteOutlined
  Headline: "Your note space is empty"
  Body: "DM @TelegizerBot 'note this' in any conversation, or generate AI notes from a group's messages."
  CTA: [Create a Note]
  Secondary: [Generate from Group ▾]

/workspace/digests (no groups with digest enabled):
  Icon: SummarizeOutlined
  Headline: "No digests configured"
  Body: "Connect a group and enable Digests to get daily AI summaries of your community activity."
  CTA: [Configure Digests]

/workspace/reminders (no reminders):
  Icon: AccessTimeOutlined
  Headline: "Nothing on your radar"
  Body: "DM @TelegizerBot 'remind me to...' or create reminders directly from the dashboard."
  CTA: [+ Add Reminder]

/analytics (no events yet):
  Icon: InsightsOutlined
  Headline: "No data to show yet"
  Body: "Once your bot is active in a group, analytics will appear here automatically."
  CTA: [Link a Group]

/custom-bots (no bots):
  Icon: SmartToyOutlined
  Headline: "No custom bots yet"
  Body: "Bring your own bot token from @BotFather for white-label community management."
  CTA: [+ Add Bot]
  Secondary: [What are custom bots? →]
```

---

## 3.11 Skeleton Loader Specification

Every data-dependent component must show MUI `Skeleton` components while loading. Rules:

```javascript
// Skeleton must MATCH the shape of the loaded content
// Never show a single bar where cards will appear

// Card grid skeleton
const CardGridSkeleton = ({ count = 3 }) => (
  <Grid container spacing={2}>
    {Array.from({ length: count }).map((_, i) => (
      <Grid key={i} item xs={12} sm={6} lg={4}>
        <Skeleton variant="rounded" height={140} animation="wave" />
      </Grid>
    ))}
  </Grid>
);

// Table skeleton
const TableSkeleton = ({ rows = 5 }) => (
  <TableBody>
    {Array.from({ length: rows }).map((_, i) => (
      <TableRow key={i}>
        <TableCell><Skeleton variant="text" width="60%" /></TableCell>
        <TableCell><Skeleton variant="text" width="40%" /></TableCell>
        <TableCell><Skeleton variant="rounded" width={80} height={24} /></TableCell>
      </TableRow>
    ))}
  </TableBody>
);

// Stats number skeleton
const StatSkeleton = () => (
  <Box>
    <Skeleton variant="text" width={60} height={40} />  {/* the number */}
    <Skeleton variant="text" width={100} height={20} /> {/* the label */}
  </Box>
);

// Rules:
// - animation="wave" always (not "pulse" — too distracting)
// - Match approximate dimensions of real content
// - Never re-show skeleton during a refresh — show stale data with a subtle loading bar at top
// - Maximum skeleton display time: if data doesn't load in 10s, show error state
```

---

## 3.12 Settings UX

The Settings page (`/settings`) follows a **tabbed sidebar layout** consistent with linear-style settings panels.

```
/settings
  ├── Profile        name, email, timezone, avatar (initial-based for MVP)
  ├── Password       current password + new password + confirm
  ├── Security       2FA setup/manage, active sessions (future), backup codes
  ├── Connected      Telegram account(s) linked, connect/disconnect
  ├── API Keys       workspace AI keys, provider selection, test connection
  └── Danger Zone    Export data, Delete account
```

**Settings UX rules:**
- Changes save on [Save Changes] button — never auto-save (prevents accidental changes)
- Destructive actions (delete account) require a dedicated confirmation with typed text: `type DELETE to confirm`
- 2FA section shows current state clearly: "2FA is ON · 6 backup codes remaining"
- API key fields: show masked value after save (`sk-...xxxx`), [Reveal] + [Regenerate] buttons

---

## 3.13 Error State UX

```
Network error (no internet):
  Toast: "Connection lost. Trying to reconnect..." (persistent until resolved)
  Retry automatically every 10s
  On reconnect: toast "Back online ✓" (green, 3s)

401 Unauthorized:
  Auto-redirect to /login (interceptor handles silently)
  /login shows: "Your session expired. Please sign in again." (if redirected)

403 Plan Gate:
  PlanGate modal slides up from bottom (not a blocking dialog)
  Shows: feature name, what plan it requires, price, [Upgrade Now] button
  Dismissible — user can close and continue with limited functionality

500 Server Error:
  Toast: "Something went wrong on our end. We've been notified."
  Show [Try Again] button on the failed component
  Log to Sentry with full context

Form validation errors:
  Inline, below each field, in error.main color
  Field border turns error.main
  Summary of errors NOT shown at top (field-level is sufficient)
  On submit: scroll to first error field
```

---

*Phase 1 complete. Sections 1–3 documented.*

---

# 4. FULL TELEGRAM BOT SYSTEM

## 4.1 Bot Architecture Philosophy

Telegizer operates a **single official bot** (`@TelegizerBot`) that serves all platform users. This is the key scalability and onboarding decision: users do not need to create their own bot to get started. The shared bot handles all group management functionality out of the box.

For users who need white-label or per-client bots, the **Custom Bot** system allows bringing any bot token and mapping it to the same feature set.

Both bot types share the same handler architecture — the difference is ownership scope.

---

## 4.2 Official Bot Lifecycle

> **⚠️ Critical Flask 3 Compatibility Note:** `@app.before_first_request` was deprecated in Flask 2.2 and **removed entirely in Flask 3.0**. The bot MUST be started using the Flask 3 compatible pattern below. Using the old decorator will cause the bot to silently never start — no error, no crash, just a dead bot in production.

```python
# app.py — bot starts after Flask is ready (Flask 3 compatible)
def create_app():
    app = Flask(__name__)
    # ... configure routes, db, etc.
    
    # Flask 3 compatible startup — NOT @before_first_request
    _start_official_bot_thread(app)
    
    return app


def _start_official_bot_thread(app):
    """Start the official bot in a daemon thread after Flask is initialized.
    Called once inside create_app(). Safe to call multiple times — uses a
    module-level flag to prevent double-start.
    """
    import threading, time
    
    if getattr(_start_official_bot_thread, '_started', False):
        return
    _start_official_bot_thread._started = True
    
    def _delayed_start():
        time.sleep(5)  # wait for DB pool to settle after app startup
        with app.app_context():
            from official_bot import start_official_bot
            start_official_bot(app)
    
    thread = threading.Thread(target=_delayed_start, daemon=True, name="TelegizerBotThread")
    thread.start()
    app.logger.info("Official bot thread scheduled for startup in 5s")

# official_bot.py
def start_official_bot(flask_app):
    application = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )
    # Register all handlers
    _register_handlers(application)
    # Run long-polling in background thread
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,   # skip queued updates on restart
    )
```

**Critical constraint:** The bot runs as a daemon thread. `numReplicas` in Railway **must be 1**. Multiple instances would receive duplicate updates from Telegram's long-polling, causing duplicate command responses, duplicate event logs, and double-fired automations. This constraint must be in the Railway config and documented in the ops runbook.

---

## 4.3 Handler Registration

```python
def _register_handlers(application):
    # Commands
    application.add_handler(CommandHandler("start",     cmd_start))
    application.add_handler(CommandHandler("help",      cmd_help))
    application.add_handler(CommandHandler("linkgroup", cmd_linkgroup))
    application.add_handler(CommandHandler("status",    cmd_status))

    # Group messages (all text in groups/supergroups)
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS,
        handle_group_message
    ))

    # Private DMs
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE,
        handle_private_message
    ))

    # Member join/leave events
    application.add_handler(ChatMemberHandler(
        handle_chat_member_update,
        ChatMemberHandler.CHAT_MEMBER
    ))

    # Inline keyboard callbacks
    application.add_handler(CallbackQueryHandler(
        handle_callback_query
    ))

    # Error handler
    application.add_error_handler(handle_error)
```

---

## 4.4 Group Linking Flow (Complete)

```
PRE-CONDITIONS:
  - User is registered and email-verified on Telegizer
  - @TelegizerBot is NOT yet in the user's group

STEP 1: User generates link code
  POST /api/telegram-groups/pending-link
  Backend:
    code = "TLG-" + secrets.token_hex(4).upper()   # TLG-A3F8C2B1
    expires_at = datetime.utcnow() + timedelta(minutes=12)
    TelegramGroupLinkCode.create(code, user_id, expires_at)
  Response: { code: "TLG-A3F8C2B1", expires_at: "..." }
  Frontend: shows code + 12-minute countdown + instructions

STEP 2: User adds bot to Telegram group
  User adds @TelegizerBot as admin via Telegram native UI
  Bot receives ChatMemberHandler update (type: bot_added)
  Bot does NOT auto-link — waits for explicit /linkgroup command
  Bot sends DM to adder (if they've started the bot):
    "I was added to [GroupName]! To link it to your Telegizer dashboard,
     go to your dashboard and get a link code, then send:
     /linkgroup TLG-XXXXXXXX in the group."

STEP 3: User sends /linkgroup in the group
  Handler: cmd_linkgroup(update, context)
  
  a) Extract code from command args
  b) Validate format: must match TLG-[A-F0-9]{8}
  c) Database lookup (SELECT FOR UPDATE — prevents race condition):
     code_row = db.query(TelegramGroupLinkCode).filter_by(code=code)
                  .with_for_update().first()
  d) Validate:
     - code exists
     - not used (used=False)
     - not expired (expires_at > utcnow)
     - user must be admin in the group (check Telegram getChatMember)
  e) On success:
     - Create TelegramGroup record
     - Mark code as used
     - Fetch and store bot permissions (getChatMember for bot itself)
     - Fetch group title + member count
     - Log BotEvent: group_linked
     - Bot sends confirmation in group: "✓ Group linked to Telegizer dashboard!"
     - Bot DMs owner: "Your group '[title]' has been linked successfully."
  f) On failure:
     - Bot replies in group: specific error message
     - Code expired: "This code has expired. Generate a new one in your dashboard."
     - Already used: "This code was already used."
     - Not admin: "Only group admins can link a group."

STEP 4: Dashboard auto-updates
  Frontend polls GET /api/telegram-groups every 10s while dialog open
  On new group appearing → close dialog, show success toast, redirect to group settings
```

---

## 4.5 Bot Permissions System

The 8 real Telegram bot admin permissions tracked in `TelegramGroup.bot_permissions`:

```python
PERMISSION_FIELDS = {
    'can_change_info':       'Change Group Info',
    'can_delete_messages':   'Delete Messages',
    'can_invite_users':      'Invite Users',
    'can_restrict_members':  'Restrict Members',
    'can_pin_messages':      'Pin Messages',
    'can_promote_members':   'Promote Members',
    'can_manage_chat':       'Manage Chat',
    'can_manage_video_chats':'Manage Video Chats',
}

# Permission score (0–100)
score = (sum(1 for v in bot_permissions.values() if v) / 8) * 100

# Score tiers
score >= 80: "Full Access"    (green)
score >= 50: "Partial Access" (yellow)
score  < 50: "Limited Access" (red)

# Live refresh
GET /api/official-groups/:id/permissions
→ calls Telegram API getChatMember(chat_id, bot_id)
→ updates TelegramGroup.bot_permissions in DB
→ returns fresh permissions object
```

**Why this matters:** If the bot lacks `can_delete_messages`, AutoMod cannot delete spam. If it lacks `can_restrict_members`, verification cannot restrict new joiners. The permission score card in the dashboard educates users on what to grant.

---

## 4.6 Admin Sync

```python
# GET /api/official-groups/:id/admins
# Returns list of Telegram admins + can_dm flag

def get_group_admins(group_id):
    chat_admins = bot.get_chat_administrators(chat_id=group_id)
    result = []
    for admin in chat_admins:
        user = admin.user
        has_started = TelegramBotStarted.exists(user.id)
        result.append({
            'telegram_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'is_anonymous': admin.is_anonymous,
            'custom_title': admin.custom_title,
            'can_dm': has_started,  # can we send them DM notifications?
        })
    return result

# OfficialMember.is_admin cached for 5 minutes
# Updated on every ChatMemberHandler update
# _require_admin in group context checks cached flag first (5-min TTL)
```

---

## 4.7 Custom Command System

```python
# Custom commands stored in CustomCommand model:
# { group_id, trigger: "/rules", response: "1. Be respectful...", created_at }

# Dispatch in handle_group_message:
def handle_group_message(update, context):
    message = update.message
    if not message or not message.text:
        return
    
    # Check if it's a command
    if message.text.startswith('/'):
        cmd = message.text.split()[0].lower().lstrip('/')
        # Look up custom command for this group
        custom_cmd = CustomCommand.get(group_id, trigger=f'/{cmd}')
        if custom_cmd:
            await message.reply_text(custom_cmd.response)
            # Log event
            BotEvent.log(group_id, 'command_triggered', {
                'command': cmd,
                'user_id': message.from_user.id,
            })
            return
    
    # Continue to automod, XP, message buffer...
```

**Command templates available in dashboard:**
- `/rules` — post group rules
- `/links` — post curated link list
- `/socials` — post social media links
- `/website` — post website URL
- `/help` — post help message
- Custom (blank template)

---

## 4.8 AutoMod System

```python
# handle_group_message — automod section
async def _check_automod(update, context, group_settings):
    message = update.message
    automod = group_settings.get('automod', {})
    user_id = message.from_user.id
    
    # Skip admins if exempt_admins is True
    if automod.get('exempt_admins') and _is_admin(user_id, group_id):
        return
    
    # LINK FILTER
    link_cfg = automod.get('link_filter', {})
    if link_cfg.get('enabled'):
        has_link = bool(re.search(r'https?://|t\.me/|@\w+', message.text))
        if has_link:
            await message.delete()
            await _apply_automod_action(
                context, message, link_cfg['action'],
                warn_delete_seconds=link_cfg.get('warn_delete_seconds', 0)
            )
            BotEvent.log(group_id, 'automod_action', {
                'rule': 'link_filter', 'action': link_cfg['action'],
                'user_id': user_id, 'message_preview': message.text[:100]
            })
            return
    
    # CAPS FILTER
    caps_cfg = automod.get('caps_filter', {})
    if caps_cfg.get('enabled'):
        text = message.text
        if len(text) > 10:  # minimum length to avoid false positives
            caps_pct = sum(1 for c in text if c.isupper()) / len(text) * 100
            threshold = caps_cfg.get('threshold_pct', 70)
            if caps_pct > threshold:
                await message.delete()
                await _apply_automod_action(
                    context, message, caps_cfg['action']
                )
                BotEvent.log(group_id, 'automod_action', {
                    'rule': 'caps_filter', 'caps_pct': round(caps_pct),
                    'user_id': user_id
                })

async def _apply_automod_action(context, message, action, warn_delete_seconds=0):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if action == 'warn':
        warn_msg = await context.bot.send_message(
            chat_id, f"⚠️ {message.from_user.mention_html()}, please follow group rules.",
            parse_mode='HTML'
        )
        if warn_delete_seconds > 0:
            asyncio.create_task(_delete_after(context, chat_id,
                                              warn_msg.message_id, warn_delete_seconds))
        # Increment Member.warnings
        Member.increment_warnings(user_id, chat_id)
    
    elif action == 'mute':
        until = datetime.utcnow() + timedelta(hours=1)
        await context.bot.restrict_chat_member(
            chat_id, user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until
        )
    
    elif action == 'ban':
        await context.bot.ban_chat_member(chat_id, user_id)
```

---

## 4.8.1 AutoMod Fallback on Permission Failure

```python
# When bot lacks can_restrict_members, mute action fails.
# Fall back gracefully: warn instead of silently failing.
async def _apply_automod_action(context, message, action, warn_delete_seconds=0):
    # ... existing actions ...
    elif action == 'mute':
        try:
            until = datetime.utcnow() + timedelta(hours=1)
            await context.bot.restrict_chat_member(...)
        except TelegramError as e:
            if 'not enough rights' in str(e).lower():
                # Permission missing — fall back to warn, log the gap
                BotEvent.log(group_id, 'permission_missing', {
                    'required': 'can_restrict_members',
                    'intended_action': 'mute',
                    'fallback': 'warn'
                })
                action = 'warn'  # retry as warn below
            else:
                raise
```

---

## 4.9 Verification System

```python
# on_member_join — triggered by ChatMemberHandler

async def handle_chat_member_update(update, context):
    result = update.chat_member
    if result.new_chat_member.status == 'member':
        # New member joined
        await _handle_new_member(result, context)

async def _handle_new_member(result, context):
    group = TelegramGroup.get_by_telegram_id(result.chat.id)
    if not group:
        return
    
    ver_cfg = group.settings.get('verification', {})
    if not ver_cfg.get('enabled'):
        return
    
    user = result.new_chat_member.user
    group_id = result.chat.id
    
    # 1. Restrict member immediately (no messages until verified)
    await context.bot.restrict_chat_member(
        group_id, user.id,
        ChatPermissions(can_send_messages=False)
    )
    
    # 2. Generate challenge
    ver_type = ver_cfg.get('type', 'button')
    if ver_type == 'math':
        a, b = random.randint(1, 10), random.randint(1, 10)
        challenge_text = f"{a} + {b}"
        answer = str(a + b)
    else:
        challenge_text = None
        answer = None
    
    # 3. Store pending verification in DB (not in-memory)
    timeout = ver_cfg.get('timeout_seconds', 600)
    PendingVerification.create(
        telegram_user_id=user.id,
        group_id=str(group_id),
        challenge_text=challenge_text,
        answer=answer,
        expires_at=datetime.utcnow() + timedelta(seconds=timeout)
    )
    
    # 4. Send challenge
    destination = ver_cfg.get('destination', 'same_group')
    target_chat = (ver_cfg.get('destination_chat_id') or group_id
                   if destination != 'same_group' else group_id)
    
    if ver_type == 'button':
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ I'm human — click to verify",
                callback_data=f"v:verify:{group_id}:{user.id}"
            )
        ]])
        await context.bot.send_message(
            target_chat,
            f"👋 Welcome {user.mention_html()}! Click below to verify yourself.\n"
            f"You have {timeout // 60} minutes.",
            reply_markup=keyboard, parse_mode='HTML'
        )
    else:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                str(i), callback_data=f"v:answer:{group_id}:{user.id}:{i}"
            ) for i in range(max(0, int(answer)-2), int(answer)+3)
        ]])
        await context.bot.send_message(
            target_chat,
            f"👋 Welcome {user.mention_html()}! Solve: {challenge_text} = ?",
            reply_markup=keyboard, parse_mode='HTML'
        )
    
    BotEvent.log(str(group_id), 'verification_started', {'user_id': user.id})

# Callback handler for verification responses
async def _handle_verification_callback(query, group_id, user_id, answer=None):
    pv = PendingVerification.get(user_id, group_id)
    if not pv or pv.expires_at < datetime.utcnow():
        await query.answer("Verification expired. Please rejoin the group.")
        return
    
    correct = (answer is None) or (answer == pv.answer)
    
    if correct:
        # Lift restriction
        await query.bot.restrict_chat_member(
            int(group_id), user_id,
            ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        PendingVerification.delete(user_id, group_id)
        await query.edit_message_text("✅ Verified! Welcome to the group.")
        BotEvent.log(group_id, 'verification_passed', {'user_id': user_id})
    else:
        await query.answer("Wrong answer. Try again.")
        BotEvent.log(group_id, 'verification_failed', {'user_id': user_id, 'reason': 'wrong_answer'})
```

**Verification timeout handling (scheduler job):**
```python
# Every 5 minutes
def expire_pending_verifications():
    expired = PendingVerification.get_expired()
    for pv in expired:
        try:
            # Step 1: Ban (kick with temporary ban)
            bot.ban_chat_member(int(pv.group_id), pv.telegram_user_id)
            
            # Step 2: Unban immediately (makes it a kick, not permanent ban)
            # ⚠️ CRITICAL: If unban fails after ban succeeds, user is permanently banned.
            # We persist the unban intent to pending_unbans BEFORE attempting, so a
            # failure can be retried by retry_pending_unbans() every 15 minutes.
            PendingUnban.create(
                telegram_user_id=pv.telegram_user_id,
                group_id=pv.group_id
            )
            bot.unban_chat_member(int(pv.group_id), pv.telegram_user_id)
            PendingUnban.mark_succeeded(pv.telegram_user_id, pv.group_id)
            
            BotEvent.log(pv.group_id, 'verification_failed', {
                'user_id': pv.telegram_user_id, 'reason': 'timeout'
            })
        except Exception as e:
            logger.warning(f"Failed to kick unverified user {pv.telegram_user_id}: {e}")
            # PendingUnban record persists — retry job will attempt unban again
        finally:
            PendingVerification.delete_by_id(pv.id)


def retry_pending_unbans():
    """Every 15 minutes: retry any failed unban attempts (max 5 retries)."""
    pending = PendingUnban.query.filter_by(unban_succeeded=False)\
        .filter(PendingUnban.unban_attempts < 5).all()
    
    for pu in pending:
        try:
            bot.unban_chat_member(int(pu.group_id), pu.telegram_user_id)
            pu.unban_succeeded = True
            pu.error_message = None
        except Exception as e:
            pu.unban_attempts += 1
            pu.last_attempt_at = datetime.utcnow()
            pu.error_message = str(e)
            if pu.unban_attempts >= 5:
                # Alert admin — user may be permanently banned
                notifications.create_admin_alert(
                    f"PERMANENT BAN RISK: Failed to unban user {pu.telegram_user_id} "
                    f"from group {pu.group_id} after 5 attempts. Manual unban required."
                )
        db.session.commit()
```

---

## 4.10 Scheduled Posting

```python
# ScheduledMessage model:
# { bot_id, group_id, message_text, scheduled_at, repeat_interval (minutes, nullable),
#   pin_message (bool), auto_delete_seconds (nullable), is_active, last_sent_at }

# Scheduler job — every 1 minute
def send_scheduled_messages():
    now = datetime.utcnow()
    due = ScheduledMessage.query.filter(
        ScheduledMessage.scheduled_at <= now,
        ScheduledMessage.is_active == True
    ).with_for_update().all()
    
    for msg in due:
        try:
            sent = bot.send_message(
                chat_id=msg.group_id,
                text=msg.message_text,
                parse_mode='HTML'
            )
            if msg.pin_message:
                bot.pin_chat_message(msg.group_id, sent.message_id, disable_notification=True)
            if msg.auto_delete_seconds:
                asyncio.create_task(_delete_after(bot, msg.group_id,
                                                  sent.message_id, msg.auto_delete_seconds))
            msg.last_sent_at = now
            if msg.repeat_interval:
                msg.scheduled_at = now + timedelta(minutes=msg.repeat_interval)
            else:
                msg.is_active = False  # one-shot
            db.session.commit()
        except Exception as e:
            logger.error(f"Scheduled message failed: {e}")
            Sentry.capture_exception(e)
```

---

## 4.11 Message Buffer (for Digests)

```python
# Messages stored temporarily for digest generation
# MessageBuffer: { group_id, sender_name, content, timestamp }
# Retention: configurable (default 7 days), cleared after digest generated

async def buffer_message(message):
    MessageBuffer.create(
        group_id=str(message.chat.id),
        sender_name=message.from_user.full_name or message.from_user.username,
        content=message.text[:500],  # max 500 chars per message
        timestamp=message.date
    )
    # Throttle: only buffer if < 10,000 messages in buffer for group
    # Prevents unbounded growth in very active groups
```

---

## 4.12 XP & Level System

```python
# On every group message
async def _track_xp(message, group_settings):
    xp_cfg = group_settings.get('levels', {})
    if not xp_cfg.get('enabled'):
        return
    
    xp_per_message = xp_cfg.get('xp_per_message', 1)
    member = Member.get_or_create(message.from_user.id, message.chat.id)
    old_level = member.level
    member.xp += xp_per_message
    
    # Calculate new level (thresholds from group_defaults.py)
    thresholds = xp_cfg.get('thresholds', DEFAULT_LEVEL_THRESHOLDS)
    new_level = _xp_to_level(member.xp, thresholds)
    
    if new_level > old_level:
        member.level = new_level
        if xp_cfg.get('announce_levelups', True):
            await message.reply_text(
                f"🎉 Congratulations {message.from_user.mention_html()}! "
                f"You reached Level {new_level}! 🏆",
                parse_mode='HTML'
            )
        BotEvent.log(str(message.chat.id), 'level_up', {
            'user_id': message.from_user.id, 'new_level': new_level
        })
    
    db.session.commit()
```

---

## 4.13 Bot Error Handling

```python
async def handle_error(update, context):
    error = context.error
    logger.error(f"Bot error: {error}", exc_info=True)
    
    # Capture to Sentry with Telegram context
    with sentry_sdk.push_scope() as scope:
        if update and update.effective_chat:
            scope.set_tag('telegram_chat_id', update.effective_chat.id)
        if update and update.effective_user:
            scope.set_tag('telegram_user_id', update.effective_user.id)
        sentry_sdk.capture_exception(error)
    
    # Don't reply to user for internal errors
    # Exception: network errors are transient — bot will retry automatically
```

---

## 4.14 Custom Bot System

```python
# bot_manager.py — manages per-user custom bot instances
class BotManager:
    _instances: dict[int, Application] = {}  # bot_id → Application
    
    def start_bot(self, bot_record: Bot):
        if bot_record.id in self._instances:
            return  # already running
        
        token = bot_record.get_token()  # Fernet decrypt
        app = ApplicationBuilder().token(token).build()
        _register_handlers(app, scope='custom', bot_id=bot_record.id)
        
        thread = threading.Thread(
            target=app.run_polling,
            kwargs={'drop_pending_updates': True},
            daemon=True
        )
        thread.start()
        self._instances[bot_record.id] = app
    
    def stop_bot(self, bot_id: int):
        if bot_id in self._instances:
            self._instances[bot_id].stop()
            del self._instances[bot_id]
    
    def health_check(self, bot_id: int) -> str:
        if bot_id not in self._instances:
            return 'offline'
        try:
            self._instances[bot_id].bot.get_me()
            return 'healthy'
        except Exception:
            return 'degraded'
```

**Custom bot limits by plan:**
```
Free:       0 custom bots
Pro:        3 custom bots
Enterprise: 50 custom bots
```

---

## 4.15 Forum Group Support

Telegram supergroups can be converted to **forum mode** (`is_forum = True`). In forum mode every message belongs to a **topic** (thread). A message sent without a `message_thread_id` lands in the "General" topic (thread 1). If the bot does not propagate `message_thread_id` through every outbound call, all automated messages pile up in General — breaking topic-scoped moderation and confusing members.

### 4.15.1 Detection & Storage

```sql
-- Migration: add is_forum to telegram_groups
ALTER TABLE telegram_groups ADD COLUMN is_forum BOOLEAN DEFAULT FALSE NOT NULL;
CREATE INDEX idx_tg_is_forum ON telegram_groups(is_forum) WHERE is_forum = TRUE;
```

```python
# On every ChatMemberUpdated or Message event, refresh forum status
async def _sync_group_meta(bot, chat_id: int):
    chat = await bot.get_chat(chat_id)
    group = TelegramGroup.query.filter_by(telegram_group_id=chat_id).first()
    if group:
        group.is_forum = bool(getattr(chat, 'is_forum', False))
        group.title = chat.title
        db.session.commit()
```

Also sync during `/linkgroup` confirmation so the flag is correct from day one.

### 4.15.2 thread_id Propagation Rule

Every outbound bot call that posts to a group **MUST** pass `message_thread_id` when the source message carried one. Create a single utility wrapper so this is never forgotten:

```python
# bot_utils.py
async def send_group_message(
    bot,
    chat_id: int,
    text: str,
    *,
    source_message=None,      # original telegram.Message that triggered this
    thread_id: int | None = None,
    parse_mode: str = 'HTML',
    reply_markup=None,
) -> telegram.Message | None:
    """
    Send a message to a group, preserving forum topic context.
    Pass either source_message (auto-extracts thread_id) or thread_id explicitly.
    """
    effective_thread_id = thread_id
    if source_message is not None and getattr(source_message, 'is_topic_message', False):
        effective_thread_id = source_message.message_thread_id

    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            message_thread_id=effective_thread_id,
            reply_markup=reply_markup,
        )
    except telegram.error.BadRequest as e:
        if 'message thread not found' in str(e).lower():
            # Topic was deleted; fall back to no thread (General)
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        raise
```

**All handlers must use `send_group_message()` instead of calling `bot.send_message()` directly.**

### 4.15.3 Affected Handlers

| Handler | Action required |
|---|---|
| AutoMod warn/mute/ban notification | Pass `source_message` |
| Verification challenge DM → group echo | Pass `source_message` |
| Scheduled post | No thread — posts to General by design |
| Custom command reply | Pass `source_message` |
| XP level-up announcement | Pass `source_message` |
| Welcome message on new member | Pass `ChatMember` update's `message_thread_id` if present |

### 4.15.4 Topic Discovery API

```python
# GET /api/groups/<group_id>/topics
@groups_bp.route('/api/groups/<int:group_id>/topics', methods=['GET'])
@jwt_required()
def get_group_topics(group_id):
    group = _get_group_or_404(group_id)
    if not group.is_forum:
        return jsonify({'success': True, 'data': []})

    # Cache for 5 minutes — topic list rarely changes
    cache_key = f'group_topics:{group.telegram_group_id}'
    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            return jsonify({'success': True, 'data': json.loads(cached)})

    try:
        bot = _get_bot_for_group(group)
        # python-telegram-bot 20.x sync wrapper
        import asyncio
        topics_raw = asyncio.run(bot.get_forum_topics(group.telegram_group_id))
        topics = [
            {'id': t.message_thread_id, 'name': t.name, 'icon_color': t.icon_color}
            for t in (topics_raw.topics if hasattr(topics_raw, 'topics') else [])
        ]
        if redis_client:
            redis_client.setex(cache_key, 300, json.dumps(topics))
        return jsonify({'success': True, 'data': topics})
    except Exception as e:
        logger.warning(f'get_forum_topics failed for group {group_id}: {e}')
        return jsonify({'success': True, 'data': [], 'warning': 'topic list unavailable'})
```

**Dashboard usage:** The scheduled post composer and custom command editor show a "Topic" dropdown populated by this endpoint when `group.is_forum` is `true`.

### 4.15.5 /linkgroup in Forum Groups

When `/linkgroup <code>` is sent inside a forum topic, the bot must:
1. Detect `message.is_topic_message` and store `message.message_thread_id` as `link_thread_id` in the link-code record.
2. Send the confirmation message back into the **same topic** using `send_group_message(source_message=message)`.
3. Persist `is_forum = True` on the group at link time.

---

## 4.16 Bot Message Formatting Standards

All bot messages must use **HTML parse mode exclusively**. Markdown parse mode is deprecated in python-telegram-bot 20.x and produces inconsistent rendering across clients.

### 4.16.1 telegram_format.py Utility

```python
# telegram_format.py — canonical formatting helpers
import html

def escape(text: str) -> str:
    """Escape user-supplied text for safe inclusion in HTML messages."""
    return html.escape(str(text), quote=False)

def bold(text: str) -> str:
    return f'<b>{escape(text)}</b>'

def italic(text: str) -> str:
    return f'<i>{escape(text)}</i>'

def code(text: str) -> str:
    return f'<code>{escape(text)}</code>'

def link(url: str, label: str) -> str:
    """Create a hyperlink. URL is NOT escaped (must be a trusted constant or validated URL)."""
    return f'<a href="{url}">{escape(label)}</a>'

def mono_block(text: str) -> str:
    return f'<pre>{escape(text)}</pre>'

def mention(full_name: str, user_id: int) -> str:
    """Inline mention by user_id (works for users without a username)."""
    return f'<a href="tg://user?id={user_id}">{escape(full_name)}</a>'
```

**Rules:**
- `escape()` is mandatory for any user-supplied string (usernames, group titles, command responses, AI output injected into templates).
- URLs passed to `link()` must be a known constant or validated against an allowlist — never pass raw user input as a URL.
- Do **not** mix Markdown syntax characters (`*`, `_`, `` ` ``) inside HTML messages.

### 4.16.2 Parse Mode Policy

```python
# Every send_group_message and bot.send_message call
await bot.send_message(
    chat_id=chat_id,
    text=message_text,
    parse_mode='HTML',          # always HTML, never ParseMode.MARKDOWN
    ...
)
```

Set this as the default in `send_group_message()` (Section 4.15.2) so it propagates automatically.

### 4.16.3 Message Length Management

Telegram hard limit: **4096 characters** per message.

```python
MAX_MESSAGE_LENGTH = 4096
SAFE_MESSAGE_LENGTH = 3800   # leave room for appended metadata

def split_long_message(text: str, max_len: int = SAFE_MESSAGE_LENGTH) -> list[str]:
    """Split at newline boundaries; never cut mid-word."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind('\n', 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip('\n')
    return chunks
```

AI-generated digests and scheduled posts **must** run through `split_long_message()` before sending.

### 4.16.4 Entity-Based Link Detection for AutoMod

Do **not** use regex to detect links in message text. Telegram parses all entities server-side and passes them in `message.entities`. This is the correct source of truth:

```python
from telegram import MessageEntityType

def message_contains_link(message) -> bool:
    """Return True if message contains any hyperlink or URL entity."""
    if not message.entities:
        return False
    link_types = {
        MessageEntityType.URL,
        MessageEntityType.TEXT_LINK,
        MessageEntityType.MENTION,      # @username links to a profile
    }
    return any(e.type in link_types for e in message.entities)

def extract_urls(message) -> list[str]:
    """Extract all raw URLs from a message using entity data."""
    urls = []
    for entity in (message.entities or []):
        if entity.type == MessageEntityType.URL:
            urls.append(message.text[entity.offset : entity.offset + entity.length])
        elif entity.type == MessageEntityType.TEXT_LINK:
            urls.append(entity.url)
    return urls
```

AutoMod's link-blocking rule (Section 4.8) **must** use `message_contains_link()` instead of any regex.

### 4.16.5 Inline Keyboard Layout Rules

- Maximum **3 buttons per row** for readability on mobile.
- Verification challenge answers: always a single row of `[A] [B] [C] [D]` (4 options max).
- Each button label ≤ 24 characters.
- Callback data format: `action:entity_id:optional_param` (colon-delimited, ≤ 64 bytes total).

```python
# Example: verification keyboard
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def build_verification_keyboard(options: list[str], pv_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=opt, callback_data=f'verify:{pv_id}:{i}')
        for i, opt in enumerate(options)
    ]
    # All options on one row (max 4)
    return InlineKeyboardMarkup([buttons])
```

---

## 4.17 Custom Bot Identity & Onboarding

Every custom bot deployed by a Telegizer user must present a coherent, branded identity to end-users. On startup, the bot sets its own description and command menu via the Bot API. In DMs, it sends a structured welcome that lists features and names the owner.

### 4.17.1 Bot Startup Identity Registration

```python
# Called once when a custom bot starts — BotManager.start_bot()
async def _register_bot_identity(bot, owner_display_name: str):
    """Set description, short description, and command menu for a custom bot."""
    try:
        await bot.set_my_description(
            description=(
                f"This bot is powered by Telegizer and managed by {owner_display_name}.\n\n"
                "Features:\n"
                "• Automated member verification\n"
                "• AutoMod (spam, links, caps filtering)\n"
                "• Scheduled announcements\n"
                "• XP & level-up rewards\n"
                "• AI-powered community digest\n\n"
                "Use /help to see available commands."
            )
        )
        await bot.set_my_short_description(
            short_description=f"Telegizer-powered community bot by {owner_display_name}"
        )
        await bot.set_my_commands([
            BotCommand('start',  'Welcome & bot info'),
            BotCommand('help',   'List all commands'),
            BotCommand('status', 'Your membership status'),
            BotCommand('verify', 'Complete verification'),
        ])
    except Exception as e:
        logger.warning(f'Bot identity registration failed: {e}')
```

Call `_register_bot_identity()` inside `BotManager.start_bot()` after the application is built but before `run_polling()`:

```python
async def _post_init(application):
    owner = User.query.get(bot_record.owner_user_id)
    display_name = owner.display_name or owner.email.split('@')[0]
    await _register_bot_identity(application.bot, display_name)

app = ApplicationBuilder().token(token).post_init(_post_init).build()
```

### 4.17.2 /start Command — DM Response

When a user starts the custom bot in a private chat:

```python
async def cmd_start_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    owner_name = context.bot_data.get('owner_display_name', 'the community owner')

    text = (
        f"👋 Hi {escape(user.first_name)}!\n\n"
        f"This bot is managed by <b>{escape(owner_name)}</b> using "
        f'<a href="https://telegizer.com">Telegizer</a>.\n\n'
        "<b>What I can do:</b>\n"
        "• Verify new members before they can post\n"
        "• Filter spam, links, and excessive caps automatically\n"
        "• Send scheduled announcements to your group\n"
        "• Reward active members with XP and levels\n"
        "• Generate AI summaries of community activity\n\n"
        "Use /help for a full command list, or join a linked group to get started."
    )
    await update.message.reply_text(text, parse_mode='HTML', disable_web_page_preview=True)
```

**Rules:**
- Always include the Telegizer attribution link (`https://telegizer.com`).
- Owner name comes from `User.display_name` (falls back to email prefix).
- `disable_web_page_preview=True` to avoid URL previews in the welcome message.

### 4.17.3 /help Command

```python
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>Available Commands</b>\n\n"
        "/start — Welcome message and bot info\n"
        "/help — This list\n"
        "/status — See your verification and XP status\n"
        "/verify — Retry verification if you were not approved\n\n"
        "<b>Automatic Features</b>\n"
        "• New member verification challenge\n"
        "• AutoMod: link blocking, spam detection, caps limit\n"
        "• XP rewards for messages; level-up announcements\n"
        "• Scheduled group announcements\n\n"
        f'Powered by <a href="https://telegizer.com">Telegizer</a>.'
    )
    await update.message.reply_text(text, parse_mode='HTML', disable_web_page_preview=True)
```

### 4.17.4 Token Validation — Lightweight httpx Approach

**Do not** call `ApplicationBuilder().token(token).build()` just to validate a token — this constructs a full Application object (opens connections, starts job queues) which is wasteful and slow.

Use a direct `httpx` call to `getMe` instead:

```python
import httpx

async def validate_bot_token(token: str) -> dict | None:
    """
    Returns bot info dict on success, None on invalid token.
    Raises httpx.TimeoutException on network timeout.
    """
    url = f'https://api.telegram.org/bot{token}/getMe'
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
    if resp.status_code == 200:
        data = resp.json()
        if data.get('ok'):
            return data['result']  # {id, first_name, username, ...}
    return None
```

**API endpoint — validate before save:**

```python
# POST /api/bots/validate-token
@bots_bp.route('/api/bots/validate-token', methods=['POST'])
@jwt_required()
def validate_token():
    token = request.json.get('token', '').strip()
    if not token:
        return jsonify({'success': False, 'error': 'Token required'}), 400

    import asyncio
    try:
        bot_info = asyncio.run(validate_bot_token(token))
    except httpx.TimeoutException:
        return jsonify({'success': False, 'error': 'Telegram API timeout — try again'}), 504

    if bot_info is None:
        return jsonify({'success': False, 'error': 'Invalid token — bot not found'}), 422

    return jsonify({'success': True, 'data': {
        'bot_id':   bot_info['id'],
        'username': bot_info.get('username'),
        'name':     bot_info.get('first_name'),
    }})
```

**Frontend two-step flow:**
1. User pastes token → call `POST /api/bots/validate-token`.
2. On success, display bot username/name as a confirmation preview.
3. User clicks "Save Bot" → call `POST /api/bots` with the token.
4. **Never clear the token field on a validation error** — show an inline error below the field so the user can correct their paste without re-typing.
5. Token input must use `type="text"` (not `type="password"`) so the user can visually verify the value.

---

# 5. AI ASSISTANT SYSTEM

## 5.1 Architecture Overview

The AI Assistant is Telegizer's key product differentiator. It transforms the platform from a passive management dashboard into an **active community co-pilot** that:

- **Observes** group conversations continuously
- **Extracts** meaningful signals (decisions, tasks, links, questions)
- **Summarizes** daily activity in structured Digests
- **Responds** to user intents in private DMs
- **Reminds** users of things they asked to be reminded about
- **Suggests** actions based on group patterns

The assistant is **never shallow**. It doesn't say "I don't understand." It routes every private message through an intent detection layer and produces a useful response or takes a concrete action.

---

## 5.2 AI Key Resolver (Two-Tier Model)

```python
# backend/assistant/ai_key_resolver.py

def get_workspace_ai_key(user) -> dict:
    """
    Priority: 
      1. User's workspace-scoped API key (UserApiKey.scope='workspace')
      2. Platform Gemini key (PLATFORM_GEMINI_API_KEY env var)
    
    Returns: { provider, api_key, model, is_platform_key }
    """
    # Check workspace key
    user_key = UserApiKey.query.filter_by(
        user_id=user.id,
        scope='workspace'
    ).first()
    
    if user_key:
        return {
            'provider': user_key.provider,
            'api_key': user_key.get_key(),  # Fernet decrypt
            'model': user_key.model or _default_model(user_key.provider),
            'is_platform_key': False,
        }
    
    # Check token quota if using platform key
    _check_and_enforce_quota(user)
    
    return {
        'provider': 'gemini',
        'api_key': config.PLATFORM_GEMINI_API_KEY,
        'model': 'gemini-2.0-flash',
        'is_platform_key': True,
    }


def get_group_ai_key(user, group_id) -> dict:
    """
    Priority:
      1. Group-scoped API key (UserApiKey.scope='group', group_id matches)
      2. Workspace AI key (via get_workspace_ai_key)
    """
    group_key = UserApiKey.query.filter_by(
        user_id=user.id,
        scope='group',
        group_id=group_id
    ).first()
    
    if group_key:
        return {
            'provider': group_key.provider,
            'api_key': group_key.get_key(),
            'model': group_key.model or _default_model(group_key.provider),
            'is_platform_key': False,
        }
    
    return get_workspace_ai_key(user)


def record_token_usage(user, tokens_used: int):
    """Called after every AI API call using the platform key."""
    user.workspace_ai_tokens_today = (user.workspace_ai_tokens_today or 0) + tokens_used
    db.session.commit()


def _check_and_enforce_quota(user):
    """
    ⚠️ RACE CONDITION FIX: The original read-then-write pattern allows concurrent
    requests to both pass the quota check before either increments the counter.
    This is fixed by using Redis atomic increment (INCR) as the authoritative
    counter, with the DB value used only for display/persistence.
    
    Redis key: ai_quota:{user_id}:{YYYY-MM-DD}
    TTL: 86400 seconds (expires at end of day UTC)
    """
    limit = _get_token_limit(user.subscription_tier)
    today = datetime.utcnow().strftime('%Y-%m-%d')
    quota_key = f"ai_quota:{user.id}:{today}"
    
    if redis_client:
        # Atomic quota check: INCR returns new value, EXPIRE sets TTL on first use
        # Pipeline ensures atomicity — increment only if under limit
        pipe = redis_client.pipeline()
        pipe.incr(quota_key)
        pipe.expire(quota_key, 86400)
        new_value, _ = pipe.execute()
        
        if new_value > limit:
            redis_client.decr(quota_key)  # rollback — don't count refused requests
            raise QuotaExceededError(
                f"Daily AI token quota reached ({limit} tokens). "
                f"{'Upgrade to Pro for 500k tokens/day.' if user.subscription_tier == 'free' else 'Add your own API key for unlimited usage.'}"
            )
    else:
        # Redis unavailable: fall back to DB check (approximate, non-atomic)
        if (user.workspace_ai_tokens_today or 0) >= limit:
            raise QuotaExceededError(
                f"Daily AI token quota reached ({limit} tokens)."
            )


def _get_token_limit(tier: str) -> int:
    return {'free': 10_000, 'pro': 500_000, 'enterprise': 500_000}.get(tier, 10_000)
```

---

## 5.3 Digest Generation System

```python
# backend/assistant/digest_ai.py

DIGEST_PROMPT = """You are a community intelligence assistant. 
Analyze these Telegram group messages and generate a structured daily digest.

Return JSON only, no markdown:
{
  "summary": "2-3 sentence overview of what happened today",
  "highlights": [
    { "type": "decision|task|event|discussion", "text": "...", "participants": ["name"] }
  ],
  "action_items": [
    { "owner": "person name or 'unclear'", "task": "what needs to be done", "deadline": "date or null" }
  ],
  "key_links": [
    { "url": "...", "description": "..." }
  ],
  "sentiment": "positive|neutral|negative|mixed",
  "activity_level": "high|medium|low",
  "notable_members": ["name — reason they were notable today"]
}

If any section is empty, return an empty array.
Be concise. Use plain English. Max 5 items per array.

Messages (format: [TIME] SENDER: MESSAGE):
{messages}
"""

def generate_digest(group: TelegramGroup, user) -> dict:
    # 1. Fetch recent messages from buffer
    since = datetime.utcnow() - timedelta(hours=24)
    messages = MessageBuffer.query.filter(
        MessageBuffer.group_id == str(group.telegram_group_id),
        MessageBuffer.timestamp >= since
    ).order_by(MessageBuffer.timestamp).all()
    
    if not messages:
        return {'error': 'no_messages', 'message': 'No messages in the last 24 hours.'}
    
    if len(messages) > 500:
        messages = messages[-500:]  # last 500 messages max
    
    # 2. Format messages
    formatted = '\n'.join(
        f"[{msg.timestamp.strftime('%H:%M')}] {msg.sender_name}: {msg.content}"
        for msg in messages
    )
    
    # 3. Get AI key
    ai_config = get_group_ai_key(user, group.id)
    
    # 4. Call AI provider
    try:
        response_text, tokens_used = _call_ai_provider(
            ai_config,
            DIGEST_PROMPT.format(messages=formatted)
        )
        
        # 5. Record token usage if platform key
        if ai_config['is_platform_key']:
            record_token_usage(user, tokens_used)
        
        # 6. Parse JSON response
        digest_data = json.loads(response_text)
        
        # 7. Log to DigestLog
        DigestLog.create(
            group_id=str(group.telegram_group_id),
            user_id=user.id,
            content_preview=digest_data.get('summary', '')[:200],
            provider=ai_config['provider'],
            tokens_used=tokens_used,
            sent_at=datetime.utcnow()
        )
        
        return digest_data
    
    except QuotaExceededError:
        raise
    except json.JSONDecodeError:
        logger.error(f"Digest AI returned invalid JSON for group {group.id}")
        raise DigestParseError("AI returned malformed response")
    except Exception as e:
        logger.error(f"Digest generation failed: {e}")
        Sentry.capture_exception(e)
        raise


def deliver_digest(group: TelegramGroup, digest_data: dict, delivery_config: dict):
    """Deliver digest via bot DM or group topic."""
    formatted = _format_digest_for_telegram(digest_data)
    
    delivery = delivery_config.get('delivery', 'owner_dm')
    
    if delivery == 'owner_dm':
        owner = User.get(group.owner_user_id)
        tg_account = UserTelegramAccount.get_primary(owner.id)
        if tg_account:
            bot.send_message(chat_id=tg_account.telegram_id, text=formatted, parse_mode='HTML')
    
    elif delivery == 'group_topic':
        topic_id = delivery_config.get('group_topic_id')
        bot.send_message(
            chat_id=group.telegram_group_id,
            text=formatted,
            message_thread_id=topic_id,
            parse_mode='HTML'
        )
    
    elif delivery == 'group':
        bot.send_message(
            chat_id=group.telegram_group_id,
            text=formatted,
            parse_mode='HTML'
        )
```

---

## 5.4 Notes Extraction System

```python
# POST /api/notes/generate/:group_id

NOTES_EXTRACTION_PROMPT = """You are a smart meeting assistant. 
Extract structured notes from these Telegram group messages.

Return JSON only:
{
  "decisions": ["A specific decision that was made..."],
  "tasks": ["person: action item by date (or 'no deadline')"],
  "links": ["https://url.com — what this link is about"],
  "questions": ["An open question that was raised but not answered"]
}

Rules:
- Only include items that are explicitly present in the messages
- If a category has no items, return empty array
- Be specific and actionable, not vague
- Max 5 items per category
- For tasks, identify the responsible person if mentioned

Messages:
{messages}
"""

def generate_notes_from_group(group_id: str, user) -> list[Note]:
    messages = MessageBuffer.query.filter_by(
        group_id=group_id
    ).order_by(MessageBuffer.timestamp.desc()).limit(200).all()
    
    formatted = '\n'.join(
        f"[{m.timestamp.strftime('%H:%M')}] {m.sender_name}: {m.content}"
        for m in reversed(messages)
    )
    
    ai_config = get_workspace_ai_key(user)
    response_text, tokens_used = _call_ai_provider(
        ai_config,
        NOTES_EXTRACTION_PROMPT.format(messages=formatted)
    )
    
    if ai_config['is_platform_key']:
        record_token_usage(user, tokens_used)
    
    extracted = json.loads(response_text)
    
    # Create one Note per non-empty category
    created_notes = []
    group = TelegramGroup.query.filter_by(
        telegram_group_id=int(group_id)
    ).first()
    
    tag_map = {
        'decisions': 'decision',
        'tasks': 'task',
        'links': 'link',
        'questions': 'question'
    }
    
    for category, items in extracted.items():
        if items:
            note = Note.create(
                user_id=user.id,
                group_id=group_id,
                group_title=group.title if group else None,
                content='\n'.join(f"• {item}" for item in items),
                source='ai',
                tags=[tag_map.get(category, category)]
            )
            created_notes.append(note)
    
    return created_notes
```

---

## 5.5 Smart Reminder System

```python
# backend/assistant/handlers/reminder.py

# Intent patterns (regex)
REMINDER_PATTERNS = [
    r'remind me (to |about )?(.+?)(?:\s+(?:at|on|tomorrow|in)\s+(.+))?$',
    r'set (?:a )?reminder (?:to |for |about )?(.+)',
    r"don'?t let me forget (?:to )?(.+)",
    r'reminder[:\s]+(.+)',
]

def detect_reminder_intent(text: str) -> dict | None:
    text_lower = text.lower().strip()
    for pattern in REMINDER_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            subject = (match.group(2) or match.group(1) or '').strip()
            time_hint = (match.group(3) if match.lastindex >= 3 else '').strip()
            return {'subject': subject, 'time_hint': time_hint}
    return None


def handle_reminder_intent(user, subject: str, time_hint: str = '') -> dict:
    """
    Generate time suggestions and create PendingReminderState.
    Returns: { message, keyboard } for bot to send.
    """
    now = datetime.now(user.get_timezone())
    suggestions = _generate_time_suggestions(now, time_hint)
    
    # Store pending state
    PendingReminderState.upsert(
        user_id=user.id,
        subject=subject,
        suggested_times=[t.isoformat() for t in suggestions],
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    
    # Build inline keyboard
    keyboard_rows = []
    # Row 1: time suggestions (max 3 per row)
    time_buttons = [
        InlineKeyboardButton(
            _format_time_label(t, now),
            callback_data=f"r:time:{i}"
        )
        for i, t in enumerate(suggestions[:3])
    ]
    keyboard_rows.append(time_buttons)
    # Custom option
    keyboard_rows.append([
        InlineKeyboardButton("⏰ Custom time...", callback_data="r:custom")
    ])
    
    return {
        'message': (
            f"📝 I'll remind you: <b>{subject}</b>\n\n"
            f"<b>When should I remind you?</b>"
        ),
        'keyboard': InlineKeyboardMarkup(keyboard_rows),
    }


def _generate_time_suggestions(now, time_hint: str) -> list[datetime]:
    """Parse natural language time hint + generate 3 smart suggestions."""
    suggestions = []
    
    if 'tomorrow' in time_hint:
        base = now.replace(hour=9, minute=0, second=0) + timedelta(days=1)
    elif 'tonight' in time_hint or 'evening' in time_hint:
        base = now.replace(hour=19, minute=0, second=0)
    elif re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)', time_hint):
        base = _parse_time_expression(time_hint, now)
    elif 'in' in time_hint and re.search(r'\d+\s*(hour|min)', time_hint):
        base = _parse_relative_time(time_hint, now)
    else:
        # Default: next hour, +30min, +2hr
        base = now.replace(minute=0, second=0) + timedelta(hours=1)
    
    suggestions = [
        base,
        base - timedelta(minutes=15),
        base - timedelta(minutes=30),
    ]
    return [s for s in suggestions if s > now]


def handle_frequency_selection(user, time: datetime, frequency: str) -> None:
    """Create WorkspaceReminder records based on frequency selection."""
    state = PendingReminderState.get_by_user(user.id)
    if not state:
        return
    
    reminder_times = []
    if frequency == 'once':
        reminder_times = [time]
    elif frequency == '2x':
        reminder_times = [time - timedelta(minutes=15), time]
    elif frequency == '3x':
        reminder_times = [
            time - timedelta(minutes=30),
            time - timedelta(minutes=15),
            time
        ]
    
    for t in reminder_times:
        WorkspaceReminder.create(
            user_id=user.id,
            text=state.subject,
            remind_at=t
        )
    
    PendingReminderState.delete_by_user(user.id)
```

---

## 5.6 Live Chat Mirror (SSE)

### SSE Token Authentication

> **⚠️ Security Note:** `EventSource` does not support custom headers. Passing the JWT as a query parameter (`?token=<jwt>`) causes the full token to appear in Railway access logs, browser history, and Sentry breadcrumbs — enabling token theft from logs. The solution is a short-lived, single-use SSE nonce separate from the main JWT.

```python
# POST /api/assistant/sse-token
# Issue a short-lived nonce specifically for SSE authentication
# The nonce is stored in Redis with a 60-second TTL

@assistant_bp.route('/api/assistant/sse-token', methods=['POST'])
@jwt_required()
def get_sse_token():
    user_id = get_jwt_identity()
    nonce = secrets.token_hex(24)
    redis_client.setex(f'sse_nonce:{nonce}', 60, str(user_id))  # 60s TTL, single-use
    return jsonify({'success': True, 'data': {'nonce': nonce, 'expires_in': 60}})
```

### SSE Stream Endpoint

> **⚠️ Connection Pool Warning:** An SSE endpoint implemented as a synchronous generator holds a SQLAlchemy DB connection open for every connected user. With `pool_size=5` per Gunicorn worker and 2 workers, this exhausts all connections at 10 simultaneous SSE users. The implementation below releases and re-acquires the session between polls to prevent pool exhaustion.

```python
# GET /api/assistant/dm-stream?nonce=<nonce>
# Server-Sent Events endpoint — streams new BotDMMessages to frontend
# Auth: short-lived nonce (not JWT) to prevent token exposure in logs

@assistant_bp.route('/api/assistant/dm-stream')
def dm_stream():
    nonce = request.args.get('nonce', '')
    if not nonce:
        return jsonify({'success': False, 'error': {'code': 'UNAUTHORIZED'}}), 401
    
    # Validate nonce (single-use: delete immediately on validation)
    user_id_bytes = redis_client.getdel(f'sse_nonce:{nonce}')
    if not user_id_bytes:
        return jsonify({'success': False, 'error': {'code': 'UNAUTHORIZED',
                        'message': 'Invalid or expired SSE token.'}}), 401
    user_id = int(user_id_bytes)
    
    def event_stream():
        last_id = request.args.get('last_id', 0, type=int)
        
        while True:
            # CRITICAL: Acquire a fresh session per poll, release immediately after.
            # Never hold a DB session across the sleep — this exhausts the connection pool.
            try:
                with db.engine.connect() as conn:
                    rows = conn.execute(
                        text("""SELECT id, direction, content, intent, created_at
                                FROM bot_dm_messages
                                WHERE user_id = :uid AND id > :last_id
                                ORDER BY id ASC LIMIT 20"""),
                        {'uid': user_id, 'last_id': last_id}
                    ).fetchall()
                
                for row in rows:
                    data = json.dumps({
                        'id': row.id,
                        'direction': row.direction,
                        'content': row.content,
                        'intent': row.intent,
                        'created_at': row.created_at.isoformat(),
                    })
                    yield f"data: {data}\n\n"
                    last_id = row.id
                
                # Send heartbeat every 30s to keep connection alive through proxies
                yield f": heartbeat\n\n"
                
            except Exception as e:
                logger.error(f"SSE stream error for user {user_id}: {e}")
                yield f"event: error\ndata: {json.dumps({'message': 'stream_error'})}\n\n"
            
            time.sleep(2)  # poll interval — 2s is acceptable for DM mirror UX
    
    return Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # disable Nginx buffering
            'Connection': 'keep-alive',
        }
    )
```

```javascript
// Frontend: SSE hook with proper reconnection and nonce-based auth
// Uses @microsoft/fetch-event-source for header support and auto-reconnect

import { fetchEventSource } from '@microsoft/fetch-event-source';

const useDMStream = (onMessage) => {
  const lastIdRef = useRef(0);
  const abortRef = useRef(null);
  
  const connect = useCallback(async () => {
    // Step 1: Get a short-lived nonce (valid 60s, single-use)
    try {
      const { data } = await api.post('/api/assistant/sse-token');
      const nonce = data.nonce;
      
      // Step 2: Open SSE stream with nonce (NOT the JWT)
      abortRef.current = new AbortController();
      
      await fetchEventSource(
        `${API_URL}/api/assistant/dm-stream?nonce=${nonce}&last_id=${lastIdRef.current}`,
        {
          signal: abortRef.current.signal,
          onmessage(event) {
            if (event.data) {
              const msg = JSON.parse(event.data);
              lastIdRef.current = msg.id;
              onMessage(msg);
            }
          },
          onerror(err) {
            // fetchEventSource auto-retries on error — no manual reconnect needed
            logger.warn('SSE error, retrying:', err);
          },
          // Reconnect on network loss: fetchEventSource handles this automatically
          openWhenHidden: false,  // pause when tab hidden (saves connections)
        }
      );
    } catch (err) {
      // Token fetch failed (401 = logged out) — don't reconnect
      logger.error('SSE connect failed:', err);
    }
  }, [onMessage]);
  
  useEffect(() => {
    connect();
    return () => abortRef.current?.abort();
  }, [connect]);
};
```

### Future: Redis Pub/Sub SSE (Phase 2)

The current SSE implementation polls the DB every 2 seconds. At 500 concurrent users, this generates 15,000 DB queries/minute purely for live chat. The Phase 2 upgrade replaces DB polling with Redis pub/sub:

```python
# Phase 2 target architecture:
# Bot writes new DMs to Redis channel: redis.publish(f"dm:{user_id}", json_payload)
# SSE subscribes: pubsub = redis.pubsub(); pubsub.subscribe(f"dm:{user_id}")
# This reduces SSE load from O(users × poll_rate) to O(new_messages)
```

---

## 5.7 Group Intelligence & Signal Extraction

```python
# backend/assistant/group_signal_extractor.py
# Runs periodically or on-demand to surface patterns in group activity

SIGNAL_EXTRACTION_PROMPT = """Analyze these Telegram group messages and identify:
1. Recurring discussion topics this week
2. Members who are most active and positive
3. Any concerning patterns (spam, conflict, off-topic drift)
4. Opportunities for the community (events, collaborations, content)

Return JSON:
{
  "topics": [{ "name": str, "frequency": int, "sentiment": str }],
  "top_members": [{ "name": str, "reason": str }],
  "concerns": [{ "type": str, "description": str, "severity": "low|medium|high" }],
  "opportunities": [str]
}"""

# Used by:
# - POST /api/notes/generate/:group_id (extract structured notes)
# - GET /api/assistant/hub-summary (surface concerns/opportunities on Hub)
# - Future: proactive push notification when high-severity concern detected
```

---

## 5.8 Proactive Suggestions Engine

```python
# backend/assistant/suggestion_engine.py
# Generates suggestions shown on the Assistant Hub

def get_hub_suggestions(user) -> list[dict]:
    """
    Returns list of actionable suggestions for the Assistant Hub.
    Based on real data, not static tips.
    """
    suggestions = []
    groups = TelegramGroup.query.filter_by(owner_user_id=user.id).all()
    
    for group in groups:
        # Check if digest is disabled but group is active
        digest_cfg = group.settings.get('digest', {})
        if not digest_cfg.get('enabled') and _group_is_active(group):
            suggestions.append({
                'type': 'setup',
                'icon': 'Summarize',
                'title': f'Enable Digests for {group.title}',
                'body': 'This group has active messages but no digest configured.',
                'action': f'/workspace/digests',
                'group_id': group.id,
            })
        
        # Check if verification is disabled and group is large
        ver_cfg = group.settings.get('verification', {})
        if not ver_cfg.get('enabled') and group.member_count > 100:
            suggestions.append({
                'type': 'security',
                'icon': 'Shield',
                'title': f'Add Member Verification to {group.title}',
                'body': f'Groups over 100 members are common spam targets.',
                'action': f'/groups/{group.id}',
                'group_id': group.id,
            })
        
        # Check for groups with no auto-replies set
        if not group.settings.get('auto_replies'):
            suggestions.append({
                'type': 'automation',
                'icon': 'Reply',
                'title': f'Add Auto-Replies to {group.title}',
                'body': 'Answer common questions automatically.',
                'action': '/workspace/smart-links',
            })
    
    # Check AI token usage
    if user.subscription_tier == 'free':
        usage_pct = (user.workspace_ai_tokens_today or 0) / 10_000 * 100
        if usage_pct > 80:
            suggestions.append({
                'type': 'upgrade',
                'icon': 'Upgrade',
                'title': 'Running low on AI tokens',
                'body': f'Used {round(usage_pct)}% of daily free quota. Upgrade to Pro for 50x more.',
                'action': '/billing',
            })
    
    return suggestions[:5]  # max 5 suggestions on Hub
```

---

## 5.9 AI Settings Page Specification

```
GET /api/workspace/ai-settings
Response:
{
  "platform": {
    "provider": "gemini",
    "model": "gemini-2.0-flash",
    "status": "active|quota_exceeded|unavailable",
    "tokens_used_today": 12430,
    "tokens_limit_today": 50000,
    "resets_at": "2026-05-09T00:00:00Z"
  },
  "user_key": {
    "provider": "openai",
    "model": "gpt-4o",
    "masked_key": "sk-...xxxx",
    "is_active": true
  } | null,
  "telegram_connected": {
    "telegram_id": 123456789,
    "username": "johndoe",
    "first_name": "John"
  } | null
}
```

**UI layout:**

```
Platform AI — Powered by Telegizer
  Google Gemini Flash 2.0
  Status: ● Active
  Today: ████████░░ 12,430 / 50,000 tokens
  [Resets in 11 hours]
  ↳ Free tier. Upgrade to Pro for 500k/day.

Your API Key — Optional
  [Gemini] [OpenAI] [Anthropic] [OpenRouter] [Custom]
  API Key: [••••••••••••••••] [Show] [Test] [Save]
  Model:   [gpt-4o ▾]
  "Bypasses platform key for all Assistant features"
  [Remove Key]  ← only if key exists

Telegram Account
  Status: ● Connected as @johndoe
  "Your bot can send you DMs and reminders"
  [Disconnect]
  ─── OR ───
  Status: ○ Not connected
  "Connect to unlock Smart Reminders, Live Chat, and DM notifications"
  [Connect via @TelegizerBot →]
```

---

# 6. DATABASE SPECIFICATION

## 6.1 Schema Design Principles

1. **JSONB for flexible settings** — group settings, bot permissions, notification data, and AI key configs use JSONB. This allows schema evolution without migrations for nested config.
2. **FK indexes on everything** — all foreign keys have explicit indexes (added in audit P1-08).
3. **Encryption at rest for secrets** — bot tokens, TOTP secrets, API keys encrypted via Fernet before storage.
4. **Soft delete for users only** — user records need a grace period. All other deletions are hard.
5. **90-day BotEvent retention** — high-volume event table purged by daily cron.

---

## 6.2 Complete Table Definitions

```sql
-- ============================================================
-- IDENTITY & AUTH
-- ============================================================

CREATE TABLE users (
    id                          SERIAL PRIMARY KEY,
    email                       VARCHAR(255) UNIQUE NOT NULL,
    password_hash               VARCHAR(255) NOT NULL,
    full_name                   VARCHAR(200),
    email_verified              BOOLEAN DEFAULT FALSE NOT NULL,
    subscription_tier           VARCHAR(20) DEFAULT 'free' NOT NULL,
                                -- values: free | pro | enterprise
    subscription_interval       VARCHAR(10),    -- monthly | annual | NULL (free)
    subscription_expires_at     TIMESTAMP,      -- NULL = free tier (no expiry)
    subscription_grace_until    TIMESTAMP,      -- 7-day grace period after expiry
    -- ⚠️ CRITICAL: subscription_expires_at MUST be set on every payment and checked
    -- by the daily downgrade cron. NOWPayments is one-time only — no auto-renewal.
    referral_code               VARCHAR(20) UNIQUE,
    is_admin                    BOOLEAN DEFAULT FALSE NOT NULL,
    totp_enabled                BOOLEAN DEFAULT FALSE NOT NULL,
    totp_secret                 TEXT,           -- Fernet encrypted
    totp_backup_codes           TEXT,           -- Fernet encrypted JSON
    timezone                    VARCHAR(50) DEFAULT 'UTC' NOT NULL,
    workspace_ai_tokens_today   INTEGER DEFAULT 0,
    workspace_ai_tokens_reset_at TIMESTAMP,
    failed_login_attempts       INTEGER DEFAULT 0,
    locked_until                TIMESTAMP,
    email_preferences           JSONB DEFAULT '{"marketing": true, "product": true, "billing": true}' NOT NULL,
    deleted_at                  TIMESTAMP,      -- soft delete
    created_at                  TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at                  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_referral_code ON users(referral_code);
CREATE INDEX idx_users_deleted_at ON users(deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX idx_users_subscription_expires_at ON users(subscription_expires_at)
    WHERE subscription_expires_at IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE user_telegram_accounts (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    telegram_id         BIGINT NOT NULL,
    telegram_username   VARCHAR(100),
    telegram_first_name VARCHAR(200),
    is_primary          BOOLEAN DEFAULT TRUE NOT NULL,
    connected_at        TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_uta_user_id ON user_telegram_accounts(user_id);
CREATE INDEX idx_uta_telegram_id ON user_telegram_accounts(telegram_id);
CREATE UNIQUE INDEX idx_uta_unique ON user_telegram_accounts(user_id, telegram_id);

CREATE TABLE telegram_bot_started (
    id          SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    recorded_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE TABLE revoked_tokens (
    id          SERIAL PRIMARY KEY,
    jti         VARCHAR(255) UNIQUE NOT NULL,
    token_type  VARCHAR(10) NOT NULL,   -- access | refresh
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMP NOT NULL,
    revoked_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_revoked_jti ON revoked_tokens(jti);
CREATE INDEX idx_revoked_user_id ON revoked_tokens(user_id);

CREATE TABLE password_reset_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    token_hash  VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256 of raw token
    expires_at  TIMESTAMP NOT NULL,
    used        BOOLEAN DEFAULT FALSE NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_prt_user_id ON password_reset_tokens(user_id);
CREATE INDEX idx_prt_token_hash ON password_reset_tokens(token_hash);

-- ============================================================
-- BOTS & GROUPS
-- ============================================================

CREATE TABLE bots (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    bot_token       TEXT NOT NULL,          -- Fernet encrypted
    username        VARCHAR(100),
    display_name    VARCHAR(200),
    health_status   VARCHAR(20) DEFAULT 'unknown',  -- healthy|degraded|offline|unknown
    is_active       BOOLEAN DEFAULT TRUE NOT NULL,
    last_active_at  TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_bots_user_id ON bots(user_id);

CREATE TABLE groups (
    id                  SERIAL PRIMARY KEY,
    bot_id              INTEGER REFERENCES bots(id) ON DELETE CASCADE NOT NULL,
    telegram_group_id   BIGINT NOT NULL,
    title               VARCHAR(300),
    member_count        INTEGER DEFAULT 0,
    settings            JSONB DEFAULT '{}' NOT NULL,
    timezone            VARCHAR(50) DEFAULT 'UTC',
    created_at          TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(bot_id, telegram_group_id)
);
CREATE INDEX idx_groups_bot_id ON groups(bot_id);

CREATE TABLE telegram_groups (
    id                  SERIAL PRIMARY KEY,
    owner_user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    telegram_group_id   BIGINT UNIQUE NOT NULL,
    title               VARCHAR(300),
    username            VARCHAR(100),
    member_count        INTEGER DEFAULT 0,
    bot_permissions     JSONB DEFAULT '{}',
    settings            JSONB DEFAULT '{}' NOT NULL,
    is_active           BOOLEAN DEFAULT TRUE NOT NULL,
    is_forum            BOOLEAN DEFAULT FALSE NOT NULL,
    linked_at           TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at          TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_tg_owner_user_id ON telegram_groups(owner_user_id);
CREATE INDEX idx_tg_is_forum ON telegram_groups(is_forum) WHERE is_forum = TRUE;

CREATE TABLE telegram_group_link_codes (
    id                  SERIAL PRIMARY KEY,
    code                VARCHAR(20) UNIQUE NOT NULL,  -- TLG-XXXXXXXX
    user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    telegram_group_id   BIGINT,
    expires_at          TIMESTAMP NOT NULL,
    used                BOOLEAN DEFAULT FALSE NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_tglc_code ON telegram_group_link_codes(code);
CREATE INDEX idx_tglc_user_id ON telegram_group_link_codes(user_id);

CREATE TABLE members (
    id                  SERIAL PRIMARY KEY,
    group_id            INTEGER REFERENCES groups(id) ON DELETE CASCADE NOT NULL,
    telegram_user_id    BIGINT NOT NULL,
    username            VARCHAR(100),
    full_name           VARCHAR(200),
    xp                  INTEGER DEFAULT 0 NOT NULL,
    level               INTEGER DEFAULT 1 NOT NULL,
    warnings            INTEGER DEFAULT 0 NOT NULL,
    is_verified         BOOLEAN DEFAULT FALSE,
    is_muted            BOOLEAN DEFAULT FALSE,
    is_banned           BOOLEAN DEFAULT FALSE,
    role                VARCHAR(20) DEFAULT 'member',
    crm_notes           TEXT,
    crm_tags            JSONB DEFAULT '[]',
    joined_at           TIMESTAMP DEFAULT NOW(),
    created_at          TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(group_id, telegram_user_id)
);
CREATE INDEX idx_members_group_id ON members(group_id);
CREATE INDEX idx_members_telegram_user_id ON members(telegram_user_id);

CREATE TABLE official_members (
    id                  SERIAL PRIMARY KEY,
    telegram_group_id   VARCHAR(50) NOT NULL,
    telegram_user_id    BIGINT NOT NULL,
    username            VARCHAR(100),
    first_name          VARCHAR(200),
    is_admin            BOOLEAN DEFAULT FALSE,
    is_admin_cached_at  TIMESTAMP,
    xp                  INTEGER DEFAULT 0,
    level               INTEGER DEFAULT 1,
    warnings            INTEGER DEFAULT 0,
    joined_at           TIMESTAMP DEFAULT NOW(),
    UNIQUE(telegram_group_id, telegram_user_id)
);
CREATE INDEX idx_om_group_id ON official_members(telegram_group_id);

-- ============================================================
-- BOT EVENTS & AUDIT
-- ============================================================

CREATE TABLE bot_events (
    id              SERIAL PRIMARY KEY,
    group_id        VARCHAR(50) NOT NULL,
    event_type      VARCHAR(50) NOT NULL,
    -- member_joined | member_left | verification_started | verification_passed
    -- verification_failed | automod_action | command_triggered | bot_added
    -- bot_removed | group_linked | level_up | raid_started | raid_completed
    -- message_sent (lightweight count event — no content stored, just count)
    -- permission_missing (bot attempted action it lacks permission for)
    -- settings_updated (admin changed group settings)
    data            JSONB DEFAULT '{}',
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_be_group_id ON bot_events(group_id);
CREATE INDEX idx_be_event_type ON bot_events(event_type);
CREATE INDEX idx_be_created_at ON bot_events(created_at);
-- Retention: 90 days

CREATE TABLE audit_logs (
    id              SERIAL PRIMARY KEY,
    bot_id          INTEGER REFERENCES bots(id) ON DELETE CASCADE,
    group_id        INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    action          VARCHAR(50) NOT NULL,
    -- ban | kick | warn | mute | unmute | unban | purge
    moderator_id    BIGINT,
    target_user_id  BIGINT,
    reason          TEXT,
    data            JSONB,
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_al_group_id ON audit_logs(group_id);
CREATE INDEX idx_al_created_at ON audit_logs(created_at);

CREATE TABLE admin_audit_logs (
    id              SERIAL PRIMARY KEY,
    admin_user_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action          VARCHAR(100) NOT NULL,
    target_type     VARCHAR(50),    -- user | group | bot | billing
    target_id       VARCHAR(50),
    detail          JSONB,          -- before/after values
    ip_address      VARCHAR(45),
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_aal_admin_user_id ON admin_audit_logs(admin_user_id);
CREATE INDEX idx_aal_created_at ON admin_audit_logs(created_at);
-- Never purged

-- ============================================================
-- BILLING & PAYMENTS
-- ============================================================

CREATE TABLE pending_invoices (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    payment_id  VARCHAR(100) UNIQUE NOT NULL,
    plan        VARCHAR(20) NOT NULL,
    interval    VARCHAR(10) NOT NULL,   -- monthly | annual
    amount_usd  DECIMAL(10,2) NOT NULL,
    currency    VARCHAR(10),            -- crypto currency code
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL,
    expires_at  TIMESTAMP
);
CREATE INDEX idx_pi_user_id ON pending_invoices(user_id);
CREATE INDEX idx_pi_payment_id ON pending_invoices(payment_id);

CREATE TABLE processed_payments (
    id              SERIAL PRIMARY KEY,
    payment_id      VARCHAR(100) UNIQUE NOT NULL,  -- idempotency key
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    plan            VARCHAR(20),
    amount_paid     DECIMAL(10,2),
    currency        VARCHAR(10),
    provider        VARCHAR(20) DEFAULT 'nowpayments',
    processed_at    TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_pp_payment_id ON processed_payments(payment_id);

CREATE TABLE payment_history (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    provider    VARCHAR(20),
    plan        VARCHAR(20),
    amount      DECIMAL(10,2),
    currency    VARCHAR(10),
    status      VARCHAR(20),    -- finished | failed | pending
    payment_id  VARCHAR(100),
    interval    VARCHAR(10),
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_ph_user_id ON payment_history(user_id);

-- ============================================================
-- AI & WORKSPACE
-- ============================================================

CREATE TABLE user_api_keys (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    provider    VARCHAR(30) NOT NULL,   -- openai|anthropic|openrouter|gemini|custom
    api_key     TEXT NOT NULL,          -- Fernet encrypted
    model       VARCHAR(100),
    base_url    VARCHAR(500),           -- for Custom provider
    scope       VARCHAR(20) DEFAULT 'group' NOT NULL,  -- group | workspace
    group_id    INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_uak_user_id ON user_api_keys(user_id);

CREATE TABLE notes (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    group_id    VARCHAR(50),
    group_title VARCHAR(200),
    content     TEXT NOT NULL,
    source      VARCHAR(20) DEFAULT 'manual' NOT NULL,  -- manual | ai | bot
    tags        JSONB DEFAULT '[]',
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_notes_user_id ON notes(user_id);
CREATE INDEX idx_notes_group_id ON notes(group_id);
CREATE INDEX idx_notes_created_at ON notes(created_at);

CREATE TABLE tasks (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    group_id    VARCHAR(50),
    title       VARCHAR(500) NOT NULL,
    description TEXT,
    status      VARCHAR(20) DEFAULT 'todo',  -- todo | in_progress | done
    owner       VARCHAR(200),               -- who is responsible
    due_date    DATE,
    source      VARCHAR(20) DEFAULT 'manual',
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_tasks_user_id ON tasks(user_id);

CREATE TABLE workspace_reminders (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    text        VARCHAR(500) NOT NULL,
    remind_at   TIMESTAMP NOT NULL,
    is_sent     BOOLEAN DEFAULT FALSE NOT NULL,
    snooze_count INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_wr_user_id ON workspace_reminders(user_id);
CREATE INDEX idx_wr_remind_at ON workspace_reminders(remind_at) WHERE is_sent = FALSE;

CREATE TABLE pending_reminder_states (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE NOT NULL,
    subject         VARCHAR(500) NOT NULL,
    suggested_times JSONB,
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE TABLE bot_dm_messages (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    direction   VARCHAR(10) NOT NULL,   -- in | out
    content     TEXT,
    intent      VARCHAR(30),   -- reminder | note | digest | help | general | unknown
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_bdm_user_id ON bot_dm_messages(user_id);
CREATE INDEX idx_bdm_created_at ON bot_dm_messages(created_at);

CREATE TABLE digest_logs (
    id              SERIAL PRIMARY KEY,
    group_id        VARCHAR(50) NOT NULL,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    content_preview TEXT,
    provider        VARCHAR(30),
    tokens_used     INTEGER,
    sent_at         TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_dl_group_id ON digest_logs(group_id);
CREATE INDEX idx_dl_user_id ON digest_logs(user_id);
CREATE INDEX idx_dl_sent_at ON digest_logs(sent_at);

-- ============================================================
-- BOT FEATURES
-- ============================================================

CREATE TABLE scheduled_messages (
    id                  SERIAL PRIMARY KEY,
    bot_id              INTEGER REFERENCES bots(id) ON DELETE CASCADE,
    group_id            INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    telegram_group_id   BIGINT,                 -- for official bot
    owner_user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
    message_text        TEXT NOT NULL,
    scheduled_at        TIMESTAMP NOT NULL,
    repeat_interval     INTEGER,                -- minutes, NULL = one-shot
    pin_message         BOOLEAN DEFAULT FALSE,
    auto_delete_seconds INTEGER,
    is_active           BOOLEAN DEFAULT TRUE NOT NULL,
    last_sent_at        TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_sm_scheduled_at ON scheduled_messages(scheduled_at) WHERE is_active = TRUE;

CREATE TABLE auto_responses (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    tg_group_id     VARCHAR(50),               -- for official bot
    trigger         VARCHAR(500) NOT NULL,
    trigger_type    VARCHAR(20) DEFAULT 'contains',  -- contains|exact|starts_with|regex
    response        TEXT NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    match_count     INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_ar_group_id ON auto_responses(group_id);

CREATE TABLE knowledge_documents (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    tg_group_id     VARCHAR(50),
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    scope           VARCHAR(20) DEFAULT 'group',   -- group | workspace
    title           VARCHAR(500),
    content         TEXT NOT NULL,
    chunks          JSONB DEFAULT '[]',
    embedding       VECTOR(1536),               -- pgvector, Phase 3
    file_size_bytes INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_kd_group_id ON knowledge_documents(group_id);
CREATE INDEX idx_kd_user_id ON knowledge_documents(user_id);

CREATE TABLE invite_links (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    telegram_group_id BIGINT,
    invite_link     VARCHAR(500) NOT NULL,
    label           VARCHAR(200),
    use_count       INTEGER DEFAULT 0,
    member_limit    INTEGER,
    expire_date     TIMESTAMP,
    is_revoked      BOOLEAN DEFAULT FALSE,
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_il_group_id ON invite_links(group_id);

CREATE TABLE invite_link_joins (
    id              SERIAL PRIMARY KEY,
    invite_link_id  INTEGER REFERENCES invite_links(id) ON DELETE CASCADE NOT NULL,
    telegram_user_id BIGINT NOT NULL,
    joined_at       TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_ilj_invite_link_id ON invite_link_joins(invite_link_id);

CREATE TABLE raids (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER REFERENCES groups(id) ON DELETE CASCADE NOT NULL,
    title           VARCHAR(300) NOT NULL,
    target_count    INTEGER NOT NULL,
    current_count   INTEGER DEFAULT 0,
    xp_reward       INTEGER DEFAULT 50,
    starts_at       TIMESTAMP NOT NULL,
    ends_at         TIMESTAMP NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_raids_group_id ON raids(group_id);

CREATE TABLE polls (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER REFERENCES groups(id) ON DELETE CASCADE NOT NULL,
    question        VARCHAR(500) NOT NULL,
    options         JSONB NOT NULL,             -- [{text, votes}]
    poll_type       VARCHAR(20) DEFAULT 'poll', -- poll | quiz
    is_anonymous    BOOLEAN DEFAULT TRUE,
    allows_multiple BOOLEAN DEFAULT FALSE,
    scheduled_at    TIMESTAMP,
    sent_at         TIMESTAMP,
    telegram_poll_id VARCHAR(100),
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_polls_group_id ON polls(group_id);

CREATE TABLE webhook_integrations (
    id              SERIAL PRIMARY KEY,
    group_id        INTEGER REFERENCES groups(id) ON DELETE CASCADE NOT NULL,
    name            VARCHAR(200),
    url             VARCHAR(1000) NOT NULL,
    signing_secret  VARCHAR(255),               -- for verifying inbound webhooks
    events          JSONB DEFAULT '[]',          -- event types to send
    is_active       BOOLEAN DEFAULT TRUE,
    last_triggered  TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_wi_group_id ON webhook_integrations(group_id);

-- ============================================================
-- REFERRALS & GROWTH
-- ============================================================

CREATE TABLE referrals (
    id              SERIAL PRIMARY KEY,
    referrer_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    referee_id      INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',  -- pending|approved|suspicious|blocked
    ip_suspicious   BOOLEAN DEFAULT FALSE,
    device_suspicious BOOLEAN DEFAULT FALSE,
    milestone_reached INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL,
    approved_at     TIMESTAMP,
    UNIQUE(referrer_id, referee_id)
);
CREATE INDEX idx_ref_referrer_id ON referrals(referrer_id);

CREATE TABLE suspicious_activities (
    id          SERIAL PRIMARY KEY,
    event_type  VARCHAR(50) NOT NULL,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    ip_hash     VARCHAR(64),
    device_hash VARCHAR(64),
    data        JSONB DEFAULT '{}',
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_sa_user_id ON suspicious_activities(user_id);
CREATE INDEX idx_sa_created_at ON suspicious_activities(created_at);

-- ============================================================
-- NOTIFICATIONS
-- ============================================================

CREATE TABLE notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    type        VARCHAR(50) NOT NULL,
    title       VARCHAR(200) NOT NULL,
    message     TEXT,
    data        JSONB DEFAULT '{}',
    read        BOOLEAN DEFAULT FALSE NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_notif_user_id ON notifications(user_id);
CREATE INDEX idx_notif_read ON notifications(user_id, read) WHERE read = FALSE;

-- ============================================================
-- DIRECTORY & MARKETPLACE
-- ============================================================

CREATE TABLE directory_listings (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    type                VARCHAR(20) NOT NULL,   -- bot | group | channel
    telegram_id         VARCHAR(100),
    title               VARCHAR(300) NOT NULL,
    description         TEXT,
    category            VARCHAR(100),
    tags                JSONB DEFAULT '[]',
    invite_link         VARCHAR(500),
    member_count        INTEGER,
    moderation_status   VARCHAR(20) DEFAULT 'pending',  -- pending|approved|rejected
    submitted_at        TIMESTAMP DEFAULT NOW() NOT NULL,
    approved_at         TIMESTAMP
);
CREATE INDEX idx_dl_user_id ON directory_listings(user_id);
CREATE INDEX idx_dl_moderation_status ON directory_listings(moderation_status);

-- ============================================================
-- CHANNELS
-- ============================================================

CREATE TABLE channels (
    id                  SERIAL PRIMARY KEY,
    owner_user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    telegram_channel_id BIGINT UNIQUE NOT NULL,
    title               VARCHAR(300),
    username            VARCHAR(100),
    subscriber_count    INTEGER DEFAULT 0,
    settings            JSONB DEFAULT '{}',
    is_active           BOOLEAN DEFAULT TRUE,
    linked_at           TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_channels_owner_user_id ON channels(owner_user_id);

-- ============================================================
-- VERIFICATION
-- ============================================================

CREATE TABLE pending_verifications (
    id                      SERIAL PRIMARY KEY,
    telegram_user_id        BIGINT NOT NULL,
    group_id                VARCHAR(50) NOT NULL,
    challenge_text          VARCHAR(500),
    answer                  VARCHAR(50),
    challenge_message_id    BIGINT,   -- message_id of the DM challenge sent to the user
    challenge_chat_id       BIGINT,   -- chat_id where the challenge was sent (user's DM)
    expires_at              TIMESTAMP NOT NULL,
    created_at              TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(telegram_user_id, group_id)
);
-- challenge_message_id + challenge_chat_id enable:
-- (a) deleting the challenge message after successful verification
-- (b) editing it to show "expired" on timeout rather than leaving a stale prompt
CREATE INDEX idx_pv_group_id ON pending_verifications(group_id);
CREATE INDEX idx_pv_expires_at ON pending_verifications(expires_at);

-- ============================================================
-- VERIFICATION SAFETY — UNBAN RETRY QUEUE
-- ============================================================
-- When a timed-out user is kicked via ban+unban, the unban call
-- may fail (network error). A failed unban = permanent ban.
-- This table tracks bans that still need an unban attempt.

CREATE TABLE pending_unbans (
    id                  SERIAL PRIMARY KEY,
    telegram_user_id    BIGINT NOT NULL,
    group_id            VARCHAR(50) NOT NULL,
    ban_succeeded_at    TIMESTAMP DEFAULT NOW() NOT NULL,
    unban_attempts      INTEGER DEFAULT 0 NOT NULL,
    last_attempt_at     TIMESTAMP,
    unban_succeeded     BOOLEAN DEFAULT FALSE NOT NULL,
    error_message       TEXT,
    UNIQUE(telegram_user_id, group_id)
);
CREATE INDEX idx_pu_unban_succeeded ON pending_unbans(unban_succeeded) WHERE unban_succeeded = FALSE;

-- ============================================================
-- SSE AUTH NONCES
-- ============================================================
-- Short-lived nonces for SSE authentication (stored in Redis,
-- not DB — this table is a fallback schema reference only).
-- Redis key: sse_nonce:{nonce} → user_id, TTL=60s, single-use (GETDEL)

-- ============================================================
-- PAYMENT SUBSCRIPTIONS
-- ============================================================

CREATE TABLE subscription_renewals (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    plan            VARCHAR(20) NOT NULL,
    interval        VARCHAR(10) NOT NULL,       -- monthly | annual
    period_start    TIMESTAMP NOT NULL,
    period_end      TIMESTAMP NOT NULL,
    payment_id      VARCHAR(100),               -- NOWPayments payment_id if paid
    status          VARCHAR(20) DEFAULT 'active', -- active | expired | cancelled | grace
    created_at      TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_sr_user_id ON subscription_renewals(user_id);
CREATE INDEX idx_sr_period_end ON subscription_renewals(period_end) WHERE status = 'active';
```

---

## 6.3 Indexing Strategy

| Query pattern | Index |
|---|---|
| `WHERE user_id = ?` (most tables) | Single-column on `user_id` |
| `WHERE group_id = ?` (events, members) | Single-column on `group_id` |
| `WHERE remind_at <= NOW() AND is_sent = FALSE` | Partial index with WHERE clause |
| `WHERE read = FALSE AND user_id = ?` | Partial index on notifications |
| `WHERE created_at > NOW() - INTERVAL '90 days'` | Index on `created_at` for bot_events |
| `WHERE jti = ?` (JWT blacklist lookup) | Unique index on `jti` |
| `WHERE email = ?` (login) | Unique index on `email` |

---

## 6.4 Caching Strategy

| Data | Cache layer | TTL | Rationale |
|---|---|---|---|
| JWT blacklist | Redis | Token expiry | Fast path for every request |
| Rate limit counters | Redis | Window size | Sub-millisecond counter increments |
| OfficialMember.is_admin | In-memory dict (bot process only) | 5 minutes | Avoids Telegram API call on every message |
| Hub summary | None | — | Too personalized to cache; loads fast from DB |
| Group settings | **Redis** (key: `group_settings:{id}`) | 5 minutes | ⚠️ Must be Redis — not a module-level dict. Gunicorn workers do not share memory. Settings updates via API must call `invalidate_group_settings_cache()` to invalidate immediately. |
| Permission score | DB (`bot_permissions` JSONB) | Refreshed on demand | Avoids repeated Telegram API calls |
| AI quota counter | Redis (key: `ai_quota:{user_id}:{date}`) | Daily (TTL=86400s) | Atomic INCR for race-free quota enforcement |
| SSE auth nonces | Redis (key: `sse_nonce:{nonce}`) | 60 seconds | Single-use via GETDEL; never stored in DB |

---

## 6.5 Migration Strategy

```python
# backend/migrate.py
# Simple, linear, idempotent migrations using CREATE TABLE IF NOT EXISTS
# and ALTER TABLE ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+)

# Run on every deploy via Procfile release step:
# release: python backend/migrate.py

def run_migrations():
    with engine.connect() as conn:
        # Each migration is a function, executed in order
        _migration_001_initial_schema(conn)
        _migration_002_add_totp_fields(conn)
        _migration_003_add_scope_to_api_keys(conn)
        _migration_004_add_indexes(conn)
        # ...
        logger.info("All migrations complete")

def _migration_004_add_indexes(conn):
    # CREATE INDEX IF NOT EXISTS — safe to run multiple times
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_bots_user_id ON bots(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_notes_user_id ON notes(user_id)",
        # ... all 10+ FK indexes
    ]
    for idx in indexes:
        try:
            conn.execute(text(idx))
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
```

**No Alembic for MVP.** The `migrate.py` approach is transparent, debuggable, and doesn't require migration file management. Alembic recommended when team size > 3 developers or when schema changes become complex.

---

*Phase 2 complete. Sections 4–6 documented.*

---

# 7. BACKEND & API SPECIFICATION

## 7.1 Flask Application Factory

```python
# backend/app.py — create_app()

def create_app():
    app = Flask(__name__)
    
    # ── Config ──────────────────────────────────────────────
    app.config.from_object(config)
    _assert_production_safety(app)  # raises RuntimeError on bad config
    
    # ── Logging ─────────────────────────────────────────────
    if not app.debug:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())  # pythonjsonlogger
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
    
    # ── Sentry ──────────────────────────────────────────────
    if config.SENTRY_DSN:
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            integrations=[FlaskIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.1,
            environment='production' if config.IS_PRODUCTION else 'development',
        )
    
    # ── Database ─────────────────────────────────────────────
    db.init_app(app)
    
    # ── JWT ──────────────────────────────────────────────────
    jwt = JWTManager(app)
    
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload['jti']
        # Fast path: Redis
        if redis_client:
            return redis_client.get(f'revoked:{jti}') is not None
        # Fallback: DB
        return RevokedToken.query.filter_by(jti=jti).first() is not None
    
    # ── CORS ─────────────────────────────────────────────────
    CORS(app, origins=config.ALLOWED_ORIGINS, supports_credentials=True)
    
    # ── Rate limiter ─────────────────────────────────────────
    limiter.init_app(app)
    
    # ── Email verification gate ──────────────────────────────
    @app.before_request
    def enforce_email_verification():
        if not request.path.startswith('/api/'):
            return
        # Whitelist: auth, health, public endpoints
        WHITELIST = {
            '/api/auth/login', '/api/auth/register', '/api/auth/verify-email',
            '/api/auth/resend-verification', '/api/auth/forgot-password',
            '/api/auth/reset-password', '/api/auth/refresh',
            '/api/billing/nowpayments-webhook',
            '/health', '/api/health', '/ready',
        }
        if request.path in WHITELIST:
            return
        try:
            verify_jwt_in_request(optional=True)
            claims = get_jwt()
            scope = claims.get('scope', 'full')
            if scope == 'email_verify_pending':
                return jsonify({'success': False, 'error': {
                    'code': 'EMAIL_NOT_VERIFIED',
                    'message': 'Please verify your email address.'
                }}), 403
            if scope == 'totp_pending':
                return jsonify({'success': False, 'error': {
                    'code': 'TOTP_REQUIRED',
                    'message': '2FA verification required.'
                }}), 403
        except Exception:
            pass
    
    # ── Blueprints ───────────────────────────────────────────
    _register_blueprints(app)
    
    # ── Health endpoints ─────────────────────────────────────
    @app.route('/health')
    @app.route('/api/health')
    def health():
        db_ok = _check_db()
        bot_ok = bot_manager.official_bot_running()
        return jsonify({
            'status': 'healthy' if db_ok else 'degraded',
            'db': db_ok, 'bot': bot_ok,
            'version': config.APP_VERSION,
        })
    
    @app.route('/ready')
    def ready():
        if not _check_db():
            return jsonify({'ready': False}), 503
        return jsonify({'ready': True})
    
    return app


def _assert_production_safety(app):
    """Fail fast on misconfiguration rather than silently misbehave."""
    if not config.IS_PRODUCTION:
        return
    required = ['SECRET_KEY', 'JWT_SECRET_KEY', 'ENCRYPTION_KEY', 'DATABASE_URL',
                'ADMIN_EMAILS', 'FRONTEND_URL', 'ALLOWED_ORIGINS']
    for key in required:
        if not getattr(config, key, None):
            raise RuntimeError(f"Required environment variable {key} is not set.")
    if '*' in config.ALLOWED_ORIGINS:
        raise RuntimeError("Wildcard CORS origin not allowed in production.")
    if any('localhost' in o for o in config.ALLOWED_ORIGINS.split(',')):
        raise RuntimeError("Localhost origin not allowed in production.")
```

---

## 7.2 Authentication System (Route-Level)

### 7.2.1 Registration

```python
# POST /api/auth/register
@auth_bp.route('/api/auth/register', methods=['POST'])
@limiter.limit("10 per minute")
def register():
    data = request.get_json(silent=True) or {}
    
    # Validate input
    errors = {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    captcha_token = data.get('captcha_token', '')  # hCaptcha or Turnstile token
    
    if not email or '@' not in email or '.' not in email.split('@')[-1]:
        errors['email'] = 'Valid email required'
    else:
        # Block known disposable email domains (maintain blocklist in config)
        domain = email.split('@')[-1]
        if domain in config.DISPOSABLE_EMAIL_DOMAINS:
            errors['email'] = 'Disposable email addresses are not allowed'
    
    # Password strength: min 10 chars, at least one non-letter
    if not password or len(password) < 10:
        errors['password'] = 'Password must be at least 10 characters'
    elif password.isalpha():
        errors['password'] = 'Password must contain at least one number or symbol'
    elif password.lower() in config.COMMON_PASSWORDS:
        errors['password'] = 'This password is too common. Please choose a stronger one.'
    
    if not full_name or len(full_name.strip()) < 2:
        errors['full_name'] = 'Name required'
    
    # CAPTCHA verification (required in production)
    if config.IS_PRODUCTION and not _verify_captcha(captcha_token):
        errors['captcha'] = 'CAPTCHA verification failed. Please try again.'
    
    if errors:
        return jsonify({'success': False, 'error': {
            'code': 'VALIDATION_ERROR', 'message': errors
        }}), 422
    
    # Check existing account
    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'error': {
            'code': 'ALREADY_EXISTS', 'message': 'An account with this email already exists.'
        }}), 409
    
    # Anti-abuse checks
    ip = _get_client_ip(request)
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()
    device_fp = data.get('device_fingerprint', '')
    device_hash = hashlib.sha256(device_fp.encode()).hexdigest() if device_fp else None
    
    if SuspiciousActivity.count_recent(ip_hash=ip_hash, hours=24) >= 3:
        return jsonify({'success': False, 'error': {
            'code': 'RATE_LIMITED', 'message': 'Too many registrations. Try again tomorrow.'
        }}), 429
    
    # Create user
    user = User(
        email=email,
        password_hash=bcrypt.generate_password_hash(password).decode(),
        full_name=full_name,
        email_verified=False,
        subscription_tier='free',
        referral_code=_generate_referral_code(),
        timezone='UTC',
    )
    db.session.add(user)
    db.session.flush()  # get user.id before commit
    
    # Handle referral
    ref_code = data.get('ref')
    if ref_code:
        _handle_referral(user, ref_code, ip_hash, device_hash)
    
    db.session.commit()
    
    # Send verification email (async, non-blocking)
    threading.Thread(
        target=_send_verification_email, args=(user,)
    ).start()
    
    # Return scoped token
    token = create_access_token(
        identity=user.id,
        additional_claims={'scope': 'email_verify_pending'}
    )
    refresh_token = create_refresh_token(identity=user.id)
    
    return jsonify({
        'success': True,
        'data': {
            'token': token,
            'refresh_token': refresh_token,
            'user': user.to_dict(public=True)
        }
    }), 201
```

### 7.2.2 Login

```python
# POST /api/auth/login
@auth_bp.route('/api/auth/login', methods=['POST'])
@limiter.limit("20 per minute")
def login():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    user = User.query.filter_by(email=email, deleted_at=None).first()
    
    # Account lockout check
    if user and user.locked_until and user.locked_until > datetime.utcnow():
        remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60)
        return jsonify({'success': False, 'error': {
            'code': 'ACCOUNT_LOCKED',
            'message': f'Too many failed attempts. Try again in {remaining} minutes.'
        }}), 423
    
    # Verify credentials
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 10:
                user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                user.failed_login_attempts = 0
            db.session.commit()
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_CREDENTIALS',
            'message': 'Invalid email or password.'
        }}), 401
    
    # Reset fail counter on success
    user.failed_login_attempts = 0
    user.locked_until = None
    
    # Auto-promote admin emails
    if email in config.ADMIN_EMAILS.split(',') and not user.is_admin:
        user.is_admin = True
        if user.subscription_tier == 'free':
            user.subscription_tier = 'enterprise'
    
    db.session.commit()
    
    # 2FA check
    if user.totp_enabled:
        nonce = secrets.token_hex(16)
        redis_client.setex(f'totp_nonce:{user.id}:{nonce}', 90, '1')
        pending_token = create_access_token(
            identity=user.id,
            expires_delta=timedelta(seconds=90),
            additional_claims={'scope': 'totp_pending', 'nonce': nonce}
        )
        return jsonify({'success': True, 'data': {
            'requires_2fa': True,
            'totp_pending_token': pending_token,
        }})
    
    # Issue full tokens
    token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)
    
    return jsonify({'success': True, 'data': {
        'token': token,
        'refresh_token': refresh_token,
        'user': user.to_dict(public=True),
        'is_admin': user.is_admin,
    }})
```

---

## 7.3 Middleware Stack

```
Request arrives at Flask
        │
        ▼
1. CORS middleware (flask-cors)
   → Check Origin against ALLOWED_ORIGINS
   → Reject if not in list

        │
        ▼
2. Rate limiter (flask-limiter)
   → Check per-IP and per-user limits via Redis
   → 429 if exceeded

        │
        ▼
3. Email verification gate (before_request)
   → Extract JWT if present
   → If scope == email_verify_pending → 403 (except whitelisted paths)
   → If scope == totp_pending → 403 (except verify-totp-login)

        │
        ▼
4. Route handler
   → @jwt_required() validates token signature + checks blacklist
   → @admin_required() checks is_admin flag + TOTP enabled

        │
        ▼
5. Response
   → Standard JSON envelope
   → Security headers (after_request)
```

---

## 7.4 Permission Decorators

```python
# @admin_required — wraps @jwt_required, adds admin check
def admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or not user.is_admin:
            return jsonify({'success': False, 'error': {
                'code': 'FORBIDDEN', 'message': 'Admin access required.'
            }}), 403
        
        if not user.totp_enabled:
            return jsonify({'success': False, 'error': {
                'code': 'TOTP_REQUIRED',
                'message': 'Admin accounts must have 2FA enabled.'
            }}), 403
        
        # Log admin action
        AdminAuditLog.log(
            admin_user_id=user_id,
            action=f"{request.method} {request.path}",
            ip_address=_get_client_ip(request),
            detail={'args': dict(request.args), 'body_keys': list(request.json.keys())
                    if request.is_json else []}
        )
        
        return f(*args, **kwargs)
    return decorated


# @plan_required('pro') — checks subscription tier
def plan_required(min_tier):
    TIER_RANK = {'free': 0, 'pro': 1, 'enterprise': 2}
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def decorated(*args, **kwargs):
            user_id = get_jwt_identity()
            user = User.query.get(user_id)
            if TIER_RANK.get(user.subscription_tier, 0) < TIER_RANK.get(min_tier, 0):
                return jsonify({'success': False, 'error': {
                    'code': 'PLAN_LIMIT_REACHED',
                    'message': f'Upgrade to {min_tier.capitalize()} to use this feature.',
                    'required_plan': min_tier,
                }}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
```

---

## 7.5 Complete API Reference

### Auth & Identity

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | None | Create account |
| POST | `/api/auth/login` | None | Login, get tokens |
| POST | `/api/auth/verify-totp-login` | totp_pending | Complete 2FA login |
| POST | `/api/auth/verify-email` | email_verify_pending | Verify email address |
| POST | `/api/auth/resend-verification` | email_verify_pending | Resend verification email |
| GET | `/api/auth/me` | JWT | Get own profile |
| PATCH | `/api/auth/me` | JWT | Update name, timezone |
| POST | `/api/auth/forgot-password` | None | Request reset email |
| POST | `/api/auth/reset-password` | None | Set new password via token |
| POST | `/api/auth/change-password` | JWT | Change password (requires current) |
| POST | `/api/auth/refresh` | refresh JWT | Get new access token |
| POST | `/api/auth/logout` | JWT | Revoke current token |
| DELETE | `/api/auth/account` | JWT | Soft-delete account |
| GET | `/api/auth/export` | JWT | Download all user data (GDPR) |
| POST | `/api/auth/2fa/setup` | JWT | Generate TOTP secret + QR |
| POST | `/api/auth/2fa/enable` | JWT | Enable TOTP after confirming code |
| POST | `/api/auth/2fa/disable` | JWT | Disable TOTP (requires code+password) |
| GET | `/api/auth/2fa/backup-codes/count` | JWT | Remaining backup codes |
| POST | `/api/auth/2fa/backup-codes/regenerate` | JWT | Generate new backup codes |

### Custom Bots

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/bots` | JWT | List user's custom bots |
| POST | `/api/bots` | JWT | Add custom bot (validate token async) |
| GET | `/api/bots/:id` | JWT | Get bot details |
| DELETE | `/api/bots/:id` | JWT | Delete bot (stops polling) |
| POST | `/api/bots/:id/toggle` | JWT | Enable/disable bot |
| GET | `/api/bots/:id/status` | JWT | Live health check |
| GET | `/api/bots/:id/groups` | JWT | Groups under this bot |

### Official Bot Groups

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/telegram-groups` | JWT | List linked groups |
| POST | `/api/telegram-groups/pending-link` | JWT | Generate link code |
| GET | `/api/telegram-groups/:id` | JWT | Group details |
| PATCH | `/api/telegram-groups/:id` | JWT | Update group settings |
| DELETE | `/api/telegram-groups/:id` | JWT | Unlink group |
| GET | `/api/telegram-groups/:id/analytics` | JWT | Group analytics |
| GET | `/api/telegram-groups/:id/digest` | JWT | Digest config |
| PUT | `/api/telegram-groups/:id/digest` | JWT | Update digest config |
| POST | `/api/telegram-groups/:id/digest/send` | JWT | Trigger digest now |
| GET | `/api/telegram-groups/:id/digest/history` | JWT | Last 20 digests |
| GET | `/api/telegram-groups/:id/members` | JWT | Member list (paginated) |
| GET | `/api/telegram-groups/:id/events` | JWT | Bot event log |
| GET | `/api/telegram-groups/:id/admins` | JWT | Telegram admin list |
| GET | `/api/telegram-groups/:id/permissions` | JWT | Live permission refresh |
| GET | `/api/telegram-groups/:id/leaderboard` | JWT | Top members by XP |
| GET/POST/PUT/DELETE | `/api/telegram-groups/:id/commands` | JWT | Custom commands CRUD |
| GET | `/api/telegram-groups/analytics/overview` | JWT | Cross-group aggregate |

### Assistant & Workspace

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/assistant/hub-summary` | JWT | Hub dashboard data |
| GET | `/api/assistant/dm-history` | JWT | Last 100 DM messages |
| GET | `/api/assistant/dm-stream` | JWT | SSE: live DM messages |
| POST | `/api/assistant/send-dm` | JWT | Send message via bot DM |
| GET | `/api/workspace/ai-settings` | JWT | AI key config + usage |
| POST | `/api/workspace/ai-settings` | JWT | Save workspace AI key |
| DELETE | `/api/workspace/ai-settings` | JWT | Remove workspace AI key |
| POST | `/api/workspace/ai-settings/test` | JWT | Test AI key connection |
| GET/POST | `/api/notes` | JWT | List / create notes |
| PUT/DELETE | `/api/notes/:id` | JWT | Update / delete note |
| POST | `/api/notes/generate/:group_id` | JWT | AI-generate notes from group |
| GET/POST | `/api/tasks` | JWT | List / create tasks |
| PUT/DELETE | `/api/tasks/:id` | JWT | Update / delete task |
| GET/POST | `/api/workspace/reminders` | JWT | List / create reminders |
| PUT/DELETE | `/api/workspace/reminders/:id` | JWT | Update / delete reminder |
| GET/POST/DELETE | `/api/workspace/knowledge` | JWT | Workspace knowledge base |
| GET/POST/DELETE | `/api/automations` | JWT | Workflow rules |
| GET/POST/DELETE | `/api/forwarding` | JWT | Message forwarding rules |

### Billing

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/billing/create-checkout` | JWT | Create NOWPayments invoice |
| POST | `/api/billing/nowpayments-webhook` | None (HMAC) | Payment webhook |
| GET | `/api/billing/history` | JWT | Payment history |
| GET | `/api/billing/subscription` | JWT | Current subscription status |
| DELETE | `/api/billing/subscription` | JWT | Cancel subscription |

### Analytics

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/analytics/:botId/:groupId` | JWT | Custom bot group analytics |
| GET | `/api/official-groups/analytics/overview` | JWT | Official groups aggregate |
| GET | `/api/official-groups/:id/analytics` | JWT | Single group analytics |

### Admin (requires is_admin + TOTP)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/admin/stats` | Admin | Platform overview stats |
| GET | `/api/admin/users` | Admin | User list with search |
| GET | `/api/admin/users/:id` | Admin | User detail |
| POST | `/api/admin/users/:id/ban` | Admin | Ban user |
| POST | `/api/admin/users/:id/unban` | Admin | Unban user |
| PATCH | `/api/admin/users/:id/plan` | Admin | Change user plan |
| GET | `/api/admin/telegram-groups` | Admin | All groups |
| POST | `/api/admin/telegram-groups/:id/disable` | Admin | Disable group |
| GET | `/api/admin/custom-bots` | Admin | All custom bots |
| POST | `/api/admin/custom-bots/:id/disable` | Admin | Disable bot |
| GET | `/api/admin/bot-events` | Admin | Cross-platform events |
| GET | `/api/admin/audit-log` | Admin | Admin action log |

---

## 7.6 Request/Response Shapes (Key Endpoints)

### POST /api/billing/create-checkout
```json
// Request
{ "plan": "pro", "interval": "monthly" }

// Response 200
{
  "success": true,
  "data": {
    "payment_url": "https://nowpayments.io/payment/...",
    "payment_id": "4521867345",
    "amount_usd": 19.00,
    "expires_at": "2026-05-08T15:30:00Z"
  }
}
```

### POST /api/billing/nowpayments-webhook
```json
// Headers: x-nowpayments-sig: <hmac-sha512>
// Body (from NOWPayments):
{
  "payment_id": "4521867345",
  "payment_status": "finished",
  "pay_address": "bc1q...",
  "price_amount": 19.00,
  "price_currency": "usd",
  "pay_amount": 0.000312,
  "pay_currency": "btc",
  "order_id": "telegizer_user_42",
  "created_at": "2026-05-08T14:00:00.000Z",
  "updated_at": "2026-05-08T14:28:00.000Z"
}
// Response 200 {"success": true} or 400 on signature failure
```

### GET /api/assistant/hub-summary
```json
{
  "success": true,
  "data": {
    "bot_connected": true,
    "bot_username": "TelegizerBot",
    "connected_groups": 3,
    "reminders_today": [
      { "id": 1, "text": "Call John", "remind_at": "2026-05-08T15:00:00Z", "is_sent": false }
    ],
    "recent_notes": [
      { "id": 5, "content": "Decided: launch Q3...", "source": "ai",
        "group_title": "Crypto Hub", "created_at": "2026-05-08T10:00:00Z" }
    ],
    "digest_status": [
      { "group_id": "123", "group_title": "Crypto Hub",
        "last_sent": "2026-05-08T09:02:00Z", "status": "sent" },
      { "group_id": "456", "group_title": "Dev Group",
        "last_sent": null, "status": "pending" }
    ],
    "automation_activity": {
      "auto_replies_today": 14,
      "workflows_today": 3,
      "messages_forwarded_today": 7
    },
    "suggestions": [
      { "type": "setup", "icon": "Summarize",
        "title": "Enable Digests for Dev Group",
        "body": "Active group with no digest configured.",
        "action": "/workspace/digests" }
    ]
  }
}
```

---

## 7.7 Error Handling

```python
# All routes use this pattern:
from functools import wraps

def handle_exceptions(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValidationError as e:
            return jsonify({'success': False, 'error': {
                'code': 'VALIDATION_ERROR', 'message': e.messages
            }}), 422
        except QuotaExceededError as e:
            return jsonify({'success': False, 'error': {
                'code': 'QUOTA_EXCEEDED', 'message': str(e)
            }}), 429
        except PermissionError as e:
            return jsonify({'success': False, 'error': {
                'code': 'FORBIDDEN', 'message': str(e)
            }}), 403
        except NotFound as e:
            return jsonify({'success': False, 'error': {
                'code': 'NOT_FOUND', 'message': str(e)
            }}), 404
        except Exception as e:
            logger.exception(f"Unhandled error in {f.__name__}: {e}")
            sentry_sdk.capture_exception(e)
            return jsonify({'success': False, 'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'An unexpected error occurred. Our team has been notified.'
            }}), 500
    return decorated
```

---

## 7.8 Rate Limiting Configuration

```python
# backend/middleware/rate_limit.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=config.REDIS_URL,
    storage_options={'socket_connect_timeout': 1},
    on_breach=_on_rate_limit_exceeded,
    default_limits=['200 per minute'],
)

def _on_rate_limit_exceeded(limit):
    return jsonify({'success': False, 'error': {
        'code': 'RATE_LIMITED',
        'message': 'Too many requests. Please slow down.',
        'retry_after': limit.reset_at.isoformat(),
    }}), 429

# Applied per-route:
@auth_bp.route('/api/auth/register', methods=['POST'])
@limiter.limit("10 per minute")
def register(): ...

@auth_bp.route('/api/auth/login', methods=['POST'])
@limiter.limit("20 per minute")
def login(): ...
```

---

# 8. SECURITY ARCHITECTURE

## 8.0 Security Architecture Principles

| Principle | Implementation |
|---|---|
| **Tokens never in URLs** | JWTs via Authorization header only; SSE uses short-lived nonces |
| **Secrets encrypted at rest** | Fernet for bot tokens, API keys, TOTP secrets |
| **Defense in depth** | Frontend PlanGate is UX; backend enforces all limits server-side |
| **Fail closed on auth** | Rate limiting fails closed on auth endpoints when Redis unavailable |
| **Quota atomicity** | AI token quota uses Redis atomic INCR — no read-then-write race |
| **Admin requires TOTP** | Admin panel inaccessible without 2FA enabled on the account |
| **Audit everything** | All admin actions logged with IP; all auth events logged |
| **No secrets in logs** | Bot tokens, API keys, and passwords regex-redacted before logging |

---

## 8.1 Threat Model

Telegizer's primary attack surfaces:

| Surface | Threat | Mitigation |
|---|---|---|
| Authentication | Credential stuffing, brute force | Account lockout at 10 failures, 15-min lockout |
| JWT tokens | Token theft, replay attacks | Short lifetime (1d), Redis blacklist on logout |
| Payment webhooks | Fake payment webhooks | HMAC-SHA512 signature verification on every webhook |
| Bot tokens | Token exposure in logs | Regex redaction before logging, Fernet encryption at rest |
| Encryption keys | Key compromise | Required env vars; ENCRYPTION_KEY_OLD for safe rotation |
| Admin panel | Unauthorized access | Backend is_admin check + TOTP requirement |
| File uploads | Malicious file upload | MIME type validation, 10MB limit, per-group quota |
| AI API keys | Key leakage in logs | Fernet encrypted; never logged; masked in UI |
| Referral system | Self-referral abuse | IP+device hash check; referral blocked on match |
| CORS | Cross-origin API abuse | Strict origin allowlist, no wildcards |

---

## 8.2 Encryption at Rest

```python
# backend/utils/encryption.py

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

def _get_fernet():
    """MultiFernet supports key rotation: tries new key first, falls back to old."""
    keys = [config.ENCRYPTION_KEY.encode()]
    if config.ENCRYPTION_KEY_OLD:
        keys.append(config.ENCRYPTION_KEY_OLD.encode())
    fernets = [Fernet(k) for k in keys]
    return MultiFernet(fernets) if len(fernets) > 1 else fernets[0]

def encrypt_value(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    return _get_fernet().encrypt(plaintext.encode()).decode()

def decrypt_value(ciphertext: str) -> str:
    if not ciphertext:
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # If decryption fails, the ciphertext is corrupt or was never encrypted
        # NEVER return the raw ciphertext — raise so callers handle it explicitly
        raise DecryptionError(f"Failed to decrypt value. Check ENCRYPTION_KEY config.")
```

**⚠️ Key Rotation Protocol:**
```
BEFORE rotating ENCRYPTION_KEY:
  1. Set ENCRYPTION_KEY_OLD = current ENCRYPTION_KEY
  2. Set ENCRYPTION_KEY = new key
  3. Deploy → all new encryptions use new key; old encryptions still decrypt via OLD
  4. Run re-encryption script to update all rows to new key
  5. After re-encryption complete → remove ENCRYPTION_KEY_OLD
  6. Never skip step 1 — skipping it makes all existing encrypted values unreadable
```

---

## 8.3 JWT Security

```python
# JWT configuration in config.py
JWT_ACCESS_TOKEN_EXPIRES  = timedelta(days=1)
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
JWT_ALGORITHM             = 'HS256'
JWT_BLACKLIST_ENABLED     = True
JWT_BLACKLIST_TOKEN_CHECKS = ['access', 'refresh']

# Token payload structure
{
  "sub": 42,                      # user_id
  "jti": "uuid-v4",               # unique token ID (for blacklisting)
  "iat": 1715000000,              # issued at
  "exp": 1715086400,              # expiry
  "scope": "full",                # full | email_verify_pending | totp_pending
  "type": "access"                # access | refresh
}

# Revocation on logout (dual-write)
def revoke_token(jti, expires_at):
    # 1. Redis (fast path for all requests)
    ttl = int((expires_at - datetime.utcnow()).total_seconds())
    if redis_client and ttl > 0:
        redis_client.setex(f'revoked:{jti}', ttl, '1')
    
    # 2. DB (fallback when Redis unavailable)
    RevokedToken(jti=jti, expires_at=expires_at, revoked_at=datetime.utcnow())
    db.session.add(revoked)
    db.session.commit()
```

---

## 8.4 TOTP Security

```python
# TOTP flow security measures:
# 1. Secret encrypted via Fernet at rest (P1-02 fix)
# 2. 90-second pending token for 2FA step (cannot be used for anything else)
# 3. One-time nonce in Redis: each pending token has a nonce, consumed on first use
#    Prevents replay attacks where attacker intercepts totp_pending_token
# 4. Backup codes: SHA-256 hashed as dict {hash: used_bool} — O(1) lookup
# 5. Backup code rate limit: 5 attempts/minute per user
# 6. Each backup code single-use: marked used=True immediately in transaction

# TOTP secret storage
class User(Base):
    _totp_secret_encrypted = Column('totp_secret', Text)
    
    @property
    def totp_secret(self):
        if not self._totp_secret_encrypted:
            return None
        return decrypt_value(self._totp_secret_encrypted)
    
    @totp_secret.setter
    def totp_secret(self, value):
        self._totp_secret_encrypted = encrypt_value(value) if value else None
```

---

## 8.5 Webhook Security

```python
# NOWPayments webhook verification
def verify_nowpayments_signature(request) -> bool:
    signature = request.headers.get('x-nowpayments-sig')
    if not signature:
        return False
    
    payload = request.data  # raw bytes
    expected = hmac.new(
        config.NOWPAYMENTS_IPN_SECRET.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()
    
    return hmac.compare_digest(signature.lower(), expected.lower())

# Custom webhook verification (per-integration signing secret)
def verify_integration_webhook(request, integration: WebhookIntegration) -> bool:
    signature = request.headers.get('x-telegizer-signature')
    if not signature or not integration.signing_secret:
        return False
    
    expected = hmac.new(
        integration.signing_secret.encode(),
        request.data,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(
        signature.replace('sha256=', ''),
        expected
    )
```

---

## 8.6 Input Validation

```python
# All user input validated at API boundary
# Group settings: ALLOWED_SETTING_KEYS whitelist
ALLOWED_SETTING_KEYS = {
    'automod', 'verification', 'welcome', 'digest',
    'levels', 'reports', 'auto_replies', 'crm', 'mini_app'
}

def update_official_settings(group_id, data):
    # Reject unknown keys
    for key in data.keys():
        if key not in ALLOWED_SETTING_KEYS:
            raise ValidationError(f"Unknown setting key: {key}")
    
    # Deep merge only allowed keys
    group = TelegramGroup.query.get(group_id)
    for key in ALLOWED_SETTING_KEYS:
        if key in data:
            group.settings[key] = data[key]
    
    db.session.commit()
```

---

## 8.7 Security Headers

Applied via `after_request` hook (or `flask-talisman`):

```python
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if config.IS_PRODUCTION:
        response.headers['Strict-Transport-Security'] = (
            'max-age=31536000; includeSubDomains; preload'
        )
    return response
```

**Content Security Policy (Vercel, `vercel.json`):**
```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {
          "key": "Content-Security-Policy",
          "value": "default-src 'self'; script-src 'self' 'unsafe-inline' https://browser.sentry-cdn.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://api.telegizer.com wss://api.telegizer.com https://sentry.io; frame-ancestors 'none';"
        }
      ]
    }
  ]
}
```

---

## 8.7.1 JWT Storage Security

> **Security Advisory:** The current implementation stores JWTs in `localStorage`. Any XSS vulnerability — including a compromised npm dependency or Sentry SDK injection — allows full token exfiltration. The Phase 2 target is HttpOnly cookie-based authentication.

**Phase 1 (MVP):** `localStorage` with strict CSP (`unsafe-inline` must be removed from script-src by setting `INLINE_RUNTIME_CHUNK=false` in the Vercel build — see Section 9.3).

**Phase 2 (Beta):** Migrate to HttpOnly, Secure, SameSite=Strict cookie-based JWT:
```python
# Backend: set cookie on login
response.set_cookie(
    'access_token', token,
    httponly=True, secure=True, samesite='Strict',
    max_age=86400,  # 1 day
    domain='.telegizer.com'
)
# Frontend: remove Authorization header usage; cookies are sent automatically
# Axios: withCredentials: true (already configured in api.js)
```

---

## 8.7.2 Rate Limit Fail-Closed on Auth Endpoints

> **Security Fix:** The current config fails open when Redis is unavailable (allows all requests). For authentication endpoints this is unacceptable — a Redis outage becomes an open brute-force window.

```python
# backend/middleware/rate_limit.py — fail-closed override for auth endpoints
AUTH_ENDPOINTS = {'/api/auth/login', '/api/auth/register', '/api/auth/verify-totp-login'}

def _on_rate_limit_exceeded(limit):
    return jsonify({'success': False, 'error': {
        'code': 'RATE_LIMITED',
        'message': 'Too many requests. Please slow down.',
        'retry_after': limit.reset_at.isoformat(),
    }}), 429

# Custom key function: use user_id for authenticated endpoints, IP for public
def _rate_limit_key():
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id:
            return f"user:{user_id}"
    except Exception:
        pass
    return get_remote_address()

limiter = Limiter(
    key_func=_rate_limit_key,
    storage_uri=config.REDIS_URL,
    storage_options={'socket_connect_timeout': 1},
    on_breach=_on_rate_limit_exceeded,
    # Fail CLOSED on auth endpoints when Redis unavailable:
    swallow_errors=False,   # raises StorageError if Redis down
    default_limits=['200 per minute'],
)

# In app.py before_request: if Redis is down and endpoint is auth → 503
@app.before_request
def enforce_rate_limit_availability():
    if request.path in AUTH_ENDPOINTS and not redis_client:
        return jsonify({'success': False, 'error': {
            'code': 'SERVICE_UNAVAILABLE',
            'message': 'Authentication temporarily unavailable. Please try again shortly.'
        }}), 503
```

---

## 8.8 Bot Abuse Prevention

```python
# Anti-spam for bot commands
# 1. Custom commands: max 20 per group (configurable per plan)
# 2. Auto-responses: max 50 per group
# 3. Scheduled messages: max 100 active per group
# 4. Digest: max 1 per group per day (enforced in digest_ai.py)
# 5. Bot token validation: non-blocking (ThreadPoolExecutor) to prevent
#    token validation endpoint from being used as a timing oracle

# Official bot: message rate limiting
# If bot sends > 30 messages/second to same chat → auto-throttle (Telegram API limit)
# APScheduler ensures no concurrent execution of same job (misfire_grace_time=60s)
```

---

## 8.9 Admin Security

```python
# Admin panel security layers:
# 1. Frontend AdminRoute: calls GET /api/auth/me, checks is_admin in response
#    (localStorage is_admin is decorative only — never trusted for access)
# 2. Backend @admin_required: checks DB is_admin field
# 3. TOTP required: admin accounts without 2FA enabled → 403
# 4. Every admin action logged to AdminAuditLog with IP
# 5. ADMIN_EMAILS env var: users with these emails auto-promoted on login
#    (changing ADMIN_EMAILS removes admin access immediately on next login)
```

---

# 9. DEPLOYMENT ARCHITECTURE

## 9.0 Service Architecture Overview

### Current Architecture (MVP)

All components run in a single Railway service:
```
Railway Service (1 replica — HARD CONSTRAINT)
  ├── Gunicorn (2 sync workers) ← Flask API
  ├── APScheduler (in-process) ← Background jobs
  └── @TelegizerBot daemon thread ← Telegram bot
```

**Critical constraint:** `numReplicas` must be 1. The Telegram long-polling bot runs in a daemon thread and cannot handle duplicate polling across multiple instances. This prevents all horizontal scaling of the API tier.

### Target Architecture (Phase 2 — Separate Services)

Separating the bot from the API breaks the 1-replica constraint:

```
Railway Service: api (N replicas, auto-scale)
  └── Gunicorn (4+ workers) ← Flask API only

Railway Service: bot (1 replica — permanent constraint)
  └── @TelegizerBot long-polling daemon

Railway Service: worker (N replicas, auto-scale)
  └── Celery worker ← AI generation, digest sending, email

Railway Cron Jobs:
  └── APScheduler replaced by Railway's native cron

Shared: PostgreSQL + Redis (same instances)
```

**Migration path:** The bot service reads/writes to the same PostgreSQL DB. The API no longer imports any bot code. The bot service no longer handles HTTP requests. This separation allows:
- API to scale horizontally
- API deployments without bot downtime
- Bot deployments without API downtime
- Independent memory/CPU allocation per service

---

## 9.1 Infrastructure Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TELEGIZER INFRASTRUCTURE                          │
│                                                                     │
│  User's Browser                                                     │
│      │                                                              │
│      ▼                                                              │
│  Cloudflare CDN ──── HTTPS ────► Vercel (Frontend SPA)             │
│      │                                app.telegizer.com            │
│      │                                React 18, static build        │
│      │                                                              │
│      │ API calls                                                    │
│      ▼                                                              │
│  Railway Platform                                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Web Service (Flask + Gunicorn)                             │   │
│  │  api.telegizer.com                                          │   │
│  │  2 workers, 1 replica (bot constraint)                      │   │
│  │  ├── Flask API (28 blueprints)                              │   │
│  │  ├── APScheduler (background jobs)                          │   │
│  │  └── @TelegizerBot (daemon thread, long-polling)            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐    │
│  │  PostgreSQL 15      │  │  Redis                           │    │
│  │  Railway managed    │  │  Railway managed                 │    │
│  │  Auto backups       │  │  JWT blacklist + rate limits     │    │
│  └─────────────────────┘  └──────────────────────────────────┘    │
│                                                                     │
│  External services:                                                 │
│  ├── Sentry (error monitoring)                                      │
│  ├── Resend (transactional email)                                   │
│  ├── NOWPayments (crypto payments)                                  │
│  └── Telegram Bot API (long-polling)                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 9.1.1 Current Deployment Constraints & Known Bottlenecks

| Constraint | Impact | Resolution |
|---|---|---|
| `numReplicas = 1` (bot polling) | Zero horizontal scaling, full downtime on deploy | Phase 2: separate bot service |
| Sync Gunicorn workers (2) | AI calls (5-30s) block all other requests | Phase 2: Celery async workers |
| APScheduler in-process | Daily digest jobs compete with HTTP worker threads | Phase 2: Railway cron jobs |
| SSE holds DB connections | 10+ concurrent SSE users exhaust connection pool | Fixed in Section 5.6 (release session per poll) |
| Settings cache in-process dict | Stale settings until TTL; not shared across workers | Migrate to Redis cache (Phase 1 fix) |

---

## 9.2 Railway Configuration

```toml
# railway.toml
[build]
  builder = "nixpacks"

[deploy]
  numReplicas = 1              # CRITICAL: must be 1 (bot polling constraint)
  startCommand = "gunicorn --workers 2 --timeout 120 --bind 0.0.0.0:$PORT backend.app:create_app()"
  healthcheckPath = "/ready"
  healthcheckTimeout = 30
  restartPolicyType = "ON_FAILURE"
  restartPolicyMaxRetries = 3
```

```
# Procfile
release: python backend/migrate.py && python backend/migrate_totp.py
web:     gunicorn --workers 2 --timeout 120 --bind 0.0.0.0:$PORT "backend.app:create_app()"
```

**Gunicorn settings rationale:**
- `--workers 2`: 2 sync workers handle concurrent requests; bot runs in thread, not worker
- `--timeout 120`: allows long-running digest generation (AI calls can be slow)
- Sync workers (not async) because SQLAlchemy sessions are not async-safe in this config

---

## 9.3 Vercel Configuration

```json
// vercel.json
{
  "buildCommand": "npm run build",
  "outputDirectory": "build",
  "framework": "create-react-app",
  "rewrites": [
    { "source": "/((?!api/).*)", "destination": "/index.html" }
  ],
  "headers": [
    {
      "source": "/static/(.*)",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
      ]
    },
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Content-Security-Policy",
          "value": "default-src 'self'; script-src 'self' 'unsafe-inline' https://browser.sentry-cdn.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://api.telegizer.com https://sentry.io; frame-ancestors 'none';"
        }
      ]
    }
  ],
  "env": {
    "REACT_APP_API_URL": "@telegizer-api-url",
    "REACT_APP_SENTRY_DSN": "@telegizer-sentry-dsn-frontend"
  }
}
```

---

## 9.4 Environment Variables (Complete)

```bash
# ── REQUIRED (app throws RuntimeError if missing in production) ────────

SECRET_KEY=                          # 32+ random bytes — Flask session signing
JWT_SECRET_KEY=                      # 32+ random bytes — JWT signing
ENCRYPTION_KEY=                      # Fernet key — generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DATABASE_URL=postgresql://...        # Railway PostgreSQL connection string
ADMIN_EMAILS=admin@telegizer.com     # Comma-separated; grants admin access on login

# ── REQUIRED FOR PRODUCTION ────────────────────────────────────────────

FRONTEND_URL=https://app.telegizer.com
ALLOWED_ORIGINS=https://app.telegizer.com
BACKEND_URL=https://api.telegizer.com    # Used in email links
TELEGRAM_BOT_TOKEN=                      # From @BotFather for @TelegizerBot
TELEGRAM_BOT_USERNAME=TelegizerBot       # Without @ prefix

# ── EMAIL (one of the two groups below required) ───────────────────────

EMAIL_PROVIDER=resend
RESEND_API_KEY=re_...

# OR:
EMAIL_PROVIDER=smtp
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=noreply@telegizer.com
SMTP_PASSWORD=

FROM_EMAIL=noreply@telegizer.com

# ── AI PROVIDERS ───────────────────────────────────────────────────────

PLATFORM_GEMINI_API_KEY=AIzaSy...    # Platform-wide AI key for free users
PLATFORM_OPENROUTER_API_KEY=         # Alternative platform key

# ── PAYMENTS ───────────────────────────────────────────────────────────

NOWPAYMENTS_API_KEY=
NOWPAYMENTS_IPN_SECRET=              # For webhook HMAC verification

# ── MONITORING ─────────────────────────────────────────────────────────

SENTRY_DSN=https://xxx@sentry.io/yyy

# ── INFRASTRUCTURE ─────────────────────────────────────────────────────

REDIS_URL=redis://...               # Rate limiting + JWT blacklist (fail-open if missing)
APP_VERSION=2.0.0                   # Shown in /health endpoint

# ── CAPTCHA ────────────────────────────────────────────────────────────

CAPTCHA_PROVIDER=hcaptcha            # hcaptcha | turnstile | disabled (dev)
CAPTCHA_SECRET_KEY=                  # hCaptcha secret or Cloudflare Turnstile secret
REACT_APP_CAPTCHA_SITE_KEY=          # Public key for frontend widget

# ── PRODUCT ANALYTICS ──────────────────────────────────────────────────

POSTHOG_API_KEY=phc_...              # Server-side PostHog key (events from backend)
REACT_APP_POSTHOG_KEY=phc_...        # Frontend PostHog key

# ── BACKGROUND JOBS (Phase 2) ──────────────────────────────────────────

# CELERY_BROKER_URL=redis://...      # Same as REDIS_URL (Phase 2 only)
# CELERY_RESULT_BACKEND=redis://...  # Same as REDIS_URL (Phase 2 only)

# ── ROTATION (temporary, during key rotation only) ─────────────────────

ENCRYPTION_KEY_OLD=                  # Set to old key BEFORE rotating ENCRYPTION_KEY
```

---

## 9.5 DNS Structure

```
telegizer.com         → Vercel (landing page redirect or landing app)
app.telegizer.com     → Vercel (React SPA)
api.telegizer.com     → Railway (Flask API)
status.telegizer.com  → Statuspage.io or self-hosted status page
```

---

## 9.6 CI/CD Flow

```
GitHub Repository
  │
  ├── push to main ─────────────────────────────────────────┐
  │                                                          │
  │   ┌─────────────────────────────────────────────────┐  │
  │   │  GitHub Actions CI                              │  │
  │   │  1. python -m pytest backend/tests/             │  │
  │   │  2. npm test --watchAll=false (frontend)        │  │
  │   │  3. npm run build (check no build errors)       │  │
  │   │  On failure: block deploy, notify Slack/email   │  │
  │   └─────────────────────────────────────────────────┘  │
  │                                                          │
  │   If CI passes:                                          │
  │   ┌─────────────────────────────────────────────────┐  │
  │   │  Railway auto-deploy                            │  │
  │   │  1. Build Docker image (nixpacks)               │  │
  │   │  2. Run release command: python migrate.py      │  │
  │   │  3. Health check /ready → must return 200       │  │
  │   │  4. Traffic switched to new deployment          │  │
  │   └─────────────────────────────────────────────────┘  │
  │                                                          │
  │   ┌─────────────────────────────────────────────────┐  │
  │   │  Vercel auto-deploy (frontend)                  │  │
  │   │  1. npm run build                               │  │
  │   │  2. Deploy static files to Vercel CDN           │  │
  │   │  3. Instant rollback available via Vercel UI    │  │
  │   └─────────────────────────────────────────────────┘  │
  └──────────────────────────────────────────────────────────┘
```

---

## 9.7 Monitoring Stack

```
Error tracking:   Sentry
  - Flask backend: FlaskIntegration + SqlalchemyIntegration
  - React frontend: Sentry React SDK
  - Alert rules: error rate > 1% in 5min → email to ADMIN_EMAILS
  - Release tracking: set release=APP_VERSION in sentry.init()

Uptime monitoring:  Railway health checks
  - /ready endpoint polled every 30s
  - Alert on non-200 response

Logging: pythonjsonlogger (structured JSON to Railway log drain)
  - Log levels: DEBUG (dev) → INFO (prod)
  - Bot errors: captured to Sentry + logged
  - Payment events: logged at INFO with payment_id (no amounts in logs)
  - Auth failures: logged at WARNING with ip_hash (no email/password)

Performance:
  - Railway metrics: CPU, memory, response time
  - Database: slow query log > 500ms
  - No APM tool for MVP (add Datadog/New Relic at scale)
```

---

## 9.8 Backup Strategy

```
PostgreSQL (Railway managed):
  - Automatic daily snapshots (7-day retention on Railway Pro plan)
  - Before major deploys: manual snapshot via Railway CLI
  - Restore procedure: Railway dashboard → Database → Restore from snapshot

Redis:
  - JWT blacklist: acceptable to lose on Redis restart
    (users logged out via logout endpoint will be re-admitted, but tokens
     expire within 1 day anyway — tolerable risk for MVP)
  - No backup required for Redis in current architecture

Bot tokens / API keys:
  - Encrypted in PostgreSQL (backed up with DB)
  - ENCRYPTION_KEY stored in Railway env vars
  - Railway env vars not automatically backed up — store ENCRYPTION_KEY
    in a password manager or secrets manager separately
```

---

## 9.9 Local Development Setup

```bash
# 1. Prerequisites
# - Python 3.11+
# - Node 18+
# - PostgreSQL (local or Docker)
# - Redis (local or Docker — optional)

# 2. Clone repo
git clone https://github.com/your-org/telegizer
cd telegizer

# 3. Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r ../requirements.txt

# Create .env from example
cp ../.env.example .env

# Edit .env — minimum required for dev:
# SECRET_KEY=dev-secret-key-change-me
# JWT_SECRET_KEY=dev-jwt-secret-change-me
# ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# DATABASE_URL=sqlite:///dev.db  (or postgresql://localhost/telegizer_dev)
# ADMIN_EMAILS=your@email.com
# FRONTEND_URL=http://localhost:3000
# ALLOWED_ORIGINS=http://localhost:3000

# Run migrations
python migrate.py

# Start Flask (development mode)
python app.py
# → API available at http://localhost:5000

# 4. Frontend setup
cd ../frontend
npm install

# Create .env.local
echo "REACT_APP_API_URL=http://localhost:5000" > .env.local

# Start React dev server
npm start
# → Frontend available at http://localhost:3000

# 5. Telegram bot (optional for local dev)
# Set TELEGRAM_BOT_TOKEN in backend/.env
# The bot starts automatically when Flask starts
# For testing: use @BotFather to create a test bot with a separate token
```

---

# 10. ANALYTICS & REPORTING

## 10.1 Analytics Data Model

```
Data flows into two separate analytics systems:

System A: Bot Events (official bot groups)
  Source: official_bot.py → BotEvent records
  Events: member_joined, member_left, verification_passed/failed,
          automod_action, command_triggered, level_up, etc.
  Aggregation: GROUP BY event_type, date
  API: GET /api/official-groups/:id/analytics

System B: Custom Bot Groups
  Source: bot_features/ handlers → AuditLog, Member records
  Aggregation: COUNT members, messages, mod actions
  API: GET /api/analytics/:botId/:groupId
```

---

## 10.2 Group Analytics Response Shape

```json
GET /api/official-groups/:id/analytics?period=30d

{
  "success": true,
  "data": {
    "period": "30d",
    "group_id": "123",
    "group_title": "Crypto Hub",
    "summary": {
      "total_members": 1247,
      "new_members_period": 89,
      "messages_period": 4320,
      "verifications_passed": 76,
      "verifications_failed": 13,
      "automod_actions": 22,
      "commands_triggered": 156
    },
    "member_growth": [
      { "date": "2026-04-08", "new_members": 3, "cumulative": 1158 },
      { "date": "2026-04-09", "new_members": 7, "cumulative": 1165 }
    ],
    "event_breakdown": [
      { "event_type": "member_joined", "count": 89 },
      { "event_type": "verification_passed", "count": 76 },
      { "event_type": "automod_action", "count": 22 },
      { "event_type": "command_triggered", "count": 156 }
    ],
    "automod_breakdown": [
      { "rule": "link_filter", "count": 15 },
      { "rule": "caps_filter", "count": 7 }
    ],
    "top_commands": [
      { "command": "/rules", "count": 54 },
      { "command": "/links", "count": 38 }
    ],
    "hourly_activity": [
      { "hour": 9, "message_count": 180 },
      { "hour": 10, "message_count": 320 }
    ]
  }
}
```

---

## 10.3 Analytics Overview (Cross-Group)

```json
GET /api/official-groups/analytics/overview?period=30d

{
  "success": true,
  "data": {
    "total_groups": 3,
    "active_groups": 3,
    "total_members_all_groups": 3842,
    "new_members_period": 203,
    "total_messages_period": 12400,
    "total_automod_actions_period": 67,
    "groups": [
      {
        "group_id": "123", "title": "Crypto Hub",
        "member_count": 1247, "new_members": 89,
        "activity_level": "high"
      }
    ]
  }
}
```

---

## 10.4 Analytics Hub Frontend

```
/analytics (tabbed)
  │
  ├── Overview tab
  │     Cross-group stats cards
  │     Member growth chart (all groups combined)
  │     Top groups by activity table
  │
  ├── Groups tab
  │     [Group selector dropdown]
  │     ↓ renders OfficialGroupAnalytics for selected group
  │       • Summary stats row
  │       • Member growth chart (Recharts LineChart)
  │       • Event breakdown (Recharts PieChart)
  │       • Automod breakdown (Recharts BarChart)
  │       • Top commands table
  │       • Hourly activity heatmap
  │
  └── Channels tab
        [Channel selector dropdown]
        ↓ renders ChannelDetail stats for selected channel
          • Subscriber count
          • Growth chart
          • Post engagement stats

Date range selector: [7d] [30d] [90d] [Custom]
→ Passes period param to API, re-fetches on change
```

---

## 10.5 Digest Analytics

```
Each sent digest logged in DigestLog:
  { group_id, user_id, content_preview, provider, tokens_used, sent_at }

Frontend (Digests page — history drawer):
  GET /api/telegram-groups/:id/digest/history
  Shows: date, time, preview (first 200 chars of summary), tokens used, provider

Token usage analytics (AI Settings page):
  GET /api/workspace/ai-settings
  Shows: tokens_used_today, limit, percentage bar
  Resets daily at midnight UTC

Future (Phase 2):
  GET /api/analytics/assistant?period=30d
  → notes created per day, digests sent, reminders completed, AI tokens by feature
```

---

## 10.6 Data Export

```python
# GET /api/auth/export
# Returns all user data as downloadable JSON (GDPR compliance)

@auth_bp.route('/api/auth/export')
@jwt_required()
@limiter.limit("1 per day")
def export_data():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    data = {
        'exported_at': datetime.utcnow().isoformat(),
        'account': {
            'email': user.email,
            'full_name': user.full_name,
            'timezone': user.timezone,
            'subscription_tier': user.subscription_tier,
            'created_at': user.created_at.isoformat(),
        },
        'telegram_accounts': [
            {'telegram_id': a.telegram_id, 'username': a.telegram_username}
            for a in user.telegram_accounts
        ],
        'bots': [
            {'username': b.username, 'created_at': b.created_at.isoformat()}
            for b in user.bots
        ],
        'groups': [
            {'title': g.title, 'linked_at': g.linked_at.isoformat()}
            for g in user.telegram_groups
        ],
        'notes': [
            {'content': n.content, 'source': n.source,
             'tags': n.tags, 'created_at': n.created_at.isoformat()}
            for n in Note.query.filter_by(user_id=user_id).all()
        ],
        'reminders': [
            {'text': r.text, 'remind_at': r.remind_at.isoformat(), 'is_sent': r.is_sent}
            for r in WorkspaceReminder.query.filter_by(user_id=user_id).all()
        ],
        'payment_history': [
            {'plan': p.plan, 'amount': float(p.amount), 'currency': p.currency,
             'status': p.status, 'created_at': p.created_at.isoformat()}
            for p in PaymentHistory.query.filter_by(user_id=user_id).all()
        ],
    }
    # Exclude: password_hash, encrypted tokens, admin fields
    
    return Response(
        json.dumps(data, indent=2),
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="telegizer-export-{user_id}.json"'
        }
    )
```

---

## 10.6 Product Analytics (User Behavior Tracking)

> **Critical Launch Requirement:** Bot events (Section 10.1) track group activity. Product analytics track *user* behavior within the Telegizer dashboard. Without product analytics, there is no visibility into onboarding drop-off, feature adoption, conversion funnels, or retention cohorts. These metrics are mandatory for any data-driven growth decisions.

### Integration: PostHog

PostHog (open-source, self-hostable) is the recommended tool. The free cloud tier covers up to 1M events/month.

```javascript
// frontend/src/index.js — initialize PostHog
import posthog from 'posthog-js'

if (process.env.REACT_APP_POSTHOG_KEY) {
  posthog.init(process.env.REACT_APP_POSTHOG_KEY, {
    api_host: 'https://app.posthog.com',
    autocapture: false,          // manual events only — avoid noise
    capture_pageview: true,      // automatic page views
    disable_session_recording: false,  // enable for UX debugging (anonymized)
  })
}
```

```javascript
// frontend/src/services/analytics.js — centralized event tracking
import posthog from 'posthog-js'

export const analytics = {
  identify: (user) => posthog.identify(String(user.id), {
    email: user.email,
    plan: user.subscription_tier,
    created_at: user.created_at,
  }),
  
  // Onboarding funnel
  track: {
    userRegistered:      ()  => posthog.capture('user_registered'),
    emailVerified:       ()  => posthog.capture('email_verified'),
    groupLinked:         (g) => posthog.capture('group_linked', { group_id: g.id }),
    firstFeatureEnabled: (f) => posthog.capture('first_feature_enabled', { feature: f }),
    onboardingComplete:  ()  => posthog.capture('onboarding_complete'),
    
    // Upgrade funnel
    planGateHit:     (feature, plan) => posthog.capture('plan_gate_hit', { feature, required_plan: plan }),
    upgradeClicked:  (plan, trigger) => posthog.capture('upgrade_clicked', { plan, trigger }),
    checkoutOpened:  (plan)          => posthog.capture('checkout_opened', { plan }),
    paymentComplete: (plan, amount)  => posthog.capture('payment_complete', { plan, amount }),
    
    // Feature adoption
    digestEnabled:      (group_id) => posthog.capture('digest_enabled', { group_id }),
    digestReceived:     ()         => posthog.capture('digest_received'),
    noteCreated:        (source)   => posthog.capture('note_created', { source }),
    reminderCreated:    ()         => posthog.capture('reminder_created'),
    autoReplyCreated:   ()         => posthog.capture('auto_reply_created'),
    customBotAdded:     ()         => posthog.capture('custom_bot_added'),
    
    // Retention signals
    dashboardOpened:    ()         => posthog.capture('dashboard_opened'),
    hubOpened:          ()         => posthog.capture('hub_opened'),
    sessionStart:       ()         => posthog.capture('session_start'),
  },
  
  reset: () => posthog.reset(),  // call on logout
}
```

### Key Funnels to Monitor

```
Acquisition Funnel:
  Landing → Register → Email Verified → Group Linked → First Feature Enabled

Activation Funnel (the "aha moment"):
  Group Linked → Digest Enabled → First Digest Received

Upgrade Funnel:
  Plan Gate Hit → Upgrade Clicked → Checkout Opened → Payment Complete

Retention Signal:
  DAU/WAU/MAU · Feature adoption by plan · Digest open rate (via Telegram)
```

### Backend Event Tracking

```python
# backend/utils/analytics.py
# Server-side events for conversion attribution (payments, plan changes)
# Uses PostHog Python SDK or direct HTTP API

import httpx

def track_server_event(user_id: int, event: str, properties: dict = None):
    """Fire a server-side PostHog event. Non-blocking — runs in background thread."""
    if not config.POSTHOG_API_KEY:
        return
    
    def _send():
        try:
            httpx.post('https://app.posthog.com/capture/', json={
                'api_key': config.POSTHOG_API_KEY,
                'event': event,
                'distinct_id': str(user_id),
                'properties': properties or {},
                'timestamp': datetime.utcnow().isoformat(),
            }, timeout=5)
        except Exception:
            pass  # analytics failures must never affect product behavior
    
    threading.Thread(target=_send, daemon=True).start()

# Usage in billing route:
track_server_event(user.id, 'payment_confirmed', {
    'plan': plan, 'amount_usd': amount, 'interval': interval
})
```

---

*Phase 3 complete. Sections 7–10 documented.*

---

# 11. MONETIZATION ARCHITECTURE

## 11.1 Plan Definitions

```python
# backend/config.py — plan limits (all enforced server-side)

PLAN_LIMITS = {
    'free': {
        'max_bots':              1,
        'max_custom_bots':       0,    # custom bots not available on free
        'max_groups_per_bot':    1,
        'ai_tokens_per_day':     10_000,
        'knowledge_storage_mb':  10,
        'scheduled_messages':    5,
        'auto_responses':        10,
        'webhooks':              0,
        'crm':                   False,
        'digests':               False,
        'api_access':            False,
        'white_label':           False,
        'marketplace':           False,
    },
    'pro': {
        'max_bots':              3,
        'max_custom_bots':       3,
        'max_groups_per_bot':    None,  # unlimited
        'ai_tokens_per_day':     500_000,
        'knowledge_storage_mb':  500,
        'scheduled_messages':    100,
        'auto_responses':        50,
        'webhooks':              10,
        'crm':                   True,
        'digests':               True,
        'api_access':            True,
        'white_label':           False,
        'marketplace':           False,
    },
    'enterprise': {
        'max_bots':              50,
        'max_custom_bots':       50,
        'max_groups_per_bot':    None,
        'ai_tokens_per_day':     500_000,
        'knowledge_storage_mb':  10_000,
        'scheduled_messages':    None,
        'auto_responses':        None,
        'webhooks':              None,
        'crm':                   True,
        'digests':               True,
        'api_access':            True,
        'white_label':           True,
        'marketplace':           True,
    },
}

PLAN_PRICES = {
    'pro':        {'monthly': 19.00,  'annual': 152.00},   # ~$12.67/mo, 33% savings
    'enterprise': {'monthly': 49.00,  'annual': 392.00},   # ~$32.67/mo, 33% savings
}
```

---

## 11.1.1 Subscription Lifecycle System

> **Critical Revenue Requirement:** NOWPayments processes one-time payments only — it does not manage recurring subscriptions. Without an explicit expiry system, users who pay once for "Pro Monthly" retain Pro forever. The `subscription_expires_at` field (added to the users table in Section 6.2) powers the entire lifecycle.

### Payment → Subscription Flow

```python
# backend/routes/billing.py — nowpayments-webhook handler (enhanced)

def _handle_successful_payment(user, plan, interval, amount_paid):
    """Called after webhook validation. Sets subscription expiry."""
    now = datetime.utcnow()
    
    # Calculate expiry
    if interval == 'monthly':
        expires_at = now + timedelta(days=31)
    elif interval == 'annual':
        expires_at = now + timedelta(days=366)
    else:
        expires_at = now + timedelta(days=31)  # default
    
    grace_until = expires_at + timedelta(days=7)  # 7-day grace period
    
    user.subscription_tier = plan
    user.subscription_interval = interval
    user.subscription_expires_at = expires_at
    user.subscription_grace_until = grace_until
    
    # Record subscription period
    SubscriptionRenewal.create(
        user_id=user.id,
        plan=plan,
        interval=interval,
        period_start=now,
        period_end=expires_at,
        payment_id=payment_id,
        status='active'
    )
    
    db.session.commit()
    
    # Notify user of expiry date in confirmation email
    _send_payment_confirmation_email(user, plan, amount_paid, expires_at)
    notifications.create(user.id, 'payment_confirmed',
        f'Your {plan.capitalize()} plan is active until {expires_at.strftime("%B %d, %Y")}.')
    track_server_event(user.id, 'payment_confirmed', {
        'plan': plan, 'interval': interval, 'expires_at': expires_at.isoformat()
    })
```

### Subscription Expiry Downgrade (Daily Cron)

```python
# backend/scheduler.py — runs daily at midnight UTC

def downgrade_expired_subscriptions():
    """Downgrade users whose subscription has expired and grace period has ended."""
    now = datetime.utcnow()
    
    # Users in grace period: keep access, send reminder
    grace_users = User.query.filter(
        User.subscription_expires_at < now,
        User.subscription_grace_until > now,
        User.subscription_tier != 'free',
        User.deleted_at.is_(None)
    ).all()
    
    for user in grace_users:
        days_left = (user.subscription_grace_until - now).days
        if days_left in [7, 3, 1]:  # send reminder at exactly these points
            _send_renewal_reminder_email(user, days_left)
    
    # Users past grace period: downgrade
    expired_users = User.query.filter(
        User.subscription_grace_until < now,
        User.subscription_tier != 'free',
        User.deleted_at.is_(None)
    ).all()
    
    for user in expired_users:
        old_tier = user.subscription_tier
        user.subscription_tier = 'free'
        user.subscription_expires_at = None
        user.subscription_grace_until = None
        user.subscription_interval = None
        
        # Mark subscription as expired
        current = SubscriptionRenewal.query.filter_by(
            user_id=user.id, status='active'
        ).first()
        if current:
            current.status = 'expired'
        
        db.session.commit()
        
        # Notify user
        _send_subscription_expired_email(user, old_tier)
        notifications.create(user.id, 'subscription_expired',
            f'Your {old_tier.capitalize()} subscription has expired. Renew to restore access.')
        track_server_event(user.id, 'subscription_expired', {'old_tier': old_tier})
    
    logger.info(f"Subscription cron: {len(expired_users)} downgraded, {len(grace_users)} in grace")
```

### Billing Page Subscription Status

```python
# GET /api/billing/subscription — enhanced response
{
  "success": true,
  "data": {
    "tier": "pro",
    "interval": "monthly",
    "status": "active",              # active | grace | expired
    "expires_at": "2026-06-08T00:00:00Z",
    "grace_until": "2026-06-15T00:00:00Z",
    "days_remaining": 31,
    "renew_url": null,               # populated when in grace period
    "ai_tokens_today": 12430,
    "ai_tokens_limit": 500000,
  }
}
```

### Payment Provider Strategy

| Provider | Status | Use Case |
|---|---|---|
| **NOWPayments** | ✅ Live | Crypto payments — primary for crypto-native users |
| **Lemon Squeezy** | 🔒 Disabled (legal review pending) | Card payments — required for mainstream adoption |
| **Stripe** | 📋 Planned (Phase 2) | Card + recurring billing — industry standard for SaaS |

> **⚠️ Revenue Risk:** Crypto-only payments create a severe conversion barrier for the target market (community managers, creators, agencies — predominantly non-crypto users). Lemon Squeezy or Stripe must be enabled before any paid user acquisition campaigns. Phase 2 milestone: card payment goes live before any paid marketing spend.

---

## 11.2 Feature Gating Architecture

```javascript
// frontend/src/components/PlanGate.js
// Wraps any Pro/Enterprise-only UI element

const PlanGate = ({ requiredPlan = 'pro', feature, children }) => {
  const user = useUser();  // from AuthContext
  const TIER_RANK = { free: 0, pro: 1, enterprise: 2 };
  
  const hasAccess = TIER_RANK[user?.subscription_tier] >= TIER_RANK[requiredPlan];
  
  if (hasAccess) return children;
  
  return (
    <PlanGateOverlay
      requiredPlan={requiredPlan}
      feature={feature}
      currentPlan={user?.subscription_tier}
    />
  );
};

// PlanGateOverlay — shown instead of feature content
const PlanGateOverlay = ({ requiredPlan, feature, currentPlan }) => (
  <Box sx={{ position: 'relative', filter: 'blur(4px) brightness(0.4)',
             pointerEvents: 'none', userSelect: 'none', minHeight: 120 }}>
    {/* Blurred preview of feature */}
    <Box sx={{
      position: 'absolute', inset: 0,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      filter: 'none', pointerEvents: 'auto',
      zIndex: 10,
    }}>
      <LockOutlined sx={{ fontSize: 40, color: 'primary.main', mb: 1 }} />
      <Typography variant="h6" align="center">
        {feature} requires {capitalize(requiredPlan)}
      </Typography>
      <Typography variant="body2" color="text.secondary" align="center" sx={{ mb: 2 }}>
        You're on {capitalize(currentPlan)}. Upgrade to unlock this feature.
      </Typography>
      <Button variant="contained" component={Link} to="/billing">
        Upgrade to {capitalize(requiredPlan)} — ${PLAN_PRICES[requiredPlan].monthly}/mo
      </Button>
    </Box>
  </Box>
);
```

**Pages with PlanGate applied:**
1. `/workspace/digests` — Pro required
2. `/workspace/ai-settings` — Pro required (AI token usage visible to free, key config is Pro)
3. `/groups/:id/crm` — Pro required
4. Bot webhooks section in Group Settings — Pro required
5. `/marketplace` (selling) — Enterprise required
6. `/workspace/assistant-bot` — Pro required

---

## 11.3 Upgrade Flow (End-to-End)

```
1. User hits plan gate → clicks [Upgrade to Pro]
2. Lands on /billing → sees plan comparison table
3. Selects plan + interval (monthly/annual)
4. Clicks [Pay with Crypto]

5. Frontend:
   POST /api/billing/create-checkout { plan: 'pro', interval: 'monthly' }
   → Returns { payment_url, payment_id, amount_usd }
   → window.location.href = payment_url (redirect to NOWPayments)

6. NOWPayments:
   - User selects crypto currency (BTC, ETH, USDT, etc.)
   - NOWPayments shows exact crypto amount at current rates
   - User pays from wallet

7. NOWPayments → Telegizer:
   POST /api/billing/nowpayments-webhook
   Headers: x-nowpayments-sig: <hmac-sha512>
   
   Backend validation:
   a) Verify HMAC-SHA512 signature
   b) Check ProcessedPayment.payment_id (idempotency)
   c) Validate amount_paid ≥ amount_usd × 0.99 (1% tolerance)
   d) Validate timestamp within 1 hour
   e) If payment_status == 'finished':
      - User.subscription_tier = plan
      - Create ProcessedPayment record
      - Create PaymentHistory record
      - Create in-app notification: "Payment confirmed!"
      - Send confirmation email
      - Return 200

8. User sees /payment/success?status=success
   (NOWPayments redirects to cancel_url=/payment/success?status=failed on cancel)

9. Dashboard shows Pro badge immediately on next load
   (GET /api/auth/me returns updated subscription_tier)
```

---

## 11.4 Billing Page Layout

```
/billing

┌───────────────────────────────────────────────────────────────────┐
│  Current Plan: FREE                                               │
│  Status: Active  ·  Member since: Jan 2026                        │
│                                                                   │
│  AI tokens today: ████░░░░░░ 3,200 / 10,000                      │
│  [Refresh Subscription]                                           │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Upgrade Your Plan                                                │
│                          [Monthly]  [Annual — Save 33%]           │
│                                                                   │
│  ┌─────────────────┐ ┌────────────────────┐ ┌──────────────────┐ │
│  │  FREE           │ │  PRO  ← popular    │ │  ENTERPRISE      │ │
│  │  $0             │ │  $19/mo            │ │  $49/mo          │ │
│  │                 │ │  $152/yr           │ │  $392/yr         │ │
│  │  ✓ 1 bot        │ │  ✓ 3 bots          │ │  ✓ 50 bots       │ │
│  │  ✓ 1 group      │ │  ✓ Unlimited groups│ │  ✓ All Pro       │ │
│  │  ✓ 10k AI/day   │ │  ✓ 500k AI/day     │ │  ✓ White-label   │ │
│  │  ✗ Digests      │ │  ✓ Digests         │ │  ✓ Full API      │ │
│  │  ✗ CRM          │ │  ✓ CRM             │ │  ✓ Marketplace   │ │
│  │  ✗ Webhooks     │ │  ✓ Webhooks        │ │  ✓ Dedicated     │ │
│  │                 │ │                    │ │    support       │ │
│  │  [Current]      │ │  [Upgrade →]       │ │  [Upgrade →]     │ │
│  └─────────────────┘ └────────────────────┘ └──────────────────┘ │
│                                                                   │
│  Payment History                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  May 1, 2026 · Pro Monthly · $19.00 · BTC · ✓ Completed    │ │
│  │  Apr 1, 2026 · Pro Monthly · $19.00 · ETH · ✓ Completed    │ │
│  └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘

Notes:
- Card payments (Lemon Squeezy): UI option HIDDEN until re-enabled
- Annual toggle: changes displayed price and interval param sent to backend
- [Refresh Subscription]: calls GET /api/billing/subscription to re-check status
  (handles case where webhook was delayed or missed)
```

---

## 11.5 Plan Enforcement (Backend)

```python
# Enforced at API layer — frontend gates are UX only, never security

def check_bot_limit(user):
    count = Bot.query.filter_by(user_id=user.id, is_active=True).count()
    limit = config.PLAN_LIMITS[user.subscription_tier]['max_bots']
    if count >= limit:
        raise PlanLimitError(
            f"Your {user.subscription_tier} plan allows {limit} bot(s). "
            f"Upgrade to add more."
        )

def check_group_limit(user, bot_id):
    limit = config.PLAN_LIMITS[user.subscription_tier]['max_groups_per_bot']
    if limit is None:
        return  # unlimited
    count = Group.query.filter_by(bot_id=bot_id).count()
    if count >= limit:
        raise PlanLimitError(
            f"Your {user.subscription_tier} plan allows {limit} group(s) per bot."
        )

def check_feature_access(user, feature: str):
    if not config.PLAN_LIMITS[user.subscription_tier].get(feature, False):
        raise PlanLimitError(
            f"The '{feature}' feature requires a Pro or Enterprise plan."
        )
```

---

# 12. FULL USER FLOWS

## 12.1 New User Onboarding (Complete)

```
HAPPY PATH:
────────────
[1] Visit telegizer.com → Landing page
[2] Click [Get Started Free]
[3] Register: name + email + password
    ↓ POST /api/auth/register
    ← 201: { token (email_verify_pending scope) }
[4] Redirect to /verify-email
    Page shows: "Check your inbox for a verification link"
    ← Email sent: "Verify your Telegizer account"
[5] User clicks link in email
    ↓ POST /api/auth/verify-email { token }
    ← 200: { token (full scope), user }
[6] Redirect to /dashboard (first-time experience)
    → Welcome modal displayed (dismissed on close, never shown again)
    → Onboarding checklist visible (bottom of Dashboard)
[7] Onboarding step 1: Add bot to group
    → Click [Generate Link Code]
    ↓ POST /api/telegram-groups/pending-link
    ← { code: "TLG-A3F8C2B1", expires_at: "..." }
    → Dialog shows code + countdown + copy button + Telegram deep link
[8] User adds @TelegizerBot to Telegram group
    → Sends /linkgroup TLG-A3F8C2B1 in group
    → Bot confirms in group: "✓ Linked to Telegizer!"
    → Bot DMs user: "Your group '[title]' has been connected."
[9] Dashboard auto-detects new group (10s poll)
    → Dialog closes, toast: "🎉 Your group 'GroupName' is now connected!"
    → Redirect to /groups/ID (group settings)
[10] Onboarding step 2: Configure first feature
    → User enables Daily Digest or sets up Auto-Reply
[11] Checklist complete → checklist card hides automatically

FAILURE STATES:
───────────────
Step 3 — Email already exists:
  → 409 error → inline: "An account with this email already exists. [Log in]"

Step 5 — Verification token expired (>24h):
  → 400 error → page: "This verification link has expired."
  → CTA: [Resend verification email]

Step 5 — Resend rate limit (already resent within 1h):
  → 429 error → "Verification email already sent. Please wait X minutes."

Step 7 — Link code expired (>12min):
  → Error in dialog: "Code expired. Generate a new one."
  → [Generate New Code] button

Step 8 — Not admin in Telegram group:
  → Bot replies in group: "Only group admins can link a group."
  → User needs to be promoted to admin first
```

---

## 12.2 Custom Bot Creation Flow

```
HAPPY PATH:
────────────
[1] /custom-bots → [+ Add Bot]
[2] Modal: "Enter your bot token from @BotFather"
    Field: bot_token (password-type input)
[3] Submit → [Adding...]
    ↓ POST /api/bots { token: "..." }
    → Backend validates token via Telegram API (async, ThreadPoolExecutor)
    → Encrypts token via Fernet
    ← 201: { id, username, display_name, health_status: 'healthy' }
[4] Modal closes → toast: "Bot @username added successfully!"
    → Bot card appears in list immediately
[5] User clicks [Manage] → /bot/:id
    → Configure groups, commands, settings

FAILURE STATES:
───────────────
Invalid token:
  → Telegram API returns 401
  → 400: "Invalid bot token. Please check the token from @BotFather."

Plan limit reached:
  → 403 PLAN_LIMIT_REACHED
  → PlanGate modal: "Upgrade to Pro to add more custom bots."

Token already used by another user:
  → 409 ALREADY_EXISTS
  → "This bot token is already registered on another account."
```

---

## 12.3 Subscription Upgrade Flow

```
HAPPY PATH:
────────────
[1] User hits PlanGate on Pro feature → [Upgrade to Pro]
    OR /billing → selects Pro → [Pay with Crypto]
[2] Toggle Monthly/Annual to choose interval
[3] Click [Upgrade to Pro — $19/mo]
    ↓ POST /api/billing/create-checkout { plan: 'pro', interval: 'monthly' }
    ← { payment_url: "https://nowpayments.io/...", payment_id: "..." }
[4] window.location.href = payment_url
    → User leaves Telegizer, lands on NOWPayments
[5] NOWPayments: user selects crypto, copies wallet address, sends payment
[6] NOWPayments webhook fires to /api/billing/nowpayments-webhook
[7] Backend: verify → upgrade → notify
    → User.subscription_tier = 'pro'
    → Email: "Payment confirmed — you're now on Pro!"
    → In-app notification created
[8] User returns to Telegizer (or was on another tab)
    → Lands on /payment/success?status=success
    → Page: "🎉 You're now on Pro! All Pro features are unlocked."
    → [Go to Dashboard] button
[9] Dashboard: plan badge shows "PRO"
    → Previously locked features now accessible

FAILURE STATES:
───────────────
Payment cancelled (user closed NOWPayments):
  → NOWPayments redirects to /payment/success?status=failed
  → Page: "Payment cancelled. Your plan was not changed." [Try Again]

Payment underpaid (sent less than 99% of expected):
  → Webhook: amount check fails
  → No plan upgrade, payment history shows 'failed'
  → In-app notification: "Payment received but amount was insufficient."

Webhook received twice (network retry):
  → ProcessedPayment check: payment_id already exists → 200 but no double-upgrade

User doesn't return to site (stays on NOWPayments):
  → Webhook still upgrades the plan in background
  → Next time user opens Telegizer → Pro badge visible
  → [Refresh Subscription] button on /billing re-checks status
```

---

## 12.4 Moderation Setup Flow

```
HAPPY PATH:
────────────
[1] /groups/:id → Settings → AutoMod tab
[2] Enable Link Filter:
    - Toggle ON
    - Action: [Warn ▾] (options: Warn / Mute 1hr / Ban)
    - Exempt admins: [✓]
    - Warning message auto-delete: [30s ▾]
[3] Enable Caps Filter:
    - Toggle ON
    - Threshold: [70% ▾]
    - Action: [Warn ▾]
[4] [Save Settings]
    ↓ PUT /api/official-groups/:id/settings { automod: {...} }
    ← 200: { success: true }
    → Toast: "Settings saved"
[5] Test: Send a link in the group
    → Bot deletes message, sends warning, auto-deletes warning after 30s
    → BotEvent logged: automod_action

EDGE CASES:
───────────
Bot lacks can_delete_messages permission:
  → Settings save succeeds (settings are stored regardless)
  → Bot attempts delete → Telegram 400 error
  → BotEvent logged with error flag
  → Permission score card on /groups shows warning: "Missing: Delete Messages"

Bot lacks can_restrict_members:
  → Mute action fails silently
  → Bot falls back to warning if mute fails
```

---

## 12.5 AI Assistant Setup Flow

```
HAPPY PATH:
────────────
[1] /workspace/ai-settings
    → Platform key status: ● Active (if PLATFORM_GEMINI_API_KEY set)
    → Telegram account: ○ Not connected
[2] Connect Telegram account:
    → Click [Connect via @TelegizerBot]
    ↓ POST /api/telegram-account/generate-connect-code
    ← { code: "CONNECT-XXXX", instructions: "..." }
    → Dialog: "DM @TelegizerBot: /connect CONNECT-XXXX"
[3] User DMs bot the connect code
    → Bot links Telegram ID to user account
    → Dialog closes, toast: "Telegram connected as @username"
[4] (Optional) Add own API key:
    → Click [OpenAI] tab
    → Paste API key
    → [Test] → ← { valid: true, model_tested: "gpt-4o" }
    → [Save]
[5] /workspace/digests → Enable digest for a group
    → Select: Daily at 9:00 AM, delivery: My DM
    → [Save]
[6] Next day at 9:00 AM:
    → Scheduler fires send_daily_digests()
    → digest_ai.py generates digest via Gemini
    → Bot DMs user the structured digest
    → DigestLog created
    → Hub shows: "✓ Sent 9:02am — 3 decisions captured"
```

---

## 12.6 Workflow Automation Setup

```
HAPPY PATH:
────────────
[1] /workspace/automations → [+ New Workflow]
[2] Configure trigger:
    - Type: [Message contains ▾]
    - Trigger text: "price"
[3] Configure action:
    - Type: [Send message ▾]
    - Message: "Current price: Check pinned message or visit [link]"
    - Send to: [Same group ▾]
[4] [Save Workflow]
    ↓ POST /api/automations { trigger_type, trigger_text, action_type, action_data, group_ids }
    ← 201: { id, ... }
[5] Test: Send "price?" in the group
    → Bot responds within 2 seconds with the configured message
    → AutomationExecution logged (for Hub activity card)

EDGE CASES:
───────────
Circular trigger (bot message triggers itself):
  → Bot ignores messages from other bots and from itself
  → Check: message.from_user.is_bot → skip automod and auto-responses

Multiple matching triggers:
  → All matching rules fire (not first-match-only)
  → Ordered by created_at ascending

Trigger with regex type:
  → Pro feature only
  → Validated server-side before save: invalid regex → 422
```

---

# 13. UI COMPONENT SYSTEM

## 13.1 Core Component Library

All components are MUI-based, customized via `sx` prop and theme overrides.

### StatCard
```javascript
// Used throughout Dashboard, Analytics, Hub
const StatCard = ({ icon: Icon, label, value, delta, deltaLabel, onClick, color = 'primary' }) => (
  <Card
    onClick={onClick}
    sx={{
      cursor: onClick ? 'pointer' : 'default',
      transition: 'all 0.2s',
      '&:hover': onClick ? {
        borderColor: 'primary.main',
        transform: 'translateY(-2px)',
        boxShadow: '0 4px 16px rgba(108,99,255,0.15)',
      } : {},
    }}
  >
    <CardContent sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
        <Box sx={{
          width: 44, height: 44, borderRadius: 2,
          background: `rgba(108, 99, 255, 0.12)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          <Icon sx={{ color: 'primary.main', fontSize: 22 }} />
        </Box>
        {delta !== undefined && (
          <Chip
            label={`${delta > 0 ? '+' : ''}${delta}%`}
            size="small"
            color={delta >= 0 ? 'success' : 'error'}
          />
        )}
      </Box>
      <Typography variant="h3">{value}</Typography>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      {deltaLabel && (
        <Typography variant="caption" color="text.disabled">{deltaLabel}</Typography>
      )}
    </CardContent>
  </Card>
);
```

### StatusDot
```javascript
const StatusDot = ({ status }) => {
  const colors = { healthy: '#4ADE80', degraded: '#FBBF24', offline: '#F87171', unknown: '#6B7280' };
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
        background: colors[status] || colors.unknown,
        animation: status === 'healthy' ? 'pulseGreen 2s infinite' : 'none',
        boxShadow: status === 'healthy' ? `0 0 0 3px ${colors.healthy}33` : 'none',
      }}
    />
  );
};
```

### PlanBadge
```javascript
const PLAN_COLORS = {
  free:       { bg: '#2A2A3D', color: '#8B8FA8', label: 'Free' },
  pro:        { bg: 'rgba(108, 99, 255, 0.15)', color: '#6C63FF', label: 'Pro' },
  enterprise: { bg: 'rgba(251, 191, 36, 0.15)', color: '#FBBF24', label: 'Enterprise' },
};

const PlanBadge = ({ tier, size = 'small' }) => {
  const plan = PLAN_COLORS[tier] || PLAN_COLORS.free;
  return (
    <Chip
      label={plan.label}
      size={size}
      sx={{ background: plan.bg, color: plan.color, fontWeight: 600, fontSize: '0.7rem' }}
    />
  );
};
```

### SourceBadge (Notes)
```javascript
const SOURCE_BADGES = {
  manual: { label: 'Manual', color: '#3B82F6', bg: 'rgba(59, 130, 246, 0.12)' },
  ai:     { label: 'AI',     color: '#4ADE80', bg: 'rgba(74, 222, 128, 0.12)' },
  bot:    { label: 'Bot',    color: '#F97316', bg: 'rgba(249, 115, 22, 0.12)' },
};

const SourceBadge = ({ source }) => {
  const s = SOURCE_BADGES[source] || SOURCE_BADGES.manual;
  return (
    <Chip label={s.label} size="small"
          sx={{ background: s.bg, color: s.color, fontWeight: 600 }} />
  );
};
```

---

## 13.2 Data Display Components

### DataTable
```javascript
// Reusable table with built-in pagination, empty state, loading skeleton
const DataTable = ({
  columns,        // [{ id, label, render, width, align }]
  rows,           // array of data objects
  loading,
  emptyState,     // { icon, title, description, action }
  pagination,     // { page, totalPages, onPageChange }
  onRowClick,
}) => {
  if (loading) return <TableSkeleton rows={5} />;
  if (!rows.length) return <EmptyState {...emptyState} />;
  
  return (
    <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
      <Table>
        <TableHead>
          <TableRow>
            {columns.map(col => (
              <TableCell key={col.id} sx={{ width: col.width, textAlign: col.align }}>
                <Typography variant="overline">{col.label}</Typography>
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow
              key={row.id || i}
              onClick={() => onRowClick?.(row)}
              sx={{ cursor: onRowClick ? 'pointer' : 'default',
                    '&:hover': { background: 'rgba(255,255,255,0.02)' } }}
            >
              {columns.map(col => (
                <TableCell key={col.id} sx={{ textAlign: col.align }}>
                  {col.render ? col.render(row) : row[col.id]}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {pagination && (
        <Box sx={{ p: 2, display: 'flex', justifyContent: 'flex-end' }}>
          <Pagination {...pagination} />
        </Box>
      )}
    </TableContainer>
  );
};
```

### AnalyticsChart
```javascript
// Wrapper around Recharts for consistent styling
const AnalyticsChart = ({ type, data, dataKey, xKey = 'date', color = '#6C63FF', height = 200 }) => {
  const tooltipStyle = {
    backgroundColor: '#1E1E2E',
    border: '1px solid #2A2A3D',
    borderRadius: 8,
    color: '#F1F0FF',
  };
  
  if (type === 'line') return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2A2A3D" />
        <XAxis dataKey={xKey} tick={{ fill: '#8B8FA8', fontSize: 12 }} />
        <YAxis tick={{ fill: '#8B8FA8', fontSize: 12 }} />
        <Tooltip contentStyle={tooltipStyle} />
        <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
  
  if (type === 'bar') return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2A2A3D" />
        <XAxis dataKey={xKey} tick={{ fill: '#8B8FA8', fontSize: 12 }} />
        <YAxis tick={{ fill: '#8B8FA8', fontSize: 12 }} />
        <Tooltip contentStyle={tooltipStyle} />
        <Bar dataKey={dataKey} fill={color} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
};
```

---

## 13.3 Modal Patterns

```javascript
// Standard confirmation modal
const ConfirmModal = ({ open, title, message, confirmLabel = 'Confirm',
                        onConfirm, onCancel, destructive = false, loading }) => (
  <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
    <DialogTitle sx={{ pb: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        {destructive
          ? <WarningAmberOutlined sx={{ color: 'error.main' }} />
          : <InfoOutlined sx={{ color: 'primary.main' }} />
        }
        {title}
      </Box>
    </DialogTitle>
    <DialogContent>
      <Typography variant="body2" color="text.secondary">{message}</Typography>
    </DialogContent>
    <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
      <Button onClick={onCancel} disabled={loading}>Cancel</Button>
      <Button
        onClick={onConfirm}
        variant="contained"
        color={destructive ? 'error' : 'primary'}
        disabled={loading}
        startIcon={loading ? <CircularProgress size={16} /> : null}
      >
        {loading ? 'Processing...' : confirmLabel}
      </Button>
    </DialogActions>
  </Dialog>
);

// TypeToConfirm modal (for dangerous actions)
const TypeToConfirmModal = ({ open, onConfirm, onCancel, confirmWord = 'DELETE',
                              title, message }) => {
  const [typed, setTyped] = useState('');
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ color: 'error.main' }}>{title}</DialogTitle>
      <DialogContent>
        <Typography color="text.secondary" gutterBottom>{message}</Typography>
        <Typography variant="body2" sx={{ mt: 2, mb: 1 }}>
          Type <strong>{confirmWord}</strong> to confirm:
        </Typography>
        <TextField
          value={typed} onChange={e => setTyped(e.target.value)}
          placeholder={confirmWord} fullWidth autoFocus
          sx={{ '& .MuiInputBase-input': { fontFamily: 'monospace' } }}
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCancel}>Cancel</Button>
        <Button
          onClick={onConfirm} variant="contained" color="error"
          disabled={typed !== confirmWord}
        >
          {confirmWord}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
```

---

## 13.4 Toast / Notification System

```javascript
// All toasts via a single utility (no direct MUI Snackbar calls in pages)
// Wraps MUI Snackbar + Alert

// Usage:
// import { useToast } from '../contexts/ToastContext';
// const { showSuccess, showError, showWarning, showInfo } = useToast();
// showSuccess('Settings saved!');
// showError('Failed to save: ' + error.message);

// ToastContext.js
const ToastContext = createContext();

export const ToastProvider = ({ children }) => {
  const [queue, setQueue] = useState([]);
  const [current, setCurrent] = useState(null);
  
  const show = (message, severity = 'info', duration = 4000) => {
    const id = Date.now();
    setQueue(prev => [...prev, { id, message, severity, duration }]);
  };
  
  useEffect(() => {
    if (!current && queue.length > 0) {
      setCurrent(queue[0]);
      setQueue(prev => prev.slice(1));
    }
  }, [queue, current]);
  
  return (
    <ToastContext.Provider value={{
      showSuccess: m => show(m, 'success'),
      showError:   m => show(m, 'error', 6000),
      showWarning: m => show(m, 'warning'),
      showInfo:    m => show(m, 'info'),
    }}>
      {children}
      <Snackbar
        open={!!current}
        autoHideDuration={current?.duration}
        onClose={() => setCurrent(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        TransitionComponent={Slide}
      >
        <Alert severity={current?.severity} sx={{ borderRadius: 2 }} onClose={() => setCurrent(null)}>
          {current?.message}
        </Alert>
      </Snackbar>
    </ToastContext.Provider>
  );
};
```

---

## 13.5 Analytics Widgets

```javascript
// PermissionScoreBadge — used on group cards
const PermissionScoreBadge = ({ score, permissions }) => {
  const color = score >= 80 ? 'success' : score >= 50 ? 'warning' : 'error';
  const label = score >= 80 ? 'Full Access' : score >= 50 ? 'Partial' : 'Limited';
  
  return (
    <Tooltip
      title={
        <Box>
          <Typography variant="caption" sx={{ display: 'block', mb: 0.5 }}>
            Bot Permissions ({score}/100)
          </Typography>
          {Object.entries(permissions).map(([key, val]) => (
            <Typography key={key} variant="caption" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              {val ? '✓' : '✗'} {PERMISSION_LABELS[key]}
            </Typography>
          ))}
        </Box>
      }
    >
      <Chip
        label={`${score}% · ${label}`}
        color={color}
        size="small"
        sx={{ cursor: 'help' }}
      />
    </Tooltip>
  );
};

// TokenUsageBar — used on AI Settings page
const TokenUsageBar = ({ used, limit, resetAt }) => {
  const pct = Math.min((used / limit) * 100, 100);
  const color = pct > 90 ? 'error' : pct > 70 ? 'warning' : 'primary';
  
  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
        <Typography variant="caption">{used.toLocaleString()} tokens used today</Typography>
        <Typography variant="caption" color="text.secondary">
          {limit.toLocaleString()} limit
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate" value={pct}
        color={color}
        sx={{ height: 8, borderRadius: 4 }}
      />
      <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5, display: 'block' }}>
        Resets {formatDistanceToNow(new Date(resetAt), { addSuffix: true })}
      </Typography>
    </Box>
  );
};
```

---

# 14. PERFORMANCE OPTIMIZATION

## 14.1 Frontend Performance

### Code Splitting
```javascript
// App.js — all heavy pages lazy-loaded
const AnalyticsHub     = React.lazy(() => import('./pages/AnalyticsHub'));
const AssistantNotes   = React.lazy(() => import('./pages/AssistantNotes'));
const AssistantDigests = React.lazy(() => import('./pages/AssistantDigests'));
const AssistantTasks   = React.lazy(() => import('./pages/AssistantTasks'));
const WorkflowBuilder  = React.lazy(() => import('./pages/WorkflowBuilder'));
const GroupCRM         = React.lazy(() => import('./pages/GroupCRM'));

// All lazy routes wrapped in Suspense:
<Suspense fallback={<PageLoader />}>
  <Route path="/analytics" element={<AnalyticsHub />} />
</Suspense>

// PageLoader — full-page skeleton while lazy chunk loads
const PageLoader = () => (
  <Box sx={{ p: 3 }}>
    <Skeleton variant="text" width="30%" height={40} sx={{ mb: 2 }} />
    <Grid container spacing={2}>
      {[1,2,3,4].map(i => <Grid key={i} item xs={12} sm={6} lg={3}>
        <Skeleton variant="rounded" height={120} />
      </Grid>)}
    </Grid>
  </Box>
);
```

### API Request Deduplication
```javascript
// Dashboard — all initial data fetched in parallel (Promise.all)
// Never serial unless dependent

useEffect(() => {
  const fetchAll = async () => {
    setLoading(true);
    try {
      const [meRes, groupsRes, notifRes, remindersRes] = await Promise.all([
        auth.getMe(),
        telegramGroups.getAll(),
        notifications.unreadCount(),
        workspace.getReminders({ due_today: true, limit: 3 }),
      ]);
      setUser(meRes.data);
      setGroups(groupsRes.data);
      setUnreadCount(notifRes.data.count);
      setReminders(remindersRes.data);
    } finally {
      setLoading(false);
    }
  };
  fetchAll();
}, []);
```

### Optimistic UI
```javascript
// Notes: show new note immediately before API confirms
const createNote = async (noteData) => {
  const tempId = `temp-${Date.now()}`;
  const tempNote = { ...noteData, id: tempId, created_at: new Date().toISOString() };
  
  // Optimistic: add to list immediately
  setNotes(prev => [tempNote, ...prev]);
  
  try {
    const { data } = await notes.create(noteData);
    // Replace temp note with real one
    setNotes(prev => prev.map(n => n.id === tempId ? data : n));
  } catch (err) {
    // Rollback on failure
    setNotes(prev => prev.filter(n => n.id !== tempId));
    showError('Failed to save note. Please try again.');
  }
};
```

---

## 14.2 Backend Performance

### Database Query Optimization
```python
# Avoid N+1 queries — use joinedload for related data
groups = TelegramGroup.query.options(
    joinedload(TelegramGroup.digest_logs.order_by(DigestLog.sent_at.desc()).limit(1))
).filter_by(owner_user_id=user_id).all()

# Hub summary — single efficient query, not 5 separate ones
def get_hub_summary(user_id):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
    
    # Batch all DB calls
    reminders = WorkspaceReminder.query.filter(
        WorkspaceReminder.user_id == user_id,
        WorkspaceReminder.remind_at >= today_start,
        WorkspaceReminder.is_sent == False
    ).limit(5).all()
    
    recent_notes = Note.query.filter_by(user_id=user_id)\
        .order_by(Note.created_at.desc()).limit(3).all()
    
    groups = TelegramGroup.query.filter_by(owner_user_id=user_id).all()
    group_ids = [str(g.telegram_group_id) for g in groups]
    
    # Single query for all recent digests
    latest_digests = {
        row.group_id: row
        for row in DigestLog.query.filter(
            DigestLog.group_id.in_(group_ids)
        ).order_by(DigestLog.sent_at.desc()).all()
    }
    
    # Single query for today's automation activity
    auto_replies_today = db.session.query(func.count(AutomationExecution.id)).filter(
        AutomationExecution.user_id == user_id,
        AutomationExecution.executed_at >= today_start
    ).scalar()
    
    return _build_hub_response(reminders, recent_notes, groups, latest_digests, auto_replies_today)
```

### Response Caching (Future)
```python
# Not implemented in MVP, but the pattern:
# Redis cache for expensive aggregations

from functools import wraps
import pickle

def cache(ttl=60, key_fn=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not redis_client:
                return f(*args, **kwargs)
            cache_key = key_fn(*args, **kwargs) if key_fn else f"{f.__name__}:{args}:{kwargs}"
            cached = redis_client.get(cache_key)
            if cached:
                return pickle.loads(cached)
            result = f(*args, **kwargs)
            redis_client.setex(cache_key, ttl, pickle.dumps(result))
            return result
        return decorated
    return decorator

# Usage:
@cache(ttl=300, key_fn=lambda user_id, period: f"analytics:overview:{user_id}:{period}")
def get_analytics_overview(user_id, period='30d'):
    ...
```

---

## 14.3 Bot Performance

```python
# Message handler performance rules:

# 1. Skip processing for bot messages
async def handle_group_message(update, context):
    if update.message.from_user.is_bot:
        return  # skip all processing for bot messages

# 2. Cache group settings in Redis (5-minute TTL)
# ⚠️ DO NOT use a module-level dict (_settings_cache = {}).
# With 2 Gunicorn workers, each worker has its own dict. The bot runs in one
# specific worker — the other worker handles API requests. A user updating settings
# via the API will update the DB but not invalidate the bot's worker cache.
# Redis is the only shared cache between all processes.

def get_group_settings(group_id: str) -> dict:
    cache_key = f"group_settings:{group_id}"
    
    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    
    group = TelegramGroup.query.filter_by(telegram_group_id=int(group_id)).first()
    settings = group.settings if group else {}
    
    if redis_client:
        redis_client.setex(cache_key, 300, json.dumps(settings))  # 5-min TTL
    
    return settings


def invalidate_group_settings_cache(group_id: str):
    """Call this after any settings update via the API."""
    if redis_client:
        redis_client.delete(f"group_settings:{group_id}")


# 3. Non-blocking DB writes for analytics
# ⚠️ DO NOT use threading.Thread() per message — creates unbounded thread count.
# In an active group with 100 messages/minute = 200 threads/minute.
# Daemon threads are killed on Railway deploy → silent data loss.
# Use a bounded ThreadPoolExecutor with error handling instead.

from concurrent.futures import ThreadPoolExecutor

# Module-level pool: bounded at 10 threads, reused across messages
_async_write_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="db_write")


def _async_db_write(func, *args):
    """Submit a non-critical DB write to the bounded thread pool.
    Errors are logged but do not affect message handling latency.
    """
    def _wrapped():
        try:
            func(*args)
        except Exception as e:
            logger.error(f"Async DB write failed in {func.__name__}: {e}", exc_info=True)
            sentry_sdk.capture_exception(e)
    
    try:
        _async_write_pool.submit(_wrapped)
    except Exception as e:
        logger.warning(f"Thread pool full, dropping async write for {func.__name__}: {e}")


# In handler (unchanged call site):
_async_db_write(_track_xp, message, group_settings)
_async_db_write(_buffer_message, message)
# These don't block the message acknowledgment to Telegram
```

---

## 14.4 Infrastructure Performance

```
Gunicorn: 2 sync workers
  → Handles 2 concurrent requests
  → Adequate for current scale (< 10k DAU)
  → Scale: increase workers or switch to gevent when concurrent requests > 20

Database connection pool:
  pool_pre_ping = True      → validates connections before use (no stale connections)
  pool_recycle = 300        → recycle connections every 5 min (Railway closes idle after 5min)
  pool_size = 5             → 5 connections per worker = 10 total
  max_overflow = 10         → burst capacity

Redis:
  socket_connect_timeout = 1  → fail fast if Redis unavailable (don't hang requests)

Telegram long-polling:
  drop_pending_updates = True   → skip queued updates on restart (prevents backlog processing)
  allowed_updates = ALL_TYPES   → receive all update types (required for ChatMemberHandler)
  connection_pool_size = 8      → concurrent Telegram API calls during handler processing
```

---

# 15. PRODUCTION READINESS CHECKLIST

## 15.0 Pre-Launch Critical Blockers

The following items are **launch blockers** — the product will silently fail, generate no revenue, or create legal liability if any of these are not resolved before going live.

- [ ] **Flask 3 bot startup** — `before_first_request` is removed in Flask 3; bot uses `_start_official_bot_thread()` pattern (Section 4.2)
- [ ] **SSE DB connection pool** — SSE endpoint releases DB session between polls, not held open for the session lifetime (Section 5.6)
- [ ] **Subscription expiry** — `subscription_expires_at` field exists in DB, daily cron downgrades expired users (Section 11.1.1)
- [ ] **SSE auth nonce** — SSE uses nonce token (`/api/assistant/sse-token`), NOT JWT in query param (Section 5.6)
- [ ] **AI quota race condition** — Redis atomic INCR used for quota enforcement (Section 5.2)
- [ ] **Redis settings cache** — Bot settings cache uses Redis, not module-level dict (Section 14.3)
- [ ] **Card payment available** — Lemon Squeezy or Stripe enabled before any paid acquisition (Section 11.1.1)
- [ ] **Marketplace removed from marketing** — Not listed as Enterprise feature until escrow is built (Appendix A T-7)
- [ ] **Knowledge base + Tasks frontends** — Built or removed from sidebar before launch (Appendix B)
- [ ] **Pending unban table** — `pending_unbans` table exists, `retry_pending_unbans()` scheduler job runs (Section 4.9)
- [ ] **Free plan digest enforcement** — `check_feature_access(user, 'digests')` called in scheduler (Section 2.8)
- [ ] **Privacy Policy covers AI processing** — Explicitly discloses message content sent to AI providers (Section 15.7)
- [ ] **Email unsubscribe** — Unsubscribe link in all non-transactional emails (Appendix A T-9)
- [ ] **Product analytics** — PostHog initialized with key events tracked (Section 10.6)
- [ ] **Status page live** — status.telegizer.com operational before any public launch (Section 9.5)
- [ ] **SSE auto-reconnect fixed** — `useDMStream` uses `fetchEventSource` with proper reconnect (Section 5.6)
- [ ] **CAPTCHA on registration** — hCaptcha or Cloudflare Turnstile configured in production (Section 7.2.1)

---

## 15.1 Security

- [ ] **ENCRYPTION_KEY, JWT_SECRET_KEY, SECRET_KEY** — set to cryptographically random values (not defaults, not "changeme")
- [ ] **MIGRATE_ENCRYPT_TOTP=1** — migration script run on production DB to encrypt existing TOTP secrets
- [ ] **CORS_ALLOWED_ORIGINS** — no wildcards, no localhost, exact app domain only
- [ ] **ADMIN_EMAILS** — set in Railway env vars; admin panel inaccessible without it
- [ ] **NOWPAYMENTS_IPN_SECRET** — set; without it, all payment webhooks rejected with 400
- [ ] **TOTP for admin accounts** — all emails in ADMIN_EMAILS have TOTP enabled before accessing admin panel
- [ ] **RUNBOOK.md created** — covers key rotation procedure (ENCRYPTION_KEY_OLD), Railway numReplicas=1 constraint, bot restart procedure
- [ ] **Security headers verified** — X-Frame-Options, X-Content-Type-Options, HSTS, CSP active
- [ ] **CSP: remove unsafe-inline** — Set `INLINE_RUNTIME_CHUNK=false` in Vercel build env; remove `unsafe-inline` from script-src in vercel.json
- [ ] **SSE nonce auth** — JWT never passed as query parameter; all SSE connections use short-lived nonces
- [ ] **Rate limit fail-closed** — auth endpoints return 503 (not allow) when Redis is unavailable
- [ ] **File upload MIME type** — server-side MIME validation (not just extension check)
- [ ] **PendingVerification DB** — wired to DB, not in-memory dict (survives dyno restart)
- [ ] **PendingUnban job** — `retry_pending_unbans()` scheduler job registered and running
- [ ] **Webhook signing_secret encrypted** — Fernet encrypt `webhook_integrations.signing_secret` (match bot token encryption)
- [ ] **`rel="noopener noreferrer"`** — all external `target="_blank"` links (audit P4-27 complete)

## 15.2 Backend & APIs

- [ ] **Standard response envelope** — all 38 route files return `{ success, data, error, pagination }`
- [ ] **`GET /api/auth/export`** — GDPR data export endpoint implemented
- [ ] **Soft delete on User** — `deleted_at` field + 14-day cron (immediate hard-delete is legally risky)
- [ ] **`DELETE /api/billing/subscription`** — cancellation endpoint with email confirmation
- [ ] **All blueprint registrations** — verify all 28+ blueprints registered in `app.py`
- [ ] **Procfile release step** — `python migrate.py` runs on every deploy
- [ ] **DB indexes** — all FK indexes created (migrate.py includes CREATE INDEX IF NOT EXISTS)
- [ ] **Scheduler jobs** — verify all jobs start correctly (check Railway logs on deploy)
- [ ] **QuotaExceededError** — raised and caught correctly in all AI endpoints
- [ ] **DigestLog written** — every sent digest creates a DigestLog record

## 15.3 Frontend & UX

- [ ] **REACT_APP_API_URL** — set in Vercel env vars (console.error if missing at startup)
- [ ] **PlanGate wired** — applied to all 6 Pro-gated pages (verify list in §11.2)
- [ ] **Empty states** — every data-dependent page has icon + message + CTA (never blank)
- [ ] **Skeleton loaders** — every data-dependent component shows skeleton while loading
- [ ] **Bottom nav for mobile** — `/groups`, `/workspace`, `/analytics`, `/billing`, `/settings`
- [ ] **All legacy routes** — `/my-groups/*` → `/groups/*`, old analytics URLs → redirects
- [ ] **Error boundary** — `ErrorBoundary` wraps root to prevent white screens
- [ ] **Sentry (frontend)** — DSN set in Vercel env, JS errors captured
- [ ] **PWA manifest** — name, icons, theme_color, display configured for Telegizer branding
- [ ] **`robots.txt`** — deployed at `/public/robots.txt` (P4-30 complete)
- [ ] **`og:` meta tags** — Open Graph + Twitter card meta in `index.html`

## 15.4 Telegram Bot

- [ ] **TELEGRAM_BOT_TOKEN** — verified to be the production @TelegizerBot token (not a test bot)
- [ ] **numReplicas = 1** — confirmed in `railway.toml` (bot polling constraint)
- [ ] **Bot has correct permissions** — @TelegizerBot added to a test group and all 8 permissions granted
- [ ] **PendingVerification model** — verification state persists across bot restarts
- [ ] **Bot token redaction** — regex redaction active before DM logging (P3-02 complete)
- [ ] **Verification timeout cron** — `expire_pending_verifications()` job running every 5 minutes
- [ ] **BotEvent cleanup cron** — 90-day retention job running daily
- [ ] **`drop_pending_updates=True`** — prevents bot processing old messages on restart

## 15.5 Payments & Billing

- [ ] **NOWPayments test** — end-to-end test payment in staging environment
- [ ] **Webhook HMAC verified** — test webhook with wrong signature → 400
- [ ] **Idempotency tested** — send duplicate webhook → only one plan upgrade
- [ ] **1% tolerance** — test with underpayment of 0.5% → upgrade succeeds
- [ ] **ProcessedPayment** — verify record created after successful payment
- [ ] **PaymentHistory** — verify record created with correct plan/amount
- [ ] **Confirmation email** — verify payment confirmation email sent via Resend
- [ ] **`/payment/success` page** — handles both `?status=success` and `?status=failed`
- [ ] **Plan display** — dashboard plan badge updates immediately after payment

## 15.6 Monitoring & Ops

- [ ] **Sentry DSN configured** — backend + frontend, both sending events to same project
- [ ] **Sentry alert rule** — error rate > 1% in 5 minutes → email to ADMIN_EMAILS
- [ ] **Railway health check** — `/ready` endpoint returns 200, Railway alert on non-200
- [ ] **Redis available** — rate limiting and JWT blacklist degradation tested
- [ ] **Admin panel accessible** — admin user can log in, access `/admin`, see user list
- [ ] **Log drain active** — Railway logs viewable and structured (JSON format)
- [ ] **DB backup verified** — Railway PostgreSQL daily snapshots enabled (Pro plan)
- [ ] **ENCRYPTION_KEY backed up** — stored in password manager (Railway env alone is insufficient)

## 15.7 Compliance & Legal

- [ ] **Privacy Policy updated** — explicitly covers: (a) Telegram message content buffered for AI processing, (b) list of third-party AI providers (Gemini, OpenAI, Anthropic, OpenRouter), (c) message buffer retention period (7 days configurable, 90 days bot events), (d) user right to deletion of AI-derived data (notes, digests), (e) DPA with all AI providers
- [ ] **Terms of Service live** — accessible at `/terms`
- [ ] **GDPR data export** — `GET /api/auth/export` implemented and tested; export includes all personal data (notes, reminders, tasks, payment history, digest previews, CRM notes)
- [ ] **Account deletion flow** — soft-delete with 14-day grace period + MessageBuffer/BotEvent purge for deleted users
- [ ] **Marketing emails** — unsubscribe link in all marketing emails; `email_preferences.marketing = false` respected
- [ ] **Referral rewards** — reward amounts defined and documented before referral links distributed (currently TBD — Appendix A T-8)
- [ ] **Non-EU AI data forwarding** — if any AI provider is US-based and users are EU residents, Standard Contractual Clauses (SCCs) required

## 15.8 Performance

- [ ] **Hub loads < 1.5s** — single `/api/assistant/hub-summary` call, measured in staging
- [ ] **Dashboard loads < 2s** — `Promise.all` parallel fetches, measured in staging
- [ ] **No N+1 queries** — check Railway slow query logs > 500ms after deploy
- [ ] **Lazy routes** — AnalyticsHub, AssistantNotes, AssistantDigests in separate webpack chunks
- [ ] **TableContainer** — all tables use MUI `TableContainer` for horizontal scroll on mobile
- [ ] **Core Web Vitals** — LCP < 2.5s, FID < 100ms, CLS < 0.1 (measure via Lighthouse)

## 15.9 Manual E2E Test Scenarios (P5-QA)

```
Must be verified by a human tester before go-live:

□ Register → verify email → reach dashboard
□ Login with wrong password 10x → account locked → 15min wait
□ Set up 2FA → log out → log in with TOTP code
□ Add @TelegizerBot to test group → generate link code → link group
□ Send a message with a link in the group → bot auto-deletes it
□ New member joins group with verification enabled → button challenge → verify → messages allowed
□ Create a note manually → AI-generate notes from group
□ Set a reminder via DM ("remind me to test at 3pm") → receive reminder at correct time
□ Enable digest for group → click Send Now → receive digest in DM
□ Upgrade to Pro via crypto payment (test net payment) → plan badge updates
□ Test PlanGate: try to access Digest page on free plan → see upgrade modal
□ Admin panel: log in as admin, view user list, change plan
□ Delete account → confirm soft-delete (user can't log in, data still in DB)
□ SSE live chat: DM bot → see message appear in dashboard < 5s
□ Mobile: verify sidebar collapses, tables scroll, modals are full-screen
```

---

## APPENDIX A: OPEN DECISIONS (Pre-Launch)

| ID | Decision | Blocking? | Recommended Action | Status |
|---|---|---|---|---|
| T-1 | GDPR data export endpoint | **Yes** | Implement `GET /api/auth/export` with full personal data | — |
| T-2 | Soft-delete User model | **Yes** | Add `deleted_at`, 14-day hard-delete cron | — |
| T-3 | Standard API response envelope | **Yes** | Audit all 38 route files, enforce `{ success, data, error }` | — |
| T-4 | CSP headers in vercel.json | **Yes** | Set `INLINE_RUNTIME_CHUNK=false`, remove `unsafe-inline` | — |
| T-5 | Flask-Talisman installed | **Yes** | Verify in requirements.txt, configure | — |
| T-6 | Server-side MIME validation | **Yes** | Add to knowledge upload handler | — |
| T-7 | Marketplace escrow model | **Yes** | Remove "Marketplace" from Enterprise marketing until built | — |
| T-8 | Referral reward amounts | No | Define before distributing referral links | — |
| T-9 | Marketing email unsubscribe | **Yes** | Required before any email sent to users (GDPR/CAN-SPAM) | — |
| T-10 | RUNBOOK.md | **Yes** | Write before any production key changes | — |
| T-11 | Card payment (Lemon Squeezy or Stripe) | **Yes** | Crypto-only prevents mainstream conversion; must be live before paid acquisition | — |
| T-12 | `DELETE /api/billing/subscription` | **Yes** | Required before annual plan goes live; must downgrade at period end, not immediately | — |
| T-13 | Flask 3 bot startup | **Yes** | Replace `before_first_request` with `_start_official_bot_thread()` (Section 4.2) | Fixed in spec |
| T-14 | Subscription expiry tracking | **Yes** | Add `subscription_expires_at` to users; add downgrade cron (Section 11.1.1) | Fixed in spec |
| T-15 | SSE JWT security | **Yes** | Replace query-param JWT with nonce via `/api/assistant/sse-token` (Section 5.6) | Fixed in spec |
| T-16 | AI quota race condition | **Yes** | Use Redis atomic INCR (Section 5.2) | Fixed in spec |
| T-17 | Settings cache worker isolation | **Yes** | Migrate bot settings cache to Redis (Section 14.3) | Fixed in spec |
| T-18 | Product analytics | **Yes** | PostHog required before launch for growth decisions (Section 10.6) | Fixed in spec |
| T-19 | Status page | **Yes** | BetterStack/Instatus live before public launch | — |
| T-20 | Unban retry safety | **Yes** | `pending_unbans` table + retry job prevents permanent accidental bans (Section 4.9) | Fixed in spec |
| T-21 | Privacy Policy AI disclosure | **Yes** | Must cover message content sent to AI providers (Section 15.7) | — |
| T-22 | CAPTCHA on registration | No | Add before any public growth campaigns | — |
| T-23 | Knowledge base + Tasks frontend | **Yes** | Build pages or remove from sidebar before launch | — |

---

## APPENDIX B: PHASE 2 FEATURE QUEUE

| Feature | Status | Notes |
|---|---|---|
| Knowledge base frontend | Ready | Backend (`KnowledgeDocument` model + routes) fully built |
| Tasks feature frontend | Ready | `tasks.py` route + `AssistantTasks.js` page built |
| Auto-Reply trigger log | Planned | `AutoReplyLog` model needed |
| Analytics assistant tab | Planned | Token usage + notes/digests activity |
| Platform key rate limiting | Partial | Counter exists, enforcement needs testing |
| Group reply reminders | Planned | "remind me about this" as reply to group message |
| Meeting link capture | Planned | Detect Zoom/Meet/Calendly URLs in group messages |

## APPENDIX B.1: CRITICAL INFRASTRUCTURE WORK (Phase 2 Sprints)

These are not features — they are architectural improvements required for production stability at scale.

| Work Item | Problem Solved | Phase |
|---|---|---|
| Separate bot service from API service | Breaks 1-replica constraint; enables API horizontal scaling | Phase 2 |
| Celery + Redis worker for AI jobs | Digest generation no longer blocks HTTP workers | Phase 2 |
| Railway cron jobs replace APScheduler | Scheduler jobs run independently; can scale separately | Phase 2 |
| Redis pub/sub for SSE | Eliminates 15k DB queries/minute at 500 active users | Phase 2 |
| HttpOnly cookie JWT | Eliminates XSS token theft risk | Phase 2 |
| Stripe recurring billing | Eliminates manual renewal; fixes LTV collapse | Phase 2 |
| Feature flags (LaunchDarkly/PostHog) | Safe gradual rollouts; A/B testing capability | Phase 2 |
| Bot → Telegram webhook mode | Reduces latency; enables horizontal bot scaling | Phase 3 |
| pgvector semantic search | Notes and Knowledge Base similarity search | Phase 3 |
| Multi-user workspace | Team access for agencies and enterprise users | Phase 3 |

---

## APPENDIX C: PHASE 3 FEATURE QUEUE (Advanced)

| Feature | Dependency | Notes |
|---|---|---|
| Semantic search (Notes/Knowledge) | pgvector extension | `embeddings.py` already exists |
| Assistant memory (persistent facts) | Phase 2 knowledge base | User-taught facts, persisted |
| Calendar integration | OAuth + Google API | Meeting links → Google Calendar |
| Cross-group intelligence | Phase 2 analytics | Query across all user's groups |
| Workflow visual builder | Phase 2 workflows | Replace form-based with node editor |
| Mini App mobile interface | Telegram Mini App | `/mini-app` routes already exist |
| Horizontal scaling (webhooks) | Bot webhook mode | Switch from long-polling to Telegram webhooks |

---

---

# 16. BACKGROUND JOB ARCHITECTURE

## 16.1 Current State vs. Target State

The MVP uses APScheduler in-process. This is functional but creates a critical bottleneck: AI generation jobs (digest, notes) are synchronous and run inside the same process as the Flask API. A digest job that takes 30 seconds for 100 groups blocks all HTTP workers for that duration.

```
Current (MVP):
  Railway Web Dyno
    ├── Gunicorn Worker 1 ──── HTTP requests
    ├── Gunicorn Worker 2 ──── HTTP requests (blocked during AI jobs)
    ├── APScheduler thread ──── All scheduled jobs (including 30s AI calls)
    └── Bot daemon thread ──── Telegram long-polling

Target (Phase 2):
  Railway: api service (N replicas)
    └── Gunicorn (4 workers) ← HTTP only

  Railway: worker service (N replicas)
    └── Celery worker ← AI generation, email, analytics

  Railway: bot service (1 replica — permanent)
    └── Telegram bot daemon

  Railway: Cron Jobs
    ├── Digest trigger (daily at configured times)
    ├── Subscription expiry check (daily at midnight)
    └── Cleanup jobs (daily)

  Shared: PostgreSQL + Redis (unchanged)
```

## 16.2 Celery Configuration (Phase 2 Target)

```python
# backend/celery_app.py
from celery import Celery

celery = Celery(
    'telegizer',
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=['backend.tasks.digest', 'backend.tasks.email', 'backend.tasks.cleanup']
)

celery.conf.update(
    task_serializer='json',
    result_expires=3600,
    task_acks_late=True,          # re-queue on worker crash
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # one task at a time per worker (AI calls are slow)
    task_time_limit=120,           # hard kill after 2 minutes
    task_soft_time_limit=90,       # soft limit: raises SoftTimeLimitExceeded
)

# Task definitions
# backend/tasks/digest.py
@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_and_send_digest(self, group_id: int, user_id: int):
    try:
        with flask_app.app_context():
            group = TelegramGroup.query.get(group_id)
            user = User.query.get(user_id)
            digest_data = generate_digest(group, user)
            deliver_digest(group, digest_data, group.settings.get('digest', {}))
    except QuotaExceededError:
        pass  # expected — no retry
    except Exception as exc:
        raise self.retry(exc=exc)
```

## 16.3 Async AI Endpoint Pattern (Phase 2)

When AI generation is moved to Celery, API endpoints that trigger AI return a job ID immediately:

```python
# POST /api/telegram-groups/:id/digest/send — non-blocking
@jwt_required()
def trigger_digest_now(group_id):
    user_id = get_jwt_identity()
    group = _get_owned_group(group_id, user_id)
    
    # Queue the job, return immediately
    job = generate_and_send_digest.delay(group.id, user_id)
    
    return jsonify({'success': True, 'data': {
        'job_id': job.id,
        'status': 'queued',
        'poll_url': f'/api/jobs/{job.id}'
    }})

# GET /api/jobs/:job_id — poll for completion
@jwt_required()
def get_job_status(job_id):
    result = celery.AsyncResult(job_id)
    return jsonify({'success': True, 'data': {
        'status': result.status,   # PENDING | SUCCESS | FAILURE
        'ready': result.ready(),
    }})
```

```javascript
// Frontend: poll for digest completion after triggering
const triggerDigest = async (groupId) => {
  const { data: { job_id } } = await api.post(`/telegram-groups/${groupId}/digest/send`);
  
  // Poll every 2s for up to 60s
  for (let i = 0; i < 30; i++) {
    await sleep(2000);
    const { data: job } = await api.get(`/jobs/${job_id}`);
    if (job.status === 'SUCCESS') {
      showSuccess('Digest sent!');
      return;
    }
    if (job.status === 'FAILURE') {
      showError('Digest generation failed. Please try again.');
      return;
    }
  }
  showWarning('Digest is taking longer than usual. Check your digest history in a few minutes.');
};
```

---

# 17. RETENTION & GROWTH SYSTEMS

## 17.1 Retention Architecture

### Time-to-Value Problem

The core value of Telegizer (AI digest) requires 24+ hours to experience. Users who register and don't complete setup will churn before their first digest. The retention architecture must close this gap.

```
Onboarding Completion Rate Targets:
  Register → Email Verified:        Target 85%+
  Email Verified → Group Linked:    Target 60%+
  Group Linked → First Feature ON:  Target 70%+
  → Digest Enabled:                 Target 40%+
  → First Digest Received:          Target 85% of digest-enabled users

If any step drops below target → fix that step before growth campaigns.
```

### Instant Demo Digest (Onboarding Fix)

The 24-hour wait for the first digest is eliminated by an "Instant Demo" on the onboarding page:

```javascript
// Component: InstantDemoDigest — shown on Dashboard for users without a linked group
// Allows users to experience digest output BEFORE completing setup

const InstantDemoDigest = () => {
  const [messages, setMessages] = useState('');
  const [digest, setDigest] = useState(null);
  const [loading, setLoading] = useState(false);
  
  const generateDemo = async () => {
    setLoading(true);
    const { data } = await api.post('/api/assistant/demo-digest', { messages });
    setDigest(data.digest);
    setLoading(false);
    analytics.track.demoDigestGenerated();
  };
  
  return (
    <Card>
      <CardContent>
        <Typography variant="h6">See What a Digest Looks Like</Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Paste some messages from your Telegram group and get an instant AI digest.
        </Typography>
        <TextField
          multiline rows={6} fullWidth
          placeholder="[09:12] Alice: Hey everyone, we decided to push the launch to next Friday..."
          value={messages} onChange={e => setMessages(e.target.value)}
        />
        <Button
          variant="contained" onClick={generateDemo}
          disabled={!messages.trim() || loading}
          sx={{ mt: 2 }}
          startIcon={loading ? <CircularProgress size={16} /> : <AutoAwesome />}
        >
          {loading ? 'Generating...' : 'Generate Demo Digest'}
        </Button>
        {digest && <DigestPreviewCard digest={digest} isDemo />}
      </CardContent>
    </Card>
  );
};
```

### Upgrade Nudge System

```python
# backend/assistant/suggestion_engine.py — additions to get_hub_suggestions()

# Nudge: approaching AI token limit
if user.subscription_tier == 'free':
    usage_pct = _get_ai_usage_pct(user)
    if usage_pct >= 80:
        suggestions.append({
            'type': 'upgrade',
            'icon': 'Upgrade',
            'title': f'Running low on AI tokens ({round(usage_pct)}% used today)',
            'body': 'Upgrade to Pro for 50× more AI power.',
            'action': '/billing',
            'urgency': 'high' if usage_pct >= 95 else 'medium',
        })

# Nudge: group approaching free tier limit
groups_count = TelegramGroup.query.filter_by(owner_user_id=user.id).count()
if user.subscription_tier == 'free' and groups_count >= 1:
    suggestions.append({
        'type': 'upgrade',
        'icon': 'AddCircle',
        'title': 'Want to manage more groups?',
        'body': 'Pro unlocks unlimited groups, 3 custom bots, and AI Digests.',
        'action': '/billing',
        'urgency': 'low',
    })
```

## 17.2 Viral Growth Loop

### Attribution via Bot Presence

When `@TelegizerBot` is active in a group, group members see the bot's name but have no way to discover Telegizer. Optional attribution closes this gap:

```python
# Group settings: attribution_footer (default: True for Free/Pro, False for Enterprise)
# When True, bot welcome messages include a subtle attribution:

WELCOME_TEMPLATE_WITH_ATTRIBUTION = """
{welcome_message}

─
Powered by Telegizer · telegizer.com
"""

# Show in:
# - New member welcome messages (if welcome is enabled)
# - Verification challenge messages
# - NOT in: auto-replies, custom commands (too intrusive)
```

```javascript
// Group settings page — attribution toggle
<FormControlLabel
  control={<Switch checked={settings.attribution_footer ?? true}
                   onChange={e => updateSetting('attribution_footer', e.target.checked)} />}
  label={
    <Box>
      <Typography variant="body2">Show "Powered by Telegizer" in bot messages</Typography>
      <Typography variant="caption" color="text.secondary">
        Helps other community managers discover the platform. Hidden for Enterprise.
      </Typography>
    </Box>
  }
/>
```

## 17.3 Win-Back Email Sequence

```
Subscription expiry email sequence:

  T-7 days: "Your Pro subscription expires in 7 days"
    Subject: "[Action needed] Your Telegizer Pro expires in 7 days"
    Body: Highlight features they've used, renew CTA, what they'll lose

  T-3 days: "3 days until your plan changes"
    Subject: "Don't lose your AI digests — renew Pro"
    Body: Show their last digest, renew button

  T-1 day: "Last chance to renew"
    Subject: "Your Pro plan expires tomorrow"
    Body: Urgent CTA, offer 7-day grace period notice

  T+0 (expiry): "Your plan has changed to Free"
    Subject: "You're now on Telegizer Free"
    Body: What's restricted, how to renew, what they still have

  T+7 (grace end): "Your Pro features are now paused"
    Subject: "Pro features paused — renew anytime to restore"
    Body: One-click renew link, no data loss assurance

  T+30 (win-back): "We miss you — here's what happened while you were away"
    Subject: "Your communities generated X events this month"
    Body: Show bot activity stats, re-engagement offer
```

---

# 18. OBSERVABILITY & RELIABILITY

## 18.1 Monitoring Stack (Complete)

```
Error Tracking:   Sentry (FlaskIntegration + React SDK)
  - Alert: error rate > 1% in 5min → email ADMIN_EMAILS
  - Release tracking: APP_VERSION in sentry.init()
  - Scrub rules: remove JWT values, bot tokens from event data

Uptime Monitoring: BetterStack / Instatus
  - /ready endpoint checked every 60s from external probe
  - status.telegizer.com: public status page
  - Alert channels: email + Telegram DM to admin

Product Analytics: PostHog
  - User behavior funnels (Section 10.6)
  - Feature adoption tracking
  - Conversion attribution

Structured Logging: pythonjsonlogger
  - All logs: JSON format to Railway log drain
  - Log levels: DEBUG (dev) → INFO (staging) → WARNING+ (prod)
  - Bot errors: Sentry + logged with telegram_chat_id tag

Performance: Railway Metrics
  - CPU, memory, response time via Railway dashboard
  - Slow query log > 500ms (PostgreSQL setting)
  - Alert: memory > 80% → investigate

Future (Phase 2):
  - Datadog or New Relic APM for distributed tracing
  - Custom business metrics dashboard (MRR, churn, active subscriptions)
```

## 18.2 Graceful Degradation Matrix

| System | Failure | Behavior |
|---|---|---|
| Redis unavailable | Rate limiting on auth endpoints | Return 503 (fail closed — see Section 8.7.2) |
| Redis unavailable | JWT blacklist check | Fall back to DB `revoked_tokens` table |
| Redis unavailable | Settings cache | Fall back to DB read (slightly slower) |
| Redis unavailable | AI quota check | Fall back to DB counter (approximate, non-atomic) |
| Telegram API unreachable | Bot polling thread | Thread retries with exponential backoff; bot_ok=false in /health |
| AI provider unavailable | Digest generation | Catch exception, log to DigestLog with error, notify user via in-app notification |
| AI provider unavailable | Notes generation | Return 503 with user-friendly message: "AI service temporarily unavailable" |
| NOWPayments webhook fails | Payment not confirmed | User can click [Refresh Subscription] which re-queries NOWPayments API |
| Resend/SMTP unavailable | Email not sent | Log failure to Sentry; do not retry transactional emails (idempotency risk) |
| PostgreSQL slow/unavailable | All API endpoints | SQLAlchemy pool timeout → 503; /ready returns 503 → Railway alerts |

## 18.3 Disaster Recovery

```
Scenario: Railway dyno crash (OOM, crash)
  Recovery: Railway auto-restarts (restartPolicyType=ON_FAILURE, maxRetries=3)
  Bot: drop_pending_updates=True → resumes from current state, skips backlog
  Scheduler: APScheduler re-registers jobs on startup; missed jobs do not catch up
  User impact: 30-120s downtime

Scenario: PostgreSQL data corruption
  Recovery: Railway daily snapshot restore
  Procedure: Railway dashboard → Database → Restore from snapshot
  RTO: ~15 minutes; RPO: up to 24 hours
  Data at risk: up to 24h of bot events, notes, reminders

Scenario: ENCRYPTION_KEY lost
  Impact: All bot tokens, API keys, TOTP secrets unreadable → complete service failure
  Prevention: Store ENCRYPTION_KEY in password manager AND Railway env vars
  Never put ENCRYPTION_KEY only in Railway — env vars can be accidentally deleted

Scenario: ADMIN_EMAILS env var cleared
  Impact: All admin accounts lose admin access on next login (is_admin not revoked, but auto-promote won't re-trigger)
  Recovery: Set ADMIN_EMAILS in Railway env vars; admin re-promoted on next login
  Note: is_admin flag persists in DB even if email not in ADMIN_EMAILS — this is intentional

Scenario: Bot token leaked
  Recovery: Regenerate via @BotFather (old token immediately invalidated by Telegram)
  → Update TELEGRAM_BOT_TOKEN in Railway env
  → Redeploy
  → All user custom bots with exposed tokens: user must generate new token via @BotFather
```

---

# 19. UNIFIED THREE-COMPONENT ARCHITECTURE

> **This section documents the canonical system design. Every feature, model, and endpoint must be consistent across all three components. Nothing exists in isolation.**

## 19.1 The Three Components

Telegizer is not a single app. It is a **unified platform** with three coordinated components that share a single backend, a single database, and a single identity system.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TELEGIZER UNIFIED PLATFORM                           │
│                                                                         │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   │
│  │  COMPONENT 1     │   │  COMPONENT 2     │   │  COMPONENT 3     │   │
│  │  Telegizer Bot   │   │  Web Dashboard   │   │  Telegram Mini   │   │
│  │  @TelegizerBot   │   │  (React SPA)     │   │  App (TMA)       │   │
│  │  + Custom Bots   │   │  Vercel          │   │  Embedded in TG  │   │
│  └────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘   │
│           │                      │                       │             │
│           └──────────────────────┴───────────────────────┘             │
│                                  │                                      │
│                    ┌─────────────▼──────────────┐                      │
│                    │   Flask Backend + PostgreSQL │                      │
│                    │   + Redis + Railway          │                      │
│                    └─────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────────┘
```

## 19.2 Component 1 — Telegizer Bot

**What it is:** The official shared Telegram bot (`@TelegizerBot`) that any user can add to their group immediately without a bot token. Advanced users may also add their own custom bot token (bring-your-own-bot) for white-label deployments.

**Runs as:** Long-polling daemon thread inside the Flask process (short-term). Separate Railway service in Phase 2. Webhook mode in Phase 3.

**Responsibilities:**
- Receive and process all Telegram group/channel/DM events
- Execute moderation actions (mute, ban, warn, delete)
- Send welcome messages, verification challenges, scheduled posts, digests
- Track member XP, levels, and engagement
- Handle custom commands, auto-replies, and knowledge base Q&A
- Write to MessageBuffer for AI digest generation
- Write BotEvents for analytics
- Accept `/linkgroup TLG-XXXXXXXX` codes to associate groups with dashboard users

**Custom Bot Extension:**
When a user provides their own bot token, the system instantiates a `BotInstance` (via `bot_manager.py`) that runs an identical handler stack to the official bot, but under the user's own bot identity. Every feature available on the official bot is available on custom bots. The only difference is branding and the Telegram bot identity.

**Uniformity Rule:** Every feature added to the official bot MUST also be implemented for custom bots via the shared handler stack. There must be no feature that works on one but not the other.

## 19.3 Component 2 — Web Dashboard

**What it is:** A React 18 SPA hosted on Vercel. This is the primary management interface where users configure bots, view analytics, manage members, write content, use the AI assistant, and manage their subscription.

**Authentication:** JWT stored in httpOnly cookies (see Section 8.2). Auto-refresh on 401. Email + password with optional TOTP.

**Routing:** 60+ routes. All authenticated routes require a valid JWT. Plan-gated routes render `<PlanGate>` for insufficient subscription tier.

**Responsibilities:**
- Full configuration UI for every bot feature (moderation, verification, welcome, digests, commands, auto-replies)
- AI Assistant hub (notes, tasks, reminders, digests, knowledge base)
- Analytics dashboards (group growth, member activity, moderation breakdown)
- Subscription and billing management
- CRM and member management
- Workspace tools (smart links, automations, forwarding rules)
- Marketplace and directory
- Admin panel (platform operators only)

## 19.4 Component 3 — Telegram Mini App (TMA)

**What it is:** A web app embedded inside Telegram via the official Telegram Mini App platform. Accessed by tapping a button in the bot's DM or via an inline keyboard button in group messages.

**Tech stack:** Same React frontend, separate route (`/mini-app`), uses `window.Telegram.WebApp` API for native Telegram integration.

**Authentication:** The TMA receives `initData` from Telegram (signed with bot token). The backend validates this signature and issues a JWT. No separate login is needed inside Telegram.

**Responsibilities (Mobile-first, simplified view):**
- Quick dashboard: member count, last 3 moderation actions, pending verifications
- Send an announcement to a linked group
- View and dismiss AI reminders
- Approve/reject pending verification queue
- View group health score
- Quick access to most-used features without leaving Telegram

**TMA Init Flow:**
```
User taps [Open Dashboard] in bot DM
  → Telegram opens Mini App URL: https://telegizer.com/mini-app?tgWebAppData=...
  → Frontend reads window.Telegram.WebApp.initDataUnsafe
  → POST /api/webapp/auth { initData: "..." }
  → Backend validates HMAC of initData using TELEGRAM_BOT_TOKEN
  → If valid: return JWT + user profile
  → Frontend stores JWT (in-memory for TMA, not localStorage)
  → TMA renders with full API access
```

**Telegram.WebApp Integration:**
```javascript
// In MiniApp.js — must implement all of:
const tg = window.Telegram.WebApp;
tg.ready();                            // Signal TMA is ready
tg.expand();                           // Full height
tg.MainButton.setText("Send Announcement");
tg.MainButton.show();
tg.MainButton.onClick(() => handleSend());
tg.BackButton.show();                  // On sub-pages
tg.BackButton.onClick(() => navigate(-1));
tg.setHeaderColor("#0f172a");          // Match app theme
tg.setBackgroundColor("#0f172a");
```

## 19.5 Uniformity Rules

These rules are non-negotiable. Violations cause inconsistent user experience and support confusion.

| Rule | Description |
|---|---|
| **Feature Parity** | Every bot feature works on BOTH official bot AND custom bots |
| **Data Parity** | Every action visible on web must also be visible in TMA (read) |
| **Config Source of Truth** | Web Dashboard is the ONLY place configuration is changed. Bot reads config from DB. TMA reads config from DB. No config stored in bot memory. |
| **Authentication Uniformity** | One User model. One JWT system. Web uses cookie JWT. TMA uses initData-validated JWT. API keys use Bearer token. All hit the same `/api/*` endpoints. |
| **Event Uniformity** | Every bot action writes a BotEvent. Every BotEvent is visible in analytics on both web and TMA. |
| **AI Uniformity** | AI features (digest, auto-reply, knowledge Q&A) use the same AI key resolver regardless of whether triggered by official bot, custom bot, or web assistant. |

## 19.6 Adding a New Custom Bot — End-to-End Flow

When a user adds a new custom bot, this exact sequence must execute:

```
1. User opens /bots → clicks "Add Bot"
2. User pastes bot token → POST /api/bots/validate-token
   → Backend calls Telegram getMe with the token
   → Checks token is not already registered (by hash)
   → Returns { username, first_name, valid: true }
3. User confirms → POST /api/custom-bots { token, name }
   → Backend Fernet-encrypts token → stores in Bot model
   → Calls _register_bot_identity(token):
       - setMyCommands: /start, /help, /rules, /stats, /leaderboard, /report
       - setMyDescription: "Powered by Telegizer"  (free tier)
       - setMyShortDescription: "Community manager"
   → Creates default group settings template
   → Returns { bot_id, username }
4. BotManager starts a BotInstance for the new bot
5. Frontend shows success + "Add this bot to your group" instructions
6. User adds bot to Telegram group
7. Bot receives chat_member update (bot was added)
   → Bot sends welcome message: "👋 I'm [BotName], managed via Telegizer. 
      Use /start to link this group to your dashboard."
8. User clicks "Generate Link Code" in the web dashboard → POST /api/telegram-groups/generate-link-code
   → Backend generates TLG-XXXXXXXX code, stores in DB with 12-minute TTL
   → Dashboard shows code + copyable instruction: "Run /linkgroup TLG-XXXXXXXX in your group"
   → Dashboard begins polling GET /api/telegram-groups/link-status?code=TLG-XXXXXXXX every 3s
9. Admin runs /linkgroup TLG-XXXXXXXX in the Telegram group
   → Bot validates code, checks admin status, creates TelegramGroup record, marks code used
   → Polling endpoint returns { status: "linked" } → dashboard auto-redirects to group settings
   → Bot sends: "✅ Group linked to your Telegizer dashboard!"
10. POST /api/telegram-groups/link is the internal endpoint called by the bot handler
   → Validates code, fetches chat info via getChat
   → Checks bot is admin via getChatMember
   → Creates TelegramGroup record linked to user
   → Stores bot_permissions JSON
   → Writes BotEvent: group_linked
10. Dashboard polls every 3s on the "waiting for link" screen
    → On success: redirect to group settings page
    → On success: bot sends: "✅ Group linked to your Telegizer dashboard!"
```

## 19.7 Adding an AI Feature — End-to-End Flow

When any AI feature is triggered (digest, auto-reply, notes), this resolver runs:

```
AI Key Resolution (priority order):
  1. Group-specific key (group.ai_api_key in settings JSONB) — if set
  2. Workspace key (user.workspace_ai_api_key) — if set
  3. Platform key (PLATFORM_GEMINI_API_KEY or PLATFORM_OPENROUTER_API_KEY env var)

Model selection:
  - Free tier: platform key only, gpt-3.5-turbo or gemini-flash
  - Pro tier: user's own key supported, gpt-4o or gemini-pro
  - Enterprise: full model selection, no daily token limit

Token tracking:
  - Every AI call: deduct from user.workspace_ai_tokens_today (atomic Redis DECR)
  - On depletion: return 429 with { error: "daily_token_limit_reached", reset_at: "..." }
  - Reset: midnight UTC cron resets counter to 0
  - DigestLog: record tokens_used per digest generation

Content safety:
  - All AI output passes through content_safety_check() before being sent to Telegram
  - Confidence scoring: only auto-reply if confidence >= 0.85
  - Topic filter: never auto-reply to medical/legal/financial questions without disclaimer
```

---

# 20. MEETINGS SYSTEM

> Documented from real implementation. Not in original spec.

## 20.1 Overview

The Meetings system allows community managers to schedule, track, and record meetings associated with their communities or workspace. It is accessible from the web dashboard.

## 20.2 Data Model

```python
class Meeting(db.Model):
    __tablename__ = "meetings"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id        = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    title           = db.Column(db.String(255), nullable=False)
    description     = db.Column(db.Text)
    scheduled_at    = db.Column(db.DateTime(timezone=True), nullable=False)
    duration_minutes= db.Column(db.Integer, default=60)
    meeting_url     = db.Column(db.String(500))           # Zoom/Meet/Telegram link
    status          = db.Column(db.String(50), default="scheduled")
                                                          # scheduled | live | completed | cancelled
    recording_url   = db.Column(db.String(500))
    transcription   = db.Column(db.Text)
    attendees_json  = db.Column(db.JSON, default=list)    # [{ telegram_id, name, joined_at }]
    notes           = db.Column(db.Text)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

## 20.3 API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/meetings` | List all meetings for current user (paginated) |
| POST | `/api/meetings` | Create a new meeting |
| GET | `/api/meetings/:id` | Get meeting detail |
| PATCH | `/api/meetings/:id` | Update meeting (status, notes, recording_url) |
| DELETE | `/api/meetings/:id` | Cancel and delete meeting |
| POST | `/api/meetings/:id/announce` | Send meeting announcement to linked group via bot |

## 20.4 Bot Integration

When a meeting is announced, the bot sends a formatted message to the linked group:

```
📅 Upcoming Meeting: [Title]
🗓 [Date & Time in group timezone]
⏱ Duration: [X] minutes
🔗 [Meeting URL]

[Description if set]

React with ✅ to confirm attendance.
```

## 20.5 Frontend

- Route: `/meetings`
- Page: `MeetingsPage.js`
- Shows: calendar/list view, create modal, status badges
- Links from GroupManagement page for group-specific meetings

---

# 21. PARTNERSHIP DEALS SYSTEM

> Documented from real implementation. Not in original spec.

## 21.1 Overview

The Partnership Deals system allows community operators to propose, negotiate, and track collaboration deals with other communities or partners. This is accessible from the Marketplace section.

## 21.2 Data Models

```python
class PartnershipDeal(db.Model):
    __tablename__ = "partnership_deals"
    id              = db.Column(db.Integer, primary_key=True)
    proposer_user_id= db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    partner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    title           = db.Column(db.String(255), nullable=False)
    description     = db.Column(db.Text)
    deal_type       = db.Column(db.String(100))   # cross_promo | collab | sponsorship | other
    status          = db.Column(db.String(50), default="proposed")
                                                  # proposed | negotiating | active | completed | rejected
    terms_json      = db.Column(db.JSON, default=dict)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DealMessage(db.Model):
    __tablename__ = "deal_messages"
    id              = db.Column(db.Integer, primary_key=True)
    deal_id         = db.Column(db.Integer, db.ForeignKey("partnership_deals.id"), nullable=False)
    sender_user_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content         = db.Column(db.Text, nullable=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

## 21.3 API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/marketplace/deals` | List user's deals (proposed + received) |
| POST | `/api/marketplace/deals` | Propose a new deal |
| GET | `/api/marketplace/deals/:id` | Deal detail with messages |
| PATCH | `/api/marketplace/deals/:id` | Update deal status or terms |
| POST | `/api/marketplace/deals/:id/messages` | Send a message in deal thread |
| GET | `/api/marketplace/deals/:id/messages` | List deal messages |

---

# 22. CUSTOM ASSISTANT BOTS

> Documented from real implementation. Extends Section 5 (AI Assistant System).

## 22.1 Overview

Beyond the main assistant hub, users can create purpose-built AI assistant bots that operate inside specific Telegram groups. These bots respond to questions using the group's knowledge base, maintain conversation context per user, and can be customized with a persona and instructions.

This is distinct from the main AI assistant (which is a dashboard tool). Custom assistant bots are Telegram-facing: they respond to group members directly.

## 22.2 Data Models

```python
class AssistantBot(db.Model):
    __tablename__ = "assistant_bots"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id        = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    name            = db.Column(db.String(100), nullable=False)
    persona         = db.Column(db.Text)          # System prompt / persona description
    model           = db.Column(db.String(100), default="gpt-3.5-turbo")
    temperature     = db.Column(db.Float, default=0.7)
    max_tokens      = db.Column(db.Integer, default=500)
    trigger_mode    = db.Column(db.String(50), default="mention")
                                                  # mention | all_messages | command
    trigger_command = db.Column(db.String(50))    # e.g. "/ask"
    is_active       = db.Column(db.Boolean, default=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

class AssistantConversationState(db.Model):
    __tablename__ = "assistant_conversation_states"
    id              = db.Column(db.Integer, primary_key=True)
    assistant_bot_id= db.Column(db.Integer, db.ForeignKey("assistant_bots.id"), nullable=False)
    telegram_user_id= db.Column(db.BigInteger, nullable=False)
    group_id        = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    history_json    = db.Column(db.JSON, default=list)  # [{ role, content, timestamp }]
    last_active_at  = db.Column(db.DateTime, default=datetime.utcnow)
    # Conversation history is capped at 20 turns; older turns are evicted (sliding window)
```

## 22.3 API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/assistant-bots` | List user's assistant bots |
| POST | `/api/assistant-bots` | Create assistant bot |
| GET | `/api/assistant-bots/:id` | Get config |
| PATCH | `/api/assistant-bots/:id` | Update config / persona |
| DELETE | `/api/assistant-bots/:id` | Delete assistant bot |
| GET | `/api/assistant-bots/:id/conversations` | List conversation threads |
| DELETE | `/api/assistant-bots/:id/conversations/:userId` | Clear a user's conversation history |

## 22.4 Bot Handler Integration

When a message arrives in a group with an active AssistantBot:
```
1. Check trigger_mode:
   - "mention": only respond if bot is @mentioned
   - "all_messages": respond to every message (use sparingly)
   - "command": only respond if message starts with trigger_command
2. Load AssistantConversationState for (assistant_bot_id, telegram_user_id)
3. Append user message to history_json (slide window at 20 turns)
4. Build prompt: persona + last N turns + current message
5. Query AI model (via AI key resolver — Section 19.7)
6. Run content_safety_check() on response
7. Send response to group (reply to original message)
8. Save updated history_json
9. Deduct tokens from user.workspace_ai_tokens_today
```

---

# 23. AUTOMATION ENGINE

> Documented from real implementation. Extends Section 7 (Backend & API Specification).

## 23.1 Overview

The Automation Engine evaluates user-defined workflow rules and executes actions when conditions are met. It runs as a background job (every 1 minute via APScheduler, or triggered by bot events).

## 23.2 Architecture

```
backend/automation/
  engine.py          # Core rule evaluator
  conditions.py      # Condition type implementations
  actions.py         # Action type implementations

backend/models.py:
  AutomationWorkflow  # The rule definition
  AutomationExecution # One record per rule execution
```

## 23.3 Data Models

```python
class AutomationWorkflow(db.Model):
    __tablename__ = "automation_workflows"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id        = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    name            = db.Column(db.String(255), nullable=False)
    is_active       = db.Column(db.Boolean, default=True)
    trigger_type    = db.Column(db.String(100))
                     # member_joined | message_received | member_left
                     # scheduled | member_warned | member_reached_level
    trigger_config  = db.Column(db.JSON, default=dict)
    conditions_json = db.Column(db.JSON, default=list)  # List of condition objects
    actions_json    = db.Column(db.JSON, default=list)  # List of action objects
    execution_count = db.Column(db.Integer, default=0)
    last_executed_at= db.Column(db.DateTime)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

class AutomationExecution(db.Model):
    __tablename__ = "automation_executions"
    id              = db.Column(db.Integer, primary_key=True)
    workflow_id     = db.Column(db.Integer, db.ForeignKey("automation_workflows.id"), nullable=False)
    trigger_data    = db.Column(db.JSON)            # What triggered this execution
    conditions_passed = db.Column(db.Boolean)
    actions_executed  = db.Column(db.JSON)          # Which actions ran + results
    success         = db.Column(db.Boolean)
    error_message   = db.Column(db.Text)
    executed_at     = db.Column(db.DateTime, default=datetime.utcnow)
    duration_ms     = db.Column(db.Integer)
```

## 23.4 Supported Conditions

```json
{ "type": "member_count_above", "value": 1000 }
{ "type": "member_count_below", "value": 100 }
{ "type": "message_contains", "value": "keyword" }
{ "type": "member_has_role", "value": "verified" }
{ "type": "member_level_above", "value": 5 }
{ "type": "time_of_day", "value": "09:00", "timezone": "UTC" }
{ "type": "day_of_week", "value": ["monday", "wednesday"] }
```

## 23.5 Supported Actions

```json
{ "type": "send_message", "text": "Welcome to {group_name}!", "pin": false }
{ "type": "assign_role", "role": "verified" }
{ "type": "send_dm", "text": "Your XP milestone: {xp}" }
{ "type": "webhook", "url": "https://...", "method": "POST", "payload": {} }
{ "type": "create_note", "content": "Auto-note: {trigger_summary}" }
{ "type": "add_xp", "amount": 50 }
{ "type": "warn_member" }
{ "type": "mute_member", "duration_seconds": 3600 }
```

## 23.6 API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/automations` | List user's automation workflows |
| POST | `/api/automations` | Create workflow |
| GET | `/api/automations/:id` | Get workflow + last 10 executions |
| PATCH | `/api/automations/:id` | Update workflow |
| DELETE | `/api/automations/:id` | Delete workflow |
| POST | `/api/automations/:id/test` | Run workflow in dry-run mode (no side effects) |
| GET | `/api/automations/:id/executions` | Full execution history (paginated) |

---

# 24. POLLS SYSTEM

> Documented from real implementation. Not in original spec.

## 24.1 Overview

Admins can create, schedule, and send Telegram native polls to their groups from the dashboard. Polls can be one-shot or recurring, and results are tracked.

## 24.2 Data Models

```python
class Poll(db.Model):
    __tablename__ = "polls"
    id              = db.Column(db.Integer, primary_key=True)
    group_id        = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    question        = db.Column(db.String(300), nullable=False)
    options_json    = db.Column(db.JSON, nullable=False)  # ["Option A", "Option B", ...]
    is_anonymous    = db.Column(db.Boolean, default=True)
    allows_multiple = db.Column(db.Boolean, default=False)
    is_quiz         = db.Column(db.Boolean, default=False)
    correct_option  = db.Column(db.Integer)               # For quiz mode
    schedule_at     = db.Column(db.DateTime(timezone=True))
    sent_at         = db.Column(db.DateTime)
    telegram_poll_id= db.Column(db.String(100))           # Telegram's poll ID after sending
    results_json    = db.Column(db.JSON, default=dict)    # { option_index: vote_count }
    open_period     = db.Column(db.Integer)               # Seconds poll stays open
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

class OfficialPoll(db.Model):
    # Identical structure but for official bot groups (linked to TelegramGroup)
    __tablename__ = "official_polls"
    # ... same fields, telegram_group_id FK instead of group_id
```

## 24.3 API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/bots/:botId/groups/:groupId/polls` | List polls |
| POST | `/api/bots/:botId/groups/:groupId/polls` | Create poll |
| DELETE | `/api/bots/:botId/groups/:groupId/polls/:id` | Delete scheduled poll |
| POST | `/api/bots/:botId/groups/:groupId/polls/:id/send` | Send immediately |

---

# 25. UNDOCUMENTED MODELS — CANONICAL REFERENCE

> This section documents all models that exist in the real codebase but were not in the original spec. These are part of the official system.

## 25.1 Reported Messages

Members or admins can report messages for review. Reports are visible in the admin/moderation dashboard.

```python
class ReportedMessage(db.Model):
    __tablename__ = "reported_messages"
    id                  = db.Column(db.Integer, primary_key=True)
    group_id            = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    reporter_telegram_id= db.Column(db.BigInteger)
    message_id          = db.Column(db.BigInteger)           # Telegram message_id
    message_text        = db.Column(db.Text)
    reason              = db.Column(db.String(200))
    status              = db.Column(db.String(50), default="pending")
                                                             # pending | reviewed | actioned | dismissed
    reviewed_by         = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)

class OfficialReportedMessage(db.Model):
    # Same as above but for official bot groups
    __tablename__ = "official_reported_messages"
```

**Bot command:** `/report` (reply to a message) → creates ReportedMessage record → notifies group admins via DM.

**Dashboard:** Reports visible in GroupManagement → Reports tab. Status can be updated.

## 25.2 Official Warnings (Structured Records)

The original spec described `Member.warnings` as an integer counter. In the real implementation, official bot groups also store structured warning records.

```python
class OfficialWarning(db.Model):
    __tablename__ = "official_warnings"
    id              = db.Column(db.Integer, primary_key=True)
    telegram_group_id = db.Column(db.Integer, db.ForeignKey("telegram_groups.id"), nullable=False)
    telegram_user_id= db.Column(db.BigInteger, nullable=False)
    reason          = db.Column(db.Text)
    warned_by       = db.Column(db.BigInteger)  # Telegram user_id of admin who warned
    message_id      = db.Column(db.BigInteger)  # The warned message
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

**Uniformity note:** Custom bots use `Member.warnings` (counter) + automod action logs. Official bot uses `OfficialWarning` structured records. Both should be surfaced identically in the dashboard.

## 25.3 Suspicious Activity

```python
class SuspiciousActivity(db.Model):
    __tablename__ = "suspicious_activities"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    ip_hash         = db.Column(db.String(64))
    device_hash     = db.Column(db.String(64))
    activity_type   = db.Column(db.String(100))
                     # multi_account | referral_abuse | rate_limit_violation
                     # payment_anomaly | excessive_api_usage
    details_json    = db.Column(db.JSON)
    risk_score      = db.Column(db.Integer, default=0)  # 0-100
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

**Written by:** Anti-abuse middleware on signup, referral system, rate limit violations.

**Read by:** Admin panel fraud detection view.

## 25.4 Admin Audit Log

```python
class AdminAuditLog(db.Model):
    __tablename__ = "admin_audit_logs"
    id              = db.Column(db.Integer, primary_key=True)
    admin_user_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action          = db.Column(db.String(100))
                     # user_suspended | subscription_changed | user_deleted
                     # bot_disabled | refund_issued | ip_blocked
    target_user_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    target_resource = db.Column(db.String(200))   # e.g. "Bot#42" or "User#99"
    details_json    = db.Column(db.JSON)
    ip_address      = db.Column(db.String(45))
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

**Classmethod (required):**
```python
@classmethod
def write(cls, admin_user_id, action, target_user_id=None,
          target_resource=None, details=None, ip_address=None):
    record = cls(
        admin_user_id=admin_user_id,
        action=action,
        target_user_id=target_user_id,
        target_resource=target_resource,
        details_json=details or {},
        ip_address=ip_address,
    )
    db.session.add(record)
    db.session.commit()
```

**Written by:** Every function in `admin.py` must call `AdminAuditLog.write(...)` before performing any state-changing action. This is enforced — no admin mutation without a log record.

## 25.5 Group Daily Signal

Pre-aggregated daily analytics snapshot per group. Written by a nightly cron job (2am UTC).

```python
class GroupDailySignal(db.Model):
    __tablename__ = "group_daily_signals"
    id              = db.Column(db.Integer, primary_key=True)
    group_id        = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    telegram_group_id = db.Column(db.Integer, db.ForeignKey("telegram_groups.id"), nullable=True)
    date            = db.Column(db.Date, nullable=False)
    message_count   = db.Column(db.Integer, default=0)
    member_joins    = db.Column(db.Integer, default=0)
    member_leaves   = db.Column(db.Integer, default=0)
    moderation_actions = db.Column(db.Integer, default=0)
    active_members  = db.Column(db.Integer, default=0)   # Members who sent >= 1 message
    top_members_json = db.Column(db.JSON, default=list)  # [{ telegram_id, message_count }] top 5
    ai_tokens_used  = db.Column(db.Integer, default=0)
    __table_args__  = (db.UniqueConstraint("group_id", "date"),)
```

## 25.6 Channel Daily Stats

```python
class ChannelDailyStat(db.Model):
    __tablename__ = "channel_daily_stats"
    id              = db.Column(db.Integer, primary_key=True)
    channel_id      = db.Column(db.Integer, db.ForeignKey("channels.id"), nullable=False)
    date            = db.Column(db.Date, nullable=False)
    subscriber_count= db.Column(db.Integer, default=0)
    post_count      = db.Column(db.Integer, default=0)
    total_views     = db.Column(db.Integer, default=0)
    total_reactions = db.Column(db.Integer, default=0)
    __table_args__  = (db.UniqueConstraint("channel_id", "date"),)

class ChannelPost(db.Model):
    __tablename__ = "channel_posts"
    id              = db.Column(db.Integer, primary_key=True)
    channel_id      = db.Column(db.Integer, db.ForeignKey("channels.id"), nullable=False)
    telegram_message_id = db.Column(db.BigInteger)
    text            = db.Column(db.Text)
    views           = db.Column(db.Integer, default=0)
    reactions_json  = db.Column(db.JSON, default=dict)
    posted_at       = db.Column(db.DateTime)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

## 25.7 Auto Reply Logs

```python
class AutoReplyLog(db.Model):
    __tablename__ = "auto_reply_logs"
    id              = db.Column(db.Integer, primary_key=True)
    group_id        = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    trigger_text    = db.Column(db.Text)          # What message triggered it
    pattern_matched = db.Column(db.String(200))   # Which pattern/keyword matched
    response_sent   = db.Column(db.Text)
    confidence_score= db.Column(db.Float)          # AI confidence (0–1) if AI-generated
    source          = db.Column(db.String(50))     # "keyword" | "ai" | "knowledge_base"
    telegram_user_id= db.Column(db.BigInteger)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

## 25.8 Automation Execution Logs (see Section 23.3)

## 25.9 Workspace Knowledge Document

```python
class WorkspaceKnowledgeDocument(db.Model):
    __tablename__ = "workspace_knowledge_documents"
    # Same as KnowledgeDocument but scoped to user workspace, not a specific group
    # Applied as fallback: if group KB doesn't answer, workspace KB is checked
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filename        = db.Column(db.String(255))
    content         = db.Column(db.Text)
    chunks_json     = db.Column(db.JSON, default=list)
    embedding_status= db.Column(db.String(50), default="pending")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

**Priority:** Group KB → Workspace KB → return "I don't know"

## 25.10 Connect Code (Telegram Account Linking)

```python
class TelegramConnectCode(db.Model):
    __tablename__ = "telegram_connect_codes"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    code            = db.Column(db.String(8), unique=True, nullable=False)  # 8-digit code
    telegram_user_id= db.Column(db.BigInteger)   # Filled when Telegram user submits code
    expires_at      = db.Column(db.DateTime)     # 10-minute TTL
    used            = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
```

**Flow:** User clicks "Connect Telegram Account" in Settings → system generates 8-digit code → user sends `/connect XXXXXXXX` to @TelegizerBot in DM → bot validates code → creates UserTelegramAccount record.

---

# 26. ASSISTANT SYSTEM — FULL MODULE ARCHITECTURE

> Extends Section 5. Documents the real implementation structure.

## 26.1 Module Map

```
backend/assistant/
  __init__.py
  ai_client.py              # Unified AI client (OpenAI / Gemini / OpenRouter)
  key_resolver.py           # AI key resolution (Section 19.7)
  context_service.py        # Builds enriched context for AI prompts
  profile_service.py        # Manages UserAssistantProfile
  embeddings.py             # pgvector embedding generation (Phase 3)
  group_signal_extractor.py # Extracts signals from GroupDailySignal for suggestions
  suggestion_engine.py      # Generates proactive assistant suggestions
  handlers/
    __init__.py
    state_machine.py        # Multi-turn conversation state management
    analyze.py              # "Analyze my community" intent
    general.py              # Fallback general chat intent
    groups.py               # Group-specific queries ("how is my group doing?")
    meeting.py              # Meeting scheduling intent
    reminder.py             # Reminder creation intent
    schedule.py             # Scheduled post creation via assistant
    tasks.py                # Task creation/listing intent
    notes.py                # Note extraction intent
    _ai.py                  # Internal: raw AI call wrapper
    _patterns.py            # Internal: intent detection regex patterns
    _prompts.py             # Internal: all prompt templates (DIGEST_PROMPT etc.)
    _parsers.py             # Internal: parse AI JSON responses safely
    _state.py               # Internal: conversation state helpers
    _suggestions.py         # Internal: suggestion formatting
```

## 26.2 Intent Detection Flow

```python
# handlers/_patterns.py — intent matching order (first match wins)

INTENT_PATTERNS = {
    "reminder":  [r"remind me", r"don't let me forget", r"set a reminder", r"alert me"],
    "note":      [r"note (that|this|down)", r"save this", r"remember (that|this)"],
    "schedule":  [r"schedule a (post|message|announcement)", r"post .* at "],
    "task":      [r"add a task", r"todo:", r"create a task", r"mark .* as done"],
    "meeting":   [r"schedule a meeting", r"set up a call", r"book a meeting"],
    "analyze":   [r"analyze", r"how is my (group|community)", r"give me insights"],
    "digest":    [r"summarize", r"what happened", r"catch me up", r"digest"],
    "general":   ["*"]   # Fallback
}

def detect_intent(text: str) -> str:
    text_lower = text.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        if intent == "general":
            return "general"
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent
    return "general"
```

## 26.3 State Machine

The state machine manages multi-turn conversations where the assistant needs clarification before completing an action.

```python
# State example: Reminder creation
# Turn 1: User says "remind me about the weekly call"
#   → Intent: reminder
#   → State: AWAITING_REMINDER_TIME
#   → Bot: "When should I remind you?"
# Turn 2: User says "tomorrow at 3pm"
#   → State: AWAITING_REMINDER_CONFIRM
#   → Bot: "Remind you about 'weekly call' tomorrow at 3pm? [Yes/No]"
# Turn 3: User says "yes"
#   → State: COMPLETE
#   → Bot: creates WorkspaceReminder → "Done! ✅ I'll remind you tomorrow at 3pm."

class ConversationState:
    IDLE                   = "idle"
    AWAITING_REMINDER_TIME = "awaiting_reminder_time"
    AWAITING_REMINDER_CONFIRM = "awaiting_reminder_confirm"
    AWAITING_TASK_TITLE    = "awaiting_task_title"
    AWAITING_SCHEDULE_TIME = "awaiting_schedule_time"
    AWAITING_MEETING_TIME  = "awaiting_meeting_time"
    AWAITING_MEETING_CONFIRM = "awaiting_meeting_confirm"
```

## 26.4 Context Service

Before every AI call, the context service builds a structured context object:

```python
# context_service.py
def build_context(user_id: int, group_id: int = None) -> dict:
    return {
        "user": {
            "name": user.display_name,
            "timezone": user.timezone,
            "subscription": user.subscription_tier,
        },
        "group": {                              # None if no group selected
            "name": group.name,
            "member_count": group.member_count,
            "last_7d_signals": GroupDailySignal.last_7_days(group_id),
        },
        "recent_notes": Note.recent(user_id, limit=5),
        "pending_reminders": WorkspaceReminder.pending(user_id, limit=3),
        "open_tasks": Task.open(user_id, limit=5),
        "current_time": datetime.now(user_timezone).isoformat(),
    }
```

## 26.5 Assistant Space & Profile

```python
class AssistantSpace(db.Model):
    __tablename__ = "assistant_spaces"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True)
    default_group_id= db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    pinned_notes    = db.Column(db.JSON, default=list)    # Note IDs
    pinned_tasks    = db.Column(db.JSON, default=list)    # Task IDs
    daily_briefing_enabled = db.Column(db.Boolean, default=True)
    briefing_time   = db.Column(db.String(5), default="08:00")   # HH:MM

class UserAssistantProfile(db.Model):
    __tablename__ = "user_assistant_profiles"
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True)
    preferred_tone  = db.Column(db.String(50), default="professional")
                                                     # professional | casual | concise
    focus_areas     = db.Column(db.JSON, default=list)  # ["growth", "moderation", "content"]
    ai_model_pref   = db.Column(db.String(100))     # Overrides default model
    system_prompt_addition = db.Column(db.Text)     # Custom instruction appended to system prompt
```

---

# 27. TCS ENGINE (TEMPLATE CONTENT SYSTEM)

> Documented from real implementation. Not in original spec.

## 27.1 Overview

The TCS Engine handles variable substitution in all bot message templates. It is used for welcome messages, scheduled posts, auto-replies, digest intros, and any user-defined text that includes template variables.

## 27.2 Supported Variables

| Variable | Resolves To |
|---|---|
| `{username}` | Telegram username (@handle) or first name |
| `{first_name}` | User's Telegram first name |
| `{group_name}` | Telegram group/channel title |
| `{member_count}` | Current group member count |
| `{date}` | Today's date in group timezone (e.g. "May 8, 2026") |
| `{time}` | Current time in group timezone (e.g. "14:30") |
| `{xp}` | Member's current XP score |
| `{level}` | Member's current level |
| `{warnings}` | Member's current warning count |
| `{invite_link}` | Group's invite link (if bot has permission) |
| `{rules_link}` | Link to rules (if configured in group settings) |

## 27.3 Usage

```python
# backend/tcs_engine.py
def render(template: str, context: dict) -> str:
    """
    Renders a template string by substituting {variable} placeholders.
    Unknown variables are left as-is (not removed).
    Errors in context lookup are silently skipped.
    """
    for key, value in context.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template

# Usage example:
msg = render(
    "Welcome {first_name}! You're member #{member_count} of {group_name}.",
    { "first_name": "Alice", "member_count": 1042, "group_name": "Crypto Alpha" }
)
# → "Welcome Alice! You're member #1042 of Crypto Alpha."
```

## 27.4 Validation

Before saving any template (welcome message, scheduled post, auto-reply), the backend validates all `{variable}` tags against the supported variable list and returns a warning for unknown variables.

---

# 28. GROUP DEFAULTS SYSTEM

> Documented from real implementation.

## 28.1 Overview

`backend/group_defaults.py` defines the default settings applied when a group is first linked to the dashboard. This ensures every group starts in a consistent, safe state without requiring manual configuration.

## 28.2 Default Values

```python
# backend/group_defaults.py

DEFAULT_GROUP_SETTINGS = {
    # Moderation
    "automod_enabled": False,
    "link_filter": False,
    "caps_filter": False,
    "caps_threshold": 70,             # % caps before action
    "spam_filter": False,
    "emoji_filter": False,
    "emoji_max": 10,
    "automod_action": "warn",         # warn | mute | ban
    "automod_mute_duration": 300,     # seconds
    "exempt_admins": True,

    # Verification
    "verification_enabled": False,
    "verification_type": "button",    # button | word | math
    "verification_word": "agree",
    "verification_timeout": 180,      # seconds before kick
    "verification_ban_on_fail": False,

    # Welcome
    "welcome_enabled": False,
    "welcome_message": "Welcome {first_name} to {group_name}! 🎉",
    "welcome_delete_after": 0,        # 0 = never delete

    # Digest
    "digest_enabled": False,
    "digest_frequency": "daily",
    "digest_hour": 8,
    "digest_timezone": "UTC",

    # AI
    "ai_enabled": False,
    "ai_auto_reply": False,
    "ai_confidence_threshold": 0.85,
    "ai_api_key": None,               # If null, use workspace/platform key

    # XP
    "xp_enabled": True,
    "xp_per_message": 1,
    "level_thresholds": [0, 100, 300, 600, 1000, 2000],
}
```

---

*TELEGIZER ENTERPRISE SPECIFICATION — VERSION 2.3 — UPDATED MAY 2026*
*Sections 19–28 added to document real implementation features not in original spec.*
*Version 2.1 · May 2026 · All 18 sections documented across 4 phases*
*Sections 1–15: Original specification · Sections 16–18: Audit-driven additions*
*Pre-launch audit: 23 open decisions tracked in Appendix A (17 resolved in spec, 6 require implementation)*
*Next update trigger: Launch of Phase 2 features or significant architecture change*
