"""Adversarial probes of the answer-figures check (CC-121), run against the code as committed.

Each probe feeds `figures.checked` or `take_chart` one input and prints what happened, with a
verdict against what a researcher would want:

    HELD            the check did what it should
    DEFECT          a figure the response does not carry passed unchecked (a silent wrong answer)
    FALSE-POSITIVE  text that states only what the response carries was replaced
    GAP             a known limit of a digits-only check (owner decision); named, not solved
    OBSERVATION     behaviour worth knowing, neither right nor wrong

Seeded rows only; no model, no network, no key. From the repository root:

    uv run python -B -X utf8 evidence/slice-6/gate1-probes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "api"), str(ROOT / "api" / "tests")]

import test_figures as seed  # noqa: E402
from src import figures  # noqa: E402
from src.contract import take_chart  # noqa: E402
from src.vintages import REASON_GAP_2020  # noqa: E402

COOK, DUPAGE = seed.COOK, seed.DUPAGE
tally: dict[str, int] = {}


def say(pid: str, verdict: str, what: str, outcome: str) -> None:
    tally[verdict] = tally.get(verdict, 0) + 1
    print(f"PROBE {pid:<4} {verdict:<14} {what}  ->  {outcome}")


def check(
    pid: str, prose: str, *, flag: bool, known: str = "", rows: Any = None, record: Any = None
) -> None:
    """flag=True: the text states a number the response does not carry, so it must be replaced."""
    rows = [COOK, DUPAGE] if rows is None else rows
    answer, problem = figures.checked(prose, rows, record or seed._record())
    replaced = bool(problem)
    if replaced == flag:
        verdict = "HELD"
    elif known:
        verdict = known
    else:
        verdict = "DEFECT" if flag else "FALSE-POSITIVE"
    say(pid, verdict, repr(prose), "replaced" if replaced else "kept as written")


def section(title: str) -> None:
    print(f"\n-- {title}")


section("a figure that is not in the response must be replaced")
for pid, prose in [
    ("A01", "Cook County earns 76,001."),
    ("A02", "Cook County earns 75,999."),
    ("A03", "Cook County earns 7600."),
    ("A04", "Cook County earns 760,000."),
    ("A05", "Cook County earns 76.000."),
    ("A06", "Incomes run 76,000-78,462."),
    ("A07", "About 1/2 of households."),
    ("A08", "Cook County earns $76k."),
    ("A09", "Cook County earns $1.2M."),
    ("A10", "Cook County earns 78,462USD."),
    ("A11", "Cook County ranks #3."),
    ("A12", "Cook County earns $78,462."),
    ("A13", "Cook County earns 78,462%."),
    ("A14", "Cook County earns (78,462)."),
    ("A15", "Cook County earns **78,462**."),
    ("A16", "Cook County earns ７８,４６２."),
    ("A17", "Cook County earns 78_462."),
    ("A18", "Cook County earns 7.8462e4."),
    ("A19", "Circled ① of households."),
]:
    check(pid, prose, flag=True)
big = {**COOK, "B19013_001E": "2132000", "B19013_001M": "9000"}
check("A20", "Cook County has 2.1 million people.", flag=True, rows=[big])

section("a number written without a decimal digit: the check reads digits only")
for pid, glyph in [("B01", "½"), ("B02", "¼"), ("B03", "¾"), ("B04", "⅔"), ("B05", "Ⅻ")]:
    check(pid, f"About {glyph} of households.", flag=True)
check("B06", "About half of households.", flag=True, known="GAP")
check("B07", "Cook County earns seventy-six thousand.", flag=True, known="GAP")
check("B08", "About 1½ times as many.", flag=True)

section("words float() would read, and carried numbers, must pass")
for pid, word in [("C01", "nan"), ("C02", "inf"), ("C03", "-Infinity")]:
    check(pid, f"The value {word} is a word here.", flag=False)
check("C04", "Cook County earns $76,000 in 2023, give or take 1,200.", flag=False)
check("C05", "Incomes run 76,000–99,500 across the two counties.", flag=False)
check("C06", "Table B19013 (B19013_001E), GEOID 0500000US17031, ACS 5-year.", flag=False)
check("C07", "These are 1-year estimates.", flag=True)

section("known limits of a digits-only check (owner decision, named in the plan)")
check("D01", "Cook County earns 99,500.", flag=True, known="GAP")  # DuPage's figure, wrong place
neg = {**COOK, "B19013_001E": "-1200", "B19013_001M": "300"}
check("D02", "Cook County gained 1,200.", flag=True, known="GAP", rows=[neg])  # sign flipped
check("D03", "Cook County is 17 percent.", flag=True, known="GAP")  # state FIPS 17 carries it
check("D04", "That is about 5 percent.", flag=True, known="GAP")  # the dataset's 5 carries it

section("text that states only what the response carries but is replaced")
check("E01", "Cook County earns 76,000…", flag=False)
check("E02", "The 2nd table in the list.", flag=False, known="OBSERVATION")
url = "https://api.census.gov/data/2023/acs/acs5?get=NAME,B19013_001E&for=county:031&in=state:17"
check("E03", f"Fetched from {url}", flag=False, known="OBSERVATION")
omitted = seed._record()
omitted.fetch.omitted_years = [2020]
omitted.fetch.omission_reasons = [REASON_GAP_2020]
check("E04", f"2020 was omitted ({REASON_GAP_2020}).", flag=False, record=omitted)
check("E05", "The fetch returned 2 rows over 1/1 legs.", flag=False, known="OBSERVATION")

section("take_chart with a reply that is not the envelope it expects: it must not raise")
BAR = {"type": "bar", "x": "geography", "y": "estimate"}
replies = {
    "answer null": '{"answer": null, "chart": null}',
    "answer int": '{"answer": 12345, "chart": null}',
    "answer list": '{"answer": ["a 99,999"], "chart": null}',
    "chart str": '{"answer": "ok", "chart": "bar"}',
    "chart title null": json.dumps({"answer": "ok", "chart": {**BAR, "title": None}}),
    "chart title int": json.dumps({"answer": "ok", "chart": {**BAR, "title": 123456}}),
    "empty": "",
    "fence only": "```",
    "json list": "[1, 2, 3]",
    "json number": "123456",
    "nested envelope": json.dumps({"answer": json.dumps({"answer": "x 99,999"}), "chart": None}),
}
for name, reply in replies.items():
    try:
        parts = take_chart(reply, [seed.TITLED, DUPAGE], [], seed._record())
        say("F", "HELD", name, f"answer starts {parts['answer'][:28]!r}")
    except Exception as error:  # noqa: BLE001 - the probe reports whatever it finds
        say("F", "DEFECT", name, f"raised {type(error).__name__}: {error}")

section("what is rendered")
no_margin = {k: v for k, v in COOK.items() if k != "B19013_001M"}
line = figures.checked("", [no_margin], seed._record())[0].split("\n")[0]
say("G01", "OBSERVATION", "estimate column without its margin column", line)
two_tables = {**COOK, "B01001_001E": "5000", "B01001_001M": "10"}
answer = figures.checked("", [two_tables], seed._record())[0]
say(
    "G02",
    "OBSERVATION",
    "one row from two tables",
    f"{answer.count('Table B')} table line(s): {answer.splitlines()[-1]!r}",
)
many = SimpleNamespace(fetch=SimpleNamespace(labels={}), table_facts=None, universe="")
shown = figures.checked("", [seed._wide(25)], many)[0]
say(
    "G03",
    "HELD",
    "one row, 25 estimates",
    f"{shown.count('margin of error')} figure lines, last line {shown.splitlines()[-1]!r}",
)

print("\nTALLY  " + ", ".join(f"{key} {value}" for key, value in sorted(tally.items())))
