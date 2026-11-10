#!/usr/bin/env python3
"""Frozen-protocol metric comparison: B / P / A / L, family intervals, ratchets (CC-133).

    python scripts/metric_compare.py freeze [--check] [--digests]
    python scripts/metric_compare.py register NAME RUN.json --head SHA --label TEXT [--legacy]
    python scripts/metric_compare.py compare RUN.json [--refs A,A0,L,B] [--target long_tail=0.95]
    python scripts/metric_compare.py promote RUN.json     # the only way L moves

A RUN is an evidence/latest.json-shaped file (`demo.trials`). It is read by this program and only
aggregates are printed; nobody reads the trials. Every status is one of PASS, INCONCLUSIVE,
UNKNOWN (not measured), UNFROZEN (oracle not reviewed by the owner) or FAIL. Only an all-PASS
comparison exits 0. Nothing here has a rerun-until-green path: a compare is appended to the ledger
and the ledger is never rewritten.

Protocol: evals/metric_protocol.toml. Oracle review: evals/oracle_review.toml, owner-only. A scorer,
cohort or index change between a reference and a candidate is FAIL unless
evidence/metrics/bridges.json holds a bridge: {"ref", "from_scorer", "to_scorer", "from_cohorts",
"to_cohorts", "rescored_run", "note"} where rescored_run is the reference's own trials re-scored
by the new scorer on unchanged code. The candidate is then compared with that run, not the old one.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import random
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = ROOT / "evals" / "metric_protocol.toml"
REVIEW = ROOT / "evals" / "oracle_review.toml"
METRICS = ROOT / "evidence" / "metrics"
ORACLE_FIELDS = ("text", "tier", "expect_table", "expect_geo_level", "expect_warning")
ORACLE_FLAGS = ("expect_no_url", "holdout")
CONTRACT_KEYS = ("has_moe", "has_geoid", "has_universe", "has_alternatives")
RANK = {"PASS": 0, "INCONCLUSIVE": 1, "UNKNOWN": 2, "UNFROZEN": 3, "FAIL": 4}


class PlanError(ValueError):
    """The run does not contain exactly the planned trials."""


@dataclass
class Check:
    ref: str
    name: str
    status: str
    detail: str = ""


@dataclass
class Run:
    path: str
    repeat: int
    index_hash: str
    p95_reported: float
    scalars: dict[str, float]
    trials: list[dict[str, Any]]
    hashes: dict[str, Any] = field(default_factory=dict)


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


def oracle_digest(entry: dict[str, Any]) -> str:
    fields = {key: entry.get(key) for key in (*ORACLE_FIELDS, *ORACLE_FLAGS)}
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
        name: _digest(sorted(oracle_digest(e) for e in cohort(protocol, name, head)))
        for name in protocol["cohorts"]
    }


def hashes(head: str | None = None) -> dict[str, Any]:
    protocol = load_protocol()  # the frozen definition; scorer and goldens come from `head`
    return {
        "scorer": scorer_hash(protocol, head),
        "cohorts": cohort_hashes(protocol, head),
        "protocol": protocol_hash(),
    }


# --- oracle review (owner-only) ------------------------------------------------------------------


def oracle_state(protocol: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Per cohort: ids the owner accepted, ids still pending, ids accepted for an older oracle."""
    accepted = (
        tomllib.loads(REVIEW.read_text(encoding="utf-8")).get("accepted", {})
        if (REVIEW.is_file())
        else {}
    )
    state: dict[str, dict[str, list[str]]] = {}
    for name in protocol["cohorts"]:
        rows: dict[str, list[str]] = {"accepted": [], "pending": [], "stale": []}
        for entry in cohort(protocol, name):
            review = accepted.get(entry["id"])
            if not isinstance(review, dict) or not review.get("reviewer"):
                rows["pending"].append(entry["id"])
            elif review.get("oracle") != oracle_digest(entry):
                rows["stale"].append(entry["id"])
            else:
                rows["accepted"].append(entry["id"])
        state[name] = rows
    return state


# --- runs ----------------------------------------------------------------------------------------


def percentile(values: list[float], p: float) -> float:
    """Nearest rank, the same rule scripts/run_demo.py uses for demo.p95_latency_seconds."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(math.ceil(p / 100 * len(ordered)) - 1, len(ordered) - 1))]


def load_run(path: str | Path) -> Run:
    full = Path(path) if Path(path).is_absolute() else ROOT / path
    data = json.loads(full.read_text(encoding="utf-8"))
    demo = data["demo"]
    scalars = {k: float(data[k]) for k in ("retrieval_at_10", "selector_at_1") if k in data}
    scalars["answered_rate"] = float(demo["answered_rate"])
    return Run(
        path=str(path),
        repeat=int(demo["repeat"]),
        index_hash=str(demo.get("index_hash") or ""),
        p95_reported=float(demo["p95_latency_seconds"]),
        scalars=scalars,
        trials=list(demo["trials"]),
    )


def families(run: Run, ids: list[str], tier: str, repeat: int) -> dict[str, list[dict[str, Any]]]:
    """Every planned trial of a cohort, by family. A missing, extra or short family is a PlanError:
    dropped trials and a shrunken denominator can never produce a rate."""
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


def family_rates(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, float]]:
    return {
        family: {
            "trial": sum(bool(t["answered"]) for t in items) / len(items),
            "case": 1.0 if all(t["answered"] for t in items) else 0.0,
            "rows": sum(int(t.get("rows") or 0) for t in items) / len(items),
            "empty": sum(int(t.get("rows") or 0) == 0 for t in items) / len(items),
        }
        for family, items in grouped.items()
    }


# --- statistics ----------------------------------------------------------------------------------


def paired_interval(diffs: list[float], protocol: dict[str, Any]) -> tuple[float, float]:
    """(point, lower bound) of the mean paired family difference. Families are resampled, never
    trials: repeats and paraphrases of one family are one observation."""
    sampling = protocol["sampling"]
    n = len(diffs)
    point = sum(diffs) / n
    rng = random.Random(sampling["seed"])
    means = sorted(
        sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(sampling["resamples"])
    )
    tail = (1 - sampling["confidence"]) / 2
    return point, means[int(tail * len(means))]


def judge(diffs: list[float], protocol: dict[str, Any]) -> tuple[str, str]:
    sampling = protocol["sampling"]
    point = sum(diffs) / len(diffs)  # an observed decrease is a fact at any sample size
    if point < 0:
        return "FAIL", f"observed decrease ({point:+.3f} over {len(diffs)} families)"
    if len(diffs) < sampling["min_families"]:
        return "INCONCLUSIVE", f"{len(diffs)} families, need {sampling['min_families']}"
    point, lower = paired_interval(diffs, protocol)
    note = f"diff {point:+.3f}, lower {lower:+.3f}"
    if lower < -sampling["max_regression"]:
        return (
            "INCONCLUSIVE",
            f"cannot rule out a drop over {sampling['max_regression']:.0%} ({note})",
        )
    return "PASS", note


# --- comparison ----------------------------------------------------------------------------------


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


def absolute(run: Run, protocol: dict[str, Any]) -> list[Check]:
    budgets = tomllib.loads((ROOT / "budgets.toml").read_text(encoding="utf-8"))
    quality, ceiling = budgets["quality"], budgets["performance"]["p95_latency_seconds"]
    out: list[Check] = []
    for key, floor in (
        ("answered_rate", quality["answered_rate_min"]),
        ("retrieval_at_10", quality["retrieval_at_10_min"]),
        ("selector_at_1", quality["selector_at_1_min"]),
    ):
        value = run.scalars.get(key)
        ok = value is not None and value >= floor
        out.append(Check("floor", key, "PASS" if ok else "FAIL", f"{value} vs floor {floor}"))
    long_tail = [t for t in run.trials if t.get("tier") == "long_tail"]
    if long_tail and "answered_rate" in run.scalars:  # the reported rate must be the trials' own
        rate = sum(bool(t["answered"]) for t in long_tail) / len(long_tail)
        agrees = abs(rate - run.scalars["answered_rate"]) <= 0.001
        detail = f"{rate:.3f} from trials vs reported {run.scalars['answered_rate']:.3f}"
        out.append(
            Check("floor", "answered_rate matches trials", "PASS" if agrees else "FAIL", detail)
        )
    times = [float(t["latency_s"]) for t in run.trials]
    p95 = percentile(times, 95)
    agrees = abs(p95 - run.p95_reported) <= 0.01
    out.append(
        Check(
            "floor",
            "p95 matches trials",
            "PASS" if agrees else "FAIL",
            f"{p95:.3f} vs reported {run.p95_reported:.3f}",
        )
    )
    out.append(
        Check(
            "floor",
            "p95 ceiling",
            "PASS" if p95 <= ceiling else "FAIL",
            f"{p95:.3f}s vs {ceiling:g}s",
        )
    )
    answered = [
        t for t in run.trials if t.get("tier") == "long_tail" and t["answered"] and t.get("rows")
    ]
    if answered and not all(k in t for t in answered for k in CONTRACT_KEYS):
        out.append(
            Check("floor", "response contract", "UNKNOWN", "trial records carry no contract fields")
        )
    elif answered:
        bad = sum(not all(t[k] for k in CONTRACT_KEYS) for t in answered)
        out.append(
            Check(
                "floor",
                "response contract",
                "PASS" if not bad else "FAIL",
                f"{bad} of {len(answered)} answered trials lack a contract field",
            )
        )
    return out


def evaluate(
    cand: Run, ref: Run, name: str, protocol: dict[str, Any], *, label: str = ""
) -> list[Check]:
    repeat = protocol["sampling"]["repeat"]
    out: list[Check] = []
    if cand.repeat != repeat or ref.repeat != repeat:
        return [
            Check(name, "repeat", "FAIL", f"cand {cand.repeat}, ref {ref.repeat}, frozen {repeat}")
        ]
    if not cand.index_hash or cand.index_hash != ref.index_hash:
        return [Check(name, "index", "FAIL", "missing or different index; not like for like")]
    rates: dict[str, tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]] = {}
    try:
        for cohort_name in protocol["cohorts"]:
            ids = [e["id"] for e in cohort(protocol, cohort_name)]
            tier = protocol["cohorts"][cohort_name]["tier"]
            rates[cohort_name] = (
                family_rates(families(cand, ids, tier, repeat)),
                family_rates(families(ref, ids, tier, repeat)),
            )
    except PlanError as exc:
        return [Check(name, "planned trials", "FAIL", str(exc))]
    for cohort_name, (mine, theirs) in rates.items():
        for metric in ("trial", "case"):
            diffs = [mine[f][metric] - theirs[f][metric] for f in sorted(mine)]
            status, detail = judge(diffs, protocol)
            out.append(Check(name, f"{cohort_name} {metric} rate", status, detail))
    mine_lt, theirs_lt = rates["long_tail"]
    lost = sorted(f for f in mine_lt if mine_lt[f]["rows"] < theirs_lt[f]["rows"])
    out.append(
        Check(
            name,
            "rows per family",
            "FAIL" if lost else "PASS",
            f"{len(lost)} families returned fewer rows" if lost else "no family lost rows",
        )
    )
    refusal = sum(v["empty"] for v in mine_lt.values()) - sum(
        v["empty"] for v in theirs_lt.values()
    )
    out.append(
        Check(
            name,
            "empty answers (long_tail)",
            "FAIL" if refusal > 0 else "PASS",
            f"{refusal / len(mine_lt):+.3f} per family",
        )
    )
    for key in ("retrieval_at_10", "selector_at_1"):
        if key in cand.scalars and key in ref.scalars:
            drop = cand.scalars[key] < ref.scalars[key]
            out.append(
                Check(
                    name,
                    key,
                    "FAIL" if drop else "PASS",
                    f"{cand.scalars[key]} vs {ref.scalars[key]}",
                )
            )
    c95 = percentile([float(t["latency_s"]) for t in cand.trials], 95)
    r95 = percentile([float(t["latency_s"]) for t in ref.trials], 95)
    worse = c95 > r95
    credited = (
        ""
        if c95 >= r95 or all(c.status == "PASS" for c in out if "rate" in c.name)
        else "; gain not credited, answers fell"
    )
    out.append(
        Check(
            name,
            "p95 vs reference",
            "FAIL" if worse else "PASS",
            f"{c95:.3f}s vs {r95:.3f}s{credited}",
        )
    )
    if label:
        out.append(Check(name, "reference label", "PASS", label))
    return out


def target_check(
    cand: Run, base: Run, protocol: dict[str, Any], cohort_name: str, target: float
) -> list[Check]:
    """A story's owned cohort: both rates at the target; if the base was below it, a paired gain."""
    repeat = protocol["sampling"]["repeat"]
    ids = [e["id"] for e in cohort(protocol, cohort_name)]
    tier = protocol["cohorts"][cohort_name]["tier"]
    try:
        mine = family_rates(families(cand, ids, tier, repeat))
        theirs = family_rates(families(base, ids, tier, repeat))
    except PlanError as exc:
        return [Check("target", cohort_name, "FAIL", str(exc))]
    out: list[Check] = []
    for metric in ("trial", "case"):
        rate = sum(v[metric] for v in mine.values()) / len(mine)
        was = sum(v[metric] for v in theirs.values()) / len(theirs)
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
            _point, lower = paired_interval(
                [mine[f][metric] - theirs[f][metric] for f in sorted(mine)], protocol
            )
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


def compare(cand_path: str, ref_names: list[str], targets: dict[str, float]) -> list[Check]:
    protocol = load_protocol()
    now = hashes()
    cand = load_run(cand_path)
    refs = load_refs()
    out = absolute(cand, protocol)
    state = oracle_state(protocol)
    for cohort_name, rows in state.items():
        todo = len(rows["pending"]) + len(rows["stale"])
        out.append(
            Check(
                "oracle",
                cohort_name,
                "UNFROZEN" if todo else "PASS",
                f"{len(rows['accepted'])} accepted, {len(rows['pending'])} pending, "
                f"{len(rows['stale'])} stale",
            )
        )
    for name in ref_names:
        entry = refs.get(name)
        if entry is None:
            out.append(Check(name, "reference", "UNKNOWN", "not registered"))
            continue
        ref_file = ROOT / entry["run"]
        if hashlib.sha256(ref_file.read_bytes()).hexdigest() != entry["run_sha256"]:
            out.append(Check(name, "reference file", "FAIL", "run file changed since registration"))
            continue
        old = entry["hashes"]
        run_path, label = entry["run"], entry["label"]
        if old["protocol"] not in ("legacy", now["protocol"]):
            out.append(
                Check(
                    name, "protocol hash", "FAIL", "the frozen protocol changed since the reference"
                )
            )
            continue
        if old["scorer"] != now["scorer"] or old["cohorts"] != now["cohorts"]:
            bridge = _bridge(name, old, now)
            if bridge is None:
                out.append(
                    Check(
                        name,
                        "scorer / cohort hashes",
                        "FAIL",
                        "changed since the reference, no bridge; any gain is the instrument's",
                    )
                )
                continue
            rescored = ROOT / bridge["rescored_run"]
            pinned = rescored.is_file() and (
                hashlib.sha256(rescored.read_bytes()).hexdigest() == bridge.get("rescored_sha256")
            )
            if not pinned:
                out.append(Check(name, "bridge", "FAIL", "rescored run missing or not pinned"))
                continue
            run_path, label = bridge["rescored_run"], f"{label}; bridged: {bridge['note']}"
        out += evaluate(cand, load_run(run_path), name, protocol, label=label)
        for cohort_name, goal in targets.items():
            out += target_check(cand, load_run(run_path), protocol, cohort_name, goal)
    return out


def verdict(checks: list[Check]) -> str:
    return max((c.status for c in checks), key=RANK.__getitem__, default="UNKNOWN")


# --- commands ------------------------------------------------------------------------------------


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.strip()


def cmd_freeze(check: bool, digests: bool) -> int:
    protocol = load_protocol()
    print(f"protocol {protocol_hash()}  scorer {scorer_hash(protocol)}")
    todo = 0
    cohort_digest = cohort_hashes(protocol)
    for name, rows in oracle_state(protocol).items():
        todo += len(rows["pending"]) + len(rows["stale"])
        counts = " ".join(f"{len(ids)} {key}" for key, ids in rows.items())
        print(f"  {name:<10} {counts}  hash {cohort_digest[name]}")
    if digests:  # what the owner signs: the id and the digest of its expectations, nothing else
        for name, rows in oracle_state(protocol).items():
            for entry in cohort(protocol, name):
                if entry["id"] in rows["pending"] + rows["stale"]:
                    print(f"  {entry['id']:<6} {name:<10} {oracle_digest(entry)}")
    print("FROZEN" if not todo else f"UNFROZEN: {todo} cases await the owner's oracle review")
    return 1 if check and todo else 0


def build_entry(run_path: str, head: str, label: str, *, legacy: bool) -> dict[str, Any]:
    """A reference as it will be stored. `legacy` is the only way to skip the protocol-hash check:
    it says the run predates the frozen protocol, and it is stated, not inferred from a label."""
    run = load_run(run_path)
    long_tail = [t for t in run.trials if t.get("tier") == "long_tail"]
    metrics = {
        "long_tail_trial_rate": round(
            sum(bool(t["answered"]) for t in long_tail) / len(long_tail), 3
        ),
        "p95": round(percentile([float(t["latency_s"]) for t in run.trials], 95), 3),
        **run.scalars,
    }
    budgets = tomllib.loads((ROOT / "budgets.toml").read_text(encoding="utf-8"))
    blockers = [
        f"{key} {run.scalars[key]} < {floor}"
        for key, floor in (
            ("answered_rate", budgets["quality"]["answered_rate_min"]),
            ("retrieval_at_10", budgets["quality"]["retrieval_at_10_min"]),
            ("selector_at_1", budgets["quality"]["selector_at_1_min"]),
        )
        if key in run.scalars and run.scalars[key] < floor
    ]
    if metrics["p95"] > budgets["performance"]["p95_latency_seconds"]:
        blockers.append(f"p95 {metrics['p95']} > {budgets['performance']['p95_latency_seconds']}")
    return {
        "label": label,
        "head": head,
        "run": run_path,
        "run_sha256": hashlib.sha256((ROOT / run_path).read_bytes()).hexdigest(),
        "hashes": {**hashes(head), "protocol": "legacy" if legacy else protocol_hash()},
        "metrics": metrics,
        "blockers": blockers,
        "registered": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def write_refs(refs: dict[str, Any]) -> None:
    METRICS.mkdir(parents=True, exist_ok=True)
    text = json.dumps(refs, indent=2, sort_keys=True) + "\n"
    (METRICS / "references.json").write_bytes(text.encode("utf-8"))  # LF on every platform


def cmd_register(name: str, run_path: str, head: str, label: str, *, legacy: bool = False) -> int:
    refs = load_refs()
    if name in refs:
        print(f"{name} is already registered; references are immutable", file=sys.stderr)
        return 1
    refs[name] = build_entry(run_path, head, label, legacy=legacy)
    write_refs(refs)
    entry = refs[name]
    blockers = entry["blockers"] or "none"
    print(f"registered {name} at {head[:7]}: {entry['metrics']}; blockers: {blockers}")
    return 0


def cmd_compare(run_path: str, names: list[str], targets: dict[str, float], record: bool) -> int:
    checks = compare(run_path, names, targets)
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"  {c.status:<12} {c.ref:<7} {c.name:<{width}}  {c.detail}")
    final = verdict(checks)
    print(f"\nVERDICT {final}")
    if record:
        METRICS.mkdir(parents=True, exist_ok=True)
        row = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "head": _head(),
            "run": run_path,
            "refs": names,
            "verdict": final,
            "hashes": hashes(),
            "checks": [c.__dict__ for c in checks],
        }
        line = json.dumps(row, sort_keys=True) + "\n"
        with (METRICS / "ledger.jsonl").open("ab") as handle:  # append-only, LF everywhere
            handle.write(line.encode("utf-8"))
    return 0 if final == "PASS" else 1


def cmd_promote(run_path: str) -> int:
    """L moves only when the candidate passes against A and the current L: never a high watermark,
    never a reset after a run of small losses."""
    refs = load_refs()
    names = [n for n in ("A", "L") if n in refs]
    if "A" not in refs:
        print("A is not registered", file=sys.stderr)
        return 1
    if cmd_compare(run_path, names, {}, record=True):
        print("not promoted", file=sys.stderr)
        return 1
    entry = build_entry(run_path, _head(), "accepted post-merge reference", legacy=False)
    write_refs({**refs, "L": entry})  # one write: no state in which L is missing
    print(f"L is now {entry['head'][:7]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--check", action="store_true")
    freeze.add_argument("--digests", action="store_true")
    register = sub.add_parser("register")
    register.add_argument("name")
    register.add_argument("run")
    register.add_argument("--head", required=True)
    register.add_argument("--label", required=True)
    register.add_argument(
        "--legacy", action="store_true", help="the run predates the frozen protocol (no hash check)"
    )
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("run")
    cmp_.add_argument("--refs", default="A,A0,L,B")
    cmp_.add_argument("--target", action="append", default=[], metavar="COHORT=RATE")
    cmp_.add_argument("--record", action="store_true")
    promote = sub.add_parser("promote")
    promote.add_argument("run")
    args = parser.parse_args()
    if args.command == "freeze":
        return cmd_freeze(args.check, args.digests)
    if args.command == "register":
        return cmd_register(args.name, args.run, args.head, args.label, legacy=args.legacy)
    if args.command == "promote":
        return cmd_promote(args.run)
    targets = {k: float(v) for k, v in (item.split("=", 1) for item in args.target)}
    return cmd_compare(args.run, [n for n in args.refs.split(",") if n], targets, args.record)


if __name__ == "__main__":
    sys.exit(main())
