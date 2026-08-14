#!/usr/bin/env python3
"""Cache ACS metadata for every vintage in scope. No API key, no cost.

    python scripts/fetch_metadata.py

Idempotent: files already in `data/raw/` are not re-downloaded. Delete the
directory to refresh after an ACS release.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from src.retrieval import metadata  # noqa: E402


def main() -> int:
    found = metadata.fetch_all()
    print("\nMETADATA\n")
    for dataset, years in found.items():
        span = f"{years[0]}-{years[-1]}" if years else "(none)"
        print(f"  {dataset:<6} {len(years):>2} vintages  {span}")
    print(f"\nCached under {metadata.CACHE.relative_to(metadata.ROOT)}\n")
    return 0 if all(found.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
