"""Exercise the real Responses SDK and ask loop without live providers."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from ask_fixtures import _tools
from fastapi.testclient import TestClient
from langchain_core.tools import StructuredTool
from openai import AsyncOpenAI
from src import ask
from src.main import app
from test_ask_route import CONTRACT_FIELDS


def function_call(name: str, arguments: str | None = "{}") -> dict[str, Any]:
    return {
        "type": "function_call",
        "status": "completed",
        "id": f"fc_{name}",
        "call_id": f"call_{name}",
        "name": name,
        "arguments": arguments,
    }


def message(text: str) -> dict[str, Any]:
    return {
        "type": "message",
        "id": "msg_fixture",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    reply: Callable[[dict[str, Any]], dict[str, Any] | httpx.Response],
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/responses"
        payload = json.loads(request.content)
        requests.append(payload)
        result = {"id": "resp_fixture", "object": "response", "model": "gpt-6.2-sol"}
        if payload["tools"]:
            turn = reply(payload)
            if isinstance(turn, httpx.Response):
                return turn
            result.update(turn)
        else:
            result.update(status="completed", output=[message('{"asks_for":"data"}')])
        return httpx.Response(200, json=result)

    def client(**kwargs: Any) -> AsyncOpenAI:
        assert kwargs == {"timeout": 60.0, "max_retries": 0}
        transport = httpx.MockTransport(respond)
        return AsyncOpenAI(http_client=httpx.AsyncClient(transport=transport), **kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "mock-openai-key")
    monkeypatch.setattr(ask, "AsyncOpenAI", client)
    return requests


def test_ask_replays_parallel_calls_with_exact_model_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    place = "Harris County, Texas"
    question = f"Find the ACS total population for {place}."
    reasoning = {
        "type": "reasoning",
        "id": "rs_fixture",
        "summary": [],
        "encrypted_content": "opaque-encrypted-reasoning-fixture",
    }
    search = function_call("search_tables", json.dumps({"question": question}))
    geography = function_call("resolve_geography", json.dumps({"query": place, "level": "county"}))
    replies = iter(
        [
            [reasoning, search, geography],
            [function_call("build_url", '{"table_id":"B01003"}')],
            [function_call("fetch_data")],
            [message("The Census returned population data.")],
        ]
    )
    requests = install_transport(
        monkeypatch, lambda _: {"status": "completed", "output": next(replies)}
    )
    monkeypatch.setattr(ask, "default_tools", _tools)

    response = TestClient(app).post("/ask", json={"question": question})

    assert response.status_code == 200
    body = response.json()
    assert tuple(body) == CONTRACT_FIELDS
    assert body["table_id"] == "B01003"
    assert body["rows"][0]["B01003_001E"] == "4838303"
    assert body["moe"][0]["B01003_001M"] == "123"
    assert body["geoid"] == "0500000US48201"
    assert body["universe"] == "Total population"
    assert "for=county:201" in body["urls"][0]
    assert "key=" not in body["urls"][0]

    settings = {
        "model": "gpt-6.2-sol",
        "reasoning": {"effort": "low"},
        "max_output_tokens": 4096,
        "service_tier": "default",
        "store": False,
        "parallel_tool_calls": True,
    }
    assert all({key: request[key] for key in settings} == settings for request in requests)
    main_turns = [request for request in requests if request["tools"]]
    assert len(main_turns) == 4
    assert len(requests) == 5
    assert {tool["name"] for tool in main_turns[0]["tools"]} == {
        "search_tables",
        "resolve_geography",
        "build_url",
        "fetch_data",
    }
    assert all(
        tool["type"] == "function" and tool["strict"] is False and "parameters" in tool
        for tool in main_turns[0]["tools"]
    )
    assert all("previous_response_id" not in request for request in requests)
    continuation = main_turns[1]["input"]
    assert continuation[:2] == main_turns[0]["input"]
    assert continuation[2:5] == [reasoning, search, geography]
    assert [item["type"] for item in continuation[5:]] == ["function_call_output"] * 2
    assert [item["call_id"] for item in continuation[5:]] == [
        search["call_id"],
        geography["call_id"],
    ]
    assert "B01003" in continuation[5]["output"]
    assert "county:201 state:48" in continuation[6]["output"]
    assert main_turns[3]["input"][: len(continuation)] == continuation
    assert main_turns[3]["input"][-1]["call_id"] == "call_fetch_data"


@pytest.mark.parametrize("arguments", [None, "{", '[["value","incorrectly accepted"]]'])
async def test_malformed_function_arguments_use_the_existing_tool_validation(
    monkeypatch: pytest.MonkeyPatch, arguments: str | None
) -> None:
    calls = 0

    async def lookup(value: str = "default") -> str:
        nonlocal calls
        calls += 1
        return value

    tool = StructuredTool.from_function(coroutine=lookup, description="Look up a fixture value")
    bad = function_call("lookup", arguments)
    good = {
        **function_call("lookup", '{"value":"blue"}'),
        "id": "fc_retry",
        "call_id": "call_retry",
    }
    replies = iter([[bad], [good], [message("Found the fixture.")]])
    requests = install_transport(
        monkeypatch, lambda _: {"status": "completed", "output": next(replies)}
    )

    response = await ask.run_ask("Look up a fixture value.", tools={tool.name: tool})

    assert response.answer == "Found the fixture."
    assert calls == 1
    first, second, third = [request["input"] for request in requests if request["tools"]]
    assert second[: len(first)] == first
    assert second[-2] == {**bad, "arguments": "{}"}
    assert second[-1]["call_id"] == bad["call_id"]
    assert second[-1]["output"] == "lookup failed: Tool arguments must be a JSON object."
    assert third[-1] == {"type": "function_call_output", "call_id": "call_retry", "output": "blue"}


async def test_incomplete_response_does_not_execute_a_partial_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def lookup() -> str:
        pytest.fail("An incomplete response must not dispatch its function call")

    tool = StructuredTool.from_function(coroutine=lookup, description="Look up a fixture value")
    requests = install_transport(
        monkeypatch,
        lambda _: {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{**function_call("lookup"), "status": "incomplete"}],
        },
    )

    response = await ask.run_ask("Look up a fixture value.", tools={tool.name: tool})

    assert len([request for request in requests if request["tools"]]) == 1
    assert response.answer == "The model did not complete its response."
    assert response.urls == []
    assert response.rows == []


async def test_provider_failure_keeps_fetched_data_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    place = "Harris County, Texas"
    question = f"Find the ACS total population for {place}."
    replies = iter(
        [
            {
                "status": "completed",
                "output": [
                    function_call("search_tables", json.dumps({"question": question})),
                    function_call(
                        "resolve_geography", json.dumps({"query": place, "level": "county"})
                    ),
                ],
            },
            {
                "status": "completed",
                "output": [function_call("build_url", '{"table_id":"B01003"}')],
            },
            {"status": "completed", "output": [function_call("fetch_data")]},
            httpx.Response(503, json={"error": {"message": "Provider unavailable"}}),
        ]
    )
    requests = install_transport(monkeypatch, lambda _: next(replies))
    record = ask.ExecutionRecord()

    response = await ask.run_ask(question, tools=_tools(record), record=record)

    assert len([request for request in requests if request["tools"]]) == 4
    assert "The model request failed." in response.answer
    assert response.urls
    assert response.rows[0]["B01003_001E"] == "4838303"
    assert response.moe[0]["B01003_001M"] == "123"
    assert response.geoid == "0500000US48201"


async def test_answer_model_override_does_not_send_sol_reasoning_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = install_transport(monkeypatch, lambda _: pytest.fail("unexpected tool schemas"))
    monkeypatch.setattr(ask, "MODEL", "gpt-4.1")

    await ask._openai_complete([{"role": "user", "content": "Return a fixture value."}], [])

    (request,) = requests
    assert request["model"] == "gpt-4.1"
    assert "reasoning" not in request
