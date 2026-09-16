"""Four ask tools: search, geography legality, URL construction, fetch.

No live Census or model. Fakes vary by input — a stub that always returns
B01003 would hide a broken search, which is the predecessor's failure.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from ask_fixtures import ENTRIES, _describe, _geo_tool, _harris, _list_geographies, _search
from pydantic import ValidationError
from src.census_url import CensusURL
from src.contract import GeoSpec, clause_codes
from src.fetch import FetchDataTool
from src.geo import (
    filter_rows,
    find_state,
    legal_predicate,
    list_census_names,
    nests_in,
    place_token,
    rank_matches,
)
from src.retrieval.metadata import GeoLevel, geo_entries, geo_levels
from src.tools import (
    BuildUrlTool,
    ResolveGeographyInput,
    SearchTablesTool,
    pair_margins,
)


@pytest.fixture
def search_tool() -> SearchTablesTool:
    return SearchTablesTool(search=_search, describe=_describe)


async def test_different_questions_reach_different_tables(search_tool: SearchTablesTool) -> None:
    bike = await search_tool.ainvoke(
        {
            "type": "tool_call",
            "name": "search_tables",
            "args": {"question": "bike to work"},
            "id": "c1",
        }
    )
    net = await search_tool.ainvoke(
        {
            "type": "tool_call",
            "name": "search_tables",
            "args": {"question": "worst broadband access"},
            "id": "c2",
        }
    )
    assert bike.artifact.hits[0]["table_id"] == "B08301"
    assert net.artifact.hits[0]["table_id"] == "B28002"
    assert bike.artifact.hits[0]["table_id"] != net.artifact.hits[0]["table_id"]


async def test_search_carries_universe_and_family_members(search_tool: SearchTablesTool) -> None:
    message = await search_tool.ainvoke(
        {
            "type": "tool_call",
            "name": "search_tables",
            "args": {"question": "median household income", "k": 10},
            "id": "c1",
        }
    )
    hit = message.artifact.hits[0]
    assert hit["table_id"] == "B19013"
    assert hit["universe"] == "Households"
    assert hit["members"] == ["B19013A", "B19013B"]
    assert [h["table_id"] for h in message.artifact.hits] == ["B19013"]
    assert "Median Household Income" in message.content


async def test_unknown_vocabulary_does_not_invent_a_table(search_tool: SearchTablesTool) -> None:
    message = await search_tool.ainvoke(
        {
            "type": "tool_call",
            "name": "search_tables",
            "args": {"question": "zzzz nonexistent vocabulary"},
            "id": "c1",
        }
    )
    assert message.artifact.hits == []


def _pool_search(question: str, k: int = 10) -> list[str]:
    del question
    return ["B27010", "B27001"][:k]


async def test_selector_pick_is_first_hit() -> None:
    tool = SearchTablesTool(
        search=_pool_search,
        describe=_describe,
        select=lambda question, hits: "B27001",
    )
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "search_tables",
            "args": {"question": "health insurance by age"},
            "id": "c1",
        }
    )
    ids = [hit["table_id"] for hit in message.artifact.hits]
    assert ids[0] == "B27001"
    assert ids == ["B27001", "B27010"]
    assert "B27001" in message.content
    assert "B27010" not in message.content


async def test_empty_search_does_not_call_selector() -> None:
    def boom(question: str, hits: list[dict[str, object]]) -> str:
        raise AssertionError(f"selector called: {question!r} {hits!r}")

    tool = SearchTablesTool(search=_search, describe=_describe, select=boom)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "search_tables",
            "args": {"question": "zzzz nonexistent vocabulary"},
            "id": "c1",
        }
    )
    assert message.artifact.hits == []


async def test_same_question_does_not_reselect() -> None:
    calls: list[str] = []

    def select(question: str, hits: list[dict[str, object]]) -> str:
        del hits
        calls.append(question)
        return "B27001"

    tool = SearchTablesTool(search=_pool_search, describe=_describe, select=select)
    payload = {
        "type": "tool_call",
        "name": "search_tables",
        "args": {"question": "health insurance by age"},
        "id": "c1",
    }
    first = await tool.ainvoke(payload)
    second = await tool.ainvoke({**payload, "id": "c2"})
    assert calls == ["health insurance by age"]
    assert [hit["table_id"] for hit in first.artifact.hits][0] == "B27001"
    assert [hit["table_id"] for hit in second.artifact.hits][0] == "B27001"


async def test_unknown_selector_id_keeps_retrieval_order() -> None:
    tool = SearchTablesTool(
        search=_pool_search,
        describe=_describe,
        select=lambda question, hits: "B99999",
    )
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "search_tables",
            "args": {"question": "health insurance by age"},
            "id": "c1",
        }
    )
    assert [hit["table_id"] for hit in message.artifact.hits] == ["B27010", "B27001"]


def test_county_in_state_uses_summary_level_050_not_last_wins() -> None:
    chosen = legal_predicate("county", frozenset({"state"}), wildcard=True, entries=ENTRIES)
    assert chosen is not None
    assert chosen.code == "050"
    last_wins = next(entry for entry in ENTRIES if entry.code == "324")
    assert last_wins.name == "county"
    assert chosen != last_wins


def test_place_wildcard_does_not_accept_an_extra_county_parent() -> None:
    chosen = legal_predicate(
        "place", frozenset({"state", "county"}), wildcard=True, entries=ENTRIES
    )
    assert chosen is None


def test_zcta_nested_in_county_is_not_legal() -> None:
    assert (
        legal_predicate(
            "zip code tabulation area",
            frozenset({"county"}),
            wildcard=True,
            entries=ENTRIES,
        )
        is None
    )


async def test_all_zctas_in_a_county_is_rejected_not_rewritten() -> None:
    # Without the county parent in the legality check this becomes a national
    # zcta:* wildcard — a silent substitution the Census API would 400.
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "all zctas in Harris County"},
            "id": "c1",
        }
    )
    assert message.artifact.legal is False
    assert message.artifact.wildcard is True
    assert message.artifact.nested is False
    assert message.artifact.specs == []


def test_tract_nests_in_county_not_place() -> None:
    assert nests_in("tract", "county", ENTRIES)
    assert not nests_in("tract", "place", ENTRIES)
    assert not nests_in("zip code tabulation area", "county", ENTRIES)
    assert not nests_in("zip code tabulation area", "place", ENTRIES)


async def test_named_zcta_resolves_without_a_parent() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Median household income for ZCTA 90210"},
            "id": "c1",
        }
    )
    assert message.artifact.legal is True
    assert message.artifact.nested is True
    assert [row.for_spec for row in message.artifact.specs] == ["zip code tabulation area:90210"]
    assert message.artifact.specs[0].in_spec == ""
    assert message.artifact.specs[0].geoid == "860Z200US90210"


@pytest.mark.parametrize(
    "query",
    ["ZCTA 90210 Oregon", "Median household income for ZCTA 90210 in Oregon"],
)
async def test_named_zcta_with_a_state_is_not_nested(query: str) -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": query},
            "id": "c1",
        }
    )
    assert message.artifact.legal is False
    assert message.artifact.nested is False
    assert message.artifact.specs == []


def test_harris_does_not_match_harrison() -> None:
    rows = _list_geographies("county", {"state": "48"})
    hits = filter_rows("harris", rows)
    assert [row["for"] for row in hits] == ["county:201"]


def test_duplicate_names_rank_by_class_then_population() -> None:
    rows = [
        {
            "name": "Riverton CDP, Wyoming",
            "level": "place",
            "for": "place:2",
            "in": "state:56",
            "geoid": "1600000US5600002",
            "population": "999999",
        },
        {
            "name": "Riverton town, Wyoming",
            "level": "place",
            "for": "place:3",
            "in": "state:56",
            "geoid": "1600000US5600003",
            "population": "500000",
        },
        {
            "name": "Riverton city, Wyoming",
            "level": "place",
            "for": "place:1",
            "in": "state:56",
            "geoid": "1600000US5600001",
            "population": "100",
        },
    ]
    assert [row["for"] for row in rank_matches(rows)] == ["place:1", "place:3", "place:2"]


def test_missing_population_sorts_last_then_geoid() -> None:
    rows = [
        {
            "name": "Alpha city, X",
            "level": "place",
            "for": "place:1",
            "geoid": "z",
            "population": "nope",
        },
        {
            "name": "Beta city, X",
            "level": "place",
            "for": "place:2",
            "geoid": "m",
            "population": "10",
        },
        {
            "name": "Gamma city, X",
            "level": "place",
            "for": "place:3",
            "geoid": "a",
            "population": "10",
        },
    ]
    assert [row["for"] for row in rank_matches(rows)] == ["place:3", "place:2", "place:1"]


def test_county_rank_ignores_place_class() -> None:
    rows = [
        {
            "name": "Cook County, Georgia",
            "level": "county",
            "for": "county:075",
            "geoid": "0500000US13075",
            "population": "17532",
        },
        {
            "name": "Cook County, Illinois",
            "level": "county",
            "for": "county:031",
            "geoid": "0500000US17031",
            "population": "5182090",
        },
    ]
    assert rank_matches(rows)[0]["for"] == "county:031"


@pytest.mark.parametrize(
    "query",
    ["all counties in Washington state", "all counties in the state of Washington"],
)
async def test_state_descriptor_is_still_a_county_wildcard(query: str) -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": query},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.wildcard is True
    assert artifact.legal is True
    spec = artifact.specs[0]
    assert spec.for_spec == "county:*"
    assert spec.in_spec == "state:53"


async def test_all_places_in_oregon_is_a_state_wildcard() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "all places in Oregon"},
            "id": "c1",
        }
    )
    spec = message.artifact.specs[0]
    assert message.artifact.legal is True
    assert spec.for_spec == "place:*"
    assert spec.in_spec == "state:41"


async def test_all_places_in_washington_state_is_a_state_wildcard() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "all places in Washington state"},
            "id": "c1",
        }
    )
    spec = message.artifact.specs[0]
    assert message.artifact.legal is True
    assert spec.for_spec == "place:*"
    assert spec.in_spec == "state:53"


@pytest.mark.parametrize("query", ["all ZCTAs in Oregon", "ZCTAs within Oregon"])
async def test_zctas_in_a_state_are_not_nested(query: str) -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": query},
            "id": "c1",
        }
    )
    assert message.artifact.legal is False
    assert message.artifact.nested is False
    assert message.artifact.specs == []


async def test_all_counties_in_oregon_is_one_wildcard_request() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "all counties in Oregon"},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.wildcard is True
    assert artifact.legal is True
    spec = artifact.specs[0]
    assert spec.level == "county"
    assert spec.name == "all counties in Oregon"
    assert spec.for_spec == "county:*"
    assert spec.in_spec == "state:41"
    assert spec.geoid == ""
    assert spec.codes == {"county": "*", "state": "41"}
    assert spec.dataset == "acs5"
    assert spec.vintage == 2024


async def test_cook_county_selects_illinois_and_keeps_every_match() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Cook County"},
            "id": "c1",
        }
    )
    specs = message.artifact.specs
    assert [row.in_spec for row in specs] == ["state:17", "state:13", "state:27"]
    assert len(specs) == 3
    assert "selected county:031 state:17" in message.content
    assert "2 alternatives" in message.content
    assert "state:13" not in message.content


async def test_portland_selects_oregon_over_maine() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "bike to work in Portland"},
            "id": "c1",
        }
    )
    specs = message.artifact.specs
    assert specs[0].in_spec == "state:41"
    assert {row.in_spec for row in specs} == {"state:41", "state:23"}
    assert "alternatives" in message.content


async def test_springfield_selects_missouri_and_keeps_every_match() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Population of Springfield"},
            "id": "c1",
        }
    )
    specs = message.artifact.specs
    assert specs[0].in_spec == "state:29"
    assert {row.name for row in specs} == {
        "Springfield city, Missouri",
        "Springfield city, Illinois",
        "Springfield CDP, Virginia",
    }
    assert "alternatives" in message.content
    assert "Springfield city, Illinois" not in message.content


async def test_state_qualified_place_stays_exact() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Portland, Maine"},
            "id": "c1",
        }
    )
    assert [row.in_spec for row in message.artifact.specs] == ["state:23"]
    assert "alternatives" not in message.content


async def test_harris_county_texas_resolves_to_codes() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Harris County, Texas"},
            "id": "c1",
        }
    )
    assert [row.for_spec for row in message.artifact.specs] == ["county:201"]
    assert message.artifact.specs[0].in_spec == "state:48"


def test_pair_margins_adds_m_beside_every_e() -> None:
    assert pair_margins(["B01003_001E"]) == ["B01003_001E", "B01003_001M"]
    assert pair_margins(["B01003_001E", "B01003_001M"]) == ["B01003_001E", "B01003_001M"]


def _url_tool() -> BuildUrlTool:
    facts = {
        "acs5": {
            2024: {
                "B01003": {"universe": "Total population", "variables": ["001E"]},
                "B19013A": {"universe": "Households", "variables": ["001E"]},
            }
        }
    }
    allowed = {"B01003", "B19013", "B19013A"}
    return BuildUrlTool(
        allowed_tables=lambda: allowed,
        allowed_geographies=lambda: {("county:201", "state:48", "acs5")},
        latest_vintage=lambda dataset: 2024,
        table_facts=lambda dataset, year, table_id: (
            facts.get(dataset, {}).get(year, {}).get(table_id)
        ),
        last_geography=lambda: _harris(),
    )


async def test_build_url_pairs_margins_and_redacts_the_key() -> None:
    message = await _url_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B01003", "variables": ["B01003_001E"]},
            "id": "c1",
        }
    )
    url = message.artifact.url
    assert "B01003_001E" in url
    assert "B01003_001M" in url
    assert "for=county:201" in url or "for=county%3A201" in url
    assert "in=state:48" in url or "in=state%3A48" in url
    assert "key=" not in url
    assert message.artifact.ok is True


async def test_build_url_rejects_a_table_outside_the_pool() -> None:
    message = await _url_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B99999"},
            "id": "c1",
        }
    )
    assert message.artifact.ok is False
    assert message.artifact.url == ""
    assert "not in the search pool" in message.artifact.detail


async def test_build_url_accepts_a_recorded_family_member() -> None:
    message = await _url_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B19013A"},
            "id": "c1",
        }
    )
    assert message.artifact.ok is True
    assert message.artifact.table_id == "B19013A"
    assert message.artifact.universe == "Households"


async def test_build_url_rejects_a_geography_that_was_not_resolved() -> None:
    message = await _url_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B01003", "for_spec": "county:999", "in_spec": "state:48"},
            "id": "c1",
        }
    )
    assert message.artifact.ok is False
    assert message.artifact.url == ""


async def test_build_url_rejects_geography_resolved_for_a_different_dataset() -> None:
    facts = {
        "acs5": {2024: {"B01003": {"universe": "Total population", "variables": ["001E"]}}},
        "acs1": {2024: {"B01003": {"universe": "Total population", "variables": ["001E"]}}},
    }
    tool = BuildUrlTool(
        allowed_tables=lambda: {"B01003"},
        allowed_geographies=lambda: {("county:201", "state:48", "acs5")},
        latest_vintage=lambda dataset: 2024,
        table_facts=lambda dataset, year, table_id: (
            facts.get(dataset, {}).get(year, {}).get(table_id)
        ),
        last_geography=lambda: _harris(),
    )
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {
                "table_id": "B01003",
                "dataset": "acs1",
                "for_spec": "county:201",
                "in_spec": "state:48",
            },
            "id": "c1",
        }
    )
    assert message.artifact.ok is False
    assert message.artifact.url == ""


async def test_empty_in_spec_does_not_drop_the_resolved_parent() -> None:
    message = await _url_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B01003", "in_spec": ""},
            "id": "c1",
        }
    )
    assert message.artifact.ok is True
    assert "in=state:48" in message.artifact.url


async def test_fetch_keeps_the_url_when_census_returns_400() -> None:
    built = CensusURL("https://api.census.gov/data/2024/acs/acs5?get=NAME&for=county:*&in=state:41")

    def http_get(url: str) -> tuple[int, str]:
        assert "key=secret" in url
        return 400, "error: unknown/unsupported geography hierarchy"

    tool = FetchDataTool(last_url=lambda: built, census_key=lambda: "secret", http_get=http_get)
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "fetch_data", "args": {}, "id": "c1"}
    )
    assert message.artifact.ok is False
    assert message.artifact.status_code == 400
    assert "key=" not in message.artifact.url
    assert "2024/acs/acs5" in message.artifact.url
    assert str(built) == message.artifact.url


async def test_fetch_error_detail_does_not_carry_the_census_key() -> None:
    import httpx

    built = CensusURL("https://api.census.gov/data/2024/acs/acs5?get=NAME&for=state:11")

    def http_get(url: str) -> tuple[int, str]:
        raise httpx.HTTPError(f"connect failed for {url}")

    tool = FetchDataTool(last_url=lambda: built, census_key=lambda: "secret", http_get=http_get)
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "fetch_data", "args": {}, "id": "c1"}
    )
    assert message.artifact.ok is False
    assert "secret" not in message.artifact.detail
    assert "key=secret" not in message.content
    assert "key=" not in message.artifact.url


async def test_fetch_without_a_built_url_does_not_invent_one() -> None:
    tool = FetchDataTool(last_url=lambda: None, census_key=lambda: "secret")
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "fetch_data", "args": {}, "id": "c1"}
    )
    assert message.artifact.ok is False
    assert message.artifact.url == ""
    assert message.artifact.rows == []


def test_census_url_reattaches_the_key_only_at_with_key() -> None:
    url = CensusURL("https://api.census.gov/data/2024/acs/acs5?get=NAME&for=state:41&key=secret")
    assert "key=" not in str(url)
    assert "key=" not in repr(url)
    live = url.with_key("secret")
    assert live.endswith("key=secret") or "key=secret" in live


def test_census_url_strips_key_regardless_of_case() -> None:
    url = CensusURL("https://api.census.gov/data/2024/acs/acs5?get=NAME&for=state:41&KEY=secret")
    assert "secret" not in str(url)
    assert "secret" not in repr(url)
    assert "key=" not in str(url).casefold()


async def test_build_url_rejects_a_margin_with_no_estimate() -> None:
    message = await _url_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B01003", "variables": ["B01003_999M"]},
            "id": "c1",
        }
    )
    assert message.artifact.ok is False
    assert message.artifact.url == ""
    assert "B01003_999M" in message.artifact.detail


def _wide_url_tool(*, include_total: bool = True) -> BuildUrlTool:
    start = 1 if include_total else 2
    suffixes = [f"{i:03d}E" for i in range(start, start + 26)]
    facts = {"acs5": {2024: {"B99999": {"universe": "Synthetic universe", "variables": suffixes}}}}
    return BuildUrlTool(
        allowed_tables=lambda: {"B99999"},
        allowed_geographies=lambda: {("county:201", "state:48", "acs5")},
        latest_vintage=lambda dataset: 2024,
        table_facts=lambda dataset, year, table_id: (
            facts.get(dataset, {}).get(year, {}).get(table_id)
        ),
        last_geography=lambda: _harris(),
    )


async def test_omitted_variables_request_the_table_total() -> None:
    message = await _wide_url_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B99999"},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.ok is True
    assert artifact.variables == ["B99999_001E", "B99999_001M"]
    assert "get=NAME,GEO_ID,B99999_001E,B99999_001M" in artifact.url
    assert "B99999_002E" not in artifact.url
    assert "B99999_002M" not in artifact.url


async def test_explicit_estimate_does_not_expand_to_the_table() -> None:
    message = await _wide_url_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B99999", "variables": ["B99999_002E"]},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.ok is True
    assert artifact.variables == ["B99999_002E", "B99999_002M"]
    assert "B99999_001E" not in artifact.url
    assert "B99999_001M" not in artifact.url


async def test_missing_table_total_does_not_expand_to_every_cell() -> None:
    message = await _wide_url_tool(include_total=False).ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B99999"},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.ok is False
    assert artifact.url == ""
    assert "B99999_001E" in artifact.detail
    assert "B99999_002E" not in artifact.variables


async def test_fetch_error_body_does_not_carry_the_census_key() -> None:
    built = CensusURL("https://api.census.gov/data/2024/acs/acs5?get=NAME&for=state:11")

    def http_get(url: str) -> tuple[int, str]:
        return 400, f"unknown geography for {url}"

    tool = FetchDataTool(last_url=lambda: built, census_key=lambda: "secret", http_get=http_get)
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "fetch_data", "args": {}, "id": "c1"}
    )
    assert message.artifact.ok is False
    assert "secret" not in message.artifact.detail
    assert "key=secret" not in message.content


async def test_all_counties_in_the_us_keeps_the_state_wildcard() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "all counties in the US"},
            "id": "c1",
        }
    )
    artifact = message.artifact
    assert artifact.wildcard is True
    assert artifact.legal is True
    assert artifact.specs[0].for_spec == "county:*"
    assert artifact.specs[0].in_spec == "state:*"


async def test_all_places_in_a_county_is_rejected_not_broadened() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "all places in Harris County"},
            "id": "c1",
        }
    )
    assert message.artifact.legal is False
    assert message.artifact.nested is False
    assert message.artifact.specs == []
    assert "does not nest" in message.artifact.detail
    assert "state:*" not in message.content


async def test_unknown_level_does_not_list_census_names() -> None:
    called: list[tuple[str, dict[str, str]]] = []

    def listing(
        level: str, parts: dict[str, str], dataset: str = "acs5", vintage: int = 2024
    ) -> list[dict[str, str]]:
        _ = dataset, vintage
        called.append((level, parts))
        return []

    tool = _geo_tool(listing)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Harris County, Texas", "level": "county:*&get=NAME"},
            "id": "c1",
        }
    )
    assert called == []
    assert message.artifact.specs == []
    assert message.artifact.legal is False
    assert "unknown geography level" in message.artifact.detail


async def test_unknown_place_keeps_predicate_legality() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Atlantis, Texas"},
            "id": "c1",
        }
    )
    assert message.artifact.legal is True
    assert message.artifact.specs == []
    assert "no place matched" in message.artifact.detail


def test_listing_keeps_population_off_the_in_clause(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[list[str]]:
            return [
                ["NAME", "GEO_ID", "B01003_001E", "state", "county"],
                ["Cook County, Illinois", "0500000US17031", "5182090", "17", "031"],
            ]

    def fake_get(url: str, timeout: float = 0) -> object:
        _ = timeout
        captured["url"] = url
        return _Resp()

    monkeypatch.setattr("src.geo.httpx.get", fake_get)
    rows = list_census_names("county", {"state": "*"}, key="")
    assert "B01003_001E" in captured["url"]
    assert rows[0]["population"] == "5182090"
    assert rows[0]["in"] == "state:17"
    assert "B01003" not in rows[0]["in"]


def test_listing_error_does_not_carry_the_census_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from src.census_url import redact_text

    def boom(url: str, timeout: float = 0) -> object:
        _ = timeout
        raise httpx.HTTPError(f"boom {url}")

    monkeypatch.setattr("src.geo.httpx.get", boom)
    with pytest.raises(RuntimeError, match="geography listing failed") as caught:
        list_census_names("county", {"state": "48"}, key="secret")
    assert "secret" not in str(caught.value)
    assert "key=" not in str(caught.value)
    assert "key=secret" not in redact_text("https://api.census.gov/data?key=secret")


def test_washington_dc_is_not_washington_state() -> None:
    assert find_state("Washington, DC") == ("district of columbia", "11")
    assert find_state("Washington DC") == ("district of columbia", "11")
    assert find_state("Washington, D.C.") == ("district of columbia", "11")
    assert find_state("Washington") == ("washington", "53")
    assert find_state("all counties in Washington") == ("washington", "53")
    assert find_state("Washington County, Oregon") == ("oregon", "41")
    assert find_state("Washington County, OR") == ("oregon", "41")
    assert find_state("Kansas City, Missouri") == ("missouri", "29")
    assert find_state("West Virginia") == ("west virginia", "54")
    assert find_state("Virginia") == ("virginia", "51")


def test_new_york_city_token_keeps_new_york() -> None:
    assert place_token("New York City", "new york") == "new york"
    assert place_token("Austin, Texas", "texas") == "austin"
    assert place_token("State College, Pennsylvania", "pennsylvania") == "state college"


def test_empty_place_token_matches_nothing() -> None:
    rows = [{"name": "Albany city, New York", "for": "place:1"}]
    assert filter_rows("", rows) == []
    assert filter_rows("new york", rows) == []


@pytest.mark.parametrize("query", ["Washington, DC", "Washington DC", "Washington, D.C."])
async def test_washington_dc_resolves_as_district_of_columbia(query: str) -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": query},
            "id": "c1",
        }
    )
    assert [row.for_spec for row in message.artifact.specs] == ["state:11"]
    assert message.artifact.specs[0].geoid == "0400000US11"


async def test_new_york_city_does_not_return_every_new_york_place() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "New York City"},
            "id": "c1",
        }
    )
    assert [row.for_spec for row in message.artifact.specs] == ["place:3651000"]


async def test_bare_state_query_resolves_as_the_state() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "population of Texas"},
            "id": "c1",
        }
    )
    assert [row.for_spec for row in message.artifact.specs] == ["state:48"]


def _write_geo(root: Path, dataset: str, year: int, fips: list[dict[str, object]]) -> None:
    path = root / dataset / str(year) / "geography.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump({"fips": fips}, handle)


_STATE_FIPS: dict[str, object] = {
    "name": "state",
    "geoLevelDisplay": "040",
    "requires": [],
    "wildcard": [],
}
_COUNTY_FIPS: dict[str, object] = {
    "name": "county",
    "geoLevelDisplay": "050",
    "requires": ["state"],
    "wildcard": ["state"],
    "optionalWithWCFor": "state",
}


async def test_removing_county_row_from_fixture_fails_before_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.retrieval import metadata

    monkeypatch.setattr(metadata, "CACHE", tmp_path)
    called: list[tuple[str, dict[str, str]]] = []

    def listing(
        level: str, parts: dict[str, str], dataset: str = "acs5", vintage: int = 2024
    ) -> list[dict[str, str]]:
        _ = dataset, vintage
        called.append((level, parts))
        return _list_geographies(level, parts)

    tool = _geo_tool(listing, geo_table=metadata.geo_entries)
    args = {
        "type": "tool_call",
        "name": "resolve_geography",
        "args": {"query": "all counties in Oregon"},
        "id": "c1",
    }
    _write_geo(tmp_path, "acs5", 2024, [_STATE_FIPS, _COUNTY_FIPS])
    allowed = await tool.ainvoke(args)
    assert allowed.artifact.legal is True
    assert allowed.artifact.specs[0].for_spec == "county:*"
    called.clear()
    _write_geo(tmp_path, "acs5", 2024, [_STATE_FIPS])
    denied = await tool.ainvoke(args)
    assert called == []
    assert denied.artifact.legal is False
    assert denied.artifact.specs == []


async def test_acs1_table_without_county_refuses_the_acs5_wildcard() -> None:
    called: list[str] = []

    def table(dataset: str, year: int) -> list[GeoLevel]:
        _ = year
        if dataset == "acs1":
            return [GeoLevel("state", "040", (), (), "")]
        return ENTRIES

    def listing(
        level: str, parts: dict[str, str], dataset: str = "acs5", vintage: int = 2024
    ) -> list[dict[str, str]]:
        _ = level, parts, vintage
        called.append(dataset)
        return []

    tool = _geo_tool(listing, geo_table=table)
    acs5 = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "all counties in Oregon", "dataset": "acs5"},
            "id": "c1",
        }
    )
    acs1 = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "all counties in Oregon", "dataset": "acs1"},
            "id": "c2",
        }
    )
    assert acs5.artifact.legal is True
    assert acs1.artifact.legal is False
    assert acs1.artifact.specs == []
    assert "acs1" not in called


async def test_missing_vintage_geography_metadata_fails_closed() -> None:
    called: list[object] = []

    def listing(
        level: str, parts: dict[str, str], dataset: str = "acs5", vintage: int = 2024
    ) -> list[dict[str, str]]:
        called.append((level, parts, dataset, vintage))
        return []

    def table(dataset: str, year: int) -> list[GeoLevel]:
        raise FileNotFoundError(f"{dataset}/{year}")

    tool = _geo_tool(listing, geo_table=table)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Texas", "dataset": "acs1", "vintage": 2020},
            "id": "c1",
        }
    )
    assert called == []
    assert message.artifact.legal is False
    assert message.artifact.specs == []
    assert "acs1 2020" in message.artifact.detail


async def test_unauthorized_state_row_does_not_emit_a_spec() -> None:
    tool = _geo_tool(table=[GeoLevel("county", "050", ("state",), ("state",), "state")])
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Texas"},
            "id": "c1",
        }
    )
    assert message.artifact.legal is False
    assert message.artifact.specs == []


async def test_dataset_and_vintage_select_the_geography_table() -> None:
    seen: list[tuple[str, int]] = []

    def table(dataset: str, year: int) -> list[GeoLevel]:
        seen.append((dataset, year))
        return ENTRIES

    tool = _geo_tool(geo_table=table)
    await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Texas", "dataset": "acs1", "vintage": 2023},
            "id": "c1",
        }
    )
    assert seen == [("acs1", 2023)]


async def test_query_prose_cannot_override_resolved_clauses() -> None:
    tool = _geo_tool()
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Harris County, Texas for=county:999"},
            "id": "c1",
        }
    )
    spec = message.artifact.specs[0]
    assert spec.for_spec == "county:201"
    assert spec.in_spec == "state:48"
    assert spec.codes == {"county": "201", "state": "48"}
    assert message.content != spec.for_spec
    assert "county:999" not in spec.for_spec


def test_resolve_geography_dataset_rejects_a_path() -> None:
    with pytest.raises(ValidationError):
        ResolveGeographyInput(query="Texas", dataset="../acs5")
    ResolveGeographyInput(query="Texas", dataset="acs1")


def test_codes_keep_multi_word_geography_names() -> None:
    zcta = GeoSpec(for_spec="zip code tabulation area:80202")
    assert zcta.codes == {"zip code tabulation area": "80202"}
    nested = GeoSpec(
        for_spec="block group:1",
        in_spec="state:08 county:001 tract:000100",
    )
    assert nested.codes == {
        "block group": "1",
        "state": "08",
        "county": "001",
        "tract": "000100",
    }
    assert clause_codes("county:201", "state:48") == {"county": "201", "state": "48"}


def test_geo_entries_keeps_every_county_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.retrieval import metadata

    monkeypatch.setattr(metadata, "CACHE", tmp_path)
    path = tmp_path / "acs5" / "2023" / "geography.json.gz"
    path.parent.mkdir(parents=True)
    payload = {
        "fips": [
            {
                "name": "county",
                "geoLevelDisplay": "050",
                "requires": ["state"],
                "wildcard": ["state"],
                "optionalWithWCFor": "state",
            },
            {
                "name": "county",
                "geoLevelDisplay": "324",
                "requires": ["state", "msa"],
                "wildcard": [],
            },
        ]
    }
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)
    entries = geo_entries("acs5", 2023)
    assert [entry.code for entry in entries] == ["050", "324"]
    assert geo_levels("acs5", 2023)["county"].code == "324"
