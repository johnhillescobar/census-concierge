#!/usr/bin/env python3
"""What is left in the table ID once the shipped folding has taken its share?

    python experiments/run_codes.py
    python experiments/run_codes.py --encoder voyage-4-large

The ID is already the corpus's best feature: `family_id` strips the A-I race
iteration, `is_subject_table` reads the 2-digit subject as 00/98/99, and between
them they took 1,458 documents to 756 and moved @5 more than any model did. This
asks what the remaining fields are worth, and deliberately puts none of them
into the embedded document — that is where four enrichments have now failed.

  1. B vs C prefix, as a tie-break on equal scores
  2. B vs C prefix, as a reason to drop the C document altogether
  3. the 2-digit subject, as a confidence signal beside the margin

Reads cached embeddings. Costs nothing after the first encoder run.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments import arms, harness  # noqa: E402
from experiments.run_margin import auc  # noqa: E402

SUBJECT = re.compile(r"^[BC](\d{2})\d{3}$")


def pre_fold_corpus() -> tuple[list[str], list[str]]:
    """The 756-table corpus, rebuilt from metadata rather than from the index.

    `build.py` now folds the identical twins this experiment exists to measure,
    so reading the corpus out of the built index would leave nothing to compare
    and the arm would silently score zero difference. Rebuilding the pre-fold
    list keeps the experiment reproducible after the decision it informed has
    already shipped — and reproduces the exact text the cache is keyed on.
    """
    sys.path.insert(0, str(harness.ROOT / "api"))
    from src.retrieval import availability, metadata, text

    matrix = availability.load(availability.ARTIFACT)
    published = availability.union_tables(matrix)
    families: dict[str, list[str]] = defaultdict(list)
    for table_id in published:
        if metadata.is_subject_table(table_id):
            families[metadata.family_id(table_id)].append(table_id)

    tables = sorted(base for base in families if base in published)
    documents = [
        text.semantic_document(published[t].title, published[t].universe, "", []) for t in tables
    ]
    return tables, documents


def main() -> int:
    load_dotenv(harness.ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder", default="gemini-001")
    args = parser.parse_args()

    tables, texts = pre_fold_corpus()
    position = {t: i for i, t in enumerate(tables)}
    subject_of = [SUBJECT.match(t).group(1) for t in tables]  # type: ignore[union-attr]

    encoder = arms.encoders()[args.encoder]
    matrix, seconds = harness.cached_encode(encoder, texts, "document")
    if seconds:
        print(f"  (re-embedded {len(texts)} documents in {seconds:.0f}s — cache missed)")

    # Which C tables embed to byte-identical text as a B table with more cells.
    labels = harness._labels_by_table()
    by_text: dict[str, list[int]] = defaultdict(list)
    for i, document in enumerate(texts):
        by_text[document].append(i)
    twin_of: dict[str, str] = {}
    for rows in by_text.values():
        if len(rows) != 2:
            continue
        base = [i for i in rows if tables[i].startswith("B")]
        twin = [i for i in rows if tables[i].startswith("C")]
        if (len(base), len(twin)) == (1, 1) and len(labels.get(tables[base[0]], [])) > len(
            labels.get(tables[twin[0]], [])
        ):
            twin_of[tables[twin[0]]] = tables[base[0]]
    keep = [i for i, t in enumerate(tables) if t not in twin_of]

    print(f"\nTABLE CODES  —  {encoder.name}")
    print(f"  corpus {len(tables)}, of which {len(twin_of)} are C twins of a larger B\n")

    for query_set in (harness.self_retrieval_set(set(tables)), harness.golden_set()):
        vectors, _ = harness.cached_encode(encoder, query_set.questions, "query")
        scores = vectors @ matrix.T
        answers = query_set.answers
        base_ranks = harness.ranks_from_scores(scores, answers, position)
        print(f"==== {query_set.name}  n={len(answers)}")

        # 1. Tie-break. Sorting on (-score, prefix) makes C lose every exact tie.
        prefer_b = np.tile(
            np.array([0 if t.startswith("B") else 1 for t in tables]), (len(answers), 1)
        )
        keyed = np.lexsort((prefer_b, -scores), axis=1)
        tie_ranks = [
            int(np.where(keyed[row] == position[t])[0][0]) + 1 for row, t in enumerate(answers)
        ]

        # 2. Drop the twins. A question whose answer was a dropped C is scored
        #    against its B, which contains every category the C did.
        sub_position = {tables[i]: n for n, i in enumerate(keep)}
        remapped = [twin_of.get(t, t) for t in answers]
        drop_ranks = harness.ranks_from_scores(scores[:, keep], remapped, sub_position)

        for name, ranks in (
            ("plain", base_ranks),
            ("tie-break B>C", tie_ranks),
            ("drop C twins", drop_ranks),
        ):
            m = harness.metrics(ranks)
            line = f"  {name:<16} @10 {m['at_10']:.1%}  @5 {m['at_5']:.1%}  @1 {m['at_1']:.1%}"
            if name != "plain":
                for at in (10, 1):
                    d = harness.paired_delta(ranks, base_ranks, at=at)
                    line += (
                        f"   d@{at} {d['delta']:+.3f} [{d['ci_low']:+.3f},{d['ci_high']:+.3f}]"
                        f"{'*' if d['significant'] else ' '}"
                    )
            print(line)

        # A remapped question is nearly guaranteed to improve, because its answer
        # used to be tied with a twin that is now gone. Only the untouched
        # questions measure "120 fewer distractors" on its own, so split them.
        moved = [i for i, (a, r) in enumerate(zip(answers, remapped, strict=True)) if a != r]
        if moved:
            same = [i for i in range(len(answers)) if i not in set(moved)]
            for label, rows in (("answer was a twin", moved), ("answer untouched", same)):
                before = harness.metrics([base_ranks[i] for i in rows])
                after = harness.metrics([drop_ranks[i] for i in rows])
                d = harness.paired_delta(
                    [drop_ranks[i] for i in rows], [base_ranks[i] for i in rows], at=1
                )
                print(
                    f"    {label:<18} n={len(rows):>3}  @1 {before['at_1']:.1%} -> "
                    f"{after['at_1']:.1%}   d@1 {d['delta']:+.3f} "
                    f"[{d['ci_low']:+.3f},{d['ci_high']:+.3f}]{'*' if d['significant'] else ''}"
                )

        # 3. Subject agreement. Hypothesis was that top-5 spanning several
        #    subjects means the index has not found the topic. Measured below.
        order = np.argsort(-scores, axis=1, kind="stable")
        correct = np.array([o[0] == position[t] for o, t in zip(order, answers, strict=True)])
        agree = np.array(
            [
                float(sum(1 for j in row if subject_of[j] == subject_of[row[0]]))
                for row in order[:, :5]
            ]
        )
        ordered = -np.sort(-scores, axis=1)
        margin = ordered[:, 0] - ordered[:, 1]
        print(f"    subject agreement in top-5   AUC {auc(agree[correct], agree[~correct]):.3f}")
        print(f"    margin (top1 - top2)         AUC {auc(margin[correct], margin[~correct]):.3f}")
        for k in (5, 4, 3, 2, 1):
            hit = agree == k
            if hit.sum() >= 5:
                print(
                    f"      {k}/5 share a subject: {hit.mean():>4.0%} of questions,"
                    f"  top-1 right {correct[hit].mean():.0%}"
                )
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
