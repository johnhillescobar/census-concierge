"""Tests for the claims the process docs make about themselves.

`docs/playbooks/run-slice.md` and `docs/process-evidence.md` argue from evidence:
pinned git transcripts, an adversarial matrix where every row must name the slice
or PR whose defect it would have caught, a handoff rule. Each of those is a factual
claim about a repository that keeps moving, and nothing checked any of them until
this module.

It is deliberately narrow: it does not grade the prose, it re-runs what the
documents say they ran and compares. A pinned transcript that stops reproducing is
the failure this exists to catch, because the whole argument of the playbook is
that only real output counts.

**Nothing here may skip.** A guard that quietly passes when it cannot run (a
shallow clone, an unreachable commit) is worse than no guard: these tests fail and
say what to fix.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml
from docs_helpers import (
    LOOKALIKES,
    backticked,
    cells,
    code_spans,
    fenced_blocks,
    grep,
    prose_only,
    section,
    table_rows,
)

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = ROOT / "CLAUDE.md"
PROCESS_EVIDENCE_MD = ROOT / "docs" / "process-evidence.md"
RUN_SLICE_MD = ROOT / "docs" / "playbooks" / "run-slice.md"
CHECK_YML = ROOT / ".github" / "workflows" / "check.yml"

#: The adversarial matrix header in docs/process-evidence.md. Its preamble states
#: the rule this file enforces: a row that cannot name a slice or PR does not
#: belong there.
MATRIX_HEADER = "| Probe | Caught in |"

#: How many git transcripts the process docs pin between them. Asserted rather
#: than inferred: a parser change that returns nothing would otherwise turn every
#: transcript test below into a silent pass over an empty list.
EXPECTED_TRANSCRIPTS = 2

#: The matrix starts seeded from slice-0 findings and grows one row per real
#: defect. This floor catches it being emptied, which `table_rows` (asserts
#: non-empty) would not - one surviving row passes that.
MATRIX_MIN_ROWS = 4

#: The trios: one canonical playbook, a Claude Code skill and a Cursor command
#: that are thin pointers to it. Nothing else checks that the pointers resolve.
TRIOS = ("run-slice", "review-pr")

CITATION = re.compile(r"(?:PR #\d+|slice-\d+)")


def claude_md() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def evidence_md() -> str:
    return PROCESS_EVIDENCE_MD.read_text(encoding="utf-8")


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        # `-c core.abbrev=7` so a caller's `[core] abbrev = 12` does not fail a
        # transcript for a reason that has nothing to do with the docs drifting.
        ["git", "-c", "core.abbrev=7", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


# --------------------------------------------------------------------------
# Re-running the pinned transcripts


def transcript_blocks() -> list[tuple[str, str]]:
    """Every `(source, block)` in the process docs whose block runs git.

    Both files are scanned, not just the evidence file where the transcripts
    live today, so one re-added to a playbook later gets the same reproduction
    check instead of being silently dropped.
    """
    return [
        (source, block)
        for source, text in (
            ("docs/process-evidence.md", evidence_md()),
            ("CLAUDE.md", claude_md()),
        )
        for block in fenced_blocks(text)
        if block.startswith("$ git ")
    ]


def steps(block: str) -> list[tuple[str, str]]:
    """Split one transcript block into (command, expected output) pairs."""
    pairs: list[tuple[str, str]] = []
    command: str | None = None
    output: list[str] = []
    for line in block.splitlines():
        if line.startswith("$ "):
            if command is not None:
                pairs.append((command, "\n".join(output)))
            command = line[2:]
            output = []
        else:
            output.append(line)
    if command is not None:
        pairs.append((command, "\n".join(output)))
    return pairs


def run_transcript_command(command: str) -> str:
    """Execute one documented git command and return its stdout.

    The pipeline is re-implemented rather than handed to a shell: `shell=True`
    runs through `cmd.exe` on Windows, where `grep` does not exist, and this
    suite has to give the same answer on both platforms.

    An unrecognised shape **raises** - adding a transcript this cannot execute
    must break the build, not quietly reduce what is checked.
    """
    show = re.fullmatch(r"git show (\S+) \| grep (-n|-c) [\"']?(.+?)[\"']?", command)
    if show:
        ref, flag, pattern = show.groups()
        result = git("show", ref)
        assert result.returncode == 0, (
            f"`git show {ref}` failed: {result.stderr.strip()}. If this is CI, the "
            "checkout is shallow - check.yml must set fetch-depth: 0."
        )
        return grep(pattern, result.stdout, count=flag == "-c")

    raise AssertionError(
        f"no executor for the documented command {command!r}. Add one rather than "
        "letting the transcript go unchecked."
    )


def test_the_expected_number_of_transcripts_are_pinned() -> None:
    """Anti-vacuity. Every transcript test below iterates this list; a broken
    `fenced_blocks` would empty it and turn the module green checking nothing."""
    assert len(transcript_blocks()) == EXPECTED_TRANSCRIPTS


def test_every_pinned_commit_is_reachable() -> None:
    """Fails rather than skips when history is missing.

    `actions/checkout@v4` clones to depth 1 by default. The remedy is
    `fetch-depth: 0`; the point of this test is that its absence is loud.
    """
    assert git("rev-parse", "--is-shallow-repository").stdout.strip() == "false", (
        "shallow clone: the pinned transcripts cannot be re-run. Set fetch-depth: 0."
    )
    refs = {
        ref.split(":", 1)[0]
        for _source, block in transcript_blocks()
        for command, _ in steps(block)
        for ref in re.findall(r"git show (\S+)", command)
    }
    assert refs, "no pinned commits found; the parser is not seeing the transcripts"
    for ref in sorted(refs):
        assert git("cat-file", "-e", f"{ref}^{{commit}}").returncode == 0, (
            f"{ref} is not in this clone, so the transcript pinned to it cannot be "
            "re-run. Fetch full history."
        )


@pytest.mark.parametrize("index", range(EXPECTED_TRANSCRIPTS))
def test_each_pinned_transcript_still_reproduces(index: int) -> None:
    """The documents' central claim, applied to the documents."""
    source, block = transcript_blocks()[index]
    for command, expected in steps(block):
        actual = run_transcript_command(command)
        assert actual == expected.rstrip("\n"), (
            f"`{command}` no longer produces what {source} records.\n"
            f"documented:\n{expected}\n\nactual:\n{actual}"
        )


# --------------------------------------------------------------------------
# The adversarial matrix


def matrix_citation(row: str) -> str:
    """The "Caught in" cell of one matrix row."""
    columns = cells(row)
    assert len(columns) >= 2, f"matrix row has no 'Caught in' column: {row[:80]!r}"
    return columns[1]


def test_every_matrix_row_cites_a_slice_or_pr() -> None:
    """The rule the matrix opens with. It erodes one plausible row at a time, so
    it is enforced rather than trusted."""
    for row in table_rows(evidence_md(), MATRIX_HEADER):
        caught_in = matrix_citation(row)
        assert CITATION.search(caught_in), f"matrix row cites no slice or PR: {row[:80]!r}"


def test_the_matrix_has_not_quietly_emptied() -> None:
    assert len(table_rows(evidence_md(), MATRIX_HEADER)) >= MATRIX_MIN_ROWS


def test_every_matrix_citation_resolves_to_a_defect_section() -> None:
    """Each `slice-N` / `PR #N` the matrix cites must resolve to a `### slice-N`
    or `### PR #N` heading in the defect index below it.

    Anchored to the heading, not a substring: `slice-0` appears throughout the
    evidence file's prose, so a substring check would pass with the section
    deleted - the exact failure this catches.
    """
    cited = {
        token
        for row in table_rows(evidence_md(), MATRIX_HEADER)
        for token in CITATION.findall(matrix_citation(row))
    }
    assert cited, "no citations found in the matrix; the parser is not seeing the rows"
    headings = set(re.findall(r"(?m)^### (slice-\d+|PR #\d+)$", evidence_md()))
    assert headings, "no `### slice-N` / `### PR #N` sections in docs/process-evidence.md"
    missing = sorted(cited - headings)
    assert not missing, (
        f"the matrix cites {missing} with no matching `### ...` section in docs/process-evidence.md"
    )


# --------------------------------------------------------------------------
# Characters, pointers, CI


@pytest.mark.parametrize(
    "path",
    [CLAUDE_MD, PROCESS_EVIDENCE_MD, RUN_SLICE_MD, ROOT / "docs" / "playbooks" / "review-pr.md"],
    ids=lambda p: p.name,
)
def test_no_lookalike_characters_inside_code_spans(path: Path) -> None:
    """Prose may use typographic characters; commands and code may not. A
    fullwidth pipe inside a documented command reproduces wrongly and silently."""
    spans = code_spans(path.read_text(encoding="utf-8"))
    assert spans, f"no code spans found in {path.name}; the parser is not seeing them"
    for span in spans:
        for character, description in LOOKALIKES.items():
            assert character not in span, f"{description} in {path.name} code span: {span[:60]!r}"


@pytest.mark.parametrize("name", TRIOS)
def test_the_trio_pointers_resolve(name: str) -> None:
    """The skill and the command must name the canonical playbook, and it must
    exist. A rename that updates one pointer and not the others is the drift."""
    playbook = ROOT / "docs" / "playbooks" / f"{name}.md"
    skill = ROOT / ".claude" / "skills" / name / "SKILL.md"
    command = ROOT / ".cursor" / "commands" / f"{name}.md"
    assert playbook.is_file(), f"missing canonical playbook {playbook}"
    for pointer in (skill, command):
        assert pointer.is_file(), f"missing trio pointer {pointer}"
        assert f"docs/playbooks/{name}.md" in pointer.read_text(encoding="utf-8"), (
            f"{pointer} does not point at docs/playbooks/{name}.md"
        )


def test_run_slice_playbook_states_the_handoff_rule() -> None:
    """The context-management property the playbook exists for, asserted in the
    section that makes it so a rewrite inverting it fails here."""
    body = section(RUN_SLICE_MD.read_text(encoding="utf-8"), "## The handoff rule").lower()
    assert "persist" in body
    assert "before the next" in body
    assert "reconstruct" in body
    assert "never from conversation" in body


def test_ci_invariants_job_fetches_full_history() -> None:
    """`check_invariants --base` needs the merge base. The claim (a comment in
    check.yml) and the config are separate; a local run cannot tell the
    difference because this clone is never shallow. Parsed, not grepped."""
    workflow = yaml.safe_load(CHECK_YML.read_text(encoding="utf-8"))
    jobs = [
        job
        for job in workflow["jobs"].values()
        if any("check_invariants" in str(step.get("run", "")) for step in job["steps"])
    ]
    assert jobs, "no job in check.yml runs check_invariants.py"
    for job in jobs:
        depths = [
            (step.get("with") or {}).get("fetch-depth")
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]
        assert depths, "the invariants job has no actions/checkout step"
        for depth in depths:
            assert depth is not None and int(depth) == 0, (
                "actions/checkout defaults to depth 1, which cannot resolve the merge "
                "base; the invariants job must set fetch-depth: 0."
            )


def test_process_evidence_has_code_spans() -> None:
    """Standalone anti-vacuity for the lookalike sweep's parser."""
    assert len(code_spans(evidence_md())) > 10


def test_run_slice_playbook_has_code_spans() -> None:
    assert len(code_spans(RUN_SLICE_MD.read_text(encoding="utf-8"))) > 5


# --------------------------------------------------------------------------
# The helpers' own defensive branches
#
# Each guards a case no document in the repo contains today, so the
# document-level tests above would agree with a broken implementation.


def test_cells_respects_an_escaped_pipe() -> None:
    row = r"| **probe `a \| b`** | slice-0: something |"
    assert cells(row) == [r"**probe `a \| b`**", "slice-0: something"]
    assert CITATION.search(cells(row)[1])


def test_cells_handles_an_ordinary_row() -> None:
    assert cells("| Probe | Caught in |") == ["Probe", "Caught in"]


def test_grep_applies_the_pattern_as_a_regex() -> None:
    text = "def one():\n    indented def two():\ndef three():"
    assert grep("^def ", text, count=False) == "1:def one():\n3:def three():"
    assert grep("^def ", text, count=True) == "2"
    assert grep("def ", text, count=True) == "3"


@pytest.mark.parametrize(
    "text",
    ["prose\n\n```bash\nunclosed\n", "```\nopened and never closed\n\n```\n\n```\n"],
    ids=["single-unclosed", "odd-number-of-fences"],
)
def test_an_unbalanced_fence_is_loud(text: str) -> None:
    with pytest.raises(ValueError, match="unbalanced"):
        fenced_blocks(text)
    with pytest.raises(ValueError, match="unbalanced"):
        prose_only(text)


def test_backticked_does_not_span_lines() -> None:
    text = "here is a lone ` backtick\nand a line later `real span` end"
    assert backticked(text) == ["real span"]


def test_section_stops_at_the_next_heading() -> None:
    text = (
        "# Doc\n\n## First\n\nhandoff rule: persist before the next phase\n\n"
        "## Second\n\nsomething else entirely\n"
    )
    assert "persist" in section(text, "## First")
    assert "persist" not in section(text, "## Second")
    assert "something else" not in section(text, "## First")
