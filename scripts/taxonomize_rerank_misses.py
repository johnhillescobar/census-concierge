#!/usr/bin/env python3
"""Classify long-tail rerank misses by failure mode.

Runs one pass with the current rerank.py model. For each miss, records whether
the expected table was in the raw top-10 pool and how the selector failed.

    python scripts/taxonomize_rerank_misses.py
    python scripts/taxonomize_rerank_misses.py --json evidence/gemini-rerank-taxonomy.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "golden_questions.toml"
POOL = 10

load_dotenv(ROOT / ".env")


@dataclass
class Miss:
    id: str
    question: str
    expected: str
    picked: str
    raw_rank: int | None
    category: str
    raw_top3: list[str]
    note: str


def _subject(table_id: str) -> str:
    body = table_id[1:] if table_id and table_id[0] in "BC" else table_id
    return body[:2] if len(body) >= 2 else ""


def _classify(expected: str, picked: str, raw: list[str], raw_rank: int | None) -> tuple[str, str]:
    if raw_rank is None:
        return "out_of_pool", "expected table not in raw top-10"

    if raw_rank == 1:
        stage = "selector_overrode_correct_top1"
    elif raw_rank <= 3:
        stage = "selector_miss_near_top"
    else:
        stage = "selector_miss_deep_in_pool"

    exp_subj = _subject(expected)
    pick_subj = _subject(picked)
    if exp_subj and exp_subj == pick_subj:
        family = "sibling_same_subject"
    elif expected[:4] == picked[:4]:
        family = "sibling_same_prefix"
    else:
        family = "cross_topic"

    return f"{stage}:{family}", f"raw rank {raw_rank}, picked {picked}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, help="write full report here")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "api"))
    from src.retrieval.index import load, search  # type: ignore[import-not-found]
    from src.retrieval.rerank import MODEL, Candidate, choose  # type: ignore[import-not-found]

    try:
        index = load()
    except FileNotFoundError:
        print("index_store/ not found — run `make index` first", file=sys.stderr)
        return 1

    position = {table: i for i, table in enumerate(index.tables)}
    with QUESTIONS.open("rb") as handle:
        entries = [
            q
            for q in tomllib.load(handle)["question"]
            if q.get("tier") == "long_tail" and q.get("expect_table") and not q.get("holdout")
        ]

    hits = 0
    misses: list[Miss] = []
    by_category: dict[str, int] = {}

    for entry in entries:
        question = entry["text"]
        expected = entry["expect_table"]
        raw = search(question, POOL)
        raw_rank = raw.index(expected) + 1 if expected in raw else None
        pool = raw[:POOL]
        picked = choose(
            question,
            [
                Candidate(t, index.titles[position[t]], index.universes[position[t]])
                for t in pool
                if t in position
            ],
        )
        if picked == expected:
            hits += 1
            continue
        category, note = _classify(expected, picked, raw, raw_rank)
        by_category[category] = by_category.get(category, 0) + 1
        misses.append(
            Miss(
                id=entry["id"],
                question=question,
                expected=expected,
                picked=picked,
                raw_rank=raw_rank,
                category=category,
                raw_top3=raw[:3],
                note=note,
            )
        )

    n = len(entries)
    report = {
        "model": MODEL,
        "n": n,
        "retrieval_at_1": round(hits / n, 3) if n else 0.0,
        "hits": hits,
        "misses": [asdict(m) for m in misses],
        "by_category": by_category,
    }

    print(f"TAXONOMY  model={MODEL}  n={n}  @1={hits / n:.1%}  misses={len(misses)}\n")
    print("BY CATEGORY")
    for category, count in sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:>2}  {category}")
    print("\nMISSES")
    for miss in misses:
        pool = f"raw@{miss.raw_rank}" if miss.raw_rank else "not in top-10"
        print(f"  {miss.id}  {miss.category}")
        print(f"      expected {miss.expected}  picked {miss.picked}  ({pool})")
        print(f"      {miss.question}")

    if args.json:
        out = args.json if args.json.is_absolute() else ROOT / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote {out.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
