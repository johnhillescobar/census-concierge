"""Facts about a table, DERIVED from its variable labels — never authored.

The distinction matters. Asked to describe B19131, a person writes "earnings of
two-parent families with children" — and the table's own labels include "Other
family, Female householder, no spouse present." It is not two-parent. A wrong
fact in the index is the exact failure this product exists to prevent, so every
field here is computed from metadata already on disk.

Which fields are worth adding is an empirical question with a rule attached:
synthetic questions were slice 0's biggest regression (@1 40% -> 25%) because
six ways of describing a table describe its neighbours equally well. So a field
earns its place only if it DISCRIMINATES between siblings rather than
describing the topic. `median` vs `bracket distribution` separates B19013 from
B19001; keywords like "income, salary, wealth" apply to both and to five more.
"""

from __future__ import annotations

import re

from src.retrieval import text

_MONEY_BRACKET = re.compile(r"\$[\d,]+ (?:to|or more)|less than \$[\d,]+", re.IGNORECASE)
# Order matters below: "20.0 to 24.9 percent" also matches a naive age pattern,
# which had B25091 (owner cost burden) reporting "counts by age band". Percent
# is tested first and age now requires the word "years".
_PERCENT_BRACKET = re.compile(
    r"\d+(?:\.\d+)? (?:to|percent or more)[^.]{0,24}percent", re.IGNORECASE
)
_AGE_BRACKET = re.compile(r"\d+ (?:to \d+ years|years and over)", re.IGNORECASE)


def statistic_type(labels: list[str]) -> str:
    """What KIND of number this table reports.

    The single most discriminating fact available, and it appears nowhere in the
    embedded text today. B19013 (a median) and B19001 (the bracket distribution
    behind it) share a universe, a topic and nearly a title.
    """
    if not labels:
        return "counts"
    phrases = [text.label_phrase(label) for label in labels]
    joined = " ".join(phrases).lower()
    lead = phrases[0].lower()

    if "median" in lead or joined.count("median") > len(phrases) / 2:
        return "a median" if len(labels) == 1 else "medians by category"
    if "aggregate" in lead:
        return "an aggregate total"
    if "mean" in lead:
        return "a mean"
    if _PERCENT_BRACKET.search(joined):
        return "counts by percentage-of-income band"
    if _MONEY_BRACKET.search(joined):
        return "counts by dollar bracket"
    if _AGE_BRACKET.search(joined) and len(labels) > 4:
        return "counts by age band"
    if re.search(r"\b(19|20)\d{2} (?:to|or)\b", joined):
        return "counts by year band"
    if len(labels) == 1:
        return "a single count"
    return "counts by category"


def dimensions(title: str) -> list[str]:
    """`Sex by Age by Disability Status` -> the three things it is cut by.

    Census titles encode their own cross-tabulation. Splitting it out gives the
    reranker the breakdown as a list rather than as prose it has to parse.
    """
    cleaned = text.strip_vintage(title)
    parts = [p.strip() for p in re.split(r"\bby\b", cleaned) if p.strip()]
    return parts if len(parts) > 1 else []


def facts(table_id: str, title: str, universe: str, labels: list[str]) -> dict[str, object]:
    return {
        "table_id": table_id,
        "title": text.strip_vintage(title),
        "universe": universe or "not published",
        "reports": statistic_type(labels),
        "broken_out_by": dimensions(title)[1:],
        "cells": len(labels),
    }


# Statistic types that actually separate siblings. "counts by category" fits
# 56% of the corpus and separates nothing, so adding it is pure length -- and
# length with no signal is what made the first enriched listing LOSE four
# questions and gain none.
DISCRIMINATING = ("a median", "medians by category", "an aggregate total", "a mean")


def lean_listing(table_id: str, title: str, universe: str, labels: list[str]) -> str:
    """Add the statistic type ONLY when it distinguishes, and nothing else.

    The breakdown is dropped because Census titles already state it -- "Sex by
    Age by Disability Status" needs no restating -- and the cell count is
    dropped because no question is about it.
    """
    row = facts(table_id, title, universe, labels)
    line = f"{table_id}: {row['title']} | universe: {row['universe']}"
    reports = str(row["reports"])
    if reports in DISCRIMINATING or "bracket" in reports or "band" in reports:
        line += f" | reports: {reports}"
    return line


def listing(table_id: str, title: str, universe: str, labels: list[str]) -> str:
    """One candidate as a reranker sees it.

    Today it sees `B19013: Median Household Income | universe: Households` — 12
    words, of which only two separate it from three sibling tables. This adds
    the statistic type and the breakdown, and costs no re-embedding to test
    because the reranker reads text at request time.
    """
    row = facts(table_id, title, universe, labels)
    line = f"{table_id}: {row['title']} | universe: {row['universe']} | reports: {row['reports']}"
    breakdown = row["broken_out_by"]
    if isinstance(breakdown, list) and breakdown:
        line += f" | broken out by: {', '.join(breakdown)}"
    return f"{line} | {row['cells']} cells"


def document(title: str, universe: str, labels: list[str]) -> str:
    """The embedded text variant. Short and discriminating on purpose.

    Deliberately NOT the keywords or the generated questions: both describe the
    topic, and every sibling shares the topic. Length is kept near the current
    document so the comparison is about content, not about size.
    """
    row = facts("", title, universe, labels)
    line = f"{row['title']}. Universe: {row['universe']}. Reports {row['reports']}"
    breakdown = row["broken_out_by"]
    if isinstance(breakdown, list) and breakdown:
        line += f", broken out by {', '.join(breakdown)}"
    return line + "."


def lean_document(title: str, universe: str, labels: list[str]) -> str:
    """Embedded-text variant carrying only the discriminating statistic type.

    The reranker gained nothing from these facts because a generative model
    already infers "median" from a title that says Median. An embedder cannot
    reason -- it compresses to one vector -- so the same fact may matter here
    even though it did not there. Different mechanism, separate test.
    """
    row = facts("", title, universe, labels)
    line = f"{row['title']}. Universe: {row['universe']}"
    reports = str(row["reports"])
    if reports in DISCRIMINATING or "bracket" in reports or "band" in reports:
        line += f". Reports {reports}"
    return line + "."
