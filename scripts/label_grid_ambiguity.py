#!/usr/bin/env python3
"""Label each grid cell ambiguous or not from Census data, and say why (CC-103).

    python scripts/label_grid_ambiguity.py --grid evals/cc103_phrasing_grid.toml
    python scripts/label_grid_ambiguity.py --grid <sealed.toml> --out evidence/x_sealed.jsonl

Definition (this app): a question is AMBIGUOUS when more than one single-state reading fits
the places it names and nothing in the question picks one. Set membership against the Census
Gazetteer decides it: take the states that hold a county with each named name; the question
is settled when exactly one state holds them all, ambiguous when several do, and
`no_single_state` when none does. State names are unique, so a state is never ambiguous.
Scope questions ("which counties?", union versus intersection) are not ambiguity.

No model and no regex: this is a lookup, so the label is reproducible and auditable. Prints
counts only, never question text, so it is safe to run on the sealed file. Reads the cells'
`expected_parents`; entries that are neither a state nor "<Name> County" are `unlabeled`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from src.geo_list import STATES  # noqa: E402

GAZETTEER = ROOT / "data" / "raw" / "census_ref" / "counties.zip"
STATE_NAMES = {name.casefold() for name, _usps, _fips in STATES}


def county_states() -> dict[str, set[str]]:
    """County name (casefolded) -> USPS codes of the states that have a county by that name."""
    with zipfile.ZipFile(GAZETTEER) as archive:
        text = archive.read(archive.namelist()[0]).decode("latin-1")
    found: dict[str, set[str]] = {}
    for line in text.splitlines()[1:]:
        usps, _geoid, _ansi, name, *_rest = line.split("\t")
        found.setdefault(name.strip().casefold(), set()).add(usps)
    return found


def label(parents: list[str], counties: dict[str, set[str]]) -> dict:
    names = [p.strip().casefold() for p in parents]
    if all(n in STATE_NAMES for n in names):
        return {"kind": "state", "ambiguous": False, "candidate_states": []}
    if not all(n.endswith(" county") and n in counties for n in names):
        return {"kind": "unlabeled", "ambiguous": None, "candidate_states": []}
    fits = set.intersection(*(counties[n] for n in names))
    kind = "settled" if len(fits) == 1 else "ambiguous" if fits else "no_single_state"
    return {"kind": kind, "ambiguous": len(fits) != 1, "candidate_states": sorted(fits)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence" / "ambiguity.jsonl")
    args = parser.parse_args()
    with args.grid.open("rb") as handle:
        cells = tomllib.load(handle)["cell"]
    counties = county_states()
    rows = [{"id": c["id"], **label(c["expected_parents"], counties)} for c in cells]
    args.out.write_text("".join(json.dumps(r) + chr(10) for r in rows), encoding="utf-8")
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    print(f"cells={len(rows)} {kinds} -> {args.out}")


if __name__ == "__main__":
    main()
