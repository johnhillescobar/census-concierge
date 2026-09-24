"""Generate the questions a table answers, so the embedding sees user phrasing."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import metadata

STORE_PATH = metadata.ROOT / "data" / "synthetic_questions.json"
MODEL = "gpt-4o-mini"
PER_TABLE = 6
WORKERS = 12

PROMPT = """You write the questions a US Census table can answer.

Given one American Community Survey table, write {n} short questions a member of \
the public or a non-profit researcher would actually type. They do not know \
Census table numbers or Census wording.

Rules:
- Never mention the table ID, and avoid copying the table's title verbatim.
- Use everyday words for what the table measures.
- Vary the phrasing: some questions plain, some as a researcher would ask.
- Do not invent a place name, a year, or a statistic.
- If the table's universe is narrow (families, renters, veterans, workers), the \
questions must reflect that universe rather than the general population.

Return JSON: {{"questions": ["...", "..."]}}"""


def prompt_hash() -> str:
    return hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()[:12]


def _metadata_hash(title: str, universe: str, labels: list[str]) -> str:
    blob = "|".join([title, universe, *labels])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def load_questions() -> dict[str, list[str]]:
    """Cached questions by table ID. Empty when nothing has been generated."""
    if not STORE_PATH.exists():
        return {}
    payload = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    return {table_id: entry["questions"] for table_id, entry in payload.get("tables", {}).items()}


def _describe(table: metadata.Table, labels: list[str]) -> str:
    from .text import label_phrase, strip_vintage

    shown = [label_phrase(label) for label in labels[:40]]
    return (
        f"Title: {strip_vintage(table.title)}\n"
        f"Universe: {table.universe or 'not published'}\n"
        f"Categories: {'; '.join(filter(None, shown))}"
    )


def generate(
    tables: dict[str, metadata.Table],
    labels: dict[str, list[str]],
    *,
    model: str = MODEL,
    per_table: int = PER_TABLE,
    workers: int = WORKERS,
) -> dict[str, Any]:
    """Fill gaps in the cache and write it back. Returns the full store."""
    from openai import OpenAI

    client = OpenAI()
    store: dict[str, Any] = {"tables": {}}
    if STORE_PATH.exists():
        store = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    cached: dict[str, Any] = store.setdefault("tables", {})
    stamp = prompt_hash()

    stale = [
        table_id
        for table_id, table in tables.items()
        if (entry := cached.get(table_id)) is None
        or entry.get("model") != model
        or entry.get("prompt_hash") != stamp
        or entry.get("metadata_hash")
        != _metadata_hash(table.title, table.universe, labels.get(table_id, []))
    ]

    def one(table_id: str) -> tuple[str, dict[str, Any] | None]:
        table = tables[table_id]
        try:
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": PROMPT.format(n=per_table)},
                    {"role": "user", "content": _describe(table, labels.get(table_id, []))},
                ],
            )
            content = response.choices[0].message.content or "{}"
            questions = [str(q).strip() for q in json.loads(content).get("questions", [])]
        except Exception as error:  # noqa: BLE001 - one bad table must not kill a 1,300-table run
            print(f"  ! {table_id}: {type(error).__name__}: {error}")
            return table_id, None
        if not questions:
            return table_id, None
        return table_id, {
            "model": model,
            "prompt_hash": stamp,
            "metadata_hash": _metadata_hash(table.title, table.universe, labels.get(table_id, [])),
            "questions": questions[:per_table],
        }

    if stale:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for done, (table_id, entry) in enumerate(pool.map(one, stale), start=1):
                if entry is not None:
                    cached[table_id] = entry
                else:
                    # A failed refresh must not leave the old, now-mismatched
                    # entry in place - it would be written back and served as
                    # current. One bad table still must not kill the run, so
                    # drop it rather than abort generate() entirely.
                    cached.pop(table_id, None)
                if done % 100 == 0:
                    print(f"  {done}/{len(stale)}")

    store["tables"] = dict(sorted(cached.items()))
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(store, indent=1, sort_keys=True), encoding="utf-8")
    return store
