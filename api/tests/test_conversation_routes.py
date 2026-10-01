"""The three conversation routes over a real Postgres, with a counting fake for `run_ask`.

The fake is the point of several tests: ownership, expiry and fullness must be
decided before any model spend, so the assertion is zero calls.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from ask_fixtures import populated_response
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from src import main, store
from src.contract import AskResponse
from src.main import create_app
from test_store import expire

NOT_FOUND = {"detail": "conversation not found"}
BODY = {"question": "poverty in Detroit"}


class FakeAsk:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail = False

    async def __call__(self, question: str, **_: Any) -> AskResponse:
        self.calls.append(question)
        if self.fail:
            raise RuntimeError("model down")
        return populated_response()


class Harness:
    def __init__(self, client: httpx.AsyncClient, pool: AsyncConnectionPool, ask: FakeAsk) -> None:
        self.client, self.pool, self.ask = client, pool, ask

    async def new(self, user: UUID) -> str:
        r = await self.client.post("/conversations", headers=hdr(user))
        assert r.status_code == 201
        return str(r.json()["thread_id"])

    async def get(self, thread: str, user: UUID) -> httpx.Response:
        return await self.client.get(f"/conversations/{thread}", headers=hdr(user))

    async def turn(
        self, thread: str, user: UUID, body: dict[str, Any] | None = None
    ) -> httpx.Response:
        return await self.client.post(
            f"/conversations/{thread}/turns", json=body or BODY, headers=hdr(user)
        )


def hdr(user: UUID) -> dict[str, str]:
    return {"x-user-id": str(user)}


async def row_exists(pool: Any, thread: UUID) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT 1 FROM conversations WHERE thread_id = %s", (thread,))
        return await cur.fetchone() is not None


async def column(pool: Any, thread: UUID, name: str) -> Any:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {name} FROM conversations WHERE thread_id = %s", (thread,)
        )
        row = await cur.fetchone()
        assert row is not None
        return row[0]


def stored(n: int) -> dict[str, Any]:
    return {
        "question": f"q{n}",
        "plan": None,
        "response": populated_response().model_dump(mode="json"),
        "created_at": "2026-10-01T00:00:00Z",
    }


def client_for(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def h(pool: AsyncConnectionPool, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Harness]:
    ask = FakeAsk()
    monkeypatch.setattr(main, "run_ask", ask)
    app = create_app()
    app.state.pool = pool  # lifespan is not run; the store tests cover opening the pool
    async with client_for(app) as client:
        yield Harness(client, pool, ask)


ROUTES = [
    ("post", "/conversations"),
    ("post", f"/conversations/{uuid4()}/turns"),
    ("get", f"/conversations/{uuid4()}"),
]


async def send(
    client: httpx.AsyncClient, method: str, path: str, headers: dict[str, str]
) -> httpx.Response:
    return await client.request(
        method, path, headers=headers, json=BODY if "turns" in path else None
    )


@pytest.mark.parametrize("bad", [None, "not-a-uuid"])
@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_user_header_is_required_and_must_be_a_uuid(
    h: Harness, method: str, path: str, bad: str | None
) -> None:
    r = await send(h.client, method, path, {} if bad is None else {"x-user-id": bad})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["header", "x-user-id"]
    assert h.ask.calls == []


async def test_create_returns_a_48_hour_thread_and_purges_expired_rows(h: Harness) -> None:
    user = uuid4()
    stale = await h.new(user)
    await expire(h.pool, UUID(stale), "-1 second")
    r = await h.client.post("/conversations", headers=hdr(user))
    body = r.json()
    assert r.status_code == 201
    assert set(body) == {"thread_id", "title", "created_at", "expires_at"}
    assert body["title"] == "New Chat"
    lifetime = datetime.fromisoformat(body["expires_at"]) - datetime.fromisoformat(
        body["created_at"]
    )
    assert abs(lifetime - timedelta(hours=48)) < timedelta(seconds=1)
    assert await row_exists(h.pool, UUID(stale)) is False


async def test_turn_equals_ask_and_is_stored(h: Harness) -> None:
    user = uuid4()
    thread = await h.new(user)
    asked = (await h.client.post("/ask", json=BODY)).json()
    r = await h.turn(thread, user)
    assert r.status_code == 200
    assert r.json() == asked
    turns = (await h.get(thread, user)).json()["turns"]
    assert [t["question"] for t in turns] == [BODY["question"]]
    assert turns[0]["response"] == asked
    assert turns[0]["plan"] is None


async def foreign(h: Harness) -> tuple[str, UUID]:
    return await h.new(uuid4()), uuid4()


async def missing(h: Harness) -> tuple[str, UUID]:
    return str(uuid4()), uuid4()


async def expired(h: Harness) -> tuple[str, UUID]:
    user = uuid4()
    thread = await h.new(user)
    await expire(h.pool, UUID(thread), "-1 second")
    return thread, user


@pytest.mark.parametrize("make", [foreign, missing, expired])
async def test_unreachable_thread_is_the_same_404_and_never_reaches_the_model(
    h: Harness, make: Any
) -> None:
    thread, user = await make(h)
    for r in (await h.turn(thread, user), await h.get(thread, user)):
        assert r.status_code == 404
        assert r.json() == NOT_FOUND
    assert h.ask.calls == []


async def test_full_thread_is_409_and_never_reaches_the_model(h: Harness) -> None:
    user = uuid4()
    thread = await h.new(user)
    for n in range(store.MAX_TURNS):
        assert await store.append(h.pool, UUID(thread), user, stored(n)) == "appended"
    r = await h.turn(thread, user)
    assert r.status_code == 409
    assert r.json() == {"detail": "conversation full"}
    assert h.ask.calls == []
    assert len((await h.get(thread, user)).json()["turns"]) == store.MAX_TURNS


async def test_invalid_override_is_the_ask_422_and_stores_nothing(h: Harness) -> None:
    user = uuid4()
    thread = await h.new(user)
    body = {**BODY, "plan": {"table_id": "B99999", "years": [2023], "requested_years": [2023]}}
    via_ask = await h.client.post("/ask", json=body)
    r = await h.turn(thread, user, body)
    assert r.status_code == via_ask.status_code == 422
    assert r.json() == via_ask.json()
    assert h.ask.calls == []
    assert (await h.get(thread, user)).json()["turns"] == []


async def test_failed_run_ask_is_500_and_stores_nothing(h: Harness) -> None:
    user = uuid4()
    thread = await h.new(user)
    h.ask.fail = True
    assert (await h.turn(thread, user)).status_code == 500
    assert (await h.get(thread, user)).json()["turns"] == []


async def test_turns_keep_append_order_and_never_move_expiry(h: Harness) -> None:
    user = uuid4()
    thread = await h.new(user)
    expires = await column(h.pool, UUID(thread), "expires_at")
    await h.turn(thread, user, {"question": "first"})
    await h.turn(thread, user, {"question": "second"})
    body = (await h.get(thread, user)).json()
    assert set(body) == {"thread_id", "title", "created_at", "expires_at", "turns"}
    assert [t["question"] for t in body["turns"]] == ["first", "second"]
    assert set(body["turns"][0]) == {"question", "plan", "response", "created_at"}
    assert await column(h.pool, UUID(thread), "expires_at") == expires


async def test_get_leaves_updated_at_unchanged(h: Harness) -> None:
    user = uuid4()
    thread = await h.new(user)
    await h.turn(thread, user)
    before = await column(h.pool, UUID(thread), "updated_at")
    assert (await h.get(thread, user)).status_code == 200
    assert await column(h.pool, UUID(thread), "updated_at") == before


async def test_user_id_never_appears_in_a_body_or_a_log(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    user, stranger = uuid4(), uuid4()
    thread = await h.new(user)
    texts = [
        (await h.get(thread, user)).text,
        (await h.turn(thread, user)).text,
        (await h.get(thread, stranger)).text,
        (await h.turn(thread, stranger)).text,
    ]
    h.ask.fail = True
    texts.append((await h.turn(thread, user)).text)
    for u in (user, stranger):
        assert not any(str(u) in t for t in texts)
        assert str(u) not in caplog.text


async def test_without_a_database_the_routes_are_503_and_ask_still_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ask = FakeAsk()
    monkeypatch.setattr(main, "run_ask", ask)
    app = create_app()
    app.state.pool = None  # what the lifespan leaves when DATABASE_URL is unset
    async with client_for(app) as client:
        for method, path in ROUTES:
            assert (await send(client, method, path, hdr(uuid4()))).status_code == 503
        assert (await client.post("/ask", json=BODY)).status_code == 200
    assert ask.calls == [BODY["question"]]


async def test_a_bad_header_is_422_even_when_there_is_no_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "run_ask", FakeAsk())
    app = create_app()
    app.state.pool = None
    async with client_for(app) as client:
        for method, path in ROUTES:
            r = await send(client, method, path, {"x-user-id": "not-a-uuid"})
            assert r.status_code == 422


@pytest.mark.parametrize(("lost", "status"), [(None, 404), ("full", 409)])
async def test_losing_a_race_after_run_ask_maps_to_the_same_errors(
    h: Harness, monkeypatch: pytest.MonkeyPatch, lost: str | None, status: int
) -> None:
    user = uuid4()
    thread = await h.new(user)

    async def lose(*_: Any) -> str | None:
        return lost

    monkeypatch.setattr(main, "append", lose)
    r = await h.turn(thread, user)
    assert r.status_code == status
    assert h.ask.calls == [BODY["question"]]  # the spend happened; nothing was stored
    assert (await h.get(thread, user)).json()["turns"] == []
