"""Grid ambiguity labels come from Gazetteer set membership, not from a model."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import label_grid_ambiguity as labels  # noqa: E402

pytestmark = pytest.mark.usefixtures("gazetteer")


def test_state_names_are_never_ambiguous() -> None:
    result = labels.label(["Ohio", "Michigan"], labels.county_states())
    assert result["kind"] == "state" and result["ambiguous"] is False


def test_a_companion_county_that_exists_in_one_state_settles_the_reading() -> None:
    result = labels.label(["Cook County", "DuPage County"], labels.county_states())
    assert (
        result["kind"] == "settled"
        and result["candidate_states"] == ["IL"]
        and result["ambiguous"] is False
    )


def test_county_names_that_fit_two_states_are_ambiguous() -> None:
    names = ["Marion County", "Hamilton County", "Lake County", "Allen County"]
    result = labels.label(names, labels.county_states())
    assert result["ambiguous"] is True and {"IN", "OH"} <= set(result["candidate_states"])


def test_counties_that_share_no_state_are_not_called_ambiguous() -> None:
    result = labels.label(["DuPage County", "Harris County"], labels.county_states())
    assert result["kind"] == "no_single_state" and result["ambiguous"] is False


def test_entries_that_are_not_states_or_counties_are_unlabeled() -> None:
    result = labels.label(["Chicago", "Houston"], labels.county_states())
    assert result["kind"] == "unlabeled" and result["ambiguous"] is None
