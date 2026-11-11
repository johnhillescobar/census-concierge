"""Tracts inside a named place, from the counties ACS 5-year says the place lies in.

Census has no tract-inside-place row; the tracts of those counties are the nearest executable
answer. It covers the place and more, so it is flagged `geography_not_nested`, naming the counties.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.contract import GeoSpec, clause_codes
from src.geo_level import ResolveGeographyResult, level_name

COUNTY_PART = "county (or part)"


Reply = tuple[str, ResolveGeographyResult]


async def tracts_in_place(
    tool: Any,
    names: list[str],
    level: str | None,
    dataset: str,
    year: int,
    entries: list[Any],
    ordinary: Reply,
) -> Reply:
    """The ordinary reply, unless it failed and tracts were asked for in one place Census knows.

    The model reads an ordinary success (told "not published" it abandons the tracts, seen live);
    the limitation is the result's detail, which the user sees as the warning.
    """
    step = any(e.name == COUNTY_PART and set(e.requires) == {"state", "place"} for e in entries)
    if ordinary[1].legal or len(names) != 1 or level_name(level) != "tract" or not step:
        return ordinary
    _detail, hit = await tool._place(names[0], "place", dataset, year, entries)
    if not (hit.legal and hit.specs):
        return ordinary
    place, state = hit.specs[0], clause_codes(hit.specs[0].in_spec).get("state", "")
    parts = {"state": state, "place": place.for_spec.split(":")[-1]}
    rows = await asyncio.to_thread(
        tool.list_geographies, COUNTY_PART, parts, dataset=dataset, vintage=year
    )
    specs = [
        GeoSpec(
            level="tract",
            name=f"census tracts in {row['name']}",
            for_spec="tract:*",
            in_spec=f"state:{state} county:{row['for'].split(':')[-1]}",
            dataset=dataset,
            vintage=year,
        )
        for row in rows
    ]
    if not specs:
        return ordinary
    named = "; ".join(row["name"] for row in rows)
    result = ResolveGeographyResult(
        specs=[*specs, *hit.specs[1:]],  # other same-name places stay visible as candidates
        wildcard=True,
        legal=True,  # tract:* in a state and county is an ordinary Census request
        wider=True,
        detail=(
            f"tracts inside a place are not published; showing every tract in the {len(specs)} "
            f"county(ies) {place.name} lies in ({named}). The place boundary is not applied"
        ),
        compare=len(specs) > 1,
        compare_count=len(specs) if len(specs) > 1 else 0,
    )
    return "wildcard " + "; ".join(f"{s.for_spec} {s.in_spec}" for s in specs), result
