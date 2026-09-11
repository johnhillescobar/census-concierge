#!/usr/bin/env python3
"""Retrieval scoreboard: can we find the right table for a question?

This is slice 0's only metric. It runs without an agent, without FastAPI and
without a frontend, so you learn whether the product is possible in week one
rather than month four.

    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --tier long_tail
    python scripts/eval_retrieval.py --verbose

Needs OPENAI_API_KEY once the index has a semantic layer — the question has to
be embedded with the same model the documents were. A BM25-only index scores
without any key.

Writes evidence/latest.json, which check_budgets.py reads.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "golden_questions.toml"
EVIDENCE = ROOT / "evidence" / "latest.json"
TOP_K = 5

load_dotenv(ROOT / ".env")


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
    def hit_at_3(self) -> bool:
        return self.rank is not None and self.rank <= 3

    @property
    def hit_at_k(self) -> bool:
        return self.rank is not None

    @property
    def reciprocal_rank(self) -> float:
        return 1.0 / self.rank if self.rank else 0.0


def load_retriever(rerank: bool = False):
    """Return search(question, k) -> [table_id, ...], best first.

    Falls back to a stub that always misses, so the harness is runnable on an
    empty repository. A stub scoring above zero would be a bug in the harness.

    With `rerank`, an LLM picks one table out of the top ten and it is promoted
    to first. That measures what slice 1's agent will do with the same list —
    `search()` itself never selects.
    """
    try:
        from src.retrieval.index import load, search  # type: ignore[import-not-found]
    except ImportError:
        print("! no retriever found at api/src/retrieval/index.py - scoring the stub\n")
        return lambda question, k: []
    try:
        # `index.py` exists once slice 0 ships, so the ImportError above is
        # never taken again - but index_store/ is gitignored, so a clean
        # checkout with no build still has no artifact to load. Probe before
        # either return path, not just the rerank one: load() crashes on
        # FileNotFoundError, and without this the plain-search path would too.
        load()
    except FileNotFoundError:
        print("! index_store/ not found - scoring the stub. Run `make index` first.\n")
        return lambda question, k: []
    if not rerank:
        return search

    from src.retrieval.rerank import Candidate, choose  # type: ignore[import-not-found]

    index = load()
    position = {table: i for i, table in enumerate(index.tables)}

    def search_and_rerank(question: str, k: int) -> list[str]:
        ranked = search(question, max(k, 10))
        if not ranked:
            # choose() reads candidates[0] unconditionally; search() returning
            # [] for a no-match question is a documented, tested case, not an
            # error, and must not crash --rerank.
            return []
        picked = choose(
            question,
            [Candidate(t, index.titles[position[t]], index.universes[position[t]]) for t in ranked],
        )
        return [picked, *(t for t in ranked if t != picked)][:k]

    return search_and_rerank


def evaluate(tier_filter: str | None, holdout: bool = False, rerank: bool = False) -> list[Result]:
    with QUESTIONS.open("rb") as handle:
        questions = tomllib.load(handle)["question"]

    search = load_retriever(rerank)
    results: list[Result] = []

    for entry in questions:
        expected = entry.get("expect_table")
        if not expected:
            continue  # warning-only traps are scored by the demo suite, not here
        # The holdout is scored at slice boundaries only and never mixed into
        # the tuning number, or it stops being a holdout after the first run.
        if bool(entry.get("holdout")) is not holdout:
            continue
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
            # @3 is recorded but not gated. `@1` is a PROXY for answered_rate,
            # which is the number that matters and cannot be measured until an
            # agent exists. If the agent turns out to weigh several candidates
            # on universe and vintage rather than taking the top hit, @3 is the
            # honest gate — revisit on this data, not on argument.
            "retrieval_at_3": round(sum(r.hit_at_3 for r in subset) / n, 3),
            f"retrieval_at_{TOP_K}": round(sum(r.hit_at_k for r in subset) / n, 3),
            "mrr": round(sum(r.reciprocal_rank for r in subset) / n, 3),
        }

    overall = rates(results)
    by_tier = {
        tier: rates([r for r in results if r.tier == tier])
        for tier in sorted({r.tier for r in results})
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # The gated number is LONG-TAIL, not the all-tier average, because
        # `core` and `trap` would move it without the product getting better.
        # budgets.toml says long-tail; this is the key it reads.
        "retrieval_at_1": by_tier.get("long_tail", overall).get("retrieval_at_1", 0.0),
        "overall": overall,
        "by_tier": by_tier,
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
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="score the held-out questions instead. Slice boundaries only.",
    )
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="let an LLM pick one of the top ten, as slice 1's agent will",
    )
    args = parser.parse_args()

    results = evaluate(args.tier, holdout=args.holdout, rerank=args.rerank)
    if not results:
        print("No scorable questions found.")
        return 1

    summary = summarize(results)

    print("RETRIEVAL (holdout)\n" if args.holdout else "RETRIEVAL\n")
    for tier, stats in summary["by_tier"].items():
        if not stats["n"]:
            continue
        print(
            f"  {tier:<10} n={stats['n']:<3}  @1={stats['retrieval_at_1']:.0%}"
            f"   @3={stats['retrieval_at_3']:.0%}"
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
        # A corrupt evidence file must not block a run that is about to
        # overwrite it anyway.
        with contextlib.suppress(ValueError):
            existing = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    if args.rerank:
        # Never over `retrieval_at_1`. That key gates the budget and must mean
        # what `search()` actually returns; reranking is a second component
        # that slice 1's agent, not the index, will perform.
        existing["retrieval_at_1_reranked"] = summary["retrieval_at_1"]
        existing["reranked"] = summary
    elif args.holdout:
        # Recorded beside the tuning number, never over it. Divergence between
        # the two is the signal; one number that quietly replaced the other is
        # no signal at all.
        existing["retrieval_at_1_holdout"] = summary["retrieval_at_1"]
        existing["holdout"] = summary
    else:
        existing.update(summary)
    EVIDENCE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\nWrote {EVIDENCE.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
