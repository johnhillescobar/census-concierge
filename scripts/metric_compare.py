#!/usr/bin/env python3
"""Metric comparison: pooled candidate runs against pooled main runs and the anchor L (CC-133,
rule from CC-143).

    python scripts/metric_compare.py freeze
    python scripts/metric_compare.py noise RUN [RUN ...] [--sizes 1x1,2x2] [--sims N]
    python scripts/metric_compare.py register NAME RUN [RUN ...] --head SHA --label TEXT [--legacy]
    python scripts/metric_compare.py compare RUN [RUN ...] [--base RUN ...] [--refs L]
                                             [--target long_tail=0.95] [--record]
    python scripts/metric_compare.py promote RUN [RUN ...]

A RUN is an evidence/latest.json-shaped file (`demo.trials`). It is read by this program and only
aggregates are printed; nobody reads the trials. Runs of one code are pooled and judged as one
sample: `compare P1 P2 --base B1 B2` judges the candidate against same-window runs of main, and
every comparison is also judged against L, the fixed anchor only the owner moves.

A row is one of two kinds. A `rate` row is noisy: unchanged code moves it from run to run, so it
fails only when the candidate is worse than the reference by more than its number in [rule] of
evals/metric_protocol.toml. A `hard` row names a failure that blocks whatever the rates did.
Statuses: PASS, EXCEPTED (a floor main already misses, under the owner's exception in
budgets.toml), INCONCLUSIVE, UNKNOWN (not measured) or FAIL. A row in parentheses is reported and
never blocks. Only a comparison with no blocking row above PASS exits 0. Nothing here has a
rerun-until-green path: a recorded compare is appended to the ledger, which is never rewritten.

A scorer, cohort or index change between a reference and a candidate is FAIL unless
evidence/metrics/bridges.json holds a bridge: {"ref", "from_scorer", "to_scorer", "from_cohorts",
"to_cohorts", "rescored_run", "note"} where rescored_run is the reference's own trials re-scored
by the new scorer on unchanged code. The candidate is then compared with that run, not the old one.
A change to [rule] alone needs none: a run records what it collected, not how it is judged.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import budget_log

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = ROOT / "evals" / "metric_protocol.toml"
METRICS = ROOT / "evidence" / "metrics"
EXPECTATION_FIELDS = ("text", "tier", "expect_table", "expect_geo_level", "expect_warning")
EXPECTATION_FLAGS = ("expect_no_url", "holdout")
CONTRACT_KEYS = ("has_moe", "has_geoid", "has_universe", "has_alternatives")
MAIN = "origin/main"  # L and a same-window base may only be a head that reached main
# what decides a run's behaviour besides the index: the app, the harness, the dependency pins
MEASURED = ("api/src", "scripts/run_demo.py", "pyproject.toml", "uv.lock")
PROVENANCE_KEYS = (
    "head",
    "scorer",
    "cohorts",
    "protocol",
    "dirty",
)  # what a run records about its scoring
# What a run collected, as opposed to how it is judged: (section, keys; None is the whole section).
COLLECTION = (
    ("sampling", ("repeat", "blocks", "stopping", "exclusions")),
    ("selection", None),
    ("scorer", None),
    ("cohorts", None),
)
RANK = {"PASS": 0, "EXCEPTED": 0, "INCONCLUSIVE": 1, "UNKNOWN": 2, "FAIL": 3}
EPS = 1e-9  # a difference exactly at its tolerance passes; float noise must not decide it
# Every rate row `compare` prints, with the [rule] number that judges it. "trial rate" is printed
# once per cohort; a cohort under sampling.min_families questions uses small_group_lost_questions.
RATE_ROWS = {
    "trial rate": "rate_drop_max",
    "empty answers (long_tail)": "empty_rise_max",
    "rows per question": "rows_lost_questions_max",
    "retrieval_at_10": "retrieval_drop_max",
    "selector_at_1": "selector_drop_max",
    "p95 vs reference": "p95_rise_max_seconds",
}
HARD_ROWS = (
    "candidate run file",
    "run identity",
    "provenance",
    "answered_rate floor",
    "retrieval_at_10 floor",
    "selector_at_1 floor",
    "answered_rate matches trials",
    "p95 matches trials",
    "p95 ceiling",
    "response contract",
    "run count",
    "same-window main",
    "reference",
    "reference file",
    "reference run file",
    "collection settings",
    "scorer / cohort hashes",
    "bridge",
    "repeat",
    "index",
    "planned trials",
    "lost questions",
    "reference label",
)
# A floor in budgets.toml the owner may except: its section, the [rule] number that says how far
# below the exception's baseline is still "not worse", and +1 when a higher value is the worse one.
EXCEPTABLE = {
    "answered_rate_min": ("quality", "rate_drop_max", -1),
    "retrieval_at_10_min": ("quality", "retrieval_drop_max", -1),
    "selector_at_1_min": ("quality", "selector_drop_max", -1),
    "p95_latency_seconds": ("performance", "p95_rise_max_seconds", 1),
}
Trials = dict[str, dict[str, list[tuple[bool, int]]]]  # cohort -> question -> (answered, rows)


class PlanError(ValueError):
    """The run does not contain exactly the planned trials."""


@dataclass
class Check:
    ref: str
    name: str
    status: str
    detail: str = ""
    kind: str = "hard"  # "rate": judged by a tolerance in [rule]; "hard": a named failure
    blocking: bool = True  # False: reported only (A, A0, a rule not adopted), never in the verdict
    worse: float | None = None  # a rate row: how much worse the candidate is, in the row's unit


@dataclass
class Run:
    path: str
    repeat: int
    index_hash: str
    p95_reported: float
    scalars: dict[str, float]
    trials: list[dict[str, Any]]
    hashes: dict[str, Any] = field(default_factory=dict)
    at: str = ""  # demo.generated_at: when the run was collected
    identity: str = ""  # of a run read from a file: a copy or a second name is the same run


@dataclass
class Sample:
    """Runs of one code pooled into the one sample the rule judges."""

    trials: Trials
    seconds: list[float]
    scalars: dict[str, float]  # the mean over the runs of each scalar every run reports


# --- hashes ------------------------------------------------------------------------------------


def _source(rel: str, head: str | None) -> str:
    if head:
        blob = subprocess.run(
            ["git", "show", f"{head}:{rel}"], cwd=ROOT, capture_output=True, check=True
        ).stdout.decode("utf-8")
    else:
        blob = (ROOT / rel).read_text(encoding="utf-8")
    return blob.replace("\r\n", "\n")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def load_protocol(head: str | None = None) -> dict[str, Any]:
    return tomllib.loads(_source(PROTOCOL.relative_to(ROOT).as_posix(), head))


def protocol_hash(head: str | None = None) -> str:
    return _digest(_source(PROTOCOL.relative_to(ROOT).as_posix(), head))


def collection_hash(protocol: dict[str, Any]) -> str:
    """Hash of the settings that decide what a run measured: trials per question, the block plan,
    exclusions, cohorts and scorer symbols. The numbers a run is judged by ([rule], the interval
    settings) are left out, so a stored run can be judged again under a changed rule."""
    picked = {
        section: protocol.get(section)
        if keys is None
        else {key: (protocol.get(section) or {}).get(key) for key in keys}
        for section, keys in COLLECTION
    }
    return _digest(picked)


def scorer_hash(protocol: dict[str, Any], head: str | None = None) -> str:
    """Hash of the scorer's syntax trees, so formatting and comments do not move it."""
    source = _source(protocol["scorer"]["source"], head)
    wanted = set(protocol["scorer"]["symbols"])
    found: dict[str, str] = {}
    for node in ast.parse(source).body:
        names = [node.name] if isinstance(node, ast.FunctionDef | ast.ClassDef) else []
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        names += [t.id for t in targets if isinstance(t, ast.Name)]  # Assign and AnnAssign
        for name in names:
            if name in wanted:
                found[name] = ast.dump(node, annotate_fields=False)
    return _digest({name: found.get(name, "<absent>") for name in sorted(wanted)})


def goldens(protocol: dict[str, Any], head: str | None = None) -> list[dict[str, Any]]:
    entries = tomllib.loads(_source("evals/golden_questions.toml", head))["question"]
    return [entry for entry in entries if isinstance(entry, dict)]


def expectation_digest(entry: dict[str, Any]) -> str:
    fields = {key: entry.get(key) for key in (*EXPECTATION_FIELDS, *EXPECTATION_FLAGS)}
    return _digest({"id": entry["id"], **fields})


def cohort(protocol: dict[str, Any], name: str, head: str | None = None) -> list[dict[str, Any]]:
    tier = protocol["cohorts"][name]["tier"]
    skipped = protocol["selection"]["exclude_flags"]
    return [
        entry
        for entry in goldens(protocol, head)
        if entry.get("tier") == tier and not any(entry.get(flag) for flag in skipped)
    ]


def cohort_hashes(protocol: dict[str, Any], head: str | None = None) -> dict[str, str]:
    return {
        name: _digest(sorted(expectation_digest(e) for e in cohort(protocol, name, head)))
        for name in protocol["cohorts"]
    }


def hashes(head: str | None = None) -> dict[str, Any]:
    """What a run records about its scoring (scripts/run_demo.py stamps exactly this)."""
    protocol = load_protocol()  # the current scorer symbols; scorer and goldens come from `head`
    return {
        "scorer": scorer_hash(protocol, head),
        "cohorts": cohort_hashes(protocol, head),
        "protocol": protocol_hash(),
    }


def collection_at(head: str | None = None) -> str:
    """The collection settings in force at `head`, or now. A run does not record them: they are
    read from the protocol its head carried, so runs stamped before the rule existed still count."""
    return collection_hash(load_protocol(head))


def judged_by(head: str | None = None) -> dict[str, Any]:
    """Everything a run or reference must share to be compared like for like."""
    return {**hashes(head), "collection": collection_at(head)}


# --- runs ----------------------------------------------------------------------------------------


def percentile(values: list[float], p: float) -> float:
    """Nearest rank, the same rule scripts/run_demo.py uses for demo.p95_latency_seconds."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(math.ceil(p / 100 * len(ordered)) - 1, len(ordered) - 1))]


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and set(value) <= set("0123456789abcdef")


def _git_status(*args: str) -> int:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode


def _same_code(head: str) -> bool:
    """The code a run measured is the code under judgment: api/src and the harness are identical
    at the run's head and at HEAD (evidence and docs may differ)."""
    return _git_status("diff", "--quiet", head, "HEAD", "--", *MEASURED) == 0


def _reachable(commit: str, tip: str) -> bool:
    return _git_status("merge-base", "--is-ancestor", commit, tip) == 0


def _pool(runs: Run | str | list[Any] | tuple[Any, ...]) -> list[Any]:
    """One run (or path) is a pool of one."""
    return [runs] if isinstance(runs, Run | str) else list(runs)


def load_run(path: str | Path) -> Run:
    """A run file as a Run. A file that is missing keys or malformed is a PlanError (a FAIL row),
    never a bare KeyError that leaves no record."""
    full = Path(path) if Path(path).is_absolute() else ROOT / path
    try:
        data = json.loads(full.read_text(encoding="utf-8"))
        demo = data["demo"]
        scalars = {k: float(data[k]) for k in ("retrieval_at_10", "selector_at_1") if k in data}
        scalars["answered_rate"] = float(demo["answered_rate"])
        stamp = demo.get("provenance")
        whole = (
            isinstance(stamp, dict)
            and all(k in stamp for k in PROVENANCE_KEYS)
            and _is_hash(stamp["head"])  # a SHA, never a ref or an option git would act on
        )
        trials = list(demo["trials"])
        for trial in trials:  # a trial the metrics cannot read is a bad file, not a traceback
            if "answered" not in trial or not math.isfinite(float(trial["latency_s"])):
                raise ValueError("a trial lacks `answered` or a finite latency_s")
        return Run(
            path=str(path),
            repeat=int(demo["repeat"]),
            index_hash=str(demo.get("index_hash") or ""),
            p95_reported=float(demo["p95_latency_seconds"]),
            scalars=scalars,
            trials=trials,
            hashes={k: stamp[k] for k in PROVENANCE_KEYS} if whole else {},
            at=str(demo.get("generated_at") or ""),
            identity=_digest([demo.get("generated_at"), trials]),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise PlanError(f"{path}: not a usable run file ({type(exc).__name__}: {exc})") from exc


def families(run: Run, ids: list[str], tier: str, repeat: int) -> dict[str, list[dict[str, Any]]]:
    """Every planned trial of a cohort, by question. A missing, extra or short question is a
    PlanError: dropped trials and a shrunken denominator can never produce a rate."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trial in run.trials:
        if trial.get("tier") == tier:
            grouped.setdefault(str(trial["id"]), []).append(trial)
    if set(grouped) != set(ids):
        missing, extra = sorted(set(ids) - set(grouped)), sorted(set(grouped) - set(ids))
        raise PlanError(
            f"{tier}: families differ from the frozen cohort (missing {missing}, extra {extra})"
        )
    for family, items in grouped.items():
        if sorted(int(t["repeat"]) for t in items) != list(range(1, repeat + 1)):
            raise PlanError(
                f"{tier}/{family}: expected repeats 1..{repeat}, got {len(items)} trials"
            )
    return grouped


def planned(run: Run, protocol: dict[str, Any]) -> None:
    """The run holds exactly the frozen (tier, id, repeat) trials: no missing, duplicate or extra
    one, in any tier. Extra fast trials would otherwise lower the full-run p95 unseen."""
    want = {
        (spec["tier"], entry["id"], n)
        for name, spec in protocol["cohorts"].items()
        for entry in cohort(protocol, name)
        for n in range(1, protocol["sampling"]["repeat"] + 1)
    }
    try:
        got = [(str(t["tier"]), str(t["id"]), int(t["repeat"])) for t in run.trials]
    except (KeyError, TypeError, ValueError) as exc:
        raise PlanError(f"a trial lacks tier, id or repeat ({type(exc).__name__})") from exc
    problems = {
        "missing": sorted(want - set(got)),
        "extra": sorted(set(got) - want),
        "duplicated": sorted({key for key in got if got.count(key) > 1}),
    }
    if any(problems.values()):
        counts = ", ".join(f"{len(v)} {k}" for k, v in problems.items() if v)
        raise PlanError(f"trials differ from the frozen plan ({counts}; first {_first(problems)})")


def _first(problems: dict[str, list[tuple[str, str, int]]]) -> str:
    return next(f"{k} {v[0]}" for k, v in problems.items() if v)


def sample(runs: list[Run], protocol: dict[str, Any]) -> Sample:
    """Every planned trial of every run, pooled by question (PlanError as in `families`)."""
    repeat = protocol["sampling"]["repeat"]
    trials: Trials = {}
    for name, spec in protocol["cohorts"].items():
        ids = [entry["id"] for entry in cohort(protocol, name)]
        pooled: dict[str, list[tuple[bool, int]]] = {family: [] for family in ids}
        for run in runs:
            for family, items in families(run, ids, spec["tier"], repeat).items():
                pooled[family] += [(bool(t["answered"]), int(t.get("rows") or 0)) for t in items]
        trials[name] = pooled
    shared = set.intersection(*(set(run.scalars) for run in runs))
    return Sample(
        trials=trials,
        seconds=[float(t["latency_s"]) for run in runs for t in run.trials],
        scalars={k: sum(run.scalars[k] for run in runs) / len(runs) for k in sorted(shared)},
    )


# --- the rule ------------------------------------------------------------------------------------


def _answered(trial: tuple[bool, int]) -> bool:
    return trial[0]


def _empty(trial: tuple[bool, int]) -> bool:
    return trial[1] == 0


def _rate(group: dict[str, list[tuple[bool, int]]], hit: Any = _answered) -> float:
    """The mean over questions of the share of a question's trials that `hit`: every question
    weighs the same however many runs were pooled."""
    if not group:
        return 0.0
    return sum(sum(map(hit, trials)) / len(trials) for trials in group.values()) / len(group)


def _rows_when_answered(trials: list[tuple[bool, int]]) -> float | None:
    got = [rows for answered, rows in trials if answered]
    return sum(got) / len(got) if got else None


def lost_questions(cand: Sample, base: Sample) -> list[str]:
    """Questions answered in every reference trial and in no candidate trial, in any cohort."""
    return sorted(
        family
        for cohort_name, mine in cand.trials.items()
        for family, trials in mine.items()
        if all(map(_answered, base.trials[cohort_name][family])) and not any(map(_answered, trials))
    )


def judge_rows(cand: Sample, base: Sample, name: str, protocol: dict[str, Any]) -> list[Check]:
    """The rule: each noisy rate against its tolerance in [rule], then the questions lost outright.
    Closed form on purpose, so `noise` can run it thousands of times."""
    rule, minimum = protocol["rule"], protocol["sampling"]["min_families"]
    out: list[Check] = []

    def rate_row(row: str, worse: float, limit: float, detail: str) -> None:
        # written so that a tolerance that is not a number (nan) fails instead of passing
        status = "PASS" if worse <= limit + EPS else "FAIL"
        out.append(Check(name, row, status, detail, kind="rate", worse=round(worse, 6)))

    for cohort_name, mine in cand.trials.items():
        theirs = base.trials[cohort_name]
        if not mine:  # nothing was asked, so nothing was measured
            row = f"{cohort_name} trial rate"
            out.append(Check(name, row, "UNKNOWN", "the cohort has no questions", kind="rate"))
            continue
        small = len(mine) < minimum  # too few questions for a rate tolerance to mean anything
        limit = rule["small_group_lost_questions"] / len(mine) if small else rule["rate_drop_max"]
        note = (
            f" ({rule['small_group_lost_questions']:g} of its {len(mine)} questions)"
            if small
            else ""
        )
        got, was = _rate(mine), _rate(theirs)
        rate_row(
            f"{cohort_name} trial rate",
            was - got,
            limit,
            f"{got:.3f} vs {was:.3f}, may fall {limit:.3f}{note}",
        )
    got, was = _rate(cand.trials["long_tail"], _empty), _rate(base.trials["long_tail"], _empty)
    rate_row(
        "empty answers (long_tail)",
        got - was,
        rule["empty_rise_max"],
        f"{got:.3f} vs {was:.3f}, may rise {rule['empty_rise_max']:.3f}",
    )
    fewer = sorted(
        family
        for cohort_name, mine in cand.trials.items()
        for family, trials in mine.items()
        if (now := _rows_when_answered(trials)) is not None
        and (then := _rows_when_answered(base.trials[cohort_name][family])) is not None
        and now < then
    )
    rate_row(
        "rows per question",
        len(fewer),
        rule["rows_lost_questions_max"],
        f"{len(fewer)} questions returned fewer rows when answered"
        f"{' (' + ', '.join(fewer[:8]) + ')' if fewer else ''}, "
        f"limit {rule['rows_lost_questions_max']:g}",
    )
    for key in ("retrieval_at_10", "selector_at_1"):
        limit = rule[RATE_ROWS[key]]
        if key in cand.scalars and key not in base.scalars:
            unknown = Check(name, key, "UNKNOWN", "the reference does not report it", kind="rate")
            out.append(unknown)
        elif key in cand.scalars:
            got, was = cand.scalars[key], base.scalars[key]
            rate_row(key, was - got, limit, f"{got:.3f} vs {was:.3f}, may fall {limit:.3f}")
    c95, r95 = percentile(cand.seconds, 95), percentile(base.seconds, 95)
    answers_held = all(c.status == "PASS" for c in out if c.name.endswith("trial rate"))
    credited = "" if c95 >= r95 or answers_held else "; gain not credited, answers fell"
    limit = rule["p95_rise_max_seconds"]
    rate_row(
        "p95 vs reference",
        c95 - r95,
        limit,
        f"{c95:.3f}s vs {r95:.3f}s, may rise {limit:g}s{credited}",
    )
    lost = lost_questions(cand, base)
    out.append(
        Check(
            name,
            "lost questions",
            "FAIL" if lost else "PASS",
            f"{len(lost)} answered in every reference trial and in no candidate trial"
            f"{': ' + ', '.join(lost) if lost else ''}",
            blocking=bool(rule["lost_questions_block"]),
        )
    )
    return out


def paired_interval(diffs: list[Fraction], protocol: dict[str, Any]) -> tuple[float, float]:
    """(point, lower bound) of the mean paired per-question difference. Questions are resampled,
    never trials: repeats of one question are one observation. Fractions, so a bound of exactly
    zero is zero and cannot pass as a gain by float error."""
    sampling = protocol["sampling"]
    n = len(diffs)
    rng = random.Random(sampling["seed"])
    totals = sorted(
        sum(diffs[rng.randrange(n)] for _ in range(n)) for _ in range(sampling["resamples"])
    )
    tail = (1 - sampling["confidence"]) / 2
    return float(sum(diffs) / n), float(totals[int(tail * len(totals))] / n)


# --- comparison ----------------------------------------------------------------------------------


def _budgets_text() -> str:
    return (ROOT / "budgets.toml").read_text(encoding="utf-8")


def _budgets() -> dict[str, Any]:
    return tomllib.loads(_budgets_text())


def _number(value: object) -> bool:
    """A finite number. A bool is not one, and nan or inf is not a limit or a baseline."""
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _exceptions(budgets: dict[str, Any]) -> list[Any]:
    entries = budgets.get("exception") or []
    return entries if isinstance(entries, list) else [entries]  # `[exception]` is one table


def exception_problems(budgets: dict[str, Any]) -> list[str]:
    """What is wrong with the [[exception]] entries: each needs a known metric, a numeric baseline,
    the owner's approval and the ticket that restores the floor."""
    out: list[str] = []
    for entry in _exceptions(budgets):
        metric = entry.get("metric") if isinstance(entry, dict) else None
        if metric not in EXCEPTABLE:
            out.append(f"exception for {metric!r}: not a floor that can be excepted")
        elif not _number(entry.get("baseline")) or not all(
            isinstance(entry.get(k), str) and entry[k].strip() for k in ("approved", "ticket")
        ):
            out.append(f"exception for {metric}: needs baseline, approved and ticket")
    return out


def excepted(limit: str, value: float, budgets: dict[str, Any], rule: dict[str, Any]) -> str:
    """Why a missed floor does not block, or "". The owner's [[exception]] for it holds while the
    value is no worse than the exception's baseline by the ratified rule; a malformed entry and a
    value that fell further excuse nothing."""
    if exception_problems(budgets):
        return ""
    _section, tolerance, sign = EXCEPTABLE[limit]
    for entry in _exceptions(budgets):
        if entry["metric"] == limit and sign * (value - entry["baseline"]) <= rule[tolerance] + EPS:
            return (
                f"exception: baseline {entry['baseline']:g}, {entry['ticket']} restores it, "
                f"approved {entry['approved']}"
            )
    return ""


def absolute(cands: Run | list[Run], protocol: dict[str, Any]) -> list[Check]:
    """The candidate against the floors in budgets.toml, and against its own trials."""
    cands = _pool(cands)
    budgets = _budgets()
    quality, ceiling = budgets["quality"], budgets["performance"]["p95_latency_seconds"]
    out: list[Check] = []

    def limit_row(
        row: str, limit: str, value: float | None, ok: bool, shown: str, waiver: str = ""
    ) -> None:
        note = "" if ok or value is None else excepted(limit, value, budgets, protocol["rule"])
        note = note or (f"waived by the owner for this run: {waiver}" if waiver else "")
        status = "PASS" if ok else "EXCEPTED" if note else "FAIL"
        out.append(Check("floor", row, status, f"{shown}; {note}" if note else shown))

    for key in ("answered_rate", "retrieval_at_10", "selector_at_1"):
        floor = quality[f"{key}_min"]
        values = [run.scalars.get(key) for run in cands]
        value = None if None in values else sum(values) / len(values)  # type: ignore[arg-type]
        ok = value is not None and value >= floor
        shown = f"{value if value is None else round(value, 3)} vs floor {floor}"
        limit_row(f"{key} floor", f"{key}_min", value, ok, shown)
    rates, clocks = [], []
    for run in cands:  # what each run reports must be its own trials'
        long_tail = [t for t in run.trials if t.get("tier") == "long_tail"]
        if long_tail:
            rate = sum(bool(t["answered"]) for t in long_tail) / len(long_tail)
            rates.append((abs(rate - run.scalars["answered_rate"]) <= 0.001, rate, run))
        p95 = percentile([float(t["latency_s"]) for t in run.trials], 95)
        clocks.append((abs(p95 - run.p95_reported) <= 0.01, p95, run))
    if rates:
        detail = "; ".join(
            f"{rate:.3f} from trials vs reported {run.scalars['answered_rate']:.3f}"
            for _agrees, rate, run in rates
        )
        status = "PASS" if all(agrees for agrees, _found, _run in rates) else "FAIL"
        out.append(Check("floor", "answered_rate matches trials", status, detail))
    detail = "; ".join(
        f"{p95:.3f} vs reported {run.p95_reported:.3f}" for _agrees, p95, run in clocks
    )
    status = "PASS" if all(agrees for agrees, _found, _run in clocks) else "FAIL"
    out.append(Check("floor", "p95 matches trials", status, detail))
    pooled = percentile([float(t["latency_s"]) for run in cands for t in run.trials], 95)
    shown = f"{pooled:.3f}s vs {ceiling:g}s"
    # the owner's `[waiver]` names one run and its p95, so it covers a pool of that one run only
    one = cands[0] if len(cands) == 1 and pooled > ceiling else None
    waiver = budget_log.p95_waiver(_budgets_text(), one.at, pooled) if one else ""
    limit_row("p95 ceiling", "p95_latency_seconds", pooled, pooled <= ceiling, shown, waiver)
    # any tier, answered or not: data is data
    returned = [t for run in cands for t in run.trials if t.get("rows")]
    if returned and not all(k in t for t in returned for k in CONTRACT_KEYS):
        out.append(
            Check("floor", "response contract", "UNKNOWN", "trial records carry no contract fields")
        )
    elif returned:
        bad = sum(not all(t[k] for k in CONTRACT_KEYS) for t in returned)
        out.append(
            Check(
                "floor",
                "response contract",
                "PASS" if not bad else "FAIL",
                f"{bad} of {len(returned)} trials that returned rows lack a contract field",
            )
        )
    return out


def evaluate(
    cands: Run | list[Run],
    refs: Run | list[Run],
    name: str,
    protocol: dict[str, Any],
    *,
    label: str = "",
) -> list[Check]:
    """Pooled candidate runs against pooled reference runs, under the rule."""
    cands, refs = _pool(cands), _pool(refs)
    repeat = protocol["sampling"]["repeat"]
    if any(run.repeat != repeat for run in (*cands, *refs)):
        found = f"cand {[r.repeat for r in cands]}, ref {[r.repeat for r in refs]}"
        return [Check(name, "repeat", "FAIL", f"{found}, frozen {repeat}")]
    indexes = {run.index_hash for run in (*cands, *refs)}
    if len(indexes) != 1 or "" in indexes:
        return [Check(name, "index", "FAIL", "missing or different index; not like for like")]
    try:
        for run in (*cands, *refs):
            planned(run, protocol)
        mine, theirs = sample(cands, protocol), sample(refs, protocol)
    except PlanError as exc:
        return [Check(name, "planned trials", "FAIL", str(exc))]
    out = judge_rows(mine, theirs, name, protocol)
    if label:
        out.append(Check(name, "reference label", "PASS", label))
    return out


def target_check(
    cands: Run | list[Run],
    bases: Run | list[Run],
    protocol: dict[str, Any],
    cohort_name: str,
    target: float,
) -> list[Check]:
    """A story's owned cohort: both rates at the target; if the base was below it, a paired gain."""
    try:
        mine = sample(_pool(cands), protocol).trials[cohort_name]
        theirs = sample(_pool(bases), protocol).trials[cohort_name]
    except PlanError as exc:
        return [Check("target", cohort_name, "FAIL", str(exc))]
    out: list[Check] = []

    def trial(trials: list[tuple[bool, int]]) -> Fraction:
        return Fraction(sum(map(_answered, trials)), len(trials))

    def case(trials: list[tuple[bool, int]]) -> Fraction:
        return Fraction(all(map(_answered, trials)))

    for metric, hit in (("trial", trial), ("case", case)):
        rate = float(sum(hit(trials) for trials in mine.values()) / len(mine))
        was = float(sum(hit(trials) for trials in theirs.values()) / len(theirs))
        if len(mine) < protocol["sampling"]["min_families"]:
            out.append(
                Check("target", f"{cohort_name} {metric}", "INCONCLUSIVE", f"{len(mine)} families")
            )
        elif rate < target:
            out.append(Check("target", f"{cohort_name} {metric}", "FAIL", f"{rate:.3f} < {target}"))
        elif was >= target:
            out.append(
                Check(
                    "target",
                    f"{cohort_name} {metric}",
                    "PASS",
                    f"{rate:.3f} preserved ({was:.3f}); no gain claimed",
                )
            )
        else:
            diffs = [hit(mine[family]) - hit(theirs[family]) for family in sorted(mine)]
            _point, lower = paired_interval(diffs, protocol)
            ok = lower > 0
            out.append(
                Check(
                    "target",
                    f"{cohort_name} {metric}",
                    "PASS" if ok else "INCONCLUSIVE",
                    f"{rate:.3f} from {was:.3f}, gain lower bound {lower:+.3f}",
                )
            )
    return out


def load_refs() -> dict[str, Any]:
    path = METRICS / "references.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def entry_runs(entry: dict[str, Any], key: str = "run") -> list[dict[str, str]]:
    """The run files behind a reference (`run`) or a bridge (`rescored`): a pool, or the one file an
    older entry names."""
    several = entry.get(f"{key}s") if key == "run" else entry.get("rescored_runs")
    if several:
        return list(several)
    if key == "run":
        return [{"run": entry["run"], "run_sha256": entry["run_sha256"]}]
    return [{"run": entry["rescored_run"], "run_sha256": entry.get("rescored_sha256", "")}]


def _pinned(files: list[dict[str, str]]) -> bool:
    return all(
        (ROOT / item["run"]).is_file()
        and hashlib.sha256((ROOT / item["run"]).read_bytes()).hexdigest() == item.get("run_sha256")
        for item in files
    )


def _bridge(ref: str, old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any] | None:
    path = METRICS / "bridges.json"
    if not path.is_file():
        return None
    for bridge in json.loads(path.read_text(encoding="utf-8")):
        if (
            bridge.get("ref") == ref
            and bridge.get("from_scorer") == old["scorer"]
            and bridge.get("to_scorer") == new["scorer"]
            and bridge.get("from_cohorts") == old["cohorts"]
            and bridge.get("to_cohorts") == new["cohorts"]
        ):
            return bridge
    return None


def provenance_checks(
    cands: Run | list[Run], now: dict[str, Any]
) -> tuple[dict[str, Any], list[Check]]:
    """(the hashes the candidate is judged by, problems with them). They are the ones in force at
    the head the runs recorded, never the ones checked out now. A run that records none predates
    this and is UNKNOWN: it can be read but not credited or promoted. The rule is not among them:
    a run whose collection settings are unchanged is judged under whatever rule is ratified now."""
    cands = _pool(cands)
    if not all(run.hashes for run in cands):
        gap = "the run records no head or hashes; it cannot be credited or promoted"
        return now, [Check("run", "provenance", "UNKNOWN", gap)]
    problems: list[Check] = []

    def fail(why: str) -> None:
        problems.append(Check("run", "provenance", "FAIL", why))

    first = cands[0].hashes
    head = str(first["head"])
    judged = {"scorer": first["scorer"], "cohorts": first["cohorts"]}
    if any(str(run.hashes["head"]) != head for run in cands):
        fail("the pooled runs measured different heads")
    # uncommitted code was measured under a clean head's name
    if any(run.hashes["dirty"] is not False for run in cands):
        fail("measured uncommitted changes")
    try:
        actual = judged_by(head)
    except (subprocess.CalledProcessError, OSError, ValueError, SyntaxError, KeyError) as exc:
        fail(f"head cannot be checked ({exc})")
        return {**judged, "collection": now["collection"]}, problems
    if any(run.hashes[k] != actual[k] for run in cands for k in ("scorer", "cohorts")):
        fail("recorded hashes are not those of its head")
    elif actual["collection"] != now["collection"]:
        fail("collected under other settings (trials per question, cohorts, scorer, exclusions)")
    elif not _same_code(head):
        fail("api/src or the harness changed since its head")
    return {**judged, "collection": actual["collection"]}, problems


def _built_on(base_head: str, cand_head: str) -> bool:
    """The main the candidate is built on (its merge base with MAIN) carries the product code,
    harness and pins the base runs measured. An older run of main, from before a change the
    candidate already contains, is not its baseline."""
    fork = subprocess.run(
        ["git", "merge-base", cand_head, MAIN], cwd=ROOT, capture_output=True, text=True
    )
    if fork.returncode or not fork.stdout.strip():
        return False
    return _git_status("diff", "--quiet", base_head, fork.stdout.strip(), "--", *MEASURED) == 0


def spread_hours(runs: list[Run]) -> float | None:
    """Hours between the earliest and the latest of the runs, or None if one does not say when it
    was collected."""
    try:
        times = [datetime.fromisoformat(run.at) for run in runs]
        return (max(times) - min(times)).total_seconds() / 3600
    except (ValueError, TypeError):  # absent, malformed, or one zoned and one not
        return None


def duplicated(runs: list[Run]) -> bool:
    """One run under two names, or a copy of it, is one measurement, not two."""
    return len({run.identity for run in runs}) != len(runs)


def blocks(protocol: dict[str, Any]) -> tuple[int, int]:
    """(candidate runs, main runs) one pre-merge judgment pools: the P and B of sampling.blocks."""
    plan = [block.strip() for block in str(protocol["sampling"]["blocks"]).split(",")]
    return plan.count("P"), plan.count("B")


Judged = tuple[list[Check], list[Run] | None]  # the rows, and the reference runs if judged


def against_main(
    cands: list[Run], base_paths: list[str], judged: dict[str, Any], protocol: dict[str, Any]
) -> Judged:
    """Reference B: the pooled same-window runs of main passed with `--base`."""

    def refuse(row: str, why: str) -> Judged:
        return [Check("B", row, "FAIL", why)], None

    want = blocks(protocol)
    if (len(cands), len(base_paths)) != want:
        found = f"{len(cands)} candidate and {len(base_paths)} main runs"
        plan = f"sampling.blocks plans {want[0]} and {want[1]}"
        return refuse("run count", f"{found}; {plan}: none dropped, none added")
    try:
        bases = [load_run(path) for path in base_paths]
    except PlanError as exc:
        return refuse("reference run file", str(exc))
    if duplicated([*cands, *bases]):
        why = "a run is given more than once; every planned block is its own run"
        return refuse("run identity", why)
    heads = {str(run.hashes.get("head", "")) for run in bases}
    head = next(iter(heads))
    clean = all(run.hashes.get("dirty") is False for run in bases)
    if len(heads) != 1 or not head or not clean or not _reachable(head, MAIN):
        return refuse("same-window main", f"the base runs must record one clean head on {MAIN}")
    mine = str(cands[0].hashes.get("head", ""))
    if not mine or not _built_on(head, mine):
        why = f"the base runs measured {head[:7]}, whose product code is not the main the candidate"
        return refuse("same-window main", f"{why} is built on; run main again in this window")
    hours, window = spread_hours([*cands, *bases]), protocol["rule"]["window_hours"]
    if hours is None or not hours <= window + EPS:
        found = "a run does not say when it was collected" if hours is None else f"{hours:.1f}h"
        why = f"the runs must be collected within {window:g}h of each other ({found})"
        return refuse("same-window main", why)
    try:
        theirs = judged_by(head)
    except (subprocess.CalledProcessError, OSError, ValueError, SyntaxError, KeyError) as exc:
        return refuse("same-window main", f"head cannot be checked ({exc})")
    recorded = all(run.hashes[k] == theirs[k] for run in bases for k in ("scorer", "cohorts"))
    if not recorded or any(theirs[k] != judged[k] for k in ("scorer", "cohorts", "collection")):
        why = "main was scored or collected differently; rebase the candidate onto it and rerun"
        return refuse("scorer / cohort hashes", why)
    label = f"{len(bases)} pooled same-window runs of main {head[:7]}"
    return evaluate(cands, bases, "B", protocol, label=label), bases


def against_reference(
    cands: list[Run], name: str, entry: dict[str, Any], judged: dict[str, Any], protocol: Any
) -> Judged:
    """A registered reference (L, or the report-only anchors), bridged if its scorer changed."""

    def refuse(row: str, why: str) -> Judged:
        return [Check(name, row, "FAIL", why)], None

    files, label = entry_runs(entry), entry["label"]
    if not _pinned(files):
        return refuse("reference file", "run file changed since registration")
    old = entry["hashes"]
    if old["protocol"] != "legacy" and old.get("collection") != judged["collection"]:
        return refuse("collection settings", "the collection settings changed since the reference")
    if old["scorer"] != judged["scorer"] or old["cohorts"] != judged["cohorts"]:
        bridge = _bridge(name, old, judged)
        if bridge is None:
            why = "changed since the reference, no bridge; any gain is the instrument's"
            return refuse("scorer / cohort hashes", why)
        files = entry_runs(bridge, "rescored")
        if not _pinned(files):
            return refuse("bridge", "rescored run missing or not pinned")
        label = f"{label}; bridged: {bridge['note']}"
    try:
        reference = [load_run(item["run"]) for item in files]
    except PlanError as exc:
        return refuse("reference run file", str(exc))
    return evaluate(cands, reference, name, protocol, label=label), reference


def anchored(ref_names: list[str]) -> list[str]:
    """The references a comparison is judged against: L always, whatever else is named. The fixed
    anchor cannot be left out of a verdict by naming another reference."""
    return ["L", *(name for name in ref_names if name != "L")]


def compare(
    cand_paths: str | list[str],
    ref_names: list[str],
    targets: dict[str, float],
    base_paths: list[str] | None = None,
) -> list[Check]:
    protocol = load_protocol()
    now = judged_by()
    try:
        cands = [load_run(path) for path in _pool(cand_paths)]
        for run in cands:
            planned(run, protocol)
    except PlanError as exc:
        return [Check("run", "candidate run file", "FAIL", str(exc))]
    refs = load_refs()
    out = absolute(cands, protocol)
    if duplicated(cands):
        why = "a run is given more than once; a pool is independent runs"
        out.append(Check("run", "run identity", "FAIL", why))
    judged, found = provenance_checks(cands, now)
    out += found
    # B is the name of the same-window base; a registered reference cannot take it over
    named = [n for n in anchored(ref_names) if not (n == "B" and base_paths)]
    for name in (["B"] if base_paths else []) + named:
        if name == "B" and base_paths:
            rows, reference = against_main(cands, base_paths, judged, protocol)
        elif name not in refs:
            rows, reference = [Check(name, "reference", "UNKNOWN", "not registered")], None
        else:
            rows, reference = against_reference(cands, name, refs[name], judged, protocol)
        for cohort_name, goal in targets.items() if reference else ():
            rows += target_check(cands, reference, protocol, cohort_name, goal)
        for row in rows:  # an anchor from before the rule is shown, and decides nothing
            row.blocking = row.blocking and name not in protocol["rule"]["report_only"]
        out += rows
    return out


def verdict(checks: list[Check]) -> str:
    """The worst blocking status; PASS when none is worse than an owner's exception."""
    worst = max((c.status for c in checks if c.blocking), key=RANK.__getitem__, default="UNKNOWN")
    return "PASS" if RANK[worst] == 0 else worst


# --- noise: how often unchanged code fails, and what the rule can catch -----------------------


def wilson(hits: int, n: int) -> tuple[float, float]:
    """The 95% Wilson interval of a proportion; (0, 1) when nothing was observed."""
    if not n:
        return 0.0, 1.0
    z = 1.959964
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass
class Stored:
    """One code's stored runs, pooled by question, to draw simulated runs from."""

    trials: dict[str, dict[str, list[tuple[bool, int, float]]]]  # + the trial's seconds
    scalars: list[dict[str, float]]  # one per stored run: these move run by run, not by trial


def stored(runs: list[Run], protocol: dict[str, Any]) -> Stored:
    repeat = protocol["sampling"]["repeat"]
    trials: dict[str, dict[str, list[tuple[bool, int, float]]]] = {}
    for name, spec in protocol["cohorts"].items():
        ids = [entry["id"] for entry in cohort(protocol, name)]
        pooled: dict[str, list[tuple[bool, int, float]]] = {family: [] for family in ids}
        for run in runs:
            for family, items in families(run, ids, spec["tier"], repeat).items():
                pooled[family] += [
                    (bool(t["answered"]), int(t.get("rows") or 0), float(t["latency_s"]))
                    for t in items
                ]
        trials[name] = pooled
    return Stored(trials=trials, scalars=[dict(run.scalars) for run in runs])


def draw(
    src: Stored, runs: int, repeat: int, rng: random.Random, broken: frozenset[str] = frozenset()
) -> Sample:
    """`runs` simulated runs of the stored code, pooled: each trial is drawn from the stored
    trials of its own question, and each run's scalars from one stored run. A `broken` question
    is never answered; its rows are kept, because most misses are a wrong table, not an empty
    reply, and the rate row has to catch it alone."""
    trials: Trials = {}
    seconds: list[float] = []
    for name, group in src.trials.items():
        pooled: dict[str, list[tuple[bool, int]]] = {}
        for family, pool in group.items():
            picks = [pool[rng.randrange(len(pool))] for _ in range(runs * repeat)]
            seconds += [pick[2] for pick in picks]
            dead = family in broken
            pooled[family] = [(not dead and pick[0], pick[1]) for pick in picks]
        trials[name] = pooled
    picked = [src.scalars[rng.randrange(len(src.scalars))] for _ in range(runs)]
    shared = set.intersection(*(set(scalars) for scalars in picked))
    return Sample(
        trials=trials,
        seconds=seconds,
        scalars={k: sum(scalars[k] for scalars in picked) / runs for k in sorted(shared)},
    )


def simulate(
    src: Stored,
    size: tuple[int, int],
    protocol: dict[str, Any],
    rng: random.Random,
    sims: int,
    broken: int = 0,
) -> tuple[int, Counter[str], dict[str, list[float]]]:
    """(comparisons the rule fails, failures by row, each rate row's worsening) over `sims` pairs of
    independent draws of one code at `size` (candidate runs, reference runs). With `broken`, that
    many long_tail questions that usually answer are made to fail in the candidate."""
    repeat = protocol["sampling"]["repeat"]
    working = sorted(
        family
        for family, pool in src.trials["long_tail"].items()
        if 2 * sum(trial[0] for trial in pool) >= len(pool)
    )
    fails = 0
    rows: Counter[str] = Counter()
    worse: dict[str, list[float]] = {}
    for _ in range(sims):
        dead = frozenset(rng.sample(working, min(broken, len(working))))
        cand = draw(src, size[0], repeat, rng, dead)
        base = draw(src, size[1], repeat, rng)
        checks = judge_rows(cand, base, "sim", protocol)
        failed = [c.name for c in checks if c.blocking and c.status == "FAIL"]
        fails += bool(failed)
        rows.update(failed)
        for c in checks:
            if c.worse is not None:
                worse.setdefault(c.name, []).append(c.worse)
    return fails, rows, worse


def _shown(hits: int, n: int) -> str:
    low, high = wilson(hits, n)
    return f"{hits / n:.3f} [{low:.3f}, {high:.3f}]" if n else "none"


def observed(group: list[Run], size: tuple[int, int], protocol: dict[str, Any]) -> list[list[str]]:
    """The rows that fail in each stored same-code comparison at `size`, one entry per disjoint
    set of the group's runs in the order given. Equal sides are judged both ways round and stay
    one observation: the two directions share their runs, so they are not two pieces of evidence."""
    step, out = sum(size), []
    for start in range(0, len(group) - step + 1, step):
        left, right = group[start : start + size[0]], group[start + size[0] : start + step]
        failing: set[str] = set()
        for cands, refs in (
            [(left, right), (right, left)] if size[0] == size[1] else [(left, right)]
        ):
            checks = evaluate(cands, refs, "same", protocol)
            failing |= {c.name for c in checks if c.blocking and c.status != "PASS"}
        out.append(sorted(failing))
    return out


def cmd_noise(paths: list[str], sizes: list[tuple[int, int]], sims: int) -> int:
    """AC1 of CC-143: at each size, how often unchanged code fails the rule and the smallest seeded
    regression it catches at least 80% of the time, each with a 95% interval; and where the stored
    runs are too few to observe a size at all, how many more are needed."""
    protocol = load_protocol()
    try:
        runs = [load_run(path) for path in paths]
        for run in runs:
            planned(run, protocol)
    except PlanError as exc:
        print(f"noise: {exc}", file=sys.stderr)
        return 1
    groups: dict[str, list[Run]] = {}
    for run in runs:
        groups.setdefault(
            str(run.hashes.get("head") or f"no recorded head: {run.path}"), []
        ).append(run)
    rule = protocol["rule"]
    numbers = ", ".join(f"{k}={v}" for k, v in rule.items() if _number(v))
    print(f"NOISE  protocol {protocol_hash()}  seed {protocol['sampling']['seed']}  sims {sims}")
    print(f"rule: {numbers}; small groups under {protocol['sampling']['min_families']} questions")
    print(f"stored runs: {len(runs)} of {len(groups)} code(s)")
    for head, group in groups.items():
        print(f"  {head[:7]}  {len(group)} run(s): {', '.join(Path(r.path).name for r in group)}")
    largest = max(len(group) for group in groups.values())
    if largest < 2:
        print("\nToo few stored runs: a same-code comparison needs 2 runs of one code; 1 more run.")
        return 0
    print(
        "\nSimulated runs draw each trial from the stored trials of its own question and code, so\n"
        "they hold the trial-to-trial noise and not a shift that moves a whole run (a provider's\n"
        "bad hour). Read a simulated rate as a floor; the observed pairs are the check on it."
    )
    rng = random.Random(protocol["sampling"]["seed"])
    for size in sizes:
        print(f"\nsize {size[0]}x{size[1]} (candidate runs x reference runs)")
        seen = [rows for group in groups.values() for rows in observed(group, size, protocol)]
        if seen:
            failing = Counter(name for rows in seen for name in rows)
            why = f"; rows: {dict(failing)}" if failing else ""
            failed = sum(bool(rows) for rows in seen)
            ways = ", each judged both ways" if size[0] == size[1] else ""
            rate = _shown(failed, len(seen))
            print(
                f"  observed  unchanged code fails {rate} of {len(seen)} set(s) of runs{ways}{why}"
            )
        else:
            print(
                f"  observed  none: one comparison needs {sum(size)} runs of one code, the largest "
                f"stored group has {largest}; {sum(size) - largest} more run(s) of that code"
            )
        for head, group in groups.items():
            if len(group) < 2:
                continue
            src = stored(group, protocol)
            fails, rows, worse = simulate(src, size, protocol, rng, sims)
            print(f"  simulated {head[:7]}  unchanged code fails {_shown(fails, sims)}")
            for name, values in worse.items():
                ordered = sorted(values)
                at = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
                share = rows[name] / sims
                print(f"      {name:<26} fails {share:.3f}; worsening passed in 95%: {at:.3f}")
            previous, caught, tries = "", False, max(200, sims // 5)
            for count in range(1, len(src.trials["long_tail"]) + 1):
                hits, _rows, _worse = simulate(src, size, protocol, rng, tries, count)
                shown = _shown(hits, tries)
                if hits / tries >= 0.8:
                    points = 100 * count / len(src.trials["long_tail"])
                    print(
                        f"      smallest seeded regression caught 80% of the time: {count} "
                        f"long_tail question(s) broken ({points:.1f} points), caught {shown}"
                        f"{f'; one fewer {previous}' if previous else ''}"
                    )
                    caught = True
                    break
                previous = shown
            if not caught:
                print("      no seeded regression of long_tail questions is caught 80% of the time")
    return 0


# --- commands ------------------------------------------------------------------------------------


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.strip()


def cmd_freeze() -> int:
    """Print what every run and reference records (the protocol, collection, scorer and cohort
    hashes) and the rule: every row `compare` prints, its kind and the number that judges it."""
    protocol = load_protocol()
    rule = protocol["rule"]
    print(
        f"protocol {protocol_hash()}  collection {collection_hash(protocol)}  "
        f"scorer {scorer_hash(protocol)}"
    )
    for name, digest in cohort_hashes(protocol).items():
        print(f"  {name:<10} {len(cohort(protocol, name)):>3} cases  hash {digest}")
    mine, main = blocks(protocol)
    print(f"rule: {mine} candidate run(s) pooled against {main} of main, and against L")
    for row, key in RATE_ROWS.items():
        print(f"  rate  {row:<28} {key} = {rule[key]:g}")
    small = f"small_group_lost_questions = {rule['small_group_lost_questions']:g}"
    minimum = protocol["sampling"]["min_families"]
    print(f"  rate  {'trial rate, a small group':<28} {small} (under {minimum} questions)")
    adopted = "blocks" if rule["lost_questions_block"] else "reported, not adopted"
    print(f"  hard  {'lost questions':<28} lost_questions_block = {adopted}")
    print(f"  hard  {'same-window main':<28} window_hours = {rule['window_hours']:g}")
    print(f"  hard  {', '.join(row for row in HARD_ROWS if row != 'lost questions')}")
    print(f"  report_only = {', '.join(rule['report_only'])} (printed, never blocking)")
    return 0


def build_entry(
    run_paths: str | list[str], head: str, label: str, *, legacy: bool
) -> dict[str, Any]:
    """A reference as it will be stored: one run or a pool of one code's runs. `legacy` is the only
    way to skip the collection check: it says the run predates the frozen protocol, and it is
    stated, not inferred from a label."""
    paths = _pool(run_paths)
    runs = [load_run(path) for path in paths]
    if not legacy:  # a legacy run predates the stamp; any other must be what its entry says
        stamps = [run.hashes for run in runs]
        if not all(stamps) or any(s["head"] != head or s["dirty"] is not False for s in stamps):
            raise PlanError(f"every run must record clean code at {head[:7]}, the head it is named")
        if duplicated(runs):
            raise PlanError("a run is given more than once; a reference pools independent runs")
    long_tail = [t for run in runs for t in run.trials if t.get("tier") == "long_tail"]
    shared = set.intersection(*(set(run.scalars) for run in runs))
    scalars = {k: round(sum(run.scalars[k] for run in runs) / len(runs), 4) for k in sorted(shared)}
    metrics = {
        "long_tail_trial_rate": round(
            sum(bool(t["answered"]) for t in long_tail) / len(long_tail), 3
        ),
        "p95": round(
            percentile([float(t["latency_s"]) for run in runs for t in run.trials], 95), 3
        ),
        **scalars,
    }
    budgets = _budgets()
    blockers = [
        f"{key} {scalars[key]} < {floor}"
        for key, floor in (
            ("answered_rate", budgets["quality"]["answered_rate_min"]),
            ("retrieval_at_10", budgets["quality"]["retrieval_at_10_min"]),
            ("selector_at_1", budgets["quality"]["selector_at_1_min"]),
        )
        if key in scalars and scalars[key] < floor
    ]
    if metrics["p95"] > budgets["performance"]["p95_latency_seconds"]:
        blockers.append(f"p95 {metrics['p95']} > {budgets['performance']['p95_latency_seconds']}")
    # a legacy head may predate the protocol file: its collection settings are not looked up
    now = hashes(head) if legacy else judged_by(head)
    return {
        "label": label,
        "head": head,
        "runs": [
            {"run": path, "run_sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
            for path in paths
        ],
        "hashes": {**now, "protocol": "legacy" if legacy else now["protocol"]},
        "metrics": metrics,
        "blockers": blockers,
        "registered": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def write_refs(refs: dict[str, Any]) -> None:
    METRICS.mkdir(parents=True, exist_ok=True)
    text = json.dumps(refs, indent=2, sort_keys=True) + "\n"
    target = METRICS / "references.json"
    scratch = target.with_suffix(".json.tmp")
    scratch.write_bytes(text.encode("utf-8"))  # LF on every platform
    os.replace(scratch, target)  # an interrupted write never leaves a truncated file


def cmd_register(
    name: str, run_paths: str | list[str], head: str, label: str, *, legacy: bool = False
) -> int:
    """Store a reference. This is also how the owner seeds L, once: `register L RUN RUN`."""
    refs = load_refs()
    if name in refs:
        print(f"{name} is already registered; references are immutable", file=sys.stderr)
        return 1
    try:
        refs[name] = build_entry(run_paths, head, label, legacy=legacy)
    except PlanError as exc:
        print(f"not registered: {exc}", file=sys.stderr)
        return 1
    write_refs(refs)
    entry = refs[name]
    blockers = entry["blockers"] or "none"
    print(f"registered {name} at {head[:7]}: {entry['metrics']}; blockers: {blockers}")
    return 0


def _run_head(path: str) -> str:
    try:
        return str(load_run(path).hashes.get("head", ""))
    except PlanError:
        return ""


def _file_record(path: str) -> dict[str, str]:
    full = ROOT / path
    digest = hashlib.sha256(full.read_bytes()).hexdigest() if full.is_file() else ""
    return {"run": path, "run_sha256": digest, "run_head": _run_head(path)}


def run_compare(
    paths: list[str],
    names: list[str],
    targets: dict[str, float],
    record: bool,
    base_paths: list[str],
) -> tuple[str, list[Check]]:
    """Judge, print every row and, with `record`, append the result to the ledger."""
    checks = compare(paths, names, targets, base_paths)
    width = max(len(c.name) for c in checks)
    for c in checks:
        status = c.status if c.blocking else f"({c.status})"
        print(f"  {status:<14} {c.kind:<4} {c.ref:<7} {c.name:<{width}}  {c.detail}")
    final = verdict(checks)
    print(f"\nVERDICT {final}")
    if record:
        METRICS.mkdir(parents=True, exist_ok=True)
        row = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "head": _head(),
            "runs": [_file_record(path) for path in paths],
            "base": [_file_record(path) for path in base_paths],
            "refs": anchored(names),
            "verdict": final,
            "hashes": judged_by(),
            "checks": [c.__dict__ for c in checks],
        }
        line = json.dumps(row, sort_keys=True) + "\n"
        with (METRICS / "ledger.jsonl").open("ab") as handle:  # append-only, LF everywhere
            handle.write(line.encode("utf-8"))
    return final, checks


def cmd_compare(
    run_paths: str | list[str],
    names: list[str],
    targets: dict[str, float],
    record: bool,
    base_paths: list[str] | None = None,
) -> int:
    final, _checks = run_compare(_pool(run_paths), names, targets, record, list(base_paths or []))
    return 0 if final == "PASS" else 1


def cmd_promote(run_paths: str | list[str]) -> int:
    """Write the entry that moves L to runs of merged main. It needs a recorded pass against the L
    it replaces and no answered rate below that L's: L never moves while a row is red, and never
    down, so a run of small losses each inside the tolerance cannot walk it away. Committing the
    result is the owner's: check_invariants rejects any change to L on a branch."""
    paths = _pool(run_paths)
    refs = load_refs()
    if "L" not in refs:
        print("L is not seeded; the owner seeds it once with `register L`", file=sys.stderr)
        return 1
    heads = {_run_head(path) for path in paths}
    produced = next(iter(heads))
    if len(heads) != 1 or not produced or not _reachable(produced, MAIN):
        print(f"not promoted: the runs' one head is not recorded or not on {MAIN}", file=sys.stderr)
        return 1
    final, checks = run_compare(paths, ["L"], {}, True, [])
    below = [c.name for c in checks if c.name.endswith("trial rate") and (c.worse or 0) > EPS]
    if final != "PASS" or below:
        why = f": below L on {', '.join(below)}" if final == "PASS" else ""
        print(f"not promoted{why}", file=sys.stderr)
        return 1
    # the head that produced the runs, not the one checked out
    entry = build_entry(paths, produced, "accepted post-merge reference", legacy=False)
    write_refs({**refs, "L": entry})  # one write: no state in which L is missing
    print(f"L is now {entry['head'][:7]}")
    return 0


def _sizes(text: str) -> list[tuple[int, int]]:
    return [
        (int(left), int(right)) for left, right in (item.split("x") for item in text.split(","))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze")
    noise = sub.add_parser("noise")
    noise.add_argument("runs", nargs="+")
    noise.add_argument(
        "--sizes", default="1x1,2x2", help="candidate x reference runs, e.g. 1x1,2x2"
    )
    noise.add_argument("--sims", type=int, default=2000)
    register = sub.add_parser("register")
    register.add_argument("name")
    register.add_argument("runs", nargs="+")
    register.add_argument("--head", required=True)
    register.add_argument("--label", required=True)
    register.add_argument(
        "--legacy", action="store_true", help="the run predates the frozen protocol (no hash check)"
    )
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("runs", nargs="+")
    cmp_.add_argument("--base", nargs="+", default=[], help="same-window runs of main (B)")
    cmp_.add_argument("--refs", default="L")
    cmp_.add_argument("--target", action="append", default=[], metavar="COHORT=RATE")
    cmp_.add_argument("--record", action="store_true")
    promote = sub.add_parser("promote")
    promote.add_argument("runs", nargs="+")
    args = parser.parse_args()
    if args.command == "freeze":
        return cmd_freeze()
    if args.command == "noise":
        return cmd_noise(args.runs, _sizes(args.sizes), args.sims)
    if args.command == "register":
        return cmd_register(args.name, args.runs, args.head, args.label, legacy=args.legacy)
    if args.command == "promote":
        return cmd_promote(args.runs)
    targets = {k: float(v) for k, v in (item.split("=", 1) for item in args.target)}
    names = [n for n in args.refs.split(",") if n]
    return cmd_compare(args.runs, names, targets, args.record, args.base)


if __name__ == "__main__":
    sys.exit(main())
