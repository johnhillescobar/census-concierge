#!/usr/bin/env python3
"""Run ONE question through the real ask loop, in this process, so a debugger can step it.

    python scripts/ask_one.py "poverty rate in Cook County, Illinois"
    python scripts/ask_one.py                  # prompts for the question

Real OpenAI, Gemini and Census calls: OPENAI_API_KEY, GEMINI_API_KEY and CENSUS_API_KEY in
.env (names are checked, values are never printed). Writes nothing: no evidence/ file, no
database, no cache. Breakpoints in api/src fire: src/ask.py run_ask and dispatch,
src/finish.py finish_tools and plan_split, src/geo.py, src/tools.py, src/fetch.py.

It prints, in order, what the loop did: each model turn and its tool calls, each tool call
with the arguments the TOOL received (after the override pins) and what it returned, the
beside-the-loop split call, and the redo steps finish_tools runs after the loop. Then the
response: answer, table, universe, GEOID, plan, URLs, years, rows, warnings, alternatives.

The loop is not changed: this passes `complete=`, `tools=` and `record=` to run_ask.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402
from src.ask import ExecutionRecord, _openai_complete, default_tools, run_ask  # noqa: E402
from src.census_url import redact_text  # noqa: E402
from src.contract import AskResponse  # noqa: E402

REQUIRED_KEYS = ("OPENAI_API_KEY", "GEMINI_API_KEY", "CENSUS_API_KEY")

Out = Callable[[str], None]


def _short(value: Any, limit: int) -> str:
    """One line of a value, key-redacted, cut at `limit` characters with its full length noted."""
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=True)
    text = redact_text(" ".join(text.split()))
    return f"{text[:limit]}... [{len(text)} chars]" if len(text) > limit else text


def _trace_tool(tool: Any, out: Out) -> None:
    """Print each call to `tool` and its result. finish_tools' redo steps go through here too."""
    name, inner = tool.name, tool.ainvoke

    async def ainvoke(payload: Any, *args: Any, **kwargs: Any) -> Any:
        out(f"[tool] {name}  args as received: {_short(payload.get('args'), 300)}")
        started = time.perf_counter()
        try:
            message = await inner(payload, *args, **kwargs)
        except Exception as exc:
            out(f"[tool] {name}  RAISED {type(exc).__name__}: {_short(str(exc), 300)}")
            raise
        ms = round((time.perf_counter() - started) * 1000)
        out(f"[tool] {name}  {ms} ms  result: {_short(getattr(message, 'content', message), 400)}")
        return message

    object.__setattr__(tool, "ainvoke", ainvoke)  # a pydantic tool: set it on the instance


def _trace_complete(complete: Callable[..., Any], out: Out) -> Callable[..., Any]:
    """Print each model call. The split call has no tools; the loop's calls do."""
    turns = 0

    async def traced(messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]) -> Any:
        nonlocal turns
        if openai_tools:
            turns += 1
            label = f"turn {turns}"
        else:
            label = "split"
        try:
            turn = await complete(messages, openai_tools)
        except Exception as exc:  # plan_split swallows this, so the summary alone would hide it
            out(f"[model {label}] RAISED {type(exc).__name__}: {_short(str(exc), 300)}")
            raise
        calls = ", ".join(
            f"{c['name']}({_short(c.get('args') or {}, 160)})" for c in turn.get("tool_calls") or []
        )
        says = _short(turn.get("content") or "", 200)
        out(f"[model {label}] says: {says or '-'}  | calls: {calls or '-'}")
        return turn

    return traced


def _summary(response: AskResponse, record: ExecutionRecord, out: Out) -> None:
    out("")
    out("== response ==")
    out(f"answer       : {_short(response.answer, 600)}")
    out(f"table        : {response.table_id}   universe: {response.universe}")
    out(f"geoid        : {response.geoid}")
    if response.plan:
        plan = response.plan
        out(f"plan         : {plan.dataset} {plan.years} {_short(plan.variables, 200)}")
        for geo in plan.geographies:
            out(f"               for={geo.for_spec}  in={geo.in_spec or '-'}")
    out(f"urls         : {len(response.urls)}")
    for url in response.urls:
        out(f"               {url}")
    out(
        f"years        : requested {response.requested_years}  attempted "
        f"{response.attempted_years}  succeeded {response.succeeded_years}"
    )
    out(f"rows         : {len(response.rows)}  (moe rows: {len(response.moe)})")
    if response.rows:
        out(f"first row    : {_short(response.rows[0], 300)}")
    for warning in response.warnings:
        out(f"warning      : {warning.code}: {_short(warning.detail, 240)}")
    alternatives = [item.table_id for item in response.alternatives]
    out(f"alternatives : {', '.join(alternatives) or '-'}")
    steps = "; ".join(
        f"{t['tool']} {t['ms']:g} ms {'ok' if t['ok'] else 'FAILED'}" for t in record.timings
    )
    out(f"timings      : {steps or '-'}")


async def ask_one(
    question: str,
    *,
    record: ExecutionRecord | None = None,
    complete: Callable[..., Any] | None = None,
    tools: dict[str, Any] | None = None,
    out: Out = print,
) -> AskResponse:
    """Run `question` through run_ask with a trace. Real model and tools unless injected."""
    record = record or ExecutionRecord()
    tools = tools or default_tools(record)
    for tool in tools.values():
        _trace_tool(tool, out)
    traced = _trace_complete(complete or _openai_complete, out)
    response = await run_ask(question, complete=traced, tools=tools, record=record)
    _summary(response, record, out)
    return response


def main() -> int:
    load_dotenv(ROOT / ".env")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a place name outside the console's codepage
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", nargs="*", help="the question; prompted for if omitted")
    args = parser.parse_args()
    missing = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
    if missing:
        print(f"missing in .env: {', '.join(missing)}", file=sys.stderr)
        return 2
    question = " ".join(args.question).strip() or input("Question: ").strip()
    if not question:
        print("no question given", file=sys.stderr)
        return 2
    asyncio.run(ask_one(question))
    return 0


if __name__ == "__main__":
    sys.exit(main())
