"""The two indexes are fed different text, and that is the design.

BM25 gets every variable label; the embedding gets a short dense summary.
Feeding both everything makes each worse at what it is for, so the tests that
matter here are about what each document LEAVES OUT.
"""

from __future__ import annotations

from src.retrieval import text


def test_inflation_parenthetical_is_stripped_but_bare_years_survive() -> None:
    # Every income table carries the parenthetical and it says nothing about
    # what the table measures. A bare year elsewhere is data: B25034 is a
    # distribution OF years, and stripping those would delete the subject.
    assert (
        text.strip_vintage("Median Household Income (in 2023 Inflation-Adjusted Dollars)")
        == "Median Household Income"
    )
    assert text.strip_vintage("Year Structure Built 1939 or earlier") == (
        "Year Structure Built 1939 or earlier"
    )


def test_label_phrase_unpacks_the_hierarchy_and_drops_the_scaffolding() -> None:
    # Every ACS variable label begins with one of these prefixes, so indexing
    # them adds one term to every document equally.
    assert text.label_phrase("Estimate!!Total:!!Male:!!18 to 24 years") == (
        "Total Male 18 to 24 years"
    )
    assert text.label_phrase("Margin of Error!!Total:!!Female:") == "Total Female"


def test_tokenize_agrees_between_document_and_query() -> None:
    # The trailing-s strip is not linguistics, it is agreement: the same rule
    # runs over documents and queries, so "households" in a title matches
    # "household" in a question.
    assert text.tokenize("Households") == text.tokenize("household")
    # Short words keep their s, or "gas" (a heating fuel in B25040) becomes
    # "ga" and stops matching itself. A double s is left alone for the same
    # reason: "business" must not become "busines".
    assert text.tokenize("Gas") == ["gas"]
    assert text.tokenize("Business") == ["business"]
    # What the crude rule does mangle, it mangles on both sides, which is all
    # it has to do: "Veteran Status" and "veteran status" meet at "statu".
    assert text.tokenize("Veteran Status") == ["veteran", "statu"]
    assert text.tokenize("veteran status") == ["veteran", "statu"]


def test_semantic_document_is_title_universe_and_nothing_else() -> None:
    document = text.semantic_document(
        "Means of Transportation to Work",
        "Workers 16 years and over",
        "Means of Transportation to Work",
        [],
    )
    # The concept repeats the title here, so it is dropped rather than doubling
    # the strongest term in the vector.
    assert document == "Means of Transportation to Work. Universe: Workers 16 years and over"
    # Universe is the field that separates households from families from
    # housing units, which is the most common silent wrong answer in this work.
    assert "Universe: Workers 16 years and over" in document


def test_semantic_document_keeps_a_concept_that_says_something_new() -> None:
    document = text.semantic_document("B08301", "Workers 16 years and over", "Commuting", [])
    assert "Commuting" in document


def test_lexical_document_keeps_the_labels_the_semantic_one_drops() -> None:
    labels = ["Estimate!!Total:!!Car, truck, or van - carpooled:!!In a 3-person carpool"]
    lexical = text.lexical_document("Means of Transportation to Work", "Workers", "", labels)
    semantic = text.semantic_document("Means of Transportation to Work", "Workers", "", [])

    # "3-person carpool" appears in a label and in no title anywhere. BM25 is
    # the only ranker that can match it, so it must reach BM25 and must not
    # reach the embedding, where 500 labels average into mush.
    assert "3-person carpool" in lexical
    assert "carpool" not in semantic
