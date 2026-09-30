#!/usr/bin/env bash
# Copy the Telegizer database from Neon back to Railway Postgres.
#
# Read-only against Neon. Backs up the current Railway DB first. Does NOT change any
# Railway variable or redeploy anything — that is a manual step (see MIGRATE_NEON_TO_RAILWAY.md).
#
# Required env vars (never commit them):
#   NEON_URL_DIRECT   Neon *direct/unpooled* URL  (Neon console -> Connect -> untick "Connection pooling")
#   RAILWAY_DB_URL    Railway Postgres *public* URL (Railway -> Postgres service -> Variables -> DATABASE_PUBLIC_URL)
#
# Needs pg_dump / pg_restore / psql, major version >= the Neon server (18).
set -euo pipefail

: "${NEON_URL_DIRECT:?set NEON_URL_DIRECT}"
: "${RAILWAY_DB_URL:?set RAILWAY_DB_URL}"
for t in pg_dump pg_restore psql; do command -v "$t" >/dev/null || { echo "missing $t"; exit 1; }; done

ts=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p backups
KEY_TABLES="users groups telegram_groups bots custom_bots members official_members payment_history scheduled_messages audit_logs knowledge_documents user_telegram_accounts"

count() { # count <url> <table>
  psql "$1" -Atc "SELECT count(*) FROM $2" 2>/dev/null || echo "n/a"
}

echo "== 1/5 Backup current Railway DB (pre-restore safety copy)"
pg_dump "$RAILWAY_DB_URL" --no-owner --no-privileges -Fc -f "backups/railway_pre_restore_$ts.dump"

echo "== 2/5 Dump Neon (~60 MB expected; counts toward Neon transfer quota)"
pg_dump "$NEON_URL_DIRECT" --no-owner --no-privileges -Fc -f "backups/neon_$ts.dump"
ls -lh "backups/neon_$ts.dump"

echo "== 3/5 Row counts BEFORE restore"
printf '%-24s %10s %10s\n' table neon railway_old
for t in $KEY_TABLES; do printf '%-24s %10s %10s\n' "$t" "$(count "$NEON_URL_DIRECT" $t)" "$(count "$RAILWAY_DB_URL" $t)"; done

read -r -p "Restore Neon dump OVER the Railway DB now? (type YES) " ans
[ "$ans" = "YES" ] || { echo "aborted; nothing was changed"; exit 0; }

echo "== 4/5 Restore into Railway"
pg_restore --clean --if-exists --no-owner --no-privileges -d "$RAILWAY_DB_URL" "backups/neon_$ts.dump" || \
  echo "pg_restore reported errors — review above (extension/vector errors are expected if pgvector is missing)"

echo "== 5/5 Row counts AFTER restore (railway must equal neon column above)"
printf '%-24s %10s\n' table railway_new
for t in $KEY_TABLES; do printf '%-24s %10s\n' "$t" "$(count "$RAILWAY_DB_URL" $t)"; done
echo "Done. Next: switch DATABASE_URL in Railway (see MIGRATE_NEON_TO_RAILWAY.md)."
