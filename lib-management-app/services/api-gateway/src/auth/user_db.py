"""
API Gateway — user lookup from the shared SQLite DB.

Reads from the `users` table created in migration 001.
Password hashing uses bcrypt via passlib.
"""
from __future__ import annotations
import sqlite3

from passlib.context import CryptContext

from ..config import settings

_pwd_ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

_DB_PATH = settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(_DB_PATH, timeout=5)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def get_user(username: str) -> dict | None:
    """Return user row dict or None if not found / DB unavailable."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT id, username, hashed_password, role, is_active FROM users WHERE username=? LIMIT 1",
            (username,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return {"id": row[0], "username": row[1], "password_hash": row[2],
                "role": row[3], "is_active": row[4]}
    except Exception:
        return None


def authenticate_user(username: str, password: str) -> dict | None:
    """Return user dict if credentials valid, else None."""
    user = get_user(username)
    if user is None:
        return None
    if not user.get("is_active", False):
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def list_users() -> list[dict]:
    """Return all users (id, username, email, full_name, role, is_active, created_at, last_login)."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, username, email, full_name, role, is_active, created_at, last_login FROM users ORDER BY id"
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "username": r[1], "email": r[2], "full_name": r[3],
             "role": r[4], "is_active": bool(r[5]), "created_at": r[6], "last_login": r[7]}
            for r in rows
        ]
    except Exception:
        return []


def create_user(username: str, email: str, password: str, full_name: str | None = None,
                role: str = "viewer") -> dict | str:
    """Create user. Returns user dict on success, or error string on failure."""
    try:
        conn = _get_conn()
        existing = conn.execute("SELECT id FROM users WHERE username=? OR email=?",
                                (username, email)).fetchone()
        if existing:
            conn.close()
            return "Username or email already exists"
        conn.execute(
            "INSERT INTO users (username, email, full_name, hashed_password, role, is_active) VALUES (?,?,?,?,?,1)",
            (username, email, full_name, hash_password(password), role),
        )
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return {"id": user_id, "username": username, "email": email,
                "full_name": full_name, "role": role, "is_active": True}
    except Exception as exc:
        return str(exc)


def update_user(user_id: int, **fields: object) -> dict | str:
    """Update allowed fields. Returns updated user dict or error string."""
    allowed = {"email", "full_name", "role", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "password" in fields and fields["password"]:
        updates["hashed_password"] = hash_password(str(fields["password"]))
    if not updates:
        return "No valid fields to update"
    try:
        conn = _get_conn()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE users SET {set_clause} WHERE id=?",
                     list(updates.values()) + [user_id])
        conn.commit()
        row = conn.execute(
            "SELECT id, username, email, full_name, role, is_active FROM users WHERE id=?",
            (user_id,)
        ).fetchone()
        conn.close()
        if row is None:
            return "User not found"
        return {"id": row[0], "username": row[1], "email": row[2],
                "full_name": row[3], "role": row[4], "is_active": bool(row[5])}
    except Exception as exc:
        return str(exc)


def delete_user(user_id: int) -> bool | str:
    """Permanently delete a user by id. Returns True on success or error string."""
    try:
        conn = _get_conn()
        row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            conn.close()
            return "User not found"
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        return str(exc)


def change_password(user_id: int, old_password: str, new_password: str) -> bool | str:
    """Verify old password then set new one. Returns True on success or error string."""
    try:
        conn = _get_conn()
        row = conn.execute("SELECT hashed_password FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            conn.close()
            return "User not found"
        if not verify_password(old_password, row[0]):
            conn.close()
            return "Current password is incorrect"
        conn.execute("UPDATE users SET hashed_password=? WHERE id=?",
                     (hash_password(new_password), user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        return str(exc)


def ensure_default_admin() -> None:
    """Create the default admin account if the users table is empty."""
    try:
        conn = _get_conn()
        # Check table exists first
        tbl = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if tbl is None:
            conn.close()
            return
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            conn.execute(
                "INSERT INTO users (username, email, hashed_password, role, is_active) VALUES (?,?,?,?,?)",
                (
                    settings.default_admin_username,
                    f"{settings.default_admin_username}@lib-mgmt.local",
                    hash_password(settings.default_admin_password),
                    "admin",
                    1,
                ),
            )
            conn.commit()
        conn.close()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("ensure_default_admin failed: %s", exc)
