"""FastAPI entrypoint. One question-answering route plus the built UI.

Start with:

    uv run uvicorn src.main:app --reload

Swagger is at /docs. The route is a thin call into `run_ask`; the four-tool
loop lives in `ask.py`. When `web/dist` exists, GET / serves it from this
process. There is no CORS middleware: the UI and POST /ask share the origin.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from psycopg_pool import AsyncConnectionPool

from src.ask import run_ask
from src.contract import AskRequest, AskResponse, reject_unknown_override
from src.store import (
    MAX_TURNS,
    Conversation,
    ConversationInfo,
    PersistenceNotConfigured,
    Turn,
    append,
    create,
    load,
    open_pool,
    require_pool,
)

log = logging.getLogger(__name__)
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def not_found() -> HTTPException:
    return HTTPException(404, "conversation not found")


User = Annotated[UUID, Header(alias="x-user-id")]


def pool_of(request: Request, _user: User) -> AsyncConnectionPool:  # header 422 before 503
    try:
        return require_pool(request.app)
    except PersistenceNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc


Pool = Annotated[AsyncConnectionPool, Depends(pool_of)]


async def answer(body: AskRequest) -> AskResponse:
    field = reject_unknown_override(body.plan)
    if field:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "plan", field),
                    "msg": f"Value error, invalid {field} override",
                    "input": getattr(body.plan, field),
                }
            ]
        )
    return await run_ask(body.question, override=body.plan)


def create_app(dist: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        url = os.environ.get("DATABASE_URL")
        app.state.pool = None
        if url:
            try:
                app.state.pool = await open_pool(url)
            except Exception as exc:  # /ask must survive a bad or unreachable database
                log.error("persistence unavailable at startup: %s", type(exc).__name__)
        try:
            yield
        finally:
            if app.state.pool is not None:
                await app.state.pool.close()

    application = FastAPI(title="census-concierge", version="0.1.0", lifespan=lifespan)

    @application.post("/ask", response_model=AskResponse, operation_id="ask")
    async def post_ask(body: AskRequest) -> AskResponse:
        return await answer(body)

    @application.post(
        "/conversations",
        status_code=201,
        response_model=ConversationInfo,
        operation_id="create_conversation",
    )
    async def post_conversation(user: User, pool: Pool) -> dict[str, Any]:
        return await create(pool, user)

    @application.post(
        "/conversations/{thread_id}/turns", response_model=AskResponse, operation_id="append_turn"
    )
    async def post_turn(thread_id: UUID, body: AskRequest, user: User, pool: Pool) -> AskResponse:
        found = await load(pool, thread_id, user)  # before run_ask: no model spend on a bad thread
        if found is None:
            raise not_found()
        if len(found["state"]["turns"]) >= MAX_TURNS:
            raise HTTPException(409, "conversation full")
        response = await answer(body)
        turn = Turn(
            question=body.question, plan=body.plan, response=response, created_at=datetime.now(UTC)
        )
        status = await append(pool, thread_id, user, turn.model_dump(mode="json"))
        if status != "appended":  # lost a race with expiry or another append
            raise not_found() if status is None else HTTPException(409, "conversation full")
        return response

    @application.get(
        "/conversations/{thread_id}", response_model=Conversation, operation_id="get_conversation"
    )
    async def get_conversation(thread_id: UUID, user: User, pool: Pool) -> dict[str, Any]:
        found = await load(pool, thread_id, user)
        if found is None:
            raise not_found()
        return {**found, "turns": found["state"]["turns"]}

    root = WEB_DIST if dist is None else dist
    if root.is_dir():
        application.mount("/", StaticFiles(directory=root, html=True), name="frontend")
    return application


app = create_app()
