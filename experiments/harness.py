"""Shared machinery: one corpus, two query sets, caching, and paired statistics.

Every arm sees byte-identical inputs from here. Document text is regenerated
from metadata rather than read out of a built index, so no arm can inherit a
corpus that another arm did not see.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from src.retrieval import index, text  # noqa: E402
from src.retrieval.synthetic import load_questions  # noqa: E402

CACHE = Path(__file__).resolve().parent / "cache"
RESULTS = Path(__file__).resolve().parent / "results"
QUESTIONS = ROOT / "evals" / "golden_questions.toml"

SELF_RETRIEVAL_SAMPLE = 600
SEED = 20260814
BOOTSTRAP = 10_000


@dataclass(frozen=True)
class Corpus:
    tables: list[str]
    documents: list[str]
    listings: list[str]  # "B19013: Title | universe: Households" — for rerankers
    rich_listings: list[str]  # the same, plus derived statistic type and breakdown
    lean_listings: list[str]  # statistic type only where it discriminates
    rich_documents: list[str]  # embedded-text variant carrying the same facts
    lean_documents: list[str]  # embedded text + discriminating statistic type only
    twin_documents: list[str]  # plain, plus detail level only where texts collide

    @property
    def position(self) -> dict[str, int]:
        return {table: i for i, table in enumerate(self.tables)}


@dataclass(frozen=True)
class QuerySet:
    name: str
    questions: list[str]
    answers: list[str]  # expected table id, parallel to questions


def _labels_by_table() -> dict[str, list[str]]:
    """Variable labels from the newest vintage each table appears in."""
    from collections import defaultdict

    from src.retrieval import metadata

    out: dict[str, list[str]] = {}
    pairs = [(d, y) for d in metadata.DATASETS for y in metadata.cached_vintages(d)]
    for dataset, year in sorted(pairs, key=lambda p: -p[1]):
        grouped: dict[str, list[str]] = defaultdict(list)
        for variable in metadata.variables(dataset, year).values():
            if variable.table_id not in out:
                grouped[variable.table_id].append(variable.label)
        out.update(grouped)
    return out


def corpus() -> Corpus:
    from experiments import describe

    loaded = index.load()
    labels = _labels_by_table()
    documents = [
        text.semantic_document(loaded.titles[i], loaded.universes[i], "", [])
        for i in range(len(loaded.tables))
    ]
    listings = [
        f"{loaded.tables[i]}: {loaded.titles[i]} | universe: "
        f"{loaded.universes[i] or 'not published'}"
        for i in range(len(loaded.tables))
    ]
    rich_listings = [
        describe.listing(
            loaded.tables[i],
            loaded.titles[i],
            loaded.universes[i],
            labels.get(loaded.tables[i], []),
        )
        for i in range(len(loaded.tables))
    ]
    lean_listings = [
        describe.lean_listing(
            loaded.tables[i],
            loaded.titles[i],
            loaded.universes[i],
            labels.get(loaded.tables[i], []),
        )
        for i in range(len(loaded.tables))
    ]
    rich_documents = [
        describe.document(loaded.titles[i], loaded.universes[i], labels.get(loaded.tables[i], []))
        for i in range(len(loaded.tables))
    ]
    lean_documents = [
        describe.lean_document(
            loaded.titles[i], loaded.universes[i], labels.get(loaded.tables[i], [])
        )
        for i in range(len(loaded.tables))
    ]
    twin_documents = describe.twin_aware_documents(
        list(loaded.tables), list(loaded.titles), list(loaded.universes), labels
    )
    return Corpus(
        tables=list(loaded.tables),
        documents=documents,
        listings=listings,
        rich_listings=rich_listings,
        lean_listings=lean_listings,
        rich_documents=rich_documents,
        lean_documents=lean_documents,
        twin_documents=twin_documents,
    )


def golden_set() -> QuerySet:
    with QUESTIONS.open("rb") as handle:
        rows = tomllib.load(handle)["question"]
    picked = [
        q
        for q in rows
        if q.get("expect_table") and q.get("tier") == "long_tail" and not q.get("holdout")
    ]
    return QuerySet("golden", [q["text"] for q in picked], [q["expect_table"] for q in picked])


def self_retrieval_set(known: set[str]) -> QuerySet:
    """The generated questions, sampled with the same seed score_synthetic uses."""
    pairs = [
        (table, question)
        for table, items in load_questions().items()
        for question in items
        if table in known
    ]
    random.Random(SEED).shuffle(pairs)
    pairs = pairs[:SELF_RETRIEVAL_SAMPLE]
    return QuerySet("self_retrieval", [q for _, q in pairs], [t for t, _ in pairs])


def _slug(name: str) -> str:
    return name.replace("/", "__").replace(":", "_")


def cached_encode(encoder, texts: list[str], kind: str) -> tuple[np.ndarray, float]:
    """Embed, or reuse a cached matrix keyed on the exact text list.

    Keying on a hash of the joined texts means a changed corpus can never be
    silently scored against a stale matrix.
    """
    from experiments.arms import timed

    # Length-prefixed so two different text lists cannot hash the same. A plain
    # join lets ["ab", "c"] and ["a", "bc"] collide.
    blob = "".join(f"{len(t)}:{t}" for t in texts)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    path = CACHE / f"{_slug(encoder.name)}-{kind}-{digest}.npy"
    if path.exists():
        cached = np.load(path)
        if cached.shape[0] == len(texts):
            return cached, 0.0
        # A truncated matrix was cached by an earlier broken run. The key covers
        # the inputs, which cannot detect an encoder that returned too few rows,
        # so the row count is checked on the way in AND on the way out.
        path.unlink()

    matrix, seconds = timed(encoder.encode, texts, kind)
    if matrix.shape[0] != len(texts):
        raise RuntimeError(
            f"{encoder.name} returned {matrix.shape[0]} vectors for {len(texts)} {kind} texts"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, matrix)
    return matrix, seconds


def ranks_from_scores(
    scores: np.ndarray, answers: list[str], position: dict[str, int]
) -> list[int]:
    """1-indexed rank of the correct table for each query row."""
    # Stable sort: 32% of documents have an exact twin, so ties are common and
    # an unstable sort made rank-1 disagree with argmax on one golden question.
    order = np.argsort(-scores, axis=1, kind="stable")
    out: list[int] = []
    for row, table in enumerate(answers):
        out.append(int(np.where(order[row] == position[table])[0][0]) + 1)
    return out


def metrics(ranks: list[int]) -> dict[str, float]:
    n = len(ranks)
    return {
        "n": n,
        "at_1": round(sum(1 for r in ranks if r <= 1) / n, 4),
        "at_3": round(sum(1 for r in ranks if r <= 3) / n, 4),
        "at_5": round(sum(1 for r in ranks if r <= 5) / n, 4),
        "at_10": round(sum(1 for r in ranks if r <= 10) / n, 4),
        "mrr": round(sum(1 / r for r in ranks) / n, 4),
    }


def paired_delta(
    arm: list[int], baseline: list[int], at: int = 10, seed: int = SEED
) -> dict[str, float]:
    """Bootstrap CI on the difference in hit-rate@`at`, resampling QUESTIONS.

    Paired: both arms answered the same questions, so the pairing is real
    information and throwing it away by comparing two independent rates costs
    most of the sensitivity this sweep needs.
    """
    if len(arm) != len(baseline):
        # Pairing is the whole point. Two arms scored on different question
        # counts cannot be paired, and silently truncating would invent a
        # comparison that was never run.
        raise ValueError(
            f"cannot pair {len(arm)} questions against {len(baseline)}: "
            "a sampled arm is only comparable to another arm at the same n"
        )
    a = np.array([1.0 if r <= at else 0.0 for r in arm])
    b = np.array([1.0 if r <= at else 0.0 for r in baseline])
    observed = float(a.mean() - b.mean())

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(BOOTSTRAP, len(a)))
    deltas = a[idx].mean(axis=1) - b[idx].mean(axis=1)
    low, high = np.percentile(deltas, [2.5, 97.5])
    return {
        "delta": round(observed, 4),
        "ci_low": round(float(low), 4),
        "ci_high": round(float(high), 4),
        "significant": bool(low > 0 or high < 0),
    }


def write(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def read(name: str) -> dict | None:
    path = RESULTS / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
