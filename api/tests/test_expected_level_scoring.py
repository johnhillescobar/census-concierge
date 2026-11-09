"""A per-leg list of expected geography levels rejects a fetch at a level nobody expected."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_demo  # noqa: E402

BASE = "https://api.census.gov/data/2024/acs/acs5?get=B25064_001E&for="
PLACE = f"{BASE}place:05000&in=state:48"
STATE = f"{BASE}state:48"
COUNTY = f"{BASE}county:201&in=state:48"


def _body(*urls: str) -> dict[str, Any]:
    return {
        "urls": list(urls),
        "table_id": "B25064",
        "rows": [{"B25064_001E": "1"}],
        "geoid": "1600000US4805000",
        "universe": "Renter-occupied housing units",
    }


def test_every_expected_leg_fetched_plus_an_unexpected_level_is_not_answered() -> None:
    entry = {"id": "q23", "expect_table": "B25064", "expect_geo_level": ["place", "state"]}
    assert run_demo.is_answered(entry, status_code=200, body=_body(PLACE, STATE)) is True
    extra = _body(PLACE, STATE, COUNTY)
    assert run_demo.is_answered(entry, status_code=200, body=extra) is False
    assert (
        run_demo.miss_detail(entry, status_code=200, body=extra) == "wrong geography level county"
    )
