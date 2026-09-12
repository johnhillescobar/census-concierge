#!/usr/bin/env python3
"""Build the retrieval index into `index_store/`. Offline; needs OPENAI_API_KEY.

    python scripts/build_index.py --bm25-only        # step 1, no key needed
    python scripts/build_index.py --no-synthetic     # step 2
    python scripts/build_index.py                    # step 3 and after
    python scripts/build_index.py --generate         # regenerate the questions too

The measured steps in PLAN.md exist so you know which parts you can delete.
Take a number before adding the next thing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from dotenv import load_dotenv  # noqa: E402
from src.retrieval import availability, build, embedding, index, metadata, synthetic  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bm25-only", action="store_true", help="no embeddings, no key needed")
    parser.add_argument(
        "--with-synthetic",
        action="store_true",
        help="fold the generated questions into the embedded document. Measured "
        "WORSE than metadata alone; see the note in build.py.",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="call the LLM for any table whose questions are missing or stale",
    )
    parser.add_argument("--model", default=embedding.DEFAULT_MODEL)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")

    if args.generate:
        matrix_path = availability.ARTIFACT
        matrix = availability.load(matrix_path) if matrix_path.exists() else availability.build()
        availability.write(matrix, matrix_path)
        tables = availability.union_tables(matrix)
        labels, _ = build._labels_by_table()
        print(f"\nGENERATING questions for up to {len(tables)} tables\n")
        synthetic.generate(tables, labels)

    meta = build.build(
        with_embeddings=not args.bm25_only,
        with_synthetic=args.with_synthetic,
        model=args.model,
    )

    print("\nINDEX\n")
    for key in ("tables", "embedding_model", "synthetic_questions", "built_at"):
        print(f"  {key:<20} {meta[key]}")
    for dataset, years in meta["vintages"].items():
        gaps = sorted(set(range(years[0], years[-1] + 1)) - set(years))
        note = f"  (missing {', '.join(map(str, gaps))})" if gaps else ""
        print(f"  {dataset:<20} {years[0]}-{years[-1]}{note}")
    print(f"  {'index_hash':<20} {index.index_hash()}")
    print(f"\nWrote {index.STORE.relative_to(metadata.ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
