#!/usr/bin/env python3
"""Do a table's own generated questions retrieve that table first?

    python scripts/score_synthetic.py

The mechanical check on generation quality. "Read what the LLM wrote" does not
survive 1,300 tables under time pressure; this does, and it is the only thing
that would catch a slice of the corpus where the questions are garbage.

Scored on a fixed random sample rather than all ~8,700 questions: at n=600 the
standard error is under two points, which is finer than any decision this
number informs. The seed is fixed so the number moves only when the
questions or the index do.

Writes `synthetic_self_retrieval` into evidence/latest.json.
"""

from __future__ import annotations

import contextlib
import json
import random
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from src.retrieval import embedding, index  # noqa: E402
from src.retrieval.synthetic import load_questions  # noqa: E402

EVIDENCE = ROOT / "evidence" / "latest.json"
SAMPLE = 600
SEED = 20260814


def main() -> int:
    load_dotenv(ROOT / ".env")
    questions = load_questions()
    if not questions:
        print("No generated questions. Run build_index.py --generate first.")
        return 1

    loaded = index.load()
    position = {table: i for i, table in enumerate(loaded.tables)}
    pairs = [
        (table, question)
        for table, items in questions.items()
        for question in items
        if table in position
    ]
    random.Random(SEED).shuffle(pairs)
    pairs = pairs[:SAMPLE]

    vectors = embedding.embed_texts([q for _, q in pairs], model=loaded.meta["embedding_model"])
    ranked = np.argsort(-(vectors @ loaded.vectors.T), axis=1)

    hits = sum(1 for i, (table, _) in enumerate(pairs) if ranked[i][0] == position[table])
    top5 = sum(1 for i, (table, _) in enumerate(pairs) if position[table] in ranked[i][:5].tolist())
    rate = hits / len(pairs)

    print("\nSYNTHETIC SELF-RETRIEVAL\n")
    print(f"  sampled       {len(pairs)} of {sum(len(v) for v in questions.values())} questions")
    print(f"  @1            {rate:.0%}")
    print(f"  @5            {top5 / len(pairs):.0%}")

    print("\n  worst tables (own question does not find them):")
    misses: dict[str, int] = {}
    for i, (table, _) in enumerate(pairs):
        if ranked[i][0] != position[table]:
            misses[table] = misses.get(table, 0) + 1
    for table, count in sorted(misses.items(), key=lambda kv: -kv[1])[:8]:
        print(f"    {table:<8} {count} miss(es)  {loaded.titles[position[table]][:52]}")

    existing: dict[str, object] = {}
    if EVIDENCE.exists():
        with contextlib.suppress(ValueError):
            existing = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    existing["synthetic_self_retrieval"] = round(rate, 3)
    EVIDENCE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\nWrote {EVIDENCE.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
