#!/bin/sh
# Initialise the SQLite DB and seed data, then start supervisord.
set -e

DB_DIR="/data/db"
DB_FILE="$DB_DIR/library_management.db"

mkdir -p "$DB_DIR"

# Preserve seed_data.json from the image before replacing the db/ dir with a symlink
if [ -f /app/lib-management-app/db/seed_data.json ] && [ ! -f "$DB_DIR/seed_data.json" ]; then
  cp /app/lib-management-app/db/seed_data.json "$DB_DIR/"
fi

# Point app's db/ symlink at the persistent volume so alembic finds the right path
rm -rf /app/lib-management-app/db
ln -sf "$DB_DIR" /app/lib-management-app/db

# Run migrations (idempotent) — failure is non-fatal; bootstrap covers schema creation
cd /app/lib-management-app
export DATABASE_URL="sqlite+aiosqlite:////${DB_FILE}"
python3 -m alembic -c migrations/alembic.ini upgrade head || {
  echo "WARNING: alembic migration failed — schema will be created by bootstrap script"
}

# Seed only on first boot
if [ ! -f "$DB_DIR/.seeded" ]; then
  PYTHONPATH=/app python3 scripts/bootstrap_database.py || true
  touch "$DB_DIR/.seeded"
fi

# Start background services (non-critical; api-gateway handles unavailable upstreams gracefully)
( cd /app/services/library-data-service && \
  PYTHONPATH=/app DATABASE_URL="$DATABASE_URL" INTERNAL_SERVICE_KEY="$INTERNAL_SERVICE_KEY" \
  exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8001 ) &

( cd /app/services/scraper-service && \
  PYTHONPATH=/app INTERNAL_SERVICE_KEY="$INTERNAL_SERVICE_KEY" \
  exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8002 ) &

( cd /app/services/comparison-service && \
  PYTHONPATH=/app INTERNAL_SERVICE_KEY="$INTERNAL_SERVICE_KEY" \
  LIBRARY_DATA_SERVICE_URL="http://localhost:8001" SCRAPER_SERVICE_URL="http://localhost:8002" \
  exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8003 ) &

( cd /app/services/recommendation-service && \
  PYTHONPATH=/app INTERNAL_SERVICE_KEY="$INTERNAL_SERVICE_KEY" \
  LIBRARY_DATA_SERVICE_URL="http://localhost:8001" COMPARISON_SERVICE_URL="http://localhost:8003" \
  LLM_PROVIDER="$LLM_PROVIDER" LLM_MODEL="$LLM_MODEL" LLM_API_KEY="$LLM_API_KEY" \
  exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8004 ) &

( cd /app/services/notification-service && \
  PYTHONPATH=/app INTERNAL_SERVICE_KEY="$INTERNAL_SERVICE_KEY" \
  SMTP_HOST="${SMTP_HOST:-smtp.office365.com}" SMTP_PORT="${SMTP_PORT:-587}" \
  SMTP_USERNAME="${SMTP_USERNAME:-}" SMTP_PASSWORD="${SMTP_PASSWORD:-}" \
  exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8005 ) &

( cd /app/services/scheduler-service && \
  PYTHONPATH=/app INTERNAL_SERVICE_KEY="$INTERNAL_SERVICE_KEY" \
  LIBRARY_DATA_SERVICE_URL="http://localhost:8001" SCRAPER_SERVICE_URL="http://localhost:8002" \
  COMPARISON_SERVICE_URL="http://localhost:8003" RECOMMENDATION_SERVICE_URL="http://localhost:8004" \
  NOTIFICATION_SERVICE_URL="http://localhost:8005" SCHEDULE_ENABLED="${SCHEDULE_ENABLED:-true}" \
  exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8006 ) &

# api-gateway runs in foreground — container exits (and restarts) if it crashes
exec sh -c '
  cd /app/services/api-gateway
  export PYTHONPATH=/app
  export LIBRARY_DATA_SERVICE_URL=http://localhost:8001
  export SCRAPER_SERVICE_URL=http://localhost:8002
  export COMPARISON_SERVICE_URL=http://localhost:8003
  export RECOMMENDATION_SERVICE_URL=http://localhost:8004
  export NOTIFICATION_SERVICE_URL=http://localhost:8005
  export SCHEDULER_SERVICE_URL=http://localhost:8006
  exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000
'
