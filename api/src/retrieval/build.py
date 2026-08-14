"""Build the search index from cached metadata. Offline, never at request time.

Separate from `index.py` on purpose: this module reaches the OpenAI client and
the loader must not. Output lands in `index_store/` and is shipped as a pinned
release asset.

The two indexes are fed differently, which is the whole design (DESIGN section 6):
BM25 gets every variable label; embeddings get a short dense summary. Feeding
both everything makes each worse at what it is for.

The corpus is also narrowed before either index sees it — one document per table
FAMILY, and no survey-quality tables. Both are Census structure, not tuning:
`B19013A` is `B19013` filtered to Black householders, and `B99053` is an
allocation rate. Together they take 1,458 documents down to 770 and were worth
more than any ranking change measured here.
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from . import availability, embedding, metadata, text
from .bm25 import Bm25
from .index import LEXICAL, SEMANTIC, STORE


def _labels_by_table() -> tuple[dict[str, list[str]], dict[str, str]]:
    """Variable labels and concept, taken from the newest vintage each table has.

    Newest-first so a table still published carries current wording, while one
    discontinued in 2018 keeps its 2018 description rather than disappearing.
    """
    labels: dict[str, list[str]] = {}
    concepts: dict[str, str] = {}
    pairs = [
        (dataset, year)
        for dataset in metadata.DATASETS
        for year in metadata.cached_vintages(dataset)
    ]
    for dataset, year in sorted(pairs, key=lambda pair: -pair[1]):
        grouped: dict[str, list[str]] = defaultdict(list)
        for variable in metadata.variables(dataset, year).values():
            if variable.table_id not in labels:
                grouped[variable.table_id].append(variable.label)
                concepts.setdefault(variable.table_id, variable.concept)
        labels.update(grouped)
    return labels, concepts


def build(
    *,
    with_embeddings: bool = True,
    # Off by default on evidence, against the plan's expectation. Measured
    # 2026-08-14 on the 40-question tuning set: folding six generated questions
    # into the embedded document cost @1 (40% -> 25%) and MRR (0.55 -> 0.47).
    # One vector per question with max-pooling was no better (30%). The
    # questions describe a table accurately and still blur what makes it
    # distinct from its neighbours, which is the whole ranking problem here.
    with_synthetic: bool = False,
    model: str = embedding.DEFAULT_MODEL,
    store: Path = STORE,
) -> dict[str, Any]:
    """Write the artifact. Returns the metadata block it stamped into it."""
    matrix_path = availability.ARTIFACT
    matrix = availability.load(matrix_path) if matrix_path.exists() else availability.build()
    if not matrix_path.exists():
        availability.write(matrix, matrix_path)

    tables = availability.union_tables(matrix)
    labels, concepts = _labels_by_table()

    questions: dict[str, list[str]] = {}
    if with_synthetic:
        from .synthetic import load_questions

        questions = load_questions()

    # One document per FAMILY. The representative is the base table when it
    # exists; a family of iterations whose parent was never published falls
    # back to its first member so the ID we return is always a real table.
    families: dict[str, list[str]] = defaultdict(list)
    for table_id in tables:
        if not metadata.is_subject_table(table_id):
            continue
        families[metadata.family_id(table_id)].append(table_id)
    representatives = {
        base: (base if base in tables else sorted(members)[0]) for base, members in families.items()
    }

    table_ids = [representatives[base] for base in sorted(families)]
    members = {
        representatives[base]: sorted(m for m in families[base] if m != representatives[base])
        for base in sorted(families)
    }

    lexical = [
        text.tokenize(
            text.lexical_document(
                tables[t].title, tables[t].universe, concepts.get(t, ""), labels.get(t, [])
            )
        )
        for t in table_ids
    ]

    store.mkdir(parents=True, exist_ok=True)
    semantic_path = store / SEMANTIC
    if with_embeddings:
        documents = [
            text.semantic_document(
                tables[t].title, tables[t].universe, concepts.get(t, ""), questions.get(t, [])
            )
            for t in table_ids
        ]
        np.savez_compressed(semantic_path, vectors=embedding.embed_texts(documents, model=model))
    elif semantic_path.exists():
        # A BM25-only rebuild must not silently keep yesterday's vectors, or the
        # measured steps measure the wrong thing.
        semantic_path.unlink()

    meta = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tables": len(table_ids),
        "collapsed_members": sum(len(m) for m in members.values()),
        "embedding_model": model if with_embeddings else None,
        "synthetic_questions": sum(len(v) for v in questions.values()) if with_synthetic else 0,
        "vintages": {
            dataset: sorted(int(y) for y in vintages)
            for dataset, vintages in matrix["datasets"].items()
        },
    }
    payload = {
        "tables": table_ids,
        "titles": [tables[t].title for t in table_ids],
        "universes": [tables[t].universe for t in table_ids],
        # Race iterations and PR variants of each representative. Slice 1 reads
        # this to answer "median income for Black households" and to populate
        # alternatives[]; retrieval itself only ever ranks representatives.
        "members": [members[t] for t in table_ids],
        "bm25": Bm25.build(lexical).to_dict(),
        "meta": meta,
    }
    with gzip.open(store / LEXICAL, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return meta
