#!/usr/bin/env python3
"""CC-113 latency probe: where does /ask time go (LLM, Census API, ours)?

    python scripts/latency_probe.py run --arms A0,L1,L2,C1 --repeat 3 --out OUT.jsonl
    python scripts/latency_probe.py run --arms A0 --inject census --out OUT.jsonl
    python scripts/latency_probe.py replay --source OUT.jsonl --out REPLAY.jsonl
    python scripts/latency_probe.py report OUT.jsonl
    python scripts/latency_probe.py validity validity-*.jsonl

Design: evidence/slice-6/latency-experiment-design.md. Nothing under api/src changes.
Spans are wrapped at the SDK / httpx boundary (leaf calls), so a nested call is never
counted twice. Time is attributed to exactly one name per instant (priority below), and
whatever no span covers is reported as `unaccounted`, never folded into "ours".
Arms are interleaved (repeat, arm, question) so provider drift cannot line up with one arm.
Sealed runs: pass --questions-file and --aggregate-only; no question text is written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_demo as demo  # noqa: E402  (loads .env and puts api/ on sys.path)

ROOT = demo.ROOT
PROBE_IDS = (
    ("q08", "q18", "q21")  # Vermont disability, Milwaukee tenure, Rio Grande Valley SNAP
    + ("q05", "q07", "q10", "q12", "q14", "q16", "q19", "q26")
    + ("q28", "q30", "q33", "q36", "q38", "q40", "q43")
    + ("t03", "t08", "t11", "t15", "q01", "q03")
)
# One instant belongs to the first active name in this order.
PRIORITY = (
    "llm",
    "census",
    "retrieval",
    "guards",
    "assemble",
    "tool:search_tables",
    "tool:build_url",
    "tool:resolve_geography",
    "tool:fetch_data",
    "finish",
)
ARMS = ("A0", "L1", "L2", "C1")
INJECT_TARGETS = ("census", "chat", "rerank", "embed", "assemble", "unwrapped")
# Gemini rejects a server deadline under 10 s (HTTP 400), so L2 bounds the wait client-side.
RERANK_TIMEOUT_S = 3.0
BOUND_POOL = ThreadPoolExecutor(max_workers=16)


@dataclass
class Span:
    name: str
    start: float
    end: float
    meta: dict[str, Any] = field(default_factory=dict)


class Recorder:
    """One per trial. `spans` and `injected` are appended from several threads."""

    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.spans: list[Span] = []
        self.injected: list[tuple[float, float]] = []
        self.arm = "A0"

    def add(self, name: str, start: float, **meta: Any) -> None:
        self.spans.append(Span(name, start, time.perf_counter(), meta))


class State:
    rec: Recorder | None = None
    arm: str = "A0"
    inject: str = ""
    inject_seconds: float = 5.0


STATE = State()


def union(intervals: list[tuple[float, float]]) -> float:
    total, end = 0.0, -math.inf
    for start, stop in sorted(intervals):
        total += max(0.0, stop - max(start, end))
        end = max(end, stop)
    return total


def overlap(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Length of (union of a) intersected with (union of b)."""
    return max(0.0, union(a) + union(b) - union(a + b))


def attribute(spans: list[Span], t0: float, t1: float) -> dict[str, float]:
    """Seconds per name with each instant given to one name; the rest is `unaccounted`."""
    points = sorted({t0, t1, *(max(t0, min(t1, p)) for s in spans for p in (s.start, s.end))})
    out: dict[str, float] = {}
    for lo, hi in zip(points, points[1:], strict=False):
        active = {s.name for s in spans if s.start <= lo and s.end >= hi}
        name = next((n for n in PRIORITY if n in active), "unaccounted")
        out[name] = out.get(name, 0.0) + (hi - lo)
    return out


def _tier(url: str, method: str) -> str | None:
    host = urlparse(url).netloc
    if host.endswith("api.openai.com"):
        if "/embeddings" in url:
            return "embed"
        return "rerank" if method == "sync" else "chat"
    if host.endswith("googleapis.com"):
        return "rerank"
    return "census" if host.endswith("census.gov") else None


def _slow(rec: Recorder | None, tier: str | None) -> float:
    """The injected delay for this call, 0 when this call is not the injection target."""
    want = {"census": "census", "chat": "chat", "rerank": "rerank", "embed": "embed"}
    if rec is None or not tier or want.get(STATE.inject) != tier:
        return 0.0
    return STATE.inject_seconds


def install_injection() -> None:
    """Sleep inside the real transport (below every span wrapper), as a slow network would.

    The OpenAI SDK sends through its own `httpx2`; Gemini and Census use `httpx`. Patch both.
    """
    import importlib

    for name in ("httpx", "httpx2"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        sync_send, async_send = module.Client.send, module.AsyncClient.send

        def send(self: Any, request: Any, *, _real: Any = sync_send, **kw: Any) -> Any:
            rec, delay = STATE.rec, _slow(STATE.rec, _tier(str(request.url), "sync"))
            if delay:
                began = time.perf_counter()
                time.sleep(delay)
                rec.injected.append((began, time.perf_counter()))  # type: ignore[union-attr]
            return _real(self, request, **kw)

        async def asend(self: Any, request: Any, *, _real: Any = async_send, **kw: Any) -> Any:
            rec, delay = STATE.rec, _slow(STATE.rec, _tier(str(request.url), "async"))
            if delay:
                began = time.perf_counter()
                await asyncio.sleep(delay)
                rec.injected.append((began, time.perf_counter()))  # type: ignore[union-attr]
            return await _real(self, request, **kw)

        module.Client.send = send
        module.AsyncClient.send = asend

    from src import ask as ask_mod

    def delayed(original: Any) -> Any:
        def call(*a: Any, **kw: Any) -> Any:
            if STATE.rec is not None:
                began = time.perf_counter()
                time.sleep(STATE.inject_seconds)
                STATE.rec.injected.append((began, time.perf_counter()))
            return original(*a, **kw)

        return call

    if STATE.inject == "assemble":
        ask_mod.assemble = delayed(ask_mod.assemble)  # type: ignore[assignment]
    if STATE.inject == "unwrapped":
        ask_mod.latest_vintages = delayed(ask_mod.latest_vintages)  # type: ignore[assignment]


def _usage(response: Any, tier: str) -> tuple[int, int]:
    if response is None:
        return 0, 0
    if tier == "rerank" and hasattr(response, "usage_metadata"):
        meta = response.usage_metadata
        return int(meta.prompt_token_count or 0), int(meta.candidates_token_count or 0)
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return int(getattr(usage, "prompt_tokens", 0) or 0), int(
        getattr(usage, "completion_tokens", 0) or 0
    )


def install_spans() -> None:
    import httpx
    from google import genai
    from openai.resources.chat.completions import AsyncCompletions, Completions
    from openai.resources.embeddings import Embeddings
    from src import ask as ask_mod
    from src import guards
    from src.census_url import redact_text
    from src.retrieval import index, rerank

    def llm_span(tier: str, rec: Recorder, began: float, response: Any, model: str) -> None:
        tokens_in, tokens_out = _usage(response, tier)
        rec.add("llm", began, tier=tier, model=model, tokens_in=tokens_in, tokens_out=tokens_out)

    chat_create = AsyncCompletions.create
    sync_create = Completions.create
    embed_create = Embeddings.create

    async def chat(self: Any, *a: Any, **kw: Any) -> Any:
        rec, began = STATE.rec, time.perf_counter()
        response = await chat_create(self, *a, **kw)
        if rec:
            llm_span("chat", rec, began, response, str(kw.get("model")))
        return response

    def sync_chat(self: Any, *a: Any, **kw: Any) -> Any:
        rec, began = STATE.rec, time.perf_counter()
        response = sync_create(self, *a, **kw)
        if rec:
            llm_span("rerank", rec, began, response, str(kw.get("model")))
        return response

    def embed(self: Any, *a: Any, **kw: Any) -> Any:
        rec, began = STATE.rec, time.perf_counter()
        response = embed_create(self, *a, **kw)
        if rec:
            llm_span("embed", rec, began, response, str(kw.get("model")))
        return response

    AsyncCompletions.create = chat  # type: ignore[method-assign]
    Completions.create = sync_chat  # type: ignore[method-assign]
    Embeddings.create = embed  # type: ignore[method-assign]

    generate = genai.models.Models.generate_content

    def gemini(self: Any, *a: Any, **kw: Any) -> Any:
        rec, began = STATE.rec, time.perf_counter()
        response = None
        try:
            if STATE.arm == "L2":
                future = BOUND_POOL.submit(generate, self, *a, **kw)
                try:
                    response = future.result(timeout=RERANK_TIMEOUT_S)
                except FutureTimeout as exc:
                    raise TimeoutError("rerank bound exceeded") from exc
            else:
                response = generate(self, *a, **kw)
            return response
        finally:  # a timeout loses the response; the span still records the wait
            if rec:
                llm_span("rerank", rec, began, response, str(kw.get("model")))

    genai.models.Models.generate_content = gemini  # type: ignore[method-assign]

    real_choose = rerank.choose

    def choose(question: str, candidates: Any, *a: Any, **kw: Any) -> Any:
        if STATE.arm == "L1":
            kw["model"] = "gpt-4o-mini"
        return real_choose(question, candidates, *a, **kw)

    rerank.choose = choose  # type: ignore[assignment]

    real_get = httpx.get

    def get(url: Any, *a: Any, **kw: Any) -> Any:
        rec, began = STATE.rec, time.perf_counter()
        status = 0
        try:
            response = real_get(url, *a, **kw)
            status = response.status_code
            return response
        finally:
            if rec:
                text = redact_text(str(url))
                rec.add(
                    "census",
                    began,
                    url=text,
                    status=status,
                    level=demo.fetched_level(text),
                    year=int(text.split("/data/")[1].split("/")[0]) if "/data/" in text else 0,
                )

    httpx.get = get  # type: ignore[assignment]

    def wrap_sync(module: Any, attr: str, name: str) -> None:
        original = getattr(module, attr)

        def call(*a: Any, **kw: Any) -> Any:
            rec, began = STATE.rec, time.perf_counter()
            try:
                return original(*a, **kw)
            finally:
                if rec:
                    rec.add(name, began)

        setattr(module, attr, call)

    wrap_sync(index, "search", "retrieval")
    wrap_sync(guards, "evaluate", "guards")
    wrap_sync(ask_mod, "assemble", "assemble")

    real_finish = ask_mod.finish_tools

    async def finish(*a: Any, **kw: Any) -> Any:
        rec, began = STATE.rec, time.perf_counter()
        try:
            return await real_finish(*a, **kw)
        finally:
            if rec:
                rec.add("finish", began)

    ask_mod.finish_tools = finish  # type: ignore[assignment]

    real_dispatch = ask_mod.dispatch

    async def dispatch(tool: Any, call: dict[str, Any], record: Any) -> str:
        rec, began = STATE.rec, time.perf_counter()
        try:
            return await real_dispatch(tool, call, record)
        finally:
            if rec:
                rec.add(f"tool:{getattr(tool, 'name', '')}", began)

    ask_mod.dispatch = dispatch  # type: ignore[assignment]


def percentile(values: list[float], p: float) -> float:
    return round(demo.percentile(values, p), 3)


def probe_entries(path: Path | None) -> list[dict[str, Any]]:
    with (path or demo.QUESTIONS).open("rb") as handle:
        entries = demo.select_questions(tomllib.load(handle)["question"])
    if path:
        return entries
    by_id = {str(e["id"]): e for e in entries}
    return [by_id[i] for i in PROBE_IDS if i in by_id]


def run_trial(client: Any, entry: dict[str, Any], arm: str, repeat: int) -> dict[str, Any]:
    from src import fetch
    from src.census_url import redact_text

    rec = Recorder()
    STATE.rec, STATE.arm = rec, arm
    fetch.MAX_IN_FLIGHT = 1 if arm == "C1" else 5
    status, body = 0, {}
    try:
        response = client.post("/ask", json={"question": entry["text"]})
        status = response.status_code
        payload = response.json()
        body = payload if isinstance(payload, dict) else {}
    except Exception as exc:  # noqa: BLE001 - one trial must not abort the run
        body = {"error": redact_text(str(exc))}
    end = time.perf_counter()
    STATE.rec = None
    spans = rec.spans
    by_name = attribute(spans, rec.t0, end)
    inclusive = {
        n: union([(s.start, s.end) for s in spans if s.name == n]) for n in {s.name for s in spans}
    }
    llm = [s for s in spans if s.name == "llm"]
    cen = [s for s in spans if s.name == "census"]
    window = [(s.start, s.end) for s in spans]
    record = {
        "id": str(entry["id"]),
        "tier": str(entry.get("tier") or "core"),
        "arm": arm,
        "repeat": repeat,
        "total_s": round(end - rec.t0, 3),
        "http_ok": demo.http_ok(status),
        "answered": demo.is_answered(entry, status_code=status, body=body),
        "table_id": str(body.get("table_id") or ""),
        "expected": str(entry.get("expect_table") or ""),
        "exclusive": {k: round(v, 3) for k, v in by_name.items()},
        "inclusive": {k: round(v, 3) for k, v in inclusive.items()},
        "unaccounted_s": round(by_name.get("unaccounted", 0.0), 3),
        "llm_calls": [
            {
                "tier": s.meta.get("tier"),
                "model": s.meta.get("model"),
                "s": round(s.end - s.start, 3),
                "in": s.meta.get("tokens_in", 0),
                "out": s.meta.get("tokens_out", 0),
            }
            for s in llm
        ],
        "census_requests": [
            {
                "level": s.meta.get("level"),
                "year": s.meta.get("year"),
                "status": s.meta.get("status"),
                "s": round(s.end - s.start, 3),
                "url": s.meta.get("url"),
            }
            for s in cen
        ],
        "injected_s": round(union(rec.injected), 3),
    }
    if rec.injected:
        record["injected_inside"] = {
            n: round(overlap(rec.injected, [(s.start, s.end) for s in spans if s.name == n]), 3)
            for n in sorted({s.name for s in spans})
        }
        record["injected_covered_by_any"] = round(overlap(rec.injected, window), 3)
    return record


def build_client() -> Any:
    from fastapi.testclient import TestClient
    from src.main import app

    install_injection()  # innermost: the sleep must sit below every span wrapper
    install_spans()
    return TestClient(app)


def cmd_run(args: argparse.Namespace) -> int:
    needed = ("OPENAI_API_KEY", "CENSUS_API_KEY", "GEMINI_API_KEY")  # no Gemini: rerank falls back
    missing = [k for k in needed if not os.environ.get(k)]
    if missing:
        print(f"Missing {', '.join(missing)}", file=sys.stderr)
        return 2
    STATE.inject, STATE.inject_seconds = args.inject, args.inject_seconds
    entries = probe_entries(Path(args.questions_file) if args.questions_file else None)
    if args.ids:
        entries = [e for e in entries if str(e["id"]) in args.ids.split(",")]
    arms = args.arms.split(",")
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        print(f"Unknown arm(s) {unknown}; choose from {ARMS}", file=sys.stderr)
        return 2
    client = build_client()
    out = Path(args.out)
    if args.aggregate_only and not (out.parent.name == "evidence" and "sealed" in out.name):
        print(
            "--aggregate-only needs --out evidence/<name containing 'sealed'> (gitignored)",
            file=sys.stderr,
        )
        return 2
    if out.exists() and out.stat().st_size and not args.append:
        print(f"{out} exists; pass --append to add rows or choose a new --out", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    total, done = len(entries) * len(arms) * args.repeat, 0
    with out.open("a", encoding="utf-8") as sink:
        for repeat in range(1, args.repeat + 1):
            for arm in arms:
                for entry in entries:
                    record = run_trial(client, entry, arm, repeat)
                    if args.inject:
                        record["inject"] = [args.inject, args.inject_seconds]
                    if args.aggregate_only:
                        for field_name in ("census_requests", "table_id", "expected"):
                            record.pop(field_name, None)
                        record["id"] = f"sealed-{done}"
                    line = json.dumps(record)
                    if demo.leaks_key(line):
                        print("Refusing to write: a Census key leaked.", file=sys.stderr)
                        return 2
                    sink.write(line + "\n")
                    sink.flush()
                    done += 1
                    print(
                        f"{done}/{total} {arm} r{repeat} {record['id']} {record['total_s']}s "
                        f"unaccounted={record['unaccounted_s']}s",
                        flush=True,
                    )
    return 0


def _get(url: str) -> tuple[int, float]:
    import httpx

    began = time.perf_counter()
    try:
        status = httpx.get(url, timeout=60.0).status_code
    except httpx.HTTPError:  # a hang or a dropped connection is a measurement, status 0
        status = 0
    return status, time.perf_counter() - began


def cold_variant(url: str, ordinal: int) -> str | None:
    """The same query plus one real sibling variable of the table, so the URL is new to the server.

    `ordinal` picks a different sibling each time; None when the table has no sibling left.
    An invented variable ID returns HTTP 400, which is not a cold request: the first replay
    did exactly that and its cold arm was discarded.
    """
    import gzip
    from urllib.parse import parse_qs

    parts = urlparse(url)
    asked = parse_qs(parts.query).get("get", [""])[0].split(",")
    bits = parts.path.split("/")
    if "data" not in bits or "acs" not in bits:
        return None
    year, dataset = bits[bits.index("data") + 1], bits[bits.index("acs") + 1]
    path = demo.ROOT / "data" / "raw" / dataset / year / "variables.json.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        known = json.load(handle)["variables"]
    names = [v for v in asked if v in known and v[1:2].isdigit()]  # not NAME or GEO_ID
    if not names:
        return None
    table = names[0].split("_")[0]
    siblings = sorted(k for k in known if k.startswith(f"{table}_") and k.endswith(("E", "M")))
    siblings = [k for k in siblings if k not in asked]
    if ordinal >= len(siblings):
        return None
    return url.replace("get=", f"get={siblings[ordinal]},", 1)


def cmd_replay(args: argparse.Namespace) -> int:
    from src.census_url import CensusURL

    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        print("Missing CENSUS_API_KEY", file=sys.stderr)
        return 2
    sets: dict[str, list[str]] = {}
    for line in Path(args.source).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["arm"] == "A0" and record["repeat"] == 1 and record.get("census_requests"):
            sets[record["id"]] = [r["url"] for r in record["census_requests"] if r["url"]]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as sink:
        for repeat in range(1, args.repeat + 1):
            for slot, workers in enumerate((1, 5, 12)):
                for qid, urls in sets.items():
                    for temp in args.temperatures.split(","):
                        ordinal = (repeat - 1) * 3 + slot
                        distinct = list(dict.fromkeys(urls))
                        batch = [
                            cold_variant(u, ordinal) if temp == "cold" else u for u in distinct
                        ]
                        batch = [b for b in batch if b]
                        full = [CensusURL(b).with_key(key) for b in batch]
                        began = time.perf_counter()
                        with ThreadPoolExecutor(max_workers=workers) as pool:
                            results = list(pool.map(_get, full))
                        record = {
                            "id": qid,
                            "repeat": repeat,
                            "workers": workers,
                            "temperature": temp,
                            "requests": len(batch),
                            "wall_s": round(time.perf_counter() - began, 3),
                            "per_request_s": [round(r[1], 3) for r in results],
                            "statuses": [r[0] for r in results],
                            "levels": [demo.fetched_level(b) for b in batch],
                            "years": [
                                int(b.split("/data/")[1].split("/")[0]) if "/data/" in b else 0
                                for b in batch
                            ],
                        }
                        sink.write(json.dumps(record) + "\n")
                        sink.flush()
                        print(qid, workers, temp, record["wall_s"], flush=True)
    return 0


def stats(values: list[float]) -> str:
    if not values:
        return "n=0"
    return (
        f"n={len(values)} mean={statistics.fmean(values):.2f} "
        f"p50={percentile(values, 50)} p95={percentile(values, 95)} max={max(values):.2f}"
    )


def cmd_report(args: argparse.Namespace) -> int:
    rows = [json.loads(line) for p in args.files for line in Path(p).read_text().splitlines()]
    for arm in sorted({r["arm"] for r in rows}):
        for tier in ("all", "long_tail", "trap"):
            sel = [r for r in rows if r["arm"] == arm and (tier == "all" or r["tier"] == tier)]
            if not sel:
                continue
            under = [r for r in sel if r["total_s"] <= 60]
            print(f"\n## arm {arm}, tier {tier}")
            print(f"total (all)        {stats([r['total_s'] for r in sel])}")
            print(f"total (<=60 s)     {stats([r['total_s'] for r in under])}")
            names = sorted({n for r in sel for n in r["exclusive"]})
            for name in names:
                print(f"  {name:<24} {stats([r['exclusive'].get(name, 0.0) for r in sel])}")
            calls = [c for r in sel for c in r["llm_calls"]]
            for t in ("chat", "rerank", "embed"):
                own = [c for c in calls if c["tier"] == t]
                if own:
                    toks = f"in={sum(c['in'] for c in own)} out={sum(c['out'] for c in own)}"
                    print(
                        f"  llm:{t:<8} calls/q={len(own) / len(sel):.2f} {toks} s: "
                        f"{stats([c['s'] for c in own])}"
                    )
            census = [c for r in sel for c in r.get("census_requests", [])]
            if census:
                print(
                    f"  census req/q={len(census) / len(sel):.2f}  "
                    f"{stats([c['s'] for c in census])}"
                )
            ok = sum(r["unaccounted_s"] <= 0.5 for r in sel) / len(sel)
            print(
                f"  reconciled within 0.5 s: {ok:.1%}  answered: "
                f"{sum(r['answered'] for r in sel) / len(sel):.3f}"
            )
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Per arm: totals per repeat (spread), rerank and chat per-call, table match, answered."""
    rows = [json.loads(line) for p in args.files for line in Path(p).read_text().splitlines()]
    for tier in ("all", "long_tail", "trap"):
        print(f"\n## tier {tier}   (p50 / p95 of trial total, seconds; per repeat then pooled)")
        for arm in sorted({r["arm"] for r in rows}):
            sel = [r for r in rows if r["arm"] == arm and (tier == "all" or r["tier"] == tier)]
            if not sel:
                continue
            per = []
            for rep in sorted({r["repeat"] for r in sel}):
                t = [r["total_s"] for r in sel if r["repeat"] == rep]
                per.append(f"r{rep}: {percentile(t, 50)}/{percentile(t, 95)}")
            tot = [r["total_s"] for r in sel]
            rr = [c["s"] for r in sel for c in r["llm_calls"] if c["tier"] == "rerank"]
            ch = [c["s"] for r in sel for c in r["llm_calls"] if c["tier"] == "chat"]
            scored = [r for r in sel if r.get("expected") and r["tier"] != "trap"]
            match = sum(r["table_id"] == r["expected"] for r in scored) / max(1, len(scored))
            answered = sum(r["answered"] for r in sel) / len(sel)
            census = statistics.fmean(r["exclusive"].get("census", 0) for r in sel)
            print(
                f"{arm}  n={len(sel)}  pooled {percentile(tot, 50)}/{percentile(tot, 95)}  "
                f"[{'  '.join(per)}]\n"
                f"    rerank/call p50={percentile(rr, 50)} p95={percentile(rr, 95)}  "
                f"chat/call p50={percentile(ch, 50)} p95={percentile(ch, 95)}  "
                f"chat calls/q={len(ch) / len(sel):.2f}\n"
                f"    answered={answered:.3f}  table-match={match:.3f}  census s mean={census:.2f}"
            )
    return 0


def cmd_duplicates(args: argparse.Namespace) -> int:
    """Census requests that repeat an earlier URL in the same trial, and the slow trials."""
    rows = [json.loads(line) for p in args.files for line in Path(p).read_text().splitlines()]
    total = dups = with_dup = 0
    dup_seconds: list[float] = []
    for r in rows:
        seen: set[str] = set()
        seconds, n = 0.0, 0
        for c in r.get("census_requests", []):
            total += 1
            if c["url"] in seen:
                dups, n, seconds = dups + 1, n + 1, seconds + c["s"]
            seen.add(c["url"])
        with_dup += bool(n)
        dup_seconds.append(seconds)
    print(f"requests {total}; exact repeats within a trial {dups} ({dups / total:.1%})")
    print(
        f"trials with a repeat {with_dup} of {len(rows)}; repeat request seconds per trial: "
        f"mean {statistics.fmean(dup_seconds):.2f} p95 {percentile(dup_seconds, 95)} "
        f"max {max(dup_seconds, default=0.0):.2f}"
    )
    slow = [r for r in rows if r["total_s"] > args.over]
    print(f"\ntrials over {args.over} s: {len(slow)}")
    for r in slow:
        chat = [c for c in r["llm_calls"] if c["tier"] == "chat"]
        top = max(r["llm_calls"], key=lambda c: c["s"], default={"tier": "-", "s": 0})
        urls = [c["url"] for c in r.get("census_requests", [])]
        print(
            f"  {r['arm']} {r['id']} {r['total_s']}s llm={r['exclusive'].get('llm', 0):.1f} "
            f"census={r['exclusive'].get('census', 0):.1f} chat_calls={len(chat)} "
            f"requests={len(urls)} distinct={len(set(urls))} slowest_llm={top['tier']} {top['s']}"
        )
    xs = [sum(c["tier"] == "chat" for c in r["llm_calls"]) for r in rows]
    ys = [r["total_s"] for r in rows]
    corr = statistics.correlation(xs, ys) if len(set(xs)) > 1 else 0.0
    print(f"\ncorrelation(chat calls, trial total) = {corr:.2f}")
    return 0


def cmd_replay_report(args: argparse.Namespace) -> int:
    """Wall seconds by fetch concurrency and temperature, plus the named questions."""
    rows = [json.loads(line) for line in Path(args.file).read_text().splitlines()]
    if args.temperature:
        rows = [r for r in rows if r["temperature"] == args.temperature]
    codes: dict[tuple[str, int], int] = {}
    for r in rows:
        for status in r["statuses"]:
            codes[(r["temperature"], status)] = codes.get((r["temperature"], status), 0) + 1
    print("status counts by temperature:", dict(sorted(codes.items())))
    for temp in ("cold", "warm"):
        for workers in (1, 5, 12):
            sel = [r for r in rows if r["workers"] == workers and r["temperature"] == temp]
            if not sel:
                continue
            many = [r["wall_s"] for r in sel if r["requests"] >= 3]
            few = [r["wall_s"] for r in sel if r["requests"] < 3]
            per = [
                percentile(
                    [r["wall_s"] for r in sel if r["repeat"] == k and r["requests"] >= 3], 50
                )
                for k in sorted({r["repeat"] for r in sel})
            ]
            print(
                f"{temp} workers={workers}: >=3 requests median {percentile(many, 50)} "
                f"(per repeat {per}); <3 requests median {percentile(few, 50)}; "
                f"all p95 {percentile([r['wall_s'] for r in sel], 95)}"
            )
    by_level: dict[str, list[float]] = {}
    for r in rows:
        if r["workers"] == 1 and r["temperature"] == "warm":
            for level, secs in zip(r["levels"], r["per_request_s"], strict=False):
                by_level.setdefault(level, []).append(secs)
    for level, secs in sorted(by_level.items()):
        print(
            f"warm per-request level={level}: n={len(secs)} p50={percentile(secs, 50)} "
            f"p95={percentile(secs, 95)}"
        )
    for qid in args.ids.split(","):
        for workers in (1, 5, 12):
            sel = [
                r
                for r in rows
                if r["id"] == qid and r["workers"] == workers and r["temperature"] == "warm"
            ]
            if sel:
                print(
                    f"{qid} workers={workers}: requests={sel[0]['requests']} "
                    f"wall median {percentile([r['wall_s'] for r in sel], 50)}"
                )
    return 0


# Which attributed name must hold the injected seconds for each injection target.
EXPECT = {
    "census": "census",
    "chat": "llm",
    "rerank": "llm",
    "embed": "llm",
    "assemble": "assemble",
}


def cmd_validity(args: argparse.Namespace) -> int:
    """Pass when the injected seconds sit inside the right name (within 0.5 s) for every trial.

    `unwrapped` is the negative control: the delay is in no span, so the reconciliation check
    must FAIL (unaccounted holds it); the control passes when it does.
    """
    ok_all = True
    for path in args.files:
        rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
        target = rows[0]["inject"][0]
        for r in rows:
            gt = r["injected_s"]
            inside = r.get("injected_inside", {})
            if target == "unwrapped":
                good = r["unaccounted_s"] >= gt - 0.5 and r["unaccounted_s"] > 0.5
                note = f"unaccounted={r['unaccounted_s']}"
            else:
                held = inside.get(EXPECT[target], 0.0)
                excl = r.get("exclusive", {}).get(EXPECT[target], 0.0)
                good = gt > 0 and abs(held - gt) <= 0.5 and excl >= gt - 0.5
                note = f"{EXPECT[target]} holds {held} (excl {excl:.1f})"
            ok_all &= good
            print(
                f"{target:<10} {r['id']:<4} injected={gt:<6} {note:<28} "
                f"{'PASS' if good else 'FAIL'}"
            )
    print("VALIDITY", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--arms", default="A0")
    run.add_argument("--repeat", type=int, default=3)
    run.add_argument("--out", required=True)
    run.add_argument("--inject", choices=INJECT_TARGETS, default="")
    run.add_argument("--inject-seconds", type=float, default=5.0)
    run.add_argument("--questions-file")
    run.add_argument("--ids", default="")
    run.add_argument("--aggregate-only", action="store_true")
    run.add_argument("--append", action="store_true", help="add to an existing --out file")
    replay = sub.add_parser("replay")
    replay.add_argument("--source", required=True)
    replay.add_argument("--out", required=True)
    replay.add_argument("--repeat", type=int, default=3)
    replay.add_argument("--temperatures", default="cold,warm", help="comma list of cold, warm")
    report = sub.add_parser("report")
    report.add_argument("files", nargs="+")
    dup = sub.add_parser("duplicates")
    dup.add_argument("files", nargs="+")
    dup.add_argument("--over", type=float, default=20.0)
    rr = sub.add_parser("replay-report")
    rr.add_argument("file")
    rr.add_argument("--ids", default="q18,q21,q08")
    rr.add_argument("--temperature", default="", help="only rows of cold or warm")
    compare = sub.add_parser("compare")
    compare.add_argument("files", nargs="+")
    validity = sub.add_parser("validity")
    validity.add_argument("files", nargs="+")
    args = parser.parse_args()
    handlers = {
        "run": cmd_run,
        "replay": cmd_replay,
        "report": cmd_report,
        "validity": cmd_validity,
        "compare": cmd_compare,
        "duplicates": cmd_duplicates,
        "replay-report": cmd_replay_report,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
