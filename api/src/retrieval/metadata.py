"""ACS metadata: fetch once, cache to disk, read from cache.

Everything in slice 0 is a join over three files per vintage — `groups.json`,
`variables.json`, `geography.json`. None of them needs an API key and none of
them runs at request time: the index is built offline and shipped as a pinned
artifact (DESIGN section 5).

`geography.json` is the authority on which `for`/`in` combinations are legal.
The agent looks them up here rather than reasoning about nesting from memory —
an invented `for=zcta:*&in=county:X` returns a 400 the model then "fixes" by
inventing a different wrong call.
"""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "raw"

BASE = "https://api.census.gov/data"
DATASETS = ("acs5", "acs1")
FILES = ("groups", "variables", "geography")

# 2016 is the first vintage in scope. Earlier ACS exists, but the computer and
# internet tables were reworked mid-decade and the product does not claim them.
FIRST_VINTAGE = 2016


@dataclass(frozen=True)
class Table:
    """One table group, as one vintage describes it."""

    table_id: str
    title: str
    universe: str


@dataclass(frozen=True)
class Variable:
    variable_id: str
    table_id: str
    label: str
    concept: str


@dataclass(frozen=True)
class GeoLevel:
    """One row of `geography.json` — a level and what it must nest inside.

    The file repeats a name at several summary levels (`county` is 050, 313,
    316, 322, 324). Callers that need a legal `for`/`in` form must scan every
    row, not a name-keyed dict: last-wins on `county` is 324 and rejects
    `for=county:*&in=state:41`.
    """

    name: str
    code: str
    requires: tuple[str, ...]
    wildcard: tuple[str, ...]
    wildcard_for: str = ""


# `B19013A` (Black householder), `B06007PR` (Puerto Rico). Exactly five digits
# then an optional A-I iteration letter and an optional PR suffix, so a real
# table like `B18135` is never mistaken for one.
_FAMILY = re.compile(r"^([BC]\d{5})[A-I]?(?:PR)?$")


# B00* unweighted sample counts, B98* imputation, B99* allocation rates. These
# describe how the SURVEY performed, not what it measured, and no user question
# is ever about them. Left in, they answer "how many people are naturalized
# citizens" with B99053, Allocation of Year of Naturalization.
_SURVEY_QUALITY = re.compile(r"^[BC](00|98|99)")


def is_subject_table(table_id: str) -> bool:
    return not _SURVEY_QUALITY.match(table_id)


def family_id(table_id: str) -> str:
    """`B19013A` -> `B19013`. `C16001` -> `C16001`.

    A race iteration is its parent table under a filter, and a Puerto Rico
    variant is the same table for one geography. They carry near-identical
    titles and universes, so indexing them separately puts 500-odd
    near-duplicates in a 1,458-table corpus, where they crowd out the very
    table they are derived from: "crowded housing" ranked `B25014G` above
    `B25014`.

    Collapsing them is not a ranking trick. It is the table-family structure
    from the domain rules, and the members become the `alternatives[]` a
    response owes the user — the `C` collapsed tables stay separate because
    they are genuinely different tables, not filtered views.
    """
    match = _FAMILY.match(table_id)
    return match.group(1) if match else table_id


def cache_path(dataset: str, year: int, name: str) -> Path:
    root = CACHE.resolve()
    path = (CACHE / dataset / str(year) / f"{name}.json.gz").resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"dataset {dataset!r} is not a cache path")
    return path


def _read(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload: dict[str, Any] = json.load(handle)
    return payload


def fetch(client: httpx.Client, dataset: str, year: int, name: str) -> dict[str, Any] | None:
    """Download one metadata file, or read the cached copy. None means 404.

    A 404 is how the caller discovers where a dataset stops; it is not an error.
    """
    path = cache_path(dataset, year, name)
    if path.exists():
        return _read(path)

    response = client.get(f"{BASE}/{year}/acs/{dataset}/{name}.json")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload: dict[str, Any] = response.json()

    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return payload


def fetch_all(*, first: int = FIRST_VINTAGE) -> dict[str, list[int]]:
    """Cache every file for every vintage in scope. Returns what exists.

    Probes the whole range and never stops at the first miss. ACS1 has a hole
    at 2020 — the standard release was never issued — and stopping there would
    silently drop 2021 onward. A missing vintage in the middle of a range is
    the fact this product has to report, not a reason to stop looking.
    """
    found: dict[str, list[int]] = {}
    horizon = datetime.now(UTC).year + 1
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        for dataset in DATASETS:
            years: list[int] = []
            for year in range(first, horizon + 1):
                if fetch(client, dataset, year, "groups") is None:
                    continue
                for name in FILES[1:]:
                    fetch(client, dataset, year, name)
                years.append(year)
            found[dataset] = years
    return found


def cached_vintages(dataset: str) -> list[int]:
    root = CACHE / dataset
    if not root.exists():
        return []
    return sorted(int(p.name) for p in root.iterdir() if p.is_dir() and p.name.isdigit())


def tables(dataset: str, year: int) -> dict[str, Table]:
    payload = _read(cache_path(dataset, year, "groups"))
    result: dict[str, Table] = {}
    for group in payload.get("groups", []):
        table_id = str(group.get("name", "")).strip()
        if not table_id:
            continue
        # The API really does emit "universe " with a trailing space. Both keys
        # have been seen; take whichever is present rather than guessing.
        universe = group.get("universe") or group.get("universe ") or ""
        result[table_id] = Table(
            table_id=table_id,
            title=str(group.get("description", "")).strip(),
            universe=str(universe).strip(),
        )
    return result


def variables(dataset: str, year: int) -> dict[str, Variable]:
    """Estimate variables only.

    `variables.json` also carries `for`, `in`, `ucgid` and the `M`/`EA`/`MA`
    companions. The `E` variables are what a question is about; the margins are
    fetched alongside at request time and add nothing to retrieval.
    """
    payload = _read(cache_path(dataset, year, "variables"))
    result: dict[str, Variable] = {}
    for variable_id, meta in payload.get("variables", {}).items():
        if not isinstance(meta, dict) or not variable_id.endswith("E"):
            continue
        table_id = str(meta.get("group", "")).strip()
        if not table_id or table_id == "N/A":
            continue
        result[variable_id] = Variable(
            variable_id=variable_id,
            table_id=table_id,
            label=str(meta.get("label", "")),
            concept=str(meta.get("concept", "")),
        )
    return result


def _geo_level(entry: dict[str, Any]) -> GeoLevel | None:
    name = str(entry.get("name", "")).strip()
    if not name:
        return None
    return GeoLevel(
        name=name,
        code=str(entry.get("geoLevelDisplay", "")),
        requires=tuple(entry.get("requires") or ()),
        wildcard=tuple(entry.get("wildcard") or ()),
        wildcard_for=str(entry.get("optionalWithWCFor") or ""),
    )


def geo_entries(dataset: str, year: int) -> list[GeoLevel]:
    """Every `fips` row. Names repeat; this is the legality table."""
    payload = _read(cache_path(dataset, year, "geography"))
    return [level for entry in payload.get("fips", []) if (level := _geo_level(entry))]


def geo_levels(dataset: str, year: int) -> dict[str, GeoLevel]:
    """Name -> last row with that name. Existence checks only — not legality."""
    result: dict[str, GeoLevel] = {}
    for level in geo_entries(dataset, year):
        result[level.name] = level
    return result
