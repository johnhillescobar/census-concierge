#!/usr/bin/env python3
"""End-to-end scoreboard: real questions through POST /ask.

    python scripts/run_demo.py --repeat 3

Needs OPENAI_API_KEY and CENSUS_API_KEY. Builds of `web/dist` are required:
GET / must be the UI on the same app that scores POST /ask (`make demo` builds
it). Writes a one-line heartbeat to evidence/demo-progress.txt each trial, then
answered_rate, p95_latency_seconds,
t_llm, t_census_api, t_ours, prompt_hash and index_hash into evidence/latest.json
without removing slice-0 retrieval metrics.

HTTP 200 and answered stay separate. Gated answered_rate is long_tail
(empty long_tail is 0, never a fallback onto core/trap). overall_answered_rate
is all tiers and is not gated. t_* are means; only total p95 is a ceiling.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import sys
import time
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "golden_questions.toml"
EVIDENCE = ROOT / "evidence" / "latest.json"
PROGRESS = ROOT / "evidence" / "demo-progress.txt"
API = ROOT / "api"

load_dotenv(ROOT / ".env")
sys.path.insert(0, str(API))

_LEAK = re.compile(r"(?i)[?&]key=(?!REDACTED)[^&\s]+")
CENSUS_TOOLS = frozenset({"fetch_data", "resolve_geography"})


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def leaks_key(text: str) -> bool:
    return bool(_LEAK.search(text))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = math.ceil(p / 100 * len(ordered)) - 1
    return ordered[max(0, min(rank, len(ordered) - 1))]


def is_slice1(entry: dict[str, Any]) -> bool:
    return not bool(entry.get("holdout"))


def select_questions(
    entries: list[dict[str, Any]], tier: str | None = None
) -> list[dict[str, Any]]:
    picked = [entry for entry in entries if is_slice1(entry)]
    if tier:
        picked = [entry for entry in picked if entry.get("tier") == tier]
    return picked


def http_ok(status_code: int) -> bool:
    return status_code == 200


def inspect_served_build(client: Any) -> dict[str, Any]:
    response = client.get("/")
    text = response.text or ""
    return {
        "status_code": response.status_code,
        "content_type": str(response.headers.get("content-type") or ""),
        "has_title": "<title>census-concierge</title>" in text,
        "has_root": 'id="root"' in text,
        "acao": response.headers.get("access-control-allow-origin"),
    }


def served_build_ok(info: dict[str, Any]) -> bool:
    return (
        http_ok(int(info["status_code"]))
        and "text/html" in str(info["content_type"])
        and bool(info["has_title"])
        and bool(info["has_root"])
        and info["acao"] is None
    )


def census_urls(body: dict[str, Any]) -> list[str]:
    items = body.get("urls")
    if not isinstance(items, list):
        return []
    return [str(item) for item in items if item]


# These traps have no legal Census URL; requiring one would score a silent substitution.
_WARNING_WITHOUT_FETCH = frozenset(
    {"ambiguous_place", "geography_not_nested", "median_not_aggregatable"}
)


def is_answered(entry: dict[str, Any], *, status_code: int, body: dict[str, Any]) -> bool:
    if not http_ok(status_code):
        return False
    warnings = {
        str(item.get("code") or "") for item in body.get("warnings") or [] if isinstance(item, dict)
    }
    table_id = str(body.get("table_id") or "")
    has_url = bool(census_urls(body))
    rows = body.get("rows") or []
    expected_table = entry.get("expect_table")
    expected_warning = entry.get("expect_warning")
    if expected_warning in _WARNING_WITHOUT_FETCH:
        return expected_warning in warnings
    if expected_warning and expected_warning not in warnings:
        return False
    if expected_warning and not has_url:
        return False
    if expected_table:
        return table_id == expected_table and has_url and bool(rows)
    return bool(expected_warning)


def miss_detail(entry: dict[str, Any], *, status_code: int, body: dict[str, Any]) -> str:
    if is_answered(entry, status_code=status_code, body=body):
        return ""
    if not http_ok(status_code):
        return f"http {status_code}"
    expected_warning = entry.get("expect_warning")
    warnings = {
        str(item.get("code") or "") for item in body.get("warnings") or [] if isinstance(item, dict)
    }
    if expected_warning and expected_warning not in warnings:
        return f"missing warning {expected_warning}"
    expected_table = entry.get("expect_table")
    table_id = str(body.get("table_id") or "")
    if expected_table and table_id != expected_table:
        return f"wrong table {table_id or '(none)'}"
    if expected_warning not in _WARNING_WITHOUT_FETCH and not census_urls(body):
        return "empty url"
    if expected_table and not body.get("rows"):
        return "no rows"
    return "not answered"


def merge_evidence(
    existing: dict[str, Any],
    demo: dict[str, Any],
    *,
    answered_floor: float,
    p95_ceiling: float | None = None,
) -> dict[str, Any]:
    """Copy retrieval keys through. Promote answered_rate to the gated key once
    a run has cleared the floor (or a prior rate exists, so a regression is visible).
    A first miss stays in demo[] only — otherwise CI is red before the agent is.
    Over-ceiling p95 stays in demo[] the same way: the transcript records it,
    and a noisy run cannot turn the scoreboard red.
    """
    out = dict(existing)
    timing = ("p95_latency_seconds", "t_llm", "t_census_api", "t_ours")
    over_ceiling = p95_ceiling is not None and demo["p95_latency_seconds"] > p95_ceiling
    for key in (*timing, "prompt_hash", "index_hash"):
        if over_ceiling and key in timing:
            continue
        out[key] = demo[key]
    if demo["answered_rate"] >= answered_floor or "answered_rate" in existing:
        out["answered_rate"] = demo["answered_rate"]
    out["demo"] = demo
    return out


@dataclass
class Clock:
    llm: float = 0.0
    census: float = 0.0

    def reset(self) -> None:
        self.llm = 0.0
        self.census = 0.0


@dataclass
class Trial:
    id: str
    text: str
    tier: str
    repeat: int
    http_ok: bool
    answered: bool
    expected_table: str
    table_id: str
    url: str
    warnings: list[str]
    latency_s: float
    t_llm: float
    t_census_api: float
    t_ours: float
    detail: str
    rows: int = 0


def install_clock(clock: Clock) -> None:
    from src import ask as ask_mod

    original_complete = ask_mod._openai_complete
    original_dispatch = ask_mod.dispatch

    async def complete(
        messages: list[dict[str, Any]], openai_tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            return await original_complete(messages, openai_tools)
        finally:
            clock.llm += time.perf_counter() - started

    async def dispatch(tool: Any, call: dict[str, Any], record: Any) -> str:
        started = time.perf_counter()
        try:
            return await original_dispatch(tool, call, record)
        finally:
            elapsed = time.perf_counter() - started
            name = getattr(tool, "name", "")
            if name in CENSUS_TOOLS:
                clock.census += elapsed

    ask_mod._openai_complete = complete  # type: ignore[method-assign]
    ask_mod.dispatch = dispatch  # type: ignore[method-assign]


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _rate(trials: list[Trial]) -> float:
    return round(sum(trial.answered for trial in trials) / len(trials), 3) if trials else 0.0


def trial_record(trial: Trial) -> dict[str, Any]:
    return {
        "id": trial.id,
        "repeat": trial.repeat,
        "question": trial.text,
        "tier": trial.tier,
        "expected": trial.expected_table,
        "got": trial.table_id,
        "url": trial.url,
        "http_ok": trial.http_ok,
        "answered": trial.answered,
        "warnings": trial.warnings,
        "detail": trial.detail,
        "latency_s": round(trial.latency_s, 3),
        "t_llm": round(trial.t_llm, 3),
        "t_census_api": round(trial.t_census_api, 3),
        "t_ours": round(trial.t_ours, 3),
        "rows": trial.rows,
    }


def summarize(trials: list[Trial], *, repeat: int, prompt: str, index: str) -> dict[str, Any]:
    latencies = [trial.latency_s for trial in trials]
    long_tail = [trial for trial in trials if trial.tier == "long_tail"]
    records = [trial_record(trial) for trial in trials]
    by_tier = {
        tier: {
            "n": len(group),
            "answered_rate": _rate(group),
            "http_ok_rate": round(sum(t.http_ok for t in group) / len(group), 3) if group else 0.0,
        }
        for tier, group in (
            (name, [trial for trial in trials if trial.tier == name])
            for name in ("core", "long_tail", "trap")
        )
        if group
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "repeat": repeat,
        "n": len(trials),
        "answered_rate": _rate(long_tail),
        "overall_answered_rate": _rate(trials),
        "p95_latency_seconds": round(percentile(latencies, 95), 3),
        "t_llm": _mean([trial.t_llm for trial in trials]),
        "t_census_api": _mean([trial.t_census_api for trial in trials]),
        "t_ours": _mean([trial.t_ours for trial in trials]),
        "prompt_hash": prompt,
        "index_hash": index,
        "by_tier": by_tier,
        "trials": records,
        "misses": [record for record in records if not record["answered"]],
    }


def _ask(client: Any, clock: Clock, entry: dict[str, Any], repeat: int) -> Trial:
    from src.census_url import redact_text

    clock.reset()
    started = time.perf_counter()
    status = 0
    body: dict[str, Any] = {}
    detail = ""
    try:
        response = client.post("/ask", json={"question": entry["text"]})
        status = response.status_code
        payload = response.json()
        body = payload if isinstance(payload, dict) else {}
    except Exception as exc:  # noqa: BLE001 - one trial must not abort the suite
        detail = redact_text(str(exc))
        status = 0
    elapsed = time.perf_counter() - started
    t_llm = clock.llm
    t_census = clock.census
    t_ours = max(0.0, elapsed - t_llm - t_census)
    url = redact_text(" ".join(census_urls(body)))
    warnings = [
        str(item.get("code") or "") for item in body.get("warnings") or [] if isinstance(item, dict)
    ]
    if not detail:
        detail = miss_detail(entry, status_code=status, body=body)
    return Trial(
        id=str(entry["id"]),
        text=str(entry["text"]),
        tier=str(entry.get("tier") or "core"),
        repeat=repeat,
        http_ok=http_ok(status),
        answered=is_answered(entry, status_code=status, body=body),
        expected_table=str(entry.get("expect_table") or ""),
        table_id=str(body.get("table_id") or ""),
        url=url,
        warnings=warnings,
        latency_s=elapsed,
        t_llm=t_llm,
        t_census_api=t_census,
        t_ours=t_ours,
        detail=detail,
        rows=len(body.get("rows") or []),
    )


def _print_report(summary: dict[str, Any], floors: tuple[float, float]) -> None:
    answered_floor, p95_ceiling = floors
    print(f"DEMO  repeat={summary['repeat']}  n_trials={summary['n']}\n")
    for tier, stats in summary["by_tier"].items():
        print(
            f"  {tier:<10} n={stats['n']:<3}  answered={stats['answered_rate']:.0%}"
            f"   http_ok={stats['http_ok_rate']:.0%}"
        )
    print(
        f"\n  answered_rate  {summary['answered_rate']:.3f}  (long_tail, floor {answered_floor:g})"
        f"   overall {summary['overall_answered_rate']:.3f}"
    )
    print(f"  p95_latency    {summary['p95_latency_seconds']:.3f}s  (ceiling {p95_ceiling:g}s)")
    print(
        f"  t_llm          {summary['t_llm']:.3f}s   t_census_api {summary['t_census_api']:.3f}s"
        f"   t_ours {summary['t_ours']:.3f}s   (means; not gated)"
    )
    print(f"  prompt_hash    {summary['prompt_hash']}   index_hash {summary['index_hash']}")
    if summary["misses"]:
        print("\nMISSES\n")
        for miss in summary["misses"]:
            print(
                f"  {miss['id']} r{miss['repeat']}  expected {miss['expected'] or '—'}"
                f"  got {miss['got'] or '—'}  http_ok={miss['http_ok']}"
                f"  {miss['detail']}"
            )
            print(f"      {miss['question']}")
            if miss["url"]:
                print(f"      {miss['url']}")


def write_progress(done: int, total: int, trial: Trial) -> None:
    """One-line heartbeat so a long `--repeat` run is readable without stdout."""
    mark = "ok" if trial.answered else "MISS"
    line = (
        f"{datetime.now(UTC).isoformat(timespec='seconds')}  "
        f"{done}/{total}  {mark}  {trial.id} r{trial.repeat}  "
        f"{trial.latency_s:.1f}s  {trial.table_id or '—'}\n"
    )
    PROGRESS.write_text(line, encoding="utf-8")
    print(line, end="", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--tier", choices=["core", "long_tail", "trap"])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.repeat < 1:
        print("--repeat must be >= 1", file=sys.stderr)
        return 2

    missing = [name for name in ("OPENAI_API_KEY", "CENSUS_API_KEY") if not os.environ.get(name)]
    if missing:
        print(f"Missing {', '.join(missing)} in the environment.", file=sys.stderr)
        return 2
    print(
        "OPENAI_API_KEY present=True  CENSUS_API_KEY present=True  (values not printed)",
        flush=True,
    )

    with QUESTIONS.open("rb") as handle:
        entries = tomllib.load(handle)["question"]
    questions = select_questions(entries, args.tier)
    if not questions:
        print("No in-scope questions.")
        return 1

    from fastapi.testclient import TestClient
    from src.main import app
    from src.prompts import ROLE
    from src.retrieval.index import index_hash

    with (ROOT / "budgets.toml").open("rb") as handle:
        budgets = tomllib.load(handle)
    floors = (
        float(budgets["quality"]["answered_rate_min"]),
        float(budgets["performance"]["p95_latency_seconds"]),
    )

    clock = Clock()
    install_clock(clock)
    prompt = short_hash(ROLE)
    index = index_hash()
    trials: list[Trial] = []
    client = TestClient(app)
    served = inspect_served_build(client)
    print(
        f"served_build  GET / {served['status_code']}  "
        f"{served['content_type'] or 'no-content-type'}  "
        f"title={'yes' if served['has_title'] else 'no'}  "
        f"root={'yes' if served['has_root'] else 'no'}  "
        f"acao={served['acao'] or 'none'}",
        flush=True,
    )
    if not served_build_ok(served):
        print(
            "Frontend is not being served. "
            "Build it first: npm --prefix web ci && npm --prefix web run build",
            file=sys.stderr,
        )
        return 2
    total = len(questions) * args.repeat
    for round_id in range(1, args.repeat + 1):
        for entry in questions:
            trial = _ask(client, clock, entry, round_id)
            trials.append(trial)
            write_progress(len(trials), total, trial)
            if args.verbose:
                mark = "ok" if trial.answered else "MISS"
                print(
                    f"  {mark:<4} {trial.id} r{round_id}  {trial.latency_s:.1f}s"
                    f"  {trial.table_id or '—'}  {trial.detail}"
                )

    summary = summarize(trials, repeat=args.repeat, prompt=prompt, index=index)
    blob = json.dumps(summary)
    if leaks_key(blob):
        print("Refusing to write evidence: a Census key leaked into the record.", file=sys.stderr)
        return 2

    existing: dict[str, Any] = {}
    if EVIDENCE.exists():
        with contextlib.suppress(ValueError):
            existing = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    merged = merge_evidence(existing, summary, answered_floor=floors[0], p95_ceiling=floors[1])
    if leaks_key(json.dumps(merged)):
        print("Refusing to write evidence: a Census key leaked into the record.", file=sys.stderr)
        return 2
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    _print_report(summary, floors)
    print(f"\nWrote {EVIDENCE.relative_to(ROOT)}\n")
    met = summary["answered_rate"] >= floors[0] and summary["p95_latency_seconds"] <= floors[1]
    if not met:
        print("Floors not met. Metrics are recorded; this is not done.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
