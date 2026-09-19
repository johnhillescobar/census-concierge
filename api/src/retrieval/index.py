"""Load the built index and answer `search(question, k)`.

Nothing here builds anything. The artifact is produced offline by `build.py`
and, in production, downloaded into the image as a pinned release asset
(DESIGN section 5). Building at import or at request time would need an API key
at container start and would make every deploy a different index.

The loaded index is cached at module scope. That is the one piece of
module-level state this project sanctions, and only because it is read-only:
there is nothing per-user in it to leak.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .bm25 import Bm25

STORE = Path(os.environ.get("INDEX_STORE", Path(__file__).resolve().parents[3] / "index_store"))
LEXICAL = "lexical.json.gz"
SEMANTIC = "semantic.npz"

# Reciprocal rank fusion, used when more than one ranker is present. Fusing on
# RANK rather than score is deliberate: BM25 magnitudes are unbounded, cosine
# sits in [-1, 1], and any weighting between them would be tuned against 40
# questions.
#
# In practice only one ranker runs. Measured 2026-08-14 on the tuning set,
# equal-weight RRF was worse than embeddings alone on every metric.
# BM25 stays built and unused while semantic.npz exists. Verbatim table-ID
# queries were never scored. See docs/retrieval.md.
RRF_K = 60


@dataclass(frozen=True)
class Index:
    tables: list[str]
    titles: list[str]
    universes: list[str]
    members: list[list[str]]
    bm25: Bm25
    vectors: np.ndarray | None
    meta: dict[str, Any]


_loaded: dict[Path, Index] = {}


def index_hash(store: Path = STORE) -> str:
    """Identifies which index produced a score. Recorded beside every result."""
    digest = hashlib.sha256()
    for name in (LEXICAL, SEMANTIC):
        path = store / name
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def load(store: Path = STORE) -> Index:
    cached = _loaded.get(store)
    if cached is not None:
        return cached

    with gzip.open(store / LEXICAL, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)

    vectors = None
    semantic = store / SEMANTIC
    if semantic.exists():
        vectors = np.load(semantic)["vectors"]

    index = Index(
        tables=payload["tables"],
        titles=payload["titles"],
        universes=payload["universes"],
        members=payload["members"],
        bm25=Bm25.from_dict(payload["bm25"]),
        vectors=vectors,
        meta=payload["meta"],
    )
    _loaded[store] = index
    return index


def _ranked(scores: dict[int, float], limit: int) -> list[int]:
    return [i for i, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:limit]]


def search(question: str, k: int = 5, store: Path = STORE) -> list[str]:
    """Table IDs, best first. The eval harness picks this up by name.

    Ranking only. It does not choose — the agent does that, from these
    candidates and their universes.
    """
    index = load(store)
    depth = max(k * 10, 50)

    rankings: list[list[int]] = []
    if index.vectors is not None:
        from .embedding import embed_query

        similarity = index.vectors @ embed_query(question, index.meta["embedding_model"])
        rankings.append([int(i) for i in np.argsort(-similarity)[:depth]])
    else:
        from .text import tokenize

        rankings.append(_ranked(index.bm25.score(tokenize(question)), depth))

    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            fused[int(doc)] = fused.get(int(doc), 0.0) + 1.0 / (RRF_K + rank)

    return [index.tables[doc] for doc in _ranked(fused, k)]
