"""Tracts inside a named place: derived from the counties the place lies in, never from the place.

Census has no tract-inside-place row, but ACS 5-year publishes which counties a place lies in.
The live API answered this for Detroit: `county (or part)` under state 26 and place 22000 is
Wayne County (163). These tests give the tool that metadata and listing and check what it does.
"""

from __future__ import annotations

from typing import Any

from ask_fixtures import ENTRIES, _geo_tool, _list_geographies, _tools
from src.ask import ExecutionRecord, run_ask
from src.census_url import CensusURL
from src.retrieval.metadata import GeoLevel

PART = GeoLevel("county (or part)", "155", ("state", "place"), (), "")
WITH_STEP = [*ENTRIES, PART]

# place code -> the counties the live API reported it lies in (name, county code)
COUNTIES = {
    "22000": [("Wayne County (part), Detroit city, Michigan", "163")],
    "19000": [
        ("Dallas County (part), Dallas city, Texas", "113"),
        ("Collin County (part), Dallas city, Texas", "085"),
    ],
}


def listing(level: str, parts: dict[str, str], **kwargs: Any) -> list[dict[str, str]]:
    """The fixture's own listings, plus the county step with the shape the live API returned."""
    if level != "county (or part)":
        return _list_geographies(level, parts, **kwargs)
    return [
        {
            "name": name,
            "level": level,
            "for": f"{level}:{county}",
            "in": f"state:{parts['state']} place:{parts['place']}",
            "geoid": "",
            "population": "1",
        }
        for name, county in COUNTIES.get(parts["place"], [])
    ]


def tool(table: list[GeoLevel] = WITH_STEP) -> Any:
    return _geo_tool(listing=listing, table=table)


async def resolve(args: dict[str, Any], table: list[GeoLevel] = WITH_STEP) -> Any:
    message = await tool(table).ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c1"}
    )
    return message.artifact


ASK = {"level": "tract", "query": "census tract in Detroit", "parents": ["Detroit, MI"]}


async def test_tracts_in_a_place_are_the_tracts_of_the_county_it_lies_in() -> None:
    result = await resolve(ASK)
    county = result.specs[0]
    assert (county.level, county.for_spec, county.in_spec) == (
        "tract",
        "tract:*",
        "state:26 county:163",
    )
    assert result.compare is False and result.legal is False
    assert "place boundary is not applied" in result.detail and "Wayne County" in result.detail


async def test_a_place_in_several_counties_gets_the_tracts_of_each() -> None:
    result = await resolve({**ASK, "parents": ["Dallas, TX"]})
    counties = [spec.in_spec for spec in result.specs[: result.compare_count]]
    assert counties == ["state:48 county:113", "state:48 county:085"]
    assert result.compare is True and result.compare_count == 2


async def test_without_the_county_step_nothing_is_derived_and_nothing_is_asked() -> None:
    """ACS 1-year publishes no county step. The live API answers HTTP 400 there, so the listing
    must not even be attempted."""

    def never(*args: Any, **kwargs: Any) -> list[dict[str, str]]:
        raise AssertionError("the county step was requested where it is not published")

    message = await _geo_tool(listing=never, table=ENTRIES).ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": ASK, "id": "c1"}
    )
    assert message.artifact.legal is False
    assert not any("county:163" in spec.in_spec for spec in message.artifact.specs)


async def test_only_a_tract_request_beside_one_named_place_is_derived() -> None:
    county = await resolve({"level": "county", "query": "Detroit", "parents": ["Detroit, MI"]})
    assert "not published" not in county.detail and all(s.level != "tract" for s in county.specs)
    two = await resolve({**ASK, "parents": ["Detroit, MI", "Dallas, TX"]})
    assert "place boundary is not applied" not in two.detail


async def test_a_name_that_is_not_a_place_is_not_derived() -> None:
    result = await resolve({**ASK, "parents": ["Nowheresville, TX"]})
    assert not any("county:" in spec.in_spec for spec in result.specs)


async def test_the_derived_url_reaches_the_user_at_tract_level_with_a_warning() -> None:
    record = ExecutionRecord()
    tools = _tools(record)
    tools["resolve_geography"] = tool()
    steps = [
        ("search_tables", {"question": "poverty"}),
        ("resolve_geography", ASK),
        ("build_url", {"table_id": "B17001"}),
        ("fetch_data", {}),
    ]
    queue: list[dict[str, Any]] = [
        {"content": "", "tool_calls": [{"id": str(i), "name": n, "args": a}]}
        for i, (n, a) in enumerate(steps)
    ]

    async def complete(messages: list[dict[str, Any]], tools_: list[dict[str, Any]]) -> Any:
        del messages
        if not tools_:
            return {"content": "{}", "tool_calls": []}
        return queue.pop(0) if queue else {"content": "done", "tool_calls": []}

    response = await run_ask(
        "Poverty rate by census tract in Detroit", complete=complete, tools=tools, record=record
    )
    url = CensusURL(response.urls[0])
    assert url.for_level() == "tract" and "county:163" in str(url) and "state:26" in str(url)
    codes = [w.code for w in response.warnings]
    assert "geography_unsupported" in codes and "geography_level_mismatch" not in codes
    assert "Wayne County" in next(
        w.detail for w in response.warnings if w.code == "geography_unsupported"
    )


async def test_the_model_is_told_the_derived_tracts_as_an_ordinary_success() -> None:
    """Told "not published", the model abandons the tracts and looks up the county instead (seen
    live). The reply it reads carries the geography; the limitation is the user's warning."""
    message = await tool().ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": ASK, "id": "c1"}
    )
    assert message.content == "wildcard tract:* state:26 county:163"
    assert "not published" in message.artifact.detail
