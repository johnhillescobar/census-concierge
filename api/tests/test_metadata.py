"""Reading ACS metadata, and the two rules that shape the corpus from it.

`family_id` and `is_subject_table` between them took 1,458 documents to 756 and
moved `@5` further than any model choice measured. They are the highest-leverage
eight lines in the repo, and both are regexes over a table ID.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest
from src.retrieval import metadata


def test_race_iterations_and_puerto_rico_variants_fold_into_their_parent() -> None:
    # These are the same table under a filter. Indexed separately they crowd
    # out the parent: "crowded housing" ranked B25014G above B25014.
    assert metadata.family_id("B19013A") == "B19013"
    assert metadata.family_id("B25014G") == "B25014"
    assert metadata.family_id("B06007PR") == "B06007"
    assert metadata.family_id("B06007APR") == "B06007"


def test_a_collapsed_table_is_not_a_filtered_view_of_its_base() -> None:
    # C16001 is its own table, not C-as-an-iteration-of-B. The B/C pair is
    # handled in build.py, on evidence, and not by this regex.
    assert metadata.family_id("C16001") == "C16001"


def test_a_five_digit_table_is_never_mistaken_for_an_iteration() -> None:
    # B18135 ends in a digit, not a letter; a looser pattern would fold it to
    # B18135's non-existent parent and lose the table entirely.
    assert metadata.family_id("B18135") == "B18135"
    assert metadata.family_id("B01003") == "B01003"


def test_survey_quality_tables_are_not_subject_tables() -> None:
    # These describe how the survey performed. Left in, "how many people are
    # naturalized citizens" answers B99053, Allocation of Year of Naturalization.
    assert not metadata.is_subject_table("B99053")
    assert not metadata.is_subject_table("B00001")
    assert not metadata.is_subject_table("B98001")
    assert not metadata.is_subject_table("C98002")

    assert metadata.is_subject_table("B01003")
    assert metadata.is_subject_table("B09001")  # 09, not 00 — the prefix is two digits
    assert metadata.is_subject_table("B25099")  # 99 in the table number, not the subject


def test_probing_vintages_does_not_stop_at_a_missing_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACS1 has no 2020 release. Stopping there silently drops 2021 onward.

    That happened: the loop used `break` and the index was built on five years
    of ACS1 while reporting nine.
    """
    probed: list[tuple[str, int]] = []

    def fake_fetch(client: Any, dataset: str, year: int, name: str) -> dict[str, Any] | None:
        if name == "groups":
            probed.append((dataset, year))
        if dataset == "acs1" and year == 2020:
            return None
        if year > 2024:
            return None
        return {"groups": []}

    monkeypatch.setattr(metadata, "fetch", fake_fetch)
    found = metadata.fetch_all(first=2016)

    assert 2020 not in found["acs1"]
    assert found["acs1"] == [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
    assert found["acs5"] == [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
    # The gap was probed past, not stopped at.
    assert ("acs1", 2021) in probed


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def test_universe_is_read_from_either_key_the_api_emits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The API really does emit "universe " with a trailing space, on some
    # vintages and not others. Universe is the field that separates households
    # from families, so losing it is a wrong answer, not a cosmetic gap.
    monkeypatch.setattr(metadata, "CACHE", tmp_path)
    _write(
        tmp_path / "acs5" / "2023" / "groups.json.gz",
        {
            "groups": [
                {
                    "name": "B19013",
                    "description": "Median Household Income",
                    "universe ": "Households",
                },
                {"name": "B11001", "description": "Household Type", "universe": "Households"},
                {"name": "", "description": "nameless rows are skipped"},
            ]
        },
    )

    tables = metadata.tables("acs5", 2023)
    assert tables["B19013"].universe == "Households"
    assert tables["B11001"].universe == "Households"
    assert "" not in tables


def test_only_estimate_variables_reach_the_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Margins are fetched alongside at request time and add nothing to
    # retrieval; a variable with no group is not part of any table.
    monkeypatch.setattr(metadata, "CACHE", tmp_path)
    _write(
        tmp_path / "acs5" / "2023" / "variables.json.gz",
        {
            "variables": {
                "B19013_001E": {
                    "group": "B19013",
                    "label": "Estimate!!Median",
                    "concept": "Income",
                },
                "B19013_001M": {"group": "B19013", "label": "Margin of Error!!Median"},
                "GEO_ID": {"group": "N/A", "label": "Geography"},
                "for": "not a dict",
            }
        },
    )

    variables = metadata.variables("acs5", 2023)
    assert set(variables) == {"B19013_001E"}
    assert variables["B19013_001E"].table_id == "B19013"


def test_cache_path_cannot_leave_the_cache_root() -> None:
    with pytest.raises(ValueError):
        metadata.cache_path("..", 2024, "geography")
    path = metadata.cache_path("acs5", 2024, "geography")
    assert path.is_relative_to(metadata.CACHE.resolve())
