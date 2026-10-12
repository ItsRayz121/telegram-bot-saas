# Telegizer — architecture map

Written 2026-10-12 from the code (not from memory). For the feature-by-feature list see
`TELEGIZER_FEATURE_MAP.md`; for undoing a bad deploy see `REVERT.md`; for audit results see
`AUDIT_REPORT.md`. For code questions, `graphify query "<question>"` is faster than reading files.

## 1. The three products, three deployables

| Product | What it is | Code | Runs on |
|---|---|---|---|
| **Telegizer** | Telegram group management (AutoMod, XP, scheduling, analytics, AI) | `backend/`, `frontend/` | Railway (API) + Vercel (UI) |
| **Echo** | Personal AI assistant on Telegram | same codebase (`backend/echo_bot.py`, `routes/assistant*.py`, `frontend/src/pages/Echo*`) | same |
| **Guildizer** | Discord server management | `discord-board/backend` (Flask), `discord-board/frontend` | separate Flask API at `guild-api.telegizer.com` |

Guildizer is a **separate codebase by design**: logic is copied, never imported, from the main app.
The main frontend embeds its UI under `/guildizer` and talks to it through `frontend/src/services/guildizerApi.js`.

```
 Browser / Telegram Mini App
        │  https://telegizer.com            (Vercel: static React build, vercel.json headers)
        ▼
 React SPA (CRA, MUI, route-level code splitting)
        │  cookies + CSRF header            https://api.telegizer.com
        ▼
 Flask API  backend/app.py  (gunicorn, 1 worker x 4 threads, Railway)
   ├── 51 blueprints in backend/routes/*  (auth, billing, groups, hub, assistant, admin ...)
   ├── in-process BotManager   – runs Telegram bots (polling or webhook) inside the web process
   ├── in-process scheduler    – _scheduler_loop in app.py runs every periodic job
   ├── PostgreSQL (Railway)    – SQLAlchemy models in backend/models.py, pgvector for knowledge search
   └── Redis (optional)        – rate limits, AI quota counters; app degrades without it
        │
        ├── Telegram Bot API   (official bot + user-supplied "custom bots")
        ├── AI providers       backend/ai_providers.py  (platform key, or the group's own key)
        ├── Payments           NOWPayments (crypto) + Lemon Squeezy webhooks, backend/routes/billing.py
        └── Email, Sentry, PostHog, Plausible, Google Analytics
```

## 2. Request paths that matter

- **Page load**: Vercel serves `index.html` (never cached) and hashed `/static/*` (immutable, 1 year).
  `public/tg-boot.js` runs first: it detects a Telegram Mini App launch and injects the web font.
- **Authenticated API call**: JWT in a cookie. State-changing requests need a CSRF header. Only
  `/api/telegram/custom/` is exempt (it is called by Telegram, not a browser) — see `test_csrf_exemptions.py`.
- **Telegram update (hot path)**: Telegram → `/api/tg-update/<hash>` or `/api/hub/webhook[/<id>]` or the custom-bot
  receiver in `app.py` (checks the per-bot `webhook_secret` with `hmac.compare_digest`) → `BotManager` →
  feature handlers in `backend/bot_features/`. These routes stay open during maintenance mode, otherwise Telegram
  retries and then disables the webhook.
- **Scheduled work**: no Celery. `railway.worker.toml` is deliberately idled. All periodic jobs run in the web
  process (`_scheduler_loop`); bringing Celery back needs the four steps written in `railway.worker.toml`.
- **Deploy**: push to `main` → Railway builds, runs `python -m backend.migrate` as the pre-deploy command, then
  health-checks `/health`. Vercel builds the frontend from the same push. Railway ignores the Procfile `release:` line.

## 3. Where things live

| Concern | Files |
|---|---|
| App wiring, blueprints, scheduler, maintenance mode, health | `backend/app.py`, `backend/health.py` |
| Config and required secrets | `backend/config.py` (`SECRET_KEY`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY` are mandatory) |
| Data model | `backend/models.py`; migrations `backend/migrate.py` |
| Plans, limits, prices | `backend/config.py` (`PLANS`), `backend/billing_config.py` (overrides `PLANS` prices) |
| Bot runtime | `backend/bot_manager.py`, `official_bot.py`, `custom_bot_*.py`, `bot_features/*` |
| AI | `ai_providers.py`, `ai_usage.py`, `assistant/ai_key_resolver.py`, `ai_activity.py` |
| Field encryption | `backend/utils/encryption.py`, `secret_vault.py` (Fernet) |
| Access control | `group_access.py`, `admin_rbac.py`, `custom_bot_access.py` |
| Frontend routes | `frontend/src/App.js` (lazy-loaded pages) |
| Frontend connection handling | `frontend/src/components/connection/*` (offline screen, status pill) |
| Tests | `backend/tests` (219), `discord-board/backend/tests` (146), `frontend/src/**/*.test.js` (71), `frontend/e2e` (browser) |

## 4. Kill switches (env var, no deploy)

`AI_TOKEN_QUOTA_ENFORCE=0`, `AI_BURST_GUARD=0`, `AI_BURST_LIMIT_PER_HOUR`, `GROUP_TEAM_ACCESS_ENABLED`,
`DISABLE_BACKGROUND_THREADS`, `USE_CELERY`. What each does and what it does *not* undo: `REVERT.md`.

## 5. Known structural risks

1. **Single process does everything.** Web requests, every Telegram bot and the scheduler share one gunicorn worker.
   A slow handler or a heavy admin sweep competes with bot traffic (admin sweeps are now single-flight).
2. **Per-worker rate-limit fallback.** When Redis is down the limiter is per process, which with one worker is fine
   but would silently weaken if workers are added.
3. **Webhook secret for official-bot routes derives from `SECRET_KEY`.** Rotating `SECRET_KEY` breaks them. Not changed
   because it would break live bots; plan a dual-secret migration first.
4. **Guildizer sessions are stateless** (logout does not revoke the token).
5. **Database is a single Railway Postgres** (moved from Neon in Sept 2026, see `MIGRATE_NEON_TO_RAILWAY.md`).
