#!/usr/bin/env python3
"""Does the top-1/top-2 similarity gap predict whether top-1 is right?

    python experiments/run_margin.py
    python experiments/run_margin.py --encoder voyage-4-large

If it does, the product gets a confidence signal for free — computed from
vectors it already has, before spending an LLM call. That signal is what turns
"similar tables and a vague question" from a coin flip into a deliberate
behaviour: answer with the top hit when the gap is wide, and when it is narrow,
show the neighbours with the reason they differ.

CLAUDE.md forbids blocking clarification questions, so a low-confidence result
must never become "did you mean households or families?". It becomes an answer
plus visible alternatives.

Reads cached embeddings. Costs nothing after the first encoder run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments import arms, harness  # noqa: E402


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """1-based ranks; tied values share the average rank (Mann-Whitney requirement)."""
    order = values.argsort()
    sorted_vals = values[order]
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(sorted_vals):
        end = start
        while end + 1 < len(sorted_vals) and sorted_vals[end + 1] == sorted_vals[start]:
            end += 1
        avg = (start + end + 2) / 2.0
        ranks[order[start : end + 1]] = avg
        start = end + 1
    return ranks


def auc(positive: np.ndarray, negative: np.ndarray) -> float:
    """P(a correct case has a wider margin than an incorrect one).

    0.5 is a coin flip and means the signal is worthless; 1.0 is perfect
    separation. Mann-Whitney U with average ranks for ties — exact cosine ties
    are common in this corpus.
    """
    if not len(positive) or not len(negative):
        return float("nan")
    combined = np.concatenate([positive, negative])
    ranks = _average_ranks(combined)
    rank_sum = ranks[: len(positive)].sum()
    return float(
        (rank_sum - len(positive) * (len(positive) + 1) / 2) / (len(positive) * len(negative))
    )


def signals(scores: np.ndarray) -> dict[str, np.ndarray]:
    """Candidate confidence measures, all computable at request time."""
    ordered = -np.sort(-scores, axis=1)
    return {
        "top1 - top2": ordered[:, 0] - ordered[:, 1],
        "top1 - top5": ordered[:, 0] - ordered[:, 4],
        "top1 - mean(top10)": ordered[:, 0] - ordered[:, :10].mean(axis=1),
        "top1 alone": ordered[:, 0],
    }


def report(name: str, values: np.ndarray, correct: np.ndarray) -> None:
    separation = auc(values[correct], values[~correct])
    print(
        f"\n  {name:<20} AUC {separation:.3f}   n={len(values)}  "
        f"correct={correct.sum()} wrong={(~correct).sum()}"
    )
    if name != "top1 - top2":
        return

    # The operating table: at each cut, how much of the traffic is above it and
    # how often is the top hit right on each side. This is what a threshold
    # would actually buy.
    print(f"    {'cut':>7} {'covered':>9} {'top-1 right above':>19} {'top-1 right below':>19}")
    for q in (0.3, 0.4, 0.5, 0.6, 0.7):
        cut = float(np.quantile(values, q))
        above, below = values >= cut, values < cut
        acc_above = correct[above].mean() if above.any() else float("nan")
        acc_below = correct[below].mean() if below.any() else float("nan")
        print(f"    {cut:>7.4f} {above.mean():>8.0%} {acc_above:>18.0%} {acc_below:>18.0%}")


def main() -> int:
    load_dotenv(harness.ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder", default="gemini-001")
    args = parser.parse_args()

    body = harness.corpus()
    encoder = arms.encoders()[args.encoder]
    documents, _ = harness.cached_encode(encoder, body.documents, "document")
    position = body.position

    print(f"\nMARGIN AS A CONFIDENCE SIGNAL  —  {encoder.name}")
    for query_set in (
        harness.self_retrieval_set(set(body.tables)),
        harness.golden_set(),
    ):
        vectors, _ = harness.cached_encode(encoder, query_set.questions, "query")
        scores = vectors @ documents.T
        chosen = scores.argmax(axis=1)
        correct = np.array([chosen[i] == position[t] for i, t in enumerate(query_set.answers)])
        print(f"\n{'=' * 4} {query_set.name}  (top-1 accuracy {correct.mean():.1%})")
        for name, values in signals(scores).items():
            report(name, values, correct)

    print(
        "\n  AUC 0.5 means the gap tells you nothing. Anything near 0.5 means a\n"
        "  narrow margin is NOT evidence of ambiguity, and the product cannot use\n"
        "  it to decide when to surface alternatives.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
