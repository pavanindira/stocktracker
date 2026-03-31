#!/bin/bash
# entrypoint.sh
# Runs inside the app container on every start.
# 1. Waits for Postgres to be ready
# 2. Runs Alembic migrations
# 3. Seeds the default admin (idempotent — skips if already exists)
# 4. Starts Uvicorn

set -e

echo "⏳ Waiting for PostgreSQL..."
until python3 - << 'EOF'
import os, sys, psycopg2
try:
    psycopg2.connect(os.environ["DATABASE_URL"])
    sys.exit(0)
except Exception:
    sys.exit(1)
EOF
do
  echo "   PostgreSQL not ready — retrying in 2s"
  sleep 2
done
echo "✅ PostgreSQL is ready"

echo "⬆️  Running Alembic migrations..."
alembic upgrade head
echo "✅ Migrations complete"

echo "🌱 Seeding admin..."
python3 seed.py
echo "✅ Seed complete"

echo "🚀 Starting StockTracker..."
exec uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${WORKERS:-2}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
