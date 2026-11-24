#!/usr/bin/env python3
"""Check that no visible golden or grid cell names a shared place without its state (CC-141).

    python scripts/verify_golden_places.py [--base origin/main]

A place name that matches more than one place nationwide, with no state the user wrote, is
refused by the product (CC-104). A golden that asks such a question measures the refusal, not the
retrieval. Each golden's places are annotated below by hand (the script never reads the question's
words to find a place); the match is the resolver's own `filter_rows` over live Census listings at
the level the golden expects. Needs CENSUS_API_KEY. With --base REF it also proves the edit changed
only the state: per id every field but `text` is equal, and `text` minus the inserted ", State" is
the old text. The phrasing grid is checked the same way from each cell's structured
`expected_parents` (a tract cell whose county names are shared must carry `parent_state`, written
in the question). Exits non-zero on any problem.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from src.geo_list import STATES, filter_rows, list_census_names  # noqa: E402

GOLDENS = "evals/golden_questions.toml"
GRID = "evals/cc103_phrasing_grid.toml"
Listing = Callable[[str], list[dict[str, str]]]
# (name as the model would write it, level, state the question carries or None)
Place = tuple[str, str, str | None]

# id -> the places it names. [] = no place a NAME can match (a state, a code, a region, no place).
PLACES: dict[str, list[Place]] = {
    "q01": [("Harris County", "county", "Texas")],
    "q02": [],
    "q03": [("Cook County", "county", "Illinois")],
    "q04": [("Detroit", "place", "Michigan")],
    "q05": [("Portland", "place", "Oregon")],
    "q06": [],
    "q07": [],
    "q08": [],
    "q09": [],
    "q10": [("Queens", "county", None)],
    "q11": [],  # one metro area, not a place-name match
    "q12": [],
    "q13": [("Providence", "place", "Rhode Island")],
    "q14": [("Baltimore City", "county", None)],
    "q15": [],
    "q16": [("Ithaca", "place", "New York")],
    "q17": [],  # an informal region; the model names the counties
    "q18": [("Milwaukee", "place", "Wisconsin")],
    "q19": [("Fairfax County", "county", None)],
    "q20": [("Boise", "place", "Idaho")],
    "q21": [],  # an informal region; the model names the counties
    "q22": [("Somerville", "place", "Massachusetts")],
    "q23": [("Austin", "place", "Texas")],
    "q24": [],
    "q25": [("Salt Lake County", "county", None)],
    "q26": [("Anchorage", "county", None)],
    "q27": [("Maricopa County", "county", None)],
    "q28": [],
    "q29": [],
    "q30": [("Hialeah", "place", None)],
    "q31": [("Nassau County", "county", "New York")],
    "q32": [],
    "q33": [("Santa Ana", "place", None)],
    "q34": [("Bozeman", "place", None)],
    "q35": [("Miami-Dade", "county", None)],
    "q36": [("Santa Cruz County", "county", "California")],
    "q37": [],
    "q38": [("Fremont", "place", "California")],
    "q39": [("Detroit", "place", "Michigan")],
    "q40": [("Cambridge", "place", "Massachusetts")],
    "q41": [("Ann Arbor", "place", None)],
    "q42": [("Fayetteville", "place", "North Carolina")],
    "q43": [("Suffolk County", "county", "New York")],
    "q44": [("Sarasota County", "county", None)],
    "t01": [("Fulton County", "county", "Georgia")],
    "t02": [],
    "t03": [],
    "t04": [],
    "t05": [("Springfield", "place", None)],
    "t06": [("Los Angeles County", "county", "California")],
    "t07": [("Phoenix", "place", "Arizona")],
    "t08": [("Travis County", "county", None)],
    "t09": [("Denver", "place", "Colorado")],
    "t10": [("Cuyahoga County", "county", None)],
    "t11": [("Middlebury", "place", "Vermont")],
    "t12": [("Fresno County", "county", None)],
    "t13": [("Wayne County", "county", "Michigan")],
    "t14": [("King County", "county", "Washington")],
    "t15": [],
    "t16": [("Denver", "place", "Colorado")],
    "t17": [("Cook County", "county", "Illinois")],
    "t18": [("Wayne County", "county", "Michigan")],
    "h01": [("Tucson", "place", "Arizona")],
    "h02": [("Dearborn", "place", "Michigan")],
    "h03": [("Cleveland", "place", "Ohio")],
    "h04": [("Buffalo", "place", "New York")],
    "h05": [],
    "h06": [("Clark County", "county", "Nevada")],
    "h07": [("Cameron County", "county", "Texas")],
    "h08": [("Portland", "place", "Maine")],
}
# Goldens that named no place: the exact phrase inserted to give them one (the diff proves it).
ADDED = {
    "t01": " in Fulton County, Georgia",
    "t06": " in Los Angeles County, California",
    "t14": " in King County, Washington",
}
# A golden whose expected behaviour IS the refusal: its place stays shared and stateless on purpose.
EXEMPT = {"t05": "expects ambiguous_place: the candidates are the answer"}


def _exact(name: str, token: str) -> bool:
    head = name.casefold().split(",", 1)[0].strip()
    return head == token.casefold() or head.startswith(f"{token.casefold()} ")


def _written(text: str, token: str, state: str) -> bool:
    """The golden's text holds the annotated state right after the place, exactly as annotated:
    "<place>, <State>" or "<place> <USPS>". A literal comparison of the fixture with its own
    annotation; nothing is read out of the wording."""
    forms = [f"{token}, {state}"]
    forms += [f"{token} {code}" for name, code, _fips in STATES if name == state.casefold()]
    padded = text + " "  # the form must end at a word edge: "Denver CO" is not in "Denver COunty"
    return any(f"{form}{edge}" in padded for form in forms for edge in " ,.?;:)")


def place_problems(goldens: list[dict[str, Any]], listing: Listing) -> list[str]:
    """Every golden is annotated; a stated state is in the text and holds that place; an unstated
    place matches at most one place nationwide (an exempt golden must still be shared)."""
    out = [
        f"{i}: annotated but not in the golden file"
        for i in sorted(set(PLACES) - {g["id"] for g in goldens})
    ]
    out += [f"{i}: exempt but not annotated" for i in sorted(set(EXEMPT) - set(PLACES))]
    for golden in goldens:
        gid, text = golden["id"], str(golden["text"])
        if gid not in PLACES:
            out.append(f"{gid}: no place annotation (add [] if it names no place)")
            continue
        for token, level, state in PLACES[gid]:
            rows = listing(level)
            hits = filter_rows(token.casefold(), rows)
            if state is not None:
                if not _written(text, token, state):
                    out.append(
                        f"{gid}: annotated state {state!r} is not in the question after {token!r}"
                    )
                if not any(
                    _exact(r["name"], token)
                    and r["name"].casefold().endswith(f", {state.casefold()}")
                    for r in hits
                ):
                    out.append(f"{gid}: no {level} {token!r} in {state}")
                continue
            if not hits:
                out.append(f"{gid}: {token!r} matches no {level} nationwide")
            if len(hits) > 1 and gid not in EXEMPT:
                where = "; ".join(sorted(r["name"] for r in hits)[:5])
                out.append(
                    f"{gid}: {token!r} matches {len(hits)} {level}s and the question writes "
                    f"no state ({where} ...)"
                )
            if len(hits) <= 1 and gid in EXEMPT:
                out.append(f"{gid}: exempt, but {token!r} now matches {len(hits)} {level}s")
    return out


def diff_problems(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[str]:
    """Same ids in the same order; only `text` may differ, and only by the inserted ", State" (or
    the one phrase ADDED to a golden that named no place)."""
    if [g["id"] for g in old] != [g["id"] for g in new]:
        return ["the golden ids or their order changed"]
    out = []
    for before, after in zip(old, new, strict=True):
        gid = after["id"]
        if {k: v for k, v in before.items() if k != "text"} != {
            k: v for k, v in after.items() if k != "text"
        }:
            out.append(f"{gid}: a field other than text changed")
        if before["text"] == after["text"]:
            continue
        inserted = [(t, s) for t, _l, s in PLACES.get(gid, []) if s]
        phrase = ADDED.get(gid)
        if not any(
            f"{t}, {s}" not in before["text"]
            and after["text"].replace(f"{t}, {s}", t, 1) == before["text"]
            for t, s in inserted
        ) and not (
            phrase
            and phrase not in before["text"]
            and after["text"].replace(phrase, "", 1) == before["text"]
        ):
            out.append(
                f"{gid}: text changed by more than the state: "
                f"{before['text']!r} -> {after['text']!r}"
            )
    return out


def grid_problems(cells: list[dict[str, Any]], listing: Listing) -> list[str]:
    """A tract cell's `expected_parents` are counties. A county name shared by several states needs
    `parent_state`, written in the question right after the last parent, and that state must hold
    every parent. County cells name states, which are unique."""
    out: list[str] = []
    for cell in cells:
        cid, state = cell["id"], cell.get("parent_state")
        if cell["level"] == "county":
            if "parent_state" in cell:
                out.append(f"{cid}: a county cell names states, which are unique: no parent_state")
            continue
        if cell["level"] != "tract":
            out.append(f"{cid}: level {cell['level']!r} is not one this check knows")
            continue
        if not cell["expected_parents"]:
            out.append(f"{cid}: a tract cell with no expected_parents")
            continue
        shared = False
        for parent in cell["expected_parents"]:
            hits = filter_rows(parent.casefold(), listing("county"))
            shared = shared or len(hits) > 1
            if not hits:
                out.append(f"{cid}: {parent!r} matches no county nationwide")
            elif state and not any(
                _exact(r["name"], parent) and r["name"].casefold().endswith(f", {state.casefold()}")
                for r in hits
            ):
                out.append(f"{cid}: no county {parent!r} in {state}")
        if shared and not state:
            out.append(f"{cid}: names a shared county and carries no parent_state")
        if state and not _written(str(cell["question"]), cell["expected_parents"][-1], state):
            out.append(
                f"{cid}: parent_state {state!r} is not in the question after the last county"
            )
    return out


def grid_diff_problems(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[str]:
    """Same cells in the same order; only `question` and a new `parent_state` may differ, and the
    question only by the inserted ", State"."""
    if [c["id"] for c in old] != [c["id"] for c in new]:
        return ["the grid cell ids or their order changed"]
    out = []
    for before, after in zip(old, new, strict=True):
        cid, state = after["id"], after.get("parent_state")
        keep = {"question", "parent_state"}
        if {k: v for k, v in before.items() if k not in keep} != {
            k: v for k, v in after.items() if k not in keep
        } or before.get("parent_state") != (state if "parent_state" in before else None):
            out.append(f"{cid}: a field other than question or a new parent_state changed")
        if before["question"] != after["question"] and not (
            state
            and f", {state}" not in before["question"]
            and after["question"].replace(f", {state}", "", 1) == before["question"]
        ):
            out.append(f"{cid}: question changed by more than the state")
    return out


def _load(ref: str | None, path: str = GOLDENS, table: str = "question") -> list[dict[str, Any]]:
    if ref is None:
        raw = (ROOT / path).read_bytes()
    else:
        raw = subprocess.run(
            ["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    return list(tomllib.loads(raw.decode("utf-8"))[table])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", help="git ref to diff the goldens against (AC2)")
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        print("CENSUS_API_KEY is not set (put it in .env); the check needs live listings")
        return 2
    cache: dict[str, list[dict[str, str]]] = {}

    def listing(level: str) -> list[dict[str, str]]:
        if level not in cache:
            cache[level] = list_census_names(level, {"state": "*"}, key=key)
        return cache[level]

    new, cells = _load(None), _load(None, GRID, "cell")
    problems = place_problems(new, listing) + grid_problems(cells, listing)
    print(
        f"{len(new)} goldens, {len(cells)} grid cells; listings: "
        + ", ".join(f"{k} {len(v)}" for k, v in cache.items())
    )
    if args.base:
        problems += diff_problems(_load(args.base), new)
        problems += grid_diff_problems(_load(args.base, GRID, "cell"), cells)
    for line in problems:
        print(f"  FAIL  {line}")
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
