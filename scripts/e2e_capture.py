#!/usr/bin/env python3
"""Capture make eval + make demo into evidence/slice-<N>/.

Every child line is appended to the transcript (UTF-8 LF) as it arrives.
The same lines print to the CLI so warnings, errors, and scoreboards are
visible while the run is in progress. `--quiet` keeps the file complete and
prints only START/DONE plus warning/error/scoreboard lines.

    uv run python scripts/e2e_capture.py --slice 3 --ticket CC-71 --phase pre
    uv run python scripts/e2e_capture.py --slice 3 --ticket CC-71 --phase post --from demo

Needs OPENAI_API_KEY, GEMINI_API_KEY (rerank), CENSUS_API_KEY (demo).
On Windows+Dropbox, `npm ci` can EBUSY while deleting node_modules; the script
retries, then falls back to `npm install`. `--from` resumes without clobbering
a partial transcript.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
STEP_IDS = ("eval", "rerank", "synthetic", "npm", "build", "demo")
EBUSY = -4082
_ERR_MARKS = ("error", "fatal", "exception", "traceback")
_WARN_MARKS = ("warn", "deprecated", "ebusy", "not recommended")
_SCORE_MARKS = (
    "retrieval",
    "overall",
    "demo ",
    "synthetic",
    "answered_rate",
    "p95_latency",
    "misses",
    "floors not met",
    "served_build",
    "wrote evidence",
)


def _git(*args: str) -> str:
    hit = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return hit.stdout.strip()


def _npm() -> str:
    for name in ("npm.cmd", "npm.exe", "npm"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit("npm not found on PATH")


def _signed_exit(code: int) -> int:
    return code - (1 << 32) if code >= (1 << 31) else code


def _classify(line: str) -> str:
    lowered = line.lower()
    if any(mark in lowered for mark in _ERR_MARKS):
        return "error"
    if any(mark in lowered for mark in _WARN_MARKS):
        return "warning"
    return "ok"


def _echo(line: str, quiet: bool) -> bool:
    if not quiet:
        return True
    if _classify(line) != "ok":
        return True
    lowered = line.lower()
    return any(mark in lowered for mark in _SCORE_MARKS)


def _persist(log: Path, msg: str) -> None:
    print(msg, flush=True)
    with log.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# {msg}\n")


def _fail(label: str, code: int, log: Path, extra: str = "") -> None:
    signed = _signed_exit(code)
    shown = f"{code} ({signed})" if signed != code else str(code)
    _persist(log, f"FAIL {label} exit={shown}{extra}")
    sys.exit(code)


def _trace_start(line: str) -> bool:
    stripped = line.rstrip("\n")
    return stripped.startswith(
        ("Traceback (most recent call last):", "Task exception was never retrieved", "future:")
    )


def _trace_cont(line: str) -> bool:
    stripped = line.rstrip("\n")
    if stripped.startswith(("  File ", "    ", "raise ", "RuntimeError")):
        return True
    return "Event loop is closed" in stripped


def _run(argv: list[str], log: Path, heading: str, *, quiet: bool) -> tuple[int, int, int]:
    errors = warnings = 0
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    hidden = 0
    with log.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n===== {heading} =====\n")
        handle.flush()
        proc = subprocess.Popen(
            argv,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.replace("\r\n", "\n").replace("\r", "\n")
            if not line.endswith("\n"):
                line += "\n"
            handle.write(line)
            handle.flush()
            if hidden and (_trace_start(line) or _trace_cont(line)):
                hidden += 1
                continue
            if hidden:
                print(f"WARN omitted {hidden} traceback lines", flush=True)
                hidden = 0
            if _trace_start(line):
                hidden = 1
                errors += 1
                print(
                    "WARN asyncio shutdown traceback (full stack in transcript)",
                    flush=True,
                )
                continue
            kind = _classify(line)
            if kind == "error":
                errors += 1
            elif kind == "warning":
                warnings += 1
            if _echo(line, quiet):
                print(line, end="", flush=True)
        if hidden:
            print(f"WARN omitted {hidden} traceback lines", flush=True)
        code = proc.wait()
        handle.write(f"# summary: exit={_signed_exit(code)} errors={errors} warnings={warnings}\n")
    return code, errors, warnings


def _step(label: str, argv: list[str], log: Path, *, quiet: bool) -> None:
    _persist(log, f"START {label}")
    code, errors, warnings = _run(argv, log, label, quiet=quiet)
    _persist(log, f"DONE {label}  errors={errors}  warnings={warnings}")
    if code:
        _fail(label, code, log)


def _npm_ci(npm: str, web: str, log: Path, *, quiet: bool) -> None:
    argv_ci = [npm, "--prefix", web, "ci"]
    _persist(log, "START npm ci")
    delays = (2.0, 4.0, 8.0)
    last = 1
    errors = warnings = 0
    for i, delay in enumerate(delays, start=1):
        last, errors, warnings = _run(
            argv_ci, log, f"npm ci (attempt {i}/{len(delays)})", quiet=quiet
        )
        if last == 0:
            _persist(log, f"DONE npm ci  errors={errors}  warnings={warnings}")
            return
        if _signed_exit(last) != EBUSY:
            _fail("npm ci", last, log)
        _persist(log, f"RETRY npm ci EBUSY in {delay:.0f}s")
        time.sleep(delay)
    _persist(log, "START npm install (EBUSY fallback)")
    last, errors, warnings = _run(
        [npm, "--prefix", web, "install"],
        log,
        "npm install (EBUSY fallback)",
        quiet=quiet,
    )
    if last == 0:
        _persist(log, f"DONE npm install  errors={errors}  warnings={warnings}")
        return
    dist = Path(web) / "dist" / "index.html"
    hint = ""
    if dist.is_file():
        hint = "\nDropbox locked node_modules. web/dist is present; resume with --from demo"
    _fail("npm ci", last, log, extra=hint)


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Capture make eval + make demo into evidence/slice-<N>/"
    )
    parser.add_argument("--slice", type=int, required=True, help="slice number, e.g. 3")
    parser.add_argument("--ticket", required=True, help="Jira key, e.g. CC-70")
    parser.add_argument("--phase", choices=("pre", "post"), required=True)
    parser.add_argument(
        "--from",
        dest="start_from",
        choices=STEP_IDS,
        help="resume at this step; appends to an existing transcript",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="CLI: START/DONE plus warnings/errors/scoreboards; full output stays in the file",
    )
    args = parser.parse_args()

    ticket = args.ticket.strip().upper()
    if not ticket.startswith("CC-"):
        ticket = f"CC-{ticket.removeprefix('CC')}"
    py = sys.executable
    npm = _npm()
    out_dir = ROOT / "evidence" / f"slice-{args.slice}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{ticket.lower()}-e2e-{args.phase}.txt"

    head = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    when = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = (
        f"# E2E {args.phase} -- slice {args.slice} / {ticket}\n"
        f"# ticket: {ticket}\n"
        f"# branch: {branch}\n"
        f"# HEAD: {head}\n"
        f"# captured: {when}\n"
        f"# recipe: make eval then make demo --repeat 3\n"
        f"# command: uv run python scripts/e2e_capture.py "
        f"--slice {args.slice} --ticket {ticket} --phase {args.phase}\n\n"
    )
    if args.start_from and out.exists():
        with out.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"\n# resumed {when} --from {args.start_from}\n")
        print(f"resume {out} --from {args.start_from}", flush=True)
    else:
        if out.exists():
            print(f"overwriting {out} (pass --from to resume)", flush=True)
        out.write_bytes(header.encode("utf-8"))
        print(f"log {out}", flush=True)
    print("demo progress: evidence/demo-progress.txt", flush=True)

    scripts = ROOT / "scripts"
    web = str(ROOT / "web")
    quiet = args.quiet
    steps: list[tuple[str, str, list[str] | None]] = [
        (
            "eval",
            "eval_retrieval --verbose",
            [py, "-u", str(scripts / "eval_retrieval.py"), "--verbose"],
        ),
        (
            "rerank",
            "eval_retrieval --tier long_tail --rerank",
            [
                py,
                "-u",
                str(scripts / "eval_retrieval.py"),
                "--tier",
                "long_tail",
                "--rerank",
            ],
        ),
        (
            "synthetic",
            "score_synthetic",
            [py, "-u", str(scripts / "score_synthetic.py")],
        ),
        ("npm", "npm ci", None),
        ("build", "npm build", [npm, "--prefix", web, "run", "build"]),
        (
            "demo",
            "run_demo --repeat 3",
            [py, "-u", str(scripts / "run_demo.py"), "--repeat", "3"],
        ),
    ]
    skipping = args.start_from is not None
    try:
        for key, label, argv in steps:
            if skipping:
                if key != args.start_from:
                    continue
                skipping = False
            if key == "npm":
                _npm_ci(npm, web, out, quiet=quiet)
            else:
                assert argv is not None
                _step(label, argv, out, quiet=quiet)
    except KeyboardInterrupt:
        _persist(out, "interrupted")
        return 130
    print(f"WROTE {out}", flush=True)
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
