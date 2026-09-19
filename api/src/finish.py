"""Finish the four-tool contract when the model stops short of a URL."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool

from src.guards import overlapping_vintage
from src.vintages import device_table

Dispatch = Callable[..., Awaitable[str]]


async def finish_tools(
    dispatch: Dispatch,
    tools: dict[str, BaseTool],
    record: Any,
) -> None:
    """Search, resolve, build, and fetch when a vintage/measure trap has no URL."""
    question = str(getattr(record, "question", "") or "")
    if not getattr(record, "url", None) and (
        device_table(question) or overlapping_vintage(record) is not None
    ):
        search = tools.get("search_tables")
        if search is not None and not record.pool:
            await dispatch(search, {"id": "search_tables", "args": {"question": question}}, record)
        geo = tools.get("resolve_geography")
        if geo is not None and not record.geographies:
            await dispatch(geo, {"id": "resolve_geography", "args": {"query": question}}, record)
        table = device_table(question) or (str(record.pool[0]["table_id"]) if record.pool else "")
        build = tools.get("build_url")
        if build is not None and table and record.geographies and not record.url:
            await dispatch(build, {"id": "build_url", "args": {"table_id": table}}, record)
    fetch = tools.get("fetch_data")
    if fetch is not None and record.url is not None and record.fetch is None:
        await dispatch(fetch, {"id": "fetch_data", "args": {"years": []}}, record)
