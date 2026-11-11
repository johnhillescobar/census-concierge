"""Finish the four-tool contract when the model stops short of a URL."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.tools import BaseTool

from src.contract import clauses_from_geoid
from src.geo_level import level_name
from src.geo_list import state_of
from src.vintages import latest_vintages, requested_years, wants_acs1

Dispatch = Callable[..., Awaitable[str]]
Complete = Callable[[list[dict[str, Any]], list[dict[str, Any]]], Awaitable[dict[str, Any]]]

_SPLIT_PARENTS = (
    'Reply with only JSON {"parents": [...], "unit": ..., "listing": bool, "parent_level": ..., '
    '"level": ..., "named": [...], "numbered": [...], "given": [...], "asks_for": ..., '
    '"pointing": bool, "county_named": bool}. parents are the places the user names, one entry '
    "each, whatever word connects them. Write a place smaller than a state as 'Name, State' "
    "with the state from your "
    "own knowledge (such as 'Lancaster County, Nebraska'), never as two entries; name a state "
    "alone. unit is county, tract, block group, zcta or place: the kind of row the user wants. "
    "listing is true when they want a row for every unit inside the parents, false when they want "
    "the parents themselves. parent_level is the level the parents are (county or place), null "
    "for states. level is the geography level the question asks about (state, county, place, "
    "tract, block group, zcta, or us for the whole nation), or null when it asks about none; a "
    "tract, block group or county "
    "identified by number asks about that level. named lists each code that identifies a place "
    "on its own, as the user wrote it ('FIPS 39049', 'GEOID 06037', a ZIP code); never replace a "
    "code with a name. given lists which of state, county and tract the question itself states, "
    "by name or code; one you supplied from your own knowledge is not given. numbered lists the "
    "level (tract, block group or county) of each place the question identifies only by a "
    "number inside another place, such as 'tract 12'; a state, ZIP "
    "code or GEOID is never numbered. asks_for is 'tables' when the question asks which table or "
    "variable holds something or where to find it, and 'data' when it asks for figures. pointing "
    "is true when a phrase stands in for a place by pointing at it ('my county', 'where I "
    "live'). county_named is true when the question names a specific county, by name or by a "
    "five-digit FIPS code."
)

_SPLIT_UNITS = frozenset({"county", "tract", "block group", "zcta", "place"})
SPLIT_WAIT_SECONDS = 6.0  # the call normally finishes beside the loop; never delay an answer more
FRAME_WAIT_SECONDS = 3.0  # before the first tool runs; past it the question is treated as complete


def _latest(record: Any) -> int:
    getter = getattr(record, "published_vintages", None)
    if callable(getter):
        years = getter("acs5")
        if years:
            return max(int(year) for year in years)
    acs5, _acs1 = latest_vintages()
    return acs5


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
    names = list(
        {
            n.strip().casefold(): n.strip() for n in names if isinstance(n, str) and n.strip()
        }.values()
    )
    frame = {
        "level": found.get("level"),
        "named": [*(named if isinstance(named, list) else []), *names],
        "numbered": numbered if isinstance(numbered, list) else [],
        "given": found["given"] if isinstance(found.get("given"), list) else None,
        "asks_for": found.get("asks_for") if isinstance(found.get("asks_for"), str) else None,
        "county_named": found.get("county_named") is True,
        "pointing": found.get("pointing") is True,
    }
    if not names:
        return {"frame": frame}
    if not found.get("listing"):
        return {"frame": frame, "places": names}
    if unit not in _SPLIT_UNITS:
        return {"frame": frame}
    up = found.get("parent_level")
    return {
        "frame": frame,
        "parents": names,
        "unit": unit,
        "parent_level": up if isinstance(up, str) else None,
    }


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


def _unit(entry: Any) -> str | None:
    """The level an entry of `numbered` states: "tract", or "tract 12" as the model wrote it."""
    words = entry.split() if isinstance(entry, str) else []
    return next((lv for n in (2, 1) if (lv := level_name(" ".join(words[:n]))) in _ORDER), None)


def _join(parts: list[str]) -> str:
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]


async def incomplete(record: Any, split: asyncio.Task[dict[str, Any] | None] | None) -> str | None:
    """The answer to return at once when a question lacks what its geography level needs.

    The model reports the level, the places and codes the question names, the levels of the places
    it identifies only by a number inside another, whether a county is named, whether a phrase
    points at a place, and whether it asks for tables (the split call, beside the loop). A place
    name gives the state (the lookup finds it); a code with a digit must ground itself. Code
    compares that with `_NEEDS` for the
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
    if frame.get("pointing") is True:
        record.geo_status = {"legal": False, "detail": "a place is not named", "nested": True}
        return (
            "This question is incomplete and cannot be searched: it is about a place it does "
            "not name. Name the place, with its state, and ask again."
        )
    reported = [n for n in frame.get("named") or [] if isinstance(n, str)][:MAX_REPORTED]
    units = [lv for n in frame.get("numbered") or [] if (lv := _unit(n)) in _ORDER][:MAX_REPORTED]
    level = level_name(frame.get("level")) or next(iter(units), None)
    need = _NEEDS.get((level or "", False), ())
    if units:  # each number is judged at its own unit's level
        need = tuple(p for p in _ORDER if any(p in _NEEDS.get((lv, True), ()) for lv in units))
    # A place the model names gives the state, with or without it written ("Los Angeles"): the
    # lookup finds it. An entry with a digit is a code, so it must ground itself (a number filed
    # under named is not a place). The county and tract are what the model reports apart.
    named = [p for p in reported if state_of(p) or (p.isascii() and p.replace(" ", "").isalpha())]
    given = frame.get("given")
    if units and isinstance(given, list):  # a number needs parents the question itself states
        have = {g for g in given if g in _ORDER}
    else:
        have = {"state"} if named else set()
    if frame.get("county_named") is True or "county" in units:
        have.add("county")
    if "tract" in units:
        have.add("tract")
    for part in reported:  # a GEOID in the report carries the hierarchy it encodes (parsing only)
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
    dispatch: Dispatch, geo: BaseTool | None, record: Any, found: Any, acs1: bool
) -> bool:
    """Re-resolve a listing the loop got wrong, with the parents and unit the model reported."""
    geos = list(getattr(record, "geographies", []) or [])
    if not (found and found.get("parents") and geo):
        return False
    parents, unit = found["parents"], found["unit"]
    dataset = "acs1" if acs1 else "acs5"
    right = [g.level == level_name(unit) and g.dataset == dataset for g in geos[: len(parents)]]
    want = {s[1] for p in parents if (s := state_of(p))}  # the states the model says it lies in
    inside = want <= {g.codes.get("state") for g in geos}
    if _all_wild(geos) and len(parents) <= len(geos) and all(right) and inside:
        return False
    before = {name: getattr(record, name) for name in _SNAPSHOT}
    before["geo_queries"] = list(record.geo_queries)
    args: dict[str, Any] = {
        "parents": parents,
        "parent_level": found.get("parent_level"),
        "level": unit,  # the model's own unit from the split call
    }
    if acs1:
        args["dataset"] = "acs1"
    try:
        await dispatch(geo, {"id": "resolve_geography", "origin": "repair", "args": args}, record)
    except Exception:  # noqa: BLE001 - keep the loop's own resolution
        record.geographies = []
    record.consecutive_failures.pop("resolve_geography", None)
    after = getattr(record, "geo_status", None) or {}
    nested = after.get("nested") is not False  # an unsupported candidate is still what was asked
    chosen = record.geographies[: len(parents)]  # the rest are ambiguity candidates
    if nested and len(chosen) == len(parents) and _all_wild(chosen):
        record.url, record.rows, record.fetch = None, [], None  # never show the old parent's data
        return True
    if not before["geographies"]:  # the loop resolved nothing: the repair, even an unsupported
        return bool(record.geographies)  # candidate with its warning, is the only answer there is
    for name, value in before.items():
        if name != "geo_status" or nested:  # keep why it cannot be nested: it is the warning
            setattr(record, name, value)
    return False


async def finish_tools(
    dispatch: Dispatch,
    tools: dict[str, BaseTool],
    record: Any,
    split: Awaitable[dict[str, Any] | None] | None = None,
) -> None:
    """Search, resolve, build, and fetch when the loop stopped without a URL.

    Geography comes only from what the model reported (the loop's own calls and the split call);
    a question the model reported nothing for gets no guessed place.
    """
    question = str(getattr(record, "question", "") or "")
    acs1 = wants_acs1(question)  # time and product are still read from words: the next story
    record.consecutive_failures.clear()
    year = _latest(record)
    geo = tools.get("resolve_geography")
    url = getattr(record, "url", None)
    plan = getattr(record, "override", None)
    refused = bool((getattr(record, "geo_status", None) or {}).get("refused"))  # never re-guess it
    try:
        found = await asyncio.wait_for(split, SPLIT_WAIT_SECONDS) if split is not None else None
    except TimeoutError:
        found = None
    redone = plan is None and await _split_parents(dispatch, geo, record, found, acs1)
    status = getattr(record, "geo_status", None) or {}
    queries = list(getattr(record, "geo_queries", None) or [])
    places = list((found or {}).get("places") or [])
    short = len(places) >= 2 and int(status.get("compare_count", 0) or 0) < len(places)
    redo = redone or short or (len(queries) >= 2 and not status.get("compare"))
    redo = redo or bool(acs1 and (url is None or "/acs/acs1" not in str(url)))
    if plan is not None and plan.geographies:
        redo = False
    if not url or redo:
        search = tools.get("search_tables")
        if search is not None and not record.pool:
            asked = {"question": question, "dataset": "acs1" if acs1 else "acs5"}
            await dispatch(search, {"id": "search_tables", "args": asked}, record)
        if geo is not None and not redone and not refused and (redo or not record.geographies):
            legs = places or queries
            stated = list(getattr(record, "asked_levels", None) or [])
            stated = stated if len(stated) == len(legs) else []  # the model's own, if any
            reported = ((found or {}).get("frame") or {}).get("level")
            level = (stated or [reported if len(legs) < 2 else None])[0]  # legs differ: none
            args: dict[str, Any] = {"places": legs, "level": level}
            if len(legs) >= 2:
                args["levels"] = stated
            if acs1:
                args["dataset"] = "acs1"
            if legs or level_name(level) == "us":  # nothing reported means nothing to resolve
                await dispatch(
                    geo, {"id": "resolve_geography", "origin": "repair", "args": args}, record
                )
        status = getattr(record, "geo_status", None) or {}
        table = (plan.table_id if plan is not None else "") or (
            str(record.pool[0]["table_id"]) if record.pool else ""
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
            if acs1:
                args["dataset"] = "acs1"
            await dispatch(build, {"id": "build_url", "args": args}, record)
    fetch = tools.get("fetch_data")
    fetch_failed = record.fetch is not None and not record.fetch.ok
    if fetch is not None and record.url is not None and (record.fetch is None or fetch_failed):
        years = requested_years(question, year)
        await dispatch(fetch, {"id": "fetch_data", "args": {"years": years}}, record)
