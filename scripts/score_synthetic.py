#!/usr/bin/env python3
"""Score generated-question quality against the shipped index.

    python scripts/score_synthetic.py

Two numbers:

- **synthetic_alignment** (gated) — mean cosine between each question embedding
  and its table's semantic document (title + universe + concept; synthetic
  questions are *not* in that document). Catches generation that drifts off-topic
  without requiring a question to beat 635 siblings at rank 1.

- **synthetic_self_retrieval** (diagnostic) — @1/@5 rank of the table when the
  question is the query. This was the original gate when questions lived in the
  embedded text; with them out it measures the same sibling-ranking problem as
  the golden set (~45% @1) and is no longer gated.

Scored on a fixed random sample (n=600, seed fixed) rather than all ~8,700
questions: standard error under two points, finer than any decision here.

Writes both keys into evidence/latest.json.
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

    own_sims: list[float] = []
    hits = 0
    top5 = 0
    for i, (table, _) in enumerate(pairs):
        doc = position[table]
        own_sims.append(float(vectors[i] @ loaded.vectors[doc]))
        if ranked[i][0] == doc:
            hits += 1
        if doc in ranked[i][:5].tolist():
            top5 += 1

    n = len(pairs)
    alignment = sum(own_sims) / n
    at_1 = hits / n
    at_5 = top5 / n

    print("\nSYNTHETIC QUESTION QUALITY\n")
    print(f"  sampled              {n} of {sum(len(v) for v in questions.values())} questions")
    print(f"  alignment (gated)    {alignment:.3f}   mean cosine to own document")
    print(f"  self-retrieval @1    {at_1:.0%}   diagnostic — same ranking problem as golden set")
    print(f"  self-retrieval @5    {at_5:.0%}   diagnostic")

    print("\n  weakest alignment (question far from its own document):")
    weak = sorted(
        ((table, own_sims[i], pairs[i][1]) for i, (table, _) in enumerate(pairs)),
        key=lambda row: row[1],
    )[:8]
    for table, sim, question in weak:
        title = loaded.titles[position[table]][:48]
        print(f"    {table:<8} {sim:.3f}  {title}")
        print(f"             {question[:72]}")

    print("\n  worst self-retrieval (own question does not rank first):")
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
    existing["synthetic_alignment"] = round(alignment, 3)
    existing["synthetic_self_retrieval"] = round(at_1, 3)
    existing["synthetic_self_retrieval_at_5"] = round(at_5, 3)
    EVIDENCE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\nWrote {EVIDENCE.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
