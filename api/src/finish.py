"""Finish the four-tool contract when the model stops short of a URL."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool

from src.guards import universe_mismatch
from src.vintages import latest_vintages, pinned_table, requested_years, wants_acs1

Dispatch = Callable[..., Awaitable[str]]


def _latest(record: Any) -> int:
    getter = getattr(record, "published_vintages", None)
    if callable(getter):
        years = getter("acs5")
        if years:
            return max(int(year) for year in years)
    acs5, _acs1 = latest_vintages()
    return acs5


async def finish_tools(
    dispatch: Dispatch,
    tools: dict[str, BaseTool],
    record: Any,
) -> None:
    """Search, resolve, build, and fetch when the loop stopped without a URL."""
    question = str(getattr(record, "question", "") or "")
    if not getattr(record, "url", None):
        search = tools.get("search_tables")
        if search is not None and not record.pool:
            await dispatch(search, {"id": "search_tables", "args": {"question": question}}, record)
        geo = tools.get("resolve_geography")
        if geo is not None and not record.geographies:
            await dispatch(geo, {"id": "resolve_geography", "args": {"query": question}}, record)
        if geo is not None and not record.geographies and universe_mismatch(record) is not None:
            await dispatch(
                geo, {"id": "resolve_geography", "args": {"query": "nationwide"}}, record
            )
        status = getattr(record, "geo_status", None) or {}
        table = pinned_table(question) or (str(record.pool[0]["table_id"]) if record.pool else "")
        build = tools.get("build_url")
        if (
            build is not None
            and table
            and record.geographies
            and not record.url
            and status.get("nested") is not False
        ):
            args: dict[str, Any] = {"table_id": table}
            if wants_acs1(question):
                args["dataset"] = "acs1"
            await dispatch(build, {"id": "build_url", "args": args}, record)
    fetch = tools.get("fetch_data")
    if fetch is not None and record.url is not None and record.fetch is None:
        years = requested_years(question, _latest(record))
        await dispatch(fetch, {"id": "fetch_data", "args": {"years": years}}, record)
