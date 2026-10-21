"""Mutation check for the Gate 2 fixes (CC-121, batch F1).

Each mutation reverts ONE fixed behaviour in ONE api/src file by exact replacement (the old text
must occur exactly once), runs ONLY the test that covers it, and records the pytest summary line.
Files are restored byte for byte in a `finally` block and compared with a snapshot at the end.
Plain str methods and subprocess only: no regex, no word list. From the repository root:

    uv run python evidence/slice-6/cc-121-fixes-mutations.py > <transcript>.txt
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
TESTS = "api/tests/test_figures.py"
T = f"{TESTS}::"
FIG, CON = "api/src/figures.py", "api/src/contract.py"
GLUED = T + "test_a_figure_glued_to_a_mark_float_cannot_read_is_still_checked"
CARRIED_GLUED = T + "test_a_carried_figure_glued_to_a_mark_is_not_trusted"
IDS = T + "test_identifiers_the_response_carries_pass_whole_and_others_do_not"
BEFORE = T + "test_a_text_before_any_fetch_may_name_the_year_and_dataset_it_built"
FAILURE = T + "test_a_failure_the_fetch_reports_keeps_its_framing"
TITLE = T + "test_a_chart_title_that_states_an_uncarried_number_is_replaced_by_the_table_id"
KEPT = T + "test_a_chart_title_with_only_carried_numbers_is_kept"
NO_RECORD = T + "test_a_chart_title_is_not_checked_without_a_record"
COMBINED = T + "test_combined_rows_are_shown_before_the_cap_cuts_anything"
CUT = T + "test_an_identifier_in_a_row_the_cap_cut_is_still_carried"
LABEL = T + "test_a_label_loses_its_estimate_prefix_and_joins_its_levels"
FOLLOW = T + "test_the_notice_says_figures_follow_only_when_they_do"


class Case(NamedTuple):
    name: str
    file: str
    old: str
    new: str
    test: str


CASES = [
    Case(
        "digit-bearing token float() cannot read skipped",
        FIG,
        "found.append(token.casefold())",
        "pass",
        GLUED,
    ),
    Case(
        "carried figure glued to a mark skipped",
        FIG,
        "found.append(token.casefold())",
        "pass",
        CARRIED_GLUED,
    ),
    Case(
        "carried tokens compared with their case",
        FIG,
        "found.append(token.casefold())",
        "found.append(token)",
        IDS,
    ),
    Case(
        "keys and table prefixes not carried",
        FIG,
        'texts += [str(cell), key, key.split("_")[0]]',
        "texts += [str(cell)]",
        IDS,
    ),
    Case(
        "cell strings not carried whole",
        FIG,
        'texts += [str(cell), key, key.split("_")[0]]',
        'texts += [key, key.split("_")[0]]',
        CUT,
    ),
    Case(
        "dataset of the built vintages not carried",
        FIG,
        "| {str(name) for name, _ in vintages}",
        "",
        BEFORE + "[vintages_only]",
    ),
    Case(
        "years of the built vintages not carried",
        FIG,
        "*(year for _, year in vintages), built]",
        "built]",
        BEFORE + "[vintages_only]",
    ),
    Case(
        "year of the built URL not carried",
        FIG,
        "*(year for _, year in vintages), built]",
        "*(year for _, year in vintages)]",
        BEFORE + "[built_url_only]",
    ),
    Case(
        "fetch status code not carried",
        FIG,
        'getattr(fetch, "status_code", 0),',
        "0,",
        FAILURE + "[fetch_status]",
    ),
    Case(
        "leg status codes not carried",
        FIG,
        '*(x.status_code for x in getattr(fetch, "legs", None) or []),',
        "",
        FAILURE + "[leg_status]",
    ),
    Case(
        "notice says figures follow when none do",
        FIG,
        '"figures below replace it." if lines else "it was removed."',
        '"figures below replace it." if lines else "figures below replace it."',
        BEFORE + "[vintages_only]",
    ),
    Case(
        "notice drops the figures claim",
        FIG,
        '"figures below replace it." if lines else "it was removed."',
        '"it was removed." if lines else "it was removed."',
        FOLLOW,
    ),
    Case(
        "combined rows not first under the cap",
        FIG,
        'found.sort(key=lambda cell: "component_count" not in cell[0])  # combined rows first',
        "pass",
        COMBINED,
    ),
    Case(
        "trailing colon of a label kept",
        FIG,
        '.replace("!!", " - ").rstrip(":")',
        '.replace("!!", " - ")',
        LABEL,
    ),
    Case("model chart title not checked", CON, "stray(spec.title, rows, record)", "[]", TITLE),
    Case("clean chart title replaced", CON, "stray(spec.title, rows, record)", "[1]", KEPT),
    Case(
        "uncarried chart title kept",
        CON,
        'spec = spec.model_copy(update={"title": table_id})',
        "pass",
        TITLE,
    ),
    Case(
        "chart title notice has another code",
        CON,
        'code="answer_figures_unverified", detail=notice',
        'code="chart_title", detail=notice',
        TITLE,
    ),
    Case(
        "chart title checked without a record",
        CON,
        "if record is not None and spec is not None and stray(",
        "if spec is not None and stray(",
        NO_RECORD,
    ),
]


def pytest(target: str) -> tuple[int, str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    return done.returncode, done.stdout + done.stderr


def summary(out: str) -> str:
    for line in reversed(out.splitlines()):
        text = line.strip("= ").strip()
        if " in " in text and ("passed" in text or "failed" in text or "error" in text):
            return text
    return out.strip().splitlines()[-1] if out.strip() else "no output"


def run(case: Case) -> tuple[int, str]:
    path = ROOT / case.file
    original = path.read_bytes()
    text = original.decode("utf-8").replace(chr(13) + chr(10), chr(10))
    assert text.count(case.old) == 1, f"{case.name}: old text occurs {text.count(case.old)} times"
    assert case.old != case.new, f"{case.name}: nothing changed"
    try:
        path.write_bytes(text.replace(case.old, case.new).encode("utf-8"))
        return pytest(case.test)
    finally:
        path.write_bytes(original)


def main() -> int:
    snapshot = {name: (ROOT / name).read_bytes() for name in (FIG, CON)}
    print("CC-121 batch F1: mutation check of the Gate 2 fixes (api/tests/test_figures.py)")
    print(
        "Every line below is real pytest output. The CSS rule and judge-script text have no test.\n"
    )
    code, out = pytest(TESTS)
    assert code == 0, out
    print(f"GOOD unmutated code\n     {summary(out)}\n")
    caught = 0
    for case in CASES:
        code, out = run(case)
        text = summary(out)
        ok = code == 1 and " error" not in text and "failed" in text
        caught += ok
        print(f"BAD  mutation: {case.name}  [{case.test.removeprefix(T)}]")
        print(f"     {'CAUGHT' if ok else 'NOT CAUGHT'}  [{text!r}]")
    print(f"\nTALLY  {caught} of {len(CASES)} mutations CAUGHT")
    assert all((ROOT / name).read_bytes() == data for name, data in snapshot.items()), (
        "not restored"
    )
    code, out = pytest(TESTS)
    print(f"GOOD restored code (files identical to the snapshot)\n     {summary(out)}")
    return 0 if caught == len(CASES) and code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
