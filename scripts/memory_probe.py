#!/usr/bin/env python3
"""CC-123 memory probe: where does the demo process's memory go?

    python scripts/memory_probe.py run --tree PATH --arm P|T --out OUT.jsonl
    python scripts/memory_probe.py leaf --tree PATH --path L1 --out OUT.jsonl
    python scripts/memory_probe.py validity --out OUT.jsonl
    python scripts/memory_probe.py report OUT.jsonl [OUT.jsonl ...]

Design: evidence/slice-6/memory-experiment-design.md. Nothing under api/src changes.
Windows only (private bytes and handle count come from kernel32 / psapi through ctypes;
psutil is not a dependency). `run` loads the TREE's own scripts/run_demo.py by path, so
the same probe measures any checkout. Per trial: sample, gc.collect(), sample again.
Arm T adds tracemalloc. No question text and no URL is written to the record.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import gc
import hashlib
import importlib.util
import json
import math
import os
import platform
import socket
import statistics
import subprocess
import sys
import threading
import time
import tomllib
import tracemalloc
import weakref
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WARMUP = 10
WINDOW = 20
MB = 1024 * 1024
GROWTH_MB = 5.0  # retained growth: lower CI bound of the slope above this, per trial
COUNT_GROWTH = 0.5  # handles / threads / live clients: per trial
HIGH_WATER_FACTOR = 1.15
REPRODUCED_BYTES = 2 * 1024 * MB
KILL_BYTES = 6 * 1024 * MB
# t critical, 95% two-sided, by degrees of freedom.
_T95 = ((5, 2.571), (10, 2.228), (20, 2.086), (30, 2.042), (40, 2.021), (60, 2.0), (120, 1.98))


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def process_memory() -> dict[str, int]:
    """Private bytes, working set, peak working set and handle count of this process."""
    kernel32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_Counters),
        wintypes.DWORD,
    ]
    kernel32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    handle = kernel32.GetCurrentProcess()
    counters = _Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        raise OSError("GetProcessMemoryInfo failed")
    handles = wintypes.DWORD()
    if not kernel32.GetProcessHandleCount(handle, ctypes.byref(handles)):
        raise OSError("GetProcessHandleCount failed")
    return {
        "private": int(counters.PrivateUsage),
        "working_set": int(counters.WorkingSetSize),
        "peak_working_set": int(counters.PeakWorkingSetSize),
        "handles": int(handles.value),
        "threads": threading.active_count(),
    }


# --- recording ---------------------------------------------------------------------------


class Recorder:
    """Append-only JSONL, one line per record, flushed so a kill loses nothing."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._handle.write(json.dumps(record) + "\n")
            self._handle.flush()


@dataclass
class Progress:
    trial: int = 0
    killed: bool = False


@dataclass
class Tracker:
    """Live-instance counts for the classes a per-request leak would multiply.

    Weak references, so counting costs nothing on a multi-GB heap and keeps nothing alive.
    """

    refs: dict[str, list[weakref.ReferenceType[Any]]] = field(default_factory=dict)
    created: dict[str, int] = field(default_factory=dict)

    def watch(self, name: str, cls: type) -> None:
        original = cls.__init__
        self.refs.setdefault(name, [])
        self.created.setdefault(name, 0)

        def init(instance: Any, *args: Any, **kwargs: Any) -> None:
            original(instance, *args, **kwargs)
            self.created[name] += 1
            with contextlib.suppress(TypeError):
                self.refs[name].append(weakref.ref(instance))

        cls.__init__ = init  # type: ignore[method-assign]

    def live(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for name, refs in self.refs.items():
            alive = [ref for ref in refs if ref() is not None]
            self.refs[name] = alive
            counts[name] = len(alive)
        return counts


def install_tracker(tracker: Tracker) -> list[str]:
    """Wrap __init__ of the client / loop / socket classes that exist in this environment."""
    watched: list[str] = []
    targets: list[tuple[str, str, str]] = [
        ("httpx.Client", "httpx", "Client"),
        ("httpx.AsyncClient", "httpx", "AsyncClient"),
        ("openai.OpenAI", "openai", "OpenAI"),
        ("openai.AsyncOpenAI", "openai", "AsyncOpenAI"),
        ("genai.Client", "google.genai", "Client"),
    ]
    for name, module_name, attr in targets:
        try:
            module = importlib.import_module(module_name)
            tracker.watch(name, getattr(module, attr))
            watched.append(name)
        except Exception:  # noqa: BLE001 - a missing SDK just means that class is not counted
            continue
    tracker.watch("asyncio.loop", asyncio.BaseEventLoop)
    tracker.watch("socket", socket.socket)
    return [*watched, "asyncio.loop", "socket"]


@dataclass
class Sampler:
    recorder: Recorder
    tracker: Tracker
    trace: bool

    def pair(self, index: int, **extra: Any) -> dict[str, Any]:
        pre = process_memory()
        gc.collect()
        post = process_memory()
        record: dict[str, Any] = {
            "kind": "trial",
            "i": index,
            "t": round(time.time(), 3),
            "pre": pre,
            "post": post,
            "live": self.tracker.live(),
            "created": dict(self.tracker.created),
            **extra,
        }
        if self.trace:
            record["traced_current"] = tracemalloc.get_traced_memory()[0]
        self.recorder.write(record)
        return record


def watchdog(recorder: Recorder, progress: Progress, limit: int) -> None:
    """Kill this process above `limit` private bytes. The kill is recorded, so it is data."""

    def watch() -> None:
        while True:
            time.sleep(5)
            used = process_memory()["private"]
            if used > limit:
                progress.killed = True
                recorder.write(
                    {
                        "kind": "footer",
                        "outcome": "killed",
                        "trial": progress.trial,
                        "private": used,
                    }
                )
                os._exit(3)

    threading.Thread(target=watch, daemon=True, name="memory-watchdog").start()


def git_commit(tree: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def header(tree: Path, **fields: Any) -> dict[str, Any]:
    lock = tree / "uv.lock"
    return {
        "kind": "header",
        "tree": str(tree),
        "commit": git_commit(tree),
        "uv_lock": hashlib.sha256(lock.read_bytes()).hexdigest()[:12] if lock.exists() else "",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pid": os.getpid(),
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        **fields,
    }


# --- statistics --------------------------------------------------------------------------


def t_critical(df: int) -> float:
    if df <= _T95[0][0]:
        return _T95[0][1]
    for (low, t_low), (high, t_high) in zip(_T95, _T95[1:], strict=False):
        if df <= high:
            return t_low + (t_high - t_low) * (df - low) / (high - low)
    return 1.96


def ols(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """(slope, ci_low, ci_high) with a 95% t interval on the slope."""
    n = len(xs)
    if n < 3:
        return 0.0, -math.inf, math.inf
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, -math.inf, math.inf
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sxx
    intercept = mean_y - slope * mean_x
    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    se = math.sqrt(residual / (n - 2) / sxx)
    margin = t_critical(n - 2) * se
    return slope, slope - margin, slope + margin


def slope_of(
    trials: list[dict[str, Any]], pick: Callable[[dict[str, Any]], float]
) -> tuple[float, float, float]:
    body = [t for t in trials if t["i"] > WARMUP]
    return ols([float(t["i"]) for t in body], [pick(t) for t in body])


def analyze(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the design's decision rules to one run's trial records."""
    trials = sorted(trials, key=lambda t: t["i"])
    if len(trials) < WARMUP + WINDOW:
        return {"n": len(trials), "verdict": "too few trials"}
    post_mb = [t["post"]["private"] / MB for t in trials]
    slope, low, high = slope_of(trials, lambda t: t["post"]["private"] / MB)
    first = statistics.median(post_mb[WARMUP : WARMUP + WINDOW])
    last_max = max(post_mb[-WINDOW:])
    peak_pre = max(t["pre"]["private"] for t in trials)
    retained = low > GROWTH_MB
    count_slopes: dict[str, tuple[float, float, float]] = {
        "handles": slope_of(trials, lambda t: float(t["post"]["handles"])),
        "threads": slope_of(trials, lambda t: float(t["post"]["threads"])),
    }
    for name in trials[-1].get("live", {}):
        count_slopes[name] = slope_of(trials, lambda t, n=name: float(t["live"].get(n, 0)))
    resource = sorted(name for name, (_, lo, _) in count_slopes.items() if lo > COUNT_GROWTH)
    plateau = high <= GROWTH_MB and last_max <= HIGH_WATER_FACTOR * first and not resource
    high_water = plateau and peak_pre / MB > 1.5 * first
    traced = None
    owner = "n/a"
    if "traced_current" in trials[-1]:
        traced = slope_of(trials, lambda t: t["traced_current"] / MB)[0]
        if retained and slope > 0:
            share = traced / slope
            owner = "python" if share >= 0.7 else "native" if share <= 0.3 else "mixed"
    elif retained:
        owner = "needs arm T"
    if retained:
        verdict = "retained growth"
    elif resource:
        verdict = "resource growth"
    elif high_water:
        verdict = "high-water, not growth"
    elif plateau:
        verdict = "plateau"
    else:
        verdict = "inconclusive"
    return {
        "n": len(trials),
        "slope_mb": round(slope, 3),
        "ci_mb": [round(low, 3), round(high, 3)],
        "traced_slope_mb": None if traced is None else round(traced, 3),
        "count_slopes": {k: round(v[0], 3) for k, v in count_slopes.items()},
        "resource_growth": resource,
        "peak_private_mb": round(peak_pre / MB, 1),
        "last_post_mb": round(post_mb[-1], 1),
        "reproduced": peak_pre > REPRODUCED_BYTES,
        "plateau": plateau,
        "verdict": verdict,
        "owner": owner,
    }


# --- W1: the demo workload ---------------------------------------------------------------


def load_demo(tree: Path) -> Any:
    """The tree's own run_demo, so its questions, order and _ask are what is measured."""
    spec = importlib.util.spec_from_file_location("tree_run_demo", tree / "scripts" / "run_demo.py")
    if spec is None or spec.loader is None:
        raise SystemExit(f"no scripts/run_demo.py under {tree}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["tree_run_demo"] = module
    spec.loader.exec_module(module)
    return module


def cmd_run(args: argparse.Namespace) -> int:
    tree = Path(args.tree).resolve()
    demo = load_demo(tree)
    for name in ("OPENAI_API_KEY", "CENSUS_API_KEY", "GEMINI_API_KEY"):
        if not os.environ.get(name):
            print(f"Missing {name} in the environment.", file=sys.stderr)
            return 2
    with (tree / "evals" / "golden_questions.toml").open("rb") as handle:
        entries = tomllib.load(handle)["question"]
    questions = demo.select_questions(entries)[: args.limit or None]

    from fastapi.testclient import TestClient
    from src.main import app

    recorder = Recorder(Path(args.out))
    tracker = Tracker()
    watched = install_tracker(tracker)
    progress = Progress()
    clock = demo.Clock()
    demo.install_clock(clock)
    client = TestClient(app)
    trace = args.arm == "T"
    recorder.write(
        header(tree, arm=args.arm, workload="W1", questions=len(questions), watched=watched)
    )
    watchdog(recorder, progress, KILL_BYTES)
    sampler = Sampler(recorder, tracker, trace)
    gc.collect()
    if trace:
        tracemalloc.start(1)
    snapshot = None
    for index, entry in enumerate(questions, start=1):
        progress.trial = index
        trial = demo._ask(client, clock, entry, 1)
        sampler.pair(
            index,
            id=trial.id,
            tier=trial.tier,
            latency_s=round(trial.latency_s, 3),
            answered=trial.answered,
        )
        if trace and index == WARMUP:
            snapshot = tracemalloc.take_snapshot()
    footer: dict[str, Any] = {"kind": "footer", "outcome": "complete", "trials": len(questions)}
    if trace and snapshot is not None:
        diff = tracemalloc.take_snapshot().compare_to(snapshot, "lineno")[:15]
        footer["top_growth"] = [
            {
                "where": f"{s.traceback[0].filename}:{s.traceback[0].lineno}",
                "kb": round(s.size_diff / 1024),
                "n": s.count_diff,
            }
            for s in diff
        ]
    recorder.write(footer)
    return 0


# --- leaf arms ---------------------------------------------------------------------------


def census_probe_url() -> str:
    return (
        "https://api.census.gov/data/2023/acs/acs5?get=NAME,B01001_001E,B01001_001M"
        f"&for=state:01&key={os.environ['CENSUS_API_KEY']}"
    )


def make_step(path: str, tree: Path) -> tuple[Callable[[], None], Callable[[], None]]:
    """(step, teardown) for one leaf arm. Imports resolve against the TREE's api/."""
    sys.path.insert(0, str(tree / "api"))
    if path == "L1":
        from openai import AsyncOpenAI

        async def build() -> None:
            AsyncOpenAI()

        return (lambda: asyncio.run(build())), (lambda: None)
    if path == "L2":
        from google import genai
        from openai import OpenAI

        def build_sync() -> None:
            OpenAI()
            genai.Client(api_key=os.environ["GEMINI_API_KEY"])

        return build_sync, (lambda: None)
    if path == "L3":
        import httpx

        url = census_probe_url()

        def fetch() -> None:
            httpx.get(url, timeout=60.0).json()

        return fetch, (lambda: None)
    if path == "L4":
        from src.retrieval import availability

        return (lambda: availability.load()), (lambda: None)
    if path == "L5":
        from src.retrieval import metadata

        return (lambda: metadata.variables("acs5", 2023)), (lambda: None)
    if path == "L5c":
        from src import figures

        return (lambda: figures._labels("acs5", 2023, {"B01001_001E", "B01001_001M"})), (
            lambda: None
        )
    if path in ("L6a", "L6b"):
        from fastapi.testclient import TestClient
        from src.main import app

        if path == "L6a":
            bare = TestClient(app)
            return (lambda: bare.get("/")), (lambda: None)
        managed = TestClient(app)
        managed.__enter__()
        return (lambda: managed.get("/")), (lambda: managed.__exit__(None, None, None))
    raise SystemExit(f"unknown leaf path {path}")


def cmd_leaf(args: argparse.Namespace) -> int:
    tree = Path(args.tree).resolve()
    demo = load_demo(tree)  # loads the tree's .env and puts its api/ first on sys.path
    del demo
    recorder = Recorder(Path(args.out))
    tracker = Tracker()
    watched = install_tracker(tracker)
    progress = Progress()
    recorder.write(
        header(tree, arm="leaf", workload=args.path, iterations=args.iterations, watched=watched)
    )
    watchdog(recorder, progress, KILL_BYTES)
    step, teardown = make_step(args.path, tree)
    sampler = Sampler(recorder, tracker, trace=False)
    every = 10
    for iteration in range(1, args.iterations + 1):
        progress.trial = iteration
        step()
        if iteration % every == 0:
            sampler.pair(iteration // every, iteration=iteration)
    teardown()
    recorder.write({"kind": "footer", "outcome": "complete", "iterations": args.iterations})
    return 0


# --- instrument validity -----------------------------------------------------------------


def _inject_python(held: list[Any], i: int) -> None:
    held.append(bytearray(b"\x01") * (20 * MB))


def _inject_native(held: list[Any], i: int) -> None:
    libc = ctypes.CDLL("msvcrt")
    libc.malloc.restype = ctypes.c_void_p
    libc.malloc.argtypes = [ctypes.c_size_t]
    libc.memset.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
    pointer = libc.malloc(20 * MB)
    libc.memset(pointer, 1, 20 * MB)
    held.append(pointer)


def _inject_sockets(held: list[Any], i: int) -> None:
    held.extend(socket.socket() for _ in range(20))


def _inject_none(held: list[Any], i: int) -> None:
    return None


def _inject_spike(held: list[Any], i: int) -> None:
    if i == 5:
        held.append(bytearray(b"\x01") * (500 * MB))
    if i == 8:
        held.clear()


VALIDITY = {
    "python-retained": (
        _inject_python,
        {"verdict": "retained growth", "owner": "python", "slope": 20.0},
    ),
    "native-retained": (
        _inject_native,
        {"verdict": "retained growth", "owner": "native", "slope": 20.0},
    ),
    "sockets-held": (_inject_sockets, {"verdict": "resource growth", "handles": 20.0}),
    "no-injection": (_inject_none, {"verdict": "plateau"}),
    "high-water": (_inject_spike, {"verdict": "high-water, not growth"}),
}


def run_case(name: str, trials: int, recorder: Recorder) -> tuple[bool, dict[str, Any]]:
    inject, expect = VALIDITY[name]
    tracker = Tracker()
    install_tracker(tracker)
    sampler = Sampler(recorder, tracker, trace=True)
    held: list[Any] = []
    recorder.write({"kind": "header", "arm": "validity", "case": name, "expect": expect})
    gc.collect()
    tracemalloc.start(1)
    records = []
    for i in range(1, trials + 1):
        work = {n: str(n) for n in range(50_000)}  # per-trial churn, freed each trial
        inject(held, i)
        records.append(sampler.pair(i, case=name))
        del work
    tracemalloc.stop()
    outcome = analyze(records)
    ok = outcome["verdict"] == expect["verdict"]
    if "owner" in expect:
        ok = ok and outcome["owner"] == expect["owner"]
    if "slope" in expect:
        ok = ok and abs(outcome["slope_mb"] - expect["slope"]) <= 0.2 * expect["slope"]
    if "handles" in expect:
        handles = outcome["count_slopes"]["handles"]
        ok = ok and abs(handles - expect["handles"]) <= 0.2 * expect["handles"]
    recorder.write({"kind": "footer", "case": name, "ok": ok, "analysis": outcome})
    return ok, outcome


def cmd_validity(args: argparse.Namespace) -> int:
    """One fresh process per case, so a leaked injection cannot become the next baseline."""
    if args.case:
        ok, outcome = run_case(args.case, args.trials, Recorder(Path(args.out)))
        print(f"{'PASS' if ok else 'FAIL'}  {args.case:<16} {json.dumps(outcome)}")
        return 0 if ok else 1
    failed = 0
    for name in VALIDITY:
        command = [sys.executable, __file__, "validity", "--case", name, "--out", args.out]
        command += ["--trials", str(args.trials)]
        failed += subprocess.run(command, check=False).returncode != 0
    return 1 if failed else 0


# --- report ------------------------------------------------------------------------------


def report_row(name: str, lines: list[dict[str, Any]]) -> str:
    head = next((r for r in lines if r["kind"] == "header"), {})
    foot = next((r for r in reversed(lines) if r["kind"] == "footer"), {})
    result = analyze([r for r in lines if r["kind"] == "trial"])
    tree = f"{Path(head.get('tree', '')).name} @ {head.get('commit', '')[:7]}"
    cells = [Path(name).name, tree, head.get("arm", ""), foot.get("outcome", "incomplete")]
    cells.append(str(result["n"]))
    if "slope_mb" not in result:
        return "| " + " | ".join([*cells, "", "", "", result["verdict"], "", ""]) + " |"
    low, high = result["ci_mb"]
    cells += [
        str(result["peak_private_mb"]),
        str(result["last_post_mb"]),
        f"{result['slope_mb']} ({low} to {high})",
        result["verdict"],
        result["owner"],
        ",".join(result["resource_growth"]) or "-",
    ]
    return "| " + " | ".join(cells) + " |"


def cmd_report(args: argparse.Namespace) -> int:
    columns = [
        "file",
        "tree",
        "arm",
        "outcome",
        "n",
        "peak private MB",
        "last post-GC MB",
        "slope MB/trial (95% CI)",
        "verdict",
        "owner",
        "resource",
    ]
    print("| " + " | ".join(columns) + " |")
    print("|" + " --- |" * len(columns))
    for name in args.files:
        lines = [json.loads(x) for x in Path(name).read_text(encoding="utf-8").splitlines() if x]
        print(report_row(name, lines))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--tree", required=True)
    run.add_argument("--arm", choices=["P", "T"], required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--limit", type=int, default=0, help="first N questions only (smoke test)")
    run.set_defaults(fn=cmd_run)
    leaf = sub.add_parser("leaf")
    leaf.add_argument("--tree", required=True)
    leaf.add_argument(
        "--path", required=True, choices=["L1", "L2", "L3", "L4", "L5", "L5c", "L6a", "L6b"]
    )
    leaf.add_argument("--out", required=True)
    leaf.add_argument("--iterations", type=int, default=300)
    leaf.set_defaults(fn=cmd_leaf)
    validity = sub.add_parser("validity")
    validity.add_argument("--out", required=True)
    validity.add_argument("--trials", type=int, default=62)
    validity.add_argument("--case", choices=list(VALIDITY), help="one case, in this process")
    validity.set_defaults(fn=cmd_validity)
    report = sub.add_parser("report")
    report.add_argument("files", nargs="+")
    report.set_defaults(fn=cmd_report)
    args = parser.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
