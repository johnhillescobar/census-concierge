"""The phase brief: it opens with the two status commands, and it refuses to start a phase on
criteria that differ from the ones approved at pre-flight."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import brief  # noqa: E402
import closure  # noqa: E402

DESCRIPTION = "Why. Context.\nAC1. The thing works.\nAC2. It fails closed.\nTC1. A test.\nDecisions"


def approved(text: object = DESCRIPTION, **extra: Any) -> dict[str, Any]:
    return {
        "approved_ids": closure.required_ids(closure.adf_text(text)),
        "approved_sha256": closure.criteria_fingerprint(text),
        **extra,
    }


def amendment(text: str) -> dict[str, Any]:
    return {
        "id": "AC3",
        "date": "2026-11-26",
        "owner": "owner",
        "reason": "added on the owner's instruction",
        "destination": "this ticket",
        "criteria_sha256": closure.criteria_fingerprint(text),
    }


def test_the_approved_criteria_pass() -> None:
    assert brief.compare(approved(), DESCRIPTION, "gate2") == []


def test_editing_a_paragraph_that_is_not_a_criterion_passes() -> None:
    assert brief.compare(approved(), DESCRIPTION.replace("Context.", "More."), "gate1") == []


def test_a_criterion_added_in_jira_without_an_amendment_fails() -> None:
    live = DESCRIPTION + "\nAC3. A new one."
    problems = brief.compare(approved(), live, "gate1")
    assert any("AC3" in p and "not approved" in p for p in problems)


def test_a_criterion_removed_in_jira_without_an_amendment_fails() -> None:
    live = DESCRIPTION.replace("AC2. It fails closed.\n", "")
    assert any("AC2" in p and "gone" in p for p in brief.compare(approved(), live, "gate1"))


def test_a_criterion_reworded_with_its_id_unchanged_fails() -> None:
    live = DESCRIPTION.replace("It fails closed.", "It fails open.")
    assert closure.required_ids(live) == closure.required_ids(DESCRIPTION)
    problems = brief.compare(approved(), live, "implement")
    assert any("text changed" in p for p in problems)


def test_an_amendment_naming_the_new_fingerprint_lets_the_change_through() -> None:
    live = DESCRIPTION + "\nAC3. A new one."
    assert brief.compare(approved(amendment=[amendment(live)]), live, "gate2") == []


def test_an_amendment_for_other_text_does_not() -> None:
    live = DESCRIPTION + "\nAC3. A new one."
    stale = amendment(DESCRIPTION + "\nAC3. Something else.")
    assert brief.compare(approved(amendment=[stale]), live, "gate2") != []


def test_preflight_may_start_with_nothing_approved_and_no_later_phase_may() -> None:
    assert brief.compare(None, DESCRIPTION, "preflight") == []
    for phase in ("implement", "gate1", "gate2", "final"):
        assert brief.compare(None, DESCRIPTION, phase) != [], phase


@pytest.mark.parametrize("phase", brief.PHASES)
def test_every_brief_opens_with_the_two_status_commands(phase: str) -> None:
    text = brief.brief(phase, "CC-9", [], "evidence/slice-6/cc-9")
    head = text.splitlines()[1:3]
    assert [line.strip() for line in head] == brief.status_commands("CC-9")


def test_the_status_commands_name_the_ticket_and_its_closure_file() -> None:
    fetch, check = brief.status_commands("CC-9")
    assert fetch.endswith("jira_fetch.py issue CC-9 --md")
    assert "evidence/closure/CC-9.toml" in check and check.endswith("--pre-merge")


def contradiction(text: str) -> bool:
    return "list each contradiction" in " ".join(text.split())


def test_the_gate_2_brief_asks_for_a_contradiction_read_when_a_rule_file_changes() -> None:
    text = brief.brief("gate2", "CC-9", ["CLAUDE.md", "api/src/ask.py"], "e")
    assert contradiction(text) and "CLAUDE.md" in text


def test_the_gate_2_brief_omits_it_for_a_change_to_api_src_only() -> None:
    assert not contradiction(brief.brief("gate2", "CC-9", ["api/src/ask.py"], "e"))


def test_the_gate_2_brief_asks_for_it_when_git_cannot_list_the_change() -> None:
    assert contradiction(brief.brief("gate2", "CC-9", None, "e"))


@pytest.mark.parametrize("phase", ["preflight", "implement", "gate1", "final"])
def test_no_other_phase_asks_for_the_contradiction_read(phase: str) -> None:
    assert not contradiction(brief.brief(phase, "CC-9", ["CLAUDE.md"], "e"))


def test_only_the_gate_2_brief_sends_the_bug_pass_to_the_cold_agent() -> None:
    assert brief.COLD in brief.brief("gate2", "CC-9", [], "e")
    for phase in ("preflight", "implement", "gate1", "final"):
        assert brief.COLD not in brief.brief(phase, "CC-9", [], "e"), phase


def test_the_main_command_stops_with_no_brief_when_the_criteria_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "evidence" / "closure").mkdir(parents=True)
    manifest = tmp_path / "evidence" / "closure" / "CC-9.toml"
    manifest.write_text(
        'approved_ids = ["AC1", "AC2", "TC1"]\n'
        f'approved_sha256 = "{closure.criteria_fingerprint(DESCRIPTION)}"\n',
        encoding="utf-8",
    )
    live = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            for line in (DESCRIPTION + "\nAC3. New.").splitlines()
        ],
    }
    monkeypatch.setattr(brief, "ROOT", tmp_path)
    monkeypatch.setattr(brief.jira_fetch, "load_env", lambda root=None: None)
    monkeypatch.setattr(brief.jira_fetch, "_issue", lambda key: {"fields": {"description": live}})
    monkeypatch.setattr(sys, "argv", ["brief.py", "gate1", "cc-9"])
    assert brief.main() == 1
    captured = capsys.readouterr()
    assert "CC-9 gate1 brief" not in captured.out and "AC3" in captured.err


def doc(text: str) -> dict[str, Any]:
    paragraphs = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]}
        for line in text.splitlines()
    ]
    return {"type": "doc", "content": paragraphs}


def run_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fields: dict[str, Any],
    manifest: str | None,
    *argv: str,
) -> int:
    (tmp_path / "evidence" / "closure").mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (tmp_path / "evidence" / "closure" / "CC-9.toml").write_text(manifest, encoding="utf-8")
    monkeypatch.setattr(brief, "ROOT", tmp_path)
    monkeypatch.setattr(brief.jira_fetch, "load_env", lambda root=None: None)
    monkeypatch.setattr(brief.jira_fetch, "_issue", lambda key: {"fields": fields})
    monkeypatch.setattr(brief, "changed_files", lambda base: [])
    monkeypatch.setattr(sys, "argv", ["brief.py", *argv])
    return brief.main()


DONE = {"name": "Done", "statusCategory": {"key": "done"}}
OPEN = {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}


LANDED = "a" * 40


def test_a_closed_ticket_stays_closed_judged_at_the_commit_its_record_landed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fields = {"status": DONE, "description": doc(DESCRIPTION)}
    monkeypatch.setattr(brief, "landed_at", lambda key, base: LANDED)
    assert run_main(tmp_path, monkeypatch, fields, None, "final", "CC-9", "--after-merge") == 1
    out = capsys.readouterr().out
    assert "brief." not in out and "no phase may start" in out and "stays closed" in out
    assert f"evidence/closure/CC-9.toml --head {LANDED}" in out
    assert "--pre-merge" not in out and "origin/main`)" in out  # run from a main checkout


def test_a_closed_ticket_with_no_record_on_main_points_at_jira(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fields = {"status": DONE, "description": doc(DESCRIPTION)}
    monkeypatch.setattr(brief, "landed_at", lambda key, base: None)
    assert run_main(tmp_path, monkeypatch, fields, None, "gate1", "CC-9") == 1
    out = capsys.readouterr().out
    assert "closure.py check" not in out and "close comment is the record" in out


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "docs" / "playbooks").mkdir(parents=True)
    (tmp_path / "docs" / "playbooks" / "old.md").write_text("rule\n", encoding="utf-8")
    (tmp_path / "evidence" / "closure").mkdir(parents=True)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.setattr(brief, "ROOT", tmp_path)
    return tmp_path


def test_the_landing_commit_is_the_last_one_on_main_that_changed_the_record(repo: Path) -> None:
    assert brief.landed_at("CC-9", "main") is None
    (repo / "evidence" / "closure" / "CC-9.toml").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "record")
    landed = git(repo, "rev-parse", "HEAD")
    (repo / "later.txt").write_text("later\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "later work")
    assert brief.landed_at("CC-9", "main") == landed


def test_a_rule_file_moved_out_of_the_rule_set_counts_as_a_rule_change(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "work")
    (repo / "docs" / "archive").mkdir()
    git(repo, "mv", "docs/playbooks/old.md", "docs/archive/old.md")
    git(repo, "commit", "-q", "-m", "move")
    changed = brief.changed_files("main")
    assert changed is not None and "docs/playbooks/old.md" in changed
    assert contradiction(brief.brief("gate2", "CC-9", changed, "e"))


def test_a_path_with_a_space_is_one_path(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "work")
    (repo / "docs" / "playbooks" / "two words.md").write_text("x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "space")
    assert brief.changed_files("main") == ["docs/playbooks/two words.md"]


def table_row(first: str, second: str) -> dict[str, Any]:
    cell = lambda text: {"type": "tableCell", "content": [para(text)]}  # noqa: E731
    return {"type": "tableRow", "content": [cell(first), cell(second)]}


def para(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def bullet(text: str, *subs: str) -> dict[str, Any]:
    nested = [{"type": "bulletList", "content": [bullet(s) for s in subs]}] if subs else []
    return {"type": "listItem", "content": [para(text), *nested]}


SHAPES = {
    "a table cell": lambda v: {
        "type": "doc",
        "content": [{"type": "table", "content": [table_row("AC1", f"p95 under {v} seconds")]}],
    },
    "a sub-bullet": lambda v: {
        "type": "doc",
        "content": [{"type": "bulletList", "content": [bullet("AC1. Latency", f"under {v}s")]}],
    },
    "a hard break": lambda v: {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "AC1. Latency"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": f"under {v}s"},
                ],
            }
        ],
    },
    "the paragraph under an id heading": lambda v: {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "AC1"}],
            },
            para(f"p95 under {v} seconds"),
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Notes"}],
            },
            para("not a criterion"),
        ],
    },
}


@pytest.mark.parametrize("shape", SHAPES)
def test_rewording_any_part_of_a_criterion_moves_the_fingerprint(shape: str) -> None:
    before, after = SHAPES[shape]("20"), SHAPES[shape]("200")
    assert closure.required_ids(closure.adf_text(before)) == ["AC1"]
    assert closure.criteria_fingerprint(before) != closure.criteria_fingerprint(after)
    assert brief.compare(approved(before), after, "gate1") != []


def test_a_paragraph_after_a_paragraph_criterion_is_not_part_of_it() -> None:
    before = {"type": "doc", "content": [para("AC1. It works."), para("Decisions: one.")]}
    after = {"type": "doc", "content": [para("AC1. It works."), para("Decisions: two.")]}
    assert closure.criteria_fingerprint(before) == closure.criteria_fingerprint(after)


def test_a_heading_section_ends_at_the_next_heading() -> None:
    before, after = (
        SHAPES["the paragraph under an id heading"]("20"),
        SHAPES["the paragraph under an id heading"]("20"),
    )
    after["content"][3] = para("edited, still not a criterion")
    assert closure.criteria_fingerprint(before) == closure.criteria_fingerprint(after)


def test_a_plain_paragraph_description_keeps_its_line_fingerprint() -> None:
    assert closure.criteria_fingerprint(doc(DESCRIPTION)) == closure.criteria_fingerprint(
        DESCRIPTION
    )


@pytest.mark.parametrize("missing", ["date", "owner", "reason", "destination"])
def test_an_incomplete_amendment_does_not_let_new_criteria_through(missing: str) -> None:
    live = DESCRIPTION + "\nAC3. A new one."
    row = amendment(live)
    del row[missing]
    assert brief.compare(approved(amendment=[row]), live, "gate2") != []


def test_a_manifest_that_is_not_toml_stops_with_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fields = {"status": OPEN, "description": doc(DESCRIPTION)}
    assert run_main(tmp_path, monkeypatch, fields, "approved_ids = [", "gate1", "CC-9") == 1
    assert "cannot be read" in capsys.readouterr().err


def test_after_merge_belongs_to_the_final_phase_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fields = {"status": OPEN, "description": doc(DESCRIPTION)}
    with pytest.raises(SystemExit) as stopped:
        run_main(tmp_path, monkeypatch, fields, None, "gate1", "CC-9", "--after-merge")
    assert stopped.value.code == 2


def test_an_open_ticket_is_judged_before_the_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sha = closure.criteria_fingerprint(DESCRIPTION)
    manifest = f'approved_ids = ["AC1", "AC2", "TC1"]\napproved_sha256 = "{sha}"\n'
    fields = {"status": OPEN, "description": doc(DESCRIPTION)}
    assert run_main(tmp_path, monkeypatch, fields, manifest, "gate1", "CC-9") == 0
    out = capsys.readouterr().out
    assert "CC-9 gate1 brief." in out and "CC-9.toml --pre-merge" in out


def test_a_record_from_before_approval_stops_and_prints_what_to_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fields = {"status": OPEN, "description": doc(DESCRIPTION)}
    assert run_main(tmp_path, monkeypatch, fields, 'ticket = "CC-9"\n', "gate1", "CC-9") == 1
    out = capsys.readouterr().out
    assert "brief." not in out
    assert 'approved_ids = ["AC1", "AC2", "TC1"]' in out
    assert f'approved_sha256 = "{closure.criteria_fingerprint(DESCRIPTION)}"' in out


def test_the_same_criteria_in_a_different_order_fail_and_say_so() -> None:
    live = "Why. Context.\nAC2. It fails closed.\nAC1. The thing works.\nTC1. A test.\nDecisions"
    problems = brief.compare(approved(), live, "gate1")
    assert any("different order" in p for p in problems)


def test_the_fingerprint_ignores_how_a_criterion_is_spaced_and_nothing_else() -> None:
    respaced = DESCRIPTION.replace("AC1. The thing works.", "AC1.  The thing\tworks.  ")
    assert closure.criteria_fingerprint(respaced) == closure.criteria_fingerprint(DESCRIPTION)
    assert brief.compare(approved(), respaced, "gate1") == []


def test_the_change_is_read_from_git_and_an_unknown_base_is_not_an_empty_change() -> None:
    assert brief.changed_files("HEAD") == []
    assert brief.changed_files("no-such-ref-for-the-brief-test") is None


def test_the_contradiction_trigger_covers_exactly_the_files_the_doc_budget_counts() -> None:
    import check_budgets

    counted = {
        p.relative_to(ROOT).as_posix()
        for pattern in check_budgets.DOC_PATTERNS
        for p in ROOT.glob(pattern)
        if p.is_file()
    }
    assert {".cursor/rules/00-guardrails.mdc", ".claude/skills/run-slice/SKILL.md"} <= counted
    assert all(check_budgets.is_prescriptive(rel) for rel in counted)
    for rel in ("api/src/ask.py", "docs/ARCHITECTURE.md", ".claude/agents/gate2-cold.md"):
        assert not check_budgets.is_prescriptive(rel), rel
    # a `*` stops at a `/`, as the glob that counts the lines does
    for rel in ("docs/playbooks/archive/old.md", ".claude/skills/a/b/SKILL.md", "x/AGENTS.md"):
        assert not check_budgets.is_prescriptive(rel), rel
