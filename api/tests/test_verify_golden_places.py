"""A golden that names a shared place without its state measures the product's refusal, not its
retrieval. The checker must fail that golden, pass one that carries its state, and prove an edit
changed nothing but the state. Real golden file, real `filter_rows`; only the listings are fixtures
(the live run against Census is the evidence)."""

from __future__ import annotations

import subprocess
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
    lists: dict[str, list[dict[str, str]]] | None = None,
) -> list[str]:
    monkeypatch.setattr(vg, "PLACES", places)
    monkeypatch.setattr(vg, "EXEMPT", exempt or {})
    if lists is None:
        return vg.place_problems(goldens, listing)
    return vg.place_problems(goldens, lambda level: lists[level])


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


@pytest.mark.parametrize(
    "text",
    [
        "Illinois attainment in Cook County",  # the state is elsewhere in the question
        "Attainment in cook county, illinois",  # the annotation is the exact written form
        "Attainment in Cook County in Illinois",  # not "<place>, <State>"
    ],
)
def test_the_state_must_follow_the_place_exactly_as_annotated(
    monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    places: dict[str, list[vg.Place]] = {"a": [("Cook County", "county", "Illinois")]}
    problems = check(monkeypatch, places, [golden("a", text)])
    assert any("not in the question after 'Cook County'" in p for p in problems)


def test_an_unknown_state_is_a_problem_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    places: dict[str, list[vg.Place]] = {"a": [("Cook County", "county", "Atlantis")]}
    problems = check(monkeypatch, places, [golden("a", "Attainment in Cook County, Atlantis")])
    assert any("no county 'Cook County' in Atlantis" in p for p in problems)


@pytest.mark.parametrize("text", ["Housing in Fresno", "The MAYOR of Fresno"])
def test_a_word_that_only_looks_like_the_state_code_does_not_count(
    monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    # "in" is Indiana lower case, "MA" sits inside MAYOR; neither is the state written
    places: dict[str, list[vg.Place]] = {
        "a": [("Fresno", "place", "Indiana")],
        "b": [("Fresno", "place", "Massachusetts")],
    }
    problems = check(
        monkeypatch,
        places,
        [golden("a", text), golden("b", text)],
        lists={"place": [{"name": "Fresno city, Indiana"}, {"name": "Fresno city, Massachusetts"}]},
    )
    assert sum("not in the question" in p for p in problems) == 2


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


def test_a_state_held_only_by_a_longer_state_name_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    lists = {"county": [{"name": "Fairfax County, West Virginia"}]}
    problems = check(
        monkeypatch,
        {"a": [("Fairfax County", "county", "Virginia")]},
        [golden("a", "Poverty in Fairfax County, Virginia")],
        lists=lists,
    )
    assert any("no county 'Fairfax County' in Virginia" in p for p in problems)


def test_a_state_held_only_by_a_word_match_of_the_name_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # East Portland is a hit of the resolver's matcher, but it is not Portland
    lists = {"place": [{"name": "East Portland CDP, Oregon"}, {"name": "Portland city, Maine"}]}
    problems = check(
        monkeypatch,
        {"a": [("Portland", "place", "Oregon")]},
        [golden("a", "Population of Portland, Oregon")],
        lists=lists,
    )
    assert any("no place 'Portland' in Oregon" in p for p in problems)


def test_a_state_held_by_a_name_with_a_suffix_word_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Population of Portland, Oregon"
    places: dict[str, list[vg.Place]] = {"a": [("Portland", "place", "Oregon")]}
    assert check(monkeypatch, places, [golden("a", text)]) == []


def test_every_place_of_a_golden_is_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    places: dict[str, list[vg.Place]] = {
        "a": [("Cook County", "county", "Illinois"), ("Portland", "place", None)]
    }
    # the state-holding place comes first: a check that stops there never reaches Portland
    text = "Cook County, Illinois against Portland"
    lists = {"county": COUNTY, "place": PLACE}
    problems = check(monkeypatch, places, [golden("a", text)], lists=lists)
    assert len(problems) == 1 and "'Portland' matches 3 places" in problems[0]


def test_the_listing_is_read_at_the_level_the_place_is_annotated_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    def spy(level: str) -> list[dict[str, str]]:
        asked.append(level)
        return LISTINGS[level]

    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", None)]})
    monkeypatch.setattr(vg, "EXEMPT", {})
    vg.place_problems([golden("a", "Poverty in Cook County")], spy)
    assert asked == ["county"]


def test_a_name_that_matches_nothing_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    problems = check(
        monkeypatch, {"a": [("Atlantis", "place", None)]}, [golden("a", "People in Atlantis")]
    )
    assert any("matches no place" in p for p in problems)


def test_an_unannotated_golden_does_not_hide_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    problems = check(
        monkeypatch,
        {"b": [("Cook County", "county", None)]},
        [golden("a", "Population of the nation"), golden("b", "Poverty in Cook County")],
    )
    assert len(problems) == 2
    assert problems[0].startswith("a: no place annotation")
    assert problems[1].startswith("b:") and "writes no state" in problems[1]


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
        for name, _level, state in vg.PLACES[e["id"]]
        if state and not vg._written(e["text"], name, state)
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


def test_an_unchanged_golden_that_already_carries_its_state_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")], "b": []})
    old = [golden("a", "Poverty in Cook County, Illinois"), OLD[1]]
    assert vg.diff_problems(old, [dict(g) for g in old]) == []


def test_a_changed_expectation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")], "b": []})
    new = edit(a={"text": "Poverty in Cook County, Illinois", "expect_table": "B17001"})
    assert vg.diff_problems(OLD, new) == ["a: a field other than text changed"]


def test_an_added_or_removed_field_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {})
    added = [{**OLD[0], "expect_warning": "ambiguous_place"}, OLD[1]]
    removed = [{k: v for k, v in OLD[0].items() if k != "tier"}, OLD[1]]
    assert vg.diff_problems(OLD, added) == ["a: a field other than text changed"]
    assert vg.diff_problems(OLD, removed) == ["a: a field other than text changed"]


def test_a_second_golden_is_still_checked_after_the_first_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")], "b": []})
    new = edit(a={"text": "Poverty in Cook County, Illinois"}, b={"expect_table": "B17001"})
    assert vg.diff_problems(OLD, new) == ["b: a field other than text changed"]


def test_an_edit_that_adds_more_than_the_state_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")], "b": []})
    new = edit(a={"text": "Poverty in Cook County, Illinois, in 2024"})
    assert any("more than the state" in p for p in vg.diff_problems(OLD, new))


def test_a_state_written_twice_is_more_than_the_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")], "b": []})
    new = edit(a={"text": "Poverty in Cook County, Illinois, Illinois"})
    assert any("more than the state" in p for p in vg.diff_problems(OLD, new))


def test_a_rewording_with_no_state_annotation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", None)], "b": []})
    new = edit(a={"text": "Poverty in Cook County, Illinois"})
    assert any("more than the state" in p for p in vg.diff_problems(OLD, new))


def test_a_dropped_or_reordered_golden_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {})
    assert vg.diff_problems(OLD, OLD[:1]) == ["the golden ids or their order changed"]
    assert vg.diff_problems(OLD, OLD[::-1]) == ["the golden ids or their order changed"]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(
    tmp_path: Path, old: str, new: str, grid_old: str | None = None, grid_new: str | None = None
) -> Path:
    """A real git repo: the golden and grid files committed as `old`, the working tree holding
    `new`. The grid defaults to one unchanged county-level cell, nothing to flag."""
    (tmp_path / "evals").mkdir()
    path, grid = tmp_path / vg.GOLDENS, tmp_path / vg.GRID
    _git(tmp_path, "init", "-q")
    path.write_text(old, encoding="utf-8")
    grid.write_text(grid_old or GRID_FILE, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "old")
    path.write_text(new, encoding="utf-8")
    grid.write_text(grid_new or grid_old or GRID_FILE, encoding="utf-8")
    return tmp_path


GRID_FILE = '[[cell]]\nid = "g1"\nlevel = "county"\nexpected_parents = ["Ohio"]\nquestion = "x"\n'
FILE_OLD = '[[question]]\nid = "a"\ntext = "Poverty in Cook County"\nexpect_table = "B17001"\n'
FILE_NEW = FILE_OLD.replace("Cook County", "Cook County, Illinois")


def test_load_reads_the_working_file_or_the_ref_asked_for(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(vg, "ROOT", _repo(tmp_path, FILE_OLD, FILE_NEW))
    assert vg._load(None)[0]["text"] == "Poverty in Cook County, Illinois"
    assert vg._load("HEAD")[0]["text"] == "Poverty in Cook County"


def test_a_ref_that_does_not_exist_is_an_error_not_an_empty_diff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(vg, "ROOT", _repo(tmp_path, FILE_OLD, FILE_NEW))
    with pytest.raises(subprocess.CalledProcessError):
        vg._load("no-such-ref")


def run_main(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    argv: list[str],
    *,
    ids: tuple[str, ...] = ("a",),
    key: str | None = "k",
) -> tuple[int, list[tuple[str, str | None]]]:
    calls: list[tuple[str, str | None]] = []

    def fake(level: str, geo: dict[str, str], *, key: str | None = None) -> list[dict[str, str]]:
        assert geo == {"state": "*"}
        calls.append((level, key))
        return LISTINGS[level]

    monkeypatch.setattr(vg, "ROOT", root)
    monkeypatch.setattr(vg, "list_census_names", fake)
    monkeypatch.setattr(vg, "PLACES", {i: [("Cook County", "county", "Illinois")] for i in ids})
    monkeypatch.setattr(vg, "EXEMPT", {})
    monkeypatch.setattr(sys, "argv", ["verify_golden_places", *argv])
    if key is None:
        monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    else:
        monkeypatch.setenv("CENSUS_API_KEY", key)
    return vg.main(), calls


def test_main_passes_a_clean_file_and_reads_each_level_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _repo(tmp_path, FILE_OLD, FILE_NEW + FILE_NEW.replace('"a"', '"b"'))
    code, calls = run_main(monkeypatch, root, [], ids=("a", "b"))
    assert (code, calls) == (0, [("county", "k")])


def test_main_fails_a_golden_that_names_a_shared_place_without_its_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, _ = run_main(monkeypatch, _repo(tmp_path, FILE_OLD, FILE_OLD), [])
    assert code == 1


def test_main_with_a_base_fails_an_edit_that_changed_more_than_the_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _repo(tmp_path, FILE_OLD, FILE_NEW.replace("B17001", "B19013"))
    assert run_main(monkeypatch, root, [])[0] == 0
    assert run_main(monkeypatch, root, ["--base", "HEAD"])[0] == 1


def test_main_with_a_base_passes_an_edit_that_changed_only_the_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _repo(tmp_path, FILE_OLD, FILE_NEW)
    assert run_main(monkeypatch, root, ["--base", "HEAD"])[0] == 0


def test_main_without_a_census_key_does_not_check_anything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, calls = run_main(monkeypatch, _repo(tmp_path, FILE_OLD, FILE_NEW), [], key=None)
    assert (code, calls) == (2, [])


def test_a_state_doubled_after_the_place_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    old = [golden("a", "Poverty in Cook County, Illinois")]
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")]})
    new = [golden("a", "Poverty in Cook County, Illinois, Illinois")]
    assert any("more than the state" in p for p in vg.diff_problems(old, new))


def test_a_state_inserted_away_from_the_place_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vg, "PLACES", {"a": [("Cook County", "county", "Illinois")], "b": []})
    new = edit(a={"text": "Poverty, Illinois in Cook County"})
    assert any("more than the state" in p for p in vg.diff_problems(OLD, new))


GRID_COUNTY = [
    {"name": "Marion County, Indiana"},
    {"name": "Marion County, Ohio"},
    {"name": "Hamilton County, Indiana"},
    {"name": "Hamilton County, Ohio"},
    {"name": "DuPage County, Illinois"},
]


def grid_check(cells: list[dict[str, Any]]) -> list[str]:
    return vg.grid_problems(cells, lambda level: {"county": GRID_COUNTY}[level])


def cell(**fields: Any) -> dict[str, Any]:
    base = {
        "id": "g1",
        "level": "tract",
        "expected_parents": ["Marion County", "Hamilton County"],
        "question": "All tracts in Marion and Hamilton County, Indiana.",
        "parent_state": "Indiana",
    }
    return {**base, **fields}


def test_a_grid_cell_with_shared_counties_and_its_state_passes() -> None:
    assert grid_check([cell()]) == []


def test_a_grid_cell_with_shared_counties_and_no_state_fails() -> None:
    bare = {k: v for k, v in cell().items() if k != "parent_state"}
    problems = grid_check([{**bare, "question": "All tracts in Marion and Hamilton County."}])
    assert problems == ["g1: names a shared county and carries no parent_state"]


def test_a_grid_cell_whose_state_the_question_does_not_write_fails() -> None:
    problems = grid_check([cell(question="All tracts in Marion and Hamilton County.")])
    assert any("not in the question after the last county" in p for p in problems)


def test_a_grid_cell_whose_state_does_not_hold_the_county_fails() -> None:
    problems = grid_check(
        [cell(parent_state="Illinois", question="Marion and Hamilton County, Illinois")]
    )
    assert any("no county 'Marion County' in Illinois" in p for p in problems)


def test_a_grid_cell_with_a_county_that_exists_nowhere_fails() -> None:
    problems = grid_check([cell(expected_parents=["Atlantis County"], parent_state=None)])
    assert any("matches no county nationwide" in p for p in problems)


def test_a_unique_county_needs_no_state() -> None:
    unique = cell(expected_parents=["DuPage County"], question="All tracts in DuPage County.")
    del unique["parent_state"]
    assert grid_check([unique]) == []


def test_county_level_cells_name_unique_states_and_are_not_checked() -> None:
    states = {"id": "g2", "level": "county", "expected_parents": ["Ohio"], "question": "x"}
    assert grid_check([states]) == []


def test_a_grid_level_the_check_does_not_know_is_a_problem_not_a_pass() -> None:
    assert grid_check([cell(level="block group")]) == [
        "g1: level 'block group' is not one this check knows"
    ]


OLD_CELL = {
    "id": "g1",
    "level": "tract",
    "expected_parents": ["Marion County"],
    "question": "All tracts in Marion County.",
}


def test_a_grid_edit_that_only_adds_the_state_passes() -> None:
    new = {
        **OLD_CELL,
        "question": "All tracts in Marion County, Indiana.",
        "parent_state": "Indiana",
    }
    assert vg.grid_diff_problems([OLD_CELL], [new]) == []


def test_a_grid_edit_that_changes_the_level_or_parents_fails() -> None:
    base = {
        **OLD_CELL,
        "question": "All tracts in Marion County, Indiana.",
        "parent_state": "Indiana",
    }
    for changed in ({"level": "county"}, {"expected_parents": ["Hamilton County"]}):
        assert vg.grid_diff_problems([OLD_CELL], [{**base, **changed}]) == [
            "g1: a field other than question or a new parent_state changed"
        ]


def test_a_grid_edit_that_rewords_more_than_the_state_fails() -> None:
    new = {
        **OLD_CELL,
        "question": "Every tract in Marion County, Indiana.",
        "parent_state": "Indiana",
    }
    assert "g1: question changed by more than the state" in vg.grid_diff_problems([OLD_CELL], [new])


def test_a_grid_edit_that_writes_a_state_without_declaring_it_fails() -> None:
    new = {**OLD_CELL, "question": "All tracts in Marion County, Indiana."}
    assert "g1: question changed by more than the state" in vg.grid_diff_problems([OLD_CELL], [new])


def test_grid_cells_dropped_or_reordered_fail() -> None:
    other = {**OLD_CELL, "id": "g2"}
    assert vg.grid_diff_problems([OLD_CELL, other], [other, OLD_CELL]) == [
        "the grid cell ids or their order changed"
    ]


def test_every_curated_cell_in_the_real_grid_writes_its_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cells = tomllib.loads((ROOT / vg.GRID).read_text(encoding="utf-8"))["cell"]
    tract = [c for c in cells if c["level"] == "tract"]
    assert tract and all(
        vg._written(c["question"], c["expected_parents"][-1], c["parent_state"]) for c in tract
    )


@pytest.mark.parametrize("gid", ["t01", "t06", "t14"])
def test_a_golden_that_named_no_place_gains_exactly_the_added_phrase(
    monkeypatch: pytest.MonkeyPatch, gid: str
) -> None:
    old = [golden(gid, "Share of households")]
    phrase = vg.ADDED[gid]
    new = [golden(gid, f"Share of households{phrase}")]
    assert vg.diff_problems(old, new) == []
    worse = [golden(gid, f"Share of households{phrase} in 2024")]
    assert any("more than the state" in p for p in vg.diff_problems(old, worse))


def test_the_added_places_are_the_annotated_ones() -> None:
    for gid, phrase in vg.ADDED.items():
        name, _level, state = vg.PLACES[gid][0]
        assert phrase == f" in {name}, {state}"


def test_a_unique_county_that_also_writes_its_state_passes() -> None:
    unique = cell(expected_parents=["DuPage County"], question="Tracts in DuPage County, Illinois")
    assert grid_check([{**unique, "parent_state": "Illinois"}]) == []


@pytest.mark.parametrize(
    "parents", [["Marion County", "DuPage County"], ["DuPage County", "Marion County"]]
)
def test_one_shared_county_among_the_parents_needs_the_state_wherever_it_sits(
    parents: list[str],
) -> None:
    bare = {k: v for k, v in cell().items() if k != "parent_state"}
    problems = grid_check([{**bare, "expected_parents": parents, "question": "Tracts in these."}])
    assert problems == ["g1: names a shared county and carries no parent_state"]


def test_every_parent_must_be_in_the_state_not_only_the_first() -> None:
    problems = grid_check(
        [
            cell(
                expected_parents=["DuPage County", "Marion County"],
                parent_state="Illinois",
                question="Tracts in DuPage and Marion County, Illinois",
            )
        ]
    )
    assert problems == ["g1: no county 'Marion County' in Illinois"]


def test_a_state_written_after_another_county_than_the_last_is_not_written() -> None:
    wrong_spot = "Tracts in Marion County, Indiana and Hamilton County"
    before_all = "In Indiana, all tracts in Marion and Hamilton County."
    for question in (wrong_spot, before_all):
        problems = grid_check([cell(question=question)])
        assert problems == [
            "g1: parent_state 'Indiana' is not in the question after the last county"
        ]


def test_a_county_that_only_contains_the_name_does_not_hold_the_state() -> None:
    lists = [{"name": "Little Marion County, Illinois"}, {"name": "Marion County, Ohio"}]
    one = cell(
        expected_parents=["Marion County"],
        parent_state="Illinois",
        question="Marion County, Illinois",
    )
    problems = vg.grid_problems([one], lambda _level: lists)
    assert problems == ["g1: no county 'Marion County' in Illinois"]


def test_a_bad_cell_does_not_hide_the_next_one() -> None:
    bare = {k: v for k, v in cell().items() if k != "parent_state"}
    problems = grid_check([bare, {**bare, "id": "g2"}, cell(id="g3")])
    assert [p.split(":")[0] for p in problems] == ["g1", "g2"]


STATED = {
    **OLD_CELL,
    "question": "All tracts in Marion County, Indiana.",
    "parent_state": "Indiana",
}


@pytest.mark.parametrize(
    "changed",
    [{"verb": "every"}, {"connector": "or"}, {"parent_count": 3}, {"note": "added field"}],
)
def test_a_grid_edit_that_changes_any_other_field_fails(changed: dict[str, Any]) -> None:
    old = {**OLD_CELL, "verb": "all", "connector": "and", "parent_count": 2}
    new = {**old, "question": STATED["question"], "parent_state": "Indiana", **changed}
    assert vg.grid_diff_problems([old], [new]) == [
        "g1: a field other than question or a new parent_state changed"
    ]


@pytest.mark.parametrize("how", ["changed", "dropped"])
def test_a_grid_edit_that_changes_or_drops_a_parent_state_fails(how: str) -> None:
    new = (
        {**STATED, "parent_state": "Ohio"}
        if how == "changed"
        else {k: v for k, v in STATED.items() if k != "parent_state"}
    )
    assert vg.grid_diff_problems([STATED], [new]) == [
        "g1: a field other than question or a new parent_state changed"
    ]


def test_a_grid_edit_that_writes_the_state_twice_fails() -> None:
    new = {**STATED, "question": "All tracts in Marion County, Indiana, Indiana."}
    assert vg.grid_diff_problems([STATED], [new]) == ["g1: question changed by more than the state"]


def test_an_unchanged_grid_cell_that_already_carries_its_state_passes() -> None:
    assert vg.grid_diff_problems([STATED], [dict(STATED)]) == []


def test_load_reads_a_named_file_and_table_from_the_tree_or_a_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    grid_new = GRID_FILE.replace('"x"', '"y"')
    monkeypatch.setattr(vg, "ROOT", _repo(tmp_path, FILE_OLD, FILE_NEW, GRID_FILE, grid_new))
    assert vg._load(None, vg.GRID, "cell")[0]["question"] == "y"
    assert vg._load("HEAD", vg.GRID, "cell")[0]["question"] == "x"
    assert vg._load("HEAD")[0]["id"] == "a"


TRACT_OLD = (
    '[[cell]]\nid = "g1"\nlevel = "tract"\nverb = "all"\nexpected_parents = ["Cook County"]\n'
    'question = "All tracts in Cook County."\n'
)
TRACT_NEW = (
    TRACT_OLD.replace("Cook County.", "Cook County, Illinois.") + 'parent_state = "Illinois"\n'
)


def main_grid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, old: str, new: str, argv: list[str]
) -> tuple[int, list[tuple[str, str | None]]]:
    fresh = tmp_path / str(len(list(tmp_path.iterdir())))  # one repo per call
    fresh.mkdir()
    return run_main(monkeypatch, _repo(fresh, FILE_OLD, FILE_NEW, old, new), argv)


def test_main_passes_a_grid_cell_that_writes_its_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, calls = main_grid(monkeypatch, tmp_path, TRACT_NEW, TRACT_NEW, ["--base", "HEAD"])
    assert (code, calls) == (0, [("county", "k")])


def test_main_fails_a_grid_cell_that_names_a_shared_county_without_its_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert main_grid(monkeypatch, tmp_path, TRACT_OLD, TRACT_OLD, [])[0] == 1


def test_main_fails_a_grid_state_that_is_declared_but_not_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declared_only = TRACT_OLD + 'parent_state = "Illinois"\n'
    assert main_grid(monkeypatch, tmp_path, TRACT_OLD, declared_only, ["--base", "HEAD"])[0] == 1


def test_main_fails_a_grid_state_written_away_from_the_last_county(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    away = TRACT_OLD.replace("All tracts in", "All tracts, Illinois, in")
    away += 'parent_state = "Illinois"\n'
    assert main_grid(monkeypatch, tmp_path, TRACT_OLD, away, [])[0] == 1
    assert main_grid(monkeypatch, tmp_path, TRACT_OLD, away, ["--base", "HEAD"])[0] == 1


def test_main_with_a_base_passes_a_grid_edit_that_only_adds_the_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert main_grid(monkeypatch, tmp_path, TRACT_OLD, TRACT_NEW, ["--base", "HEAD"])[0] == 0


def test_main_with_a_base_fails_a_grid_edit_that_changed_more_than_the_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reworded = TRACT_NEW.replace('verb = "all"', 'verb = "every"')
    assert main_grid(monkeypatch, tmp_path, TRACT_OLD, reworded, [])[0] == 0
    assert main_grid(monkeypatch, tmp_path, TRACT_OLD, reworded, ["--base", "HEAD"])[0] == 1


def test_main_with_a_base_fails_a_dropped_grid_cell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    two = TRACT_NEW + TRACT_NEW.replace('"g1"', '"g2"')
    assert main_grid(monkeypatch, tmp_path, two, TRACT_NEW, ["--base", "HEAD"])[0] == 1


def test_every_grid_state_in_the_real_grid_is_one_the_scorer_knows() -> None:
    cells = tomllib.loads((ROOT / vg.GRID).read_text(encoding="utf-8"))["cell"]
    known = {name for name, _usps, _fips in vg.STATES}
    states = [c["parent_state"].casefold() for c in cells if "parent_state" in c]
    assert len(states) == 16 and set(states) <= known


def test_the_added_phrase_is_in_the_real_golden_exactly_once() -> None:
    entries = {
        e["id"]: e["text"]
        for e in tomllib.loads((ROOT / vg.GOLDENS).read_text(encoding="utf-8"))["question"]
    }
    assert all(entries[gid].count(phrase) == 1 for gid, phrase in vg.ADDED.items())


def test_the_real_goldens_differ_from_their_phrase_less_text_by_the_added_phrase_only() -> None:
    entries = tomllib.loads((ROOT / vg.GOLDENS).read_text(encoding="utf-8"))["question"]
    old = [{**e, "text": e["text"].replace(vg.ADDED.get(e["id"], "\0"), "", 1)} for e in entries]
    changed = [n["id"] for n, o in zip(entries, old, strict=True) if n["text"] != o["text"]]
    assert changed == sorted(vg.ADDED)
    assert vg.diff_problems(old, entries) == []


def test_a_golden_may_not_gain_the_phrase_added_to_another() -> None:
    old = [golden("t06", "Share of households")]
    new = [golden("t06", f"Share of households{vg.ADDED['t01']}")]
    assert any("more than the state" in p for p in vg.diff_problems(old, new))


def test_the_added_phrase_written_twice_or_already_there_fails() -> None:
    phrase = vg.ADDED["t01"]
    there = [golden("t01", f"Income{phrase} by year")]
    twice = [golden("t01", f"Income{phrase}{phrase} by year")]
    assert any("more than the state" in p for p in vg.diff_problems(there, twice))


def test_the_added_phrase_with_a_changed_place_fails() -> None:
    old = [golden("t01", "Income by year")]
    new = [golden("t01", "Income in Fulton County Georgia by year")]
    assert any("more than the state" in p for p in vg.diff_problems(old, new))


def test_a_usps_code_must_end_at_a_word_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    places: dict[str, list[vg.Place]] = {"a": [("Denver", "place", "Colorado")]}
    rows = {"place": [{"name": "Denver city, Colorado"}, {"name": "Denver city, Iowa"}]}
    bad = check(monkeypatch, places, [golden("a", "Homes in Denver COunty")], lists=rows)
    assert any("not in the question after 'Denver'" in p for p in bad)


@pytest.mark.parametrize("tail", ["", ".", "?", ",", " since 2017"])
def test_a_usps_code_before_punctuation_or_a_space_counts(
    monkeypatch: pytest.MonkeyPatch, tail: str
) -> None:
    places: dict[str, list[vg.Place]] = {"a": [("Denver", "place", "Colorado")]}
    rows = {"place": [{"name": "Denver city, Colorado"}, {"name": "Denver city, Iowa"}]}
    assert check(monkeypatch, places, [golden("a", f"Homes in Denver CO{tail}")], lists=rows) == []


def test_a_county_cell_carrying_a_state_is_a_problem() -> None:
    states = {"id": "g2", "level": "county", "expected_parents": ["Ohio"], "parent_state": "Ohio"}
    assert grid_check([{**states, "question": "x"}]) == [
        "g2: a county cell names states, which are unique: no parent_state"
    ]


def test_a_tract_cell_with_no_parents_is_a_problem_not_a_crash() -> None:
    assert grid_check([cell(expected_parents=[])]) == ["g1: a tract cell with no expected_parents"]


def test_a_tract_cell_that_names_no_county_is_flagged_even_where_the_scorer_skips_it() -> None:
    # run_grid's tract_identity_ok returns True for a list that is not county names; the check
    # must be the one that catches a state written beside such a list
    odd = cell(expected_parents=["Atlantis"], question="All tracts in Atlantis, Indiana.")
    assert any("matches no county nationwide" in p for p in grid_check([odd]))
