"""Four ask tools: search, geography legality, URL construction, fetch.

No live Census or model. Fakes vary by input — a stub that always returns
B01003 would hide a broken search, which is the predecessor's failure.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from src.census_url import CensusURL
from src.geo import (
    ResolveGeographyTool,
    filter_rows,
    find_state,
    legal_predicate,
    list_census_names,
    place_token,
)
from src.retrieval.metadata import GeoLevel, geo_entries, geo_levels
from src.tools import (
    BuildUrlTool,
    FetchDataTool,
    SearchTablesTool,
    pair_margins,
)

ENTRIES = [
    GeoLevel("state", "040", (), (), ""),
    GeoLevel("county", "050", ("state",), ("state",), "state"),
    GeoLevel(
        "county",
        "324",
        (
            "state",
            "metropolitan statistical area/micropolitan statistical area (or part)",
            "metropolitan division (or part)",
        ),
        (),
        "",
    ),
    GeoLevel("place", "160", ("state",), ("state",), "state"),
    GeoLevel("zip code tabulation area", "860", (), (), ""),
]


def _search(question: str, k: int = 10) -> list[str]:
    q = question.casefold()
    if "bike" in q or "bicycle" in q:
        return ["B08301"][:k]
    if "broadband" in q:
        return ["B28002"][:k]
    if "income" in q:
        return ["B19013"][:k]
    if "population" in q:
        return ["B01003"][:k]
    return []


def _describe(table_id: str) -> dict[str, object] | None:
    catalog = {
        "B01003": {"title": "Total Population", "universe": "Total population", "members": []},
        "B08301": {
            "title": "Means of Transportation to Work",
            "universe": "Workers 16 years and over",
            "members": [],
        },
        "B19013": {
            "title": "Median Household Income",
            "universe": "Households",
            "members": ["B19013A", "B19013B"],
        },
        "B28002": {
            "title": "Internet Subscriptions",
            "universe": "Households",
            "members": [],
        },
    }
    return catalog.get(table_id)


def _list_geographies(level: str, in_parts: dict[str, str]) -> list[dict[str, str]]:
    counties = [
        {
            "name": "Harris County, Texas",
            "level": "county",
            "for": "county:201",
            "in": "state:48",
            "geoid": "0500000US48201",
        },
        {
            "name": "Harrison County, Texas",
            "level": "county",
            "for": "county:203",
            "in": "state:48",
            "geoid": "0500000US48203",
        },
        {
            "name": "Cook County, Georgia",
            "level": "county",
            "for": "county:075",
            "in": "state:13",
            "geoid": "0500000US13075",
        },
        {
            "name": "Cook County, Illinois",
            "level": "county",
            "for": "county:031",
            "in": "state:17",
            "geoid": "0500000US17031",
        },
        {
            "name": "Cook County, Minnesota",
            "level": "county",
            "for": "county:031",
            "in": "state:27",
            "geoid": "0500000US27031",
        },
    ]
    if level == "place":
        places = [
            {
                "name": "New York city, New York",
                "level": "place",
                "for": "place:3651000",
                "in": "state:36",
                "geoid": "1600000US3651000",
            },
            {
                "name": "Albany city, New York",
                "level": "place",
                "for": "place:3601000",
                "in": "state:36",
                "geoid": "1600000US3601000",
            },
            {
                "name": "Austin city, Texas",
                "level": "place",
                "for": "place:4805000",
                "in": "state:48",
                "geoid": "1600000US4805000",
            },
        ]
        state = in_parts.get("state")
        if state and state != "*":
            return [row for row in places if row["in"] == f"state:{state}"]
        return places
    if level != "county":
        return []
    state = in_parts.get("state")
    if state and state != "*":
        return [row for row in counties if row["in"] == f"state:{state}"]
    return counties


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
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
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
    assert message.artifact.matches == []


def test_harris_does_not_match_harrison() -> None:
    rows = _list_geographies("county", {"state": "48"})
    hits = filter_rows("harris", rows)
    assert [row["for"] for row in hits] == ["county:201"]


async def test_all_counties_in_oregon_is_one_wildcard_request() -> None:
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
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
    assert artifact.matches == [
        {
            "name": "all counties in Oregon",
            "level": "county",
            "for": "county:*",
            "in": "state:41",
            "geoid": "",
        }
    ]


async def test_cook_county_returns_candidates_instead_of_picking() -> None:
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Cook County"},
            "id": "c1",
        }
    )
    codes = sorted(row["in"] for row in message.artifact.matches)
    assert codes == ["state:13", "state:17", "state:27"]
    assert len(message.artifact.matches) == 3
    assert "Cook County, Illinois" in message.content
    assert "county:031" in message.content
    assert "state:13" in message.content


async def test_harris_county_texas_resolves_to_codes() -> None:
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Harris County, Texas"},
            "id": "c1",
        }
    )
    assert [row["for"] for row in message.artifact.matches] == ["county:201"]
    assert message.artifact.matches[0]["in"] == "state:48"


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
        allowed_geographies=lambda: {("county:201", "state:48")},
        latest_vintage=lambda dataset: 2024,
        table_facts=lambda dataset, year, table_id: (
            facts.get(dataset, {}).get(year, {}).get(table_id)
        ),
        last_geography=lambda: {"for": "county:201", "in": "state:48"},
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
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
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
    assert artifact.matches[0]["for"] == "county:*"
    assert artifact.matches[0]["in"] == "state:*"


async def test_all_places_in_a_county_is_rejected_not_broadened() -> None:
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "all places in Harris County"},
            "id": "c1",
        }
    )
    assert message.artifact.legal is False
    assert message.artifact.matches == []
    assert "unresolved" in message.artifact.detail


async def test_unknown_level_does_not_list_census_names() -> None:
    called: list[tuple[str, dict[str, str]]] = []

    def listing(level: str, parts: dict[str, str]) -> list[dict[str, str]]:
        called.append((level, parts))
        return []

    tool = ResolveGeographyTool(list_geographies=listing, entries=ENTRIES)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Harris County, Texas", "level": "county:*&get=NAME"},
            "id": "c1",
        }
    )
    assert called == []
    assert message.artifact.matches == []
    assert message.artifact.legal is False
    assert "unknown geography level" in message.artifact.detail


async def test_unknown_place_keeps_predicate_legality() -> None:
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "Atlantis, Texas"},
            "id": "c1",
        }
    )
    assert message.artifact.legal is True
    assert message.artifact.matches == []
    assert "no place matched" in message.artifact.detail


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


def test_empty_place_token_matches_nothing() -> None:
    rows = [{"name": "Albany city, New York", "for": "place:1"}]
    assert filter_rows("", rows) == []
    assert filter_rows("new york", rows) == []


@pytest.mark.parametrize("query", ["Washington, DC", "Washington DC", "Washington, D.C."])
async def test_washington_dc_resolves_as_district_of_columbia(query: str) -> None:
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": query},
            "id": "c1",
        }
    )
    assert [row["for"] for row in message.artifact.matches] == ["state:11"]
    assert message.artifact.matches[0]["geoid"] == "0400000US11"


async def test_new_york_city_does_not_return_every_new_york_place() -> None:
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "New York City"},
            "id": "c1",
        }
    )
    assert [row["for"] for row in message.artifact.matches] == ["place:3651000"]


async def test_bare_state_query_resolves_as_the_state() -> None:
    tool = ResolveGeographyTool(list_geographies=_list_geographies, entries=ENTRIES)
    message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"query": "population of Texas"},
            "id": "c1",
        }
    )
    assert [row["for"] for row in message.artifact.matches] == ["state:48"]


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
