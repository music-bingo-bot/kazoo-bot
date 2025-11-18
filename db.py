import time
from typing import List, Optional, Tuple

import aiosqlite

DB_PATH = "uploads/db.sqlite3"


CREATE_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id   INTEGER PRIMARY KEY,
    username  TEXT,
    joined_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tracks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    points     INTEGER NOT NULL DEFAULT 1,
    hint       TEXT,
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    sent_at    INTEGER
);

CREATE TABLE IF NOT EXISTS broadcast_files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_id INTEGER NOT NULL,
    kind         TEXT NOT NULL, -- photo / video / file
    path         TEXT NOT NULL,
    created_at   INTEGER NOT NULL,
    FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id) ON DELETE CASCADE
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_SQL)
        await db.commit()


# ---------- Users ----------

async def add_user(user_id: int, username: Optional[str]) -> None:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, joined_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username
            """,
            (user_id, username, now),
        )
        await db.commit()


async def get_all_users() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        rows = await cur.fetchall()
    return [r[0] for r in rows]


# ---------- Tracks ----------

async def create_track(title: str, points: int, hint: Optional[str]) -> int:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tracks (title, points, hint, is_active, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (title, points, hint, now),
        )
        await db.commit()
        return cur.lastrowid


async def list_tracks() -> List[Tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, title, points, hint, is_active, created_at "
            "FROM tracks ORDER BY id DESC"
        )
        rows = await cur.fetchall()
    return rows


async def get_track(track_id: int) -> Optional[Tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, title, points, hint, is_active, created_at "
            "FROM tracks WHERE id = ?",
            (track_id,),
        )
        row = await cur.fetchone()
    return row


async def update_track(
    track_id: int,
    title: str,
    points: int,
    hint: Optional[str],
    is_active: bool,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tracks SET title = ?, points = ?, hint = ?, is_active = ? "
            "WHERE id = ?",
            (title, points, hint, 1 if is_active else 0, track_id),
        )
        await db.commit()


async def delete_track(track_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        await db.commit()


async def get_random_track() -> Optional[Tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, title, points, hint, is_active, created_at "
            "FROM tracks WHERE is_active = 1 ORDER BY RANDOM() LIMIT 1"
        )
        row = await cur.fetchone()
    return row


# ---------- Broadcasts ----------

async def create_broadcast(text: str) -> int:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO broadcasts (text, created_at) VALUES (?, ?)",
            (text, now),
        )
        await db.commit()
        return cur.lastrowid


async def mark_broadcast_sent(broadcast_id: int) -> None:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE broadcasts SET sent_at = ? WHERE id = ?",
            (now, broadcast_id),
        )
        await db.commit()


async def list_broadcasts() -> List[Tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, text, created_at, sent_at "
            "FROM broadcasts ORDER BY COALESCE(sent_at, created_at) DESC"
        )
        rows = await cur.fetchall()
    return rows


async def delete_broadcast(broadcast_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM broadcasts WHERE id = ?", (broadcast_id,))
        await db.commit()


# ---------- Broadcast media ----------

async def create_broadcast_file(
    broadcast_id: int,
    kind: str,
    path: str,
) -> int:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO broadcast_files (broadcast_id, kind, path, created_at) "
            "VALUES (?, ?, ?, ?)",
            (broadcast_id, kind, path, now),
        )
        await db.commit()
        return cur.lastrowid


async def get_broadcast_files(broadcast_id: int) -> List[Tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, kind, path, created_at "
            "FROM broadcast_files WHERE broadcast_id = ? "
            "ORDER BY id ASC",
            (broadcast_id,),
        )
        rows = await cur.fetchall()
    return rows
