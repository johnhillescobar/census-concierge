"""CC-121 pre-flight: the restored 2026-10-04 numeric check, prototyped on stored answers.

Measurement only; nothing here is product code and nothing imports from api/src. No regex
and no word lists: whitespace tokens, str.strip, float(). A number written in words or with a
scale word ("two", "2.1 million") is not read as a number; telling the model to write digits is
the model's job, by instruction.

Run from anywhere: uv run python -I evidence/slice-6/cc-121-preflight-check.py
Probe reading: ... cc-121-preflight-check.py probe-nodigits (after collect and judge)
"""

import collections
import contextlib
import json
import sys
import time
from pathlib import Path

EV = Path(__file__).resolve().parent
EDGE = ".,;:!?()[]{}\"'*_`~<>=+$"
ANSWERS = "cc-121-answers-base-fixed.jsonl"
JUDGES = ["cc-121-judged-base-fixed-gpt-4.1.jsonl", "cc-121-judged-base-fixed-gpt-5.5.jsonl"]


def load(name):
    return [json.loads(line) for line in (EV / name).open(encoding="utf-8") if line.strip()]


def words(text):
    for ch in "-–—/|\n":
        text = text.replace(ch, " ")
    return text.split()


def number(tok):
    t = tok.strip(EDGE).rstrip("%").strip(EDGE).replace(",", "")
    try:
        value = float(t)
    except ValueError:
        return None
    return value, (len(t.split(".")[1]) if "." in t else 0)


def numbers(text):
    """(value, decimals) for every token float() reads."""
    return [parsed for tok in words(text) if (parsed := number(tok)) is not None]


def flat(obj):
    """Every string inside nested dicts and lists, space-joined (labels are system text)."""
    if isinstance(obj, dict):
        return " ".join(flat(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(flat(v) for v in obj)
    return "" if obj is None else str(obj)


def allowed(rec):
    vals = set()
    for row in rec["rows"]:
        for key, cell in row.items():
            if key == "GEO_ID" and cell:
                cell = str(cell).split("US")[-1]
            if cell is None:
                continue
            with contextlib.suppress(ValueError):
                vals.add(abs(float(str(cell).replace(",", ""))))
    extra = " ".join(
        [rec.get("universe") or "", *map(str, rec.get("notes") or []), flat(rec.get("labels"))]
    )
    vals.update(abs(value) for value, _d in numbers(extra))
    return vals


def flags(rec):
    """Numeric tokens in the answer that match no allowed value at the precision written."""
    ok = allowed(rec)
    bad = []
    for value, dec in numbers(rec["answer"]):
        value = abs(value)
        if any(abs(round(a, dec) - value) < 1e-9 for a in ok):
            continue
        bad.append(value)
    return bad


def year_like(v):
    return 1900 <= v <= 2100 and v == int(v)


def line_markers(text):
    """Values of tokens that open a line and look like list numbering ("3." or "3)")."""
    out = []
    for line in text.split("\n"):
        parts = line.strip().lstrip("-*• ").split()
        if parts and parts[0][-1:] in ".)" and parts[0][:-1].isdigit():
            out.append(float(parts[0][:-1]))
    return out


def crosstab(label, flagged, verdicts):
    pairs = [(v["verdict"] == "unsupported", f) for v, f in zip(verdicts, flagged, strict=True)]
    print(
        f"  {label}: flags {sum(flagged)}; judge unsupported {sum(u for u, _ in pairs)}; "
        f"both {sum(u and f for u, f in pairs)}; judge only {sum(u and not f for u, f in pairs)}; "
        f"checker only {sum(f and not u for u, f in pairs)}"
    )


def main():
    recs = load(ANSWERS)
    t0 = time.perf_counter()
    res = [flags(r) for r in recs]
    ms = (time.perf_counter() - t0) * 1000
    strict = [bool(f) for f in res]
    old = [any(v >= 100 and not year_like(v) for v in f) for f in res]
    with_rows = sum(bool(r["rows"]) for r in recs)
    print(f"== {ANSWERS}: {len(recs)} answers, {with_rows} with rows; check time {ms:.1f} ms")
    print(
        f"answers with any numeric token {sum(bool(numbers(r['answer'])) for r in recs)}; "
        f"strict flags {sum(strict)}; >=100 non-year flags {sum(old)}"
    )
    print(
        "unmatched tokens by kind",
        dict(
            collections.Counter(
                "year" if year_like(v) else "<100" if v < 100 else ">=100" for f in res for v in f
            )
        ),
    )

    exempt = []
    for r in recs:
        bad = flags(r)
        for m in line_markers(r["answer"]):
            if m in bad:
                bad.remove(m)
        exempt.append(bool(bad))

    unparsed = collections.Counter()
    for r in recs:
        for tok in words(r["answer"]):
            t = tok.strip(EDGE)
            if any(c.isdigit() for c in t) and number(tok) is None:
                unparsed[t if len(t) < 14 else t[:14] + "…"] += 1
    print("digit-bearing tokens float() cannot read (top 25):", unparsed.most_common(25))

    for name in JUDGES:
        verdicts = load(name)
        assert [(a["id"], a["repeat"]) for a in verdicts] == [(a["id"], a["repeat"]) for a in recs]
        print(f"vs {name}")
        crosstab("strict", strict, verdicts)
        crosstab("strict, list markers exempt", exempt, verdicts)
        crosstab(">=100 non-year", old, verdicts)

    for name in JUDGES:
        print(f"\n{name}: judged unsupported, passed by the strict check (first 14 claims):")
        shown = 0
        for r, f, v in zip(recs, strict, load(name), strict=True):
            if v["verdict"] == "unsupported" and not f and shown < 14:
                shown += 1
                claim = v["unsupported"][0]
                text = claim.get("claim") if isinstance(claim, dict) else claim
                print("  ", r["id"], r["repeat"], "|", str(text)[:150])

    rows_per = [len(r["rows"]) for r in recs]
    cells = [sum(1 for row in r["rows"] for k in row if k.endswith("E") and "_" in k) for r in recs]
    print(
        f"\nrows per answer: 0 rows {sum(x == 0 for x in rows_per)}, "
        f"1 row {sum(x == 1 for x in rows_per)}, 2-20 {sum(2 <= x <= 20 for x in rows_per)}, "
        f">20 {sum(x > 20 for x in rows_per)}; "
        f"answers with >20 estimate cells {sum(x > 20 for x in cells)}, max {max(cells)}"
    )

    key = {
        k["sample_id"]: k
        for k in json.loads((EV / "cc-121-handlabel-key.json").read_text(encoding="utf-8"))
    }
    lab = {d["sample_id"]: d["label"] for d in load("cc-121-handlabels.jsonl")}
    files = {
        "baseline": load("cc-121-answers-baseline.jsonl"),
        "after": load("cc-121-answers-after.jsonl"),
    }
    tally = collections.Counter()
    for sid, k in key.items():
        rec = next(r for r in files[k["arm"]] if r["id"] == k["id"] and r["repeat"] == k["repeat"])
        tally[(bool(flags(rec)), lab[sid] == "unsupported")] += 1
    agree = tally[(True, True)] + tally[(False, False)]
    print(
        f"hand labels (30): strict check agrees {agree}/30; "
        f"flagged and unsupported {tally[(True, True)]}; missed {tally[(False, True)]}; "
        f"flagged but ok {tally[(True, False)]}; passed and ok {tally[(False, False)]}"
    )


def probe(label):
    """Digits-only reading of one probe run, beside the repeat-1 slice of the base-fixed run."""
    arms = {
        label: (
            load(f"cc-121-answers-{label}.jsonl"),
            load(f"cc-121-judged-{label}-gpt-4.1.jsonl"),
        ),
        "base-fixed, repeat 1 only": (
            [r for r in load(ANSWERS) if r["repeat"] == 1],
            [v for v in load(JUDGES[0]) if v["repeat"] == 1],
        ),
    }
    for name, (recs, verdicts) in arms.items():
        done = [r for r in recs if "answer" in r]
        flagged = [bool(flags(r)) for r in done]
        figures = [any(not year_like(abs(v)) for v, _d in numbers(r["answer"])) for r in done]
        any_num = [bool(numbers(r["answer"])) for r in done]
        judged = [v for v in verdicts if v["verdict"] in ("ok", "unsupported")]
        secs = sorted(r["latency_s"] for r in done if "latency_s" in r)
        print(f"== {name}: {len(recs)} trials, {len(recs) - len(done)} errored")
        print(f"  strict flags (unmatched numeric token): {sum(flagged)} of {len(done)}")
        print(
            f"  numeric token that is not a year: {sum(figures)}; any numeric token: {sum(any_num)}"
        )
        unsupported = sum(v["verdict"] == "unsupported" for v in judged)
        states = sum(bool(v.get("states_figures")) for v in judged)
        print(
            f"  judge gpt-4.1: unsupported {unsupported} of {len(judged)}; states a figure {states}"
        )
        if secs:
            print(f"  latency s (relative only): p50 {secs[len(secs) // 2]}, max {secs[-1]}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        probe(sys.argv[1])
    else:
        main()
