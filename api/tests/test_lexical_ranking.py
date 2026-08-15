"""BM25, and specifically the corpus-derived stopwords.

Probabilistic IDF floors at zero rather than going negative, so a term in most
documents still contributes a small positive score. Label-heavy tables collect
enough of those to outrank the short table that answers the question: before
the `max_df` drop, "population of Harris County" ranked geographic-mobility
tables first, on `the`, `of` and `population`.
"""

from __future__ import annotations

from src.retrieval.bm25 import Bm25

# Five documents. "population" is in four of them and discriminates nothing;
# "broadband", "carpool" and "veteran" each appear once and discriminate
# completely. That asymmetry is the whole point of the module.
CORPUS = [
    ["population", "total", "broadband", "subscription"],
    ["population", "total", "carpool", "commute"],
    ["population", "total", "veteran", "service"],
    ["population", "total", "age", "sex"],
    ["housing", "unit", "tenure"],
]


def test_a_term_in_most_documents_is_dropped_from_the_index() -> None:
    index = Bm25.build(CORPUS)

    # 4 of 5 documents is 80%, over the 40% ceiling.
    assert "population" in index.stopwords
    assert "population" not in index.postings
    # 1 of 5 is 20% and stays.
    assert "broadband" not in index.stopwords


def test_a_stopword_query_scores_nothing_rather_than_scoring_everything() -> None:
    index = Bm25.build(CORPUS)

    assert index.score(["population"]) == {}
    # And a query mixing one of each is decided entirely by the rare term.
    assert list(index.score(["population", "broadband"])) == [0]


def test_document_length_is_measured_after_the_drop() -> None:
    # Two documents share a rare term. The second is padded with a term that
    # every document has. If length were counted before the drop, the padded
    # document would be penalized by length normalization for carrying words
    # that were thrown away.
    padded = ["carpool"] + ["population"] * 20
    index = Bm25.build([["carpool"], padded, ["population"], ["population"], ["population"]])

    scores = index.score(["carpool"])
    assert scores[0] == scores[1]


def test_the_rare_term_outranks_the_common_one() -> None:
    index = Bm25.build(CORPUS)
    scores = index.score(["veteran", "housing"])

    # Document 2 holds "veteran", document 4 holds "housing"; both are rare, so
    # both score, and neither is drowned by a document that merely shares
    # "total" with everything.
    assert set(scores) == {2, 4}


def test_the_serialized_index_scores_identically_to_the_built_one() -> None:
    # The artifact is built offline and shipped; a round-trip that quietly lost
    # the stopword set would make the shipped index behave unlike every number
    # ever recorded from it.
    index = Bm25.build(CORPUS)
    restored = Bm25.from_dict(index.to_dict())

    assert restored.stopwords == index.stopwords
    assert restored.doc_lengths == index.doc_lengths
    for query in (["broadband"], ["carpool", "commute"], ["population"]):
        assert restored.score(query) == index.score(query)
