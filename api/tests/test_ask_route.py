"""The POST /ask HTTP surface.

No Census calls and no model: this file proves the route, the validation, and
that a valid body reaches `run_ask`. Tool behaviour is in test_ask_tools and
test_ask_loop.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from src.contract import AskResponse
from src.main import app

client = TestClient(app)

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
    "chart",
    "chart_unavailable",
)
REQUIRED_FIELDS = CONTRACT_FIELDS[:-2]


def test_openapi_documents_post_ask() -> None:
    schema = client.get("/openapi.json").json()
    assert list(schema["paths"]) == ["/ask"]
    post = schema["paths"]["/ask"]["post"]
    assert post["operationId"] == "ask"
    assert post["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AskRequest"
    }
    assert post["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AskResponse"
    }
    request_props = schema["components"]["schemas"]["AskRequest"]["properties"]
    assert list(request_props) == ["question"]
    assert request_props["question"]["minLength"] == 1
    response = schema["components"]["schemas"]["AskResponse"]
    assert response["required"] == list(REQUIRED_FIELDS)
    assert list(response["properties"])[-2:] == ["chart", "chart_unavailable"]
    assert response["properties"]["alternatives"]["items"] == {
        "$ref": "#/components/schemas/Alternative"
    }
    assert response["properties"]["warnings"]["items"] == {
        "$ref": "#/components/schemas/AskWarning"
    }
    assert response["properties"]["urls"]["type"] == "array"
    assert response["properties"]["urls"]["items"]["type"] == "string"
    assert "url" not in response["properties"]
    assert "description" in response["properties"]["urls"]
    assert response["properties"]["legs"]["items"] == {"$ref": "#/components/schemas/RequestLeg"}
    alternative = schema["components"]["schemas"]["Alternative"]
    assert alternative["required"] == ["table_id", "reason"]
    warning = schema["components"]["schemas"]["AskWarning"]
    assert warning["required"] == ["code", "detail"]
    comparison = schema["components"]["schemas"]["Comparison"]
    assert comparison["required"] == [
        "variable",
        "geoid_a",
        "geoid_b",
        "year",
        "estimate_a",
        "estimate_b",
        "moe_a",
        "moe_b",
        "threshold",
        "distinguishable",
        "shared_sample",
    ]
    assert response["properties"]["comparisons"]["items"] == {
        "$ref": "#/components/schemas/Comparison"
    }
    leg = schema["components"]["schemas"]["RequestLeg"]
    assert leg["required"] == ["year", "url", "ok", "status_code", "detail"]
    assert "for_spec" in leg["properties"]
    chart = schema["components"]["schemas"]["ChartSpec"]
    assert chart.get("additionalProperties") is False
    assert set(chart["properties"]) == {"type", "x", "y", "series_by", "title", "show_moe"}
    assert "vega" not in chart["properties"]
    assert "svg" not in chart["properties"]
    assert chart["properties"]["type"]["enum"] == ["line", "bar"]
    assert chart["properties"]["x"]["enum"] == ["year", "geography"]
    assert chart["properties"]["y"]["const"] == "estimate"
    assert chart["properties"]["show_moe"]["const"] is True
    assert response["properties"]["chart"]["anyOf"] == [
        {"$ref": "#/components/schemas/ChartSpec"},
        {"type": "null"},
    ]


def test_empty_question_is_a_validation_error() -> None:
    response = client.post("/ask", json={"question": ""})
    assert response.status_code == 422


def test_blank_question_is_a_validation_error() -> None:
    response = client.post("/ask", json={"question": "   "})
    assert response.status_code == 422


def test_missing_question_is_a_validation_error() -> None:
    response = client.post("/ask", json={})
    assert response.status_code == 422


EMPTY_CONTRACT = {
    "answer": "",
    "urls": [],
    "requested_years": [],
    "attempted_years": [],
    "succeeded_years": [],
    "failed_years": [],
    "omitted_years": [],
    "omission_reasons": [],
    "legs": [],
    "rows": [],
    "moe": [],
    "geoid": "",
    "universe": "",
    "table_id": "",
    "alternatives": [],
    "comparisons": [],
    "warnings": [],
    "chart": None,
    "chart_unavailable": False,
}


def test_a_valid_question_returns_the_declared_contract(monkeypatch: Any) -> None:
    # CI has no index and no keys. The assembler is tested in test_ask_loop;
    # this only proves the route still returns every contract field.
    async def fake_loop(question: str) -> AskResponse:
        _ = question
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = client.post("/ask", json={"question": "population of Harris County"})
    assert response.status_code == 200
    assert response.json() == EMPTY_CONTRACT


def test_valid_question_reaches_the_ask_loop(monkeypatch: Any) -> None:
    seen: list[str] = []

    async def fake_loop(question: str) -> AskResponse:
        seen.append(question)
        return AskResponse(
            answer="from-loop",
            urls=[],
            requested_years=[],
            attempted_years=[],
            succeeded_years=[],
            failed_years=[],
            omitted_years=[],
            omission_reasons=[],
            legs=[],
            rows=[],
            moe=[],
            geoid="",
            universe="",
            table_id="",
            alternatives=[],
            comparisons=[],
            warnings=[],
        )

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = client.post("/ask", json={"question": "  population of Harris County  "})
    assert response.status_code == 200
    assert seen == ["population of Harris County"]
    assert response.json()["answer"] == "from-loop"


def test_ask_is_the_only_question_route() -> None:
    schema = client.get("/openapi.json").json()
    assert list(schema["paths"]) == ["/ask"]
    assert list(schema["paths"]["/ask"]) == ["post"]
