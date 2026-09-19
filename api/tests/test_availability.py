"""The vintage matrix: what existed when, and under what description.

The semantic index is deliberately vintage-agnostic so a discontinued table
stays findable. This file is where "does it exist in 2019?" is answered, and
slice 3's guards read it rather than asking the model to remember.
"""

from __future__ import annotations

from typing import Any

from src.retrieval import availability

MATRIX: dict[str, Any] = {
    "datasets": {
        "acs5": {
            "2019": {
                "B19013": {
                    "title": "Median Household Income in the Past 12 Months",
                    "universe": "Households",
                    "variables": ["001E"],
                },
                "B99053": {
                    "title": "Allocation of Year of Naturalization",
                    "universe": "Total population",
                    "variables": ["001E"],
                },
            },
            "2023": {
                "B19013": {
                    "title": "Median Household Income (in 2023 Inflation-Adjusted Dollars)",
                    "universe": "Households",
                    "variables": ["001E"],
                },
                "B28002": {
                    "title": "Presence and Types of Internet Subscriptions in Household",
                    "universe": "Households",
                    "variables": ["001E", "002E"],
                },
            },
        }
    }
}


def test_a_table_is_described_by_its_most_recent_vintage() -> None:
    # Titles get reworded between vintages. The newest wording is what a user
    # types, so it is what should be indexed.
    tables = availability.union_tables(MATRIX)
    assert tables["B19013"].title == "Median Household Income (in 2023 Inflation-Adjusted Dollars)"


def test_a_table_dropped_after_2019_is_still_in_the_union() -> None:
    # It is still the right answer to a question about 2018. Taking only the
    # newest vintage would make it unfindable and answer with something else.
    tables = availability.union_tables(MATRIX)
    assert "B99053" in tables
    assert tables["B99053"].title == "Allocation of Year of Naturalization"


def test_the_union_carries_the_universe() -> None:
    # Households vs families vs housing units is the most common silent wrong
    # answer in Census work, and it is half of what the embedded document says.
    tables = availability.union_tables(MATRIX)
    assert tables["B28002"].universe == "Households"


def test_the_union_is_ordered_by_table_id() -> None:
    # `build.py` derives document positions from this ordering, and the
    # experiments cache is keyed on the exact document list. A reordering
    # invalidates every recorded number without changing a score.
    assert list(availability.union_tables(MATRIX)) == ["B19013", "B28002", "B99053"]


def test_household_encoding_and_title_case_are_the_same_definition() -> None:
    early = {
        "title": "TYPES OF COMPUTERS IN HOUSEHOLD",
        "universe": "",
        "variables": ["001E"],
    }
    late = {
        "title": "Types of Computers in Household",
        "universe": "Households",
        "variables": ["001E"],
    }
    assert availability.same_definition(early, late)
    assert availability.same_definition(late, {"title": late["title"], "universe": "HSHLD"})
    assert availability.same_definition(
        {"title": "Median Household Income (in 2023 inflation-adjusted dollars)", "universe": ""},
        {"title": "Median Household Income", "universe": "Households"},
    )
    assert not availability.same_definition(
        {"title": "Median Household Income", "universe": "Households"},
        {"title": "Median Family Income", "universe": "Families"},
    )


def test_recoded_suffix_labels_are_dropped_missing_signatures_are_not() -> None:
    stable = {
        "title": "Types of Computers in Household",
        "universe": "Households",
        "variables": ["001E", "005E"],
    }
    assert availability.same_definition(stable, dict(stable))
    assert not availability.same_definition(
        {**stable, "label_sig": "aaaa"}, {**stable, "label_sig": "bbbb"}
    )
    facts = {
        2017: {**stable, "label_sig": "aaaa"},
        2024: {**stable, "label_sig": "bbbb"},
    }

    def lookup(dataset: str, year: int, table_id: str) -> dict[str, object] | None:
        assert dataset == "acs5" and table_id == "B28001"
        return facts[year]

    kept, omitted, reasons = availability.drop_incompatible(
        lookup, "acs5", [2017, 2024], "B28001", ["005E"]
    )
    assert kept == [2024]
    assert omitted == [2017]
    assert reasons == [availability.REASON_VARIABLE]


def test_changed_universe_or_missing_suffix_is_dropped() -> None:
    facts = {
        2016: None,
        2019: {"title": "Median Household Income", "universe": "Families", "variables": ["001E"]},
        2024: {
            "title": "Median Household Income",
            "universe": "Households",
            "variables": ["001E", "002E"],
        },
    }

    def lookup(dataset: str, year: int, table_id: str) -> dict[str, object] | None:
        assert dataset == "acs5" and table_id == "B19013"
        return facts[year]

    kept, omitted, reasons = availability.drop_incompatible(
        lookup, "acs5", [2016, 2019, 2024], "B19013", ["001E"]
    )
    assert kept == [2024]
    assert omitted == [2016, 2019]
    assert reasons == [availability.REASON_VARIABLE, availability.REASON_VARIABLE]
    kept, omitted, reasons = availability.drop_incompatible(
        lookup, "acs5", [2024], "B19013", ["002E"]
    )
    assert kept == [2024]
    assert omitted == []
    kept, omitted, _reasons = availability.drop_incompatible(
        lookup, "acs5", [2019, 2024], "B19013", ["002E"]
    )
    assert 2019 in omitted
    assert kept == [2024]


def test_latest_calendar_year_is_the_definition_reference() -> None:
    facts = {
        2019: {"title": "Median Household Income", "universe": "Families", "variables": ["001E"]},
        2024: {"title": "Median Household Income", "universe": "Households", "variables": ["001E"]},
    }

    def lookup(dataset: str, year: int, table_id: str) -> dict[str, object] | None:
        assert dataset == "acs5" and table_id == "B19013"
        return facts[year]

    kept, omitted, _reasons = availability.drop_incompatible(
        lookup, "acs5", [2024, 2019], "B19013", ["001E"]
    )
    assert kept == [2024]
    assert omitted == [2019]
