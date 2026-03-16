from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class ClientAuthStore:
    """SQLite-backed client credential store for WebSocket authentication."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or Path(__file__).with_name("clients.db")
        self._lock = threading.Lock()
        self._init_db()
        self._seed_default_client()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS clients (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        salt TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_auth_at TEXT
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def _seed_default_client(self) -> None:
        # Ensure first-time setup has one usable account.
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM clients").fetchone()
                if row["cnt"] == 0:
                    now = self._now_iso()
                    salt = os.urandom(16)
                    password_hash = self._hash_password("admin123", salt)
                    conn.execute(
                        """
                        INSERT INTO clients (username, password_hash, salt, is_active, created_at, updated_at)
                        VALUES (?, ?, ?, 1, ?, ?)
                        """,
                        ("admin", password_hash, salt.hex(), now, now),
                    )
                    conn.commit()
            finally:
                conn.close()

    def list_clients(self) -> list[dict]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT id, username, is_active, created_at, updated_at, last_auth_at
                    FROM clients
                    ORDER BY username COLLATE NOCASE ASC
                    """
                ).fetchall()
                return [
                    {
                        "id": row["id"],
                        "username": row["username"],
                        "is_active": bool(row["is_active"]),
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "last_auth_at": row["last_auth_at"],
                    }
                    for row in rows
                ]
            finally:
                conn.close()

    def add_client(self, username: str, password: str) -> None:
        username = username.strip()
        self._validate_credentials(username, password)

        salt = os.urandom(16)
        password_hash = self._hash_password(password, salt)
        now = self._now_iso()

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO clients (username, password_hash, salt, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (username, password_hash, salt.hex(), now, now),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Client '{username}' already exists.") from exc
            finally:
                conn.close()

    def delete_client(self, client_id: int) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
                conn.commit()
            finally:
                conn.close()

    def set_active(self, client_id: int, active: bool) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE clients SET is_active = ?, updated_at = ? WHERE id = ?",
                    (1 if active else 0, self._now_iso(), client_id),
                )
                conn.commit()
            finally:
                conn.close()

    def update_password(self, client_id: int, password: str) -> None:
        if len(password) < 4:
            raise ValueError("Password must be at least 4 characters long.")

        salt = os.urandom(16)
        password_hash = self._hash_password(password, salt)

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE clients SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
                    (password_hash, salt.hex(), self._now_iso(), client_id),
                )
                conn.commit()
            finally:
                conn.close()

    def authenticate_client(self, username: str, password: str) -> tuple[bool, str]:
        username = username.strip()
        if not username or not password:
            return False, "Username and password are required."

        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT id, password_hash, salt, is_active
                    FROM clients
                    WHERE username = ?
                    """,
                    (username,),
                ).fetchone()
                if row is None:
                    return False, "Invalid credentials."
                if not bool(row["is_active"]):
                    return False, "Client is disabled."

                calc_hash = self._hash_password(password, bytes.fromhex(row["salt"]))
                if not hmac.compare_digest(calc_hash, row["password_hash"]):
                    return False, "Invalid credentials."

                conn.execute(
                    "UPDATE clients SET last_auth_at = ?, updated_at = ? WHERE id = ?",
                    (self._now_iso(), self._now_iso(), row["id"]),
                )
                conn.commit()
                return True, "Authenticated."
            finally:
                conn.close()

    @staticmethod
    def _validate_credentials(username: str, password: str) -> None:
        if not username:
            raise ValueError("Username is required.")
        if len(password) < 4:
            raise ValueError("Password must be at least 4 characters long.")

    @staticmethod
    def _hash_password(password: str, salt: bytes) -> str:
        # Basic secure hashing: salted PBKDF2-HMAC-SHA256.
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
        return digest.hex()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
