"""The model's structured geography intent decides what runs; what the user typed does not.

Every case drives the real resolver with scripted tool calls, and the real `run_ask` chain for the
cases about wording. Nothing here reads a sentence: the inputs are the fields the tool takes.
"""

from __future__ import annotations

from typing import Any

import pytest
from ask_fixtures import _geo_tool, only_dane
from src.geo_level import ResolveGeographyResult, level_name
from src.geo_list import DOMINANCE, dominant, fips_state, name_token, state_of
from test_execution_isolation import BUILD, FETCH, NEUTRAL, SEARCH, differing, execute, resolve
from test_geography_completeness import STOPPED, _ask, _frame, _run
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


async def test_a_level_nothing_publishes_is_refused_not_read_as_another() -> None:
    hit = await resolved(places=["Harris County, TX"], level="neighbourhood")
    assert hit.specs == [] and hit.legal is False and hit.refused is True


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


def test_only_a_state_code_makes_a_code_a_state() -> None:
    assert state_of("state 21") == ("kentucky", "21")
    assert state_of("geoid 06037") is None  # a county code is not a state
    assert state_of("fips 39049") is None
    assert state_of("zip 21234") is None  # a label that is not a state's own
    assert state_of("state 2112") is None  # "state" takes the two digits of a state, no more
    assert state_of("21234") is None


def test_a_labelled_fips_or_geoid_code_grounds_only_the_state_it_lies_in() -> None:
    assert fips_state("GEOID 06037") == ("california", "06")
    assert fips_state("FIPS 39049") == ("ohio", "39")
    assert fips_state("fips 3904") is None  # not the length of any FIPS code
    assert fips_state("zip 60614") is None and fips_state("fips 99999") is None


async def test_a_county_code_asked_for_with_no_level_is_not_answered_as_its_state() -> None:
    hit = await resolved(places=["FIPS 39049"], level=None)
    assert [spec.level for spec in hit.specs] != ["state"]


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
    assert record.timings  # the code grounds the state it lies in, for completeness only


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
    [
        ("census tract", "tract"),
        ("census tracts", "tract"),
        ("Census Block Groups", "block group"),
        ("census block group", "block group"),
        ("ZIP codes", "zcta"),
        ("zip code", "zcta"),
        ("ZCTA5", "zcta"),
    ],
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


async def test_places_that_only_repeat_the_parents_are_redundant_not_a_second_request() -> None:
    same = await resolved(
        parents=["Texas", "Louisiana"], places=["texas", "Louisiana"], level="county"
    )
    assert same.legal and same.compare and len(same.specs) == 2


async def test_a_numbered_unit_the_model_writes_with_its_number_still_needs_its_parents() -> None:
    for written in (["tract 12"], ["Tract 12"], ["block group 4"]):
        level = "block group" if "block" in written[0] else "tract"
        frame = _frame(level, ["Kentucky"], written)  # the state is named: the county is what lacks
        response, record, fetched = await _ask("Poverty in tract 12 in Kentucky", frame)
        assert STOPPED in response.answer and record.timings == [] and fetched == []


async def test_a_labelled_zip_code_is_the_code_and_not_a_nationwide_search() -> None:
    calls: list[str] = []

    def listing(level: str, parts: dict[str, str], **kw: Any) -> list[dict[str, str]]:
        calls.append(level)
        return []

    hit = await resolved(listing, places=["ZCTA5 90210"], level="zcta")
    assert hit.legal and [s.for_spec for s in hit.specs] == ["zip code tabulation area:90210"]
    assert calls == []  # the code names it: nothing was listed


async def test_a_bare_name_that_is_also_a_state_is_not_taken_for_the_state_as_a_parent() -> None:
    seen: list[dict[str, str]] = []

    def listing(level: str, parts: dict[str, str], **kw: Any) -> list[dict[str, str]]:
        seen.append(parts)
        return []

    await resolved(listing, parents=["Washington"], parent_level="county", level="tract")
    assert seen == [{"state": "*"}]  # a county named Washington, searched everywhere: not state 53


async def test_a_place_named_without_its_state_is_searched_in_every_state() -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    def listing(level: str, parts: dict[str, str], **kw: Any) -> list[dict[str, str]]:
        seen.append((level, parts))
        return []

    await resolved(listing, places=["Springfield"], level="place")
    assert seen == [("place", {"state": "*"})]  # the API takes no place listing without `in`


async def test_a_comparison_that_resolves_no_leg_is_not_looked_up_a_second_time() -> None:
    calls: list[str] = []

    def listing(level: str, parts: dict[str, str], **kw: Any) -> list[dict[str, str]]:
        calls.append(level)
        return []

    hit = await resolved(listing, places=["Nowhere, TX", "Noplace, OH"], level="county")
    assert hit.specs == [] and len(calls) == 2  # one lookup per leg, none repeated


def _row(name: str, state: str, county: str, people: str) -> dict[str, str]:
    return {
        "name": name,
        "level": "county",
        "for": f"county:{county}",
        "in": f"state:{state}",
        "geoid": "",
        "population": people,
    }


ALIKE = [
    _row("Washington County, Ohio", "39", "167", "61000"),
    _row("Washington County, Pennsylvania", "42", "125", "210000"),
]


def alike(level: str, parts: dict[str, str], **kwargs: Any) -> list[dict[str, str]]:
    """Two same-named counties of similar size, listed the way the Census API lists them."""
    state = parts.get("state", "*")
    return [r for r in ALIKE if level == "county" and state in {"*", r["in"].split(":")[1]}]


def test_a_best_match_dominates_only_when_it_is_several_times_the_next() -> None:
    big, small = {"population": str(DOMINANCE * 100)}, {"population": "100"}
    near = {"population": str(DOMINANCE * 100 - 1)}
    assert dominant([big, small]) and dominant([small]) and dominant([])
    assert not dominant([near, small])  # just under the threshold: not known to dominate
    assert not dominant([big, {"name": "no population"}])  # nothing to judge by


async def test_an_unqualified_parent_that_no_match_dominates_returns_candidates_not_a_pick() -> (
    None
):
    hit = await resolved(alike, parents=["Washington County"], parent_level="county", level="tract")
    assert hit.ambiguous and hit.legal and hit.wildcard is False
    assert [s.name for s in hit.specs] == [
        r["name"] for r in reversed(ALIKE)
    ]  # ranked, largest first
    assert "name its state" in hit.detail


async def test_a_parent_with_its_state_is_never_ambiguous() -> None:
    """Two matches inside the one state named are not a reason to hold the listing back."""

    def inside_ohio(level: str, parts: dict[str, str], **kwargs: Any) -> list[dict[str, str]]:
        return [
            _row("Washington County, Ohio", "39", "167", "61000"),
            _row("Fort Washington County, Ohio", "39", "168", "60000"),
        ]

    hit = await resolved(
        inside_ohio, parents=["Washington County, OH"], parent_level="county", level="tract"
    )
    assert hit.legal and hit.wildcard and not hit.ambiguous
    assert hit.specs[0].in_spec == "state:39 county:167"


@pytest.mark.parametrize("model_builds", [True, False])
async def test_an_ambiguous_listing_ships_candidates_and_no_url_to_fetch(
    model_builds: bool,
) -> None:
    question = "Poverty by tract in Washington County"
    steps = [
        ("search_tables", {"question": question}),
        (
            "resolve_geography",
            {"parents": ["Washington County"], "parent_level": "county", "level": "tract"},
        ),
    ]
    if model_builds:  # the model builds and fetches itself, or stops and finish would
        steps += [("build_url", {"table_id": "B17001"}), ("fetch_data", {})]
    response, record, fetched, _calls = await _run(
        question, _frame("tract", ["Washington County"]), steps=steps, listing=alike
    )
    assert response.urls == [] and fetched == [] and record.geography is None
    ambiguous = [w for w in response.warnings if w.code == "ambiguous_place"]
    assert len(ambiguous) == 1 and len(ambiguous[0].candidates) == 2


async def test_tracts_in_an_ambiguous_place_return_candidates_not_the_largest() -> None:
    from test_tracts_in_place import WITH_STEP, listing

    def places(level: str, parts: dict[str, str], **kwargs: Any) -> list[dict[str, str]]:
        if level != "place":
            return listing(level, parts, **kwargs)
        return [
            {
                **_row(f"Springfield city, {state}", fips, "000", people),
                "level": "place",
                "for": f"place:{code}",
            }
            for state, fips, code, people in [
                ("Illinois", "17", "72000", "114000"),
                ("Missouri", "29", "70000", "169000"),
            ]
        ]

    hit = (
        await _geo_tool(listing=places, table=WITH_STEP).ainvoke(
            {
                "type": "tool_call",
                "name": "resolve_geography",
                "args": {"parents": ["Springfield"], "parent_level": "place", "level": "tract"},
                "id": "c1",
            }
        )
    ).artifact
    assert hit.ambiguous and len(hit.specs) == 2 and "name its state" in hit.detail


async def test_a_tract_by_number_needs_parents_the_question_states_not_supplied_ones() -> None:
    cook = ["Cook County, Illinois"]
    supplied = _frame("tract", cook, ["tract"], county_named=True, given=["county"])
    response, record, fetched = await _ask("Poverty in tract 12 in Cook County", supplied)
    assert STOPPED in response.answer and "state" in response.answer
    assert record.timings == [] and fetched == []


async def test_a_tract_by_number_runs_when_the_question_states_its_parents() -> None:
    cook = ["Cook County, Illinois"]
    stated = _frame("tract", cook, ["tract"], county_named=True, given=["state", "county"])
    _response, record, _fetched = await _ask("Poverty in tract 12 in Cook County, IL", stated)
    assert record.timings


async def test_a_report_without_given_keeps_the_lenient_rule_rather_than_refusing() -> None:
    cook = ["Cook County, Illinois"]  # a model that sends no `given` at all must not fail closed
    _response, record, _fetched = await _ask(
        "Poverty in tract 12 in Cook County", _frame("tract", cook, ["tract"], county_named=True)
    )
    assert record.timings


@pytest.mark.parametrize("name", ["St. Louis", "Winston-Salem", "San José", "Coeur d'Alene"])
async def test_a_place_name_with_punctuation_or_accents_still_gives_the_state(name: str) -> None:
    """Real names carry periods, hyphens, apostrophes and accents: only a digit makes a code."""
    response, record, _fetched = await _ask(
        f"Population by tract in {name}", _frame("tract", [name])
    )
    assert record.timings and STOPPED not in response.answer


async def test_a_bare_state_name_among_several_parents_is_not_a_parent_with_its_state() -> None:
    args = {"parent_level": "place", "level": "tract"}
    hit = await resolved(alike, parents=["Washington", "Kansas City, MO"], **args)
    assert hit.specs == [] and "with its state" in hit.detail  # "Washington" was never qualified


async def test_tracts_in_a_place_written_with_its_state_take_the_largest_match() -> None:
    from test_tracts_in_place import WITH_STEP, listing

    def places(level: str, parts: dict[str, str], **kwargs: Any) -> list[dict[str, str]]:
        if level != "place":
            return listing(level, parts, **kwargs)
        return [
            {
                **_row("Detroit city, Michigan", "26", "000", "630000"),
                "level": "place",
                "for": "place:22000",
            },
            {
                **_row("Detroit township, Michigan", "26", "000", "500000"),
                "level": "place",
                "for": "place:99999",
            },
        ]

    args = {"parents": ["Detroit, MI"], "parent_level": "place", "level": "tract"}
    tool = _geo_tool(listing=places, table=WITH_STEP)
    hit = (
        await tool.ainvoke(
            {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c"}
        )
    ).artifact
    assert hit.legal and not hit.ambiguous and hit.specs[0].in_spec == "state:26 county:163"


@pytest.mark.parametrize(
    "written", ["Census Block Group 3", "census block groups", "block group 3"]
)
async def test_a_numbered_unit_is_found_wherever_the_model_wrote_its_level(written: str) -> None:
    frame = _frame("block group", ["Kentucky"], [written], given=["state"])
    response, record, fetched = await _ask("Income in block group 3 in Kentucky", frame)
    assert STOPPED in response.answer and record.timings == [] and fetched == []


async def test_given_is_read_however_the_model_cases_or_pads_it() -> None:
    dane = ["Dane County, Wisconsin"]
    frame = _frame("tract", dane, ["tract"], county_named=True, given=["State ", " COUNTY"])
    _response, record, _fetched = await _ask("Poverty in tract 12 in Dane County, WI", frame)
    assert record.timings


async def test_the_nation_level_does_not_swallow_a_named_state() -> None:
    texas = await resolved(places=["Texas"], level="us")
    assert texas.specs == [] and texas.legal is False and "nation" in texas.detail
    nation = await resolved(places=["United States"], level="us")
    assert [spec.for_spec for spec in nation.specs] == ["us:1"]


def test_empty_places_dominate_nothing_and_the_comparison_is_with_the_largest_other() -> None:
    zero = {"population": "0"}
    assert not dominant([zero, zero])
    big, mid, small = {"population": "1000"}, {"population": "900"}, {"population": "10"}
    assert not dominant([big, small, mid])  # the best match is compared with the largest other one
