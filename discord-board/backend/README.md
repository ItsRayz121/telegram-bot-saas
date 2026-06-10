# Guildizer — Backend

Standalone Flask API + `discord.py` bot for the **Guildizer** Discord board.
Fully isolated from the Telegizer (Telegram) code — no shared imports, own DB, own deploy.

## Two processes
- **web** (`app.py`) — Flask API the dashboard talks to.
- **worker** (`bot.py`) — the Discord bot (Gateway connection + slash commands).

## Local setup
```bash
cd discord-board/backend

# 1. Create a virtual env and install deps
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
pip install -r requirements.txt

# 2. Create your .env (NEVER commit it)
copy .env.example .env          # Windows
#   then open .env and paste your real BOT TOKEN + CLIENT SECRET

# 3a. Run the API
python app.py                   # -> http://localhost:5000/health

# 3b. Run the bot (separate terminal)
python bot.py                   # -> logs "Guildizer is online as ..."
```

## Test the bot
1. Invite the bot to your test server using this URL (replace nothing — client id is baked in):
   `https://discord.com/oauth2/authorize?client_id=1514145107559845949&scope=bot+applications.commands&permissions=8`
2. In the server, type `/ping` → the bot replies "🟢 Guildizer is online — Xms".

## Deploy (later — see ../SETUP.md Part B)
Railway service rooted at `discord-board/backend`, Procfile defines `web` + `worker`.
Set Watch Paths to `discord-board/**` so Telegizer pushes never redeploy this.
