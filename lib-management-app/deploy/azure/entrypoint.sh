#!/bin/sh
# Initialise the SQLite DB and seed data, then start supervisord.
set -e

DB_DIR="/data/db"
DB_FILE="$DB_DIR/library_management.db"

mkdir -p "$DB_DIR"

# Point app's db/ symlink at the persistent volume so alembic finds the right path
rm -rf /app/lib-management-app/db
ln -sf "$DB_DIR" /app/lib-management-app/db

# Run migrations (idempotent)
cd /app/lib-management-app
export DATABASE_URL="sqlite+aiosqlite:////${DB_FILE}"
python3 -m alembic -c migrations/alembic.ini upgrade head

# Seed only on first boot
if [ ! -f "$DB_DIR/.seeded" ]; then
  python3 scripts/bootstrap_database.py || true
  touch "$DB_DIR/.seeded"
fi

exec /usr/local/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
