# Migrate Telegizer DB: Neon → Railway Postgres

**Why:** Neon free plan hard-stopped the project on 2026-09-25 (network-transfer cap, ~5 GB/month).
The site returns 500 on login until the DB is reachable. On Railway, app↔DB traffic over the
private network (`postgres.railway.internal`) is not metered per GB, so the app's heavy DB reads stop being an outage risk.

**Data note:** Railway Postgres holds a snapshot from 2026-09-20 ~09:00 UTC. Everything written
2026-09-20 → 2026-09-25 03:15 UTC exists **only on Neon**, so it must be dumped from Neon, not skipped.
Neon is blocked (HTTP 402) until its quota resets (API says 2026-10-01 00:00 UTC — confirm in Neon → Billing).

## Steps
1. **Now:** in Railway, stop the `telegram-bot-saas` web service (Deployments → Remove/Stop). Otherwise it
   will start hammering Neon the moment the quota resets and burn the new allowance before the dump.
2. Confirm the old Railway `Postgres` service is still running; check pgvector:
   `SELECT extname FROM pg_extension;` (needs `vector` if the vector columns are real vectors).
3. **After Neon resets** (console shows project no longer paused): run `scripts/neon_to_railway.sh`
   from a machine with PostgreSQL 18 client tools. Compare the before/after row counts it prints.
4. Railway → `telegram-bot-saas` → Variables: `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`;
   delete `DATABASE_URL_UNPOOLED`. Settings → Deploy → **clear the custom Start Command** so
   `Procfile`/`railway.toml` apply (`preDeployCommand = python -m backend.migrate`).
5. Deploy. Verify `https://api.telegizer.com/health` shows `"db":"connected"` and a real login works.
6. Keep Neon and the `backups/` dumps for a week; do not delete either until verified.

## Not undone by this
Telegram updates that arrived while the DB was down (polling bots keep updates ≤24 h) and any
messages/actions attempted 2026-09-25 → cutover are not recoverable.
