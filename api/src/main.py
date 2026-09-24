"""FastAPI entrypoint. One question-answering route plus the built UI.

Start with:

    uv run uvicorn src.main:app --reload

Swagger is at /docs. The route is a thin call into `run_ask`; the four-tool
loop lives in `ask.py`. When `web/dist` exists, GET / serves it from this
process. There is no CORS middleware: the UI and POST /ask share the origin.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from src.ask import run_ask
from src.contract import AskRequest, AskResponse, reject_unknown_override

WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def create_app(dist: Path | None = None) -> FastAPI:
    application = FastAPI(title="census-concierge", version="0.1.0")

    @application.post("/ask", response_model=AskResponse, operation_id="ask")
    async def post_ask(body: AskRequest) -> AskResponse:
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

    root = WEB_DIST if dist is None else dist
    if root.is_dir():
        application.mount("/", StaticFiles(directory=root, html=True), name="frontend")
    return application


app = create_app()
