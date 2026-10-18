"""scripts/ask_one.py: the one-question debugging runner traces a loop without live keys."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from ask_fixtures import _tools
from langchain_core.tools import BaseTool
from src.ask import ExecutionRecord

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import ask_one  # noqa: E402

QUESTION = "population of Harris County, Texas"


def _queue() -> list[dict[str, Any]]:
    def call(id_: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"content": "", "tool_calls": [{"id": id_, "name": name, "args": args}]}

    return [
        call("1", "search_tables", {"question": QUESTION}),
        call("2", "resolve_geography", {"query": "Harris County, Texas"}),
        call("3", "build_url", {"table_id": "B01003"}),
        call("4", "fetch_data", {}),
        {"content": "Harris County has data.", "tool_calls": []},
    ]


async def _run() -> tuple[Any, str]:
    record = ExecutionRecord()
    queue = _queue()

    async def complete(messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]) -> Any:
        _ = messages
        if not openai_tools:  # the split call that runs beside the loop: one place, no split
            return {"content": "{}", "tool_calls": []}
        return queue.pop(0)

    lines: list[str] = []
    response = await ask_one.ask_one(
        QUESTION, record=record, complete=complete, tools=_tools(record), out=lines.append
    )
    return response, "\n".join(lines)


async def test_the_trace_shows_every_model_turn_and_tool_call_in_order() -> None:
    response, text = await _run()
    assert response.table_id == "B01003"
    positions = [
        text.index(f"[tool] {name}")
        for name in ("search_tables", "resolve_geography", "build_url", "fetch_data")
    ]
    assert positions == sorted(positions)
    assert "[model turn 1]" in text and "[model turn 5]" in text
    assert "[model split]" in text
    assert '[tool] build_url  args as received: {"table_id": "B01003"}' in text


async def test_the_summary_shows_the_answer_table_geoid_and_a_redacted_url() -> None:
    response, text = await _run()
    assert "== response ==" in text
    assert "table        : B01003   universe: Total population" in text
    assert "geoid        : 0500000US48201" in text
    assert response.urls[0] in text
    assert "key=" not in text


def test_a_long_value_is_cut_and_its_full_length_is_kept() -> None:
    assert ask_one._short("x" * 1000, 50) == "x" * 50 + "... [1000 chars]"
    assert ask_one._short({"a": 1}, 50) == '{"a": 1}'


def test_a_census_key_in_a_value_is_redacted_before_it_is_printed() -> None:
    url = "https://api.census.gov/data/2023/acs/acs5?get=B01003_001E&for=state:*&key=SECRET123"
    for value in (url, {"url": url}):
        text = ask_one._short(value, 500)
        assert "SECRET123" not in text
        assert "key=REDACTED" in text


class _Boom(BaseTool):
    name: str = "boom"
    description: str = "always raises"

    def _run(self, *args: Any, **kwargs: Any) -> str:
        raise ValueError("no data&key=SECRET123")

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise ValueError("no data&key=SECRET123")


async def test_a_tool_that_raises_is_traced_and_still_raises() -> None:
    lines: list[str] = []
    tool = _Boom()
    ask_one._trace_tool(tool, lines.append)
    with pytest.raises(ValueError, match="no data"):
        await tool.ainvoke({"type": "tool_call", "name": "boom", "args": {"q": 1}, "id": "1"})
    assert any("RAISED ValueError: no data&key=REDACTED" in line for line in lines)
    assert "SECRET123" not in " ".join(lines)


async def test_a_model_call_that_raises_is_traced_and_still_raises() -> None:
    lines: list[str] = []

    async def complete(messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]) -> Any:
        _ = messages
        raise RuntimeError("quota&key=SECRET123")

    traced = ask_one._trace_complete(complete, lines.append)
    with pytest.raises(RuntimeError, match="quota"):
        await traced([], [])  # no tools: the split call, which plan_split swallows
    with pytest.raises(RuntimeError, match="quota"):
        await traced([], [{"type": "function"}])
    assert any("[model split] RAISED RuntimeError: quota&key=REDACTED" in x for x in lines)
    assert any("[model turn 1] RAISED RuntimeError" in x for x in lines)
    assert "SECRET123" not in " ".join(lines)
