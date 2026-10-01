import asyncio
import os
from uuid import uuid4

import pytest
from ask_fixtures import populated_response
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg_pool import AsyncConnectionPool
from src import store
from src.contract import AskResponse
from src.main import create_app

URL = os.environ.get("DATABASE_URL")


def turn(n: int = 0) -> dict[str, object]:
    return {"question": f"q{n}", "plan": None, "response": {"answer": str(n)}, "created_at": "t"}


async def expire(pool: AsyncConnectionPool, thread_id: object, interval: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE conversations SET expires_at = now() + %s::interval WHERE thread_id = %s",
            (interval, thread_id),
        )


async def test_foreign_user_gets_none_like_a_missing_thread(pool: AsyncConnectionPool) -> None:
    owner, other = uuid4(), uuid4()
    thread = (await store.create(pool, owner))["thread_id"]
    assert await store.load(pool, thread, other) is None
    assert await store.append(pool, thread, other, turn()) is None
    assert await store.load(pool, uuid4(), owner) is None
    assert await store.load(pool, thread, owner) is not None


async def test_expired_thread_is_none_before_any_purge(pool: AsyncConnectionPool) -> None:
    user = uuid4()
    thread = (await store.create(pool, user))["thread_id"]
    await expire(pool, thread, "-1 second")
    assert await store.load(pool, thread, user) is None
    assert await store.append(pool, thread, user, turn()) is None


async def test_concurrent_appends_lose_nothing(pool: AsyncConnectionPool) -> None:
    user = uuid4()
    thread = (await store.create(pool, user))["thread_id"]
    results = await asyncio.gather(
        store.append(pool, thread, user, turn(1)), store.append(pool, thread, user, turn(2))
    )
    assert results == ["appended", "appended"]
    loaded = await store.load(pool, thread, user)
    assert loaded is not None
    assert sorted(t["question"] for t in loaded["state"]["turns"]) == ["q1", "q2"]


async def test_turn_cap_rejects_the_next_turn_and_stores_nothing(
    pool: AsyncConnectionPool,
) -> None:
    user = uuid4()
    thread = (await store.create(pool, user))["thread_id"]
    for n in range(store.MAX_TURNS):
        assert await store.append(pool, thread, user, turn(n)) == "appended"
    assert await store.append(pool, thread, user, turn(99)) == "full"
    loaded = await store.load(pool, thread, user)
    assert loaded is not None
    assert len(loaded["state"]["turns"]) == store.MAX_TURNS


async def test_append_sets_updated_at_and_never_moves_expiry(pool: AsyncConnectionPool) -> None:
    user = uuid4()
    thread = (await store.create(pool, user))["thread_id"]
    await expire(pool, thread, "1 hour")
    before = await store.load(pool, thread, user)
    await store.append(pool, thread, user, turn())
    after = await store.load(pool, thread, user)
    assert before and after and after["expires_at"] == before["expires_at"]
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT updated_at > created_at FROM conversations WHERE thread_id = %s", (thread,)
        )
        row = await cur.fetchone()
    assert row == (True,)


async def test_purge_deletes_only_expired_rows(pool: AsyncConnectionPool) -> None:
    await store.purge(pool)
    user = uuid4()
    gone = [(await store.create(pool, user))["thread_id"] for _ in range(2)]
    keep = (await store.create(pool, user))["thread_id"]
    for thread in gone:
        await expire(pool, thread, "-1 second")
    await expire(pool, keep, "1 hour")
    assert await store.purge(pool) == 2
    assert await store.load(pool, keep, user) is not None


async def test_purge_leaves_a_row_expiring_in_one_second(pool: AsyncConnectionPool) -> None:
    user = uuid4()
    thread = (await store.create(pool, user))["thread_id"]
    await expire(pool, thread, "2 seconds")
    await store.purge(pool)
    assert await store.load(pool, thread, user) is not None


async def test_create_purges_expired_rows(pool: AsyncConnectionPool) -> None:
    user = uuid4()
    old = (await store.create(pool, user))["thread_id"]
    await expire(pool, old, "-1 second")
    await store.create(pool, user)
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT count(*) FROM conversations WHERE thread_id = %s", (old,))
        assert await cur.fetchone() == (0,)


async def test_open_pool_purges_expired_rows(pool: AsyncConnectionPool) -> None:
    old = (await store.create(pool, uuid4()))["thread_id"]
    await expire(pool, old, "-1 second")
    assert URL
    second = await store.open_pool(URL)
    try:
        async with second.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM conversations WHERE thread_id = %s", (old,)
            )
            assert await cur.fetchone() == (0,)
    finally:
        await second.close()


async def test_create_expires_in_48_hours(pool: AsyncConnectionPool) -> None:
    created = await store.create(pool, uuid4())
    hours = (created["expires_at"] - created["created_at"]).total_seconds() / 3600
    assert abs(hours - 48) < 0.01
    assert created["title"] == "New Chat"


async def test_populated_response_round_trips_without_a_key(pool: AsyncConnectionPool) -> None:
    user = uuid4()
    thread = (await store.create(pool, user))["thread_id"]
    response = populated_response()
    stored = {
        "question": "q",
        "plan": None,
        "response": response.model_dump(mode="json"),
        "created_at": "t",
    }
    await store.append(pool, thread, user, stored)
    loaded = await store.load(pool, thread, user)
    assert loaded is not None
    back = loaded["state"]["turns"][0]
    assert AskResponse.model_validate(back["response"]) == response
    assert "key=" not in str(loaded["state"])


def test_app_starts_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as client:
        assert app.state.pool is None
        assert client.post("/ask", json={"question": " "}).status_code == 422
        with pytest.raises(store.PersistenceNotConfigured):
            store.require_pool(app)


def test_require_pool_returns_the_app_pool() -> None:
    app = FastAPI()
    app.state.pool = sentinel = object()
    assert store.require_pool(app) is sentinel


async def test_failed_startup_closes_the_pool(
    pool: AsyncConnectionPool, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[AsyncConnectionPool] = []

    class Spy(AsyncConnectionPool):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]
            opened.append(self)

    async def boom(_: AsyncConnectionPool) -> int:
        raise RuntimeError("purge failed")

    monkeypatch.setattr(store, "AsyncConnectionPool", Spy)
    monkeypatch.setattr(store, "purge", boom)
    with pytest.raises(RuntimeError):
        await store.open_pool(URL or "")
    assert len(opened) == 1
    assert opened[0].closed


def test_app_serves_ask_when_the_database_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:x@127.0.0.1:1/postgres")
    monkeypatch.setattr(store, "STARTUP_TIMEOUT", 1.0)
    app = create_app()
    with TestClient(app) as client:
        assert app.state.pool is None
        assert client.post("/ask", json={"question": " "}).status_code == 422
        with pytest.raises(store.PersistenceNotConfigured):
            store.require_pool(app)


async def test_concurrent_startup_does_not_race_on_ddl(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        await conn.execute("DROP TABLE conversations")
    pools = await asyncio.gather(*(store.open_pool(URL or "") for _ in range(8)))
    for opened in pools:
        await opened.close()


async def test_append_treats_a_missing_turns_array_as_empty(pool: AsyncConnectionPool) -> None:
    user = uuid4()
    thread = (await store.create(pool, user))["thread_id"]
    async with pool.connection() as conn:
        await conn.execute("UPDATE conversations SET state = '{}' WHERE thread_id = %s", (thread,))
    assert await store.append(pool, thread, user, turn()) == "appended"
    loaded = await store.load(pool, thread, user)
    assert loaded is not None
    assert [t["question"] for t in loaded["state"]["turns"]] == ["q0"]
