"""A comparison leg runs at the level the model stated for it, not the level its words suggest."""

from __future__ import annotations

from ask_fixtures import _geo_tool


async def test_a_leg_is_not_resolved_at_a_level_other_than_the_one_stated() -> None:
    # Harris County names a county, but the model stated place for it: the code runs place, finds
    # no such place, and does not quietly fetch the county.
    args = {
        "level": None,
        "places": ["Austin, Texas", "Harris County, Texas"],
        "levels": ["place", "place"],
    }
    result = await _geo_tool().ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c1"}
    )
    artifact = result.artifact
    assert {spec.level for spec in artifact.specs} == {"place"}
    assert artifact.compare is False
