"""SQLite orqali foydalanuvchilar va yuklashlar statistikasi.

Standart `sqlite3` ishlatiladi; bloklovchi chaqiruvlar `asyncio.to_thread` orqali
alohida thread'da bajariladi. Har bir amal o'z ulanishini ochadi (SQLite uchun arzon
va thread-xavfsiz), WAL rejimi bir vaqtdagi o'qish/yozishni yengillashtiradi.
Havolalar saqlanmaydi - faqat post kodi (shortcode).
"""
from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    username       TEXT,
    first_name     TEXT,
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    requests_count INTEGER NOT NULL DEFAULT 0,
    is_blocked     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    shortcode   TEXT,
    kind        TEXT,
    status      TEXT NOT NULL CHECK (status IN ('success', 'failed')),
    error_type  TEXT,
    file_size   INTEGER,
    duration_ms INTEGER,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created_at);
CREATE INDEX IF NOT EXISTS idx_downloads_user ON downloads(user_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # -- sinxron amallar (thread ichida bajariladi) ------------------------
    def _init_sync(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            with conn:
                conn.executescript(_SCHEMA)
                # Eski bazalar uchun migratsiya: is_blocked ustuni.
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
                if "is_blocked" not in columns:
                    conn.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0")

    def _upsert_user_sync(self, user_id: int, username: str | None, first_name: str | None) -> None:
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, first_seen, last_seen, requests_count)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_seen = excluded.last_seen,
                    is_blocked = 0,
                    requests_count = users.requests_count + 1
                """,
                (user_id, username, first_name, now, now),
            )

    def _get_broadcast_recipients_sync(self) -> list[int]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT user_id FROM users WHERE is_blocked = 0 ORDER BY user_id").fetchall()
            return [int(row["user_id"]) for row in rows]

    def _mark_blocked_sync(self, user_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))

    def _record_download_sync(
        self,
        user_id: int,
        shortcode: str | None,
        kind: str | None,
        status: str,
        error_type: str | None,
        file_size: int | None,
        duration_ms: int | None,
    ) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO downloads
                    (user_id, shortcode, kind, status, error_type, file_size, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, shortcode, kind, status, error_type, file_size, duration_ms, _now()),
            )

    def _get_stats_sync(self) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            def one(sql: str) -> int:
                row = conn.execute(sql).fetchone()
                return int(row[0] or 0)

            stats: dict[str, Any] = {
                "total_users": one("SELECT COUNT(*) FROM users"),
                "blocked_users": one("SELECT COUNT(*) FROM users WHERE is_blocked = 1"),
                "new_users_today": one("SELECT COUNT(*) FROM users WHERE date(first_seen) = date('now')"),
                "active_users_today": one("SELECT COUNT(*) FROM users WHERE date(last_seen) = date('now')"),
                "total_downloads": one("SELECT COUNT(*) FROM downloads"),
                "successful_downloads": one("SELECT COUNT(*) FROM downloads WHERE status = 'success'"),
                "failed_downloads": one("SELECT COUNT(*) FROM downloads WHERE status = 'failed'"),
                "downloads_last_24h": one(
                    "SELECT COUNT(*) FROM downloads WHERE created_at >= datetime('now', '-1 day')"
                ),
                "total_bytes": one("SELECT COALESCE(SUM(file_size), 0) FROM downloads WHERE status = 'success'"),
            }
            rows = conn.execute(
                """
                SELECT COALESCE(error_type, 'Unknown') AS error_type, COUNT(*) AS cnt
                FROM downloads WHERE status = 'failed'
                GROUP BY error_type ORDER BY cnt DESC LIMIT 5
                """
            ).fetchall()
            stats["top_errors"] = [(row["error_type"], int(row["cnt"])) for row in rows]
            return stats

    # -- asinxron API ------------------------------------------------------
    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    async def upsert_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        await asyncio.to_thread(self._upsert_user_sync, user_id, username, first_name)

    async def record_download(
        self,
        *,
        user_id: int,
        shortcode: str | None,
        kind: str | None,
        success: bool,
        error_type: str | None = None,
        file_size: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_download_sync,
            user_id,
            shortcode,
            kind,
            "success" if success else "failed",
            error_type,
            file_size,
            duration_ms,
        )

    async def get_broadcast_recipients(self) -> list[int]:
        """Botni bloklamagan barcha foydalanuvchilar ID'lari."""
        return await asyncio.to_thread(self._get_broadcast_recipients_sync)

    async def mark_blocked(self, user_id: int) -> None:
        await asyncio.to_thread(self._mark_blocked_sync, user_id)

    async def get_stats(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_stats_sync)
