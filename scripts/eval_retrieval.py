#!/usr/bin/env python3
"""Retrieval scoreboard: can we find the right table for a question?

This is slice 0's only metric. It runs without an agent, without FastAPI and
without a frontend, so you learn whether the product is possible in week one
rather than month four.

    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --tier long_tail
    python scripts/eval_retrieval.py --verbose

Writes evidence/latest.json, which check_budgets.py reads.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "golden_questions.toml"
EVIDENCE = ROOT / "evidence" / "latest.json"
TOP_K = 5


@dataclass
class Result:
    id: str
    text: str
    tier: str
    expected: str
    ranked: list[str] = field(default_factory=list)

    @property
    def rank(self) -> int | None:
        """1-indexed position of the expected table, or None if absent."""
        try:
            return self.ranked.index(self.expected) + 1
        except ValueError:
            return None

    @property
    def hit_at_1(self) -> bool:
        return self.rank == 1

    @property
    def hit_at_k(self) -> bool:
        return self.rank is not None

    @property
    def reciprocal_rank(self) -> float:
        return 1.0 / self.rank if self.rank else 0.0


def load_retriever():
    """Return search(question, k) -> [table_id, ...], best first.

    Falls back to a stub that always misses, so the harness is runnable on an
    empty repository. A stub scoring above zero would be a bug in the harness.
    """
    try:
        from src.retrieval.index import search  # type: ignore[import-not-found]

        return search
    except ImportError:
        print("! no retriever found at api/src/retrieval/index.py - scoring the stub\n")
        return lambda question, k: []


def evaluate(tier_filter: str | None) -> list[Result]:
    with QUESTIONS.open("rb") as handle:
        questions = tomllib.load(handle)["question"]

    search = load_retriever()
    results: list[Result] = []

    for entry in questions:
        expected = entry.get("expect_table")
        if not expected:
            continue  # warning-only traps are scored by the demo suite, not here
        if tier_filter and entry.get("tier") != tier_filter:
            continue
        ranked = list(search(entry["text"], TOP_K))[:TOP_K]
        results.append(
            Result(
                id=entry["id"],
                text=entry["text"],
                tier=entry.get("tier", "core"),
                expected=expected,
                ranked=ranked,
            )
        )
    return results


def summarize(results: list[Result]) -> dict:
    def rates(subset: list[Result]) -> dict:
        if not subset:
            return {"n": 0}
        n = len(subset)
        return {
            "n": n,
            "retrieval_at_1": round(sum(r.hit_at_1 for r in subset) / n, 3),
            f"retrieval_at_{TOP_K}": round(sum(r.hit_at_k for r in subset) / n, 3),
            "mrr": round(sum(r.reciprocal_rank for r in subset) / n, 3),
        }

    overall = rates(results)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retrieval_at_1": overall.get("retrieval_at_1", 0.0),
        "overall": overall,
        "by_tier": {
            tier: rates([r for r in results if r.tier == tier])
            for tier in sorted({r.tier for r in results})
        },
        "misses": [
            {"id": r.id, "question": r.text, "expected": r.expected, "got": r.ranked[:3]}
            for r in results
            if not r.hit_at_1
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["core", "long_tail", "trap"])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    results = evaluate(args.tier)
    if not results:
        print("No scorable questions found.")
        return 1

    summary = summarize(results)

    print("RETRIEVAL\n")
    for tier, stats in summary["by_tier"].items():
        if not stats["n"]:
            continue
        print(
            f"  {tier:<10} n={stats['n']:<3}  @1={stats['retrieval_at_1']:.0%}"
            f"   @{TOP_K}={stats[f'retrieval_at_{TOP_K}']:.0%}   mrr={stats['mrr']:.2f}"
        )
    overall = summary["overall"]
    print(f"\n  {'OVERALL':<10} n={overall['n']:<3}  @1={overall['retrieval_at_1']:.0%}")

    if args.verbose and summary["misses"]:
        print("\nMISSES\n")
        for miss in summary["misses"]:
            got = ", ".join(miss["got"]) or "(nothing)"
            print(f"  {miss['id']}  expected {miss['expected']:<8} got {got}")
            print(f"      {miss['question']}")

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if EVIDENCE.exists():
        try:
            existing = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    existing.update(summary)
    EVIDENCE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\nWrote {EVIDENCE.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
