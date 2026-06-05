import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import aiosqlite

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'denied', 'deployed', 'failed')),
    container_name TEXT,
    password_hash TEXT,
    api_token TEXT UNIQUE,
    display_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON registrations(status);
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    event_type TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_events_user ON security_events(username);
"""

_MIGRATIONS = (
    ("password_hash", "TEXT"),
    ("api_token", "TEXT"),
    ("display_name", "TEXT"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str | None = None) -> None:
        self._path = str(path or DB_PATH)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_SCHEMA)
            await self._migrate_columns(db)
            await db.commit()

    async def _migrate_columns(self, db: aiosqlite.Connection) -> None:
        cursor = await db.execute("PRAGMA table_info(registrations)")
        existing = {row[1] for row in await cursor.fetchall()}
        for column, col_type in _MIGRATIONS:
            if column not in existing:
                await db.execute(
                    f"ALTER TABLE registrations ADD COLUMN {column} {col_type}"
                )

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        db = await aiosqlite.connect(self._path)
        db.row_factory = aiosqlite.Row
        try:
            yield db
        finally:
            await db.close()

    async def create_student_account(
        self,
        username: str,
        password_hash: str,
        api_token: str,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        existing = await self.get_by_username(username)
        if existing:
            if existing["status"] == "denied":
                async with self.connect() as db:
                    await db.execute(
                        """
                        UPDATE registrations
                        SET status = 'pending', password_hash = ?, api_token = ?,
                            display_name = ?, updated_at = ?, error_message = NULL
                        WHERE username = ?
                        """,
                        (password_hash, api_token, display_name, now, username),
                    )
                    await db.commit()
                row = await self.get_by_username(username)
                if row:
                    return row
            return existing

        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO registrations (
                    username, status, password_hash, api_token,
                    display_name, created_at, updated_at
                )
                VALUES (?, 'pending', ?, ?, ?, ?, ?)
                """,
                (username, password_hash, api_token, display_name, now, now),
            )
            await db.commit()
            reg_id = cursor.lastrowid
        created = await self.get_by_id(reg_id)  # type: ignore[arg-type]
        if created is None:
            raise RuntimeError("account creation failed")
        return created

    async def verify_login(self, username: str, password: str) -> dict[str, Any] | None:
        from .auth_store import verify_password

        row = await self.get_by_username(username)
        if not row or not row.get("password_hash"):
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return row

    async def enqueue_registration(self, username: str) -> dict[str, Any]:
        now = _now()
        existing = await self.get_by_username(username)
        if existing:
            if existing["status"] == "denied":
                async with self.connect() as db:
                    await db.execute(
                        """
                        UPDATE registrations
                        SET status = 'pending', updated_at = ?, error_message = NULL
                        WHERE username = ?
                        """,
                        (now, username),
                    )
                    await db.commit()
                refreshed = await self.get_by_username(username)
                if refreshed:
                    return refreshed
            return existing

        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO registrations (username, status, created_at, updated_at)
                VALUES (?, 'pending', ?, ?)
                """,
                (username, now, now),
            )
            await db.commit()
            reg_id = cursor.lastrowid
        created = await self.get_by_id(reg_id)  # type: ignore[arg-type]
        if created is None:
            raise RuntimeError("registration insert failed")
        return created

    async def get_by_id(self, reg_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM registrations WHERE id = ?", (reg_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_by_username(self, username: str) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM registrations WHERE username = ?", (username,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_by_api_token(self, token: str) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM registrations WHERE api_token = ?", (token,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def set_api_token(self, reg_id: int, api_token: str) -> None:
        now = _now()
        async with self.connect() as db:
            await db.execute(
                """
                UPDATE registrations
                SET api_token = ?, updated_at = ?
                WHERE id = ?
                """,
                (api_token, now, reg_id),
            )
            await db.commit()

    async def record_security_event(
        self,
        username: str | None,
        event_type: str,
        detail: str | None = None,
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO security_events (username, event_type, detail, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (username, event_type[:64], (detail or "")[:500], _now()),
            )
            await db.commit()

    async def list_security_events(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT * FROM security_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def list_by_status(self, status: str) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT * FROM registrations
                WHERE status = ?
                ORDER BY created_at ASC
                """,
                (status,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT * FROM registrations
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def set_status(
        self,
        reg_id: int,
        status: str,
        *,
        container_name: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        now = _now()
        async with self.connect() as db:
            await db.execute(
                """
                UPDATE registrations
                SET status = ?, container_name = COALESCE(?, container_name),
                    updated_at = ?, error_message = ?
                WHERE id = ?
                """,
                (status, container_name, now, error_message, reg_id),
            )
            await db.commit()
        return await self.get_by_id(reg_id)


_db: Database | None = None
_db_lock = asyncio.Lock()


async def get_db() -> Database:
    global _db
    if _db is not None:
        return _db
    async with _db_lock:
        if _db is None:
            instance = Database()
            await instance.init()
            _db = instance
    return _db
