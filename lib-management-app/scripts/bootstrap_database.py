#!/usr/bin/env python3
"""Create the local SQLite schema and load sanitized seed data when empty."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import unquote

from passlib.context import CryptContext


APP_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = APP_ROOT / "db" / "seed_data.json"
PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def load_dotenv() -> None:
    env_path = APP_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def sqlite_db_path() -> Path:
    url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./db/library_management.db")
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            raw_path = unquote(url[len(prefix):])
            path = Path(raw_path)
            return path if path.is_absolute() else APP_ROOT / path
    raise SystemExit(f"Unsupported DATABASE_URL for local bootstrap: {url}")


async def create_schema() -> None:
    sys.path.insert(0, str(APP_ROOT))
    sys.path.insert(0, str(APP_ROOT / "services" / "library-data-service"))

    from src.database import Base, engine  # type: ignore
    from src.models import orm  # noqa: F401  # type: ignore

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def create_support_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            full_name TEXT,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin','viewer')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            last_login TEXT
        );

        CREATE TABLE IF NOT EXISTS scraper_registry_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registry_key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            ecosystem TEXT NOT NULL DEFAULT 'mobile',
            framework_language TEXT,
            base_url TEXT,
            timeout_seconds INTEGER NOT NULL DEFAULT 10,
            rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
            max_retries INTEGER NOT NULL DEFAULT 3,
            circuit_breaker_threshold INTEGER NOT NULL DEFAULT 5,
            circuit_breaker_cooldown INTEGER NOT NULL DEFAULT 60,
            custom_headers TEXT,
            strategy_class TEXT,
            release_phase TEXT NOT NULL DEFAULT 'mvp',
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_by TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS notification_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cron_expression TEXT NOT NULL DEFAULT '0 8 * * 1',
            enabled INTEGER NOT NULL DEFAULT 1,
            channels TEXT NOT NULL DEFAULT 'both',
            email_recipients TEXT,
            teams_webhook_url TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )


def load_seed_data(db_path: Path) -> None:
    if not SEED_PATH.exists():
        print("Seed file not found; schema is ready.")
        return

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        create_support_tables(conn)
        for table, rows in seed.get("tables", {}).items():
            if not rows:
                continue
            columns = table_columns(conn, table)
            if not columns:
                print(f"Skipping seed table not present in schema: {table}")
                continue
            if table_count(conn, table) > 0:
                print(f"Skipping seed table with existing rows: {table}")
                continue

            row_columns = [column for column in rows[0].keys() if column in columns]
            placeholders = ", ".join("?" for _ in row_columns)
            quoted_columns = ", ".join(f'"{column}"' for column in row_columns)
            sql = f'INSERT OR IGNORE INTO "{table}" ({quoted_columns}) VALUES ({placeholders})'
            values = [[row.get(column) for column in row_columns] for row in rows]
            conn.executemany(sql, values)
            print(f"Seeded {conn.total_changes} total rows after table: {table}")
        conn.commit()
    finally:
        conn.close()


def ensure_default_admin(db_path: Path) -> None:
    username = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
    password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "changeme")
    conn = sqlite3.connect(db_path)
    try:
        if table_count(conn, "users") > 0:
            print("Skipping default admin; users table already has rows")
            return
        conn.execute(
            """
            INSERT INTO users (username, email, hashed_password, role, is_active)
            VALUES (?, ?, ?, 'admin', 1)
            """,
            (username, f"{username}@lib-mgmt.local", PWD_CONTEXT.hash(password)),
        )
        conn.commit()
        print(f"Created default admin user: {username}")
    finally:
        conn.close()


async def main() -> None:
    load_dotenv()
    db_path = sqlite_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    await create_schema()
    load_seed_data(db_path)
    ensure_default_admin(db_path)
    print(f"Database ready: {db_path}")


if __name__ == "__main__":
    asyncio.run(main())