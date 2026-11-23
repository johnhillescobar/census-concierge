"""A golden that names a shared place without its state measures the product's refusal, not its
retrieval. The checker must fail that golden, pass one that carries its state, and prove an edit
changed nothing but the state. Real golden file, real `filter_rows`; only the listings are fixtures
(the live run against Census is the evidence)."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_golden_places as vg  # noqa: E402

COUNTY = [
    {"name": "Cook County, Illinois"},
    {"name": "Cook County, Georgia"},
    {"name": "Maricopa County, Arizona"},
]
PLACE = [
    {"name": "Portland city, Oregon"},
    {"name": "Portland city, Maine"},
    {
        "name": "East Portland CDP, Oregon"
    },  # matches by word, not by name: still counts for the rule
    {"name": "Somerville city, Massachusetts"},
    {"name": "Somerville city, Texas"},
    {"name": "Ann Arbor city, Michigan"},
]
LISTINGS = {"county": COUNTY, "place": PLACE}


def listing(level: str) -> list[dict[str, str]]:
    return LISTINGS[level]


def golden(gid: str, text: str, **fields: Any) -> dict[str, Any]:
    return {"id": gid, "text": text, "expect_table": "B01003", "tier": "core", **fields}


def check(
    monkeypatch: pytest.MonkeyPatch,
    places: dict[str, list[vg.Place]],
    goldens: list[dict[str, Any]],
    exempt: dict[str, str] | None = None,
) -> list[str]:
    monkeypatch.setattr(vg, "PLACES", places)
    monkeypatch.setattr(vg, "EXEMPT", exempt or {})
    return vg.place_problems(goldens, listing)


def test_a_shared_place_with_no_state_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    problems = check(
        monkeypatch,
        {"a": [("Cook County", "county", None)]},
        [golden("a", "Educational attainment in Cook County")],
    )
    assert len(problems) == 1 and problems[0].startswith("a:") and "writes no state" in problems[0]


def test_a_shared_place_that_writes_its_state_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Educational attainment in Cook County, Illinois"
    assert (
        check(monkeypatch, {"a": [("Cook County", "county", "Illinois")]}, [golden("a", text)])
        == []
    )


def test_a_usps_code_counts_as_the_state(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Housing units in Somerville MA"
    assert (
        check(monkeypatch, {"a": [("Somerville", "place", "Massachusetts")]}, [golden("a", text)])
        == []
    )


def test_a_place_that_matches_one_place_needs_no_state(monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        check(monkeypatch, {"a": [("Ann Arbor", "place", None)]}, [golden("a", "Ann Arbor study")])
        == []
    )


def test_a_stated_state_the_question_does_not_carry_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    problems = check(
        monkeypatch,
        {"a": [("Cook County", "county", "Illinois")]},
        [golden("a", "Educational attainment in Cook County")],
    )
    assert any("not in the question" in p for p in problems)


def test_a_state_that_does_not_hold_the_place_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    problems = check(
        monkeypatch,
        {"a": [("Cook County", "county", "Texas")]},
        [golden("a", "Educational attainment in Cook County, Texas")],
    )
    assert any("no county 'Cook County' in Texas" in p for p in problems)


def test_a_name_that_matches_nothing_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    problems = check(
        monkeypatch, {"a": [("Atlantis", "place", None)]}, [golden("a", "People in Atlantis")]
    )
    assert any("matches no place" in p for p in problems)


def test_a_golden_nobody_annotated_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    problems = check(monkeypatch, {}, [golden("a", "Population of the nation")])
    assert problems == ["a: no place annotation (add [] if it names no place)"]


def test_an_annotation_for_a_golden_that_is_gone_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    problems = check(monkeypatch, {"a": [], "gone": []}, [golden("a", "Population of the nation")])
    assert problems == ["gone: annotated but not in the golden file"]


def test_a_golden_that_expects_the_refusal_may_stay_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    places: dict[str, list[vg.Place]] = {"t": [("Portland", "place", None)]}
    why = {"t": "expects ambiguous_place"}
    assert check(monkeypatch, places, [golden("t", "Population of Portland")], why) == []


def test_an_exemption_that_is_no_longer_shared_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    places: dict[str, list[vg.Place]] = {"t": [("Ann Arbor", "place", None)]}
    problems = check(monkeypatch, places, [golden("t", "Population of Ann Arbor")], {"t": "x"})
    assert any("exempt, but" in p for p in problems)


def test_an_exemption_without_an_annotation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    problems = check(monkeypatch, {}, [], {"t": "x"})
    assert problems == ["t: exempt but not annotated"]


def test_every_golden_in_the_real_file_is_annotated() -> None:
    entries = tomllib.loads((ROOT / vg.GOLDENS).read_text(encoding="utf-8"))["question"]
    assert {e["id"] for e in entries} == set(vg.PLACES)


def test_every_stated_state_is_in_the_real_question_text() -> None:
    entries = tomllib.loads((ROOT / vg.GOLDENS).read_text(encoding="utf-8"))["question"]
    missing = [
        e["id"]
        for e in entries
        for _name, _level, state in vg.PLACES[e["id"]]
        if state and not vg._carries(e["text"], state)
    ]
    assert missing == []


def test_the_real_file_holds_every_unqualified_exemption_unchanged() -> None:
    entries = {
        e["id"]: e for e in tomllib.loads((ROOT / vg.GOLDENS).read_text("utf-8"))["question"]
    }
    for gid in vg.EXEMPT:
        assert all(state is None for _n, _l, state in vg.PLACES[gid])
        assert entries[gid]["expect_warning"] == "ambiguous_place"


OLD = [golden("a", "Poverty in Cook County"), golden("b", "Population of the nation")]


def edit(**changes: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**g, **changes.get(g["id"], {})} for g in OLD]


def test_an_edit_that_only_adds_the_state_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")], "b": []})
    new = edit(a={"text": "Poverty in Cook County, Illinois"})
    assert vg.diff_problems(OLD, new) == []


def test_an_untouched_file_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {})
    assert vg.diff_problems(OLD, edit()) == []


def test_a_changed_expectation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")], "b": []})
    new = edit(a={"text": "Poverty in Cook County, Illinois", "expect_table": "B17001"})
    assert vg.diff_problems(OLD, new) == ["a: a field other than text changed"]


def test_an_edit_that_adds_more_than_the_state_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")], "b": []})
    new = edit(a={"text": "Poverty in Cook County, Illinois, in 2024"})
    assert any("more than the state" in p for p in vg.diff_problems(OLD, new))


def test_a_rewording_with_no_state_annotation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", None)], "b": []})
    new = edit(a={"text": "Poverty in Cook County, Illinois"})
    assert any("more than the state" in p for p in vg.diff_problems(OLD, new))


def test_a_dropped_or_reordered_golden_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {})
    assert vg.diff_problems(OLD, OLD[:1]) == ["the golden ids or their order changed"]
    assert vg.diff_problems(OLD, OLD[::-1]) == ["the golden ids or their order changed"]
