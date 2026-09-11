"""Parsers shared by the tests that check this repo's prescriptive docs against reality.

Ported from job_serach_agent, trimmed to what census-concierge's `test_process`
needs. Each piece carries a correction a fresh copy would not inherit:
`fenced_blocks` is a line-state scan because the obvious regex pairs a *closing*
fence with the next *opening* one; `prose_only` exists because ``` fences are
themselves backticks; `backticked` is line-bounded so one stray tick does not
swallow a paragraph.

Not a package - `api/tests/` has no `__init__.py`, so pytest's prepend import mode
puts this directory on `sys.path` and `from docs_helpers import ...` resolves.
"""

from __future__ import annotations

import re

#: Characters that look like ASCII and are not. A lookalike inside a documented
#: command reproduces wrongly and silently. Keyed by codepoint, not by a literal:
#: a literal is invisible in a diff and in review, which is how one gets into a
#: document in the first place.
LOOKALIKE_CODEPOINTS: tuple[tuple[int, str], ...] = (
    (0xFF5C, "fullwidth vertical line"),
    (0x2013, "en dash"),
    (0x2014, "em dash"),
    (0x2018, "left single quote"),
    (0x2019, "right single quote"),
    (0x201C, "left double quote"),
    (0x201D, "right double quote"),
    (0x00A0, "non-breaking space"),
)

LOOKALIKES = {chr(code): name for code, name in LOOKALIKE_CODEPOINTS}


def backticked(text: str) -> list[str]:
    """Every `code` token in a chunk of markdown, single-line only.

    `[^`]+` matches newlines, so one unclosed backtick pairs with the next one
    further down and returns the prose between them as a code span - which then
    fails the lookalike check pointing at an ordinary sentence.
    """
    return re.findall(r"`([^`\n]+)`", text)


def fenced_blocks(text: str) -> list[str]:
    """The contents of every ``` fenced block, dedented to its fence.

    A line-state scan, not a regex: ```` ```[a-z]*\\n(.*?)``` ```` pairs a
    *closing* fence with the next *opening* one. Indented fences count - a pinned
    transcript nested in a list item must not be invisible to the parser, which
    is the vacuous-guard failure this repo has been bitten by before.
    """
    blocks: list[str] = []
    current: list[str] | None = None
    indent = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if current is None:
                current = []
                indent = len(line) - len(stripped)
            else:
                blocks.append("\n".join(current))
                current = None
            continue
        if current is not None:
            prefix = len(line) - len(line.lstrip())
            current.append(line[min(indent, prefix) :])
    if current is not None:
        raise ValueError(
            "unbalanced ``` fence: the document opens a block it never closes, so "
            "everything after it would be dropped from these checks"
        )
    return blocks


def prose_only(text: str) -> str:
    """`text` with every fenced block removed.

    `backticked` must never run over a whole document: the ``` fences are
    themselves backticks and pair with inline ones.
    """
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            out.append(line)
    if inside:
        raise ValueError(
            "unbalanced ``` fence: everything after the unclosed fence would be "
            "silently dropped from the prose"
        )
    return "\n".join(out)


def code_spans(text: str) -> list[str]:
    """Every inline code span and fenced block in a document.

    One function so the check has a single surface and "did the parser return
    anything at all" is a question a test can ask.
    """
    return backticked(prose_only(text)) + fenced_blocks(text)


def cells(row: str) -> list[str]:
    """The cells of one markdown table row, respecting escaped pipes.

    A plain `row.split("|")` shifts every column when a cell contains an escaped
    pipe, so a row that does cite a slice gets reported as citing none.
    """
    parts = re.split(r"(?<!\\)\|", row.strip())
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [part.strip() for part in parts]


def table_rows(text: str, header: str) -> list[str]:
    """The body rows of the markdown table introduced by `header`."""
    assert header in text, f"no table with header {header!r}"
    rows: list[str] = []
    for line in text.split(header, 1)[1].splitlines():
        stripped = line.strip()
        if not stripped:
            if rows:
                break
            continue
        if not stripped.startswith("|"):
            break
        if set(stripped) <= set("|- "):  # the |---|---| separator
            continue
        rows.append(stripped)
    assert rows, f"table {header!r} has no rows"
    return rows


def section(text: str, heading: str) -> str:
    """The body of one markdown section, up to the next heading of any level.

    Lets a test assert a claim appears *in the section that makes it* rather than
    anywhere in a long document, where two unanchored substring checks can be
    satisfied from opposite ends of the file.
    """
    assert heading in text, f"no section {heading!r}"
    body = text.split(heading, 1)[1]
    lines: list[str] = []
    for line in body.splitlines()[1:]:
        if line.startswith("#"):
            break
        lines.append(line)
    return "\n".join(lines)


def grep(pattern: str, text: str, *, count: bool) -> str:
    """`grep -n` / `grep -c` over `text`, as the shell tool behaves.

    A regex, because that is what `grep` is. Substring matching agrees for the
    patterns pinned today and diverges the moment one has an anchor or a class -
    at which point a transcript test would assert a command it never ran still
    reproduces.
    """
    matched = [
        (number, line)
        for number, line in enumerate(text.splitlines(), start=1)
        if re.search(pattern, line)
    ]
    if count:
        return str(len(matched))
    return "\n".join(f"{number}:{line}" for number, line in matched)
