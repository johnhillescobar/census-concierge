"""Shared fakes for ask-loop and guard tests.

Not a package — `api/tests/` has no `__init__.py`, so pytest's prepend import mode
puts this directory on `sys.path` and `from ask_fixtures import ...` resolves.
The type checker will not treat `test_*.py` files as importable modules; keep
shared helpers here instead, same pattern as `docs_helpers.py`.
"""

from __future__ import annotations

from typing import Any

from src.ask import ExecutionRecord
from src.fetch import FetchDataTool
from src.geo import ResolveGeographyTool
from src.retrieval.metadata import GeoLevel
from src.tools import BuildUrlTool, SearchTablesTool

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
            "population": "4731145",
        },
        {
            "name": "Harrison County, Texas",
            "level": "county",
            "for": "county:203",
            "in": "state:48",
            "geoid": "0500000US48203",
            "population": "69091",
        },
        {
            "name": "Cook County, Georgia",
            "level": "county",
            "for": "county:075",
            "in": "state:13",
            "geoid": "0500000US13075",
            "population": "17532",
        },
        {
            "name": "Cook County, Illinois",
            "level": "county",
            "for": "county:031",
            "in": "state:17",
            "geoid": "0500000US17031",
            "population": "5182090",
        },
        {
            "name": "Cook County, Minnesota",
            "level": "county",
            "for": "county:031",
            "in": "state:27",
            "geoid": "0500000US27031",
            "population": "5635",
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
                "population": "8336817",
            },
            {
                "name": "Albany city, New York",
                "level": "place",
                "for": "place:3601000",
                "in": "state:36",
                "geoid": "1600000US3601000",
                "population": "99224",
            },
            {
                "name": "Austin city, Texas",
                "level": "place",
                "for": "place:4805000",
                "in": "state:48",
                "geoid": "1600000US4805000",
                "population": "974447",
            },
            {
                "name": "Portland city, Maine",
                "level": "place",
                "for": "place:60545",
                "in": "state:23",
                "geoid": "1600000US2360545",
                "population": "68854",
            },
            {
                "name": "Portland city, Oregon",
                "level": "place",
                "for": "place:59000",
                "in": "state:41",
                "geoid": "1600000US4159000",
                "population": "641165",
            },
            {
                "name": "Springfield CDP, Virginia",
                "level": "place",
                "for": "place:75344",
                "in": "state:51",
                "geoid": "1600000US5175344",
                "population": "31882",
            },
            {
                "name": "Springfield city, Illinois",
                "level": "place",
                "for": "place:72000",
                "in": "state:17",
                "geoid": "1600000US1772000",
                "population": "114394",
            },
            {
                "name": "Springfield city, Missouri",
                "level": "place",
                "for": "place:70000",
                "in": "state:29",
                "geoid": "1600000US2970000",
                "population": "169954",
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


def _tools(record: ExecutionRecord) -> dict[str, Any]:
    facts = {"acs5": {2024: {"B01003": {"universe": "Total population", "variables": ["001E"]}}}}
    return {
        "search_tables": SearchTablesTool(search=_search, describe=_describe),
        "resolve_geography": ResolveGeographyTool(
            list_geographies=_list_geographies, entries=ENTRIES
        ),
        "build_url": BuildUrlTool(
            allowed_tables=lambda: (
                {hit["table_id"] for hit in record.pool}
                | {member for hit in record.pool for member in hit.get("members") or []}
            ),
            latest_vintage=lambda dataset: 2024,
            table_facts=lambda dataset, year, table_id: (
                facts.get(dataset, {}).get(year, {}).get(table_id)
            ),
            last_geography=lambda: record.geography,
            allowed_geographies=lambda: {
                (str(geo.get("for") or ""), str(geo.get("in") or "")) for geo in record.geographies
            },
        ),
        "fetch_data": FetchDataTool(
            last_url=lambda: record.url,
            census_key=lambda: "secret",
            http_get=lambda url: (
                200,
                [
                    ["NAME", "B01003_001E", "B01003_001M", "GEO_ID", "state", "county"],
                    ["Harris County, Texas", "4838303", "123", "0500000US48201", "48", "201"],
                ],
            ),
        ),
    }
