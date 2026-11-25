"""The one-time bulk edit replaces only the pasted gate wording: it never moves an AC/TC id, never
writes what the owner did not approve, and finds nothing left once it has written."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import jira_gate_line as jg  # noqa: E402

CONTRACT = "Metric progression and non-regression contract\nNo observed decrease against A."
CLEARANCE = "Mandatory AC/TC clearance before shipping\nEvery merged change owes a run."
AUDIT = "Existing AC/TC, earned floors, and the old uncertainty rule remain binding."


def para(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def doc(*blocks: str) -> dict[str, Any]:
    return {"type": "doc", "version": 1, "content": [para(block) for block in blocks]}


def texts(body: dict[str, Any]) -> list[str]:
    return [node["content"][0]["text"] for node in body["content"]]


@pytest.fixture(autouse=True)
def pasted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand-ins for the pasted paragraphs, so the rule is tested and not the wording."""
    known = {
        jg.fingerprint(para(CONTRACT)): "metric contract",
        jg.fingerprint(para(CLEARANCE)): "AC/TC clearance",
        jg.fingerprint(para(AUDIT)): "audit gates",
    }
    monkeypatch.setattr(jg, "PASTED", known)


class Jira:
    """Descriptions by key, answering as the REST API does, and a record of every write."""

    def __init__(self, **tickets: dict[str, Any]) -> None:
        self.tickets = {key.replace("_", "-"): body for key, body in tickets.items()}
        self.writes: list[str] = []
        self.calls: list[str] = []

    def search(self, jql: str, *, fields: str) -> list[dict[str, Any]]:
        self.calls.append("search")
        return [
            {"key": key, "fields": {"description": copy.deepcopy(body)}}
            for key, body in self.tickets.items()
        ]

    def api(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(method)
        key = path.split("/")[2].split("?")[0]
        if method == "GET":
            return {"fields": {"description": copy.deepcopy(self.tickets[key])}}
        assert method == "PUT" and body is not None
        self.writes.append(key)
        self.tickets[key] = copy.deepcopy(body["fields"]["description"])
        return {}


def ticket() -> dict[str, Any]:
    return doc("Owned outcome", CONTRACT, "AC1. a\nAC2. b", CLEARANCE, "TC1. c")


def approve(folder: Path) -> None:
    digest = jg._sha((folder / "manifest.json").read_bytes())
    (folder / "APPROVED").write_text(digest + "\n", encoding="utf-8")


def snapshot(jira: Jira, folder: Path) -> int:
    return jg.dry_run(folder, jira.search)


def test_the_pasted_paragraphs_become_one_line_where_the_first_stood() -> None:
    after, replaced = jg.edit(ticket())
    assert texts(after) == ["Owned outcome", jg.GATE_LINE, "AC1. a\nAC2. b", "TC1. c"]
    assert replaced == ["metric contract", "AC/TC clearance"]


def test_a_paragraph_is_known_by_its_text_not_its_spacing() -> None:
    spaced = CONTRACT.replace(" ", "  ") + "\n"
    assert jg.edit(doc(spaced))[1] == ["metric contract"]


def test_a_ticket_without_the_wording_is_left_alone() -> None:
    before = doc("Owned outcome", "AC1. a")
    assert jg.edit(before) == (before, [])
    assert jg.changes([{"key": "CC-1", "fields": {"description": before}}]) == []
    assert jg.changes([{"key": "CC-2", "fields": {"description": None}}]) == []


def test_a_gate_line_already_there_is_not_added_twice() -> None:
    after, _ = jg.edit(doc(jg.GATE_LINE, AUDIT))
    assert texts(after) == [jg.GATE_LINE]


def test_the_line_pointing_at_the_removed_contract_is_shortened() -> None:
    pointed = jg.OLD_POINTER + "\nSemantic variable selection\nAC1. a"
    after, _ = jg.edit(doc(CONTRACT, pointed))
    assert texts(after)[1] == "Existing scope\nSemantic variable selection\nAC1. a"


def test_the_pointer_stays_while_the_contract_it_points_at_does() -> None:
    after, _ = jg.edit(doc(jg.OLD_POINTER, AUDIT))
    assert texts(after)[0] == jg.OLD_POINTER


@pytest.mark.parametrize(
    "block",
    [
        CONTRACT + "\nAC9. a criterion pasted inside the block",  # would drop an id
        CONTRACT + "\nTC1. repeats an id the ticket also has below",  # drops only a repeat
    ],
)
def test_an_edit_that_would_drop_an_id_is_refused_and_left_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, block: str
) -> None:
    monkeypatch.setattr(jg, "PASTED", {jg.fingerprint(para(block)): "metric contract"})
    jira = Jira(CC_1=doc(block, "AC1. a", "TC1. c"))
    original = copy.deepcopy(jira.tickets["CC-1"])
    assert snapshot(jira, tmp_path) == 1
    assert not (tmp_path / "manifest.json").exists()
    assert jira.tickets["CC-1"] == original


def test_an_edit_that_would_add_an_id_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(jg, "GATE_LINE", "AC7. a line that reads as a criterion")
    jira = Jira(CC_1=ticket())
    assert snapshot(jira, tmp_path) == 1
    assert not (tmp_path / "manifest.json").exists()


def test_an_approved_edit_that_would_change_the_ids_is_still_not_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    monkeypatch.setattr(jg, "criterion_ids", lambda body: [str(len(body["content"]))])
    assert jg.apply(tmp_path, jira.api) == 1
    assert jira.writes == []


@pytest.mark.parametrize(
    "reworded",
    [CONTRACT + " An owner added this sentence.", AUDIT + " Except on one ticket."],
)
def test_a_reworded_copy_refuses_the_whole_ticket(tmp_path: Path, reworded: str) -> None:
    jira = Jira(CC_1=doc(CLEARANCE, reworded, "AC1. a"), CC_2=ticket())
    assert snapshot(jira, tmp_path) == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert list(manifest["tickets"]) == ["CC-2"]


def test_a_ticket_that_only_has_a_reworded_copy_is_reported_not_skipped(tmp_path: Path) -> None:
    jira = Jira(CC_1=doc(CONTRACT + " reworded"))
    assert snapshot(jira, tmp_path) == 1


def test_a_dry_run_only_reads_and_writes_both_sides(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket())
    assert snapshot(jira, tmp_path) == 0
    assert jira.calls == ["search"]
    before = (tmp_path / "CC-1.before.md").read_text(encoding="utf-8")
    after = (tmp_path / "CC-1.after.md").read_text(encoding="utf-8")
    assert CONTRACT in before and jg.GATE_LINE not in before
    assert CONTRACT not in after and jg.GATE_LINE in after
    assert json.loads((tmp_path / "CC-1.before.json").read_bytes()) == ticket()


def test_snapshot_files_survive_the_commit_hooks(tmp_path: Path) -> None:
    """A hook that trims a line or an extra final newline would void the approved hashes."""
    snapshot(Jira(CC_1=doc("Owned outcome  \n\ntrailing ", CONTRACT, "")), tmp_path)
    for path in tmp_path.glob("CC-1.*"):
        body = path.read_bytes()
        assert body.endswith(b"\n") and not body.endswith(b"\n\n"), path.name
        assert b"\r" not in body
        assert all(line == line.rstrip() for line in body.split(b"\n")), path.name


def test_approved_snapshots_are_written_and_every_id_is_kept(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket(), CC_2=doc("AC1. a", AUDIT))
    snapshot(jira, tmp_path)
    approve(tmp_path)
    assert jg.apply(tmp_path, jira.api) == 0
    assert jira.writes == ["CC-1", "CC-2"]
    assert jira.tickets["CC-1"] == jg.edit(ticket())[0]
    assert jg.criterion_ids(jira.tickets["CC-1"]) == ["AC1", "AC2", "TC1"]


def test_a_byte_order_mark_does_not_hide_an_approval(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    digest = jg._sha((tmp_path / "manifest.json").read_bytes())
    (tmp_path / "APPROVED").write_text(digest + "\r\n", encoding="utf-8-sig")
    assert jg.apply(tmp_path, jira.api) == 0


@pytest.mark.parametrize("approval", [None, "", "yes", "0" * 64])
def test_without_an_approval_nothing_is_read_or_written(
    tmp_path: Path, approval: str | None
) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    if approval is not None:
        (tmp_path / "APPROVED").write_text(approval, encoding="utf-8")
    jira.calls.clear()
    assert jg.apply(tmp_path, jira.api) == 2
    assert jira.calls == []


def test_apply_without_a_directory_exits_non_zero_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jira = Jira(CC_1=ticket())
    monkeypatch.setattr(jg.jira_transition, "_api", jira.api)
    monkeypatch.setattr(jg.jira_transition, "_load_env", lambda: None)
    with pytest.raises(SystemExit) as stopped:
        jg.main(["--apply"])
    assert stopped.value.code != 0
    assert jg.main(["--apply", "--approved", str(tmp_path / "absent")]) == 2
    assert jira.calls == []


def test_new_snapshots_void_an_earlier_approval(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    old = (tmp_path / "APPROVED").read_text(encoding="utf-8")
    (tmp_path / "APPROVED").unlink()
    jira.tickets["CC-2"] = ticket()
    snapshot(jira, tmp_path)
    (tmp_path / "APPROVED").write_text(old, encoding="utf-8")
    assert jg.apply(tmp_path, jira.api) == 2
    assert jira.writes == []


def test_a_snapshot_changed_after_approval_writes_nothing(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    (tmp_path / "CC-1.after.json").write_bytes(jg._dump(doc("something else", "AC1. a")))
    assert jg.apply(tmp_path, jira.api) == 2
    assert jira.writes == []


def test_an_approved_dir_is_not_overwritten_by_a_later_dry_run(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    kept = (tmp_path / "manifest.json").read_bytes()
    jira.tickets["CC-2"] = ticket()
    assert snapshot(jira, tmp_path) == 1
    assert (tmp_path / "manifest.json").read_bytes() == kept
    assert not (tmp_path / "CC-2.after.json").exists()


def test_new_snapshots_drop_the_files_of_a_ticket_no_longer_in_the_set(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    (tmp_path / "notes.txt").write_text("not ours", encoding="utf-8")
    del jira.tickets["CC-2"]
    snapshot(jira, tmp_path)
    assert sorted(p.name for p in tmp_path.glob("CC-2.*")) == []
    assert (tmp_path / "CC-1.after.md").exists()
    assert (tmp_path / "notes.txt").exists()


def test_only_the_rule_s_own_edit_can_be_written(tmp_path: Path) -> None:
    """Approval covers the files; the script still writes nothing but the gate-line edit."""
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    other = jg._dump(doc("AC1. a\nAC2. b", "TC1. c", "a rewritten ticket"))
    (tmp_path / "CC-1.after.json").write_bytes(other)
    manifest = json.loads((tmp_path / "manifest.json").read_bytes())
    manifest["tickets"]["CC-1"]["files"]["CC-1.after.json"] = jg._sha(other)
    (tmp_path / "manifest.json").write_bytes(jg._dump(manifest))
    approve(tmp_path)
    assert jg.apply(tmp_path, jira.api) == 1
    assert jira.writes == []


def test_a_ticket_edited_since_the_snapshot_is_left_alone(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    jira.tickets["CC-1"]["content"].append(para("the owner added a note"))
    edited = copy.deepcopy(jira.tickets["CC-1"])
    assert jg.apply(tmp_path, jira.api) == 1
    assert jira.writes == ["CC-2"]
    assert jira.tickets["CC-1"] == edited


@pytest.mark.parametrize(
    "stored",
    [doc("AC1. a"), doc("Owned outcome", "AC1. a\nAC2. b", "TC1. c")],  # lost ids, lost the line
)
def test_a_write_jira_did_not_keep_stops_the_run(tmp_path: Path, stored: dict[str, Any]) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def mangling(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        done = jira.api(method, path, body)
        if method == "PUT":
            jira.tickets["CC-1"] = stored
        return done

    assert jg.apply(tmp_path, mangling) == 1
    assert jira.writes == ["CC-1"]


def test_after_apply_a_dry_run_finds_nothing_left_and_a_second_apply_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jira = Jira(CC_1=ticket())
    first = tmp_path / "snapshots"
    snapshot(jira, first)
    approve(first)
    jg.apply(first, jira.api)
    capsys.readouterr()
    again = tmp_path / "again"
    assert snapshot(jira, again) == 0
    assert "0 ticket(s) left to change, 0 refused" in capsys.readouterr().out
    assert not again.exists()
    assert snapshot(jira, first) == 0  # the default directory, approved: still a clean pass
    jira.writes.clear()
    assert jg.apply(first, jira.api) == 0
    assert jira.writes == []
