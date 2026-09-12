#!/usr/bin/env python3
"""Experiment: selector prompt and listing variants for in-pool sibling misses.

Does NOT write to evidence/latest.json or change api/src/retrieval/rerank.py.
Uses the live index pool from search() and gemini-3.7-flash.

    python experiments/prompt_tuning.py
    python experiments/prompt_tuning.py --only sibling_rules --repeat 5 \\
        --json evidence/prompt-tuning-sibling.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT))

from src.retrieval import metadata  # noqa: E402
from src.retrieval.index import load, search  # noqa: E402

from experiments import describe  # noqa: E402

load_dotenv(ROOT / ".env")

POOL = 10
MODEL = "gemini-3.7-flash"
QUESTIONS = ROOT / "evals" / "golden_questions.toml"
FOCUS = ("q11", "q21", "q41")

BASELINE = """Pick the ACS table that best answers the question.

Match the UNIVERSE — households, families, population and housing units are \
different denominators and picking the wrong one is the most common error in \
Census work. Prefer the table whose subject IS the question over one that \
crosses that subject with another variable.

Return JSON: {"table": "Bxxxxx"}"""

SIBLING_RULES = """Pick the ACS table that best answers the question.

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

STATISTIC_HINT = """Pick the ACS table that best answers the question.

Match the UNIVERSE — households, families, population and housing units are \
different denominators and picking the wrong one is the most common error in \
Census work. Prefer the table whose subject IS the question over one that \
crosses that subject with another variable.

Each candidate may include `reports:` — use it. An aggregate total answers \
"how many minutes total" not "how long is the commute"; a distribution by band \
answers commute length; counts by category answer "how many households receive X".

Return JSON: {"table": "Bxxxxx"}"""

COMBINED = SIBLING_RULES.replace(
    "Return JSON:",
    "Each candidate may include `reports:` — prefer distribution/band tables over \
aggregate totals for commute-length questions.\n\nReturn JSON:",
)


@dataclass(frozen=True)
class Variant:
    name: str
    prompt: str
    listing: str  # basic | lean | rich


VARIANTS = (
    Variant("baseline", BASELINE, "basic"),
    Variant("sibling_rules", SIBLING_RULES, "basic"),
    Variant("lean_listing", BASELINE, "lean"),
    Variant("sibling+lean", SIBLING_RULES, "lean"),
    Variant("statistic_hint", STATISTIC_HINT, "lean"),
    Variant("combined", COMBINED, "lean"),
)


def _labels_by_table() -> dict[str, list[str]]:
    from collections import defaultdict

    out: dict[str, list[str]] = {}
    pairs = [(d, y) for d in metadata.DATASETS for y in metadata.cached_vintages(d)]
    for dataset, year in sorted(pairs, key=lambda p: -p[1]):
        grouped: dict[str, list[str]] = defaultdict(list)
        for variable in metadata.variables(dataset, year).values():
            if variable.table_id not in out:
                grouped[variable.table_id].append(variable.label)
        out.update(grouped)
    return out


def _listing(
    kind: str,
    table_id: str,
    title: str,
    universe: str,
    labels: list[str],
) -> str:
    if kind == "lean":
        return describe.lean_listing(table_id, title, universe, labels)
    if kind == "rich":
        return describe.listing(table_id, title, universe, labels)
    return f"{table_id}: {title} | universe: {universe or 'not published'}"


def _choose(question: str, candidates: list[str], prompt: str, model: str = MODEL) -> str | None:
    from google import genai
    from google.genai import types

    listing = "\n".join(candidates)
    client = genai.Client(api_key=__import__("os").environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=model,
        contents=f"{prompt}\n\nQuestion: {question}\n\nCandidates:\n{listing}",
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    try:
        table = json.loads(response.text or "{}").get("table")
    except (TypeError, json.JSONDecodeError):
        return None
    return table if isinstance(table, str) else None


def _golden() -> list[dict]:
    with QUESTIONS.open("rb") as handle:
        return [
            q
            for q in tomllib.load(handle)["question"]
            if q.get("tier") == "long_tail" and q.get("expect_table") and not q.get("holdout")
        ]


def evaluate(variant: Variant, entries: list[dict], index, labels: dict[str, list[str]]) -> dict:
    position = {table: i for i, table in enumerate(index.tables)}
    hits = 0
    in_pool = 0
    rows: list[dict] = []
    for entry in entries:
        question = entry["text"]
        expected = entry["expect_table"]
        raw = search(question, POOL)
        pool = raw[:POOL]
        cands = [
            _listing(
                variant.listing,
                t,
                index.titles[position[t]],
                index.universes[position[t]],
                labels.get(t, []),
            )
            for t in pool
            if t in position
        ]
        picked = _choose(question, cands, variant.prompt)
        ids = [t for t in pool if t in position]
        if picked not in ids:
            picked = ids[0] if ids else None
        ok = picked == expected
        hits += int(ok)
        raw_rank = raw.index(expected) + 1 if expected in raw else None
        if raw_rank is not None:
            in_pool += 1
        rows.append(
            {
                "id": entry["id"],
                "expected": expected,
                "picked": picked,
                "ok": ok,
                "raw_rank": raw_rank,
            }
        )
    n = len(entries)
    focus = {r["id"]: r for r in rows if r["id"] in FOCUS}
    return {
        "variant": variant.name,
        "listing": variant.listing,
        "selector_at_1": round(hits / n, 4) if n else 0.0,
        "retrieval_at_10": round(in_pool / n, 4) if n else 0.0,
        "hits": hits,
        "in_pool": in_pool,
        "n": n,
        "focus": focus,
        "regressions": [r["id"] for r in rows if not r["ok"] and r["id"] not in FOCUS],
    }


def _summarize(runs: list[dict]) -> dict:
    rates = [r["selector_at_1"] for r in runs]
    pools = [r["retrieval_at_10"] for r in runs]
    return {
        "runs": len(runs),
        "selector_at_1_mean": round(sum(rates) / len(rates), 4),
        "selector_at_1_min": min(rates),
        "selector_at_1_max": max(rates),
        "retrieval_at_10_mean": round(sum(pools) / len(pools), 4),
        "retrieval_at_10_min": min(pools),
        "retrieval_at_10_max": max(pools),
        "focus_hits": {
            qid: sum(1 for r in runs if r["focus"][qid]["ok"])
            for qid in FOCUS
            if runs and qid in runs[0]["focus"]
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, help="write full report")
    parser.add_argument("--only", help="comma-separated variant names")
    parser.add_argument("--repeat", type=int, default=1, help="repeat each variant")
    args = parser.parse_args()

    try:
        index = load()
    except FileNotFoundError:
        print("index_store/ not found — run `make index` first", file=sys.stderr)
        return 1

    labels = _labels_by_table()
    entries = _golden()
    chosen = VARIANTS
    if args.only:
        names = {n.strip() for n in args.only.split(",")}
        chosen = tuple(v for v in VARIANTS if v.name in names)

    print(f"\nPROMPT TUNING  model={MODEL}  n={len(entries)}  pool={POOL}  repeat={args.repeat}\n")
    print(f"{'variant':<18} {'run':>3}  {'ret@10':>6}  {'sel@1':>6}  focus q11 q21 q41")

    all_variants: list[dict] = []
    for variant in chosen:
        runs: list[dict] = []
        for run in range(1, args.repeat + 1):
            report = evaluate(variant, entries, index, labels)
            report["run"] = run
            runs.append(report)
            focus = report["focus"]
            marks = " ".join("ok" if focus[q]["ok"] else "MISS" for q in FOCUS if q in focus)
            print(
                f"{variant.name:<18} {run:>3}  "
                f"{report['retrieval_at_10']:>5.0%}  "
                f"{report['selector_at_1']:>5.0%}  {marks}"
            )
        summary = _summarize(runs)
        all_variants.append({"variant": variant.name, "runs": runs, "summary": summary})
        if args.repeat > 1:
            print(
                f"{'':18} avg  "
                f"{summary['retrieval_at_10_mean']:>5.0%}  "
                f"{summary['selector_at_1_mean']:>5.0%}  "
                f"q11={summary['focus_hits'].get('q11', 0)}/{args.repeat} "
                f"q21={summary['focus_hits'].get('q21', 0)}/{args.repeat} "
                f"q41={summary['focus_hits'].get('q41', 0)}/{args.repeat}"
            )

    floors = {"retrieval_at_10_min": 0.90, "selector_at_1_min": 0.70}
    print("\nGATE CHECK (budgets.toml floors on long_tail)")
    for block in all_variants:
        s = block["summary"]
        ret_ok = s["retrieval_at_10_min"] >= floors["retrieval_at_10_min"]
        sel_ok = s["selector_at_1_min"] >= floors["selector_at_1_min"]
        print(
            f"  {block['variant']:<18} ret@10 {s['retrieval_at_10_mean']:.0%} "
            f"({'pass' if ret_ok else 'FAIL'})  "
            f"sel@1 {s['selector_at_1_mean']:.0%} "
            f"[{s['selector_at_1_min']:.0%}-{s['selector_at_1_max']:.0%}] "
            f"({'pass' if sel_ok else 'FAIL'})"
        )

    if args.json:
        out = args.json if args.json.is_absolute() else ROOT / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": MODEL,
            "n": len(entries),
            "pool": POOL,
            "repeat": args.repeat,
            "floors": floors,
            "variants": all_variants,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote {out.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
