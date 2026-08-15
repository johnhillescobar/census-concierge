#!/usr/bin/env python3
"""Run the retrieval model sweep. See PROTOCOL.md — written before any results.

    python experiments/run_sweep.py encoders
    python experiments/run_sweep.py encoders --only openai-3-large,bge-large
    python experiments/run_sweep.py rerankers
    python experiments/run_sweep.py table

Results land in `experiments/results/`. Nothing here writes to
`evidence/latest.json`, `budgets.toml`, or `api/src/`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments import arms, harness  # noqa: E402

BASELINE_ENCODER = "openai-3-large"
CANDIDATE_DEPTH = 10


def run_encoders(only: list[str] | None) -> None:
    body = harness.corpus()
    golden = harness.golden_set()
    self_set = harness.self_retrieval_set(set(body.tables))
    registry = arms.encoders()
    chosen = only or list(registry)

    print(
        f"\nAXIS A - bi-encoders   corpus={len(body.tables)}  "
        f"golden={len(golden.questions)}  self={len(self_set.questions)}\n"
    )

    for key in chosen:
        encoder = registry.get(key)
        if encoder is None:
            print(f"  ?? unknown arm {key}")
            continue
        try:
            documents, doc_seconds = harness.cached_encode(encoder, body.documents, "document")
            record: dict = {
                "arm": key,
                "model": encoder.name,
                "note": encoder.note,
                "params": getattr(encoder, "params", ""),
                "dimensions": int(documents.shape[1]),
                "index_mb": round(documents.nbytes / 1_000_000, 2),
                "corpus_embed_seconds": round(doc_seconds, 1),
                "trust_remote_code": bool(getattr(encoder, "trust_remote_code", False)),
            }
            for query_set in (self_set, golden):
                vectors, seconds = harness.cached_encode(encoder, query_set.questions, "query")
                ranks = harness.ranks_from_scores(
                    vectors @ documents.T, query_set.answers, body.position
                )
                record[query_set.name] = harness.metrics(ranks)
                record[f"{query_set.name}_ranks"] = ranks
                if seconds:
                    record["query_ms"] = round(1000 * seconds / len(query_set.questions), 1)
        except Exception as error:  # noqa: BLE001 - one dead arm must not end the sweep
            print(f"  FAIL {key}: {type(error).__name__}: {error}")
            harness.write(
                f"encoder-{key}", {"arm": key, "error": f"{type(error).__name__}: {error}"}
            )
            continue

        harness.write(f"encoder-{key}", record)
        print(
            f"  {key:<16} self @10={record['self_retrieval']['at_10']:.0%} "
            f"@1={record['self_retrieval']['at_1']:.0%}   "
            f"golden @10={record['golden']['at_10']:.0%} @1={record['golden']['at_1']:.0%}   "
            f"{record['dimensions']}d {record['index_mb']}MB"
        )


def run_rerankers(only: list[str] | None) -> None:
    """Every reranker sees the SAME candidate list, from the baseline encoder."""
    body = harness.corpus()
    golden = harness.golden_set()
    baseline = harness.read(f"encoder-{BASELINE_ENCODER}")
    if baseline is None:
        print(f"Run `encoders --only {BASELINE_ENCODER}` first: rerankers need its candidates.")
        return

    encoder = arms.encoders()[BASELINE_ENCODER]
    documents, _ = harness.cached_encode(encoder, body.documents, "document")
    queries, _ = harness.cached_encode(encoder, golden.questions, "query")
    order = np.argsort(-(queries @ documents.T), axis=1)[:, :CANDIDATE_DEPTH]

    registry = arms.rerankers()
    chosen = only or list(registry)
    ceiling = sum(
        1 for row, table in enumerate(golden.answers) if body.position[table] in order[row].tolist()
    )
    print(f"\nAXIS B - rerankers over a frozen top-{CANDIDATE_DEPTH} from {BASELINE_ENCODER}")
    print(
        f"  candidate ceiling: {ceiling}/{len(golden.questions)} = "
        f"{ceiling / len(golden.questions):.0%}\n"
    )

    for key in chosen:
        reranker = registry.get(key)
        if reranker is None:
            print(f"  ?? unknown arm {key}")
            continue
        ranks: list[int] = []
        try:
            for row, question in enumerate(golden.questions):
                docs = [int(d) for d in order[row]]
                listings = [body.listings[d] for d in docs]
                ordered = reranker.rank(question, listings)
                reordered = [docs[i] for i in ordered]
                want = body.position[golden.answers[row]]
                ranks.append(reordered.index(want) + 1 if want in reordered else 999)
        except Exception as error:  # noqa: BLE001
            print(f"  FAIL {key}: {type(error).__name__}: {error}")
            harness.write(
                f"reranker-{key}", {"arm": key, "error": f"{type(error).__name__}: {error}"}
            )
            continue

        failures = getattr(reranker, "failures", 0)
        record = {
            "arm": key,
            "model": reranker.name,
            "note": reranker.note,
            "candidate_depth": CANDIDATE_DEPTH,
            "ceiling": round(ceiling / len(golden.questions), 4),
            "golden": harness.metrics(ranks),
            "golden_ranks": ranks,
            "failures": failures,
            "last_error": getattr(reranker, "last_error", ""),
        }
        harness.write(f"reranker-{key}", record)
        if failures:
            # An arm that fell back scores like one with no opinion. Say so
            # loudly rather than letting a 404 read as a mediocre model.
            print(
                f"  {key:<16} UNUSABLE - {failures}/{len(golden.questions)} calls failed"
                f"\n                   {record['last_error'][:100]}"
            )
        else:
            print(
                f"  {key:<16} @1={record['golden']['at_1']:.0%}  mrr={record['golden']['mrr']:.2f}"
            )


def table() -> None:
    """The report table, with paired CIs against the pre-registered baseline."""
    base = harness.read(f"encoder-{BASELINE_ENCODER}")
    rows = [harness.read(f"encoder-{k}") for k in arms.encoders()]
    rows = [r for r in rows if r and "error" not in r]
    rows.sort(key=lambda r: -r["self_retrieval"]["at_10"])

    print("\nAXIS A - ranked by self-retrieval @10 (the pre-registered rule)\n")
    print(
        f"  {'arm':<16} {'@10':>6} {'@5':>6} {'@1':>6} {'mrr':>6}  "
        f"{'gold@10':>8} {'gold@1':>7}  {'d@10 vs base [95% CI]':<26} {'dims':>5} {'MB':>6}"
    )
    for row in rows:
        delta = harness.paired_delta(
            row["self_retrieval_ranks"], base["self_retrieval_ranks"], at=10
        )
        mark = "*" if delta["significant"] else " "
        span = f"{delta['delta']:+.3f} [{delta['ci_low']:+.3f},{delta['ci_high']:+.3f}]{mark}"
        s, g = row["self_retrieval"], row["golden"]
        print(
            f"  {row['arm']:<16} {s['at_10']:>6.1%} {s['at_5']:>6.1%} {s['at_1']:>6.1%} "
            f"{s['mrr']:>6.2f}  {g['at_10']:>8.1%} {g['at_1']:>7.1%}  {span:<26} "
            f"{row['dimensions']:>5} {row['index_mb']:>6.1f}"
        )

    # Do the two query sets agree on the ordering? PROTOCOL calls disagreement a
    # finding: the self-retrieval set is the sensitive one but it is generated by
    # gpt-4o-mini, so a low correlation means it is measuring that model's taste
    # rather than retrieval quality.
    if len(rows) > 2:
        primary = np.argsort(np.argsort([-r["self_retrieval"]["at_10"] for r in rows]))
        secondary = np.argsort(np.argsort([-r["golden"]["at_1"] for r in rows]))
        rho = float(np.corrcoef(primary, secondary)[0, 1])
        print(f"\n  self-retrieval @10 vs golden @1, Spearman rho = {rho:+.2f}")

    rerank_rows = [harness.read(f"reranker-{k}") for k in arms.rerankers()]
    dead = [r for r in rerank_rows if r and r.get("failures")]
    rerank_rows = [r for r in rerank_rows if r and "error" not in r and not r.get("failures")]
    if rerank_rows:
        rerank_rows.sort(key=lambda r: -r["golden"]["at_1"])
        print(f"\nAXIS B - ranked by golden @1 over a frozen top-{CANDIDATE_DEPTH}\n")
        print(f"  {'arm':<16} {'@1':>6} {'mrr':>6}  vs ceiling")
        for row in rerank_rows:
            gap = row["golden"]["at_1"] / row["ceiling"] if row["ceiling"] else 0.0
            print(
                f"  {row['arm']:<16} {row['golden']['at_1']:>6.1%} "
                f"{row['golden']['mrr']:>6.2f}  {gap:.0%} of what was reachable"
            )
    for row in dead:
        print(f"  {row['arm']:<16} EXCLUDED - {row['failures']} failed calls, not a score")
    print()


def main() -> int:
    load_dotenv(harness.ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["encoders", "rerankers", "table"])
    parser.add_argument("--only", help="comma-separated arm names")
    args = parser.parse_args()
    only = args.only.split(",") if args.only else None

    if args.stage == "encoders":
        run_encoders(only)
    elif args.stage == "rerankers":
        run_rerankers(only)
    else:
        table()
    return 0


if __name__ == "__main__":
    sys.exit(main())
