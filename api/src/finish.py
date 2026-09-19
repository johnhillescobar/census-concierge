"""Finish the four-tool contract when the model stops short of a URL."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool

from src.compare import parentless_tracts
from src.geo import split_versus
from src.guards import universe_mismatch
from src.vintages import latest_vintages, pinned_table, requested_years, wants_acs1

Dispatch = Callable[..., Awaitable[str]]

_LISTING = re.compile(
    r"\b(?:all|every|each)\s+(?:census\s+)?(block groups?|tracts?)\b|"
    r"\b(?:census\s+)?(block groups?|tracts?)\s+(?:within|inside)\b",
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
    match = _LISTING.search(question)
    if not match:
        return None
    raw = next((group for group in match.groups() if group), "")
    return "block group" if raw.casefold().startswith("block") else "tract"


def _wrong_listing(record: Any, question: str) -> bool:
    wanted = _listing_level(question)
    geos = list(getattr(record, "geographies", []) or [])
    if wanted is None:
        return False
    return not geos or geos[0].level != wanted


def _wrong_versus(record: Any, question: str) -> bool:
    if split_versus(question) is None:
        return False
    status = getattr(record, "geo_status", None) or {}
    geos = list(getattr(record, "geographies", []) or [])
    return not status.get("compare") or len(geos) < 2


def _wrong_parentless(record: Any, question: str, year: int) -> bool:
    if parentless_tracts(question, dataset="acs5", year=year) is None:
        return False
    geos = list(getattr(record, "geographies", []) or [])
    status = getattr(record, "geo_status", None) or {}
    return status.get("legal") is not False or len(geos) < 2 or geos[0].level != "tract"


async def finish_tools(
    dispatch: Dispatch,
    tools: dict[str, BaseTool],
    record: Any,
) -> None:
    """Search, resolve, build, and fetch when the loop stopped without a URL."""
    question = str(getattr(record, "question", "") or "")
    record.consecutive_failures.clear()
    year = _latest(record)
    geo = tools.get("resolve_geography")
    redo = _wrong_listing(record, question) or _wrong_versus(record, question)
    redo = redo or _wrong_parentless(record, question, year)
    redo = redo or bool(wants_acs1(question) and not getattr(record, "url", None))
    if not getattr(record, "url", None) or redo:
        pin = pinned_table(question)
        search = tools.get("search_tables")
        if search is not None and (
            not record.pool
            or (pin is not None and all(hit["table_id"] != pin for hit in record.pool))
        ):
            await dispatch(search, {"id": "search_tables", "args": {"question": question}}, record)
        if geo is not None and (redo or not record.geographies):
            args: dict[str, Any] = {"query": question}
            if wants_acs1(question):
                args["dataset"] = "acs1"
            await dispatch(geo, {"id": "resolve_geography", "args": args}, record)
        if geo is not None and not record.geographies and universe_mismatch(record) is not None:
            await dispatch(
                geo, {"id": "resolve_geography", "args": {"query": "nationwide"}}, record
            )
        status = getattr(record, "geo_status", None) or {}
        table = pin or (str(record.pool[0]["table_id"]) if record.pool else "")
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
    if fetch is not None and record.url is not None and record.fetch is None:
        years = requested_years(question, year)
        await dispatch(fetch, {"id": "fetch_data", "args": {"years": years}}, record)
