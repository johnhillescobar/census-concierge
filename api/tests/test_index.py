"""Loading a built index and ranking against it.

No keys and no network: with no `semantic.npz` in the store, `search()` ranks on
BM25, which is enough to prove the loader, the fusion and the k limit behave.
The embedding path is measured by `scripts/eval_retrieval.py`, which needs a key
and is not a unit test.

The fixture corpus is five tables on five subjects with no shared vocabulary.
A fake that returned the same table for every question would pass a test built
on one document; it cannot pass one built on five.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from src.retrieval import index, text
from src.retrieval.bm25 import Bm25

TABLES = [
    ("B08301", "Means of Transportation to Work", "Workers 16 years and over", "bicycle carpool"),
    ("B19013", "Median Household Income", "Households", "income earnings"),
    ("B21001", "Sex by Age by Veteran Status", "Civilian population", "veteran military"),
    ("B25014", "Tenure by Occupants per Room", "Occupied housing units", "crowding occupants"),
    ("B28002", "Types of Internet Subscriptions", "Households", "broadband subscription"),
]


@pytest.fixture
def store(tmp_path: Path) -> Path:
    documents = [
        text.tokenize(text.lexical_document(title, universe, "", [labels]))
        for _, title, universe, labels in TABLES
    ]
    payload = {
        "tables": [t for t, _, _, _ in TABLES],
        "titles": [title for _, title, _, _ in TABLES],
        "universes": [universe for _, _, universe, _ in TABLES],
        "members": [[] for _ in TABLES],
        "bm25": Bm25.build(documents).to_dict(),
        "meta": {"tables": len(TABLES), "embedding_model": None},
    }
    with gzip.open(tmp_path / index.LEXICAL, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)
    index._loaded.pop(tmp_path, None)
    return tmp_path


def test_different_questions_reach_different_tables(store: Path) -> None:
    assert index.search("bicycle carpool commute", k=1, store=store) == ["B08301"]
    assert index.search("broadband subscription", k=1, store=store) == ["B28002"]
    assert index.search("veteran military service", k=1, store=store) == ["B21001"]


def test_candidates_come_back_in_score_order_not_corpus_order(store: Path) -> None:
    # "household" is the universe of both B19013 (row 1) and B28002 (row 4), so
    # both score; only B28002 also matches "broadband" and "subscription".
    # Ranking by row index instead of by score would put B19013 first and look
    # correct on any single-match question — this is the one that catches it.
    ranked = index.search("broadband subscription household", k=5, store=store)
    assert ranked[0] == "B28002"
    assert ranked.index("B28002") < ranked.index("B19013")


def test_k_bounds_the_candidate_list(store: Path) -> None:
    # The agent selects from these; the list is a budget, not a suggestion.
    assert len(index.search("household income", k=3, store=store)) <= 3
    assert index.search("household income", k=0, store=store) == []


def test_a_question_matching_nothing_returns_nothing_rather_than_guessing(store: Path) -> None:
    # Ranking with no evidence is where a wrong table gets presented as an
    # answer. Better an empty candidate list the agent can report on.
    assert index.search("zzzz nonexistent vocabulary", k=5, store=store) == []


def test_the_loaded_index_is_cached_per_store(store: Path) -> None:
    # Read-only module state, sanctioned because there is nothing per-user in
    # it. Two loads of one store must not re-read and re-parse the artifact.
    assert index.load(store) is index.load(store)


def test_the_index_hash_changes_when_the_artifact_does(store: Path, tmp_path: Path) -> None:
    # Every recorded score carries this hash. A score whose index you cannot
    # identify is not evidence.
    before = index.index_hash(store)
    assert before == index.index_hash(store)

    other = tmp_path / "other"
    other.mkdir()
    with gzip.open(other / index.LEXICAL, "wt", encoding="utf-8") as handle:
        json.dump({"tables": []}, handle)
    assert index.index_hash(other) != before
