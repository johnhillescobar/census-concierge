#!/usr/bin/env python3
"""CC-121 instrument: how many answers state a figure the fetched data does not support.

    python scripts/judge_figures.py collect --label baseline --repeat 3
    python scripts/judge_figures.py judge --label baseline

`collect` runs the visible long_tail questions through run_ask and stores each answer
with its rows, universe and warnings (evidence/slice-6/cc-121-answers-<label>.jsonl).
`judge` asks a model whether each stored answer states anything its own data does not
support. Measurement only: the product's own check is digits-only (figures.py); this judge
measures what that check lets through, and nothing here parses the answer text. Needs
OPENAI_API_KEY and CENSUS_API_KEY.
"""

# ruff: noqa: E501  (the judge prompt is one literal)
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "golden_questions.toml"
OUT = ROOT / "evidence" / "slice-6"
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "api"))

JUDGE = """You check an answer written for a Census data tool against the data it was written from. FACTS holds the fetched rows (E is an estimate, M its 90% margin of error), the label of each variable for each year (a label can name its own year's dollars), the universe, and system notes. ANSWER is the written text. List each statement in ANSWER that presents a quantity, share, ranking, trend or comparison, in any form (digits, words, abbreviations, 'about', 'roughly'), that FACTS does not support for the same place, variable and year. A statement is supported when FACTS holds that quantity, even rounded or reworded. Anything computed from the data (a sum, share, average, difference, rank or trend) is unsupported unless FACTS states it. A figure attached to the wrong variable or place is unsupported. Years, table IDs and statements with no quantity are fine. Reply with JSON only: {"states_figures": true or false, "unsupported": [{"claim": "quoted text", "why": "short reason"}]}."""
KEEP = ("NAME", "GEO_ID", "year")


def questions() -> list[dict[str, Any]]:
    entries = tomllib.loads(QUESTIONS.read_text(encoding="utf-8"))["question"]
    return [q for q in entries if q.get("tier") == "long_tail" and not q.get("holdout")]


def labels(dataset: str, year: int) -> dict[str, str]:
    from src.retrieval import metadata

    try:
        return {k: v.label for k, v in metadata.variables(dataset, year).items()}
    except Exception:  # noqa: BLE001 - a missing or corrupt cache must not stop the run
        return {}


async def collect(label: str, repeat: int, limit: int, workers: int, answer_model: str) -> None:
    from src import ask
    from src.ask import run_ask

    ask.MODEL = answer_model or ask.MODEL  # this process only; the product's constant is unchanged

    gate = asyncio.Semaphore(workers)
    out = OUT / f"cc-121-answers-{label}.jsonl"
    if out.exists():
        raise SystemExit(
            f"{out} exists; use a new --label (a finished run is evidence, not scratch)"
        )
    todo = [(q, r) for r in range(1, repeat + 1) for q in questions()[: limit or None]]

    async def one(q: dict[str, Any], r: int) -> dict[str, Any]:
        async with gate:
            started = time.perf_counter()
            try:
                got = await run_ask(q["text"])
            except Exception as exc:  # noqa: BLE001 - one trial must not stop the run
                return {"id": q["id"], "repeat": r, "error": type(exc).__name__}
        rows = [
            {k: v for k, v in row.items() if k in KEEP or k[-1] in "EM" and "_" in k}
            for row in got.rows
        ]
        notes = [w.detail for w in got.warnings]
        seconds = round(time.perf_counter() - started, 2)
        names = {
            int(y): labels(got.plan.dataset, int(y))
            for y in {r["year"] for r in rows if "year" in r}
        }
        used = {
            y: {k: n[k] for row in rows if str(row.get("year")) == str(y) for k in row if k in n}
            for y, n in names.items()
        }
        return {"id": q["id"], "repeat": r, "text": q["text"], "answer": got.answer, "rows": rows,
                "labels": used, "universe": got.universe, "notes": notes,
                "answer_model": ask.MODEL, "latency_s": seconds}  # fmt: skip

    failed = 0
    with out.open("w", encoding="utf-8") as handle:
        for done in asyncio.as_completed([one(q, r) for q, r in todo]):
            trial = await done
            failed += "error" in trial
            handle.write(json.dumps(trial) + "\n")
            handle.flush()
    print(f"wrote {out}: {len(todo)} trials, {failed} errored")


async def judge(label: str, model: str, workers: int) -> None:
    from openai import AsyncOpenAI

    path = OUT / f"cc-121-judged-{label}-{model}.jsonl"
    if path.exists():
        raise SystemExit(f"{path} exists; use a new --label (a finished run is evidence)")
    client, gate = AsyncOpenAI(), asyncio.Semaphore(workers)
    trials = [
        json.loads(line) for line in (OUT / f"cc-121-answers-{label}.jsonl").open(encoding="utf-8")
    ]

    async def one(t: dict[str, Any]) -> dict[str, Any]:
        if "answer" not in t:
            return {**t, "verdict": "no_answer"}
        facts = {k: t[k] for k in ("rows", "labels", "universe", "notes")}
        user = json.dumps({"facts": facts, "answer": t["answer"]})
        async with gate:
            try:
                reply = await client.chat.completions.create(
                    model=model,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": JUDGE},
                        {"role": "user", "content": user},
                    ],
                )
                found = json.loads(reply.choices[0].message.content or "{}")
                bad = found["unsupported"]
                assert isinstance(bad, list)
            except Exception as exc:  # noqa: BLE001 - count it, never score it as supported
                return {**t, "verdict": "judge_error", "why": type(exc).__name__}
        return {**t, "verdict": "unsupported" if bad else "ok", "unsupported": bad,
                "states_figures": bool(found.get("states_figures"))}  # fmt: skip

    scored = await asyncio.gather(*(one(t) for t in trials))
    path.write_text("".join(json.dumps(s) + "\n" for s in scored), encoding="utf-8")
    judged = [s for s in scored if s["verdict"] in ("ok", "unsupported")]
    bad = [s for s in judged if s["verdict"] == "unsupported"]
    withrows = [s for s in judged if s["rows"]]
    print(f"label={label} model={model} trials={len(scored)} judged={len(judged)}")
    print(f"unsupported={len(bad)}/{len(judged)} ({len(bad) / max(1, len(judged)):.1%}); "
          f"with rows={sum(s in bad for s in withrows)}/{len(withrows)}; "
          f"judge_errors={sum(s['verdict'] == 'judge_error' for s in scored)}; "
          f"no_answer={sum(s['verdict'] == 'no_answer' for s in scored)}")  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["collect", "judge"])
    parser.add_argument("--label", required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="first N questions (smoke test)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model", default="gpt-4.1", help="judge model")
    parser.add_argument("--answer-model", default="", help="collect: model that writes the answers")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "collect":
        asyncio.run(collect(args.label, args.repeat, args.limit, args.workers, args.answer_model))
    else:
        asyncio.run(judge(args.label, args.model, args.workers))


if __name__ == "__main__":
    main()
