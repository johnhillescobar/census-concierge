"""The level a question asks for is stated by the model, run exactly, and checked against the URL.

These tests stand in for the model by stating (or failing to state) a level, then check what the
code does with it. None asserts on prose; they assert on the level that was executed and on the
warning code raised when it was not the level that was asked for.
"""

from __future__ import annotations

from typing import Any

import pytest
from ask_fixtures import ENTRIES, _geo_tool, _harris, _tools
from pydantic import ValidationError
from src.ask import ExecutionRecord, assemble, dispatch, run_ask
from src.census_url import CensusURL
from src.contract import GeoSpec
from src.geo_level import declared_levels, note_intent
from src.guards import evaluate
from src.retrieval.metadata import GeoLevel
from src.tools import ResolveGeographyInput

TRACT_URL = "https://api.census.gov/data/2024/acs/acs5?get=B01003_001E&for=tract:*&in=state:55"
COUNTY_URL = "https://api.census.gov/data/2024/acs/acs5?get=B01003_001E&for=county:201&in=state:48"
US_URL = "https://api.census.gov/data/2024/acs/acs5?get=B01003_001E&for=us:1"


def _codes(record: ExecutionRecord) -> list[str]:
    return [warning.code for warning in evaluate(record)]


def _answered(url: str, asked: list[str | None], **fields: Any) -> ExecutionRecord:
    record = ExecutionRecord(question="population", asked_levels=asked)
    record.geographies = [_harris()]
    record.geography = record.geographies[0]
    record.url = CensusURL(url)
    for name, value in fields.items():
        setattr(record, name, value)
    return record


# --- intent: the model must state a level ------------------------------------------------------


def test_the_schema_requires_the_model_to_state_a_level() -> None:
    with pytest.raises(ValidationError):
        ResolveGeographyInput(query="Texas")
    assert ResolveGeographyInput(query="Texas", level=None).level is None


async def test_a_call_that_omits_the_level_is_refused_for_repair_and_is_bounded() -> None:
    record = ExecutionRecord()
    geo = _tools(record)["resolve_geography"]
    refused = await dispatch(geo, {"id": "1", "args": {"query": "Harris County"}}, record)
    assert refused.startswith("resolve_geography failed")
    assert record.geographies == [] and record.asked_levels == []
    with pytest.raises(RuntimeError, match="failed twice"):
        await dispatch(geo, {"id": "2", "args": {"query": "Harris County"}}, record)


async def test_a_repair_call_never_overwrites_the_level_the_model_stated() -> None:
    record = ExecutionRecord()
    geo = _tools(record)["resolve_geography"]
    await dispatch(geo, {"id": "1", "args": {"level": "county", "query": "Harris County"}}, record)
    assert record.asked_levels == ["county"]
    repair = {"id": "2", "origin": "repair", "args": {"level": "tract", "query": "Harris County"}}
    await dispatch(geo, repair, record)
    assert record.asked_levels == ["county"]


def test_declared_levels_follow_the_legs_the_call_resolves() -> None:
    legs = ["Austin, Texas", "Texas"]
    assert declared_levels({"level": "county", "query": "x"}) == ["county"]
    assert declared_levels({"level": None, "query": "x"}) == [None]
    assert declared_levels({"places": legs, "levels": ["Place", "state"]}) == ["place", "state"]
    assert declared_levels({"places": legs, "level": "tract"}) == ["tract", "tract"]
    assert declared_levels({"places": legs, "level": "place", "levels": ["place"]}) == ["place"] * 2


def test_only_a_resolve_call_that_states_a_level_records_one() -> None:
    record = ExecutionRecord()
    note_intent(record, "resolve_geography", {"args": {"query": "x"}})
    note_intent(record, "build_url", {"args": {"level": "county"}})
    assert record.asked_levels == []


# --- execution: the stated level is the level run ----------------------------------------------


async def test_the_stated_level_is_run_even_when_the_query_names_another() -> None:
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": "place", "query": "Cook County"},
            "id": "c1",
        }
    )
    assert {spec.level for spec in result.artifact.specs} <= {"place"}
    assert result.artifact.inferred is False


async def test_a_level_the_model_did_not_state_is_marked_inferred() -> None:
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": None, "query": "Cook County"},
            "id": "c1",
        }
    )
    assert result.artifact.inferred is True


async def test_an_unpublished_level_is_refused_with_the_published_names() -> None:
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": "congressional district", "query": "Texas"},
            "id": "c1",
        }
    )
    artifact = result.artifact
    assert artifact.legal is False and artifact.specs == []
    assert all(entry.name in artifact.detail for entry in ENTRIES)


async def test_a_published_level_with_no_alias_is_run_by_exact_metadata_match() -> None:
    table = [*ENTRIES, GeoLevel("urban area", "400", (), (), "")]

    def listing(level: str, parts: dict[str, str], **_: Any) -> list[dict[str, str]]:
        assert level == "urban area"
        return [
            {
                "name": "Denver, Colorado Urban Area",
                "level": "urban area",
                "for": "urban area:23527",
                "in": "",
                "geoid": "400C100US23527",
                "population": "2374203",
            }
        ]

    result = await _geo_tool(listing=listing, table=table).ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": "Urban Area", "query": "Denver"},
            "id": "c1",
        }
    )
    assert [spec.for_spec for spec in result.artifact.specs] == ["urban area:23527"]


async def test_each_comparison_leg_is_run_at_its_own_stated_level() -> None:
    args = {"level": None, "places": ["Austin, Texas", "Texas"], "levels": ["place", "state"]}
    result = await _geo_tool().ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c1"}
    )
    artifact = result.artifact
    assert artifact.compare is True
    assert [spec.level for spec in artifact.specs[:2]] == ["place", "state"]


async def test_a_single_level_stated_for_mixed_legs_is_not_quietly_corrected() -> None:
    args = {"level": "place", "places": ["Austin, Texas", "Texas"]}
    result = await _geo_tool().ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c1"}
    )
    assert "state" not in {spec.level for spec in result.artifact.specs}


# --- validation: what was fetched must be the level that was asked -----------------------------


def test_a_fetch_at_another_level_is_flagged_and_still_shows_its_url() -> None:
    record = _answered(COUNTY_URL, ["tract"])
    assert _codes(record) == ["geography_level_mismatch"]
    response = assemble("shown", record)
    assert response.urls and "county:201" in response.urls[0]
    detail = response.warnings[0].detail
    assert "tract" in detail and "county" in detail


def test_a_fetch_at_the_stated_level_is_not_flagged() -> None:
    assert _codes(_answered(COUNTY_URL, ["county"])) == []


def test_the_nationwide_fallback_cannot_hide_a_substituted_level() -> None:
    us = GeoSpec(level="us", name="United States", for_spec="us:1", geoid="0100000US")
    record = _answered(US_URL, ["tract"], geographies=[us])
    assert "geography_level_mismatch" in _codes(record)


def test_every_fetched_url_is_held_to_the_stated_level() -> None:
    record = _answered(TRACT_URL, ["tract"])
    record.fetch = type("Fetch", (), {"urls": [TRACT_URL, COUNTY_URL]})()
    assert "geography_level_mismatch" in _codes(record)


def test_a_leg_with_no_stated_level_is_checked_against_the_level_the_lookup_chose() -> None:
    assert _codes(_answered(COUNTY_URL, [None])) == []
    record = _answered(TRACT_URL, [None])
    assert "geography_level_mismatch" in _codes(record)


def test_a_table_question_is_never_flagged_for_its_level() -> None:
    record = _answered(COUNTY_URL, ["tract"], tables_only=True)
    assert "geography_level_mismatch" not in _codes(record)


# --- visibility: an unstated or inferred level is shown, not guessed quietly -------------------


def test_a_geography_resolved_without_a_stated_level_is_unverified() -> None:
    assert _codes(_answered(COUNTY_URL, [])) == ["geography_level_unverified"]


def test_a_level_the_code_inferred_is_unverified_even_when_the_model_stated_none() -> None:
    record = _answered(COUNTY_URL, [None], geo_status={"legal": True, "inferred": True})
    assert _codes(record) == ["geography_level_unverified"]


def test_a_stated_level_that_was_run_as_stated_raises_no_level_warning() -> None:
    record = _answered(COUNTY_URL, ["county"], geo_status={"legal": True, "inferred": False})
    assert _codes(record) == []


def test_a_users_own_plan_is_not_a_model_reading() -> None:
    plan = type("Plan", (), {"geographies": [_harris()]})()
    assert _codes(_answered(COUNTY_URL, [], override=plan)) == []


async def test_a_loop_whose_model_states_the_level_raises_no_level_warning() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    steps = [
        ("search_tables", {"question": "population of Harris County, Texas"}),
        ("resolve_geography", {"level": "county", "query": "Harris County, Texas"}),
        ("build_url", {"table_id": "B01003"}),
        ("fetch_data", {}),
    ]
    queue: list[dict[str, Any]] = [
        {"content": "", "tool_calls": [{"id": str(i), "name": name, "args": args}]}
        for i, (name, args) in enumerate(steps)
    ]
    queue.append({"content": "done", "tool_calls": []})

    async def complete(messages: list[dict[str, Any]], tools_: list[dict[str, Any]]) -> Any:
        del messages
        if not tools_:  # the beside-the-loop split call carries no tools and reads no queue
            return {"content": "{}", "tool_calls": []}
        return queue.pop(0)

    response = await run_ask(
        "population of Harris County, Texas", complete=complete, tools=tools, record=record
    )
    assert record.asked_levels == ["county"]
    assert response.urls
    assert not {w.code for w in response.warnings} & {
        "geography_level_mismatch",
        "geography_level_unverified",
    }


async def test_a_refused_level_stands_and_is_not_re_guessed_from_the_question() -> None:
    """The model stated a level the dataset does not publish. Finish must not rerun the lookup
    from the question's words and overwrite that refusal with an empty, silent result."""
    record = ExecutionRecord()
    tools = _tools(record)
    steps = [
        ("search_tables", {"question": "population of Texas congressional districts"}),
        ("resolve_geography", {"level": "congressional district", "query": "Texas"}),
    ]
    queue: list[dict[str, Any]] = [
        {"content": "", "tool_calls": [{"id": str(i), "name": name, "args": args}]}
        for i, (name, args) in enumerate(steps)
    ]
    queue.append({"content": "done", "tool_calls": []})

    async def complete(messages: list[dict[str, Any]], tools_: list[dict[str, Any]]) -> Any:
        del messages
        if not tools_:
            return {"content": "{}", "tool_calls": []}
        return queue.pop(0) if queue else {"content": "done", "tool_calls": []}

    response = await run_ask(
        "population of Texas congressional districts", complete=complete, tools=tools, record=record
    )
    assert record.geo_status is not None and record.geo_status["refused"] is True
    assert record.geographies == [] and response.urls == []
    assert [w.code for w in response.warnings] == ["geography_unsupported"]
    assert all(entry.name in response.warnings[0].detail for entry in ENTRIES)


async def test_a_published_level_is_not_marked_refused() -> None:
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": "county", "query": "Harris County, Texas"},
            "id": "c1",
        }
    )
    assert result.artifact.refused is False


async def test_a_nationwide_resolution_the_code_chose_is_marked_inferred() -> None:
    """The model stated no level and named no place; code chose the United States. Say so."""
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": None, "query": "How has the share of households changed since 2013?"},
            "id": "c1",
        }
    )
    assert [spec.for_spec for spec in result.artifact.specs] == ["us:1"]
    assert result.artifact.inferred is True


async def test_a_stated_level_is_never_replaced_by_the_nationwide_guess() -> None:
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": "state", "query": "Texas population since 2013"},
            "id": "c1",
        }
    )
    assert [spec.level for spec in result.artifact.specs] == ["state"]
    assert result.artifact.inferred is False
