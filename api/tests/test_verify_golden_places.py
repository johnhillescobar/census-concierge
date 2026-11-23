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


def _repo(tmp_path: Path, old: str, new: str) -> Path:
    """A real git repo: the golden file committed as `old`, the working tree holding `new`."""
    (tmp_path / "evals").mkdir()
    path = tmp_path / vg.GOLDENS
    _git(tmp_path, "init", "-q")
    path.write_text(old, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "old")
    path.write_text(new, encoding="utf-8")
    return tmp_path


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
