# Discord Board — Setup Checklist

Two parts: **(A) what you do RIGHT NOW** (before any code can be tested),
and **(B) deploy-time steps** (later, at the end of Phase 0). Nothing here touches Telegizer.

> 🔒 SECURITY: Never paste the bot **token** or **client secret** into chat or commit them.
> You put them into env vars yourself. I never need to see them.

---

## A. DO THIS NOW (you — ~15 min)

### A1. Create the Discord Application
1. Go to https://discord.com/developers/applications → **New Application** → give it a name (your Discord board's brand).
2. **Bot** tab → **Add Bot**.
   - Copy the **TOKEN** → save it somewhere private (this is the bot's password).
   - Scroll to **Privileged Gateway Intents** and turn ON:
     - ✅ **MESSAGE CONTENT INTENT** (needed for moderation/commands)
     - ✅ **SERVER MEMBERS INTENT** (needed for welcome/roles/raid guard)
     - (Presence intent: leave off unless we need it later.)
3. **OAuth2** tab:
   - Copy the **CLIENT ID** and **CLIENT SECRET** → save privately.
   - Under **Redirects**, add (for local dev): `http://localhost:5000/auth/discord/callback`
     (we'll add the production URL later.)

### A2. Create a test Discord server
- In the Discord app: click the **+** on the left → **Create My Own** → **For me and my friends**.
- This is our sandbox to test the bot. (Real customer servers come later.)

### A3. Name/brand — DONE
- ✅ Name chosen: **Guildizer**. Use this for the Discord Application name, bot name, and UI title.

### A4. Hand me the NON-secret values
- Share with me only the **CLIENT ID** (that one is safe / public).
- Keep TOKEN and CLIENT SECRET to yourself — you'll paste them into the env file I prepare.

**That's all you need before I start building.** Railway/Vercel come later — see Part B.

---

## B. DEPLOY-TIME (later — end of Phase 0, I give exact steps then)

### B1. Railway — add a NEW SERVICE (not a new account)
- Open your existing Railway project → **New** → **GitHub Repo** → same repo.
- Settings → **Root Directory** = `discord-board/backend`
- Settings → **Watch Paths** = `discord-board/**` (so Telegizer pushes never redeploy this)
- Add a **new Postgres** in the project for Discord (separate DB).
- **Variables** → paste Discord env vars (token, client id/secret, DB url, etc.).
- Repeat for the **worker** service if needed.
- ℹ️ The worker pins **Python 3.12** via `backend/runtime.txt` — `discord.py` 2.4
  uses the `audioop` module that Python 3.13+ removed. Keep the pin (or bump
  discord.py + add `audioop-lts`) so the bot boots on Railway.

### B2. Vercel — add a NEW PROJECT (same account)
- **Add New → Project** → same GitHub repo.
- **Root Directory** = `discord-board/frontend`
- Under **Git** → **Ignored Build Step**: only build when `discord-board/frontend` changes.
- Add frontend env vars (API URL, Discord client id).

### B3. Final wiring
- Update the Discord App OAuth2 redirect to the production dashboard URL.
- Confirm: a push to `main` auto-deploys ONLY the Discord services, Telegizer untouched.

---

## Status
- [ ] A1 Discord Application created
- [ ] A2 Test server created
- [ ] A3 Name chosen
- [ ] A4 Client ID shared (secrets kept private)
- [ ] B (deploy) — later
