#!/usr/bin/env python3
"""CC-114: classify geography-level mismatches by the rule in evidence/slice-6/cc-114-rule.md.

    uv run python scripts/classify_geo_levels.py

The golden audit (every golden with `expect_geo_level`) reads only question text,
`expect_*` fields, ACS metadata and Census reference files. Trial outcomes are read
only afterwards, to place each mismatched trial in a bucket.
"""

from __future__ import annotations

import io
import json
import re
import sys
import tomllib
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from src.retrieval import metadata  # noqa: E402

CACHE = ROOT / "data" / "raw" / "census_ref"
GAZ = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gaz_"
PBC = "https://www2.census.gov/geo/docs/reference/codes2020/place_by_cou/"
BAND = (0.99, 1.01)
LEVEL_WORDS = {
    "tract": "tract",
    "tracts": "tract",
    "county": "county",
    "counties": "county",
    "state": "state",
    "metro": "metropolitan statistical area/micropolitan statistical area",
    "zip": "zip code tabulation area",
    "zcta": "zip code tabulation area",
}
# Rule 4: expected level per leg for multi-geography questions.
MULTI_LEG = {"q23": ["place", "state"]}
# Rule 2: the bare name in the question -> (gazetteer name, state or None, exact match).
# A state is given only where the question names it; otherwise every same-name place
# must be coterminous, which is the conservative reading.
ENTITY = {
    "q05": ("Portland", None, False),
    "q10": ("Queens", None, False),
    "q13": ("Providence", None, False),
    "q14": ("Baltimore city", None, True),
    "q16": ("Ithaca", None, False),
    "q18": ("Milwaukee", None, False),
    "q20": ("Boise", None, False),
    "q22": ("Somerville", "MA", False),
    "q26": ("Anchorage", None, False),
    "q30": ("Hialeah", None, False),
    "q33": ("Santa Ana", None, False),
    "q34": ("Bozeman", None, False),
    "q35": ("Miami-Dade", None, False),
    "q38": ("Fremont", None, False),
    "q39": ("Detroit", None, False),
    "q40": ("Cambridge", None, False),
    "q41": ("Ann Arbor", None, False),
    "q42": ("Fayetteville", None, False),
    "t09": ("Denver", None, False),
    "t11": ("Middlebury", "VT", False),
    "q23": ("Austin", "TX", False),
    "h01": ("Tucson", None, False),
    "h02": ("Dearborn", None, False),
    "h03": ("Cleveland", None, False),
    "h04": ("Buffalo", None, False),
    "h08": ("Portland", "ME", False),
}
STATE_ENTITIES = {"q12", "q28", "q29", "q32", "h05"}  # a bare state name


def fetch(url: str, name: str) -> bytes:
    path = CACHE / name
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(urlopen(url, timeout=60).read())
    return path.read_bytes()


def gazetteer(kind: str) -> list[dict[str, str]]:
    raw = zipfile.ZipFile(io.BytesIO(fetch(f"{GAZ}{kind}_national.zip", f"{kind}.zip")))
    lines = raw.read(raw.namelist()[0]).decode("latin-1").splitlines()
    head = [h.strip() for h in lines[0].split("\t")]
    return [dict(zip(head, (c.strip() for c in ln.split("\t")), strict=False)) for ln in lines[1:]]


def base(name: str) -> str:
    out = name.lower()
    while True:
        new = re.sub(
            r"\s+(city|town|village|cdp|borough|municipality|county|\(balance\)|"
            r"and borough|consolidated government)$",
            "",
            out,
        )
        if new == out:
            return out
        out = new


def place_counties(
    usps: str, fips: str, cache: dict[str, dict[str, set[str]]]
) -> dict[str, set[str]]:
    if fips not in cache:
        text = fetch(
            f"{PBC}st{fips}_{usps.lower()}_place_by_county2020.txt", f"pbc_{fips}.txt"
        ).decode("latin-1")
        rows: dict[str, set[str]] = defaultdict(set)
        for ln in text.splitlines()[1:]:
            cols = ln.split("|")
            if len(cols) > 4:
                rows[cols[1] + cols[4]].add(cols[1] + cols[2])
        cache[fips] = rows
    return cache[fips]


def coterminous(entity: tuple[str, str | None, bool]) -> tuple[bool, bool, str]:
    """Rule 2: (strict, any, note). Strict (binding): every same-name place is coterminous
    with its one county. Any (shown beside it, not a verdict): at least one is."""
    name, state, exact = entity
    places, counties = gazetteer("place"), {c["GEOID"]: c for c in gazetteer("counties")}
    want = name.lower()
    hits = [
        p
        for p in places
        if (p["NAME"].lower() == want if exact else base(p["NAME"]) == want)
        and (state is None or p["USPS"] == state)
    ]
    if not hits:
        return False, False, "no same-name place in the Gazetteer"
    cache: dict[str, dict[str, set[str]]] = {}
    notes, ok, some = [], True, False
    for p in hits:
        in_counties = place_counties(p["USPS"], p["GEOID"][:2], cache).get(p["GEOID"], set())
        if len(in_counties) != 1:
            ok = False
            notes.append(f"{p['NAME']}, {p['USPS']}: {len(in_counties)} counties")
            continue
        county = counties[next(iter(in_counties))]
        ratio = float(p["ALAND"]) / float(county["ALAND"])
        inside = BAND[0] <= ratio <= BAND[1]
        ok, some = ok and inside, some or inside
        notes.append(f"{p['NAME']}, {p['USPS']} / {county['NAME']}: {ratio:.4f}")
    return ok, some, "; ".join(notes)


def named_level(text: str) -> str | None:
    text = re.sub(r"\b(another|other) state\b", "", text, flags=re.I)
    found = re.search(r"\b(tracts?|count(?:y|ies)|metro|zip|zcta|state)\b", text, re.I)
    return LEVEL_WORDS[found.group(1).lower()] if found else None


def fetched_level(url: str) -> str:
    return parse_qs(urlparse(url).query).get("for", [""])[0].split(":")[0]


def split_urls(joined: str) -> list[str]:
    """run_demo stores every fetched URL in one space-separated string; split at URL starts."""
    return re.split(r"\s+(?=https?://)", joined.strip())


def served(dataset: str, level: str) -> bool:
    return any(level in metadata.geo_levels(dataset, y) for y in metadata.cached_vintages(dataset))


def audit(entry: dict) -> dict:
    """Outcome-independent. `rule` is the first rule that applies (1-4, or 6)."""
    gid, expect = entry["id"], entry["expect_geo_level"]
    named = named_level(entry["text"])
    out = {"id": gid, "golden": expect, "rule": 6, "note": "informal region, no entity to test"}
    if gid in MULTI_LEG:
        out.update(rule=4, note=f"legs {MULTI_LEG[gid]}; golden has one level")
    elif named:
        out.update(rule=1, expected=named, note=f"names {named!r}")
    elif gid in STATE_ENTITIES:
        out.update(rule=2, expected="state", arguable=False, note="bare state name")
    elif gid in ENTITY:
        ok, some, why = coterminous(ENTITY[gid])
        out.update(rule=2, expected=expect, arguable=ok, arguable_any=some, note=why)
    return out


def classify(trial: dict, a: dict, *, any_reading: bool = False) -> tuple[str, str]:
    levels = sorted({fetched_level(u) for u in trial["urls"]})
    dataset = "acs1" if "/acs1" in trial["url"] else "acs5"
    if a["rule"] == 4:
        return "golden_misspecified", f"fetched {levels}; legs {MULTI_LEG[a['id']]}"
    if a["rule"] == 6:
        return "unclassified", f"fetched {levels}"
    if not served(dataset, a["expected"]):
        return "table_cannot_serve", f"{dataset} lacks {a['expected']!r}"
    arguable = a.get("arguable_any" if any_reading else "arguable")
    if a["rule"] == 2 and arguable and set(levels) <= {"place", "county"}:
        return "golden_arguable", f"coterminous: {a['note']}"
    return "pipeline_wrong", f"expected {a['expected']!r}, fetched {levels}"


def main() -> int:
    if not any(metadata.cached_vintages(d) for d in metadata.DATASETS):
        print("No cached metadata. Run scripts/fetch_metadata.py first.")
        return 1
    goldens = tomllib.loads((ROOT / "evals" / "golden_questions.toml").read_text("utf-8"))
    entries = {e["id"]: e for e in goldens["question"] if e.get("expect_geo_level")}
    audits = {gid: audit(e) for gid, e in entries.items()}
    demo = json.loads((ROOT / "evidence" / "latest.json").read_text("utf-8"))["demo"]
    lines = [
        "# CC-114 classification",
        "",
        "Rule: `evidence/slice-6/cc-114-rule.md`. "
        "Command: `uv run python scripts/classify_geo_levels.py`.",
        f"Trials: `evidence/latest.json` generated {demo['generated_at']}, "
        f"--repeat {demo['repeat']}, n={demo['n']}.",
        "",
        "## Golden audit (all goldens, outcome-blind)",
        "",
        "| id | golden | rule | expected by rule | note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for a in audits.values():
        flag = " **differs**" if a.get("expected") not in (None, a["golden"]) else ""
        lines.append(
            f"| {a['id']} | {a['golden']} | {a['rule']} | {a.get('expected', '-')}{flag}"
            f" | {a['note']} |"
        )
    lines += [
        "",
        "## Mismatched trials",
        "",
        "| id | repeat | bucket | detail | url |",
        "| --- | --- | --- | --- | --- |",
    ]
    counts: Counter[str] = Counter()
    alt: Counter[str] = Counter()
    for trial in demo["trials"]:
        if "wrong geography level" not in trial["detail"]:
            continue
        trial = {**trial, "urls": split_urls(trial["url"])}
        bucket, why = classify(trial, audits[trial["id"]])
        other, _ = classify(trial, audits[trial["id"]], any_reading=True)
        counts[bucket] += 1
        alt[other] += 1
        if other != bucket:
            why += f" [any-coterminous reading: {other}]"
        warned = f" (warnings: {', '.join(trial['warnings'])})" if trial["warnings"] else ""
        lines.append(
            f"| {trial['id']} | {trial['repeat']} | {bucket} | {why}{warned} | `{trial['url']}` |"
        )
    lines += [
        "",
        "## Totals",
        "",
        *(f"- {k}: {v}" for k, v in sorted(counts.items())),
        f"- total mismatched trials: {sum(counts.values())}",
        "",
        "Any-coterminous reading (not a verdict; rule amendment 2):",
        "",
        *(f"- {k}: {v}" for k, v in sorted(alt.items())),
        "",
    ]
    out = ROOT / "evidence" / "slice-6" / "cc-114-classification.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[-8:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
