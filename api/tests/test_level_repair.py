"""Finish's repair calls re-resolve geography without ever rewriting the level the model stated.

The loop's own `resolve_geography` call records what the model stated. Finish may call the tool
again to repair a bad resolution; that call must be marked a repair and must carry the stated levels
rather than invent others. These tests drive `finish_tools` and check the calls it makes.
"""

from __future__ import annotations

import json
from typing import Any

from ask_fixtures import _geo_tool
from src.ask import ExecutionRecord, dispatch
from src.contract import GeoSpec
from src.finish import finish_tools, plan_split


async def test_a_repair_of_sequential_places_passes_each_stated_level_marked_as_repair() -> None:
    record = ExecutionRecord(question="Austin and Texas")
    record.geo_queries = ["Austin, Texas", "Texas"]
    record.geo_status = {"legal": True, "compare": False}
    record.asked_levels = ["place", "state"]
    calls: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        calls.append(call)
        return ""

    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record)
    assert [c.get("origin") for c in calls] == ["repair"]
    assert calls[0]["args"]["places"] == ["Austin, Texas", "Texas"]
    assert calls[0]["args"]["levels"] == ["place", "state"]


async def test_a_repair_resolution_never_replaces_the_level_the_model_stated() -> None:
    record = ExecutionRecord(question="population of Harris County, Texas")
    record.asked_levels = ["county"]
    record.geo_queries = ["Harris County, Texas"]
    await finish_tools(dispatch, {"resolve_geography": _geo_tool()}, record)
    assert record.geographies  # the repair did resolve something
    assert record.asked_levels == ["county"]


async def test_a_question_the_model_reported_no_place_for_is_given_no_guessed_one() -> None:
    record = ExecutionRecord(question="households and families in Texas")
    record.asked_levels = ["tract"]
    calls: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        calls.append(call)
        return ""

    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record)
    assert calls == []


async def test_a_repair_of_a_multi_parent_listing_is_marked_as_repair() -> None:
    record = ExecutionRecord(question="List every county in Ohio and Michigan.")
    record.geographies = [
        GeoSpec(level="county", name="m", for_spec="county:*", in_spec="state:26")
    ]
    calls: list[dict[str, Any]] = []

    async def complete(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        reply = {"level": None, "parents": ["Ohio", "Michigan"], "unit": "county", "listing": True}
        return {"content": json.dumps(reply), "tool_calls": []}

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        calls.append(call)
        return ""

    await finish_tools(
        fake_dispatch,
        {"resolve_geography": object()},
        record,
        plan_split(record.question, complete),
    )
    assert calls[0]["origin"] == "repair" and calls[0]["args"]["level"] == "county"
