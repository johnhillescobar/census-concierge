"""The one-time bulk edit replaces only the pasted gate wording: it never moves an AC/TC id, never
writes what the owner did not approve, and finds nothing left once it has written."""

from __future__ import annotations

import copy
import http.client
import json
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import jira_gate_line as jg  # noqa: E402

CONTRACT = "Metric progression and non-regression contract\nNo observed decrease against A."
CLEARANCE = "Mandatory AC/TC clearance before shipping\nEvery merged change owes a run."
AUDIT = "Existing AC/TC, earned floors, and the old uncertainty rule remain binding."
REAL_PASTED = dict(jg.PASTED)  # read before any test stands in its own
REAL_SENTENCES = jg.SENTENCES
# two descriptions as Jira held them before and after the edit
FIXTURES = ROOT / "api" / "tests" / "fixtures" / "gate_wording"


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
    stand_ins = (CONTRACT, CLEARANCE, AUDIT)
    sentences = {jg._sentence_mark(s) for block in stand_ins for s in jg._sentences(para(block))}
    monkeypatch.setattr(jg, "SENTENCES", frozenset(sentences))


class Jira:
    """Descriptions by key, answering as the REST API does, and a record of every write."""

    def __init__(self, **tickets: dict[str, Any]) -> None:
        self.tickets = {key.replace("_", "-"): body for key, body in tickets.items()}
        self.writes: list[str] = []
        self.calls: list[str] = []
        self.closed: set[str] = set()
        self.history: dict[str, list[dict[str, Any]]] = {key: [] for key in self.tickets}
        self.page = 100  # how many history entries one request returns

    def search(self, jql: str, *, fields: str) -> list[dict[str, Any]]:
        self.calls.append("search")
        return [
            {"key": key, "fields": {"description": copy.deepcopy(body)}}
            for key, body in self.tickets.items()
        ]

    def api(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(method)
        key = path.split("/")[2].split("?")[0]
        if method == "GET" and "/changelog?" in path:
            start = int(path.split("startAt=")[1].split("&")[0])
            entries = self.history.get(key, [])
            return {"values": entries[start : start + self.page], "total": len(entries)}
        if method == "GET":
            asked = path.split("fields=")[1].split(",")
            category = "done" if key in self.closed else "indeterminate"
            held = {
                "description": copy.deepcopy(self.tickets[key]),
                "status": {"statusCategory": {"key": category}},
            }
            return {"fields": {name: held[name] for name in asked}}
        assert method == "PUT" and body is not None
        self.writes.append(key)
        self.tickets[key] = copy.deepcopy(body["fields"]["description"])
        self.changed(key)
        return {}

    def changed(self, key: str, field: str = "description") -> None:
        """One history entry, as Jira adds for every change to a field."""
        entries = self.history.setdefault(key, [])
        entries.append({"id": f"{key}-{len(entries)}", "items": [{"fieldId": field}]})

    def owner_adds_a_note(self, key: str) -> None:
        self.tickets[key]["content"].append(para("the owner's note"))
        self.changed(key)


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
    [
        CONTRACT + " An owner added this sentence.",
        CLEARANCE + " An owner added this sentence.",
        AUDIT + " Except on one ticket.",
        CONTRACT.upper(),
        "Note: " + CLEARANCE,
        "Retained from before.\n" + AUDIT,
        "Existing AC/TC, earned\nfloors, in two lines.",
    ],
)
def test_a_reworded_copy_refuses_the_whole_ticket(tmp_path: Path, reworded: str) -> None:
    jira = Jira(CC_1=doc(CLEARANCE, reworded, "AC1. a"), CC_2=ticket())
    assert snapshot(jira, tmp_path) == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert list(manifest["tickets"]) == ["CC-2"]


def test_a_ticket_that_only_has_a_reworded_copy_is_reported_not_skipped(tmp_path: Path) -> None:
    jira = Jira(CC_1=doc(CONTRACT + " reworded"))
    assert snapshot(jira, tmp_path) == 1


LINK = {"type": "link", "attrs": {"href": "https://example.invalid/waiver"}}


@pytest.mark.parametrize(
    "addition",
    [
        {"type": "inlineCard", "attrs": {"url": "https://example.invalid/waiver"}},
        {"type": "mention", "attrs": {"id": "someone"}},
        {"type": "status", "attrs": {"text": "WAIVED"}},
        "a link on the pasted words",
        "a heading in place of the paragraph",
    ],
)
def test_a_copy_carrying_what_its_text_does_not_show_is_refused_not_deleted(
    tmp_path: Path, addition: Any
) -> None:
    body = ticket()
    block = body["content"][1]  # the contract, its words unchanged
    if isinstance(addition, dict):
        block["content"].append(addition)
    elif addition.startswith("a link"):
        block["content"][0]["marks"] = [LINK]
    else:
        block["type"] = "heading"
    assert jg.fingerprint(block) == jg.fingerprint(para(CONTRACT))
    after, _ = jg.edit(body)
    assert block in after["content"]
    jira = Jira(CC_1=body)
    assert snapshot(jira, tmp_path) == 1
    assert not (tmp_path / "manifest.json").exists()


def test_a_pasted_paragraph_split_by_line_breaks_is_still_an_exact_copy() -> None:
    first, second = CONTRACT.split("\n")
    block = para(first)
    block["content"] += [{"type": "hardBreak"}, {"type": "text", "text": second}]
    assert jg.edit({"type": "doc", "version": 1, "content": [block]})[1] == ["metric contract"]


@pytest.mark.parametrize(
    "left", [{"CC_9": doc("no wording here")}, {"CC_1": doc(CONTRACT + " reworded")}]
)
def test_a_run_with_nothing_to_write_leaves_no_earlier_set_to_approve(
    tmp_path: Path, left: dict[str, Any]
) -> None:
    snapshot(Jira(CC_1=ticket()), tmp_path)
    (tmp_path / "notes.txt").write_text("not ours", encoding="utf-8")
    snapshot(Jira(**left), tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["notes.txt"]


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


@pytest.mark.parametrize("name", ["before.json", "after.json", "before.md", "after.md"])
def test_a_snapshot_changed_after_approval_writes_nothing(tmp_path: Path, name: str) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    (tmp_path / f"CC-1.{name}").write_bytes(jg._dump(doc("something else", "AC1. a")))
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


def test_a_formatting_only_edit_since_the_snapshot_is_left_alone(tmp_path: Path) -> None:
    """A link added to the same words is the owner's edit too, and a write would remove it."""
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    link = {"type": "link", "attrs": {"href": "https://example.invalid"}}
    jira.tickets["CC-1"]["content"][0]["content"][0]["marks"] = [link]
    edited = copy.deepcopy(jira.tickets["CC-1"])
    assert jg.apply(tmp_path, jira.api) == 1
    assert jira.writes == []
    assert jira.tickets["CC-1"] == edited


def test_text_jira_stores_with_attributes_of_its_own_counts_as_written(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def annotating(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        done = jira.api(method, path, body)
        if method == "PUT":
            for node in jira.tickets[jira.writes[-1]]["content"]:
                node["attrs"] = {"localId": "set-by-jira"}
        return done

    assert jg.apply(tmp_path, annotating) == 0
    assert jira.writes == ["CC-1", "CC-2"]
    assert jg.apply(tmp_path, annotating) == 0  # already reads as approved
    assert jira.writes == ["CC-1", "CC-2"]


def test_the_readable_files_put_a_blank_line_between_blocks(tmp_path: Path) -> None:
    snapshot(Jira(CC_1=ticket()), tmp_path)
    after = (tmp_path / "CC-1.after.md").read_text(encoding="utf-8")
    assert after == f"Owned outcome\n\n{jg.GATE_LINE}\n\nAC1. a\nAC2. b\n\nTC1. c\n"


def test_the_same_tickets_give_the_same_manifest_in_any_key_order(tmp_path: Path) -> None:
    """The approval is a hash of the manifest, so key order must not reach it."""

    def reversed_keys(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: reversed_keys(value[key]) for key in reversed(list(value))}
        return [reversed_keys(item) for item in value] if isinstance(value, list) else value

    snapshot(Jira(CC_1=ticket()), tmp_path / "one")
    snapshot(Jira(CC_1=reversed_keys(ticket())), tmp_path / "two")
    assert (tmp_path / "one" / "manifest.json").read_bytes() == (
        tmp_path / "two" / "manifest.json"
    ).read_bytes()


def test_the_real_table_turns_each_snapshotted_ticket_into_its_after_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other tests stand in their own paragraphs. This one holds the real hashes and the
    real line to the descriptions that were read from Jira."""
    monkeypatch.setattr(jg, "PASTED", REAL_PASTED)
    monkeypatch.setattr(jg, "SENTENCES", REAL_SENTENCES)
    seen: set[str] = set()
    for key in ("CC-104", "CC-105"):  # between them they hold every pasted paragraph
        before, after = (
            json.loads((FIXTURES / f"{key}.{side}.json").read_bytes())
            for side in ("before", "after")
        )
        assert jg.edit(before)[0] == after, key
        assert jg.refusal(before, after) is None, key
        seen |= {jg.fingerprint(node) for node in before["content"]} & set(REAL_PASTED)
    assert seen == set(REAL_PASTED)


def never(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("this command used a Jira client it must not")


def test_the_dry_run_command_asks_for_open_tickets_and_only_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requests: list[tuple[str, str, dict[str, Any]]] = []

    def reading(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        requests.append((method, path, body))
        return {"issues": [{"key": "CC-1", "fields": {"description": ticket()}}]}

    monkeypatch.setattr(jg.jira_fetch, "_api", reading)
    monkeypatch.setattr(jg.jira_transition, "_api", never)
    monkeypatch.setattr(jg.jira_transition, "_load_env", lambda: None)
    monkeypatch.setattr(jg, "OUT", tmp_path / "default")
    out = tmp_path / "snapshots"
    assert jg.main(["--dry-run", "--out", str(out)]) == 0
    [(method, path, body)] = requests
    assert (method, path) == ("POST", "/search/jql")  # Jira's search is a POST that only reads
    assert body["jql"].startswith("project = CC AND statusCategory != Done ")
    assert body["fields"] == ["description"]
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert manifest["tickets"]["CC-1"]["ids"] == ["AC1", "AC2", "TC1"]


def test_the_apply_command_writes_what_the_printed_hash_approves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    printed = capsys.readouterr().out.strip().splitlines()[-1].rsplit(": ", 1)[1]
    (tmp_path / "APPROVED").write_text(printed + "\n", encoding="utf-8")
    loaded: list[bool] = []
    monkeypatch.setattr(jg.jira_transition, "_load_env", lambda: loaded.append(True))
    monkeypatch.setattr(jg.jira_transition, "_api", jira.api)
    monkeypatch.setattr(jg.jira_fetch, "_api", never)
    monkeypatch.setattr(jg.jira_fetch, "_search", never)
    assert jg.main(["--apply", "--approved", str(tmp_path)]) == 0
    assert jira.writes == ["CC-1"]
    assert loaded == [True]


def test_a_dry_run_and_an_apply_asked_at_once_write_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    jira.calls.clear()
    monkeypatch.setattr(jg.jira_transition, "_load_env", lambda: None)
    monkeypatch.setattr(jg.jira_transition, "_api", jira.api)
    monkeypatch.setattr(jg.jira_fetch, "_search", jira.search)
    monkeypatch.setattr(jg, "OUT", tmp_path / "default")
    with pytest.raises(SystemExit) as stopped:
        jg.main(["--dry-run", "--apply", "--approved", str(tmp_path)])
    assert stopped.value.code != 0
    assert jira.calls == []


def structured() -> dict[str, Any]:
    """A ticket with the things its visible text does not show: a link, a card and a list."""
    body = ticket()
    body["content"][0]["content"][0]["marks"] = [copy.deepcopy(LINK)]
    body["content"][0]["content"].append(
        {"type": "inlineCard", "attrs": {"url": "https://example.invalid/card"}}
    )
    body["content"].append(
        {"type": "bulletList", "content": [{"type": "listItem", "content": [para("a point")]}]}
    )
    return body


@pytest.mark.parametrize(
    "lost", ["the link", "the card", "the card's address", "the list structure"]
)
def test_a_write_that_loses_what_the_text_does_not_show_stops_the_run(
    tmp_path: Path, lost: str
) -> None:
    jira = Jira(CC_1=structured(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def dropping(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        done = jira.api(method, path, body)
        if method == "PUT":
            blocks = jira.tickets["CC-1"]["content"]
            if lost == "the link":
                del blocks[0]["content"][0]["marks"]
            elif lost == "the card":
                del blocks[0]["content"][1]
            elif lost == "the card's address":
                blocks[0]["content"][1]["attrs"]["url"] = "https://example.invalid/other"
            else:
                blocks[-1] = para("a point")
        return done

    assert jg.apply(tmp_path, dropping) == 1
    assert jira.writes == ["CC-1"]
    assert (tmp_path / "FAILED").read_text(encoding="utf-8").startswith("CC-1:")


@pytest.mark.parametrize(
    "fault",
    [
        urllib.error.URLError("timed out"),
        TimeoutError("read timed out"),
        http.client.IncompleteRead(b""),
        ValueError("not JSON"),
        SystemExit(1),  # what the real client does on an HTTP error
    ],
)
@pytest.mark.parametrize("during", ["PUT", "GET"])
def test_a_write_that_cannot_be_confirmed_fails_loudly_and_stays_stopped(
    tmp_path: Path, fault: BaseException, during: str, capsys: pytest.CaptureFixture[str]
) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    put: list[bool] = []

    def faulty(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == during and (during == "PUT" or put):
            raise fault
        if method == "PUT":
            put.append(True)
        return jira.api(method, path, body)

    assert jg.apply(tmp_path, faulty) == 1
    assert "CC-1.before.json" in capsys.readouterr().err
    written = list(jira.writes)
    jira.calls.clear()
    assert jg.apply(tmp_path, jira.api) == 2  # a rerun must not carry on to the next ticket
    assert jira.calls == [] and jira.writes == written


def test_an_applied_ticket_that_has_since_lost_a_link_is_not_reported_done(tmp_path: Path) -> None:
    jira = Jira(CC_1=structured())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    assert jg.apply(tmp_path, jira.api) == 0
    del jira.tickets["CC-1"]["content"][0]["content"][0]["marks"]  # same words, no link
    jira.writes.clear()
    assert jg.apply(tmp_path, jira.api) == 1
    assert jira.writes == []


@pytest.mark.parametrize("during", ["PUT", "GET"])
def test_a_run_interrupted_before_the_write_is_confirmed_stays_stopped(
    tmp_path: Path, during: str
) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    put: list[bool] = []

    def interrupted(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == "PUT":
            put.append(True)
        if method == during and put:
            raise KeyboardInterrupt
        return jira.api(method, path, body)

    with pytest.raises(KeyboardInterrupt):
        jg.apply(tmp_path, interrupted)
    assert "CC-1" in (tmp_path / "FAILED").read_text(encoding="utf-8")
    jira.calls.clear()
    assert jg.apply(tmp_path, jira.api) == 2
    assert jira.calls == []


def test_a_confirmed_write_leaves_no_stop_file(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    assert jg.apply(tmp_path, jira.api) == 0
    assert not (tmp_path / "FAILED").exists()


@pytest.mark.parametrize("approval_kept", [True, False])
@pytest.mark.parametrize("left", ["tickets to change", "nothing to change"])
def test_a_dry_run_leaves_the_files_to_restore_from_alone(
    tmp_path: Path, approval_kept: bool, left: str
) -> None:
    snapshot(Jira(CC_1=ticket()), tmp_path)
    approve(tmp_path)
    if not approval_kept:
        (tmp_path / "APPROVED").unlink()
    (tmp_path / "FAILED").write_text("CC-1: did not hold\n", encoding="utf-8")
    kept = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    later = ticket() if left == "tickets to change" else doc("no wording here")
    assert snapshot(Jira(CC_2=later), tmp_path) == 1
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == kept


def test_a_ticket_closed_after_the_snapshot_is_left_alone(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    jira.closed.add("CC-1")
    assert jg.apply(tmp_path, jira.api) == 1
    assert jira.writes == ["CC-2"]
    assert jira.tickets["CC-1"] == ticket()


def test_a_ticket_the_dry_run_refused_is_still_reported_by_apply(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jira = Jira(CC_1=doc(CONTRACT + " reworded"), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    capsys.readouterr()
    assert jg.apply(tmp_path, jira.api) == 1
    out = capsys.readouterr().out
    assert "REFUSED  CC-1" in out and "1 written, 1 refused" in out
    assert jira.writes == ["CC-2"]


@pytest.mark.parametrize("wording", ["NOT approved {}", "{} rejected", "{0} {0}"])
def test_a_file_that_says_more_than_the_hash_is_not_an_approval(
    tmp_path: Path, wording: str
) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    digest = jg._sha((tmp_path / "manifest.json").read_bytes())
    (tmp_path / "APPROVED").write_text(wording.format(digest), encoding="utf-8")
    jira.calls.clear()
    assert jg.apply(tmp_path, jira.api) == 2
    assert jira.calls == []


def test_a_search_that_returns_nothing_is_a_fault_and_touches_nothing(tmp_path: Path) -> None:
    snapshot(Jira(CC_1=ticket()), tmp_path)
    kept = sorted(p.name for p in tmp_path.iterdir())
    assert snapshot(Jira(), tmp_path) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == kept


def test_a_dry_run_says_how_many_tickets_it_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot(Jira(CC_1=ticket(), CC_2=doc("no wording"), CC_3=doc("none here")), tmp_path)
    assert "3 open ticket(s) read: 1 ticket(s) left to change, 0 refused" in capsys.readouterr().out


def _pointer_survives(shape: str) -> list[dict[str, Any]]:
    head, tail = jg.OLD_POINTER[:14], jg.OLD_POINTER[14:]
    if shape == "split by formatting":
        bold = {"type": "text", "text": head, "marks": [{"type": "strong"}]}
        return [{"type": "paragraph", "content": [bold, {"type": "text", "text": tail}]}]
    if shape == "inside a panel":
        return [{"type": "panel", "content": [para(jg.OLD_POINTER)]}]
    if shape == "after a newline":
        return [para("A heading line\n" + jg.OLD_POINTER)]
    return [para(jg.OLD_POINTER.replace("contract above", "contract\nabove"))]


@pytest.mark.parametrize(
    "shape", ["split by formatting", "inside a panel", "after a newline", "broken mid-phrase"]
)
def test_a_pointer_the_edit_cannot_shorten_refuses_the_ticket(tmp_path: Path, shape: str) -> None:
    body = doc(CONTRACT, "AC1. a")
    body["content"] += _pointer_survives(shape)
    assert snapshot(Jira(CC_1=body), tmp_path) == 1
    assert not (tmp_path / "manifest.json").exists()


# --- an edit that arrives during a write -------------------------------------------------------


@pytest.mark.parametrize("when", ["after the last read", "after the write", "after the read-back"])
def test_an_edit_that_arrives_during_a_write_stops_the_run(tmp_path: Path, when: str) -> None:
    """Jira cannot refuse a stale write, so the history is what shows the other edit."""
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    done: list[bool] = []
    put: list[bool] = []

    def racing(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        reading = method == "GET" and "/changelog?" not in path
        if method == "PUT":
            put.append(True)
        if not done and when == "after the read-back" and put and "/changelog?" in path:
            done.append(True)
            jira.owner_adds_a_note("CC-1")
        answer = jira.api(method, path, body)
        if not done and when == "after the last read" and reading and not put:
            done.append(True)
            jira.owner_adds_a_note("CC-1")  # the write that follows removes it
        if not done and when == "after the write" and method == "PUT":
            done.append(True)
            jira.owner_adds_a_note("CC-1")
        return answer

    assert jg.apply(tmp_path, racing) == 1
    assert done and jira.writes == ["CC-1"]
    stopped = (tmp_path / "FAILED").read_text(encoding="utf-8")
    assert "2 description changes" in stopped and "History" in stopped


def test_a_write_the_history_does_not_show_is_not_called_done(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def lagging(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        done = jira.api(method, path, body)
        if method == "PUT":
            jira.history["CC-1"].clear()
        return done

    assert jg.apply(tmp_path, lagging) == 1
    assert jira.writes == ["CC-1"]
    assert "does not show this write" in (tmp_path / "FAILED").read_text(encoding="utf-8")


@pytest.mark.parametrize("raced", [False, True])
def test_a_history_longer_than_one_page_is_read_to_the_end(tmp_path: Path, raced: bool) -> None:
    jira = Jira(CC_1=ticket())
    jira.page = 2
    for _ in range(5):
        jira.changed("CC-1")
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def maybe_raced(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if raced and method == "PUT":
            jira.owner_adds_a_note("CC-1")
        return jira.api(method, path, body)

    assert jg.apply(tmp_path, maybe_raced) == (1 if raced else 0)


def test_a_change_to_another_field_during_a_write_does_not_stop_the_run(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def busy(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == "PUT":
            jira.changed(path.split("/")[2], "status")
        return jira.api(method, path, body)

    assert jg.apply(tmp_path, busy) == 0
    assert jira.writes == ["CC-1", "CC-2"]


# --- two runs at once --------------------------------------------------------------------------


def test_a_second_apply_of_the_same_folder_cannot_run_beside_the_first(tmp_path: Path) -> None:
    """The first fails and leaves its stop file; a second that started meanwhile must not run, so
    it cannot take that file away."""
    first, second = Jira(CC_1=ticket()), Jira(CC_1=ticket())
    snapshot(first, tmp_path)
    approve(tmp_path)
    codes: list[int] = []

    def drops_the_write(
        method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not codes:
            codes.append(jg.apply(tmp_path, second.api))
        return {} if method == "PUT" else first.api(method, path, body)

    assert jg.apply(tmp_path, drops_the_write) == 1
    assert codes == [2] and second.calls == []
    assert (tmp_path / "FAILED").is_file()


@pytest.mark.parametrize("ending", ["written", "refused", "failed", "interrupted", "stopped"])
def test_an_apply_that_has_ended_leaves_the_folder_free(tmp_path: Path, ending: str) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    if ending == "refused":
        jira.closed.add("CC-1")
    if ending == "stopped":
        (tmp_path / "FAILED").write_text("CC-1: earlier\n", encoding="utf-8")

    def ends(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == "PUT" and ending == "failed":
            return {}
        if method == "PUT" and ending == "interrupted":
            raise KeyboardInterrupt
        return jira.api(method, path, body)

    if ending == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            jg.apply(tmp_path, ends)
    else:
        jg.apply(tmp_path, ends)
    assert not (tmp_path / "APPLYING").exists()


def test_a_lock_left_by_a_killed_run_blocks_until_a_person_removes_it(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    (tmp_path / "APPLYING").write_bytes(b"")
    jira.calls.clear()
    assert jg.apply(tmp_path, jira.api) == 2
    assert jira.calls == [] and (tmp_path / "APPLYING").exists()
    (tmp_path / "APPLYING").unlink()
    assert jg.apply(tmp_path, jira.api) == 0


def test_an_unapproved_folder_gets_no_lock_file(tmp_path: Path) -> None:
    snapshot(Jira(CC_1=ticket()), tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    assert jg.apply(tmp_path, never) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == before


# --- an inexact copy must not stand beside the gate line --------------------------------------


def _real_copies() -> list[tuple[str, str]]:
    """(ticket, fingerprint) for each pasted paragraph, from the two stored descriptions."""
    found: dict[str, str] = {}
    for key in ("CC-105", "CC-104"):
        for node in json.loads((FIXTURES / f"{key}.before.json").read_bytes())["content"]:
            if jg.fingerprint(node) in REAL_PASTED:
                found.setdefault(jg.fingerprint(node), key)
    return [(key, mark) for mark, key in found.items()]


@pytest.fixture
def real_wording(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jg, "PASTED", REAL_PASTED)
    monkeypatch.setattr(jg, "SENTENCES", REAL_SENTENCES)


def _altered(key: str, mark: str, change: str) -> dict[str, Any]:
    """A stored description with one pasted paragraph altered."""
    body = json.loads((FIXTURES / f"{key}.before.json").read_bytes())
    node = next(n for n in body["content"] if jg.fingerprint(n) == mark)
    first = node["content"][0]
    heading, newline, rest = first["text"].partition("\n")
    if change == "one word of the opening":
        words = heading.split(" ")
        words[1] = "&" if words[1] == "and" else words[1] + "s"
        heading = " ".join(words).replace(" and ", " & ")
    else:
        heading = "Earlier rules, kept for reference. " + heading[40:]
    first["text"] = heading + newline + rest
    return body


@pytest.mark.parametrize("change", ["one word of the opening", "the whole opening"])
@pytest.mark.parametrize(("key", "mark"), _real_copies())
def test_a_copy_with_an_altered_opening_refuses_the_ticket(
    real_wording: None, tmp_path: Path, key: str, mark: str, change: str
) -> None:
    body = _altered(key, mark, change)
    assert jg.fingerprint(body) != jg.fingerprint(
        json.loads((FIXTURES / f"{key}.before.json").read_bytes())
    )
    jira = Jira(**{key.replace("-", "_"): body})
    assert snapshot(jira, tmp_path) == 1
    assert not (tmp_path / "manifest.json").exists()


def test_one_old_sentence_left_anywhere_is_reported(real_wording: None, tmp_path: Path) -> None:
    """What a second dry run sees if a copy was altered past recognition by its opening."""
    source = json.loads((FIXTURES / "CC-105.before.json").read_bytes())
    node = next(n for n in source["content"] if jg.fingerprint(n) in REAL_PASTED)
    sentence = max(jg._lines(node), key=len).split(". ")[0] + "."
    jira = Jira(CC_1=doc(jg.GATE_LINE, "A paragraph of its own.\n" + sentence))
    assert snapshot(jira, tmp_path) == 1


def test_the_sentence_table_is_the_five_pasted_paragraphs(real_wording: None) -> None:
    expected: set[str] = set()
    for key, mark in _real_copies():
        body = json.loads((FIXTURES / f"{key}.before.json").read_bytes())
        node = next(n for n in body["content"] if jg.fingerprint(n) == mark)
        expected |= {jg._sentence_mark(s) for s in jg._sentences(node)}
    assert len(_real_copies()) == len(REAL_PASTED)
    assert expected == REAL_SENTENCES


# --- cleanup removes snapshot files and nothing else ------------------------------------------


def _names(key: str) -> dict[str, str]:
    return {name: "0" for name in jg._snapshot_names(key)}


@pytest.mark.parametrize(
    "bad",
    [
        "a file above the folder",
        "an absolute path",
        "another file in the folder",
        "a key that is a path",
        "another ticket's files",
        "one bad entry after a good one",
        "not JSON",
    ],
)
def test_a_manifest_that_names_other_files_removes_nothing(tmp_path: Path, bad: str) -> None:
    out = tmp_path / "snapshots"
    snapshot(Jira(CC_1=ticket()), out)
    victim = tmp_path / "unrelated.txt"
    victim.write_text("keep me", encoding="utf-8")
    (out / "notes.txt").write_text("keep me too", encoding="utf-8")
    (tmp_path / "x.before.json").write_text("keep", encoding="utf-8")
    manifest = json.loads((out / "manifest.json").read_bytes())
    files = manifest["tickets"]["CC-1"]["files"]
    if bad == "a file above the folder":
        files["../unrelated.txt"] = "0"
    elif bad == "an absolute path":
        files[str(victim)] = "0"
    elif bad == "another file in the folder":
        files["notes.txt"] = "0"
    elif bad == "a key that is a path":
        manifest["tickets"]["../x"] = {"files": _names("../x")}
    elif bad == "another ticket's files":
        manifest["tickets"]["CC-2"] = {"files": _names("CC-1")}
    elif bad == "one bad entry after a good one":
        manifest["tickets"]["CC-2"] = {"files": {"../unrelated.txt": "0"}}
    raw = "{ not json" if bad == "not JSON" else json.dumps(manifest)
    (out / "manifest.json").write_text(raw, encoding="utf-8")
    kept = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert snapshot(Jira(CC_9=ticket()), out) == 1
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == kept


@pytest.mark.parametrize("name", ["../unrelated.txt", "notes.txt"])
def test_an_approved_manifest_that_names_other_files_writes_nothing(
    tmp_path: Path, name: str
) -> None:
    out = tmp_path / "snapshots"
    snapshot(Jira(CC_1=ticket()), out)
    other = (out / name).resolve()
    other.write_bytes(b"x")
    manifest = json.loads((out / "manifest.json").read_bytes())
    manifest["tickets"]["CC-1"]["files"][name] = jg._sha(b"x")
    (out / "manifest.json").write_bytes(jg._dump(manifest))
    approve(out)
    assert jg.apply(out, never) == 2
