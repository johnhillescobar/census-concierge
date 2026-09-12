"""The ask loop: call_model() then dispatch(), no graph.

Tools are constructed per request and handed an ExecutionRecord. That is
per-request state, not a module global.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.census_url import CensusURL, redact_text
from src.contract import Alternative, AskResponse
from src.geo import ResolveGeographyTool, list_census_names
from src.prompts import system_prompt
from src.retrieval.metadata import family_id
from src.tools import (
    BuildUrlResult,
    BuildUrlTool,
    FetchDataResult,
    FetchDataTool,
    SearchTablesResult,
    SearchTablesTool,
)

MAX_TURNS = 8
MAX_TOOL_CALLS = 12
MODEL = "gpt-4o-mini"

CompleteFn = Callable[[list[dict[str, Any]], list[dict[str, Any]]], Awaitable[dict[str, Any]]]


@dataclass
class ExecutionRecord:
    pool: list[dict[str, Any]] = field(default_factory=list)
    geography: dict[str, str] | None = None
    geographies: list[dict[str, str]] = field(default_factory=list)
    url: CensusURL | None = None
    table_id: str = ""
    universe: str = ""
    rows: list[dict[str, str | None]] = field(default_factory=list)
    timings: list[dict[str, Any]] = field(default_factory=list)
    consecutive_failures: dict[str, int] = field(default_factory=dict)


def _artifact_ok(artifact: Any) -> bool:
    if artifact is None:
        return True
    ok = getattr(artifact, "ok", None)
    if ok is None and isinstance(artifact, dict):
        ok = artifact.get("ok")
    return ok is not False


def _absorb(record: ExecutionRecord, name: str, artifact: Any) -> None:
    if artifact is None:
        return
    if name == "search_tables":
        hits = (
            artifact.hits if isinstance(artifact, SearchTablesResult) else artifact.get("hits", [])
        )
        record.pool = list(hits)
    elif name == "resolve_geography":
        matches = artifact.matches if hasattr(artifact, "matches") else artifact.get("matches", [])
        record.geographies = [dict(match) for match in matches]
        if len(matches) == 1:
            record.geography = dict(matches[0])
        else:
            record.geography = None
    elif name == "build_url" and isinstance(artifact, BuildUrlResult):
        record.rows = []
        if artifact.ok:
            record.url = CensusURL(artifact.url)
            record.table_id = artifact.table_id
            record.universe = artifact.universe
        else:
            record.url = None
            record.table_id = ""
            record.universe = ""
    elif name == "fetch_data" and isinstance(artifact, FetchDataResult):
        record.rows = artifact.rows
        if artifact.url:
            record.url = CensusURL(artifact.url)


def _allowed(record: ExecutionRecord) -> set[str]:
    allowed: set[str] = set()
    for hit in record.pool:
        allowed.add(str(hit["table_id"]))
        allowed.update(str(member) for member in hit.get("members") or [])
    return allowed


# A-I race/ethnicity iteration, optional Puerto Rico suffix. Not a PR-only table.
_RACE = re.compile(r"^[BC]\d{5}[A-I](?:PR)?$")


def _moe_rows(rows: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    """One dict per row: GEOID/NAME plus the M that belongs to each E."""
    out: list[dict[str, str | None]] = []
    for row in rows:
        moe: dict[str, str | None] = {}
        for key in ("GEO_ID", "NAME"):
            if key in row:
                moe[key] = row[key]
        for key in row:
            if key.endswith("E") and "_" in key:
                margin = f"{key[:-1]}M"
                moe[margin] = row.get(margin)
        out.append(moe)
    return out


def _rows_with_geoid(
    rows: list[dict[str, str | None]], fallback: str
) -> list[dict[str, str | None]]:
    copied = [dict(row) for row in rows]
    if not fallback:
        return copied
    for row in copied:
        if not row.get("GEO_ID"):
            row["GEO_ID"] = fallback
    return copied


def _response_geoid(rows: list[dict[str, str | None]], fallback: str) -> str:
    if fallback:
        return fallback
    if len(rows) == 1:
        return rows[0].get("GEO_ID") or ""
    return ""


def _how_differs(
    other_id: str,
    selected_id: str,
    *,
    member_of: str = "",
    other_universe: str = "",
    selected_universe: str = "",
    other_title: str = "",
    selected_title: str = "",
) -> str:
    if (
        selected_id
        and family_id(other_id) == family_id(selected_id)
        and (_RACE.match(other_id) or _RACE.match(selected_id))
    ):
        return "race iteration"
    if member_of:
        if _RACE.match(other_id):
            return "race iteration"
        if (other_id.startswith("C") and member_of.startswith("B")) or (
            other_id.startswith("B") and member_of.startswith("C")
        ):
            return "collapsed table"
    if selected_universe and other_universe and selected_universe != other_universe:
        return "universe"
    if other_title and selected_title and other_id[1:3] == selected_id[1:3]:
        other_median = "median" in other_title.casefold()
        selected_median = "median" in selected_title.casefold()
        if other_median != selected_median:
            return "distribution versus median"
    return "related table"


def assemble(answer: str, record: ExecutionRecord) -> AskResponse:
    selected_hit = next(
        (hit for hit in record.pool if str(hit["table_id"]) == record.table_id),
        {},
    )
    selected_universe = record.universe or str(selected_hit.get("universe") or "")
    selected_title = str(selected_hit.get("title") or "")
    alternatives: list[Alternative] = []
    for hit in record.pool:
        table_id = str(hit["table_id"])
        if table_id != record.table_id:
            alternatives.append(
                Alternative(
                    table_id=table_id,
                    reason=_how_differs(
                        table_id,
                        record.table_id,
                        other_universe=str(hit.get("universe") or ""),
                        selected_universe=selected_universe,
                        other_title=str(hit.get("title") or ""),
                        selected_title=selected_title,
                    ),
                )
            )
        for member in hit.get("members") or []:
            member_id = str(member)
            if member_id != record.table_id:
                alternatives.append(
                    Alternative(
                        table_id=member_id,
                        reason=_how_differs(
                            member_id,
                            record.table_id,
                            member_of=table_id,
                            selected_universe=selected_universe,
                            selected_title=selected_title,
                        ),
                    )
                )
    fallback = (record.geography or {}).get("geoid") or ""
    rows = _rows_with_geoid(record.rows, fallback)
    return AskResponse(
        answer=answer,
        url=str(record.url) if record.url else "",
        rows=rows,
        moe=_moe_rows(rows),
        geoid=_response_geoid(rows, fallback),
        universe=selected_universe,
        table_id=record.table_id,
        alternatives=alternatives,
        warnings=[],
    )


async def dispatch(tool: BaseTool, call: dict[str, Any], record: ExecutionRecord) -> str:
    name = tool.name
    started = time.perf_counter()
    ok = False
    content = ""
    try:
        message = await tool.ainvoke(
            {
                "type": "tool_call",
                "name": name,
                "args": call.get("args") or {},
                "id": call.get("id") or name,
            }
        )
        content = str(getattr(message, "content", message))
        artifact = getattr(message, "artifact", None)
        ok = _artifact_ok(artifact)
        _absorb(record, name, artifact)
    except Exception as exc:  # noqa: BLE001 - contained tool failure goes back to the model
        content = f"{name} failed: {redact_text(str(exc))}"
        ok = False
    record.timings.append(
        {"tool": name, "ms": round((time.perf_counter() - started) * 1000, 1), "ok": ok}
    )
    if ok:
        record.consecutive_failures[name] = 0
    else:
        record.consecutive_failures[name] = record.consecutive_failures.get(name, 0) + 1
        if record.consecutive_failures[name] >= 2:
            raise RuntimeError(f"{name} failed twice")
    return content


async def _openai_complete(
    messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
) -> dict[str, Any]:
    from openai import AsyncOpenAI

    response = await AsyncOpenAI().chat.completions.create(
        model=MODEL,
        messages=messages,  # type: ignore[arg-type]
        tools=openai_tools or None,  # type: ignore[arg-type]
    )
    choice = response.choices[0].message
    calls: list[dict[str, Any]] = []
    for tool_call in choice.tool_calls or []:
        function = getattr(tool_call, "function", None)
        if function is None:
            continue
        try:
            args = json.loads(function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append({"id": tool_call.id, "name": function.name, "args": args})
    return {"content": choice.content or "", "tool_calls": calls}


def _latest_vintages() -> tuple[int, int | None]:
    from src.retrieval import availability

    try:
        matrix = availability.load()
    except (OSError, ValueError, KeyError):
        return 2024, None
    acs5 = max(int(year) for year in matrix["datasets"]["acs5"])
    acs1_years = [int(year) for year in matrix["datasets"].get("acs1", {})]
    return acs5, max(acs1_years) if acs1_years else None


def default_tools(record: ExecutionRecord) -> dict[str, BaseTool]:
    from src.retrieval import availability, index, metadata

    idx = index.load()
    matrix = availability.load()
    acs5, _acs1 = _latest_vintages()
    by_id = {table_id: i for i, table_id in enumerate(idx.tables)}

    def search(question: str, k: int) -> list[str]:
        return index.search(question, k)

    def describe(table_id: str) -> dict[str, Any] | None:
        position = by_id.get(table_id)
        if position is None:
            return None
        return {
            "title": idx.titles[position],
            "universe": idx.universes[position],
            "members": idx.members[position],
        }

    def latest(dataset: str) -> int:
        years = [int(year) for year in matrix["datasets"].get(dataset, {})]
        return max(years) if years else acs5

    def facts(dataset: str, year: int, table_id: str) -> dict[str, Any] | None:
        table = matrix["datasets"].get(dataset, {}).get(str(year), {}).get(table_id)
        return table if isinstance(table, dict) else None

    key = os.environ.get("CENSUS_API_KEY", "")
    entries = metadata.geo_entries("acs5", acs5)
    return {
        "search_tables": SearchTablesTool(search=search, describe=describe),
        "resolve_geography": ResolveGeographyTool(
            list_geographies=lambda level, parts: list_census_names(
                level, parts, vintage=acs5, key=key
            ),
            entries=entries,
        ),
        "build_url": BuildUrlTool(
            allowed_tables=lambda: _allowed(record),
            allowed_geographies=lambda: (
                {
                    (str(geo.get("for") or ""), str(geo.get("in") or ""))
                    for geo in record.geographies
                }
                if len(record.geographies) == 1
                else set()
            ),
            latest_vintage=latest,
            table_facts=facts,
            last_geography=lambda: record.geography,
        ),
        "fetch_data": FetchDataTool(
            last_url=lambda: record.url,
            census_key=lambda: os.environ.get("CENSUS_API_KEY", ""),
        ),
    }


async def run_ask(
    question: str,
    *,
    complete: CompleteFn | None = None,
    tools: dict[str, BaseTool] | None = None,
    record: ExecutionRecord | None = None,
) -> AskResponse:
    record = record or ExecutionRecord()
    tools = tools or default_tools(record)
    openai_tools = [convert_to_openai_tool(tool) for tool in tools.values()]
    acs5, acs1 = _latest_vintages()
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": system_prompt(today=date.today().isoformat(), acs5=acs5, acs1=acs1),
        },
        {"role": "user", "content": question},
    ]
    complete = complete or _openai_complete
    answer = ""
    calls_used = 0
    try:
        for _turn in range(MAX_TURNS):
            turn = await complete(messages, openai_tools)
            answer = str(turn.get("content") or "")
            pending = list(turn.get("tool_calls") or [])
            if not pending:
                break
            assistant_tools = []
            for call in pending:
                assistant_tools.append(
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call.get("args") or {}),
                        },
                    }
                )
            messages.append(
                {"role": "assistant", "content": answer or None, "tool_calls": assistant_tools}
            )
            for call in pending:
                if calls_used >= MAX_TOOL_CALLS:
                    break
                tool = tools.get(str(call["name"]))
                if tool is None:
                    content = f"unknown tool {call['name']}"
                else:
                    content = await dispatch(tool, call, record)
                    calls_used += 1
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
            else:
                continue
            break
    except RuntimeError as exc:
        answer = answer or str(exc)
    return assemble(answer, record)
