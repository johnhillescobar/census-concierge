"""Read the budget change log at the bottom of budgets.toml, without a regex.

Two gates read it: `check_budgets.py` for the owner's p95 `[waiver]` lines, and
`check_invariants.py` for `old -> new` limit changes and for new waivers under `--base`.
"""

from __future__ import annotations


def entries(text: str) -> list[list[str]]:
    """The words of each log entry below the "budget change log" header.

    An entry is `<date> [<section>] <field> ...`. One physical line can hold two entries
    joined by "# ", so every comment line is split on that.
    """
    found: list[list[str]] = []
    in_log = False
    for line in text.splitlines():
        if "budget change log" in line.lower():
            in_log = True
        if in_log and line.startswith("#"):
            found.extend(entry.split() for entry in line.split("# ")[1:])
    return found


def p95_waiver(text: str, run: str, p95: float) -> str:
    """The reason from `[waiver] p95_latency_seconds <run> <value> <ticket> <why>`, or "".

    The owner writes that line in budgets.toml. It is bound to one run id (demo.generated_at) and
    value, so the next over-ceiling run is unwaived until the owner decides again.
    """
    for words in entries(text):
        if len(words) < 6 or words[1:4] != ["[waiver]", "p95_latency_seconds", run]:
            continue
        try:
            logged = float(words[4])
        except ValueError:
            continue
        if abs(logged - p95) < 0.0005:
            return " ".join(words[5:])
    return ""
