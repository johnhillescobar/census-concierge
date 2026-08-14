"""Choose one table from the candidates the index ranked.

PLAN slice 0 authorizes a reranker under one condition: `@5` high and `@1` low.
Measured 2026-08-14 on the tuning set that is exactly the shape — `@10` 90%,
`@1` 42% — so the index finds the right table and cannot put it first. What
separates `B25091` from `B25095` is universe and phrasing, which is a reading
task, not a distance in vector space.

Deliberately NOT called from `search()`. Retrieval ranks; selection is the
agent's job, and in slice 1 this prompt becomes part of what the agent already
does with the candidate list. Keeping it separate means slice 1 can delete this
module rather than unpick an LLM call from inside the loader.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

MODEL = "gpt-4o-mini"

PROMPT = """Pick the ACS table that best answers the question.

Match the UNIVERSE — households, families, population and housing units are \
different denominators and picking the wrong one is the most common error in \
Census work. Prefer the table whose subject IS the question over one that \
crosses that subject with another variable.

Return JSON: {"table": "Bxxxxx"}"""


@dataclass(frozen=True)
class Candidate:
    table_id: str
    title: str
    universe: str


def choose(question: str, candidates: list[Candidate], model: str = MODEL) -> str:
    """The chosen table ID, or the top candidate if the model cannot answer."""
    from openai import OpenAI

    fallback = candidates[0].table_id
    listing = "\n".join(
        f"{c.table_id}: {c.title} | universe: {c.universe or 'not published'}" for c in candidates
    )
    try:
        response = OpenAI().chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": f"Question: {question}\n\nCandidates:\n{listing}"},
            ],
        )
        picked = json.loads(response.choices[0].message.content or "{}").get("table")
    except Exception:  # noqa: BLE001 - a reranker that fails must not lose the ranking
        return fallback
    # Never invent a table: a hallucinated ID would be a 400 from the Census API
    # that the agent then "fixes" by inventing a different wrong call.
    return picked if any(c.table_id == picked for c in candidates) else fallback
