"""FastAPI entrypoint. One question-answering route.

Start with:

    uv run uvicorn src.main:app --reload

Swagger is at /docs. The route is a thin call into `run_ask`; the four-tool
loop lives in `ask.py`.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.ask import run_ask
from src.contract import AskRequest, AskResponse

app = FastAPI(title="census-concierge", version="0.1.0")


@app.post("/ask", response_model=AskResponse, operation_id="ask")
async def post_ask(body: AskRequest) -> AskResponse:
    return await run_ask(body.question)
