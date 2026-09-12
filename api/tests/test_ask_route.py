"""The POST /ask HTTP surface.

No Census calls and no model: this file proves the route, the validation, and
that a valid body reaches `run_ask`. The loop's tools are a later story.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from src.contract import AskResponse
from src.main import app

client = TestClient(app)

CONTRACT_FIELDS = (
    "answer",
    "url",
    "rows",
    "moe",
    "geoid",
    "universe",
    "table_id",
    "alternatives",
    "warnings",
)


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
    assert response["required"] == list(CONTRACT_FIELDS)
    assert "items" in response["properties"]["alternatives"]
    assert "items" in response["properties"]["warnings"]
    assert response["properties"]["url"]["type"] == "string"


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
    "url": "",
    "rows": [],
    "moe": [],
    "geoid": "",
    "universe": "",
    "table_id": "",
    "alternatives": [],
    "warnings": [],
}


def test_a_valid_question_returns_the_declared_contract() -> None:
    # No mock: a stub that drops url/moe/geoid/universe would still pass the
    # monkeypatched loop test below, which only checks answer.
    response = client.post("/ask", json={"question": "population of Harris County"})
    assert response.status_code == 200
    assert response.json() == EMPTY_CONTRACT


def test_valid_question_reaches_the_ask_loop(monkeypatch: Any) -> None:
    seen: list[str] = []

    async def fake_loop(question: str) -> AskResponse:
        seen.append(question)
        return AskResponse(
            answer="from-loop",
            url="",
            rows=[],
            moe=[],
            geoid="",
            universe="",
            table_id="",
            alternatives=[],
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
