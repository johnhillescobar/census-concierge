"""The POST /ask HTTP surface.

No Census calls and no model: this file proves the route, the validation, and
that a valid body reaches `run_ask`. Tool behaviour is in test_ask_tools and
test_ask_loop.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from src.contract import AskResponse, ResultPlan
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
    "plan",
    "chart",
    "chart_unavailable",
)
REQUIRED_FIELDS = CONTRACT_FIELDS[:-2]


def test_openapi_documents_post_ask() -> None:
    schema = client.get("/openapi.json").json()
    assert list(schema["paths"]) == [
        "/ask",
        "/conversations",
        "/conversations/{thread_id}/turns",
        "/conversations/{thread_id}",
    ]
    post = schema["paths"]["/ask"]["post"]
    assert post["operationId"] == "ask"
    assert post["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AskRequest"
    }
    assert post["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AskResponse"
    }
    request_props = schema["components"]["schemas"]["AskRequest"]["properties"]
    assert list(request_props) == ["question", "plan"]
    assert request_props["question"]["minLength"] == 1
    assert "plan" in request_props
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
    assert alternative["required"] == ["table_id", "title", "universe", "reason"]
    plan = schema["components"]["schemas"]["ResultPlan"]
    assert set(plan["properties"]) == {
        "table_id",
        "variables",
        "dataset",
        "years",
        "requested_years",
        "geographies",
        "allow_overlapping_acs5",
    }
    assert response["properties"]["plan"]["$ref"] == "#/components/schemas/ResultPlan"
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


EMPTY_PLAN = {
    "table_id": "",
    "variables": [],
    "dataset": "acs5",
    "years": [],
    "requested_years": [],
    "geographies": [],
    "allow_overlapping_acs5": False,
}

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
    "plan": EMPTY_PLAN,
    "chart": None,
    "chart_unavailable": False,
}


def test_a_valid_question_returns_the_declared_contract(monkeypatch: Any) -> None:
    # CI has no index and no keys. The assembler is tested in test_ask_loop;
    # this only proves the route still returns every contract field.
    async def fake_loop(question: str, **_: Any) -> AskResponse:
        _ = question
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = client.post("/ask", json={"question": "population of Harris County"})
    assert response.status_code == 200
    assert response.json() == EMPTY_CONTRACT


def test_valid_question_reaches_the_ask_loop(monkeypatch: Any) -> None:
    seen: list[str] = []

    async def fake_loop(question: str, **_: Any) -> AskResponse:
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
            plan=ResultPlan(),
        )

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = client.post("/ask", json={"question": "  population of Harris County  "})
    assert response.status_code == 200
    assert seen == ["population of Harris County"]
    assert response.json()["answer"] == "from-loop"


def test_question_only_clients_omit_plan(monkeypatch: Any) -> None:
    seen: list[object] = []

    async def fake_loop(question: str, override: object = None) -> AskResponse:
        seen.append((question, override))
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = client.post("/ask", json={"question": "population of Harris County"})
    assert response.status_code == 200
    assert seen == [("population of Harris County", None)]


def test_geography_override_without_geoid_is_rejected_before_ask(monkeypatch: Any) -> None:
    called: list[str] = []

    async def fake_loop(question: str, override: object = None) -> AskResponse:
        called.append(question)
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = client.post(
        "/ask",
        json={
            "question": "population of Harris County",
            "plan": {
                "geographies": [
                    {"level": "county", "for_spec": "county:201", "in_spec": "state:48"}
                ]
            },
        },
    )
    assert response.status_code == 422
    assert called == []
    assert "GEOID" in response.text


def test_nonnumeric_geoid_override_is_rejected_before_ask(monkeypatch: Any) -> None:
    called: list[str] = []

    async def fake_loop(question: str, override: object = None) -> AskResponse:
        called.append(question)
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = client.post(
        "/ask",
        json={
            "question": "population of Harris County",
            "plan": {"geographies": [{"geoid": "0500000USABCDE"}]},
        },
    )
    assert response.status_code == 422
    assert called == []
    assert "GEOID" in response.text


def test_acs1_zcta_override_is_rejected_before_ask(monkeypatch: Any) -> None:
    called: list[str] = []

    async def fake_loop(question: str, override: object = None) -> AskResponse:
        called.append(question)
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = client.post(
        "/ask",
        json={
            "question": "population of ZIP 90210",
            "plan": {
                "dataset": "acs1",
                "geographies": [
                    {
                        "geoid": "860Z200US90210",
                        "level": "zip code tabulation area",
                    }
                ],
            },
        },
    )
    assert response.status_code == 422
    assert called == []


def test_unknown_table_override_is_rejected_before_ask(monkeypatch: Any) -> None:
    called: list[str] = []

    async def fake_loop(question: str, override: object = None) -> AskResponse:
        called.append(question)
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    monkeypatch.setattr(
        "src.retrieval.availability.load",
        lambda: {"datasets": {"acs5": {"2024": {"B19013": {"variables": ["001E"]}}}}},
    )
    response = client.post(
        "/ask",
        json={"question": "median household income", "plan": {"table_id": "NOPE", "years": [2024]}},
    )
    assert response.status_code == 422
    assert called == []
    assert "table_id" in response.text


def test_unknown_variable_override_is_rejected_before_ask(monkeypatch: Any) -> None:
    called: list[str] = []

    async def fake_loop(question: str, override: object = None) -> AskResponse:
        called.append(question)
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    monkeypatch.setattr(
        "src.retrieval.availability.load",
        lambda: {"datasets": {"acs5": {"2024": {"B19013": {"variables": ["001E"]}}}}},
    )
    response = client.post(
        "/ask",
        json={
            "question": "median household income",
            "plan": {"table_id": "B19013", "variables": ["B19013_999E"], "years": [2024]},
        },
    )
    assert response.status_code == 422
    assert called == []


def test_acs1_table_override_uses_that_dataset_latest_vintage(monkeypatch: Any) -> None:
    called: list[str] = []

    async def fake_loop(question: str, override: object = None) -> AskResponse:
        called.append(question)
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    monkeypatch.setattr(
        "src.retrieval.availability.load",
        lambda: {
            "datasets": {
                "acs5": {"2024": {"B01003": {"variables": ["001E"]}}},
                "acs1": {"2023": {"B01003": {"variables": ["001E"]}}},
            }
        },
    )
    response = client.post(
        "/ask",
        json={
            "question": "1-year ACS population",
            "plan": {"table_id": "B01003", "dataset": "acs1"},
        },
    )
    assert response.status_code == 200
    assert called == ["1-year ACS population"]


def test_typed_plan_override_reaches_the_ask_loop(monkeypatch: Any) -> None:
    seen: list[object] = []

    async def fake_loop(question: str, override: object = None) -> AskResponse:
        seen.append(override)
        return AskResponse(**EMPTY_CONTRACT)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = client.post(
        "/ask",
        json={
            "question": "population of Harris County",
            "plan": {
                "table_id": "B19013",
                "geographies": [{"geoid": "0500000US48201"}],
                "allow_overlapping_acs5": True,
            },
        },
    )
    assert response.status_code == 200
    plan = seen[0]
    assert plan is not None
    assert plan.table_id == "B19013"
    assert plan.geographies[0].for_spec == "county:201"
    assert plan.geographies[0].in_spec == "state:48"
    assert plan.allow_overlapping_acs5 is True


def test_ask_is_the_only_question_route() -> None:
    schema = client.get("/openapi.json").json()
    assert list(schema["paths"]) == [
        "/ask",
        "/conversations",
        "/conversations/{thread_id}/turns",
        "/conversations/{thread_id}",
    ]
    assert list(schema["paths"]["/ask"]) == ["post"]
