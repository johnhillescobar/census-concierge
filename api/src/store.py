"""Conversation store: one Postgres row per thread, turns in a jsonb array.

A thread is owned by a `user_id` and lives 48 hours from creation. Ownership,
expiry and the turn cap are enforced in SQL, so a foreign, missing or expired
thread is the same `None` and nothing can be appended past the cap. The pool is
an argument everywhere; the app creates it in its lifespan.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import FastAPI
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

MAX_TURNS = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    thread_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL,
    title      text NOT NULL DEFAULT 'New Chat',
    state      jsonb NOT NULL DEFAULT '{"turns": []}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now() + interval '48 hours'
);
CREATE INDEX IF NOT EXISTS conversations_expires_at ON conversations (expires_at);
"""

_LIVE = "thread_id = %(thread_id)s AND user_id = %(user_id)s AND expires_at > now()"


class PersistenceNotConfigured(RuntimeError):
    """`DATABASE_URL` was not set, so there is no pool."""


def require_pool(app: FastAPI) -> AsyncConnectionPool:
    pool: AsyncConnectionPool | None = getattr(app.state, "pool", None)
    if pool is None:
        raise PersistenceNotConfigured("persistence not configured: DATABASE_URL is unset")
    return pool


async def open_pool(url: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(url, open=False, kwargs={"autocommit": True})
    await pool.open(wait=True)
    async with pool.connection() as conn:
        await conn.execute(SCHEMA)
    await purge(pool)
    return pool


async def purge(pool: AsyncConnectionPool) -> int:
    async with pool.connection() as conn:
        cur = await conn.execute("DELETE FROM conversations WHERE expires_at <= now()")
        return cur.rowcount


async def create(pool: AsyncConnectionPool, user_id: UUID) -> dict[str, Any]:
    await purge(pool)
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "INSERT INTO conversations (user_id) VALUES (%s)"
            " RETURNING thread_id, title, created_at, expires_at",
            (user_id,),
        )
        return await cur.fetchone() or {}


async def load(pool: AsyncConnectionPool, thread_id: UUID, user_id: UUID) -> dict[str, Any] | None:
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT thread_id, title, state, created_at, expires_at FROM conversations"
            f" WHERE {_LIVE}",
            {"thread_id": thread_id, "user_id": user_id},
        )
        return await cur.fetchone()


async def append(
    pool: AsyncConnectionPool, thread_id: UUID, user_id: UUID, turn: dict[str, Any]
) -> Literal["appended", "full"] | None:
    """Add a turn atomically. None: not yours, missing or expired. "full": at the cap."""
    params = {"thread_id": thread_id, "user_id": user_id, "turn": Jsonb(turn), "cap": MAX_TURNS}
    async with pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE conversations SET updated_at = now(),"
            " state = jsonb_set(state, '{turns}', (state->'turns') || jsonb_build_array(%(turn)s))"
            f" WHERE {_LIVE} AND jsonb_array_length(state->'turns') < %(cap)s",
            params,
        )
        if cur.rowcount:
            return "appended"
    return "full" if await load(pool, thread_id, user_id) else None
