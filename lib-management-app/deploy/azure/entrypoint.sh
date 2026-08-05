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

exec /usr/local/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
