"""Choose one table from the candidates the index ranked.

PLAN slice 0 authorizes a reranker under one condition: `@5` high and `@1` low.
Measured 2026-08-14 on the tuning set that is exactly the shape — `@10` 90%,
`@1` 42% — so the index finds the right table and cannot put it first. What
separates `B25091` from `B25095` is universe and phrasing, which is a reading
task, not a distance in vector space.

Deliberately NOT called from `search()`. `search_tables` calls `choose()` so
the ask loop gets the same pick as `make eval --rerank`. The loader stays free
of the LLM; an empty pool must not reach `candidates[0]`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

# Measured in experiments/ axis B on the golden 40: 77.5% @1 vs 67.5% for
# gpt-4o-mini over the same frozen top-10 pool.
MODEL = "gemini-3.7-flash"

PROMPT = """Pick the ACS table that best answers the question.

Match the UNIVERSE — households, families, population and housing units are \
different denominators and picking the wrong one is the most common error in \
Census work. Prefer the table whose subject IS the question over one that \
crosses that subject with another variable.

When several candidates share a subject, match the TITLE to what the question \
asks — not the narrowest cross-tab unless the question names that breakdown.

Sibling rules (same universe, different table):
- Commute length / how long people travel → "Travel Time to Work" (time bands), \
NOT "Aggregate Travel Time... (in Minutes)" — those are summed minutes, not commute length.
- Households receiving SNAP / food stamps → "Public Assistance Income or Food \
Stamps/SNAP for Households", NOT receipt crossed with age, poverty, disability, \
or income medians.
- What people studied / college major / field of degree → "Total Fields of \
Bachelor's Degrees Reported" or "Field of Bachelor's Degree", NOT enrollment \
or general educational attainment tables.
- When a B and C table both fit, prefer the B table — C tables collapse categories.

Return JSON: {"table": "Bxxxxx"}"""


@dataclass(frozen=True)
class Candidate:
    table_id: str
    title: str
    universe: str


def _pick_table(payload: str) -> str | None:
    try:
        table = json.loads(payload).get("table")
    except (TypeError, json.JSONDecodeError):
        return None
    return table if isinstance(table, str) else None


def _choose_gemini(question: str, listing: str, model: str) -> str | None:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=model,
        contents=f"{PROMPT}\n\nQuestion: {question}\n\nCandidates:\n{listing}",
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _pick_table(response.text or "{}")


def _choose_openai(question: str, listing: str, model: str) -> str | None:
    from openai import OpenAI

    response = OpenAI().chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nCandidates:\n{listing}"},
        ],
    )
    return _pick_table(response.choices[0].message.content or "{}")


def choose(question: str, candidates: list[Candidate], model: str = MODEL) -> str:
    """The chosen table ID, or the top candidate if the model cannot answer."""
    fallback = candidates[0].table_id
    listing = "\n".join(
        f"{c.table_id}: {c.title} | universe: {c.universe or 'not published'}" for c in candidates
    )
    try:
        if model.startswith("gemini"):
            picked = _choose_gemini(question, listing, model)
        else:
            picked = _choose_openai(question, listing, model)
    except Exception:  # noqa: BLE001 - a reranker that fails must not lose the ranking
        return fallback
    # Never invent a table: a hallucinated ID would be a 400 from the Census API
    # that the agent then "fixes" by inventing a different wrong call.
    return picked if picked and any(c.table_id == picked for c in candidates) else fallback
