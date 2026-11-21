"""The ask loop: _openai_complete() then dispatch(), no graph."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast

from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import APIError, AsyncOpenAI, omit
from openai.types.responses import ResponseInputParam, ToolParam

from src.census_url import CensusURL, redact_text
from src.contract import (
    Alternative,
    AskResponse,
    GeoSpec,
    apply_override,
    override_years,
    pin_tool_args,
    plan_from_record,
    response_geoid,
    rows_with_geoid,
    take_chart,
)
from src.fetch import FetchDataResult, FetchDataTool, clear_series, series_from_record
from src.finish import degraded_answer, finish_tools, incomplete, split_beside
from src.geo import ResolveGeographyTool, track_geo_query
from src.geo_level import geo_status, note_intent
from src.geo_list import list_census_names
from src.guards import finish_aggregation, response_pool, selected_hit
from src.prompts import system_prompt
from src.retrieval.metadata import family_id
from src.tools import BuildUrlResult, BuildUrlTool, SearchTablesResult, SearchTablesTool
from src.vintages import latest_vintages, moe_rows, requested_years, stamp_provenance

MAX_TURNS = 8
MAX_TOOL_CALLS = 12
MODEL = "gpt-6.2-sol"

CompleteFn = Callable[[list[dict[str, Any]], list[dict[str, Any]]], Awaitable[dict[str, Any]]]


@dataclass
class ExecutionRecord:
    pool: list[dict[str, Any]] = field(default_factory=list)
    built_pool: list[dict[str, Any]] = field(default_factory=list)
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
    geo_status: dict[str, str | bool | int] | None = None
    # Level per leg the model stated in its own resolve_geography call; [] if it never did.
    asked_levels: list[str | None] = field(default_factory=list)
    # Levels the model stated that came back unsupported and were not later served by a legal call.
    unmet_levels: set[str] = field(default_factory=set)
    fetch: FetchDataResult | None = None
    allow_overlapping_acs5: bool = False
    override: Any = None
    table_facts: Any = None
    published_vintages: Any = None
    retained_urls: list[str] = field(default_factory=list)
    # Single-place resolve_geography queries, most recent last. finish_tools
    # replays these as one `places` call when the model resolved legs of a
    # comparison one at a time instead of together -- mechanical bookkeeping
    # of what was actually asked, not a re-parse of the question's prose.
    geo_queries: list[str] = field(default_factory=list)
    # The question asks which table holds something: no geography is wanted, so none is flagged.
    tables_only: bool = False


def _artifact_ok(artifact: Any) -> bool:
    ok = artifact.get("ok") if isinstance(artifact, dict) else getattr(artifact, "ok", None)
    return ok is not False


def _absorb(record: ExecutionRecord, name: str, artifact: Any, args: dict[str, Any]) -> None:
    if artifact is None:
        return
    if name == "search_tables":
        record.pool = list(
            artifact.hits if isinstance(artifact, SearchTablesResult) else artifact.get("hits", [])
        )
    elif name == "resolve_geography":
        if record.override and record.override.geographies:
            return
        previous = record.geography
        pull = artifact.get if isinstance(artifact, dict) else None
        get = pull or (lambda k, d=None: getattr(artifact, k, d))
        specs = get("specs")
        record.geographies = list(specs if specs is not None else get("matches") or [])
        record.geo_status = geo_status(get)
        record.geography = record.geographies[0] if record.geographies else None
        if record.geography != previous:
            clear_series(record)
        query = str(args.get("query") or "").strip()
        if record.geo_status["compare"] or get("wildcard", False) or args.get("places"):
            record.geo_queries = []
        # An unsupported candidate (legal False) is not a place that was compared.
        elif query and record.geographies and record.geo_status["legal"]:
            record.geo_queries = track_geo_query(record.geo_queries, query)
    elif name == "build_url" and isinstance(artifact, BuildUrlResult):
        record.vintages.append((artifact.dataset, artifact.vintage))
        clear_series(record)
        if artifact.ok:
            record.url = CensusURL(artifact.url)
            record.table_id = artifact.table_id
            record.universe = artifact.universe
            record.built_pool = record.pool.copy()
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


def assemble(answer: str, record: ExecutionRecord) -> AskResponse:
    pool = response_pool(record)
    selected = selected_hit(pool, record.table_id)
    selected_universe = record.universe or str(selected.get("universe") or "")
    selected_title = str(selected.get("title") or "")
    alternatives: list[Alternative] = []
    for hit in pool:
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
    rows = rows_with_geoid(record.rows, fallback)
    warnings, combined, extra, compared = finish_aggregation(
        record, rows, {item.table_id for item in alternatives}
    )
    alternatives.extend(extra)
    dataset = str(getattr(record.fetch, "dataset", "") or getattr(record.url, "dataset", ""))
    dataset = dataset or (record.vintages[0][0] if record.vintages else "acs5")
    year = record.vintages[-1][1] if record.vintages else None
    table_id = record.table_id
    rows = stamp_provenance(rows, dataset=dataset, table_id=table_id, fallback_year=year)
    combined = stamp_provenance(combined, dataset=dataset, table_id=table_id, fallback_year=year)
    return AskResponse(
        **take_chart(answer, [*rows, *combined], warnings, record),
        **series_from_record(record),
        rows=rows,
        combined_rows=combined,
        moe=moe_rows(rows),
        geoid=response_geoid(rows, fallback),
        universe=selected_universe,
        table_id=table_id,
        plan=plan_from_record(record),
        alternatives=alternatives,
        comparisons=compared,
        warnings=warnings,
    )


async def dispatch(tool: BaseTool, call: dict[str, Any], record: ExecutionRecord) -> str:
    name = tool.name
    started = time.perf_counter()
    try:
        if (provided := call.get("args", {})) is None:
            raise ValueError("Tool arguments must be a JSON object.")
        args = pin_tool_args(name, provided, record.override, record.question)
        if name == "resolve_geography" and record.override and record.override.geographies:
            content, ok = "override geography", True
        else:
            message = await tool.ainvoke(
                {"type": "tool_call", "name": name, "args": args, "id": call.get("id") or name}
            )
            content = str(getattr(message, "content", message))
            artifact = getattr(message, "artifact", None)
            ok = _artifact_ok(artifact)
            _absorb(record, name, artifact, args)
            note_intent(record, name, call)
    except Exception as exc:  # noqa: BLE001 - contained tool failure goes back to the model
        content = f"{name} failed: {redact_text(str(exc))}"
        ok = False
        note_intent(record, name, call, failed=True)  # the level it asked for was not served
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
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("missing OPENAI_API_KEY")
    tools = [{"type": "function", **tool["function"], "strict": False} for tool in openai_tools]
    try:
        async with AsyncOpenAI(timeout=60.0, max_retries=0) as client:
            response = await client.responses.create(
                model=MODEL,
                input=cast("ResponseInputParam", messages),
                tools=cast("list[ToolParam]", tools),
                reasoning={"effort": "low"} if MODEL == "gpt-6.2-sol" else omit,
                max_output_tokens=4096,
                service_tier="default",
                store=False,
                parallel_tool_calls=True,
            )
    except APIError:
        return {"content": "The model request failed.", "model_failed": True}
    if response.status != "completed":
        return {"content": "The model did not complete its response.", "model_failed": True}
    calls: list[dict[str, Any]] = []
    output = [item.model_dump(mode="json", exclude_none=True) for item in response.output]
    for item in output:
        if item["type"] == "function_call":
            try:
                parsed = json.loads(item.get("arguments", ""))
            except (json.JSONDecodeError, TypeError):
                parsed = None
            args = parsed if isinstance(parsed, dict) else None
            # The service needs a valid history item even when dispatch rejects the call.
            item["arguments"] = "{}" if args is None else item["arguments"]
            calls.append({"id": item["call_id"], "name": item["name"], "args": args})
    return {"content": response.output_text, "tool_calls": calls, "output": output}


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

    def is_published(dataset: str, table_id: str) -> bool:
        return facts(dataset, latest(dataset), table_id) is not None

    record.table_facts = facts
    record.published_vintages = lambda d: {int(year) for year in matrix["datasets"].get(d, {})}
    return {
        "search_tables": SearchTablesTool(search=search, describe=describe, published=is_published),
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
                record.geographies[: int((record.geo_status or {}).get("compare_count") or 0)]
                if (record.geo_status or {}).get("compare")
                else []
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
    record.question = record.question or question
    apply_override(record, override)
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
    given = bool(record.override and record.override.geographies)  # a plan that names the places
    async with split_beside(question, complete, not given) as split:
        try:
            for turn_no in range(MAX_TURNS):
                turn = await complete(messages, openai_tools)
                if not turn_no and (stop := await incomplete(record, split)):
                    return assemble(stop, record)
                answer = str(turn.get("content") or "")
                if turn.get("model_failed"):
                    return assemble(answer, record)
                if not (pending := list(turn.get("tool_calls") or [])):
                    break
                # Replay provider items before the corresponding tool results with store=False.
                messages.extend(turn.get("output", []))
                for call in pending:
                    if calls_used >= MAX_TOOL_CALLS:
                        break
                    tool = tools.get(str(call["name"]))
                    if tool is None:
                        out = f"unknown tool {call['name']}"
                    else:
                        out = await dispatch(tool, call, record)
                        calls_used += 1
                    messages.append(
                        {"type": "function_call_output", "call_id": call["id"], "output": out}
                    )
                else:
                    continue
                break
        except RuntimeError as exc:
            answer = answer or str(exc)
        await finish_tools(dispatch, tools, record, split)
    if record.rows and re.match(r"^[a-z_]+ failed twice$", answer):
        answer = degraded_answer(record)
    return assemble(answer, record)
