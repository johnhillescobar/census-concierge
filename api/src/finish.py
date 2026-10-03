"""Finish the four-tool contract when the model stops short of a URL."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool

from src.compare import parentless_tracts
from src.geo import split_comparison
from src.guards import universe_mismatch
from src.vintages import latest_vintages, pinned_table, requested_years, wants_acs1

Dispatch = Callable[..., Awaitable[str]]
Complete = Callable[[list[dict[str, Any]], list[dict[str, Any]]], Awaitable[dict[str, Any]]]

_SPLIT_PARENTS = (
    'Reply with only JSON {"parents": [...], "unit": ..., "listing": bool}. parents are the '
    "places the user names, one entry each, whatever word connects them. A place and its own "
    "state are one parent: write 'Cook County, Illinois', never 'Cook County' and 'Illinois'. "
    "Name a state alone. unit is county, tract, block group, zcta or place: the kind of row "
    "the user wants. listing is true when they want a row for every unit inside the parents, "
    "false when they want the parents themselves."
)

_SPLIT_UNITS = frozenset({"county", "tract", "block group", "zcta", "place"})

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


def _wrong_parentless(record: Any, question: str, year: int) -> bool:
    if parentless_tracts(question, dataset="acs5", year=year) is None:
        return False
    geos = list(getattr(record, "geographies", []) or [])
    status = getattr(record, "geo_status", None) or {}
    return status.get("legal") is not False or len(geos) < 2 or geos[0].level != "tract"


def _all_wild(geos: list[Any]) -> bool:
    return bool(geos) and all(g.for_spec.endswith(":*") for g in geos)


_SNAPSHOT = ("geographies", "geo_status", "geography", "geo_queries", "url", "rows") + (
    "fetch",
    "table_id",
    "universe",
    "vintages",
)


async def _split_parents(
    dispatch: Dispatch, geo: BaseTool | None, record: Any, question: str, complete: Complete | None
) -> bool:
    """Re-resolve a multi-parent listing the loop got wrong; the model only splits parents."""
    geos = list(getattr(record, "geographies", []) or [])
    if not (complete and geo):
        return False
    try:
        turn = await complete(
            [{"role": "system", "content": _SPLIT_PARENTS}, {"role": "user", "content": question}],
            [],
        )
        raw = str(turn.get("content") or "")
        found = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except Exception:  # noqa: BLE001 - a failed repair must never fail the answer
        return False
    names, unit = found.get("parents"), str(found.get("unit") or "")
    if not (found.get("listing") and unit in _SPLIT_UNITS and isinstance(names, list)):
        return False
    parents = [name.strip() for name in names if isinstance(name, str) and name.strip()]
    parents = list({name.casefold(): name for name in parents}.values())
    if len(parents) < 2 or (_all_wild(geos) and len(parents) <= len(geos)):
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
    if legal and len(record.geographies) >= 2 and _all_wild(record.geographies):
        return True
    for name, value in before.items():
        setattr(record, name, value)
    return False


async def finish_tools(
    dispatch: Dispatch,
    tools: dict[str, BaseTool],
    record: Any,
    complete: Complete | None = None,
) -> None:
    """Search, resolve, build, and fetch when the loop stopped without a URL."""
    question = str(getattr(record, "question", "") or "")
    record.consecutive_failures.clear()
    year = _latest(record)
    geo = tools.get("resolve_geography")
    url = getattr(record, "url", None)
    plan = getattr(record, "override", None)
    split = plan is None and await _split_parents(dispatch, geo, record, question, complete)
    redo = split or _wrong_listing(record, question) or _wrong_comparison(record, question)
    redo = redo or _wrong_parentless(record, question, year)
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
        if geo is not None and not split and (redo or not record.geographies):
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
