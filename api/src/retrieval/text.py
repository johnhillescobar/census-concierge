"""Turning Census metadata into text worth indexing.

Two jobs, and the second is the one that matters:

1. Strip vintage tokens. `(in 2023 inflation-adjusted dollars)` appears in every
   income table and says nothing about what the table measures. It pollutes the
   embedding and hands BM25 a year to match on. Bare years elsewhere are left
   alone — "1939 or earlier" in `B25034` is data, not noise.
2. Unpack `!!`-delimited variable labels into readable phrases.
"""

from __future__ import annotations

import re

# Only the inflation parenthetical, never every four-digit number.
_DOLLAR_VINTAGE = re.compile(r"\(in \d{4}[^)]*dollars\)", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")

# Label scaffolding that carries no meaning: every ACS variable begins with one
# of these, so indexing them adds a term to all ~1,300 documents equally.
_LABEL_NOISE = frozenset({"estimate", "annotation of estimate", "margin of error"})


def strip_vintage(text: str) -> str:
    return _DOLLAR_VINTAGE.sub("", text).strip()


def label_phrase(label: str) -> str:
    """`Estimate!!Total:!!Male:!!18 to 24 years` -> `Total Male 18 to 24 years`."""
    parts = [segment.strip().rstrip(":") for segment in label.split("!!")]
    return " ".join(part for part in parts if part and part.lower() not in _LABEL_NOISE)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, crudely singularized."""
    tokens = []
    for word in _WORD.findall(text.lower()):
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        tokens.append(word)
    return tokens


def lexical_document(title: str, universe: str, concept: str, labels: list[str]) -> str:
    """BM25 text: everything, including all variable labels."""
    parts = [title, universe, concept, *(label_phrase(label) for label in labels)]
    return strip_vintage(" ".join(part for part in parts if part))


def semantic_document(title: str, universe: str, concept: str, questions: list[str]) -> str:
    """Embedding text: short and dense. Not the variable labels."""
    header = strip_vintage(title)
    if concept and concept.strip().lower() != title.strip().lower():
        header = f"{header}. {strip_vintage(concept)}"
    if universe:
        header = f"{header}. Universe: {universe}"
    return ". ".join([header, *questions])
