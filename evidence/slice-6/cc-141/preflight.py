"""CC-141 pre-flight: which named places in the visible goldens match more than one place nationwide?

Reads no question wording: the (token, level) pairs below were annotated by hand from the goldens.
Uses the repo's own grounded NAME match (filter_rows) over live Census listings.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
CACHE = Path(sys.argv[2])
sys.path.insert(0, str(ROOT / "api"))

from src.geo_list import filter_rows, list_census_names  # noqa: E402

KEY = ""
for line in (ROOT.parent.parent / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("CENSUS_API_KEY="):
        KEY = line.split("=", 1)[1].strip().strip("\"'")

# id -> [(token, level, state written in the question or None)]
PLACES = {
    "q01": [("Harris County", "county", "Texas")],
    "q03": [("Cook County", "county", None)],
    "q04": [("Detroit", "place", None)],
    "q05": [("Portland", "place", None)],
    "q10": [("Queens", "county", None)],
    "q13": [("Providence", "place", None)],
    "q14": [("Baltimore City", "county", None)],
    "q16": [("Ithaca", "place", None)],
    "q18": [("Milwaukee", "place", None)],
    "q19": [("Fairfax County", "county", None)],
    "q20": [("Boise", "place", None)],
    "q22": [("Somerville", "place", "Massachusetts")],
    "q23": [("Austin", "place", None)],
    "q25": [("Salt Lake County", "county", None)],
    "q26": [("Anchorage", "county", None)],
    "q27": [("Maricopa County", "county", None)],
    "q30": [("Hialeah", "place", None)],
    "q31": [("Nassau County", "county", None)],
    "q33": [("Santa Ana", "place", None)],
    "q34": [("Bozeman", "place", None)],
    "q35": [("Miami-Dade", "county", None)],
    "q36": [("Santa Cruz County", "county", None)],
    "q38": [("Fremont", "place", None)],
    "q39": [("Detroit", "place", None)],
    "q40": [("Cambridge", "place", None)],
    "q41": [("Ann Arbor", "place", None)],
    "q42": [("Fayetteville", "place", None)],
    "q43": [("Suffolk County", "county", None)],
    "q44": [("Sarasota County", "county", None)],
    "t05": [("Springfield", "place", None)],
    "t07": [("Phoenix", "place", None)],
    "t08": [("Travis County", "county", None)],
    "t09": [("Denver", "place", None)],
    "t10": [("Cuyahoga County", "county", None)],
    "t11": [("Middlebury", "place", "Vermont")],
    "t12": [("Fresno County", "county", None)],
    "t13": [("Wayne County", "county", None)],
    "t16": [("Denver", "place", None)],
    "t17": [("Cook County", "county", "Illinois")],
    "t18": [("Wayne County", "county", None)],
    "h01": [("Tucson", "place", None)],
    "h02": [("Dearborn", "place", None)],
    "h03": [("Cleveland", "place", None)],
    "h04": [("Buffalo", "place", None)],
    "h06": [("Clark County", "county", None)],
    "h07": [("Cameron County", "county", None)],
    "h08": [("Portland", "place", "Maine")],
}


def listing(level: str) -> list[dict[str, str]]:
    path = CACHE / f"{level}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    rows = list_census_names(level, {"state": "*"}, key=KEY)
    path.write_text(json.dumps(rows), encoding="utf-8")
    return rows


out = {}
for qid, entries in PLACES.items():
    for token, level, state in entries:
        rows = listing(level)
        hits = filter_rows(token.casefold(), rows)
        names = sorted(r["name"] for r in hits)
        out[qid] = (token, level, state, len(hits), names)
        flag = "SHARED" if len(hits) > 1 else ("none" if not hits else "unique")
        shown = "; ".join(names[:6]) + (" ..." if len(names) > 6 else "")
        print(f"{qid} {token!r:22} {level:6} state={state!s:13} matches={len(hits):3} {flag:6} {shown}")
print(f"\nrows: county={len(listing('county'))} place={len(listing('place'))}")
