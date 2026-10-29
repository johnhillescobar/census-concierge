"""Gate 1 mutation check of the CC-121 tests, on the code as committed (HEAD).

For every new or changed test, revert ONE behaviour it covers in ONE source file (exact text
replacement; the old text must occur exactly once), run ONLY that test, and require a failure.
The file is restored byte for byte in a `finally` block and `git diff --quiet -- api/src` is
checked at the end. Plain str methods and subprocess only: no regex, no word list.

Cases come from three places:
  - the two earlier harnesses (cc-121-gate1-mutations.py, pinned to f59eee8, and
    cc-121-fixes-mutations.py), reused where their old text still occurs exactly once in the
    source today; the rest are listed as STALE and re-authored below against today's code;
  - the cases written in this file for the tests this pass added;
  - the cases for the tests whose assertions the change rewrote (test_chart, test_guards,
    test_ask_loop).
Then every new or changed test function is checked against the set of targeted tests, and the
two strict xfail tests are shown to flip when their defect is repaired in the source.

    uv run python -B -X utf8 evidence/slice-6/gate1-mutations.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TESTS = "api/tests/test_figures.py"
T = f"{TESTS}::"
FIG, CON, ASK, FET, URL = (
    f"api/src/{name}.py" for name in ("figures", "contract", "ask", "fetch", "census_url")
)
CHART, GUARDS, LOOP = (f"api/tests/test_{name}.py::" for name in ("chart", "guards", "ask_loop"))


class Case(NamedTuple):
    name: str
    file: str
    old: str
    new: str
    test: str
    also: tuple[tuple[str, str], ...] = ()  # more replacements applied in the same file


def load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source(path: str) -> str:
    return (ROOT / path).read_bytes().decode("utf-8").replace(chr(13) + chr(10), chr(10))


NEW: list[Case] = []
FIXED: list[Case] = []  # defect repaired in the source: a strict xfail must flip to XPASS


def case(
    name: str,
    file: str,
    old: str,
    new: str,
    test: str,
    into: list[Case] = NEW,
    also: tuple[tuple[str, str], ...] = (),
) -> None:
    into.append(Case(name, file, old, new, test, also))


# --- re-authored: the earlier cases whose target lines the Gate 2 fixes rewrote ----------------
KEPT = "if number not in allowed}"
DIGITS = '"".join(c if c.isdigit() else " " for c in name)'
CELLS = 'texts += [str(cell), key, key.split("_")[0]]'
PRES = "            _warn_unverified(warnings, problem)"
t = "test_figures_carry_label_estimate_margin_place_geoid_and_vintage"
case(
    "figures not appended after the framing",
    FIG,
    "(prose.strip(), block) if part",
    "(prose.strip(),) if part",
    T + t,
)
for t in (
    "test_numbers_that_equal_the_rows_pass_however_they_are_written",
    "test_a_range_of_two_carried_figures_passes",
):
    case(
        f"carried figure flagged instead of the stray one ({t[5:25]})",
        FIG,
        KEPT,
        "if number in allowed}",
        T + t,
    )
t = "test_numbers_from_the_dataset_title_and_geography_columns_pass"
case("dataset digits not carried", FIG, DIGITS, "name", T + t)
case("title, universe and rendered lines not carried", FIG, "[*texts, *lines])", "[])", T + t)
case("row cells not carried", FIG, CELLS, 'texts += [key, key.split("_")[0]]', T + t)
t = "test_the_dataset_decides_which_span_the_text_may_name"
case("dataset digits not carried (span)", FIG, DIGITS, "name", T + t)
case("any span carried whatever the dataset", FIG, DIGITS, '"1 5"', T + t)
for t in (
    "test_a_number_equal_only_to_a_sentinel_is_not_carried",
    "test_a_sentinel_written_in_the_models_text_is_replaced",
):
    case(
        f"sentinel cells carried ({t[5:25]})",
        FIG,
        "if cell not in CENSUS_MISSING:",
        "if True:",
        T + t,
    )
t = "test_the_chart_survives_when_the_text_is_replaced"
case(
    "chart dropped when the text is replaced",
    CON,
    PRES,
    PRES + '\n            return {"answer": cleaned, "chart": None, "chart_unavailable": False}',
    T + t,
)
case("warning never added", CON, PRES, "            pass", T + t)
t = "test_a_figure_that_differs_in_any_digit_is_not_carried"
case(
    "a figure within one percent counted as carried",
    FIG,
    KEPT,
    "if not any(number == k or (isinstance(number, float) and isinstance(k, float) "
    "and abs(number - k) <= k * 0.01) for k in allowed)}",
    T + t,
)
case(
    "trailing zeros ignored when comparing figures",
    FIG,
    KEPT,
    'if (str(int(number)).rstrip("0") if isinstance(number, float) else number) '
    'not in {(str(int(k)).rstrip("0") if isinstance(k, float) else k) for k in allowed}}',
    T + t,
)
case(
    "periods dropped like thousands separators",
    FIG,
    'abs(float(token.replace(",", "")))',
    'abs(float(token.replace(",", "").replace(".", "")))',
    T + "test_a_period_is_not_read_as_a_thousands_separator",
)
case(
    "rounded millions counted as carried",
    FIG,
    KEPT,
    "if number not in allowed and not (isinstance(number, float) and any("
    "isinstance(k, float) and abs(number * 1e6 - k) <= k * 0.05 for k in allowed))}",
    T + "test_a_rounded_figure_with_a_magnitude_word_is_not_carried",
)
case(
    "GEO_ID read whole so its FIPS digits are lost",
    FIG,
    'texts += [str(cell).split("US")[-1]] if key == "GEO_ID" else []',
    "texts += []",
    T + "test_the_fips_digits_of_a_geoid_are_carried",
)
case(
    "period column not carried",
    FIG,
    "if cell not in CENSUS_MISSING:",
    'if cell not in CENSUS_MISSING and key != "period":',
    T + "test_the_period_of_a_vintage_may_be_named_in_a_real_response",
)
case(
    "warning appended to a missing list",
    CON,
    "    if warnings is not None:",
    "    if True:",
    T + "test_take_chart_without_a_warnings_list_still_replaces_the_text",
)
t = "test_take_chart_warns_only_when_it_replaced_the_text"
case("warning added when the text was kept", CON, "        if problem:", "        if True:", T + t)
case("warning never added (hook)", CON, PRES, "            pass", T + t)
case(
    "model chart reset when the text is dropped",
    CON,
    PRES,
    PRES + "\n            saw = False",
    T + "test_the_models_own_chart_spec_survives_when_the_text_is_replaced",
)

# --- the tests this pass added ------------------------------------------------------------------
t = "test_a_notice_joins_only_the_unverified_warning_never_another_code"
case(
    "a notice joins a warning of any code",
    CON,
    'if getattr(item, "code", "") == "answer_figures_unverified":',
    'if getattr(item, "code", "") != "":',
    T + t,
)
case(
    "only the first warning is searched for the unverified one",
    CON,
    "    for item in warnings or []:",
    "    for item in (warnings or [])[:1]:",
    T + t,
)
t = "test_a_cell_that_is_not_a_plain_number_is_shown_as_the_census_sent_it"
case(
    "a cell that is not a number shown as nothing",
    FIG,
    "    except ValueError:\n        return raw",
    '    except ValueError:\n        return ""',
    T + t,
)
case(
    "a cell that is not a number shown as zero",
    FIG,
    "    except ValueError:\n        return raw",
    '    except ValueError:\n        return "0"',
    T + t,
)
t = "test_every_cell_may_be_quoted_and_every_shown_cell_is_stated_as_sent"
case("rendered lines not carried", FIG, "[*texts, *lines])", "texts)", T + t)
case(
    "decimals dropped from a shown figure",
    FIG,
    'f"{int(whole):,}{dot}{fraction}"',
    'f"{int(whole):,}"',
    T + t,
)
case("row cells not carried (quoted)", FIG, CELLS, 'texts += [key, key.split("_")[0]]', T + t)
case(
    "sentinel shown as a figure (fuzz)",
    FIG,
    "None if row.get(k) in CENSUS_MISSING else row.get(k)",
    "row.get(k)",
    T + t,
)
case("margin read from the estimate column (fuzz)", FIG, 'key[:-1] + "M"', "key", T + t)
t = "test_a_real_record_carries_what_the_check_reads_from_it"
case(
    "year of the built URL not read",
    FIG,
    'getattr(record, "url", None), "year", None',
    'getattr(record, "url", None), "yr", None',
    T + t + "[built_url]",
)
case(
    "year of a real CensusURL broken",
    URL,
    "return int(bits[index + 1])\n        return None\n\n    @property\n    def dataset",
    "return None\n        return None\n\n    @property\n    def dataset",
    T + t + "[built_url]",
)
case(
    "status code of a leg not read",
    FIG,
    "*(x.status_code for x in",
    "*(x.status for x in",
    T + t + "[leg_status]",
)
case(
    "alternative table not carried",
    FIG,
    '[hit.get("table_id"), *(hit.get("members") or [])]',
    '[hit.get("id"), *(hit.get("members") or [])]',
    T + t + "[search_pool]",
)
case(
    "alternative family members not carried",
    FIG,
    '*(hit.get("members") or [])]',
    '*(hit.get("member") or [])]',
    T + t + "[search_pool]",
)
case(
    "vintage dataset not carried",
    FIG,
    "| {str(name) for name, _ in vintages}",
    "",
    T + t + "[vintages]",
)
case(
    "vintage year not carried",
    FIG,
    "*(year for _, year in vintages), built]",
    "built]",
    T + t + "[vintages]",
)
case(
    "the unverified notice not added to the real response",
    ASK,
    "**take_chart(answer, rows, warnings, record),",
    "**take_chart(answer, rows, warnings),",
    T + t + "[leg_status]",
)

# --- tests added after the operator sweep found behaviours nothing pinned -----------------------
STAND_IN = 'NO_FIGURES = "No figures were fetched for this request; see the warnings and the URL."'
t = "test_a_dropped_text_with_no_figures_to_show_is_never_a_blank_answer"
case("the stand-in for a dropped text is empty", FIG, STAND_IN, 'NO_FIGURES = ""', T + t)
case(
    "a dropped text with nothing to show is left blank",
    FIG,
    " or NO_FIGURES, problem",
    ' or "", problem',
    T + t,
)
t = "test_a_figure_written_with_separators_that_the_cap_cut_is_still_carried"
case(
    "thousands separators not removed when reading",
    FIG,
    'abs(float(token.replace(",", "")))',
    "abs(float(token))",
    T + t,
)
t = "test_the_cut_notice_appears_only_when_a_figure_was_cut"
case(
    "the notice appears at the cap",
    FIG,
    "if total > MAX_FIGURES:",
    "if total >= MAX_FIGURES:",
    T + t + "[at_cap]",
)
case("the notice never appears", FIG, "if total > MAX_FIGURES:", "if False:", T + t + "[over_cap]")
t = "test_table_facts_are_asked_in_the_dataset_of_each_row"
case(
    "table facts asked without the dataset",
    FIG,
    'str(row.get("dataset") or ""), year) for row, _key, year in shown',
    '"", year) for row, _key, year in shown',
    T + t,
)
t = "test_vintages_that_share_a_description_are_listed_together"
case("years listed without a separator", FIG, "', '.join(years)", "''.join(years)", T + t)
t = "test_the_notice_lists_the_first_five_stray_numbers_in_order"
case("six stray numbers listed", FIG, "bad[:5]", "bad[:6]", T + t)
case(
    "stray numbers listed without a comma", FIG, 'listed = ", ".join(', 'listed = " ".join(', T + t
)
t = "test_the_two_notices_of_one_response_are_joined_in_order"
JOIN = 'item.detail = f"{item.detail} {detail}"'
case(
    "second notice not joined with a space",
    CON,
    JOIN,
    'item.detail = f"{item.detail}{detail}"',
    T + t,
)
case("second notice replaces the first", CON, JOIN, "item.detail = detail", T + t)
case(
    "labels returned for variables nobody asked for",
    FIG,
    "for key in wanted & found.keys()",
    "for key in found.keys()",
    T + "test_labels_come_back_only_for_the_variables_asked_for",
)

# --- marks and separators. Since the Gate 2 fix an unreadable token with a digit in it is flagged,
# so taking ONE mark or separator out no longer lets a stray figure through, and the older
# flag-tests cannot fail by one revert. They are checked against the pre-fix state (the mark
# taken out AND unreadable tokens skipped); the keep-tests added in this pass are checked against
# the single revert: a carried figure in marks, or a carried range, must still pass.
EDGE = '_EDGE = ".,;:!?()[]{}\\"\'*_`~<>=+$%"'
BREAKS = 'str.maketrans("-–—/|", "     ")'
SKIP = ("found.append(token.casefold())", "pass")
for ident, char, label in (
    ("dollar", "$", "dollar sign"),
    ("percent", "%", "percent sign"),
    ("bold", "*", "markdown asterisk"),
    ("parenthesis", "(", "opening parenthesis"),
    ("double_quote", '\\"', "double quote"),
    ("semicolon", ";", "semicolon"),
):
    case(
        f"{label} not stripped from a carried figure",
        FIG,
        EDGE,
        EDGE.replace(char, "", 1),
        T + f"test_marks_around_a_carried_figure_do_not_change_it[{ident}]",
    )
    case(
        f"pre-fix state: {label} not stripped, unreadable tokens skipped",
        FIG,
        EDGE,
        EDGE.replace(char, "", 1),
        T + f"test_marks_around_a_figure_do_not_hide_it[{ident}]",
        also=(SKIP,),
    )
for ident, char, label in (
    ("hyphen", "-", "hyphen"),
    ("en_dash", "–", "en dash"),
    ("em_dash", "—", "em dash"),
    ("slash", "/", "slash"),
    ("pipe", "|", "pipe"),
):
    shorter = BREAKS.replace(char, "", 1).replace('"     ")', '"    ")')
    case(
        f"{label} not a break between carried figures",
        FIG,
        BREAKS,
        shorter,
        T + f"test_a_range_of_two_carried_figures_passes_whatever_the_separator[{ident}]",
    )
    case(
        f"pre-fix state: {label} not a break, unreadable tokens skipped",
        FIG,
        BREAKS,
        shorter,
        T + f"test_a_stray_figure_after_a_separator_is_found[{ident}]",
        also=(SKIP,),
    )
case(
    "pre-fix state: slash not a break, unreadable tokens skipped (fraction)",
    FIG,
    BREAKS,
    BREAKS.replace("/", "", 1).replace('"     ")', '"    ")'),
    T + "test_a_fraction_is_two_figures_and_neither_is_carried",
    also=(SKIP,),
)

SUPERSEDED = {
    "hyphen not a break between figures",
    "en dash not a break between figures",
    "em dash not a break between figures",
    "slash not a break between figures",
    "pipe not a break between figures",
    "slash not a break between figures (fraction)",
    "dollar sign not stripped from a figure",
    "percent sign not stripped from a figure",
    "markdown asterisk not stripped from a figure",
    "opening parenthesis not stripped from a figure",
    "double quote not stripped from a figure",
    "semicolon not stripped from a figure",
    "labels returned for variables nobody asked for",
}

# --- the tests whose assertions the change rewrote -----------------------------------------------
BLOCK = "(prose.strip(), block) if part"
rewritten = [
    CHART + "test_year_series_keeps_a_line_chart",
    CHART + "test_scalar_result_has_no_chart",
    CHART + "test_prose_answer_stays_a_prose_answer",
    CHART + "test_prose_comparison_gets_a_geography_bar",
    CHART + "test_unknown_chart_type_is_discarded",
    CHART + "test_fenced_json_still_extracts_the_chart",
    GUARDS + "test_zip_language_warns_without_blocking_a_zcta_row",
    LOOP + "test_sequential_single_place_calls_are_repaired_by_finish_tools",
]
for test in rewritten:
    short = test.split("::")[1][5:40]
    case(f"framing dropped from the answer ({short})", FIG, BLOCK, "(block,) if part", test)
    case(
        f"figures placed before the framing ({short})",
        FIG,
        BLOCK,
        "(block, prose.strip()) if part",
        test,
    )
compared = [
    LOOP + "test_and_phrased_comparison_resolves_both_geographies",
    LOOP + "test_and_phrased_comparison_across_states",
    LOOP + "test_three_way_and_list_comparison",
    LOOP + "test_bare_unqualified_city_names_resolve_all_places",
]
for test in compared:
    short = test.split("::")[1][5:40]
    case(
        f"a warning on every answer ({short})",
        CON,
        "        if problem:",
        "        if True or problem:",
        test,
    )

# --- strict xfail tests: repair the defect in the source and the xfail must flip ---------------
glyphs = ("1/2", "1/4", "3/4", "2/3")
for glyph in glyphs:
    case(
        f"numeric characters read as figures ({glyph})",
        FIG,
        "if any(char.isdigit() for char in token):",
        "if any(char.isnumeric() for char in token):",
        T + f"test_a_fraction_character_is_a_figure_too[{glyph}]",
        FIXED,
    )
case(
    "omission reasons carried",
    FIG,
    '    pool = getattr(record, "pool", None) or []\n',
    '    pool = getattr(record, "pool", None) or []\n'
    '    texts += [str(x) for x in getattr(fetch, "omission_reasons", None) or []]\n',
    T + "test_the_reason_the_fetch_gives_for_an_omitted_year_may_be_quoted",
    FIXED,
)


def pytest(*targets: str) -> tuple[int, str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", *targets, "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done.returncode, done.stdout


def summary(out: str) -> str:
    for line in reversed(out.splitlines()):
        text = line.strip("= ").strip()
        if " in " in text and any(word in text for word in ("passed", "failed", "error")):
            return text
    return out.strip().splitlines()[-1] if out.strip() else "no output"


def run(item: Case) -> tuple[int, str]:
    path = ROOT / item.file
    original = path.read_bytes()
    text = original.decode("utf-8").replace(chr(13) + chr(10), chr(10))
    edits = ((item.old, item.new), *item.also)
    for old, new in edits:
        assert text.count(old) == 1, f"{item.name}: old text occurs {text.count(old)} times"
        assert old != new, f"{item.name}: nothing changed"
    mutated = text
    for old, new in edits:
        mutated = mutated.replace(old, new)
    try:
        path.write_bytes(mutated.encode("utf-8"))
        return pytest(item.test)
    finally:
        path.write_bytes(original)


def function_of(node_id: str) -> str:
    return node_id.split("::")[-1].split("[")[0]


def collected(path: str) -> set[str]:
    _code, out = pytest(path, "--collect-only")
    return {function_of(line) for line in out.splitlines() if "::" in line}


def main() -> int:
    print(__doc__.split("\n\n")[0])
    print("\ncode under test: the working tree at HEAD; api/src is unchanged by this pass\n")
    code, out = pytest(TESTS)
    assert code == 0, out
    print(f"GOOD unmutated code\n     {summary(out)}\n")

    earlier = []
    stale = []
    superseded = []
    for name in ("cc-121-gate1-mutations", "cc-121-fixes-mutations"):
        for old_case in load(name).CASES:  # type: ignore[attr-defined]
            if source(old_case.file).count(old_case.old) != 1:
                stale.append(old_case)
            elif old_case.name in SUPERSEDED:
                superseded.append(old_case)
            else:
                earlier.append(Case(*old_case))
    print(f"{len(earlier)} earlier cases still match today's source and are reused;")
    print(f"{len(stale)} are STALE (their target lines were rewritten) and are re-authored above:")
    for old_case in stale:
        print(f"     STALE  {old_case.name}  [{old_case.test.split('::')[-1]}]")
    print(f"{len(superseded)} more are SUPERSEDED: one revert no longer fails their test (see the")
    print("marks-and-separators note above), so each is checked below by a pair of reverts and by")
    print("a keep-test written in this pass:")
    for old_case in superseded:
        print(f"     SUPERSEDED  {old_case.name}  [{old_case.test.split('::')[-1]}]")
    print()

    targeted: set[str] = set()
    caught = 0
    cases = earlier + NEW
    for item in cases:
        code, out = run(item)
        text = summary(out)
        ok = code == 1 and " error" not in text and "failed" in text and "xpassed" not in text
        caught += ok
        targeted.add(function_of(item.test))
        print(f"BAD  mutation: {item.name}  [{item.test.split('::', 1)[1]}]")
        print(f"     {'CAUGHT' if ok else 'NOT CAUGHT'}  [{text!r}]")
    confirmed = 0
    for item in FIXED:
        code, out = run(item)
        text = summary(out)
        ok = code == 1 and "XPASS(strict)" in out
        confirmed += ok
        targeted.add(function_of(item.test))
        print(f"FIX  defect repaired in the source: {item.name}  [{item.test.split('::', 1)[1]}]")
        print(f"     {'XPASS(strict)' if ok else 'NOT XPASS'}  [{text!r}]")

    new_tests = collected(TESTS)
    changed = {function_of(test) for test in rewritten + compared}
    untargeted = sorted(new_tests - targeted)
    print(
        f"\nCOVERAGE  {len(new_tests)} test functions in {TESTS}; "
        f"{len(new_tests & targeted)} targeted"
    )
    for name in untargeted:
        print(f"     UNTARGETED  {name}")
    for name in sorted(changed - targeted):
        print(f"     UNTARGETED  {name}")

    clean = subprocess.run(["git", "diff", "--quiet", "--", "api/src"], cwd=ROOT, check=False)
    assert clean.returncode == 0, "api/src differs from HEAD after the mutations"
    print(
        f"\nTALLY  {caught} of {len(cases)} mutations CAUGHT; "
        f"{confirmed} of {len(FIXED)} defect repairs turned the strict xfail into XPASS"
    )
    code, out = pytest(TESTS)
    assert code == 0, out
    print("GOOD restored code (git diff --quiet -- api/src is clean)")
    print(f"     {summary(out)}")
    ok = caught == len(cases) and confirmed == len(FIXED) and not untargeted
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
