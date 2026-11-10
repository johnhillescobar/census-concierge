"""A ticket closes only on a whole AC/TC record: every ID present and PASS, evidence real and
current, new tests mutation-checked, and the post-merge run on a commit that is on the base."""

from __future__ import annotations

import hashlib
import json
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


def pinned(repo: Path) -> dict[str, str]:
    digest = hashlib.sha256((repo / "e2e-post.txt").read_bytes()).hexdigest()
    return {"path": "e2e-post.txt", "sha256": digest}


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
        "post_merge": {"e2e": pinned(repo), "main_head": FAKE},
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
    (repo.parent / "outside.txt").write_text("a real file, but not in the repository\n")
    found = blocked(repo, manifest(repo, row(repo, evidence=["../outside.txt"])))
    assert any("outside the repository" in line for line in found)


def test_a_row_without_a_tested_head_or_reviewer_blocks(repo: Path) -> None:
    assert blocked(repo, manifest(repo, row(repo, tested_head="")))
    assert blocked(repo, manifest(repo, row(repo, reviewer="")))


def test_new_tests_need_a_mutation_check_on_record(repo: Path) -> None:
    assert blocked(repo, manifest(repo, row(repo, new_tests=True)))
    assert blocked(repo, manifest(repo, row(repo, new_tests=True, mutation="no-such.txt")))
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
    on_main = {"e2e": pinned(fresh), "main_head": merged}
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
    off_main = {"e2e": pinned(fresh), "main_head": sha(fresh)}  # a run on a commit not on main
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
    for missing in ("owner", "reason", "destination"):
        partial = {k: v for k, v in good.items() if k != missing}
        assert blocked(repo, manifest(repo, amended, amendment=[partial])), missing


def test_the_post_merge_evidence_file_must_exist(repo: Path) -> None:
    body = manifest(repo, row(repo), post_merge={"e2e": "no-e2e.txt", "main_head": FAKE})
    assert any("post_merge" in line for line in blocked(repo, body))


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
                    {"type": "text", "text": "AC. nope and ACx. nope"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "TC10 no terminator"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "AC3 not dotted"},
                ],
            }
        ],
    }
    assert closure.required_ids(closure.adf_text(description)) == ["AC1", "AC2", "TC1"]


# --- the Jira Done paths ---------------------------------------------------------------------


def move(name: str, category: str) -> dict[str, Any]:
    return {"id": name, "to": {"name": name, "statusCategory": {"key": category}}}


MOVES = [move("Done", "done"), move("Closed", "done"), move("In Progress", "indeterminate")]


def done_calls(monkeypatch: pytest.MonkeyPatch, argv: list[str], gate: Any) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(sys, "argv", ["jira_transition.py", "CC-7", *argv])
    monkeypatch.setattr(jt, "_load_env", lambda: None)
    monkeypatch.setattr(jt, "_closure_gate", gate)
    monkeypatch.setattr(jt, "_add_comment", lambda key, text: calls.append("comment"))
    monkeypatch.setattr(jt, "_transition", lambda key, target: calls.append(f"to {target}"))
    monkeypatch.setattr(jt, "_issue", lambda key, fields="": {"fields": {"status": {"name": "x"}}})
    monkeypatch.setattr(jt, "_transitions", lambda key: MOVES)
    return calls


def refuse(key: str) -> None:
    raise SystemExit(1)


@pytest.mark.parametrize(
    "argv",
    [["--done"], ["--transition", "Done"], ["--transition", "done"], ["--transition", "Closed"]],
)
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


def doc(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def issue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str, kind: str) -> None:
    fields = {"description": doc(text), "issuetype": {"name": kind}}
    monkeypatch.setattr(jt, "ROOT", tmp_path)
    monkeypatch.setattr(jt, "_issue", lambda key, f="": {"fields": fields})


def test_a_description_with_ac_ids_needs_a_manifest_to_close(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    issue(monkeypatch, tmp_path, "AC1. x", "Story")
    with pytest.raises(SystemExit):
        jt._closure_gate("CC-7")


def test_a_story_with_no_recognised_ids_is_refused_not_waved_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    issue(monkeypatch, tmp_path, "Acceptance: first thing, second thing", "Story")
    with pytest.raises(SystemExit):
        jt._closure_gate("CC-7")
    issue(monkeypatch, tmp_path, "", "Bug")
    with pytest.raises(SystemExit):
        jt._closure_gate("CC-7")


def test_an_epic_with_no_ids_needs_no_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    issue(monkeypatch, tmp_path, "scope of the slice", "Epic")
    jt._closure_gate("CC-7")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("AC1: x", ["AC1"]),
        ("- AC1. x", ["AC1"]),
        ("**AC1.** x", ["AC1"]),
        ("**AC1**: x", ["AC1"]),
        ("AC 1. x", ["AC1"]),
        ("ac1) x", ["AC1"]),
        ("TC1. x", ["TC1"]),
        ("AC1 - x", ["AC1"]),
        ("AC1", ["AC1"]),
        ("AC007. x", ["AC7"]),
        (chr(0x2013) + " AC1. x", ["AC1"]),
        ("AC" + chr(0xA0) + "1. x", ["AC1"]),
        ("AC1 is the first criterion", []),
        ("ACCESS 1. foo", []),
        ("AC" + "9" * 5000 + ". x", []),
    ],
)
def test_ids_in_ordinary_jira_formatting_are_still_required(text: str, expected: list[str]) -> None:
    assert closure.required_ids(text) == expected


def test_a_manifest_with_no_rows_cannot_back_a_closure(repo: Path) -> None:
    only_post_merge = {"post_merge": {"e2e": pinned(repo), "main_head": FAKE}}
    found = blocked(repo, only_post_merge, required=[])
    assert any("no rows" in line for line in found)


def test_done_is_gated_whatever_category_the_workflow_files_it_under(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for moves in (
        [{"to": {"name": "Done"}}],
        [{"to": {"name": "Done", "statusCategory": {"key": "indeterminate"}}}],
        [{"to": None}],
        [],
    ):
        monkeypatch.setattr(jt, "_transitions", lambda key, moves=moves: moves)
        assert jt._is_done("CC-7", "Done") is True
        assert jt._is_done("CC-7", "done") is True
    monkeypatch.setattr(jt, "_transitions", lambda key: [{"to": None}, {"to": {"name": "Shipped"}}])
    assert jt._is_done("CC-7", "Shipped") is False  # no category says it is a closure
    assert jt._is_done("CC-7", "") is False


def test_a_references_file_that_is_not_an_object_is_a_violation_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert records(monkeypatch, tmp_path, {REFS: ("[]", "[]")})


def test_a_malformed_manifest_blocks_instead_of_crashing(tmp_path: Path) -> None:
    broken = tmp_path / "CC-7.toml"
    broken.write_text("row = 5\n")  # not a list of tables: iterating it raises
    found = closure.check_file(broken, root=tmp_path)
    assert found and "malformed" in found[0]


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
        ("resamples = 10000", "resamples = 100"),
        ('stopping = "fixed"', 'stopping = "optional"'),
        ('blocks = "B,P,P,B"', 'blocks = "B,P"'),
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


# --- protocol and records the owner holds ---------------------------------------------------


def records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, files: dict[str, tuple[str | None, str]]
) -> list[Any]:
    """Each file is (text at the base, text now)."""
    for rel, (_old, new) in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(new.encode())
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(ci, "_text_at", lambda ref, rel: files.get(rel, (None, ""))[0])
    return ci.check_metric_records_not_rewritten("origin/main")


REFS = "evidence/metrics/references.json"
LEDGER = "evidence/metrics/ledger.jsonl"
REVIEW = "evals/oracle_review.toml"


def reference_l(run: str, head: str = "h2", sha: str = "s2") -> dict[str, str]:
    return {"run": run, "head": head, "run_sha256": sha}


def refs_json(**entries: Any) -> str:
    return json.dumps(entries)


def test_a_registered_reference_cannot_be_edited_and_a_new_one_may_be_added(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = refs_json(A={"head": "1"}, L=reference_l("r2.json"))
    added = refs_json(A={"head": "1"}, L=reference_l("r2.json"), B={"head": "4"})
    assert records(monkeypatch, tmp_path, {REFS: (before, added)}) == []
    edited = refs_json(A={"head": "9"}, L=reference_l("r2.json"))
    assert records(monkeypatch, tmp_path, {REFS: (before, edited)})
    assert records(monkeypatch, tmp_path, {REFS: (before, refs_json(L=reference_l("r2.json")))})


def promoted(run: str, verdict: str = "PASS", head: str = "h3", sha: str = "s3") -> str:
    row = {"run": run, "verdict": verdict, "head": head, "run_sha256": sha}
    return json.dumps(row) + chr(10)


def test_l_moves_only_with_a_pass_record_that_names_the_same_run_file_and_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = refs_json(A={"head": "1"}, L=reference_l("r2.json"))
    moved = refs_json(A={"head": "1"}, L=reference_l("r3.json", "h3", "s3"))
    old_ledger = promoted("r2.json", head="h2", sha="s2")

    def moves(ledger_now: str, refs_now: str = moved) -> list[Any]:
        files = {REFS: (before, refs_now), LEDGER: (old_ledger, old_ledger + ledger_now)}
        return records(monkeypatch, tmp_path, files)

    assert moves(promoted("r3.json")) == []
    assert moves("")  # a hand edit: nothing in the ledger says promote ran
    assert moves(promoted("r3.json", "FAIL"))  # the run did not pass
    assert moves(promoted("other.json"))  # a PASS, but for a different run
    assert moves(promoted("r3.json", head="other"))  # a different head
    assert moves(promoted("r3.json", sha="other"))  # a different file
    assert records(monkeypatch, tmp_path, {REFS: (before, refs_json(A={"head": "1"}))})  # removed


@pytest.mark.parametrize("bad", ["null", "5", '{"verdict": "PASS"}', '{"run": "r3.json"}', "[]"])
def test_an_l_that_is_not_a_complete_entry_cannot_slip_past_a_bare_ledger_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: str
) -> None:
    before = refs_json(L=reference_l("r2.json"))
    now_refs = '{"L": ' + bad + "}"
    ledger = promoted("r2.json", head="h2", sha="s2") + json.dumps({"verdict": "PASS"}) + chr(10)
    old = promoted("r2.json", head="h2", sha="s2")
    assert records(monkeypatch, tmp_path, {REFS: (before, now_refs), LEDGER: (old, ledger)})


def test_a_base_ledger_with_windows_line_endings_still_prefixes_the_current_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    crlf = '{"n": 1}' + chr(13) + chr(10)
    now_text = '{"n": 1}' + chr(10) + '{"n": 2}' + chr(10)
    assert records(monkeypatch, tmp_path, {LEDGER: (crlf, now_text)}) == []


def test_a_ledger_with_bytes_that_are_not_utf8_is_a_violation_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / LEDGER).write_bytes(b'{"n": 1}' + bytes([10, 255, 254]))
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(
        ci, "_text_at", lambda ref, rel: '{"n": 2}' + chr(10) if rel == LEDGER else None
    )
    assert ci.check_metric_records_not_rewritten("origin/main")


def test_an_oracle_review_whose_accepted_is_not_a_table_is_a_violation_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert records(
        monkeypatch, tmp_path, {REVIEW: ("accepted = 5" + chr(10), "accepted = 5" + chr(10))}
    )


def test_a_bridge_is_owner_only_whether_added_changed_or_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bridges = "evidence/metrics/bridges.json"
    one = '[{"ref": "A", "note": "x"}]'
    assert records(monkeypatch, tmp_path, {bridges: (one, one)}) == []
    assert records(monkeypatch, tmp_path, {bridges: (None, one)})  # a first bridge is an addition
    assert records(monkeypatch, tmp_path, {bridges: (one, '[{"ref": "A", "note": "y"}]')})
    assert records(monkeypatch, tmp_path, {bridges: (one, "[]")})
    assert records(monkeypatch, tmp_path, {bridges: (one, "not json")})
    assert records(monkeypatch, tmp_path, {bridges: (None, "not json")})  # nothing to remove
    assert records(monkeypatch, tmp_path, {bridges: ("not json", "other junk")})  # both bad
    assert records(monkeypatch, tmp_path, {bridges: ("{}", '{"a": 1}')})  # both not lists


def test_the_ledger_only_grows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    first, second = '{"n": 1}' + chr(10), '{"n": 2}' + chr(10)
    assert records(monkeypatch, tmp_path, {LEDGER: (first, first + second)}) == []
    assert records(monkeypatch, tmp_path, {LEDGER: (first + second, first)})
    assert records(monkeypatch, tmp_path, {LEDGER: (first, second)})


def test_an_oracle_signature_is_never_added_in_the_change_it_would_let_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    signed = "[accepted.q05]" + chr(10) + 'reviewer = "owner"' + chr(10)
    assert records(monkeypatch, tmp_path, {REVIEW: (signed, signed)}) == []
    assert records(monkeypatch, tmp_path, {REVIEW: ("# empty" + chr(10), signed)})
    changed = signed.replace("owner", "someone else")
    assert records(monkeypatch, tmp_path, {REVIEW: (signed, changed)})


@pytest.mark.parametrize(
    "edit",
    [
        ('source = "scripts/run_demo.py"', 'source = "scripts/other.py"'),
        ("version = 1", "version = 2"),
        ('tier = "long_tail"', 'tier = "core"'),
        ('source = "evals/golden_questions.toml"', 'source = "evals/other.toml"'),
    ],
)
def test_repointing_the_scorer_or_a_cohort_fails_the_protocol_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, edit: tuple[str, str]
) -> None:
    assert loosened(monkeypatch, tmp_path, edit)


def test_a_deleted_protocol_file_is_a_violation_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(ci, "_text_at", lambda ref, rel: "version = 1")
    assert ci.check_protocol_not_weakened("origin/main")


def test_dropping_a_cohort_fails_the_protocol_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    text = (ROOT / ci.PROTOCOL).read_text(encoding="utf-8")
    kept = text[: text.index("[cohorts.core]")]
    (tmp_path / "evals").mkdir()
    (tmp_path / ci.PROTOCOL).write_text(kept, encoding="utf-8")
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(ci, "_text_at", lambda ref, rel: text)
    assert any("cohort dropped" in v.message for v in ci.check_protocol_not_weakened("origin/main"))


@pytest.mark.parametrize("key", ["not a key", "CC-", "-7", "CC-7; rm -rf", "../CC-7"])
def test_an_issue_key_that_is_not_a_key_is_refused_before_any_request(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    calls = done_calls(monkeypatch, ["--done"], refuse)
    monkeypatch.setattr(sys, "argv", ["jira_transition.py", key, "--done"])
    with pytest.raises(SystemExit) as stop:
        jt.main()
    assert stop.value.code == 2 and calls == []


# --- type strictness: a mistyped field must block, never skip a check ----------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"affects": "src"},  # a string iterates as pathspecs s, r, c
        {"affects": ["nonexistent"]},
        {"affects": [":(exclude)src"]},
        {"affects": ["-p"]},
        {"affects": []},
        {"affects": None},
        {"tested_head": "HEAD"},
        {"tested_head": "main"},
        {"tested_head": "--stat"},
        {"tested_head": "zzzzzzz"},
        {"command": "   "},
        {"expected": "   "},
        {"observed": "   "},
        {"reviewer": True},
        {"reviewer": "   "},
        {"evidence": "gate1.txt"},  # a string iterates as characters
        {"evidence": []},
        {"evidence": [5]},
    ],
)
def test_a_mistyped_or_blank_field_blocks_instead_of_skipping_its_check(
    repo: Path, bad: dict[str, Any]
) -> None:
    assert blocked(repo, manifest(repo, row(repo, **bad)))


def test_a_stale_row_with_a_mistyped_affects_is_still_blocked_by_git(fresh: Path) -> None:
    body = manifest(fresh, row(fresh, tested_head=sha(fresh), affects="src"))
    (fresh / "src" / "code.py").write_text("two\n")
    git(fresh, "commit", "-qam", "change covered code")
    assert blocked_by_git(fresh, body, done=False)


def test_the_post_merge_run_must_be_pinned_a_hash_and_contain_the_tested_work(
    fresh: Path,
) -> None:
    tested = sha(fresh)
    git(fresh, "commit", "-q", "--allow-empty", "-m", "later work")
    later = sha(fresh)
    rows = row(fresh, tested_head=tested)
    good = {"e2e": pinned(fresh), "main_head": later}
    assert blocked_by_git(fresh, manifest(fresh, rows, post_merge=good), head=tested) == []
    unpinned = {"e2e": "e2e-post.txt", "main_head": later}
    assert blocked_by_git(fresh, manifest(fresh, rows, post_merge=unpinned), head=tested)
    not_a_hash = {"e2e": pinned(fresh), "main_head": "main"}
    assert blocked_by_git(fresh, manifest(fresh, rows, post_merge=not_a_hash), head=tested)
    # a commit on main that is older than the tested work does not contain it
    git(fresh, "branch", "old", tested)
    git(fresh, "checkout", "-q", "-b", "newer")
    (fresh / "src" / "code.py").write_text("newer\n")
    git(fresh, "commit", "-qam", "newer work")
    work = sha(fresh)
    git(fresh, "checkout", "-q", "main")
    early = {"e2e": pinned(fresh), "main_head": tested}
    body = manifest(fresh, row(fresh, tested_head=work), post_merge=early)
    found = blocked_by_git(fresh, body, head=work)
    assert any("does not contain" in line for line in found)


def test_adf_lists_and_code_blocks_keep_their_ids_on_separate_lines() -> None:
    def item(kind: str, text: str) -> dict[str, Any]:
        return {"type": kind, "content": [{"type": "text", "text": text}]}

    doc_ = {
        "type": "doc",
        "content": [
            {
                "type": "taskList",
                "content": [item("taskItem", "AC1. a"), item("taskItem", "AC2. b")],
            },
            item("codeBlock", "some code"),
            item("paragraph", "TC1. c"),
            item("paragraph", "(AC3) d"),
        ],
    }
    assert closure.required_ids(closure.adf_text(doc_)) == ["AC1", "AC2", "TC1", "AC3"]


def test_only_known_chore_types_skip_the_ac_requirement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for kind in ("Epic", "Task", "Sub-task", "Spike"):
        issue(monkeypatch, tmp_path, "no criteria here", kind)
        jt._closure_gate("CC-7")
    for kind in ("Story", "Bug", "Feature", ""):
        issue(monkeypatch, tmp_path, "no criteria here", kind)
        with pytest.raises(SystemExit):
            jt._closure_gate("CC-7")


def test_a_status_that_is_not_in_the_workflow_is_not_a_closure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jt, "_transitions", lambda key: MOVES)
    assert jt._is_done("CC-7", "No Such Status") is False
    assert jt._is_done("CC-7", "In Progress") is False
    assert jt._is_done("CC-7", "Closed") is True
