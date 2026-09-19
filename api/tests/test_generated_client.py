"""The committed OpenAPI snapshot is the TypeScript client's source of truth.

A handwritten AskResponse in the web app is how the contract drifts. The
snapshot is the Python half of the CI drift gate; `generate_client.py --check`
also regenerates schema.d.ts.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.main import app

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "packages" / "client"
ASK_TS = ROOT / "web" / "src" / "ask.ts"

CONTRACT_FIELDS = (
    "answer",
    "urls",
    "requested_years",
    "attempted_years",
    "succeeded_years",
    "failed_years",
    "omitted_years",
    "omission_reasons",
    "legs",
    "rows",
    "moe",
    "geoid",
    "universe",
    "table_id",
    "alternatives",
    "comparisons",
    "warnings",
)


def test_committed_openapi_matches_the_live_app() -> None:
    live = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    committed = (CLIENT / "openapi.json").read_text(encoding="utf-8")
    assert committed == live, (
        "packages/client/openapi.json is stale. "
        "Regenerate with: uv run python scripts/generate_client.py"
    )


def test_generated_schema_declares_every_contract_field() -> None:
    text = (CLIENT / "schema.d.ts").read_text(encoding="utf-8")
    start = text.index("AskResponse:")
    end = text.index("AskWarning:", start)
    body = text[start:end]
    for field in CONTRACT_FIELDS:
        assert f"{field}:" in body, field


def test_ask_ts_consumes_generated_types() -> None:
    text = ASK_TS.read_text(encoding="utf-8")
    assert "packages/client/schema" in text
    assert "export type AskResponse = {" not in text
