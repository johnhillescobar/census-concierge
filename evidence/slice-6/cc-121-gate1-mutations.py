"""Gate 1 mutation check for api/tests/test_figures.py (CC-121).

Each mutation reverts ONE behaviour in ONE api/src file by exact string replacement (the old
text must occur exactly once), runs ONLY the test that covers it, and records the pytest summary
line. The file is restored in a `finally` block. Plain str methods and subprocess only: no
regex, no word list. Run from the repository root:

    uv run python evidence/slice-6/cc-121-gate1-mutations.py
        > evidence/slice-6/cc-121-gate1-restored.txt
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
TEST_FILE = "api/tests/test_figures.py"
T = f"{TEST_FILE}::"
FIG, CON, ASK, FET = (f"api/src/{name}.py" for name in ("figures", "contract", "ask", "fetch"))

HEADER = """\
CC-121 Gate 1: mutation check of api/tests/test_figures.py
code under test: f59eee8 (render the figures by code, check the model's text digit by digit);
api/src is identical at branch tip 52f4292. Every line below is real pytest output.

Adversarial matrix: docs/process-evidence.md lists four rows, all slice-0 retrieval probes
(identical inputs ranked by float noise, a family returned by one member, a ranking change
measured on the tuning set alone, "expect the largest jump" checked against the number).
None of them targets answer figures, so the probes here come from the Gate 1 brief instead:
off-by-one and dropped digits, European separators, ranges and fractions, rounded millions,
float-readable words without digits, marks around a figure, dataset specificity, rows without
year or dataset or place, non-estimate columns, a 25-column row, a place with no estimates,
the take_chart hook (no record, no warnings list, failed fetch, chart kept), sentinels.

KNOWN GAP, not tested as solved: the check compares digits only. A framing that attaches a
carried number to the wrong place (it says Cook County earns 99,500, which is DuPage's) passes.

Not tested, by the owner's decision (no word list anywhere): a number written in words.

DEFECTS (api/src not touched): a token that holds a digit but that float() cannot read is
skipped, so a figure glued to a mark passes unchecked. test_a_figure_glued_to_a_mark_float_
cannot_read_is_still_checked asserts the correct behaviour under xfail(strict=True) for five
inputs; the FIX lines at the end repair each one in api/src and show the xfail turning into a
strict XPASS (a failure), proving the test is sensitive to the defect and not to something else.

BAD  = the behaviour is reverted; the test must fail (CAUGHT).  GOOD = the code as committed.
"""


class Case(NamedTuple):
    name: str
    file: str
    old: str
    new: str
    test: str


EDGE = '_EDGE = ".,;:!?()[]{}\\"\'*_`~<>=+$%"'
BREAKS = 'str.maketrans("-–—/|", "     ")'
YEARS = (
    '_YEARS = ("requested_years", "attempted_years", "succeeded_years", "failed_years", '
    '"omitted_years")'
)
SHOWN = 'f"{int(whole):,}{dot}{fraction}"'
DATASET_YEAR = '(row.get("dataset"), year)'
CELLS = 'if key.endswith("E") and "_" in key'
PLACE = '(row.get("NAME"), f"({geoid})"'
GEOID = 'f"({geoid})" if geoid else ""'
VINTAGE = 'vintage = " ".join(part for part in (row.get("dataset"), year) if part)'
JOIN = '"".join(f", {p}" for p in (place, vintage) if p)'
MARGIN = "f\"{_shown(est)} (margin of error {_shown(moe) if moe else 'not published'})\""
STRAY = "stray = sorted({number for number in _numbers(prose) if number not in allowed})"
CAP = "    return found[:MAX_FIGURES], len(found)"
COUNT = 'f"{MAX_FIGURES} of {total} figures shown; the table has the rest."'
UNIVERSE = 'facts.get("universe") or getattr(record, "universe", "")'
LOOP = (
    '    for dataset, year in dict.fromkeys(\n        (str(row.get("dataset") or ""), year)'
    " for row, _key, year in shown\n    ):"
)
ROWS = "    for row in rows:\n        for key, cell in row.items():"
MISSING = "            if cell in CENSUS_MISSING:\n                continue"
APPEND = '            warnings.append(AskWarning(code="answer_figures_unverified", detail=problem))'
CHECKED = "cleaned, problem = checked(cleaned, rows, record)"
HOOK = "    if record is not None:"
LABEL = 'found[key].label.removeprefix("Estimate!!").replace("!!", " - ")'
FETCH_LABELS = "result.labels = await figures.labels_for(rows, plan.dataset)"


def without_year_field(name: str) -> str:
    return YEARS.replace(f'"{name}", ', "").replace(f', "{name}"', "")


CASES: list[Case] = []


def mutate(name: str, file: str, old: str, new: str, test: str) -> None:
    CASES.append(Case(name, file, old, new, T + test))


# --- the implementer's tests, one behaviour each -------------------------------------------
t = "test_figures_carry_label_estimate_margin_place_geoid_and_vintage"
mutate("margin of error left out", FIG, MARGIN, 'f"{_shown(est)}"', t)
mutate("margin read from the estimate column", FIG, 'key[:-1] + "M"', "key", t)
mutate("place name left out", FIG, PLACE, '("", f"({geoid})"', t)
mutate("GEOID left out", FIG, GEOID, '""', t)
mutate("dataset left out of the vintage", FIG, '(row.get("dataset"), year)', "(None, year)", t)
mutate("no thousands separators", FIG, SHOWN, SHOWN.replace(":,", ""), t)
mutate("universe left out", FIG, 'f"Universe: {universe}" if universe else ""', '""', t)
mutate("table title left out", FIG, 'f"Table {table}: {title}." if title else ""', '""', t)
mutate(
    "figures not appended after the framing",
    FIG,
    'part for part in (prose.strip(), "\\n".join(lines)) if part',
    "part for part in (prose.strip(),) if part",
    t,
)
t = "test_a_sentinel_is_never_shown_as_a_figure"
mutate(
    "sentinel shown as a figure",
    FIG,
    "None if row.get(k) in CENSUS_MISSING else row.get(k)",
    "row.get(k)",
    t,
)
mutate("unavailable estimate shown as zero", FIG, 'else "not available"', 'else "0"', t)
mutate("unpublished margin shown as blank", FIG, "if moe else 'not published'", "if moe else ''", t)
t = "test_a_long_result_shows_the_first_twenty_and_says_how_many_there_are"
mutate("no cap on figures shown", FIG, CAP, "    return found, len(found)", t)
mutate("cut figures not counted", FIG, "if total > MAX_FIGURES:", "if False:", t)
mutate(
    "shown count reported as the total", FIG, COUNT, COUNT.replace("{total}", "{MAX_FIGURES}"), t
)
t = "test_a_number_the_response_does_not_carry_replaces_the_models_text"
mutate("a stray number does not drop the text", FIG, '        prose = ""', "        pass", t)
t = "test_numbers_that_equal_the_rows_pass_however_they_are_written"
mutate(
    "carried figure flagged instead of the stray one",
    FIG,
    STRAY,
    STRAY.replace(" not in ", " in "),
    t,
)
t = "test_numbers_from_the_dataset_title_and_geography_columns_pass"
mutate(
    "dataset digits not carried",
    FIG,
    'text = "".join(char if char.isdigit() else " " for char in text)',
    "text = text",
    t,
)
mutate(
    "title, universe and rendered lines not carried",
    FIG,
    "    allowed.update(number for text in texts for number in _numbers(text))",
    "    pass",
    t,
)
mutate(
    "row cells not carried",
    FIG,
    "            allowed.update(_numbers(text))",
    "            pass",
    t,
)
t = "test_a_number_equal_only_to_a_sentinel_is_not_carried"
mutate("sentinel cells carried", FIG, MISSING, MISSING.replace("CENSUS_MISSING", "()"), t)
t = "test_nothing_fetched_leaves_a_clean_text_alone_and_removes_a_figure"
mutate(
    "empty answer when every figure is dropped",
    FIG,
    ") or NO_FIGURES, problem",
    ') or "", problem',
    t,
)
mutate(
    "clean text dropped when nothing was fetched",
    FIG,
    '        return prose, ""',
    '        return "", ""',
    t,
)
t = "test_each_vintage_is_read_with_its_own_label_title_and_universe"
mutate(
    "labels read from one fixed vintage",
    FIG,
    "labels.get(year, {}).get(key, key)",
    'labels.get("2023", {}).get(key, key)',
    t,
)
mutate(
    "table facts read from one fixed vintage",
    FIG,
    "table_facts(dataset, int(year), table)",
    "table_facts(dataset, 2023, table)",
    t,
)
mutate(
    "every label looked up at one fixed vintage",
    FIG,
    "asyncio.to_thread(_labels, dataset, int(year), keys)",
    "asyncio.to_thread(_labels, dataset, 2024, keys)",
    "test_labels_are_looked_up_once_per_vintage",
)
mutate(
    "only KeyError tolerated on label lookup",
    FIG,
    "    except Exception:  # noqa: BLE001 - a label lookup must never fail a fetch that succeeded",
    "    except KeyError:",
    "test_a_failed_label_lookup_is_empty_not_an_error",
)
t = "test_the_chart_survives_when_the_text_is_replaced"
mutate(
    "chart dropped when the text is replaced",
    CON,
    APPEND,
    APPEND + '\n            return {"answer": cleaned, "chart": None, "chart_unavailable": False}',
    t,
)
mutate("warning never added", CON, APPEND, "            pass", t)
t = "test_assemble_adds_the_figures_and_warns_when_the_text_states_another"
mutate(
    "ask.py does not pass the record",
    ASK,
    "**take_chart(answer, rows, warnings, record),",
    "**take_chart(answer, rows, warnings),",
    t,
)
mutate(
    "label lookup has no fallback",
    FIG,
    "labels.get(year, {}).get(key, key)",
    "labels.get(year, {})[key]",
    t,
)
mutate(
    "labels not kept on the artifact",
    FET,
    FETCH_LABELS,
    FETCH_LABELS.replace("result.labels = ", ""),
    "test_fetch_data_carries_each_vintages_labels_on_its_artifact",
)

# --- reading the model's numbers -------------------------------------------------------------
mutate(
    "a figure within one percent counted as carried",
    FIG,
    STRAY,
    "stray = sorted({number for number in _numbers(prose) if not any("
    "abs(number - known) <= known * 0.01 for known in allowed)})",
    "test_a_figure_that_differs_in_any_digit_is_not_carried",
)
mutate(
    "trailing zeros ignored when comparing figures",
    FIG,
    STRAY,
    "stray = sorted({number for number in _numbers(prose) if "
    'str(int(number)).rstrip("0") not in {str(int(known)).rstrip("0") for known in allowed}})',
    "test_a_figure_that_differs_in_any_digit_is_not_carried",
)
mutate(
    "periods dropped like thousands separators",
    FIG,
    'token = token.strip(_EDGE).replace(",", "")',
    'token = token.strip(_EDGE).replace(",", "").replace(".", "")',
    "test_a_period_is_not_read_as_a_thousands_separator",
)
mutate(
    "carried figure flagged instead of the stray one (range)",
    FIG,
    STRAY,
    STRAY.replace(" not in ", " in "),
    "test_a_range_of_two_carried_figures_passes",
)
for sep, drop in (
    ("hyphen", "-"),
    ("en_dash", "–"),
    ("em_dash", "—"),
    ("slash", "/"),
    ("pipe", "|"),
):
    shorter = BREAKS.replace(drop, "", 1).replace('"     ")', '"    ")')
    mutate(
        f"{sep.replace('_', ' ')} not a break between figures",
        FIG,
        BREAKS,
        shorter,
        f"test_a_stray_figure_after_a_separator_is_found[{sep}]",
    )
slash = BREAKS.replace("/", "", 1).replace('"     ")', '"    ")')
mutate(
    "slash not a break between figures (fraction)",
    FIG,
    BREAKS,
    slash,
    "test_a_fraction_is_two_figures_and_neither_is_carried",
)
mutate(
    "rounded millions counted as carried",
    FIG,
    STRAY,
    "stray = sorted({number for number in _numbers(prose) if number not in allowed and not any("
    "abs(number * 1e6 - known) <= known * 0.05 for known in allowed)})",
    "test_a_rounded_figure_with_a_magnitude_word_is_not_carried",
)
mutate(
    "tokens without a digit read as numbers",
    FIG,
    "        if any(char.isdigit() for char in token):",
    "        if True:",
    "test_words_float_would_read_are_not_figures",
)
for ident, char, label in (
    ("dollar", "$", "dollar sign"),
    ("percent", "%", "percent sign"),
    ("bold", "*", "markdown asterisk"),
    ("parenthesis", "(", "opening parenthesis"),
    ("double_quote", '\\"', "double quote"),
    ("semicolon", ";", "semicolon"),
):
    mutate(
        f"{label} not stripped from a figure",
        FIG,
        EDGE,
        EDGE.replace(char, "", 1),
        f"test_marks_around_a_figure_do_not_hide_it[{ident}]",
    )
mutate(
    "sentinel cells carried (text form)",
    FIG,
    MISSING,
    MISSING.replace("CENSUS_MISSING", "()"),
    "test_a_sentinel_written_in_the_models_text_is_replaced",
)
t = "test_the_dataset_decides_which_span_the_text_may_name"
mutate(
    "dataset digits not carried (span)",
    FIG,
    'text = "".join(char if char.isdigit() else " " for char in text)',
    "text = text",
    t,
)
mutate(
    "any span carried whatever the dataset",
    FIG,
    'text = "".join(char if char.isdigit() else " " for char in text)',
    'text = "1 5"',
    t,
)
mutate(
    "GEO_ID read whole so its FIPS digits are lost",
    FIG,
    'text = str(cell).split("US")[-1] if key == "GEO_ID" else str(cell)',
    "text = str(cell)",
    "test_the_fips_digits_of_a_geoid_are_carried",
)
for field in (
    "requested_years",
    "attempted_years",
    "succeeded_years",
    "failed_years",
    "omitted_years",
):
    mutate(
        f"{field.replace('_', ' ')} not carried",
        FIG,
        YEARS,
        without_year_field(field),
        f"test_every_year_the_fetch_reports_may_be_named[{field}]",
    )
mutate(
    "period column not carried",
    FIG,
    MISSING,
    MISSING.replace("cell in CENSUS_MISSING", 'cell in CENSUS_MISSING or key == "period"'),
    "test_the_period_of_a_vintage_may_be_named_in_a_real_response",
)

# --- what is rendered --------------------------------------------------------------------------
t = "test_a_row_with_no_year_or_dataset_renders_no_vintage_text"
mutate(
    "missing dataset or year rendered as None",
    FIG,
    VINTAGE,
    "vintage = f\"{row.get('dataset')} {year}\".strip()",
    t,
)
mutate("empty place or vintage left as a dangling comma", FIG, JOIN, JOIN.replace(" if p)", ")"), t)
mutate("dataset left out of the vintage (no year)", FIG, DATASET_YEAR, "(None, year)", t)
mutate(
    "year left out of the vintage (no dataset)", FIG, DATASET_YEAR, '(row.get("dataset"), "")', t
)
t = "test_a_row_missing_part_of_its_place_renders_the_rest"
mutate("missing GEOID rendered as (None)", FIG, GEOID, 'f"({geoid})"', t)
mutate("missing place name rendered as None", FIG, PLACE, '(str(row.get("NAME")), f"({geoid})"', t)
t = "test_only_estimate_columns_are_rendered_as_figures"
mutate("margin and id columns rendered as figures", FIG, CELLS, 'if "_" in key', t)
mutate("NAME rendered as a figure", FIG, CELLS, 'if key.endswith("E")', t)
mutate("annotation columns rendered as figures", FIG, CELLS, 'if "E" in key[-2:] and "_" in key', t)
t = "test_one_wide_row_shows_twenty_figures_and_counts_the_rest"
mutate("no cap on figures shown (wide row)", FIG, CAP, "    return found, len(found)", t)
mutate("cut figures not counted (wide row)", FIG, "if total > MAX_FIGURES:", "if False:", t)
mutate(
    "shown count reported as the total (wide row)",
    FIG,
    COUNT,
    COUNT.replace("{total}", "{MAX_FIGURES}"),
    t,
)
mutate(
    "table facts printed when no figure was shown",
    FIG,
    LOOP,
    '    for dataset, year in [("acs5", "2023")]:',
    "test_a_result_with_a_place_but_no_estimate_cells_renders_no_figures",
)
t = "test_the_universe_comes_from_the_table_facts_then_from_the_record"
mutate(
    "record universe not used when the facts lack one", FIG, UNIVERSE, 'facts.get("universe")', t
)
mutate(
    "record universe preferred over the vintage's own",
    FIG,
    UNIVERSE,
    'getattr(record, "universe", "") or facts.get("universe")',
    t,
)
mutate(
    "year prefix printed even when every vintage agrees",
    FIG,
    "text if len(about) == 1 else f\"{', '.join(years)}: {text}\"",
    "f\"{', '.join(years)}: {text}\"",
    "test_the_facts_line_is_printed_once_when_every_vintage_agrees",
)
mutate(
    "decimals dropped from a shown figure",
    FIG,
    'f"{int(whole):,}{dot}{fraction}"',
    'f"{int(whole):,}"',
    "test_a_figure_keeps_its_decimals_and_its_sign",
)
mutate(
    "sign dropped from a shown figure",
    FIG,
    SHOWN,
    SHOWN.replace("int(whole)", "abs(int(whole))"),
    "test_a_figure_keeps_its_decimals_and_its_sign",
)
mutate(
    "zero margin shown as not published",
    FIG,
    "if moe else 'not published'",
    "if moe and moe != '0' else 'not published'",
    "test_a_figure_keeps_its_decimals_and_its_sign",
)

# --- labels ------------------------------------------------------------------------------------
t = "test_a_label_loses_its_estimate_prefix_and_joins_its_levels"
mutate(
    "estimate prefix left on the label",
    FIG,
    LABEL,
    LABEL.replace('.removeprefix("Estimate!!")', ""),
    t,
)
mutate("label levels joined with a colon", FIG, LABEL, LABEL.replace('" - "', '": "'), t)
mutate(
    "labels returned for variables nobody asked for",
    FIG,
    "for key in wanted & found.keys()",
    "for key in found.keys()",
    t,
)
mutate(
    "variables the metadata lacks looked up anyway",
    FIG,
    "for key in wanted & found.keys()",
    "for key in wanted",
    t,
)
mutate(
    "only the last variable of a vintage looked up",
    FIG,
    "wanted.setdefault(year, set()).add(key)",
    "wanted[year] = {key}",
    "test_labels_are_asked_for_every_variable_of_a_vintage",
)
mutate(
    "no cap on figures shown (labels)",
    FIG,
    CAP,
    "    return found, len(found)",
    "test_labels_are_asked_only_for_the_figures_that_are_shown",
)
mutate(
    "rows without a vintage looked up",
    FIG,
    "        if year.isdigit():",
    "        if True:",
    "test_rows_without_a_vintage_are_not_looked_up",
)
mutate(
    "labels read from the wrong fetch attribute",
    FIG,
    'getattr(getattr(record, "fetch", None), "labels", None)',
    'getattr(getattr(record, "fetch", None), "label", None)',
    "test_assemble_renders_the_labels_the_fetch_carried",
)
mutate(
    "labels looked up in the wrong dataset",
    FET,
    FETCH_LABELS,
    FETCH_LABELS.replace("plan.dataset", '"acs1"'),
    "test_fetch_data_looks_labels_up_in_the_dataset_it_fetched",
)

# --- the take_chart hook -----------------------------------------------------------------------
mutate(
    "text checked even without a record",
    CON,
    HOOK,
    "    if True:",
    "test_take_chart_without_a_record_leaves_the_text_alone",
)
mutate(
    "warning appended to a missing list",
    CON,
    "if problem and warnings is not None:",
    "if problem:",
    "test_take_chart_without_a_warnings_list_still_replaces_the_text",
)
t = "test_take_chart_warns_only_when_it_replaced_the_text"
mutate(
    "warning added when the text was kept",
    CON,
    "if problem and warnings is not None:",
    "if warnings is not None:",
    t,
)
mutate("warning never added (hook)", CON, APPEND, "            pass", t)
for form in ("bare_json", "fenced_json"):
    mutate(
        f"envelope checked instead of its answer ({form})",
        CON,
        CHECKED,
        CHECKED.replace("(cleaned,", "(answer,"),
        f"test_take_chart_checks_the_text_inside_the_envelope[{form}]",
    )
mutate(
    "plain-text reply not checked",
    CON,
    HOOK,
    "    if record is not None and payload is not None:",
    "test_take_chart_checks_a_reply_that_is_not_json",
)
mutate(
    "text not checked when nothing was fetched",
    CON,
    HOOK,
    "    if record is not None and rows:",
    "test_take_chart_after_a_failed_fetch_keeps_a_clean_text_and_replaces_a_figure",
)
mutate(
    "clean text dropped when nothing was fetched (hook)",
    FIG,
    '        return prose, ""',
    '        return "", ""',
    "test_take_chart_after_a_failed_fetch_keeps_a_clean_text_and_replaces_a_figure",
)
mutate(
    "model chart reset when the text is dropped",
    CON,
    APPEND,
    APPEND + "\n            saw = False",
    "test_the_models_own_chart_spec_survives_when_the_text_is_replaced",
)

# Defect-sensitivity: repair each defect in api/src and the xfail(strict) test must flip to XPASS.
FIXES: list[Case] = []
glued = "test_a_figure_glued_to_a_mark_float_cannot_read_is_still_checked"
for ident, name, file, old, new in (
    ("k_suffix", "k stripped from a figure", FIG, EDGE, EDGE.replace("$%", "$%k")),
    ("plus_minus", "plus-minus stripped from a figure", FIG, EDGE, EDGE.replace("$%", "$%±")),
    (
        "unicode_minus",
        "unicode minus a break between figures",
        FIG,
        BREAKS,
        BREAKS.replace("/|", "/|−").replace('"     ")', '"      ")'),
    ),
    (
        "curly_quotes",
        "curly quotes stripped from a figure",
        FIG,
        EDGE,
        EDGE.replace("$%", "$%“”"),
    ),
    (
        "currency_code",
        "currency code stripped from a figure",
        FIG,
        EDGE,
        EDGE.replace("$%", "$%USD"),
    ),
):
    FIXES.append(Case(name, file, old, new, f"{T}{glued}[{ident}]"))


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


def run(case: Case) -> tuple[int, str]:
    path = ROOT / case.file
    original = path.read_bytes()
    text = original.decode("utf-8")
    assert text.count(case.old) == 1, f"{case.name}: old text occurs {text.count(case.old)} times"
    assert case.old != case.new, f"{case.name}: nothing changed"
    try:
        path.write_bytes(text.replace(case.old, case.new).encode("utf-8"))
        return pytest(case.test)
    finally:
        path.write_bytes(original)


def main() -> int:
    print(HEADER)
    code, out = pytest(TEST_FILE)
    assert code == 0, out
    print(f"GOOD unmutated code\n     {summary(out)}\n")
    caught = confirmed = 0
    for case in CASES:
        code, out = run(case)
        text = summary(out)
        # exit 1 is a test failure; a collection or import error would be exit 2 or an "error" count
        ok = code == 1 and " error" not in text and "failed" in text
        caught += ok
        print(f"BAD  mutation: {case.name}  [{case.test.removeprefix(T)}]")
        print(f"     {'CAUGHT' if ok else 'NOT CAUGHT'}  [{text!r}]")
    for case in FIXES:
        code, out = run(case)
        text = summary(out)
        ok = code == 1 and "XPASS(strict)" in out
        confirmed += ok
        print(f"FIX  defect repaired in api/src: {case.name}  [{case.test.removeprefix(T)}]")
        print(f"     {'XPASS(strict)' if ok else 'NOT XPASS'}  [{text!r}]")
    clean = subprocess.run(["git", "diff", "--quiet", "--", "api/src"], cwd=ROOT, check=False)
    assert clean.returncode == 0, "api/src differs from HEAD after the mutations"
    print(
        f"\nTALLY  {caught} of {len(CASES)} mutations CAUGHT; "
        f"{confirmed} of {len(FIXES)} defect repairs turned the xfail into a strict XPASS"
    )
    code, out = pytest(TEST_FILE)
    assert code == 0, out
    print("GOOD restored code (git diff --quiet -- api/src is clean)")
    print(f"     {summary(out)}")
    return 0 if caught == len(CASES) and confirmed == len(FIXES) else 1


if __name__ == "__main__":
    sys.exit(main())
