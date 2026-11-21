"""Exercise the real Responses SDK and ask loop without live providers."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

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


@pytest.mark.parametrize("failure", ["unavailable", "incomplete"])
@pytest.mark.parametrize("stage", ["initial", "ranked", "built"])
def test_ask_returns_collected_artifacts_after_model_failure(
    monkeypatch: pytest.MonkeyPatch, failure: str, stage: str
) -> None:
    place = "Harris County, Texas"
    question = f"Get ACS total population for {place}."
    fetched: list[str] = []

    def census_get(url: str) -> tuple[int, list[list[str]]]:
        fetched.append(urlsplit(url).path)
        return 200, [
            ["NAME", "B01003_001E", "B01003_001M", "GEO_ID"],
            [place, "120", "3", "0500000US48201"],
        ]

    def ranked_tools(record: ask.ExecutionRecord) -> dict[str, Any]:
        tools = _tools(record)
        search = tools["search_tables"].search
        tools["search_tables"].search = lambda query, k: (
            ["B19013", "B01003"][:k] if query == question else search(query, k)
        )
        tools["fetch_data"].http_get = census_get
        tools["fetch_data"].question_years = lambda: [2014, 2019, 2024]
        return tools

    search = function_call("search_tables", json.dumps({"question": question}))
    geography = function_call("resolve_geography", json.dumps({"query": place, "level": "county"}))
    build = function_call("build_url", '{"table_id":"B01003","vintage":2024}')
    failure_reply = (
        httpx.Response(503, json={"error": {"message": "Provider unavailable"}})
        if failure == "unavailable"
        else {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [search],
        }
    )
    turns = {
        "initial": [],
        "ranked": [[search, geography]],
        "built": [[search, geography], [build]],
    }
    replies = iter(
        [*({"status": "completed", "output": items} for items in turns[stage]), failure_reply]
    )
    requests = install_transport(monkeypatch, lambda _: next(replies))
    monkeypatch.setattr(ask, "default_tools", ranked_tools)

    response = TestClient(app).post("/ask", json={"question": question})

    assert response.status_code == 200
    body = response.json()
    assert tuple(body) == CONTRACT_FIELDS
    assert len([request for request in requests if request["tools"]]) == len(turns[stage]) + 1
    if stage == "built":
        assert body["table_id"] == "B01003"
        assert len(body["urls"]) == 1
        assert "B01003_001E" in body["urls"][0] and "for=county:201" in body["urls"][0]
        assert body["attempted_years"] == [2024]
        assert len(fetched) == 1
        assert body["rows"][0]["GEO_ID"] == "0500000US48201"
        assert body["moe"][0]["B01003_001M"] == "3"
    else:
        assert fetched == body["rows"] == []
        assert not body["table_id"]
        assert body["urls"] == []
    candidates = {item["table_id"] for item in body["alternatives"]}
    assert ("B19013" in candidates) == (stage != "initial")


@pytest.mark.parametrize("failure_stage", ["none", "after-fetch", "before-fetch"])
def test_ask_keeps_calculated_totals_separate_from_geocoded_rows(
    monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    places = ["Detroit city, Michigan", "Phoenix city, Arizona"]
    question = f"What is the total population of {places[0]} and {places[1]} combined?"
    census_rows = {
        "state:26": [places[0], "120", "3", "1600000US2622000"],
        "state:04": [places[1], "80", "4", "1600000US0455000"],
    }
    fetched: list[str] = []

    def census_get(url: str) -> tuple[int, list[list[str]]]:
        state = parse_qs(urlsplit(url).query)["in"][0]
        fetched.append(state)
        return 200, [["NAME", "B01003_001E", "B01003_001M", "GEO_ID"], census_rows[state]]

    def tools(record: ask.ExecutionRecord) -> dict[str, Any]:
        found = _tools(record)
        found["fetch_data"].http_get = census_get
        return found

    turns = [
        [
            function_call("search_tables", json.dumps({"question": question})),
            function_call("resolve_geography", json.dumps({"places": places, "level": "place"})),
        ],
        [function_call("build_url", '{"table_id":"B01003"}')],
    ]
    if failure_stage != "before-fetch":
        turns.append([function_call("fetch_data", '{"years":[2024]}')])
    final = (
        httpx.Response(503, json={"error": {"message": "Provider unavailable"}})
        if failure_stage != "none"
        else {"status": "completed", "output": [message("The fetch completed.")]}
    )
    replies = iter([*({"status": "completed", "output": items} for items in turns), final])
    install_transport(monkeypatch, lambda _: next(replies))
    monkeypatch.setattr(ask, "default_tools", tools)

    response = TestClient(app).post("/ask", json={"question": question})

    assert response.status_code == 200
    body = response.json()
    assert sorted(fetched) == sorted(census_rows)
    assert [row["GEO_ID"] for row in body["rows"]] == [row[-1] for row in census_rows.values()]
    assert [row["B01003_001M"] for row in body["moe"]] == ["3", "4"]
    assert len(body["urls"]) == len(body["legs"]) == 2
    assert {parse_qs(urlsplit(url).query)["in"][0] for url in body["urls"]} == census_rows.keys()
    (total,) = body["combined_rows"]
    assert not total.get("GEO_ID")
    assert (total["B01003_001E"], total["B01003_001M"], total["component_count"]) == (
        "200",
        "5",
        "2",
    )
    assert total["year"] == "2024"
    assert total["NAME"] in body["answer"]


@pytest.mark.parametrize("prior_fetch", ["rows", "failed-fetch", "invalid-arguments"])
async def test_provider_failure_preserves_a_prior_fetch_without_retry(
    monkeypatch: pytest.MonkeyPatch, prior_fetch: str
) -> None:
    place = "Harris County, Texas"
    question = f"Find the ACS total population for {place}."
    fetch_args = None if prior_fetch == "invalid-arguments" else "{}"
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
            {"status": "completed", "output": [function_call("fetch_data", fetch_args)]},
            httpx.Response(503, json={"error": {"message": "Provider unavailable"}}),
        ]
    )
    requests = install_transport(monkeypatch, lambda _: next(replies))
    record = ask.ExecutionRecord()
    tools = _tools(record)
    census_get = tools["fetch_data"].http_get
    fetched: list[str] = []

    def census(url: str) -> tuple[int, Any]:
        fetched.append(urlsplit(url).path)
        return census_get(url) if prior_fetch == "rows" else (503, [])

    tools["fetch_data"].http_get = census
    response = await ask.run_ask(question, tools=tools, record=record)

    assert len([request for request in requests if request["tools"]]) == 4
    assert "The model request failed." in response.answer
    assert len(response.urls) == 1
    if prior_fetch == "invalid-arguments":
        assert fetched == response.legs == response.rows == []
    elif prior_fetch == "rows":
        assert len(fetched) == 1
        assert response.rows[0]["B01003_001E"] == "4838303"
        assert response.moe[0]["B01003_001M"] == "123"
        assert response.geoid == "0500000US48201"
    else:
        assert len(fetched) == 1
        assert response.rows == []
        assert [leg.status_code for leg in response.legs] == [503]


@pytest.mark.parametrize(
    ("dataset", "acs1_status"),
    [("acs5", None), ("acs1", 204), ("acs1", 404)],
    ids=["new-build", "empty-acs1", "missing-acs1"],
)
def test_provider_failure_fetches_only_the_current_accepted_plan(
    monkeypatch: pytest.MonkeyPatch, dataset: str, acs1_status: int | None
) -> None:
    place = "Harris County, Texas"
    question = f"Find the ACS total population for {place}."
    fetched: list[str] = []

    def tools(record: ask.ExecutionRecord) -> dict[str, Any]:
        found = _tools(record)
        success = found["fetch_data"].http_get

        def census(url: str) -> tuple[int, Any]:
            path = urlsplit(url).path
            fetched.append(path)
            if path.endswith("/acs1"):
                assert acs1_status is not None
                return acs1_status, []
            return (503, []) if "/2019/" in path else success(url)

        found["fetch_data"].http_get = census
        return found

    turns = [
        [
            function_call("search_tables", json.dumps({"question": question, "dataset": dataset})),
            function_call(
                "resolve_geography",
                json.dumps({"query": place, "level": "county", "dataset": dataset}),
            ),
        ],
    ]
    if dataset == "acs5":
        previous = function_call("build_url", '{"table_id":"B01003","vintage":2019}')
        previous.update(id="fc_previous_build", call_id="call_previous_build")
        turns.extend([[previous], [function_call("fetch_data")]])
    build = json.dumps({"table_id": "B01003", "dataset": dataset, "vintage": 2024})
    turns.append([function_call("build_url", build)])
    failure = httpx.Response(503, json={"error": {"message": "Provider unavailable"}})
    replies = iter([*({"status": "completed", "output": items} for items in turns), failure])
    install_transport(monkeypatch, lambda _: next(replies))
    monkeypatch.setattr(ask, "default_tools", tools)

    response = TestClient(app).post("/ask", json={"question": question})

    assert response.status_code == 200
    body = response.json()
    assert body["urls"] == [leg["url"] for leg in body["legs"]]
    assert all("key=" not in url for url in body["urls"])
    assert [urlsplit(url).path for url in body["urls"]] == fetched
    assert body["requested_years"] == body["attempted_years"] == body["plan"]["years"] == [2024]
    if dataset == "acs5":
        assert fetched == ["/data/2019/acs/acs5", "/data/2024/acs/acs5"]
        assert [(leg["year"], leg["status_code"]) for leg in body["legs"]] == [
            (2019, 503),
            (2024, 200),
        ]
        assert body["failed_years"] == [] and body["succeeded_years"] == [2024]
        assert body["rows"][0]["GEO_ID"] == "0500000US48201"
    else:
        assert fetched == ["/data/2024/acs/acs1"]
        (leg,) = body["legs"]
        assert leg["status_code"] == acs1_status and body["rows"] == []
        warnings = {warning["code"]: warning["detail"] for warning in body["warnings"]}
        detail = warnings["acs1_geography_ineligible"]
        assert "ACS1 is not published" in detail
        assert "returned instead" not in detail


@pytest.mark.parametrize("later_topic", [None, "empty", "singleton"])
def test_ask_keeps_published_alternatives_for_the_validated_table(
    monkeypatch: pytest.MonkeyPatch, later_topic: str | None
) -> None:
    place = "Harris County, Texas"
    question = f"Get ACS total population for {place}."
    pools = {
        "population": ["B01003", "B02008", "B01001"],
        "empty": [],
        "singleton": ["B01003"],
    }
    titles = {"B01003": "Total Population", "B02008": "Unpublished", "B01001": "Sex by Age"}
    request_tools: dict[str, Any] = {}

    def tools(record: ask.ExecutionRecord) -> dict[str, Any]:
        request_tools.update(_tools(record))
        search = request_tools["search_tables"]
        search.search = lambda topic, k: pools[topic][:k]
        search.describe = lambda table: {"title": titles[table], "universe": "Total population"}
        search.published = lambda _, table: table != "B02008"
        search.select = lambda _, hits: hits[0]["table_id"]
        return request_tools

    search_args = {"question": question, "topic": "population", "k": 2 if later_topic else 1}
    turns = [
        [
            function_call("search_tables", json.dumps(search_args)),
            function_call("resolve_geography", json.dumps({"query": place, "level": "county"})),
        ],
        [function_call("build_url", '{"table_id":"B01003"}')],
        [function_call("fetch_data")],
    ]
    if later_topic:
        turns.append(
            [
                {
                    **function_call("search_tables", json.dumps({"topic": later_topic})),
                    "id": "fc_later_search",
                    "call_id": "call_later_search",
                }
            ]
        )
    final = (
        httpx.Response(503, json={"error": {"message": "Provider unavailable"}})
        if later_topic
        else {"status": "completed", "output": [message("The fetch completed.")]}
    )
    replies = iter([*({"status": "completed", "output": items} for items in turns), final])
    install_transport(monkeypatch, lambda _: next(replies))
    monkeypatch.setattr(ask, "default_tools", tools)

    response = TestClient(app).post("/ask", json={"question": question})

    assert response.status_code == 200
    body = response.json()
    assert body["table_id"] == "B01003"
    assert len(body["urls"]) == len(body["rows"]) == 1
    assert body["rows"][0]["GEO_ID"] == "0500000US48201"
    assert [item["table_id"] for item in body["alternatives"]] == ["B01001"]
    if later_topic:
        assert request_tools["build_url"].allowed_tables() == set(pools[later_topic])


async def test_answer_model_override_does_not_send_sol_reasoning_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = install_transport(monkeypatch, lambda _: pytest.fail("unexpected tool schemas"))
    monkeypatch.setattr(ask, "MODEL", "gpt-4.1")

    await ask._openai_complete([{"role": "user", "content": "Return a fixture value."}], [])

    (request,) = requests
    assert request["model"] == "gpt-4.1"
    assert "reasoning" not in request
