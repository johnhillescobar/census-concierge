"""A ticket closes only on a whole AC/TC record: every ID present and PASS, evidence real and
current, new tests mutation-checked, and the post-merge run on a commit that is on the base."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
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
    for name in ("s", "r", "c", "-p"):  # real paths, so only the type and option checks stop them
        (path / name).write_text("x")
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


def pin(repo: Path, name: str) -> dict[str, str]:
    return {"path": name, "sha256": hashlib.sha256((repo / name).read_bytes()).hexdigest()}


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
        "evidence": [pin(repo, "gate1.txt")],
        "tested_head": FAKE,
        "affects": ["src"],
        "reviewer": "gate2.txt",
    }
    made.update(fields)
    return made


def manifest(repo: Path, *rows: dict[str, Any], **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "required": [str(r["id"]) for r in rows],
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
    assert blocked(
        repo, manifest(repo, row(repo, new_tests=True, mutation="gate1.txt"))
    )  # unpinned
    pinned_mutation = pin(repo, "gate1.txt")
    assert blocked(repo, manifest(repo, row(repo, new_tests=True, mutation=pinned_mutation))) == []


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
    assert loosened(monkeypatch, tmp_path, ("resamples = 10000", "resamples = 20000")) == []


def protocol_text() -> str:
    return (ROOT / ci.PROTOCOL).read_text(encoding="utf-8")


def rule_line(key: str) -> tuple[str, Any]:
    """A [rule] parameter's line in the committed protocol, and its value."""
    line = next(text for text in protocol_text().splitlines() if text.startswith(f"{key} = "))
    return line, tomllib.loads(line)[key]


def guarded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, base: str, now: str) -> list[Any]:
    (tmp_path / "evals").mkdir(exist_ok=True)
    (tmp_path / ci.PROTOCOL).write_text(now, encoding="utf-8")
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(ci, "_text_at", lambda ref, rel: base)
    return ci.check_protocol_not_weakened("origin/main")


def test_every_rule_parameter_in_the_committed_protocol_is_guarded() -> None:
    rule = tomllib.loads(protocol_text())["rule"]
    assert set(rule) == ci.RULE_GUARDED
    assert {key for key, value in rule.items() if isinstance(value, int | float)} - {
        key for key in rule if isinstance(rule[key], bool)
    } == set(ci.RULE_NOT_HIGHER)


@pytest.mark.parametrize("key", ci.RULE_NOT_HIGHER)
def test_raising_a_rule_tolerance_fails_and_lowering_it_is_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key: str
) -> None:
    line, value = rule_line(key)
    found = loosened(monkeypatch, tmp_path, (line, f"{key} = {value + 1}"))
    assert [v.where for v in found] == [f"{ci.PROTOCOL} [rule] {key}"]
    assert loosened(monkeypatch, tmp_path, (line, f"{key} = {value / 2}")) == []
    assert loosened(monkeypatch, tmp_path, (line, f"{key} = {value}")) == []


@pytest.mark.parametrize("key", ci.RULE_NOT_HIGHER)
def test_a_rule_number_that_is_removed_or_not_a_number_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key: str
) -> None:
    line, _value = rule_line(key)
    assert loosened(monkeypatch, tmp_path, (line, ""))
    assert loosened(monkeypatch, tmp_path, (line, f'{key} = "none"'))
    assert loosened(monkeypatch, tmp_path, (line, f"{key} = true"))
    for wild in ("nan", "inf"):  # a tolerance nothing can exceed switches its row off
        found = loosened(monkeypatch, tmp_path, (line, f"{key} = {wild}"))
        assert [v.where for v in found] == [f"{ci.PROTOCOL} [rule] {key}"], wild


def test_a_rule_parameter_the_guard_does_not_know_is_a_violation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    text = protocol_text()
    added = text.replace("[rule]\n", "[rule]\nskip_rows = 2\n")
    assert added != text
    found = guarded(monkeypatch, tmp_path, added, added)  # even when main already carries it
    assert [v.where for v in found] == [f"{ci.PROTOCOL} [rule] skip_rows"]


def test_a_rule_number_main_does_not_have_yet_is_the_owners_to_ratify(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    text = protocol_text()
    without = text[: text.index("\n[rule]\n")] + "\n[rule]\n"
    found = guarded(monkeypatch, tmp_path, without, text)
    flagged = {v.where.rsplit(" ", 1)[1] for v in found}
    assert flagged == ci.RULE_GUARDED  # every number, the switch and the report-only list
    assert guarded(monkeypatch, tmp_path, text, text) == []  # once main has it: nothing to say


def test_a_blocking_rule_may_be_turned_on_and_never_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    line, value = rule_line("lost_questions_block")
    off = protocol_text().replace(line, "lost_questions_block = false")
    on = protocol_text().replace(line, "lost_questions_block = true")
    assert on != off and isinstance(value, bool)
    assert guarded(monkeypatch, tmp_path, on, off)
    assert guarded(monkeypatch, tmp_path, off, on) == []
    assert guarded(monkeypatch, tmp_path, off, off) == []
    assert guarded(monkeypatch, tmp_path, on, on.replace("= true", "= 1"))  # not a switch


def test_a_reference_may_leave_the_report_only_list_and_never_join_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    line, value = rule_line("report_only")
    assert value == ["A", "A0"]
    assert loosened(monkeypatch, tmp_path, (line, 'report_only = ["A", "A0", "L"]'))
    assert loosened(monkeypatch, tmp_path, (line, 'report_only = ["A"]')) == []


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


def promoted(run: str, verdict: str = "PASS", refs: tuple[str, ...] = ("L",)) -> str:
    """A ledger line as `promote` appends it."""
    files = [{"run": run, "run_sha256": "s3", "run_head": "h3"}]
    return json.dumps({"runs": files, "verdict": verdict, "refs": list(refs)}) + chr(10)


def test_a_change_to_l_outside_the_owners_own_commit_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = refs_json(A={"head": "1"}, L=reference_l("r2.json"))
    moved = refs_json(A={"head": "1"}, L=reference_l("r3.json", "h3", "s3"))
    old_ledger = promoted("r2.json")

    def change(refs_now: str, ledger_now: str = "") -> list[Any]:
        files = {REFS: (before, refs_now), LEDGER: (old_ledger, old_ledger + ledger_now)}
        return records(monkeypatch, tmp_path, files)

    assert change(before) == []
    assert change(before, promoted("r3.json")) == []  # a recorded compare alone moves nothing
    assert change(moved)  # a hand edit
    assert change(moved, promoted("r3.json"))  # and what `promote` wrote after a recorded pass
    assert change(refs_json(A={"head": "1"}))  # removed
    for bad in ("null", "5", "[]", '{"run": "r2.json"}'):
        assert change('{"A": {"head": "1"}, "L": ' + bad + "}"), bad
    found = change(moved)
    assert [v.where for v in found] == [REFS] and "owner" in found[0].message


def test_seeding_l_is_the_owners_own_commit_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    anchors = refs_json(A={"head": "1"})
    seeded = refs_json(A={"head": "1"}, L=reference_l("r.json"))
    assert records(monkeypatch, tmp_path, {REFS: (anchors, seeded)})
    assert records(monkeypatch, tmp_path, {REFS: (None, seeded)})  # a store new at the base
    assert records(monkeypatch, tmp_path, {REFS: (None, anchors)}) == []
    assert records(monkeypatch, tmp_path, {REFS: (seeded, seeded)}) == []  # landed: no change


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
        {"tested_head": "abc"},  # hex, but too short to name a commit
        {"tested_head": "a" * 41},
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


# --- findings of the /code-review pass -----------------------------------------------------------


def test_a_pass_cannot_rest_on_evidence_that_is_not_pinned(repo: Path) -> None:
    unpinned = blocked(repo, manifest(repo, row(repo, evidence=["gate1.txt"])))
    assert any("pinned" in line for line in unpinned)
    assert blocked(repo, manifest(repo, row(repo, evidence=[pin(repo, "gate1.txt")]))) == []
    # a row still being worked may cite a plain path: only a PASS is a claim
    open_row = row(repo, status="UNKNOWN", evidence=["gate1.txt"])
    assert blocked(repo, manifest(repo, open_row), readiness=False) == []


def test_a_manifest_must_declare_which_ids_it_covers(repo: Path) -> None:
    body = manifest(repo, row(repo), row(repo, "TC1"))
    del body["required"]
    assert any("declare `required`" in line for line in blocked(repo, body))
    body["required"] = []
    assert blocked(repo, body)
    body["required"] = ["AC1", "TC1", "TC2"]  # claims a row it does not have
    assert any("TC2: absent" in line for line in blocked(repo, body))


def test_dotted_and_ranged_ids_are_each_required() -> None:
    text = "AC 6.1: a\nAC 6.2: b\nAC6.2: again\nTC3-5\nAC9. plain\nAC1-2 are first"
    assert closure.required_ids(text) == [
        "AC6.1",
        "AC6.2",
        "TC3",
        "TC4",
        "TC5",
        "AC9",
        "AC1",
        "AC2",
    ]
    assert closure.required_ids("AC1-9999") == ["AC1"]  # not a range: far too wide
    assert closure.required_ids("AC5-3") == ["AC5"]  # backwards is not a range


@pytest.mark.parametrize("target", ["Won't Do", "Cancelled", "Duplicate"])
def test_a_cancellation_needs_a_reason_and_no_manifest(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    gated: list[str] = []
    monkeypatch.setattr(jt, "_closure_gate", lambda key: gated.append(key))
    sent: list[str] = []
    monkeypatch.setattr(jt, "_add_comment", lambda key, text: sent.append(text))
    monkeypatch.setattr(jt, "_transition", lambda key, to: sent.append(f"-> {to}"))
    monkeypatch.setattr(jt, "_issue", lambda key, fields="": {"fields": {"status": {"name": "x"}}})
    argv = ["jira_transition.py", "CC-9", "--transition", target]
    monkeypatch.setattr(sys, "argv", argv)
    assert jt.main() == 1 and sent == []  # no reason, nothing sent
    monkeypatch.setattr(sys, "argv", [*argv, "--comment", "duplicate of CC-7"])
    assert jt.main() == 0 and gated == [] and sent[-1] == f"-> {target}"


def test_done_is_still_gated_whatever_the_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    gated: list[str] = []
    monkeypatch.setattr(jt, "_closure_gate", lambda key: gated.append(key))
    monkeypatch.setattr(jt, "_add_comment", lambda key, text: None)
    monkeypatch.setattr(jt, "_transition", lambda key, to: None)
    monkeypatch.setattr(jt, "_issue", lambda key, fields="": {"fields": {"status": {"name": "x"}}})
    monkeypatch.setattr(sys, "argv", ["jira_transition.py", "CC-9", "--done", "--comment", "x"])
    assert jt.main() == 0 and gated == ["CC-9"]


# --- a post-merge run is owed by what was merged, read from the diff ----------------------------

# what a merged change may touch, and whether it then owes a post-merge run
OWES = {
    "api/src/geo.py": True,
    "evals/golden_questions.toml": True,
    "evals/metric_protocol.toml": True,
    "scripts/run_demo.py": True,
    "scripts/run_grid.py": True,
    "scripts/metric_compare.py": True,
    "Makefile": True,
    "uv.lock": True,
    "api/pyproject.toml": True,
    "web/index.html": True,  # `make demo` builds it and run_demo checks the served page
    "web/src/App.tsx": True,
    "api/tests/test_geo.py": False,
    "scripts/jira_fetch.py": False,
    "scripts/closure.py": False,
    "docs/ARCHITECTURE.md": False,
    "evidence/slice-6/notes.txt": False,
    "api/src_notes.md": False,  # beside api/src, not in it
    "Makefile.bak": False,
}


def ticket(number: int) -> str:
    return f"evidence/closure/CC-{number}.toml"


def merge(repo: Path, branch: str, files: dict[str, str]) -> str:
    """Commit `files` on a branch and merge it into main with a merge commit, as a pull request
    lands. Returns the branch tip: the head a row was tested at."""
    git(repo, "checkout", "-q", "-b", branch)
    tip = commit(repo, branch, files)
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", f"Merge {branch}", branch)
    return tip


def commit(repo: Path, message: str, files: dict[str, str]) -> str:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return sha(repo)


@pytest.fixture(scope="module")
def landed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One history, built once and only read by its tests (git is slow to start here). Each key is
    the head a row would have been tested at: the tip of a merged branch, or a commit on main."""
    repo = make_repo(tmp_path_factory.mktemp("landed"))
    heads: dict[str, Any] = {"repo": repo}
    heads["docs"] = merge(repo, "docs", {"docs/playbook.md": "rule\n", ticket(1): "m\n"})
    both = {"docs/more.md": "x\n", "api/src/ask.py": "code\n", ticket(2): "m\n"}
    heads["feature"] = merge(repo, "feature", both)
    heads["paths"] = merge(repo, "paths", {**dict.fromkeys(OWES, "x\n"), ticket(3): "m\n"})
    heads["code"] = merge(repo, "code", {"api/src/other.py": "code\n"})  # no manifest in it
    heads["evidence"] = merge(repo, "evidence", {ticket(4): "m\n", "evidence/gate1.txt": "ok\n"})
    heads["straight"] = commit(repo, "straight onto main", {"evals/golden.toml": "q\n"})
    heads["on top"] = commit(repo, "an unrelated commit on top", {"notes.txt": "later\n"})
    git(repo, "checkout", "-q", "-b", "unmerged")
    heads["unmerged"] = commit(repo, "unmerged docs", {"docs/unmerged.md": "x\n"})
    git(repo, "checkout", "-q", "main")
    return heads


def closing(
    landed: dict[str, Any], tested: str, manifest_path: str | None, **kwargs: Any
) -> list[str]:
    """What blocks a closure that records no post-merge run."""
    repo = landed["repo"]
    body = manifest(repo, row(repo, tested_head=landed[tested], affects=["gate1.txt"]))
    del body["post_merge"]
    kwargs.setdefault("base", "main")
    return closure.problems(body, repo, path=manifest_path, **kwargs)


def test_a_ticket_that_merged_no_product_eval_or_harness_file_closes_without_a_post_merge_run(
    landed: dict[str, Any],
) -> None:
    assert closing(landed, "docs", ticket(1)) == []


def test_a_ticket_whose_merge_touched_api_src_still_owes_its_post_merge_run(
    landed: dict[str, Any],
) -> None:
    found = closing(landed, "feature", ticket(2))  # its row covers gate1.txt: the diff decides
    assert len(found) == 1 and "post_merge" in found[0] and "api/src/ask.py" in found[0]
    assert closing(landed, "feature", None) == found  # the tested head alone finds the merge
    assert closing(landed, "feature", ticket(2), done=False) == []  # before the merge: not yet


def test_what_owes_a_post_merge_run_is_the_product_the_evals_and_the_run_harness(
    landed: dict[str, Any],
) -> None:
    repo = landed["repo"]
    owed = closure.merged_e2e_paths(repo, ticket(3), [landed["paths"]], "main", closure._git)
    assert owed == sorted(rel for rel, owes in OWES.items() if owes)
    assert closure.merged_e2e_paths(repo, ticket(1), [landed["docs"]], "main", closure._git) == []


def test_code_merged_in_one_pull_request_is_seen_when_the_manifest_lands_in_another(
    landed: dict[str, Any],
) -> None:
    assert any("api/src/other.py" in line for line in closing(landed, "code", ticket(4)))
    # a row tested later, on the evidence branch, names only the evidence merge: a pull request
    # with neither the manifest nor a tested head is not seen, which the docstring owns up to
    assert closing(landed, "evidence", ticket(4)) == []


def test_a_change_committed_straight_onto_the_base_is_diffed_as_itself(
    landed: dict[str, Any],
) -> None:
    at_the_tip = closing(landed, "straight", None, base=landed["straight"])
    assert any("evals/golden.toml" in line for line in at_the_tip)
    assert any("evals/golden.toml" in line for line in closing(landed, "straight", None))
    assert closing(landed, "on top", None) == []  # the later commit touched nothing that counts


def test_work_that_is_not_on_the_base_cannot_close_without_a_run(landed: dict[str, Any]) -> None:
    found = closing(landed, "unmerged", ticket(1))
    assert len(found) == 1 and "not on main" in found[0]


def test_a_merge_git_cannot_diff_owes_the_run(landed: dict[str, Any]) -> None:
    def no_diff(root: Path, *args: str) -> Any:
        if args[:2] == ("diff", "--name-only") and len(args) == 4:  # a commit against its parent
            return subprocess.CompletedProcess(args, 128, "", "bad object")
        return closure._git(root, *args)

    found = closing(landed, "docs", ticket(1), git=no_diff)
    assert len(found) == 1 and "E2E is required" in found[0]


def test_a_half_recorded_post_merge_run_is_not_waved_through(landed: dict[str, Any]) -> None:
    repo = landed["repo"]
    body = manifest(repo, row(repo, tested_head=landed["docs"], affects=["gate1.txt"]))
    body["post_merge"] = {"e2e": pinned(repo)}  # a run with no head: recorded wrongly, not absent
    found = closure.problems(body, repo, base="main", path=ticket(1))
    assert any("post_merge" in line for line in found)


def test_check_file_names_the_manifest_whose_merges_are_diffed(landed: dict[str, Any]) -> None:
    repo = landed["repo"]
    digest = hashlib.sha256((repo / "gate1.txt").read_bytes()).hexdigest()
    lines = [
        'required = ["AC1"]',
        "[[row]]",
        'id = "AC1"',
        'status = "PASS"',
        'command = "pytest"',
        'expected = "passes"',
        'observed = "passed"',
        'reviewer = "gate2.txt"',
        'affects = ["gate1.txt"]',
        f'tested_head = "{landed["on top"]}"',  # on main, and after every merge: only the
        f'evidence = [{{path = "gate1.txt", sha256 = "{digest}"}}]',  # manifest names the ticket
    ]
    for number, owed in ((1, False), (2, True)):
        (repo / ticket(number)).write_text("\n".join(lines) + "\n")
        found = closure.check_file(repo / ticket(number), root=repo, base="main")
        assert bool(found) is owed, number
        assert all("api/src/ask.py" in line for line in found)
