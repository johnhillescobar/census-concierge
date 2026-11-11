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
from src.finish import finish_tools
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
        ResolveGeographyInput(places=["Texas"])
    assert ResolveGeographyInput(places=["Texas"], level=None).level is None


async def test_a_call_that_omits_the_level_is_refused_for_repair_and_is_bounded() -> None:
    record = ExecutionRecord()
    geo = _tools(record)["resolve_geography"]
    refused = await dispatch(geo, {"id": "1", "args": {"places": ["Harris County, TX"]}}, record)
    assert refused.startswith("resolve_geography failed")
    assert record.geographies == [] and record.asked_levels == []
    with pytest.raises(RuntimeError, match="failed twice"):
        await dispatch(geo, {"id": "2", "args": {"places": ["Harris County, TX"]}}, record)


async def test_a_repair_call_never_overwrites_the_level_the_model_stated() -> None:
    record = ExecutionRecord()
    geo = _tools(record)["resolve_geography"]
    await dispatch(
        geo, {"id": "1", "args": {"level": "county", "places": ["Harris County, TX"]}}, record
    )
    assert record.asked_levels == ["county"]
    # a repair call that DOES resolve something, at another level: it must not become the stated one
    repair = {"id": "2", "origin": "repair", "args": {"level": "place", "places": ["Austin, TX"]}}
    await dispatch(geo, repair, record)
    assert [g.level for g in record.geographies] == ["place"]
    assert record.asked_levels == ["county"]


def test_declared_levels_follow_the_legs_the_call_resolves() -> None:
    legs = ["Austin, Texas", "Texas"]
    assert declared_levels({"level": "county", "places": ["x"]}) == ["county"]
    assert declared_levels({"level": None, "places": ["x"]}) == [None]
    assert declared_levels({"places": legs, "levels": ["Place", "state"]}) == ["place", "state"]
    assert declared_levels({"places": legs, "level": "tract"}) == ["tract", "tract"]
    assert declared_levels({"places": legs, "level": "place", "levels": ["place"]}) == ["place"] * 2


def test_only_a_resolve_call_that_states_a_level_records_one() -> None:
    record = ExecutionRecord()
    note_intent(record, "resolve_geography", {"args": {"places": ["x"]}})
    note_intent(record, "build_url", {"args": {"level": "county"}})
    assert record.asked_levels == []


# --- execution: the stated level is the level run ----------------------------------------------


async def test_the_stated_level_is_run_even_when_the_query_names_another() -> None:
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": "place", "places": ["Cook County, IL"]},
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
            "args": {"level": None, "places": ["Cook County, IL"]},
            "id": "c1",
        }
    )
    assert result.artifact.inferred is True


async def test_an_unpublished_level_is_refused_with_the_published_names() -> None:
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": "congressional district", "places": ["Texas"]},
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
            "args": {"level": "Urban Area", "places": ["Denver"]},
            "id": "c1",
        }
    )
    assert [spec.for_spec for spec in result.artifact.specs] == ["urban area:23527"]


async def test_each_comparison_leg_is_run_at_its_own_stated_level() -> None:
    """Without the stated levels each leg's level would be unstated, so the result would be marked
    inferred; with them it is not."""
    args = {
        "level": None,
        "places": ["Harris County, Texas", "Houston, Texas"],
        "levels": ["county", "place"],
    }
    result = await _geo_tool().ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c1"}
    )
    artifact = result.artifact
    assert artifact.compare is True and artifact.inferred is False
    assert [spec.level for spec in artifact.specs[:2]] == ["county", "place"]


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
        ("resolve_geography", {"level": "county", "places": ["Harris County, Texas"]}),
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
        ("resolve_geography", {"level": "congressional district", "places": ["Texas"]}),
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
            "args": {"level": "county", "places": ["Harris County, Texas"]},
            "id": "c1",
        }
    )
    assert result.artifact.refused is False


async def test_a_call_that_names_no_place_and_no_level_resolves_nothing() -> None:
    """With neither a place nor a level the code does not choose the United States for the model."""
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": None, "places": []},
            "id": "c1",
        }
    )
    assert result.artifact.legal is False and result.artifact.specs == []
    assert result.artifact.inferred is False


async def test_a_stated_level_is_run_for_the_place_named_and_is_not_inferred() -> None:
    result = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": "state", "places": ["Texas"]},
            "id": "c1",
        }
    )
    assert [spec.for_spec for spec in result.artifact.specs] == ["state:48"]
    assert result.artifact.inferred is False


def _plan(*geographies: GeoSpec) -> Any:
    return type("Plan", (), {"geographies": list(geographies)})()


def test_an_override_url_at_a_level_its_own_plan_did_not_name_is_flagged() -> None:
    record = _answered(TRACT_URL, [], override=_plan(_harris()))
    assert _codes(record) == ["geography_level_mismatch"]
    assert "county" in evaluate(record)[0].detail and "tract" in evaluate(record)[0].detail


def test_an_override_url_at_its_plans_level_is_not_flagged() -> None:
    assert _codes(_answered(COUNTY_URL, [], override=_plan(_harris()))) == []


def test_the_models_stated_level_does_not_judge_a_users_plan_edit() -> None:
    """The user moved the plan from tracts to a county on purpose: the model's reading of the
    question's tracts is stale and must not raise a warning against the user's own choice."""
    record = _answered(COUNTY_URL, ["tract"], override=_plan(_harris()))
    assert _codes(record) == []


async def test_a_real_override_run_builds_its_url_at_the_plans_level() -> None:
    from src.contract import ResultPlan

    record = ExecutionRecord()
    plan = ResultPlan.model_validate(
        {"geographies": [{"geoid": "0500000US17031", "for_spec": "x:1", "in_spec": "state:00"}]}
    )
    steps = [
        ("search_tables", {"question": "population"}),
        ("resolve_geography", {"level": "tract", "places": ["Cook County, Illinois"]}),
        ("build_url", {"table_id": "B01003"}),
        ("fetch_data", {}),
    ]
    queue: list[dict[str, Any]] = [
        {"content": "", "tool_calls": [{"id": str(i), "name": n, "args": a}]}
        for i, (n, a) in enumerate(steps)
    ]

    async def complete(messages: list[dict[str, Any]], tools_: list[dict[str, Any]]) -> Any:
        del messages
        return (
            {"content": "{}", "tool_calls": []}
            if not tools_
            else (queue.pop(0) if queue else {"content": "done", "tool_calls": []})
        )

    response = await run_ask(
        "population of Cook County",
        complete=complete,
        tools=_tools(record),
        record=record,
        override=plan,
    )
    assert response.urls and CensusURL(response.urls[0]).for_level() == "county"
    assert "geography_level_mismatch" not in {w.code for w in response.warnings}


async def _scripted_run(question: str, calls: list[tuple[str, dict[str, Any]]]) -> Any:
    record = ExecutionRecord()
    queue: list[dict[str, Any]] = [
        {"content": "", "tool_calls": [{"id": str(i), "name": n, "args": a}]}
        for i, (n, a) in enumerate(calls)
    ]

    async def complete(messages: list[dict[str, Any]], tools_: list[dict[str, Any]]) -> Any:
        del messages
        if not tools_:
            return {"content": "{}", "tool_calls": []}
        return queue.pop(0) if queue else {"content": "done", "tool_calls": []}

    response = await run_ask(question, complete=complete, tools=_tools(record), record=record)
    return record, response


async def test_legs_resolved_one_call_at_a_time_each_keep_their_own_stated_level() -> None:
    record, response = await _scripted_run(
        "population of Harris County, Texas and Houston, Texas",
        [
            ("search_tables", {"question": "population"}),
            ("resolve_geography", {"level": "county", "places": ["Harris County, Texas"]}),
            ("resolve_geography", {"level": "place", "places": ["Houston, Texas"]}),
            ("build_url", {"table_id": "B01003"}),
            ("fetch_data", {}),
        ],
    )
    assert record.asked_levels == ["county", "place"]
    # finish replays the legs as one call; the county leg must not be run as a place
    assert sorted(spec.level for spec in record.geographies[:2]) == ["county", "place"]
    assert "geography_level_mismatch" not in {w.code for w in response.warnings}


async def test_a_refinement_of_the_same_place_replaces_its_level_not_adds_a_leg() -> None:
    """ "Springfield" then "Springfield, Illinois" is one place asked twice, not two legs."""
    record, _ = await _scripted_run(
        "population of Springfield, Illinois",
        [
            ("search_tables", {"question": "population"}),
            ("resolve_geography", {"level": "place", "places": ["Springfield"]}),
            ("resolve_geography", {"level": "place", "places": ["Springfield, Illinois"]}),
        ],
    )
    assert record.geo_queries == ["Springfield, Illinois"]
    assert record.asked_levels == ["place"]


async def test_a_levels_list_that_does_not_match_the_places_is_refused_for_repair() -> None:
    args = {"level": None, "places": ["Austin, Texas", "Texas"], "levels": ["place"]}
    result = await _geo_tool().ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c1"}
    )
    assert result.artifact.legal is False and result.artifact.specs == []
    assert "pairs with two or more places" in result.artifact.detail


async def test_finish_resolves_no_geography_from_the_question_when_the_model_reported_none() -> (
    None
):
    """The question names a listing, but the model stated no place and no split reported one.
    Finish has nothing to resolve and must not pick a geography from the question's words."""
    record = ExecutionRecord(question="Show every tract in Cook County, Illinois")
    record.asked_levels = [None]
    geo = _tools(record)["resolve_geography"]
    await finish_tools(dispatch, {"resolve_geography": geo}, record)
    assert record.geographies == [] and record.geo_status is None


async def test_a_refused_level_is_not_followed_by_the_nationwide_fallback() -> None:
    record = ExecutionRecord(question="households and families in Texas")
    record.geo_status = {"legal": False, "refused": True}
    calls: list[dict[str, Any]] = []

    async def fake_dispatch(tool: Any, call: dict[str, Any], rec: Any) -> str:
        calls.append(call)
        return ""

    await finish_tools(fake_dispatch, {"resolve_geography": object()}, record)
    assert calls == []


async def test_a_call_that_finds_nothing_does_not_shift_the_legs_stated_levels() -> None:
    record, response = await _scripted_run(
        "population of Harris County, Texas and Houston, Texas",
        [
            ("search_tables", {"question": "population"}),
            ("resolve_geography", {"level": "county", "places": ["Harris County, Texas"]}),
            ("resolve_geography", {"level": "place", "places": ["Nowheresville, Texas"]}),
            ("resolve_geography", {"level": "place", "places": ["Houston, Texas"]}),
            ("build_url", {"table_id": "B01003"}),
            ("fetch_data", {}),
        ],
    )
    assert record.asked_levels == ["county", "place"]
    assert sorted(spec.level for spec in record.geographies[:2]) == ["county", "place"]


async def test_a_refused_call_between_legs_does_not_shift_the_legs_stated_levels() -> None:
    record, _ = await _scripted_run(
        "population of Harris County, Texas and Houston, Texas",
        [
            ("search_tables", {"question": "population"}),
            ("resolve_geography", {"level": "county", "places": ["Harris County, Texas"]}),
            ("resolve_geography", {"level": "city proper", "places": ["Houston, Texas"]}),
            ("resolve_geography", {"level": "place", "places": ["Houston, Texas"]}),
            ("build_url", {"table_id": "B01003"}),
            ("fetch_data", {}),
        ],
    )
    assert record.asked_levels == ["county", "place"]


async def test_a_level_the_code_chose_is_marked_inferred_in_every_result_shape() -> None:
    async def resolved(args: dict[str, Any]) -> Any:
        message = await _geo_tool().ainvoke(
            {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c1"}
        )
        return message.artifact

    comparison = await resolved(
        {"level": None, "places": ["Harris County, Texas", "Cook County, Illinois"]}
    )
    assert comparison.compare is True and comparison.inferred is True
    assert (await resolved({"level": None, "places": ["Cook County, Illinois"]})).inferred is True
    stated = await resolved({"level": "county", "places": ["Cook County, Illinois"]})
    assert stated.inferred is False


async def test_levels_beside_a_single_place_are_refused_for_repair() -> None:
    args = {"level": None, "places": ["Harris County, Texas"], "levels": ["county"]}
    result = await _geo_tool().ainvoke(
        {"type": "tool_call", "name": "resolve_geography", "args": args, "id": "c1"}
    )
    assert (
        result.artifact.legal is False and "pairs with two or more places" in result.artifact.detail
    )


def test_a_stated_level_with_no_url_of_its_own_is_flagged() -> None:
    record = _answered(COUNTY_URL, ["county", "place"])
    codes = _codes(record)
    assert codes == ["geography_level_mismatch"]
    assert "no URL fetches place" in evaluate(record)[0].detail


def test_the_mismatch_message_names_a_missing_stated_level_plainly() -> None:
    record = _answered(COUNTY_URL, [None], geographies=[])
    detail = evaluate(record)[0].detail
    assert "no stated level" in detail and "county" in detail


async def test_a_level_asked_for_and_not_served_cannot_be_swapped_for_place_without_a_flag() -> (
    None
):
    """The model asked for tracts, the lookup could not serve them (a tract needs its county),
    and the model then answered at place. A place is the right answer only when a place was
    asked for: the response must say the tract request went unserved."""
    record, response = await _scripted_run(
        "tract-level population in Austin, Texas",
        [
            ("search_tables", {"question": "population"}),
            ("resolve_geography", {"level": "tract", "places": ["Austin, Texas"]}),
            ("resolve_geography", {"level": "place", "places": ["Austin, Texas"]}),
            ("build_url", {"table_id": "B01003"}),
            ("fetch_data", {}),
        ],
    )
    assert record.unmet_levels == {"tract"}
    assert response.urls and CensusURL(response.urls[0]).for_level() == "place"
    flag = [w for w in response.warnings if w.code == "geography_level_mismatch"]
    assert flag and "no URL fetches tract" in flag[0].detail


async def test_an_unserved_level_is_cleared_once_a_later_call_serves_it() -> None:
    record = ExecutionRecord()
    geo = _tools(record)["resolve_geography"]
    unserved = {"id": "1", "args": {"level": "tract", "places": ["Cook County, Illinois"]}}
    await dispatch(geo, unserved, record)
    assert record.unmet_levels == {"tract"}
    listing = {"level": "tract", "parents": ["Cook County, Illinois"], "parent_level": "county"}
    await dispatch(geo, {"id": "2", "args": listing}, record)
    assert record.unmet_levels == set()


async def test_a_refused_level_followed_by_a_place_lookup_is_flagged_not_swapped_silently() -> None:
    """Seen live: the model stated a metro level, the lookup refused it, the model then fetched the
    city. Refusing the level does not end the request: the URL must say it answers another level."""
    record, response = await _flow(
        [
            ("resolve_geography", {"level": "congressional district", "places": ["Texas"]}),
            ("resolve_geography", {"level": "place", "places": ["Austin, Texas"]}),
        ]
    )
    assert record.unmet_levels == {"congressional district"}
    assert CensusURL(response.urls[0]).for_level() == "place"
    flag = [w for w in response.warnings if w.code == "geography_level_mismatch"]
    assert flag and "no URL fetches congressional district" in flag[0].detail


async def _flow(geo_steps: list[tuple[str, dict[str, Any]]]) -> tuple[ExecutionRecord, Any]:
    """A scripted ask: search, the given geography calls, then build and fetch."""
    record = ExecutionRecord()
    steps = [
        ("search_tables", {"question": "population"}),
        *geo_steps,
        ("build_url", {"table_id": "B01003"}),
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

    response = await run_ask("population", complete=complete, tools=_tools(record), record=record)
    return record, response


async def test_a_lookup_that_matched_nothing_leaves_the_stated_level_unmet() -> None:
    """A legal lookup with no NAME match resolves nothing. Its level must not vanish, or the next
    lookup at another level returns with no mismatch warning."""
    record, response = await _flow(
        [
            ("resolve_geography", {"level": "place", "places": ["Zzyzx, Texas"]}),
            ("resolve_geography", {"level": "county", "places": ["Harris County, Texas"]}),
        ]
    )
    assert CensusURL(response.urls[0]).for_level() == "county"
    assert record.unmet_levels == {"place"}
    flag = [w for w in response.warnings if w.code == "geography_level_mismatch"]
    assert flag and "no URL fetches place" in flag[0].detail


async def test_an_unserved_candidate_does_not_overwrite_an_earlier_legs_level() -> None:
    record = ExecutionRecord()
    geo = _tools(record)["resolve_geography"]
    place = {"level": "place", "places": ["Austin, Texas"]}
    await dispatch(geo, {"id": "1", "args": place}, record)
    await dispatch(geo, {"id": "2", "args": {"level": "tract", "places": ["Texas"]}}, record)
    assert record.asked_levels == ["place"] and record.unmet_levels == {"tract"}


async def test_a_partial_comparison_keeps_every_stated_level_unmet() -> None:
    record = ExecutionRecord()
    geo = _tools(record)["resolve_geography"]
    args = {
        "level": None,
        "places": ["Austin, Texas", "Zzyzx, Texas"],
        "levels": ["place", "county"],
    }
    await dispatch(geo, {"id": "1", "args": args}, record)
    assert record.unmet_levels == {"place", "county"} and record.asked_levels == []


async def test_malformed_level_arguments_do_not_crash_the_failure_handler() -> None:
    """Schema validation fails, and the handler reads the original arguments. Reading them must not
    raise (a non-string level, a non-list places, a non-string entry in levels)."""
    for args in (
        {"level": 42, "places": ["Austin, Texas"]},
        {"level": "place", "places": 42},
        {"level": None, "places": ["a", "b"], "levels": ["place", 3]},
    ):
        record = ExecutionRecord()  # two failures in a row stop the tool: one record per call
        geo = _tools(record)["resolve_geography"]
        reply = await dispatch(geo, {"id": "1", "args": args}, record)
        assert reply.startswith("resolve_geography failed")
    assert declared_levels({"level": 42, "places": 42, "levels": ["place", 3]}) == ["place", None]
    assert declared_levels({"level": 42}) == [None]


def test_an_unserved_level_not_covered_by_the_url_is_flagged_and_a_covered_one_is_not() -> None:
    assert _codes(_answered(COUNTY_URL, ["county"], unmet_levels={"tract"})) == [
        "geography_level_mismatch"
    ]
    assert _codes(_answered(TRACT_URL, ["tract"], unmet_levels={"tract"})) == []
    # fetching a level the model stated but could not be served is not a swap to another level
    assert _codes(_answered(TRACT_URL, [], unmet_levels={"tract"})) == []


async def test_an_unsupported_candidate_is_not_a_comparison_leg() -> None:
    """A place lookup followed by a tract listing the API cannot serve (it returns a candidate with
    legal False) is not a comparison of two places. If finish counted it as one it would replay it
    and replace the model's own URL with the place."""
    record = ExecutionRecord()
    geo = _tools(record)["resolve_geography"]
    place = {"level": "place", "places": ["Austin, Texas"]}
    await dispatch(geo, {"id": "1", "args": place}, record)
    assert record.geo_queries == ["Austin, Texas"]
    listing = {"level": "tract", "parents": ["Texas"]}
    await dispatch(geo, {"id": "2", "args": listing}, record)
    assert record.geo_status is not None and record.geo_status["legal"] is False
    assert [g.level for g in record.geographies] == ["tract"]  # the candidate the model may build
    assert len(record.geo_queries) < 2  # one place at most: finish sees no comparison to replay


def test_a_stated_level_not_served_is_flagged_even_when_nothing_else_was_stated() -> None:
    record = _answered(COUNTY_URL, [], unmet_levels={"tract"})
    assert _codes(record) == ["geography_level_mismatch"]
    assert "never stated" not in evaluate(record)[0].detail


async def test_a_wildcard_listing_for_several_parents_is_a_comparison_at_the_stated_level() -> None:
    message = await _geo_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "resolve_geography",
            "args": {"level": "county", "parents": ["Texas", "Louisiana"]},
            "id": "c1",
        }
    )
    assert message.artifact.compare is True and message.artifact.inferred is False
    assert [spec.level for spec in message.artifact.specs] == ["county", "county"]
