# Telegizer — Telegram Bot SaaS Platform

A production-ready SaaS platform for managing Telegram community bots with features including member verification, XP leveling, AutoMod, scheduled messages, and raid management.

## Features

- **Bot Management** — Add and manage multiple Telegram bots from one dashboard
- **Member Verification** — Button, math captcha, or word captcha challenges
- **XP & Levels** — Customizable XP system with role assignment and rank cards
- **AutoMod** — Spam, bad words, link filtering, caps lock, emoji limits
- **Moderation** — Warn, ban, kick, mute, tempban, tempmute commands
- **Scheduled Messages** — One-time or repeating announcements with media and buttons
- **Raid Manager** — Coordinate Twitter/X raids with XP rewards
- **Analytics** — Member growth, level distribution, moderation action charts
- **Billing** — Stripe-powered Free / Pro / Enterprise tiers
- **Admin Panel** — User management, subscription control, platform statistics

## Stack

| Layer | Tech |
|-------|------|
| Backend | Flask, SQLAlchemy, python-telegram-bot 20.x |
| Database | PostgreSQL |
| Queue | Celery + Redis |
| Auth | JWT (flask-jwt-extended) |
| Payments | Stripe |
| Frontend | React 18, Material-UI v5, Recharts |
| Deploy | Railway (backend), Vercel (frontend) |

## Local Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL
- Redis

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r ../requirements.txt
cp ../.env.example ../.env
# Edit .env with your values
python migrate.py
python app.py
```

### Frontend

```bash
cd frontend
npm install
# Create .env.local with:
# REACT_APP_API_URL=http://localhost:5000
npm start
```

### Celery Workers (optional, for scheduled messages)

```bash
# In separate terminals:
celery -A backend.scheduler worker --loglevel=info
celery -A backend.scheduler beat --loglevel=info
```

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | Flask secret key (random string) |
| `JWT_SECRET_KEY` | JWT signing secret (random string) |
| `REDIS_URL` | Redis connection URL |
| `STRIPE_SECRET_KEY` | Stripe secret key (sk_...) |
| `STRIPE_PUBLISHABLE_KEY` | Stripe publishable key (pk_...) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret (whsec_...) |
| `STRIPE_PRO_PRICE_ID` | Stripe Price ID for Pro plan |
| `STRIPE_ENTERPRISE_PRICE_ID` | Stripe Price ID for Enterprise plan |
| `SMTP_SERVER` | SMTP server hostname |
| `SMTP_PORT` | SMTP port (587 for TLS) |
| `SMTP_USERNAME` | SMTP username / email |
| `SMTP_PASSWORD` | SMTP password |
| `FROM_EMAIL` | Sender email address |
| `FRONTEND_URL` | Frontend URL for CORS and redirects |
| `ADMIN_EMAILS` | Comma-separated admin email addresses |

## Deployment

### Backend → Railway

1. Create a new Railway project and connect your repo
2. Add a PostgreSQL and Redis plugin
3. Set all environment variables in Railway settings
4. Railway will auto-detect the `Procfile` and deploy

### Frontend → Vercel

1. Import the `frontend/` directory into Vercel
2. Set build command: `npm run build`
3. Set output directory: `build`
4. Add environment variable: `REACT_APP_API_URL=https://your-railway-app.up.railway.app`
5. Deploy

### Stripe Webhooks

After deploying the backend, create a webhook in the Stripe Dashboard:
- URL: `https://your-backend.railway.app/api/billing/webhook`
- Events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`
- Copy the signing secret to `STRIPE_WEBHOOK_SECRET`

## Bot Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Copy the token
3. Add the bot to your dashboard via "Add Bot"
4. Invite the bot to your Telegram group
5. Make the bot an **admin** with appropriate permissions
6. The group will appear in the dashboard automatically

## Subscription Tiers

| Feature | Free | Pro ($9/mo) | Enterprise ($49/mo) |
|---------|------|-------------|---------------------|
| Bots | 1 | 5 | 50 |
| Groups | 1 per bot | Unlimited | Unlimited |
| Raids | ✗ | ✓ | ✓ |
| Analytics | ✗ | ✓ | ✓ |
| Scheduled Messages | ✗ | ✓ | ✓ |

## License

MIT
