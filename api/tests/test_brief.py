"""The phase brief: it opens with the two status commands, and it refuses to start a phase on
criteria that differ from the ones approved at pre-flight."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import brief  # noqa: E402
import closure  # noqa: E402

DESCRIPTION = "Why. Context.\nAC1. The thing works.\nAC2. It fails closed.\nTC1. A test.\nDecisions"


def approved(text: str = DESCRIPTION, **extra: Any) -> dict[str, Any]:
    return {
        "approved_ids": closure.required_ids(text),
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
