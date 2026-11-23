#!/usr/bin/env python3
"""Check that no visible golden names a shared place without its state (CC-141).

    python scripts/verify_golden_places.py [--base origin/main]

A place name that matches more than one place nationwide, with no state the user wrote, is
refused by the product (CC-104). A golden that asks such a question measures the refusal, not the
retrieval. Each golden's places are annotated below by hand (the script never reads the question's
words to find a place); the match is the resolver's own `filter_rows` over live Census listings at
the level the golden expects. Needs CENSUS_API_KEY. With --base REF it also proves the edit changed
only the state: per id every field but `text` is equal, and `text` minus the inserted ", State" is
the old text. Exits non-zero on any problem.
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
    "t01": [],
    "t02": [],
    "t03": [],
    "t04": [],
    "t05": [("Springfield", "place", None)],
    "t06": [],
    "t07": [("Phoenix", "place", "Arizona")],
    "t08": [("Travis County", "county", None)],
    "t09": [("Denver", "place", "Colorado")],
    "t10": [("Cuyahoga County", "county", None)],
    "t11": [("Middlebury", "place", "Vermont")],
    "t12": [("Fresno County", "county", None)],
    "t13": [("Wayne County", "county", "Michigan")],
    "t14": [],
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
    return any(form in text for form in forms)


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
    """Same ids in the same order; only `text` may differ, and only by the inserted ", State"."""
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
        if not any(
            f"{t}, {s}" not in before["text"]
            and after["text"].replace(f"{t}, {s}", t, 1) == before["text"]
            for t, s in inserted
        ):
            out.append(
                f"{gid}: text changed by more than the state: "
                f"{before['text']!r} -> {after['text']!r}"
            )
    return out


def _load(ref: str | None) -> list[dict[str, Any]]:
    if ref is None:
        raw = (ROOT / GOLDENS).read_bytes()
    else:
        raw = subprocess.run(
            ["git", "show", f"{ref}:{GOLDENS}"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    return list(tomllib.loads(raw.decode("utf-8"))["question"])


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

    new = _load(None)
    problems = place_problems(new, listing)
    print(f"{len(new)} goldens; listings: " + ", ".join(f"{k} {len(v)}" for k, v in cache.items()))
    if args.base:
        problems += diff_problems(_load(args.base), new)
    for line in problems:
        print(f"  FAIL  {line}")
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
