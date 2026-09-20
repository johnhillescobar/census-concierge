"""Okapi BM25 over ~1,300 documents.

No dependency, because none is warranted at this size: the whole inverted index
is a few hundred thousand postings and a query touches only the terms it
contains. `rank_bm25` would be a dependency to save forty lines.

BM25 is here for what embeddings are bad at — exact table IDs, Census jargon,
and category names that appear in a variable label and nowhere else. `search()`
does not consult it while semantic.npz exists. See docs/retrieval.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

K1 = 1.2  # term-frequency saturation
B = 0.75  # length normalization; the 500-label tables depend on this

# A term in more than this share of documents cannot discriminate between them.
# Dropped from documents and queries alike, which is why it is derived from the
# corpus rather than written as a stopword list: in ACS metadata the useless
# words are "population", "total", "estimate" and "past", not just "the".
#
# Probabilistic IDF alone does not handle this. It floors at zero rather than
# going negative, so a term in 70% of documents still contributes a small
# positive score — and long label-heavy tables collect enough of those to
# outrank the short table that actually answers the question.
MAX_DOCUMENT_FREQUENCY = 0.4


@dataclass(frozen=True)
class Bm25:
    postings: dict[str, list[tuple[int, int]]]
    doc_lengths: list[int]
    stopwords: frozenset[str] = frozenset()

    @property
    def n_docs(self) -> int:
        return len(self.doc_lengths)

    @property
    def average_length(self) -> float:
        return sum(self.doc_lengths) / self.n_docs if self.n_docs else 0.0

    @classmethod
    def build(cls, documents: list[list[str]], max_df: float = MAX_DOCUMENT_FREQUENCY) -> Bm25:
        counted = [cls._counts(tokens) for tokens in documents]
        document_frequency: dict[str, int] = {}
        for counts in counted:
            for token in counts:
                document_frequency[token] = document_frequency.get(token, 0) + 1

        ceiling = max_df * len(documents)
        stopwords = frozenset(t for t, df in document_frequency.items() if df > ceiling)

        postings: dict[str, list[tuple[int, int]]] = {}
        lengths: list[int] = []
        for index, counts in enumerate(counted):
            kept = {t: c for t, c in counts.items() if t not in stopwords}
            # Length is counted AFTER the drop, so normalization compares
            # documents on the terms that still carry signal.
            lengths.append(sum(kept.values()))
            for token, count in kept.items():
                postings.setdefault(token, []).append((index, count))
        return cls(postings=postings, doc_lengths=lengths, stopwords=stopwords)

    @staticmethod
    def _counts(tokens: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        return counts

    def score(self, query: list[str]) -> dict[int, float]:
        """Sparse scores by document index. Absent means zero."""
        scores: dict[int, float] = {}
        average = self.average_length or 1.0
        for token in query:
            if token in self.stopwords:
                continue
            entries = self.postings.get(token)
            if not entries:
                continue
            # Probabilistic IDF, floored: a term in almost every document
            # would otherwise score negative and actively penalize a match.
            idf = max(
                math.log((self.n_docs - len(entries) + 0.5) / (len(entries) + 0.5) + 1.0),
                0.0,
            )
            for index, frequency in entries:
                norm = 1 - B + B * self.doc_lengths[index] / average
                weight = frequency * (K1 + 1) / (frequency + K1 * norm)
                scores[index] = scores.get(index, 0.0) + idf * weight
        return scores

    def to_dict(self) -> dict[str, Any]:
        # Postings become flat [doc, tf, doc, tf, ...] runs: same information,
        # roughly half the JSON, and it decodes without a per-pair allocation.
        return {
            "doc_lengths": self.doc_lengths,
            "stopwords": sorted(self.stopwords),
            "postings": {
                token: [value for pair in entries for value in pair]
                for token, entries in self.postings.items()
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Bm25:
        postings = {
            token: [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
            for token, flat in payload["postings"].items()
        }
        return cls(
            postings=postings,
            doc_lengths=list(payload["doc_lengths"]),
            stopwords=frozenset(payload.get("stopwords", ())),
        )
