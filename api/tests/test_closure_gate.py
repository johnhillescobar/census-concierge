"""A ticket closes only on a whole AC/TC record: every ID present and PASS, evidence real and
current, new tests mutation-checked, and the post-merge run on a commit that is on the base."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_invariants as ci  # noqa: E402
import closure  # noqa: E402
import jira_transition as jt  # noqa: E402


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def make_repo(path: Path) -> Path:
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    (path / "src").mkdir()
    (path / "src" / "code.py").write_text("one\n")
    (path / "gate1.txt").write_text("42 of 42 mutations caught\n")
    (path / "e2e-post.txt").write_text("demo\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "first")
    return path


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Read-only for its tests: git is slow to start here, so they share one repository."""
    return make_repo(tmp_path_factory.mktemp("shared"))


@pytest.fixture
def fresh(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


FAKE = "a" * 40  # a head for tests that never ask git


def sha(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def row(repo: Path, name: str = "AC1", **fields: Any) -> dict[str, Any]:
    made: dict[str, Any] = {
        "id": name,
        "status": "PASS",
        "command": "pytest",
        "expected": "passes",
        "observed": "passed",
        "evidence": ["gate1.txt"],
        "tested_head": FAKE,
        "affects": ["src"],
        "reviewer": "gate2.txt",
    }
    made.update(fields)
    return made


def manifest(repo: Path, *rows: dict[str, Any], **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "row": list(rows),
        "post_merge": {"e2e": "e2e-post.txt", "main_head": FAKE},
    }
    body.update(extra)
    return body


class _Quiet:
    returncode = 0
    stdout = ""


def quiet(root: Path, *args: str) -> _Quiet:
    """git answering 'nothing changed, on the base': git starts slowly here, and only the tests
    that are about git itself (staleness, the base, a bad head) run it for real."""
    return _Quiet()


def blocked(repo: Path, body: dict[str, Any], **kwargs: Any) -> list[str]:
    kwargs.setdefault("git", quiet)
    return closure.problems(body, repo, base="main", **kwargs)


def blocked_by_git(repo: Path, body: dict[str, Any], **kwargs: Any) -> list[str]:
    return closure.problems(body, repo, base="main", **kwargs)


def test_a_whole_record_backs_the_closure(repo: Path) -> None:
    assert blocked(repo, manifest(repo, row(repo), row(repo, "TC1")), required=["AC1", "TC1"]) == []


def test_a_required_id_with_no_row_blocks(repo: Path) -> None:
    found = blocked(repo, manifest(repo, row(repo)), required=["AC1", "TC4"])
    assert any(line.startswith("TC4") for line in found)


@pytest.mark.parametrize("status", ["NOT RUN", "FAIL", "UNKNOWN", "pass", ""])
def test_any_status_but_pass_blocks(repo: Path, status: str) -> None:
    assert blocked(repo, manifest(repo, row(repo, status=status)), required=["AC1"])


def test_a_listed_row_is_not_enough_without_its_evidence(repo: Path) -> None:
    missing = row(repo, evidence=["no-such-file.txt"])
    assert blocked(repo, manifest(repo, missing))
    assert blocked(repo, manifest(repo, row(repo, evidence=[])))


def test_evidence_that_changed_since_it_was_recorded_blocks(repo: Path) -> None:
    pinned = {"path": "gate1.txt", "sha256": hashlib.sha256(b"something else").hexdigest()}
    assert blocked(repo, manifest(repo, row(repo, evidence=[pinned])))
    actual = hashlib.sha256((repo / "gate1.txt").read_bytes()).hexdigest()
    good = {"path": "gate1.txt", "sha256": actual}
    assert blocked(repo, manifest(repo, row(repo, evidence=[good]))) == []


def test_evidence_outside_the_repository_is_refused(repo: Path) -> None:
    assert blocked(repo, manifest(repo, row(repo, evidence=["../outside.txt"])))


def test_a_row_without_a_tested_head_or_reviewer_blocks(repo: Path) -> None:
    assert blocked(repo, manifest(repo, row(repo, tested_head="")))
    assert blocked(repo, manifest(repo, row(repo, reviewer="")))


def test_new_tests_need_a_mutation_check_on_record(repo: Path) -> None:
    assert blocked(repo, manifest(repo, row(repo, new_tests=True)))
    assert blocked(repo, manifest(repo, row(repo, new_tests=True, mutation="gate1.txt"))) == []


def test_evidence_goes_stale_when_a_covered_file_changes(fresh: Path) -> None:
    body = manifest(fresh, row(fresh, tested_head=sha(fresh)))
    (fresh / "src" / "code.py").write_text("two\n")
    git(fresh, "commit", "-qam", "change covered code")
    assert any("stale" in line for line in blocked_by_git(fresh, body, done=False))


def test_a_change_outside_the_covered_files_leaves_evidence_current(fresh: Path) -> None:
    body = manifest(fresh, row(fresh, tested_head=sha(fresh)))
    (fresh / "notes.txt").write_text("unrelated\n")
    git(fresh, "add", "-A")
    git(fresh, "commit", "-qm", "docs")
    assert blocked_by_git(fresh, body, done=False) == []


def test_a_row_that_covers_nothing_cannot_show_it_is_current(repo: Path) -> None:
    assert blocked(repo, manifest(repo, row(repo, affects=[])))


def test_closing_needs_the_post_merge_run_on_a_commit_on_the_base(fresh: Path) -> None:
    merged = sha(fresh)
    on_main = {"e2e": "e2e-post.txt", "main_head": merged}
    rows = row(fresh, tested_head=merged)
    assert blocked_by_git(fresh, manifest(fresh, rows, post_merge=on_main), head=merged) == []
    nothing = manifest(fresh, rows)
    del nothing["post_merge"]
    assert blocked_by_git(fresh, nothing, head=merged)  # no post-merge run recorded
    assert blocked_by_git(fresh, nothing, head=merged, done=False) == []  # before merge: not needed
    git(fresh, "checkout", "-q", "-b", "feature")
    (fresh / "notes.txt").write_text("unmerged\n")
    git(fresh, "add", "-A")
    git(fresh, "commit", "-qm", "unmerged")
    off_main = {"e2e": "e2e-post.txt", "main_head": sha(fresh)}  # a run on a commit not on main
    found = blocked_by_git(fresh, manifest(fresh, rows, post_merge=off_main), head=merged)
    assert any("not on main" in line for line in found)


def test_an_amended_row_needs_a_dated_owner_amendment(repo: Path) -> None:
    amended = row(repo, status="AMENDED")
    assert blocked(repo, manifest(repo, amended))
    bad_date = {
        "id": "AC1", "date": "yesterday", "owner": "o", "reason": "r", "destination": "CC-9",
    }  # fmt: skip
    assert blocked(repo, manifest(repo, amended, amendment=[bad_date]))
    good = {**bad_date, "date": "2026-11-09"}
    assert blocked(repo, manifest(repo, amended, amendment=[good])) == []


def test_the_same_id_twice_is_refused(repo: Path) -> None:
    assert blocked(repo, manifest(repo, row(repo), row(repo)))


def test_a_ticket_in_progress_may_have_rows_not_yet_run(repo: Path) -> None:
    draft = manifest(repo, row(repo, status="NOT RUN"), row(repo, "TC1"))
    assert closure.problems(draft, repo, readiness=False) == []
    assert closure.problems(manifest(repo, row(repo, status="done")), repo, readiness=False)
    assert closure.problems(manifest(repo, row(repo, evidence=["gone.txt"])), repo, readiness=False)


def test_identifiers_are_read_from_the_start_of_each_line_only() -> None:
    description = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "AC1. First"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "AC2. Second (see AC9)"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "TC1. Edge"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "AC1. repeated"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "AC. nope and ACx. nope and TC10 no dot"},
                ],
            }
        ],
    }
    assert closure.required_ids(closure.adf_text(description)) == ["AC1", "AC2", "TC1"]


# --- the Jira Done paths ---------------------------------------------------------------------


def done_calls(monkeypatch: pytest.MonkeyPatch, argv: list[str], gate: Any) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(sys, "argv", ["jira_transition.py", "CC-7", *argv])
    monkeypatch.setattr(jt, "_load_env", lambda: None)
    monkeypatch.setattr(jt, "_closure_gate", gate)
    monkeypatch.setattr(jt, "_add_comment", lambda key, text: calls.append("comment"))
    monkeypatch.setattr(jt, "_transition", lambda key, target: calls.append(f"to {target}"))
    monkeypatch.setattr(jt, "_issue", lambda key, fields="": {"fields": {"status": {"name": "x"}}})
    return calls


def refuse(key: str) -> None:
    raise SystemExit(1)


@pytest.mark.parametrize("argv", [["--done"], ["--transition", "Done"], ["--transition", "done"]])
def test_both_done_paths_stop_at_a_refused_closure_before_any_write(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    calls = done_calls(monkeypatch, [*argv, "--comment", "closing"], refuse)
    with pytest.raises(SystemExit):
        jt.main()
    assert calls == []


def test_a_move_that_is_not_done_does_not_meet_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = done_calls(monkeypatch, ["--transition", "In Progress"], refuse)
    jt.main()
    assert calls == ["to In Progress"]


def test_a_description_with_ac_ids_needs_a_manifest_to_close(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    text = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "AC1. x"}]}],
    }
    monkeypatch.setattr(jt, "ROOT", tmp_path)
    monkeypatch.setattr(jt, "_issue", lambda key, fields="": {"fields": {"description": text}})
    with pytest.raises(SystemExit):
        jt._closure_gate("CC-7")
    plain = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "chore"}]}],
    }
    monkeypatch.setattr(jt, "_issue", lambda key, fields="": {"fields": {"description": plain}})
    jt._closure_gate("CC-7")  # nothing to cover: no manifest required


# --- the invariants -------------------------------------------------------------------------------


def test_a_manifest_in_the_tree_with_a_bad_status_fails_the_invariants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "evidence" / "closure").mkdir(parents=True)
    manifest_file = tmp_path / "evidence" / "closure" / "CC-1.toml"
    manifest_file.write_text('[[row]]\nid = "AC1"\nstatus = "mostly"\n')
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(ci, "EVIDENCE", tmp_path / "evidence")
    assert ci.check_closure_manifests()
    manifest_file.write_text('[[row]]\nid = "AC1"\nstatus = "NOT RUN"\n')
    assert ci.check_closure_manifests() == []


def loosened(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, edit: tuple[str, str]) -> list[Any]:
    text = (ROOT / ci.PROTOCOL).read_text(encoding="utf-8")
    assert edit[0] in text
    (tmp_path / "evals").mkdir(exist_ok=True)
    (tmp_path / ci.PROTOCOL).write_text(text.replace(*edit), encoding="utf-8")
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(ci, "_text_at", lambda ref, rel: text)
    return ci.check_protocol_not_weakened("origin/main")


@pytest.mark.parametrize(
    "edit",
    [
        ("min_families = 30", "min_families = 20"),
        ("confidence = 0.95", "confidence = 0.90"),
        ("max_regression = 0.02", "max_regression = 0.05"),
        ("repeat = 3", "repeat = 1"),
        ("seed = 20261109", "seed = 7"),
        ('case_rule = "all_repeats"', 'case_rule = "any_repeat"'),
        ("exclusions = []", 'exclusions = ["q05"]'),
        ('exclude_flags = ["holdout"]', 'exclude_flags = ["holdout", "trap"]'),
        ('"fetched_level", ', ""),
    ],
)
def test_loosening_the_frozen_protocol_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, edit: tuple[str, str]
) -> None:
    assert loosened(monkeypatch, tmp_path, edit)


def test_tightening_the_frozen_protocol_is_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert loosened(monkeypatch, tmp_path, ("min_families = 30", "min_families = 40")) == []
    assert loosened(monkeypatch, tmp_path, ("max_regression = 0.02", "max_regression = 0.01")) == []


def test_a_tested_head_that_is_not_a_commit_blocks(repo: Path) -> None:
    found = blocked_by_git(repo, manifest(repo, row(repo, tested_head="0" * 40)), done=False)
    assert any("not a commit" in line for line in found)
