"""The model's structured geography intent decides what runs; what the user typed does not.

Every case drives the real resolver with scripted tool calls, and the real `run_ask` chain for the
cases about wording. Nothing here reads a sentence: the inputs are the fields the tool takes.
"""

from __future__ import annotations

from typing import Any

import pytest
from ask_fixtures import _geo_tool, only_dane
from src.geo_level import ResolveGeographyResult, level_name
from src.geo_list import name_token, state_of
from test_execution_isolation import BUILD, FETCH, NEUTRAL, SEARCH, differing, execute, resolve
from test_geography_completeness import STOPPED, _ask, _frame
from test_tracts_in_place import ASK as IN_PLACE
from test_tracts_in_place import resolve as in_place


async def resolved(listing: Any = None, **args: Any) -> ResolveGeographyResult:
    tool = _geo_tool(listing) if listing else _geo_tool()
    message = await tool.ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c1"}
    )
    return message.artifact  # type: ignore[no-any-return]


DANE_TRACTS = {"parents": ["Dane County, WI"], "parent_level": "county", "level": "tract"}


async def test_a_listing_is_executed_from_its_fields_with_no_listing_words_anywhere() -> None:
    hit = await resolved(only_dane, **DANE_TRACTS)
    assert hit.legal and hit.wildcard
    assert (hit.specs[0].for_spec, hit.specs[0].in_spec) == ("tract:*", "state:55 county:025")


async def test_a_changed_parent_level_changes_the_listing_it_resolves() -> None:
    hit = await resolved(only_dane, parents=["Dane County, WI"], level="tract")
    assert not hit.legal and hit.specs == []  # a county is not a state; nothing is guessed
    assert "send parent_level" in hit.detail


@pytest.mark.parametrize(
    ("args", "missing"),
    [
        ({"parents": ["Texas"], "level": None}, "level"),
        ({"places": [], "level": None}, "nation"),
        ({"places": None, "parents": None, "level": None}, "nation"),
    ],
)
async def test_intent_missing_a_field_is_sent_back_for_repair_not_guessed(
    args: dict[str, Any], missing: str
) -> None:
    hit = await resolved(**args)
    assert hit.specs == [] and hit.legal is False and missing in hit.detail
    assert hit.refused is False  # a repair, not a refusal that stands


async def test_the_nation_is_resolved_only_when_the_model_states_it() -> None:
    hit = await resolved(places=[], level="us")
    assert [spec.for_spec for spec in hit.specs] == ["us:1"] and hit.inferred is False


@pytest.mark.parametrize(
    ("entry", "state"),
    [
        ("Washington County, OR", "oregon"),
        ("Kansas City, Missouri", "missouri"),
        ("West Virginia", "west virginia"),
        ("Virginia", "virginia"),
        ("Washington, D.C.", "district of columbia"),
        ("DC", "district of columbia"),
    ],
)
def test_the_state_of_an_entry_is_an_exact_lookup(entry: str, state: str) -> None:
    found = state_of(entry)
    assert found is not None and found[0] == state


@pytest.mark.parametrize(
    "text",
    [
        "population of Texas",
        "all counties in Ohio",
        "Harris County",
        "tract 71",
        "Cook County, 2022",
    ],
)
def test_a_sentence_or_an_unnamed_state_names_no_state(text: str) -> None:
    assert state_of(text) is None  # nothing is found by scanning words


def test_the_name_of_an_entry_is_the_part_before_its_first_comma() -> None:
    assert name_token("Harris County, TX") == "harris county"
    assert name_token("Kansas City, Missouri") == "kansas city"


LISTING = [
    SEARCH,
    resolve(parents=["Harris County, TX"], parent_level="county", level="tract"),
    BUILD,
    FETCH,
]
REWORDED = [
    *NEUTRAL,
    "give me the tracts for Harris County",
    "pop. by neighborhood unit, Houston area",
]


async def test_a_fixed_listing_executes_identically_under_any_wording() -> None:
    assert await differing(LISTING, REWORDED) == []
    assert "for=tract" in (await execute(NEUTRAL[0], LISTING))["urls"][0]


async def test_changing_the_listing_level_changes_execution_under_the_same_wording() -> None:
    blocks = [
        *LISTING[:1],
        resolve(parents=["Harris County, TX"], parent_level="county", level="county"),
        *LISTING[2:],
    ]
    tracts = await execute(NEUTRAL[0], LISTING)
    other = await execute(NEUTRAL[0], blocks)
    assert tracts["urls"] != other["urls"]


async def test_a_famous_place_named_without_its_state_is_not_refused() -> None:
    """People write "Los Angeles", not "Los Angeles, CA": the lookup finds the state."""
    response, record, fetched = await _ask(
        "Population by tract in Los Angeles", _frame("tract", ["Los Angeles"])
    )
    assert record.timings and STOPPED not in response.answer


@pytest.mark.parametrize("code", ["tract 71", "tract 4821", "71"])
async def test_a_number_filed_under_named_is_a_code_that_must_ground_itself(code: str) -> None:
    response, record, fetched = await _ask("Population by tract", _frame("tract", [code]))
    assert STOPPED in response.answer and record.timings == [] and fetched == []


async def test_a_code_with_its_own_label_grounds_the_state() -> None:
    _response, record, _fetched = await _ask("Population by tract", _frame("tract", ["FIPS 39049"]))
    assert record.timings
    assert state_of("FIPS 39049") == ("ohio", "39")
    assert state_of("state 21") == ("kentucky", "21") and state_of("60614") is None


async def test_a_place_parent_named_without_its_state_is_found_by_name_across_states() -> None:
    tracts = await in_place({**IN_PLACE, "parents": ["Detroit"]})
    assert (
        tracts.legal and tracts.wider
    )  # Detroit, Michigan: the largest match, not a guess at a state
    assert tracts.specs[0].in_spec == "state:26 county:163"  # other Detroits stay as alternatives


async def test_a_county_parent_named_without_its_state_is_found_by_name_across_states() -> None:
    tracts = await resolved(parents=["Wayne County"], parent_level="county", level="tract")
    assert tracts.legal and tracts.specs[0].in_spec == "state:26 county:163"
    assert [spec.name for spec in tracts.specs[1:]] == ["Wayne County, North Carolina"]


async def test_a_nationwide_listing_is_run_only_when_parent_level_is_us() -> None:
    counties = await resolved(level="county", parent_level="us")
    assert counties.legal and counties.wildcard
    assert (counties.specs[0].for_spec, counties.specs[0].in_spec) == ("county:*", "state:*")
    tracts = await resolved(level="tract", parent_level="us")  # published nowhere: a candidate
    assert not tracts.legal and tracts.specs[0].for_spec == "tract:*"
    assert (await resolved(level="county")).specs == []  # no parent_level, no parents: a repair


async def test_a_city_written_with_its_state_is_the_city_not_the_state_it_shares_a_name_with() -> (
    None
):
    city = await resolved(places=["New York, NY"], level=None)
    state = await resolved(places=["New York"], level=None)
    assert city.specs and city.specs[0].level != "state"
    assert [spec.level for spec in state.specs] == [
        "state"
    ]  # a bare name with no level is the state


async def test_a_blank_level_is_no_level_everywhere() -> None:
    blank = await resolved(places=["Cook County, IL"], level=" ")
    none = await resolved(places=["Cook County, IL"], level=None)
    assert blank.specs and [s.for_spec for s in blank.specs] == [s.for_spec for s in none.specs]
    assert blank.inferred is none.inferred is True  # the county fallback is flagged either way


@pytest.mark.parametrize("sent", [{"places": ["Chicago, IL"]}, {"levels": ["county", "county"]}])
async def test_a_listing_mixed_with_places_or_levels_is_refused_for_repair(
    sent: dict[str, Any],
) -> None:
    hit = await resolved(parents=["Texas", "Louisiana"], level="county", **sent)
    assert hit.specs == [] and hit.legal is False and "parents" in hit.detail
    assert hit.refused is False


async def test_several_unplaced_county_parents_are_asked_for_with_their_states() -> None:
    args = {"parent_level": "county", "level": "tract"}
    bare = await resolved(parents=["Wayne County", "Harris County"], **args)
    assert bare.specs == [] and "with its state" in bare.detail
    placed = await resolved(parents=["Wayne County, MI", "Harris County, TX"], **args)
    assert placed.legal and placed.compare


@pytest.mark.parametrize(
    ("spelled", "published"),
    [("census tract", "tract"), ("Census Block Groups", "block group"), ("ZIP codes", "zcta")],
)
def test_the_spellings_a_model_gives_a_level_are_normalised(spelled: str, published: str) -> None:
    assert level_name(spelled) == level_name(published)


async def test_a_level_spelled_census_tract_still_needs_its_state() -> None:
    response, record, fetched = await _ask("Population by census tract", _frame("census tract", []))
    assert STOPPED in response.answer and record.timings == [] and fetched == []


async def test_a_question_about_the_nation_resolves_when_the_model_reports_the_nation() -> None:
    response, record, _fetched = await _ask("Total population of the country", _frame("us", []))
    assert [g.for_spec for g in record.geographies] == ["us:1"]
    assert response.urls and "for=us" in response.urls[0]
