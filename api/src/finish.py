"""Finish the four-tool contract when the model stops short of a URL."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.tools import BaseTool

from src.contract import clauses_from_geoid
from src.geo import detect_level, split_comparison
from src.guards import universe_mismatch
from src.vintages import latest_vintages, pinned_table, requested_years, wants_acs1

Dispatch = Callable[..., Awaitable[str]]
Complete = Callable[[list[dict[str, Any]], list[dict[str, Any]]], Awaitable[dict[str, Any]]]

_SPLIT_PARENTS = (
    'Reply with only JSON {"parents": [...], "unit": ..., "listing": bool, "level": ..., '
    '"named": [...], "county_named": bool, "numbered": [...], "asks_for": ..., '
    '"pointing": [...]}. parents are the '
    "places the user names, one entry each, whatever word connects them. A place and its own "
    "state are one parent: write any place smaller than a state as 'Name, State' with the state "
    "from your own knowledge (such as 'Lancaster County, Nebraska'), never as two entries and "
    "never without its state. "
    "Name a state alone. unit is county, tract, block group, zcta or place: the kind of row "
    "the user wants. listing is true when they want a row for every unit inside the parents, "
    "false when they want the parents themselves. "
    "level is the geography level the question asks about (state, county, place, tract, block "
    "group, zcta), or null when it asks about none; a question about a tract, block group or "
    "county by number asks about that level. named lists every place the question identifies by "
    "its own name or code: a state, county, city, ZIP code or other place, such as 'Lancaster "
    "County, Nebraska' or 'state 39'. A place given by a code that identifies it on its own, "
    "such as 'FIPS 39049', 'GEOID 06037' or a ZIP code, goes in named as the user wrote the "
    "code; never replace a code with a name. A tract, block group or county number alone is not "
    "such a code. 'my county' or 'the city' names no place, so leave it out. "
    "numbered lists every place the question identifies only by "
    "a number inside some other place, such as 'tract 12', 'block group 3' or 'county 5': those "
    "numbers repeat in many places, so they never go in named, wherever they sit in the "
    "sentence, even as its first words. Copy both exactly as the user "
    "wrote them. Use an empty list when there are none. "
    "A state, ZIP code or GEOID is never numbered. asks_for is 'tables' when the question asks "
    "which table or variable holds something or where to find it, and 'data' when it asks for "
    "figures. pointing lists, copied exactly as written, each phrase that stands in for a place "
    "by pointing at it, as in 'my county' or 'where I live'; a number such as 'tract 12' is not "
    "pointing, and the list is empty when no phrase points; such a phrase is never a parent. "
    "county_named is true when the question names a specific county, by its name or by a "
    "five-digit FIPS code (state and county)."
)

_SPLIT_UNITS = frozenset({"county", "tract", "block group", "zcta", "place"})
SPLIT_WAIT_SECONDS = 6.0  # the call normally finishes beside the loop; never delay an answer more
FRAME_WAIT_SECONDS = 3.0  # before the first tool runs; past it the question is treated as complete

_LISTING = re.compile(
    r"\b(?:all|every|each)\s+(?:census\s+)?(block groups?|tracts?)\b|"
    r"\b(?:census\s+)?(block groups?|tracts?)\s+(?:within|inside)\b",
    re.I,
)
_BY_COUNTY = re.compile(
    r"\bby\s+(?:census\s+)?(block groups?|tracts?)\s+in\s+"
    r"((?:(?!(?:19|20)\d{2}).)*?\bcount(?:y|ies)\b"
    r"(?:\s*,\s*(?!(?:19|20)\d{2})[A-Za-z][A-Za-z.' -]*?)?)"
    r"(?=\s*,\s*(?:19|20)\d{2}|\s*$|[.?!])",
    re.I,
)


def _latest(record: Any) -> int:
    getter = getattr(record, "published_vintages", None)
    if callable(getter):
        years = getter("acs5")
        if years:
            return max(int(year) for year in years)
    acs5, _acs1 = latest_vintages()
    return acs5


def _listing_level(question: str) -> str | None:
    match = _LISTING.search(question) or _BY_COUNTY.search(question)
    if not match:
        return None
    raw = next((group for group in match.groups() if group), "")
    return "block group" if raw.casefold().startswith("block") else "tract"


def _listing_query(question: str) -> str:
    match = _BY_COUNTY.search(question)
    if not match:
        return question
    return f"every {match.group(1)} in {match.group(2).strip()}"


def _wrong_listing(record: Any, question: str) -> bool:
    wanted = _listing_level(question)
    geos = list(getattr(record, "geographies", []) or [])
    if wanted is None:
        return False
    return not geos or geos[0].level != wanted


def _wrong_comparison(record: Any, question: str) -> bool:
    status = getattr(record, "geo_status", None) or {}
    queries = list(getattr(record, "geo_queries", None) or [])
    if len(queries) >= 2 and not status.get("compare"):
        return True
    sides = split_comparison(question)
    if sides is None:
        return False
    return int(status.get("compare_count", 0) or 0) < len(sides)


def degraded_answer(record: Any) -> str:
    names = sorted({str(row.get("NAME") or "") for row in record.rows} - {""})
    place = f" for {', '.join(names)}" if names else ""
    return f"Recovered {record.table_id} data{place} after a retry; see the table and URL below."


def _all_wild(geos: list[Any]) -> bool:
    return bool(geos) and all(g.for_spec.endswith(":*") for g in geos)


_SNAPSHOT = ("geographies", "geo_status", "geography", "geo_queries", "url", "rows") + (
    "fetch",
    "table_id",
    "universe",
    "vintages",
    "retained_urls",
)


async def plan_split(question: str, complete: Complete | None) -> dict[str, Any] | None:
    """Ask the model to split the question's parents; return validated parts or None.

    Needs only the question, so run_ask starts it beside the loop as a task.
    """
    if complete is None:
        return None
    try:
        turn = await complete(
            [{"role": "system", "content": _SPLIT_PARENTS}, {"role": "user", "content": question}],
            [],
        )
        raw = str(turn.get("content") or "")
        found = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        names, unit = found.get("parents"), str(found.get("unit") or "")
    except Exception:  # noqa: BLE001 - a failed repair must never fail the answer
        return None
    named, numbered = found.get("named"), found.get("numbered")
    names = names if isinstance(names, list) else []  # a model can send anything; use only lists
    frame = {
        "level": found.get("level"),
        "named": [*(named if isinstance(named, list) else []), *names],
        "numbered": numbered if isinstance(numbered, list) else [],
        "asks_for": found.get("asks_for") if isinstance(found.get("asks_for"), str) else None,
        "county_named": found.get("county_named") is True,
        "pointing": found["pointing"] if isinstance(found.get("pointing"), list) else [],
    }
    if not (found.get("listing") and unit in _SPLIT_UNITS):
        return {"frame": frame}
    parents = [name.strip() for name in names if isinstance(name, str) and name.strip()]
    parents = list({name.casefold(): name for name in parents}.values())
    return (
        {"parents": parents, "unit": unit, "frame": frame}
        if len(parents) >= 2
        else {"frame": frame}
    )


@asynccontextmanager
async def split_beside(
    question: str, complete: Complete | None, enabled: bool
) -> AsyncIterator[asyncio.Task[dict[str, Any] | None] | None]:
    """Run plan_split beside the caller's work; always cancel and reap it on exit."""
    task = asyncio.create_task(plan_split(question, complete)) if enabled and complete else None
    try:
        yield task
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def _key(text: str) -> str:
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text.casefold()).split())


MAX_REPORTED = 25  # a question names a handful of places; a longer report is not read past this


# The minimum the Census API accepts for the kind of question asked, measured against the live API
# (ACS 5-year 2023). A "single" unit is one identified by its number, which repeats across its
# parent, and a county wildcard is refused for it ("wildcard mismatch"), so its parents must be
# real. A listing needs only what the wildcards cannot supply: every tract or block group in a
# state needs the state, if the URL writes `county:*` itself (leaving it out is HTTP 400).
# Anything not listed needs nothing: all counties and all places list with no parent at all.
# It is geography.json `requires` less the parents `wildcard` lets a listing leave to the URL.
_NEEDS: dict[tuple[str, bool], tuple[str, ...]] = {
    ("tract", False): ("state",),
    ("block group", False): ("state",),
    ("county", True): ("state",),
    ("place", True): ("state",),
    ("tract", True): ("state", "county"),
    ("block group", True): ("state", "county", "tract"),
}
_ORDER = ("state", "county", "place", "tract", "block group")


def _join(parts: list[str]) -> str:
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]


async def incomplete(record: Any, split: asyncio.Task[dict[str, Any] | None] | None) -> str | None:
    """The answer to return at once when a question lacks what its geography level needs.

    The model reports the level, the places the question names (each written with its state), the
    places it identifies only by a number inside another, whether a county is named, and whether
    it asks for tables (the split call, beside the loop). Code compares that with `_NEEDS` for the
    kind of question asked: every tract needs the state, one tract by its number needs state and
    county, and so on. It does not second-guess a name against the question's words: measured
    live, that refused 38 of 60 valid questions that wrote a state as "Calif.", "Penn" or "tx". A
    wrong report only lets a trap through, which is where the loop already was. Call it on the
    first turn only, before any tool runs. It fails open on anything: no verdict, no model, or a
    late report means the loop runs as usual.
    """
    if split is None:
        return None
    try:
        found = await asyncio.wait_for(asyncio.shield(split), FRAME_WAIT_SECONDS)
    except Exception:  # noqa: BLE001 - a failed check must never fail the answer
        return None
    frame = (found or {}).get("frame") or {}
    if str(frame.get("asks_for") or "").strip().casefold() == "tables":
        record.tables_only = True  # no geography is wanted, so none is flagged later
        return None  # which table holds something is not a search by geography
    question = str(getattr(record, "question", "") or "")
    padded = f" {_key(question)} "
    pointing = [p for p in frame.get("pointing") or [] if isinstance(p, str)][:MAX_REPORTED]
    if any(_key(p) and f" {_key(p)} " in padded for p in pointing):
        record.geo_status = {"legal": False, "detail": "a place is not named", "nested": True}
        return (
            "This question is incomplete and cannot be searched: it is about a place it does "
            "not name. Name the place, with its state, and ask again."
        )
    numbered = [n for n in frame.get("numbered") or [] if isinstance(n, str)][:MAX_REPORTED]
    reported = [n for n in frame.get("named") or [] if isinstance(n, str)][:MAX_REPORTED]
    skip, parts, written = set(), [], []
    for entry in numbered:
        # "Census Tract 9501, Dane County": the number is skipped, its parents are named. A number
        # can make a question incomplete (a refusal), so it must be one the user wrote.
        first, *parents = entry.split(",")
        skip.add(_key(first))
        if _key(first) and f" {_key(first)} " in padded:
            written.append(detect_level(first))
        parts.extend(parents)
    parts.extend(part for entry in reported for part in entry.split(","))
    named = [part for part in parts if _key(part) and _key(part) not in skip]
    units = [lv for lv in written if lv]  # each number is judged at its own unit's level
    # A tract or block group given by its number says its own level when the model gave none.
    level = detect_level(str(frame.get("level") or "")) or next(iter(units), None)
    need = _NEEDS.get((level or "", False), ())
    if units:
        need = tuple(p for p in _ORDER if any(p in _NEEDS.get((lv, True), ()) for lv in units))
    # Every place the model names is written with its state ("Name, State"), so any name gives the
    # state; the county and tract are what the model reports apart.
    have = {"state"} if named else set()
    if frame.get("county_named") is True or "county" in written:
        have.add("county")
    if "tract" in written:
        have.add("tract")
    for part in named:  # a GEOID in the report carries the hierarchy it encodes (parsing only)
        coded = clauses_from_geoid(part)
        if coded:
            have |= {coded[0], *(clause.split(":")[0] for clause in coded[2].split("+") if clause)}
    missing = [part for part in need if part not in have]
    if not missing:
        return None
    unit = level if level in units else next(iter(units), None)
    asked = f"a {level} identified by its number" if unit == level else f"every {level}"
    if unit and unit != level:
        asked += f" in a {unit} identified by its number"
    given = [lv for lv in _ORDER if lv in have and lv != unit]  # the unit itself is no parent
    names = f"only the {_join(given)}" if given else "no geography"
    detail = f"{asked} needs {_join(list(need))}; the question names {names}"
    record.geo_status = {"legal": False, "detail": detail, "nested": True}
    return (
        f"This question is incomplete and cannot be searched: {asked} needs "
        f"{_join(list(need))}, and it names {names}. Name the {_join(missing)} and ask again."
    )


async def _split_parents(
    dispatch: Dispatch, geo: BaseTool | None, record: Any, question: str, found: Any
) -> bool:
    """Re-resolve a multi-parent listing the loop got wrong with the model's parents."""
    geos = list(getattr(record, "geographies", []) or [])
    if not (found and found.get("parents") and geo):
        return False
    parents, unit = found["parents"], found["unit"]
    if _all_wild(geos) and len(parents) <= len(geos):
        return False
    before = {name: getattr(record, name) for name in _SNAPSHOT}
    before["geo_queries"] = list(record.geo_queries)
    args: dict[str, Any] = {"query": f"every {unit} in {', '.join(parents)}", "parents": parents}
    if wants_acs1(question):
        args["dataset"] = "acs1"
    try:
        await dispatch(geo, {"id": "resolve_geography", "args": args}, record)
    except Exception:  # noqa: BLE001 - keep the loop's own resolution
        record.geographies = []
    record.consecutive_failures.pop("resolve_geography", None)
    after = getattr(record, "geo_status", None) or {}
    legal = after.get("legal") is not False and after.get("nested") is not False
    chosen = record.geographies[: len(parents)]  # the rest are ambiguity candidates
    if legal and len(chosen) == len(parents) and _all_wild(chosen):
        record.url, record.rows, record.fetch = None, [], None  # never show the old parent's data
        return True
    for name, value in before.items():
        setattr(record, name, value)
    return False


async def finish_tools(
    dispatch: Dispatch,
    tools: dict[str, BaseTool],
    record: Any,
    split: Awaitable[dict[str, Any] | None] | None = None,
) -> None:
    """Search, resolve, build, and fetch when the loop stopped without a URL."""
    question = str(getattr(record, "question", "") or "")
    record.consecutive_failures.clear()
    year = _latest(record)
    geo = tools.get("resolve_geography")
    url = getattr(record, "url", None)
    plan = getattr(record, "override", None)
    try:
        found = await asyncio.wait_for(split, SPLIT_WAIT_SECONDS) if split is not None else None
    except TimeoutError:
        found = None
    redone = plan is None and await _split_parents(dispatch, geo, record, question, found)
    redo = redone or _wrong_listing(record, question) or _wrong_comparison(record, question)
    redo = redo or bool(wants_acs1(question) and (url is None or "/acs/acs1" not in str(url)))
    if plan is not None and plan.geographies:
        redo = False
    if not url or redo:
        pin = pinned_table(question)
        search = tools.get("search_tables")
        if search is not None and (
            not record.pool
            or (pin is not None and all(hit["table_id"] != pin for hit in record.pool))
        ):
            await dispatch(search, {"id": "search_tables", "args": {"question": question}}, record)
        if geo is not None and not redone and (redo or not record.geographies):
            status = getattr(record, "geo_status", None) or {}
            queries = list(getattr(record, "geo_queries", None) or [])
            args: dict[str, Any] = (
                {"places": queries}
                if len(queries) >= 2 and not status.get("compare")
                else {"query": _listing_query(question)}
            )
            if wants_acs1(question):
                args["dataset"] = "acs1"
            await dispatch(geo, {"id": "resolve_geography", "args": args}, record)
        if geo is not None and not record.geographies and universe_mismatch(record) is not None:
            await dispatch(
                geo, {"id": "resolve_geography", "args": {"query": "nationwide"}}, record
            )
        status = getattr(record, "geo_status", None) or {}
        table = (
            (plan.table_id if plan is not None else "")
            or pin
            or (str(record.pool[0]["table_id"]) if record.pool else "")
        )
        build = tools.get("build_url")
        if (
            build is not None
            and table
            and record.geographies
            and (not record.url or redo)
            and status.get("nested") is not False
        ):
            args = {"table_id": table}
            if wants_acs1(question):
                args["dataset"] = "acs1"
            await dispatch(build, {"id": "build_url", "args": args}, record)
    fetch = tools.get("fetch_data")
    fetch_failed = record.fetch is not None and not record.fetch.ok
    if fetch is not None and record.url is not None and (record.fetch is None or fetch_failed):
        years = requested_years(question, year)
        await dispatch(fetch, {"id": "fetch_data", "args": {"years": years}}, record)
