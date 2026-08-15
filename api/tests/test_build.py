"""Folding the collapsed `C` table into the `B` it is identical to.

A `C` table publishes the same title, universe and concept as the `B` whose
categories it collapses, so its embedded document is byte-identical and its
vector is equal. 120 of 756 documents were in that state. Of 600 generated
questions the 97 asking for such a `C` scored 0% at rank 1 — they could not
have scored anything else.

`_fold_identical_twins` is exercised directly rather than through `build()`,
which needs a populated metadata cache and an OpenAI key. It is a pure function
over explicit inputs, and the case it exists to get right is a naming quirk
that no end-to-end test would isolate.
"""

from __future__ import annotations

from src.retrieval.build import _fold_identical_twins

IDENTICAL = "Educational Attainment for the Population 25 Years and Over. Universe: Population"


def test_the_collapsed_twin_is_dropped_and_kept_as_a_member() -> None:
    members: dict[str, list[str]] = {"B15003": [], "C15003": []}
    collapsed = _fold_identical_twins(
        ["B15003", "C15003"],
        members,
        {"B15003": IDENTICAL, "C15003": IDENTICAL},
        {"B15003": 25, "C15003": 18},
    )

    assert collapsed == {"C15003"}
    # Nothing a user can ask is lost: the C is reachable through the member
    # list, the same way a race iteration is.
    assert members["B15003"] == ["C15003"]
    assert "C15003" not in members


def test_a_twin_with_a_mismatched_number_still_folds() -> None:
    # C25045 is the collapsed B25044 and no C25044 is published. An earlier
    # version of this required a matching five-digit stem and silently left
    # this one unreachable, because Census does not keep the numbers aligned.
    members: dict[str, list[str]] = {"B25044": [], "C25045": []}
    collapsed = _fold_identical_twins(
        ["B25044", "C25045"],
        members,
        {"B25044": "Tenure by Vehicles Available", "C25045": "Tenure by Vehicles Available"},
        {"B25044": 15, "C25045": 7},
    )

    assert collapsed == {"C25045"}
    assert members["B25044"] == ["C25045"]


def test_the_c_keeps_its_own_iterations_when_it_folds() -> None:
    members: dict[str, list[str]] = {"B15003": ["B15003A"], "C15003": ["C15003A"]}
    _fold_identical_twins(
        ["B15003", "C15003"],
        members,
        {"B15003": IDENTICAL, "C15003": IDENTICAL},
        {"B15003": 25, "C15003": 18},
    )

    assert members["B15003"] == ["B15003A", "C15003", "C15003A"]


def test_tables_that_say_different_things_are_left_alone() -> None:
    members: dict[str, list[str]] = {"B16001": [], "C16001": []}
    collapsed = _fold_identical_twins(
        ["B16001", "C16001"],
        members,
        {
            "B16001": "Language Spoken at Home by Ability to Speak English",
            "C16001": "Language Spoken at Home for the Population 5 Years and Over",
        },
        {"B16001": 120, "C16001": 40},
    )

    assert collapsed == set()
    assert members["C16001"] == []


def test_a_c_with_more_categories_is_not_a_collapsed_table() -> None:
    # "Collapsed" means fewer categories. If the cell counts say otherwise the
    # superset argument does not hold, and folding would lose the user detail.
    members: dict[str, list[str]] = {"B15003": [], "C15003": []}
    collapsed = _fold_identical_twins(
        ["B15003", "C15003"],
        members,
        {"B15003": IDENTICAL, "C15003": IDENTICAL},
        {"B15003": 18, "C15003": 25},
    )

    assert collapsed == set()


def test_two_b_tables_sharing_a_title_are_a_real_ambiguity_not_a_twin() -> None:
    # B05013 and B05014 both publish "Sex by Age for the Foreign-Born
    # Population". Neither is a collapsed view of the other, so both stay
    # rankable and the user gets to see both.
    identical = "Sex by Age for the Foreign-Born Population. Universe: Foreign-born population"
    members: dict[str, list[str]] = {"B05013": [], "B05014": []}
    collapsed = _fold_identical_twins(
        ["B05013", "B05014"],
        members,
        {"B05013": identical, "B05014": identical},
        {"B05013": 39, "B05014": 19},
    )

    assert collapsed == set()


def test_a_table_with_no_twin_is_untouched() -> None:
    members: dict[str, list[str]] = {"B01003": [], "B19013": []}
    collapsed = _fold_identical_twins(
        ["B01003", "B19013"],
        members,
        {"B01003": "Total Population", "B19013": "Median Household Income"},
        {"B01003": 1, "B19013": 1},
    )

    assert collapsed == set()
    assert members == {"B01003": [], "B19013": []}
