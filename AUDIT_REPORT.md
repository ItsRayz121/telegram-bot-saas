# Telegizer ecosystem audit — final report (2026-10-12)

Scope: main app (Telegizer, Echo, shared React frontend), Guildizer API (`discord-board/backend`).
Every item below was verified by a test, a build, or a real-browser check as stated. Anything not verified is listed under "Not verified".

## Fixed and verified

| # | Severity | Area | Finding | Fix | Evidence |
|---|---|---|---|---|---|
| 1 | P0 | Tenant isolation | Official-bot escalation GET/PATCH only checked login; any user could read/overwrite another tenant's customer questions | Require group access (`043a4d6`) | `test_escalation_isolation.py` fails on old code |
| 2 | P0 | Public directory / webhooks | Non-atomic view counters, delivery errors leaked (`1f7a9e3`) | Throttle + atomic count, generic errors | tests |
| 3 | P1 | CSRF | Whole prefixes `/api/telegram/` and `/api/integrations/` were exempt, so cookie-authenticated writes (disconnect Telegram, create/test outbound webhooks) skipped CSRF | Exempt only `/api/telegram/custom/` | `test_csrf_exemptions.py`: 6 of 10 cases fail on old code |
| 4 | P1 | Dependencies | 69 backend CVEs, 108 npm findings (shipped: axios, react-router, posthog, protobufjs) | Bumped Flask, flask-cors, Pillow 12, requests, gunicorn, dotenv, bleach, pypdf 6 (Guildizer); axios/posthog refreshed | 201 + 146 tests pass on new pins |
| 5 | P1 | Plan limit / cost | Daily platform-AI limit compared a request counter to a token limit while Redis was up, so Pro's "200k tokens/day" never tripped | Also check the token ledger; kill switch `AI_TOKEN_QUOTA_ENFORCE=0` | `test_ai_token_quota.py` (blocking case fails on old code) |
| 6 | P1 | Cost / hot path | AI welcome and level-up fired one paid call per event with no ceiling, blocking the bot's event loop with no timeout | 20/group/hour cap, 8s timeout, no retries, off-loop; kill switch `AI_BURST_GUARD=0` | `test_ai_burst_guard.py` |
| 7 | P1 | Admin abuse | Heavy admin sweeps could stack and pin all web threads; `limit` unvalidated | Single-flight (409) + clamp | `test_single_flight.py` |
| 8 | P2 | Guildizer API | No security headers; OAuth `error` reflected unencoded; non-constant-time state compare | Headers, encoding, `compare_digest`; loud log if secret key is the public default | scripted request checks, 146 tests |
| 9 | P1 | Performance | One 794 KB (gzip) JS bundle on every page | Route-level code splitting: main 236 KB gzip | build + real-browser route checks |
| 10 | P2 | Accessibility | 109 icon-only buttons had no accessible name | Labels from icon/title | 63 frontend tests, build |
| 11 | P2 | Errors | ErrorBoundary called a non-existent Sentry API (crashes never reported); failed page downloads shown as "Something went wrong" | Real `@sentry/react`; connection-aware copy | 8 unit tests |
| 12 | P2 | CSP | Main-app CSP lacked `object-src`/`base-uri` | Added | config |

Offline screen and connection monitor (Phases 5/6) shipped earlier (`ef8b81d`, `7d09c53`).

## Needs a decision or access from you

1. **Scheduled messages: Free or Pro?** `Landing.js` lists it under Pro (card and FAQ); `Pricing.js` says Free; the backend allows it on Free for the official bot and requires Pro for custom bots (which are Pro-only anyway). I changed nothing.
2. **Production env checks** (my read of Railway variables was blocked): `ENFORCE_ADMIN_2FA` (defaults off, only warns), `FLASK_SECRET_KEY` on the Discord Board service (code default is public), `ENCRYPTION_KEY`.
3. **After deploy of #5:** users already above their daily token total will be blocked until their window resets. Set `AI_TOKEN_QUOTA_ENFORCE=0` to undo instantly.
4. `frontend/public/founder.jpg` does not exist; About page now shows initials. Add the photo to restore it.
5. `Config.PLANS` carries stale annual cents (Pro 8640, Enterprise 47040) that are always overridden by `billing_config` ($86 / $392). Harmless today; worth cleaning when you confirm intended annual prices.

## Remaining risk / not done

- Not verified: any behaviour under live Telegram, Discord, payment or AI-provider traffic; real network-cut test; prod DB state.
- Residual dependency issues: react-router v6 open-redirect advisory (no v6 fix; the app never passes user input to `navigate`); CRA source maps are published. (Fixed 2026-10-12: `cryptography` 46.0.7, `PyPDF2` -> `pypdf`, unused yanked `stripe` pin removed.)
- Webhook secret derived from `SECRET_KEY[:32]`, legacy custom-bot webhooks without a secret header, rate-limit IP from last `X-Forwarded-For`, per-worker limiter fallback when Redis is down: left alone, changing them can break live bots.
- Guildizer session is stateless (logout does not revoke the token server-side).
- Not covered: Guildizer API calls don't feed the connection monitor; `discord-board/frontend` not built or browser-tested; Core Web Vitals on the live site were measured on 2026-10-12 *before* the speed fixes in this commit deploy: mobile Lighthouse performance 38 (FCP 3.7 s, LCP 5.4 s, TBT 1.5 s, CLS 0.003), accessibility 90, best-practices 93, SEO 100. Local build after the fixes: FCP 1.0 s, accessibility 95; LCP/TBT still limited by startup JavaScript (MUI + emotion in the main bundle) and not fixed. Re-measure after deploy. Architecture map is now `ARCHITECTURE.md`. Browser e2e + screenshot tests (42, desktop and mobile) are in `frontend/e2e` (`npm run e2e:build`, then `npm run e2e`); they cover public pages, login redirect, platform switcher and the offline screen, not logged-in flows.
- Frontend lint warnings (unused vars) exist in untouched files; the production build only succeeds when `CI` is not `true`.

## New finding (2026-10-12): analytics loads before consent
`frontend/public/index.html` loads Google Analytics 4 (`G-9WBC9137VQ`) and Plausible unconditionally, while `frontend/src/index.js` and the cookie banner say analytics starts only after consent. Not changed, because it would stop data collection you may rely on. Decision needed: gate GA behind consent (the `initGA()` path already exists; set `REACT_APP_GA_MEASUREMENT_ID` in Vercel) or correct the privacy wording.

## Deliberately left alone
Webhook-secret derivation, legacy secret-less custom-bot webhooks, rate-limiter IP source and the Redis-down fallback were not touched: each can break live bots, and the fix needs a dual-secret migration plan and a staged rollout, not a quick patch.

## Rollback

Every risky commit has an entry in `REVERT.md` with the exact command and kill switches: `AI_TOKEN_QUOTA_ENFORCE`, `AI_BURST_GUARD`, `AI_BURST_LIMIT_PER_HOUR`.
