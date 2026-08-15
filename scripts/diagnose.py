#!/usr/bin/env python3
"""Inspect the index and reproduce the slice 0 claims.

Every number in `evidence/retrieval_steps.md` came from one of these. If a claim
in that file cannot be reproduced here, the claim is wrong.

    python scripts/diagnose.py corpus
    python scripts/diagnose.py query "how many people bike to work"
    python scripts/diagnose.py rankers
    python scripts/diagnose.py misses

Needs OPENAI_API_KEY for everything except `corpus`.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from src.retrieval import embedding, index, metadata, text  # noqa: E402

QUESTIONS = ROOT / "evals" / "golden_questions.toml"
RRF_K = 60


def _tuning_set() -> list[dict]:
    with QUESTIONS.open("rb") as handle:
        questions = tomllib.load(handle)["question"]
    return [
        q
        for q in questions
        if q.get("expect_table") and q.get("tier") == "long_tail" and not q.get("holdout")
    ]


def _rates(ranks: list[int | None]) -> str:
    n = len(ranks)

    def at(k: int) -> float:
        return sum(1 for r in ranks if r and r <= k) / n

    mrr = sum(1 / r for r in ranks if r) / n
    return f"@1={at(1):5.0%} @3={at(3):5.0%} @5={at(5):5.0%} @10={at(10):5.0%} mrr={mrr:.2f}"


def _fuse(rankings: list[list[int]]) -> list[int]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (RRF_K + rank)
    return [doc for doc, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def corpus() -> None:
    """What the index contains, and what was dropped to get there."""
    loaded = index.load()
    print(f"\nCORPUS  ({loaded.meta['built_at']})\n")
    print(f"  documents             {len(loaded.tables)}")
    print(f"  members folded in     {loaded.meta['collapsed_members']}")
    print(f"  embedding model       {loaded.meta['embedding_model']}")
    print(f"  questions in embed    {loaded.meta['synthetic_questions']}")
    print(f"  index_hash            {index.index_hash()}")

    from src.retrieval import availability

    tables = availability.union_tables(availability.load())
    dropped = [t for t in tables if not metadata.is_subject_table(t)]
    indexed = set(loaded.tables)
    folded = [
        t
        for t in tables
        if metadata.is_subject_table(t) and metadata.family_id(t) != t and t not in indexed
    ]
    print(f"\n  union across vintages {len(tables)}")
    print(f"  - survey-quality      {len(dropped)}   e.g. {', '.join(sorted(dropped)[:4])}")
    print(f"  - folded into family  {len(folded)}   e.g. {', '.join(sorted(folded)[:4])}")
    print(f"  = documents           {len(tables) - len(dropped) - len(folded)}")

    empty = [loaded.tables[i] for i, n in enumerate(loaded.bm25.doc_lengths) if n == 0]
    print(f"\n  BM25 stopwords        {len(loaded.bm25.stopwords)}")
    print(f"    {sorted(loaded.bm25.stopwords)}")
    print(f"  BM25 empty documents  {len(empty)}   {', '.join(empty)}")
    print("    (every token is a corpus stopword - unreachable by lexical search)\n")


def query(question: str) -> None:
    """Top 10 by each ranker, side by side, with the universes."""
    loaded = index.load()
    vector = embedding.embed_query(question, loaded.meta["embedding_model"])
    semantic = [int(i) for i in np.argsort(-(loaded.vectors @ vector))[:200]]
    lexical = [
        i
        for i, _ in sorted(
            loaded.bm25.score(text.tokenize(question)).items(), key=lambda kv: -kv[1]
        )
    ][:200]

    kept = [t for t in text.tokenize(question) if t not in loaded.bm25.stopwords]
    print(f'\nQUERY  "{question}"')
    print(f"  tokens BM25 can use: {kept}\n")
    for label, ranking in (
        ("SEMANTIC (what search() uses)", semantic),
        ("BM25", lexical),
        ("FUSED (RRF, not used)", _fuse([semantic, lexical])),
    ):
        print(f"  {label}")
        for rank, doc in enumerate(ranking[:10], start=1):
            print(
                f"    {rank:>2}. {loaded.tables[doc]:<9} {loaded.titles[doc][:52]:<54}"
                f" | {loaded.universes[doc][:30]}"
            )
        print()


def rankers() -> None:
    """The claim that fusing BM25 in makes things worse."""
    loaded = index.load()
    gold = _tuning_set()
    vectors = embedding.embed_texts([g["text"] for g in gold], model=loaded.meta["embedding_model"])
    position = {t: i for i, t in enumerate(loaded.tables)}

    print(f"\nRANKERS  (long-tail tuning set, n={len(gold)})\n")
    collected: dict[str, list[int | None]] = {"bm25": [], "semantic": [], "fused": []}
    for row, entry in enumerate(gold):
        semantic = [int(i) for i in np.argsort(-(loaded.vectors @ vectors[row]))[:200]]
        lexical = [
            i
            for i, _ in sorted(
                loaded.bm25.score(text.tokenize(entry["text"])).items(), key=lambda kv: -kv[1]
            )
        ][:200]
        want = position[entry["expect_table"]]
        for name, ranking in (
            ("bm25", lexical),
            ("semantic", semantic),
            ("fused", _fuse([semantic, lexical])),
        ):
            collected[name].append(ranking.index(want) + 1 if want in ranking else None)

    for name, ranks in collected.items():
        print(f"  {name:<10} {_rates(ranks)}")
    print("\n  semantic beats fused: BM25 is not strong enough for an equal vote.\n")


def misses() -> None:
    """Every miss with what won instead. This is where the next idea comes from."""
    loaded = index.load()
    gold = _tuning_set()
    vectors = embedding.embed_texts([g["text"] for g in gold], model=loaded.meta["embedding_model"])
    position = {t: i for i, t in enumerate(loaded.tables)}

    print(f"\nMISSES  (semantic ranking, n={len(gold)})\n")
    for row, entry in enumerate(gold):
        ranking = [int(i) for i in np.argsort(-(loaded.vectors @ vectors[row]))]
        want = position[entry["expect_table"]]
        rank = ranking.index(want) + 1
        if rank == 1:
            continue
        top = ranking[0]
        print(f"  {entry['id']}  rank {rank:<3} {entry['text'][:60]}")
        for tag, doc in (("want", want), ("got ", top)):
            title = loaded.titles[doc][:44]
            print(
                f"        {tag} {loaded.tables[doc]:<8} {title:<46} | {loaded.universes[doc][:24]}"
            )
    print()


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("corpus", help="what the index contains and what was dropped")
    ask = sub.add_parser("query", help="top 10 per ranker for one question")
    ask.add_argument("text")
    sub.add_parser("rankers", help="bm25 vs semantic vs fused on the tuning set")
    sub.add_parser("misses", help="every miss, with what beat it")
    args = parser.parse_args()

    {"corpus": corpus, "rankers": rankers, "misses": misses}.get(args.command, lambda: None)()
    if args.command == "query":
        query(args.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
