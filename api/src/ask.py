"""The ask loop: _openai_complete() then dispatch(), no graph."""

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
from src.contract import (
    Alternative,
    AskResponse,
    GeoSpec,
    apply_override,
    override_years,
    pin_tool_args,
    plan_from_record,
    take_chart,
)
from src.fetch import FetchDataResult, FetchDataTool, clear_series, series_from_record
from src.finish import finish_tools
from src.geo import ResolveGeographyTool
from src.geo_list import list_census_names
from src.guards import finish_aggregation
from src.prompts import system_prompt
from src.retrieval.metadata import family_id
from src.tools import BuildUrlResult, BuildUrlTool, SearchTablesResult, SearchTablesTool
from src.vintages import latest_vintages, moe_rows, requested_years, stamp_provenance

MAX_TURNS = 8
MAX_TOOL_CALLS = 12
MODEL = "gpt-4o-mini"

CompleteFn = Callable[[list[dict[str, Any]], list[dict[str, Any]]], Awaitable[dict[str, Any]]]


@dataclass
class ExecutionRecord:
    pool: list[dict[str, Any]] = field(default_factory=list)
    geography: GeoSpec | None = None
    geographies: list[GeoSpec] = field(default_factory=list)
    url: CensusURL | None = None
    table_id: str = ""
    universe: str = ""
    rows: list[dict[str, str | None]] = field(default_factory=list)
    timings: list[dict[str, Any]] = field(default_factory=list)
    consecutive_failures: dict[str, int] = field(default_factory=dict)
    question: str = ""
    vintages: list[tuple[str, int]] = field(default_factory=list)
    geo_status: dict[str, str | bool] | None = None
    fetch: FetchDataResult | None = None
    allow_overlapping_acs5: bool = False
    override: Any = None
    table_facts: Any = None
    published_vintages: Any = None
    retained_urls: list[str] = field(default_factory=list)


def _artifact_ok(artifact: Any) -> bool:
    if artifact is None:
        return True
    ok = artifact.get("ok") if isinstance(artifact, dict) else getattr(artifact, "ok", None)
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
        if record.override and record.override.geographies:
            return
        previous = record.geography
        pull = artifact.get if isinstance(artifact, dict) else None
        get = pull or (lambda k, d=None: getattr(artifact, k, d))
        specs = get("specs")
        record.geographies = list(specs if specs is not None else get("matches") or [])
        record.geo_status = {
            "legal": bool(get("legal", True)),
            "detail": str(get("detail", "") or ""),
            "nested": get("nested", True) is not False,
            "compare": bool(get("compare", False)),
        }
        record.geography = record.geographies[0] if record.geographies else None
        if record.geography != previous:
            clear_series(record)
    elif name == "build_url" and isinstance(artifact, BuildUrlResult):
        record.vintages.append((artifact.dataset, artifact.vintage))
        clear_series(record)
        if artifact.ok:
            record.url = CensusURL(artifact.url)
            record.table_id = artifact.table_id
            record.universe = artifact.universe
    elif name == "fetch_data" and isinstance(artifact, FetchDataResult):
        record.rows = artifact.rows
        record.fetch = artifact
        dataset = artifact.dataset or (record.url.dataset if record.url else "acs5")
        if record.url is not None and artifact.dataset:
            record.url = record.url.with_dataset(artifact.dataset)
        if artifact.attempted_years:
            record.vintages = [(dataset, year) for year in artifact.attempted_years]


def _allowed(record: ExecutionRecord) -> set[str]:
    ids = {str(hit["table_id"]) for hit in record.pool}
    ids.update(str(m) for hit in record.pool for m in hit.get("members") or [])
    ids.add(getattr(record.override, "table_id", "") or "")
    ids.discard("")
    return ids


# A-I race/ethnicity iteration, optional Puerto Rico suffix. Not a PR-only table.
_RACE = re.compile(r"^[BC]\d{5}[A-I](?:PR)?$")


def _rows_with_geoid(
    rows: list[dict[str, str | None]], fallback: str
) -> list[dict[str, str | None]]:
    return [{**row, "GEO_ID": row.get("GEO_ID") or fallback} for row in rows]


def _response_geoid(rows: list[dict[str, str | None]], fallback: str) -> str:
    ids = {(row.get("GEO_ID") or fallback) for row in rows} - {""}
    if len(ids) == 1:
        return next(iter(ids))
    return fallback if not rows else ""


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
    if not selected_id:
        return "related table"
    same = family_id(other_id) == family_id(selected_id)
    if same and (_RACE.match(other_id) or _RACE.match(selected_id)):
        return "race iteration"
    if member_of and (
        member_of == selected_id
        or other_id == member_of
        or family_id(member_of) == family_id(selected_id)
        or same
    ):
        if _RACE.match(other_id):
            return "race iteration"
        letters = {other_id[:1], selected_id[:1]}
        collapsed = letters == {"B", "C"} or (
            other_id.startswith("C")
            and member_of.startswith("B")
            or other_id.startswith("B")
            and member_of.startswith("C")
        )
        if collapsed:
            return "collapsed table"
    if selected_universe and other_universe and selected_universe != other_universe:
        return "universe"
    if (
        other_title
        and selected_title
        and other_id[1:3] == selected_id[1:3]
        and ("median" in other_title.casefold()) != ("median" in selected_title.casefold())
    ):
        return "distribution versus median"
    return "related table"


def _selected_hit(record: ExecutionRecord) -> dict[str, Any]:
    selected = record.table_id
    if not selected:
        return {}
    for hit in record.pool:
        if str(hit["table_id"]) == selected:
            return hit
    for hit in record.pool:
        members = {str(member) for member in (hit.get("members") or [])}
        if selected in members:
            return hit
    return {}


def assemble(answer: str, record: ExecutionRecord) -> AskResponse:
    selected_hit = _selected_hit(record)
    selected_universe = record.universe or str(selected_hit.get("universe") or "")
    selected_title = str(selected_hit.get("title") or "")
    alternatives: list[Alternative] = []
    for hit in record.pool:
        table_id = str(hit["table_id"])
        members = [str(member) for member in (hit.get("members") or [])]
        title, universe = str(hit.get("title") or ""), str(hit.get("universe") or "")
        parent = table_id if record.table_id in members else ""
        for other, member_of in ((table_id, parent), *((m, table_id) for m in members)):
            if other == record.table_id:
                continue
            own = other == table_id
            alternatives.append(
                Alternative(
                    table_id=other,
                    title=title,
                    universe=universe,
                    reason=_how_differs(
                        other,
                        record.table_id,
                        member_of=member_of,
                        other_universe=universe if own else "",
                        selected_universe=selected_universe,
                        other_title=title if own else "",
                        selected_title=selected_title,
                    ),
                )
            )
    fallback = record.geography.geoid if record.geography else ""
    rows = _rows_with_geoid(record.rows, fallback)
    warnings, rows, extra, compared = finish_aggregation(
        record, rows, {item.table_id for item in alternatives}
    )
    alternatives.extend(extra)
    dataset = str(getattr(record.fetch, "dataset", "") or "")
    dataset = dataset or (record.url.dataset if record.url else "")
    dataset = dataset or (record.vintages[0][0] if record.vintages else "acs5")
    year = record.vintages[-1][1] if record.vintages else None
    rows = stamp_provenance(rows, dataset=dataset, table_id=record.table_id, fallback_year=year)
    return AskResponse(
        **take_chart(answer, rows, warnings),
        **series_from_record(record),
        rows=rows,
        moe=moe_rows(rows),
        geoid=_response_geoid(rows, fallback),
        universe=selected_universe,
        table_id=record.table_id,
        plan=plan_from_record(record),
        alternatives=alternatives,
        comparisons=compared,
        warnings=warnings,
    )


async def dispatch(tool: BaseTool, call: dict[str, Any], record: ExecutionRecord) -> str:
    name = tool.name
    started = time.perf_counter()
    ok = False
    content = ""
    try:
        args = pin_tool_args(name, call.get("args") or {}, record.override)
        if name == "resolve_geography" and record.override and record.override.geographies:
            content, ok = "override geography", True
        else:
            message = await tool.ainvoke(
                {"type": "tool_call", "name": name, "args": args, "id": call.get("id") or name}
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
    record.consecutive_failures[name] = 0 if ok else record.consecutive_failures.get(name, 0) + 1
    if not ok and record.consecutive_failures[name] >= 2:
        raise RuntimeError(f"{name} failed twice")
    return content


async def _openai_complete(
    messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
) -> dict[str, Any]:
    from openai import AsyncOpenAI

    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("missing OPENAI_API_KEY")
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


def default_tools(record: ExecutionRecord) -> dict[str, BaseTool]:
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        raise ValueError("missing CENSUS_API_KEY")
    from src.retrieval import availability, index, metadata

    idx = index.load()
    matrix = availability.load()
    acs5, _acs1 = latest_vintages(matrix)
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

    record.table_facts = facts
    record.published_vintages = lambda d: {int(year) for year in matrix["datasets"].get(d, {})}
    return {
        "search_tables": SearchTablesTool(search=search, describe=describe),
        "resolve_geography": ResolveGeographyTool(
            list_geographies=lambda level, parts, dataset="acs5", vintage=2024: list_census_names(
                level, parts, dataset=dataset, vintage=vintage, key=key
            ),
            geo_table=metadata.geo_entries,
            latest_vintage=latest,
        ),
        "build_url": BuildUrlTool(
            allowed_tables=lambda: _allowed(record),
            allowed_geographies=lambda: {
                (geo.for_spec, geo.in_spec, geo.dataset) for geo in record.geographies
            },
            latest_vintage=latest,
            table_facts=facts,
            last_geography=lambda: record.geography,
        ),
        "fetch_data": FetchDataTool(
            last_url=lambda: record.url,
            last_geographies=lambda: (
                record.geographies[:2] if (record.geo_status or {}).get("compare") else []
            ),
            census_key=lambda: key,
            published=lambda dataset: {int(year) for year in matrix["datasets"].get(dataset, {})},
            table_facts=facts,
            question_years=lambda: (
                override_years(record.override) or requested_years(record.question, latest("acs5"))
            ),
            allow_overlapping_acs5=record.allow_overlapping_acs5,
        ),
    }


async def run_ask(
    question: str,
    *,
    complete: CompleteFn | None = None,
    tools: dict[str, BaseTool] | None = None,
    record: ExecutionRecord | None = None,
    override: Any = None,
) -> AskResponse:
    record = record or ExecutionRecord()
    apply_override(record, override)
    record.question = record.question or question
    tools = tools or default_tools(record)
    openai_tools = [convert_to_openai_tool(tool) for tool in tools.values()]
    acs5, acs1 = latest_vintages()
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
    await finish_tools(dispatch, tools, record)
    return assemble(answer, record)
