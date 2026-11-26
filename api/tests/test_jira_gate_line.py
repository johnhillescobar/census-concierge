"""The one-time bulk edit replaces only the pasted gate wording: it never moves an AC/TC id, never
writes what the owner did not approve, and finds nothing left once it has written."""

from __future__ import annotations

import copy
import http.client
import io
import json
import sys
import tempfile
import urllib.error
import urllib.request
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


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches Jira: a request nobody stood in for fails it."""

    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a test tried to open a connection")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)


# the inline formatting real Jira's text was seen to show, as its wiki markup writes it
MARKUP = {"code": ("{{", "}}"), "strong": ("*", "*"), "em": ("_", "_")}


def wiki(node: Any) -> str:
    """Links and the marks above show in the text. How other nodes and marks look there was not
    observed, so they add nothing here."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        text = str(node.get("text") or "")
        for mark in node.get("marks") or []:
            if mark["type"] == "link":
                text = f"[{text}|{mark['attrs']['href']}]"
            elif mark["type"] in MARKUP:
                text = MARKUP[mark["type"]][0] + text + MARKUP[mark["type"]][1]
        return text
    if node.get("type") == "hardBreak":
        return "\n"
    inner = "".join(wiki(child) for child in node.get("content") or [])
    return inner + "\n" if node.get("type") in jg.closure.LINE_NODES else inner


def as_text(body: Any) -> str | None:
    """The description as the history and API v2 write it. An empty one is null."""
    return None if body is None else wiki(body)


class Jira:
    """Descriptions by key, in the reply shapes Jira was seen to use, and a record of every
    write. Assumed, because only a write or a moved ticket would show it: a write adds its
    history entry at once and in the same text; a read right after it is current; a moved ticket
    still answers to its old key, for writes too (the worst case)."""

    def __init__(self, **tickets: dict[str, Any]) -> None:
        self.tickets = {key.replace("_", "-"): body for key, body in tickets.items()}
        self.writes: list[str] = []
        self.calls: list[str] = []
        self.closed: set[str] = set()
        self.moved: dict[str, str] = {}  # old key -> the key the ticket answers with now
        self.history: dict[str, list[dict[str, Any]]] = {key: [] for key in self.tickets}
        self.page = 100  # how many history entries one request returns
        self.entries = 10000  # history ids are numbers, never reused

    def _status(self, key: str) -> dict[str, Any]:
        return {"statusCategory": {"key": "done" if key in self.closed else "indeterminate"}}

    def _reply(self, key: str, fields: dict[str, Any]) -> dict[str, Any]:
        return {"id": "1", "key": self.moved.get(key, key), "fields": fields}

    def search(self, jql: str, *, fields: str) -> list[dict[str, Any]]:
        self.calls.append("search")
        assert fields == "status"
        return [{"id": "1", "key": key, "fields": {}} for key in self.tickets]

    def api(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(method)
        key = path.split("/")[2].split("?")[0]
        if method == "GET" and "/changelog?" in path:
            start = int(path.split("startAt=")[1].split("&")[0])
            entries = self.history.get(key, [])
            values = copy.deepcopy(entries[start : start + self.page])
            return {
                "startAt": start,
                "maxResults": self.page,
                "total": len(entries),
                "isLast": start + len(values) >= len(entries),
                "values": values,
            }
        if method == "GET" and path.startswith("/rest/api/2/"):
            key = path.split("/")[5].split("?")[0]
            return self._reply(key, {"description": as_text(self.tickets[key])})
        if method == "GET":
            asked = path.split("fields=")[1].split(",")
            held = {
                "description": copy.deepcopy(self.tickets[key]),
                "status": self._status(key),
            }
            return self._reply(key, {name: held[name] for name in asked})
        assert method == "PUT" and body is not None
        self.writes.append(key)
        was = as_text(self.tickets[key])
        self.tickets[key] = copy.deepcopy(body["fields"]["description"])
        self.changed(key, was=was)
        return {}  # what jira_transition._api makes of an empty reply (its code; no write sent)

    def changed(self, key: str, field: str = "description", was: str | None = None) -> None:
        """One history entry, as Jira adds for every change to a field."""
        now = as_text(self.tickets[key]) if key in self.tickets else ""
        item = {
            "field": field,
            "fieldtype": "jira",
            "fieldId": field,
            "from": None,
            "fromString": now if was is None else was,
            "to": None,
            "toString": now,
        }
        self.entries += 1
        self.history.setdefault(key, []).append(
            {
                "id": str(self.entries),
                "author": {"accountId": "someone"},
                "created": "2026-01-01T00:00:00.000+0000",
                "items": [item],
            }
        )

    def owner_adds_a_note(self, key: str) -> None:
        was = as_text(self.tickets[key])
        self.tickets[key]["content"].append(para("the owner's note"))
        self.changed(key, was=was)


def ticket() -> dict[str, Any]:
    return doc("Owned outcome", CONTRACT, "AC1. a\nAC2. b", CLEARANCE, "TC1. c")


def approve(folder: Path) -> None:
    digest = jg._sha((folder / "manifest.json").read_bytes())
    (folder / "APPROVED").write_text(digest + "\n", encoding="utf-8")


def snapshot(jira: Jira, folder: Path) -> int:
    return jg.dry_run(folder, jira.search, jira.api)


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
        "EXISTING AC/TC, EARNED FLOORS, rewritten since.",
        "Note: " + CLEARANCE,
        "Retained from before.\n" + AUDIT,
        "Existing AC/TC, earned\nfloors, in two lines.",
        # no sentence of the pasted wording is left whole, so only the opening words show it
        "Metric progression and non-regression contract, rewritten since.",
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
    assert jira.calls == ["search", "GET"]
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
    # the history proof stops this run too; the comparison of what Jira holds is what must say it
    assert "does not hold the approved description" in (tmp_path / "FAILED").read_text("utf-8")


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
    assert snapshot(jira, first) == 0  # the approved directory itself: still a clean pass
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

    jira = Jira(CC_1=ticket())
    monkeypatch.setattr(jg.jira_fetch, "_api", reading)
    monkeypatch.setattr(jg.jira_transition, "_api", jira.api)
    monkeypatch.setattr(jg.jira_transition, "_load_env", lambda: None)
    monkeypatch.setattr(jg, "OUT", tmp_path / "default")
    out = tmp_path / "snapshots"
    assert jg.main(["--dry-run", "--out", str(out)]) == 0
    assert jira.calls == ["GET"] and jira.writes == []
    [(method, path, body)] = requests
    assert (method, path) == ("POST", "/search/jql")  # Jira's search is a POST that only reads
    assert body["jql"].startswith("project = CC AND statusCategory != Done ")
    assert body["fields"] == ["status"]
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
    opened: list[tuple[str, str, str]] = []

    def serving(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        auth = str(request.get_header("Authorization"))
        opened.append((request.get_method(), request.full_url, auth))
        path = request.full_url.removeprefix("https://jira.invalid")
        return io.BytesIO(json.dumps(jira.api("GET", path)).encode())

    def v3_only(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        assert path.startswith("/issue/"), path
        return jira.api(method, path, body)

    monkeypatch.setattr(urllib.request, "urlopen", serving)
    monkeypatch.setattr(jg.jira_transition, "_site", lambda: "jira.invalid")
    monkeypatch.setattr(jg.jira_transition, "_auth_header", lambda: {"Authorization": "stand-in"})
    monkeypatch.setattr(jg.jira_transition, "_load_env", lambda: loaded.append(True))
    monkeypatch.setattr(jg.jira_transition, "_api", v3_only)
    monkeypatch.setattr(jg.jira_fetch, "_api", never)
    monkeypatch.setattr(jg.jira_fetch, "_search", never)
    assert jg.main(["--apply", "--approved", str(tmp_path)]) == 0
    assert jira.writes == ["CC-1"]
    assert loaded == [True]
    text_read = "https://jira.invalid/rest/api/2/issue/CC-1?fields=description"
    assert opened == [("GET", text_read, "stand-in")] * 2  # before the write, and after it


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
        reading = path.endswith("fields=description,status")
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
    # the before snapshot lacks the other edit, so copying it back would lose it again
    assert "restore it from there" not in stopped
    assert "put back only what this write took out" in stopped


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
        "a key from another project",
        "a CC key that is a path",
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
    elif bad == "a key from another project":
        manifest["tickets"]["EXT-2"] = {"files": _names("EXT-2")}
    elif bad == "a CC key that is a path":
        manifest["tickets"]["CC-/../../x"] = {"files": _names("CC-/../../x")}
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


# --- another person's change must not pass for this write -------------------------------------


NOT_THIS_WRITE = "not shown to be this write"


@pytest.mark.parametrize(
    ("when", "unlisted", "said"),
    [
        # the one entry listed is the owner's, then this write's
        ("before the write", "this write's entry", NOT_THIS_WRITE),
        ("before the write", "the owner's entry", NOT_THIS_WRITE),
        # the owner's note is still on the ticket when it is read last
        ("after the text read-back", "this write's entry", "does not hold the approved"),
    ],
)
def test_one_listed_change_that_is_not_shown_to_be_this_write_stops_the_run(
    tmp_path: Path, when: str, unlisted: str, said: str
) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    put: list[bool] = []
    done: list[bool] = []

    def racing(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        history = "/CC-1/changelog?" in path
        if method == "PUT":
            if when == "before the write" and not done:
                done.append(True)
                jira.owner_adds_a_note("CC-1")
            put.append(True)
        if when == "after the text read-back" and put and history and not done:
            done.append(True)
            jira.owner_adds_a_note("CC-1")
        answer = jira.api(method, path, body)
        if put and history:
            entries = list(jira.history["CC-1"])
            owners, own = entries if when == "before the write" else entries[::-1]
            seen = [owners if unlisted == "this write's entry" else own]
            return {"values": seen, "total": 1}
        return answer

    assert jg.apply(tmp_path, racing) == 1
    assert done and jira.writes == ["CC-1"]
    stopped = (tmp_path / "FAILED").read_text(encoding="utf-8")
    assert said in stopped and "before restoring anything" in stopped
    assert "put back only what this write took out" in stopped


@pytest.mark.parametrize("missing", ["fromString", "toString"])
def test_a_history_entry_without_its_text_is_not_taken_for_this_write(
    tmp_path: Path, missing: str
) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def bare(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        done = jira.api(method, path, body)
        if method == "PUT":
            del jira.history["CC-1"][-1]["items"][0][missing]
        return done

    assert jg.apply(tmp_path, bare) == 1
    assert "not shown to be this write" in (tmp_path / "FAILED").read_text(encoding="utf-8")


def test_an_edit_between_the_reads_before_a_write_is_never_written_over(tmp_path: Path) -> None:
    """Whichever read comes first, the owner edits right after it and the history has not listed
    the edit. The text compared with the history must not be one that already holds it."""
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    done: list[bool] = []

    def racing(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        answer = jira.api(method, path, body)
        if not done and method == "GET" and "/changelog?" not in path:
            done.append(True)
            jira.tickets["CC-1"]["content"].append(para("the owner's note"))
        return answer

    assert jg.apply(tmp_path, racing) == 1
    assert jira.writes == []
    assert "the owner's note" in texts(jira.tickets["CC-1"])


# --- a ticket that closes while it is being written --------------------------------------------


@pytest.mark.parametrize("when", ["just before the write", "just after the write"])
def test_a_ticket_that_closed_during_its_write_stops_the_run(tmp_path: Path, when: str) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def closing(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == "PUT" and when == "just before the write":
            jira.closed.add("CC-1")
        answer = jira.api(method, path, body)
        if method == "PUT":
            jira.closed.add("CC-1")
        return answer

    assert jg.apply(tmp_path, closing) == 1
    assert jira.writes == ["CC-1"]
    assert "reads as closed" in (tmp_path / "FAILED").read_text(encoding="utf-8")


# --- where a routine dry run puts its files ----------------------------------------------------


def test_the_default_snapshot_folder_is_outside_the_repository() -> None:
    assert jg.OUT.is_relative_to(Path(tempfile.gettempdir()))
    assert not jg.OUT.is_relative_to(jg.ROOT)


# --- the search may be behind: each ticket is read from its own record -------------------------


@pytest.mark.parametrize("approved_dir", [True, False])
def test_a_search_from_before_the_apply_does_not_report_work_left(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], approved_dir: bool
) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    first = tmp_path / "snapshots"
    snapshot(jira, first)
    approve(first)
    behind = jira.search(jg.OPEN_JQL, fields="status")
    for found in behind:
        found["fields"] = {"description": ticket()}  # the search still holds the old text
    assert jg.apply(first, jira.api) == 0
    capsys.readouterr()
    out = first if approved_dir else tmp_path / "again"
    assert jg.dry_run(out, lambda *args, **kwargs: behind, jira.api) == 0
    assert "2 open ticket(s) read: 0 ticket(s) left to change, 0 refused" in capsys.readouterr().out


def test_wording_a_ticket_holds_now_is_found_when_the_search_does_not_show_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jira = Jira(CC_1=ticket())

    def behind(jql: str, *, fields: str) -> list[dict[str, Any]]:
        return [{"key": "CC-1", "fields": {"description": doc("no wording here")}}]

    assert jg.dry_run(tmp_path, behind, jira.api) == 0
    assert "1 ticket(s) left to change" in capsys.readouterr().out
    assert json.loads((tmp_path / "CC-1.before.json").read_bytes()) == ticket()


def test_a_ticket_closed_since_the_search_listed_it_is_not_snapshotted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    jira.closed.add("CC-1")
    assert snapshot(jira, tmp_path) == 0
    assert "1 open ticket(s) read: 1 ticket(s) left to change" in capsys.readouterr().out
    manifest = json.loads((tmp_path / "manifest.json").read_bytes())
    assert list(manifest["tickets"]) == ["CC-2"]


def test_a_ticket_that_cannot_be_read_leaves_the_earlier_set_as_it_was(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    kept = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    def failing(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        raise SystemExit(1)  # what the real client does on an HTTP error

    with pytest.raises(SystemExit):
        jg.dry_run(tmp_path, jira.search, failing)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == kept


# --- one change by another person, before each request of a write -------------------------------

# the requests one write makes about its ticket, in order
REQUESTS = ["history", "text", "ticket", "write", "text", "history", "ticket"]
JUST_BEFORE_THE_WRITE = REQUESTS.index("write")  # earlier positions come before a read that does
AFTER_THE_LAST_READ = len(REQUESTS)


def request_kind(method: str, path: str) -> str:
    if method == "PUT":
        return "write"
    if "/changelog?" in path:
        return "history"
    return "text" if path.startswith("/rest/api/2/") else "ticket"


def about_cc1(path: str) -> bool:
    return path.endswith("/issue/CC-1") or "/issue/CC-1?" in path or "/issue/CC-1/" in path


def two_tickets(folder: Path) -> Jira:
    """CC-1 and CC-2, snapshotted and approved."""
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    snapshot(jira, folder)
    approve(folder)
    return jira


def test_a_write_reads_the_ticket_itself_last(tmp_path: Path) -> None:
    jira = two_tickets(tmp_path)
    seen: list[str] = []

    def watching(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if about_cc1(path):
            seen.append(request_kind(method, path))
        return jira.api(method, path, body)

    assert jg.apply(tmp_path, watching) == 0
    assert seen == REQUESTS


class Race:
    """One change by another person before request number `when` about CC-1 (or after the last),
    and the history entries of one side, or both, not listed for the rest of the run."""

    def __init__(self, jira: Jira, change: str, when: int, unlisted: str) -> None:
        self.jira, self.change, self.when, self.unlisted = jira, change, when, unlisted
        self.seen = 0
        self.happened = False
        self.hidden: set[str] = set()

    def hide(self, side: str, since: int) -> None:
        if self.unlisted in (side, "both"):
            self.hidden |= {entry["id"] for entry in self.jira.history["CC-1"][since:]}

    def happen(self) -> None:
        self.happened = True
        since = len(self.jira.history["CC-1"])
        if self.change == "an edit":
            self.jira.owner_adds_a_note("CC-1")
        elif self.change in ("a link", "code", "strong", "em"):
            was = as_text(self.jira.tickets["CC-1"])
            mark = copy.deepcopy(LINK) if self.change == "a link" else {"type": self.change}
            self.jira.tickets["CC-1"]["content"][0]["content"][0]["marks"] = [mark]
            self.jira.changed("CC-1", was=was)
        elif self.change == "a close":
            self.jira.closed.add("CC-1")
        else:
            self.jira.moved["CC-1"] = "EXT-2"
        self.hide("the other change's", since)

    def api(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        mine = about_cc1(path)
        if mine and not self.happened and self.seen == self.when:
            self.happen()
        since = len(self.jira.history["CC-1"])
        answer = self.jira.api(method, path, body)
        if mine and method == "PUT":
            self.hide("this write's", since)
        if "/changelog?" in path:
            listed = [entry for entry in answer["values"] if entry["id"] not in self.hidden]
            answer = {**answer, "values": listed, "total": len(listed)}
        if mine:
            self.seen += 1
            if self.seen == self.when == AFTER_THE_LAST_READ:
                self.happen()
        return answer


RACES = [
    (change, when, unlisted)
    for change in ("an edit", "a link", "a close", "a move")
    for when in range(AFTER_THE_LAST_READ + 1)
    for unlisted in (
        ("nothing", "the other change's", "this write's", "both")
        if change in ("an edit", "a link")
        else ("nothing", "this write's")
    )
]
TRACES = {"an edit": "the owner's note", "a link": LINK["attrs"]["href"]}


@pytest.mark.parametrize(("change", "when", "unlisted"), RACES)
def test_another_change_at_any_point_of_a_write_is_never_hidden_by_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    change: str,
    when: int,
    unlisted: str,
) -> None:
    jira = two_tickets(tmp_path)
    race = Race(jira, change, when, unlisted)
    capsys.readouterr()
    code = jg.apply(tmp_path, race.api)
    out = capsys.readouterr().out
    assert race.happened
    if when < JUST_BEFORE_THE_WRITE:  # a read ahead of the write sees it: nothing is written
        assert code == 1 and jira.writes == ["CC-2"]
        assert "REFUSED  CC-1" in out and not (tmp_path / "FAILED").exists()
    elif when < AFTER_THE_LAST_READ or unlisted in ("this write's", "both"):
        # the write may remove the change; and a write the history does not list never counts
        assert code == 1 and jira.writes == ["CC-1"]
        assert "written  CC-1" not in out
        assert (tmp_path / "FAILED").read_text(encoding="utf-8").startswith("CC-1:")
    else:  # a limit: a change after the last read is not seen
        assert code == 0 and jira.writes == ["CC-1", "CC-2"] and "written  CC-1" in out
    outside_the_write = when < JUST_BEFORE_THE_WRITE or when == AFTER_THE_LAST_READ
    if change in TRACES and outside_the_write:  # the other person's change is still there
        assert TRACES[change] in json.dumps(jira.tickets["CC-1"])


@pytest.mark.parametrize("mark", ["code", "strong", "em"])  # listed here, not read from MARKUP
def test_formatting_added_just_before_a_write_does_not_pass_for_part_of_it(
    tmp_path: Path, mark: str
) -> None:
    """The write removes it, and its own history entry is not listed yet. This write's entry then
    goes from a text that shows the formatting, which is not the text read before the write."""
    jira = two_tickets(tmp_path)
    race = Race(jira, mark, JUST_BEFORE_THE_WRITE, "the other change's")
    assert jg.apply(tmp_path, race.api) == 1
    assert race.happened and jira.writes == ["CC-1"]
    assert NOT_THIS_WRITE in (tmp_path / "FAILED").read_text(encoding="utf-8")


# --- a reply that cannot be used is not evidence -----------------------------------------------


def spoiled(answer: dict[str, Any], fault: str) -> dict[str, Any]:
    if fault == "unreadable":
        raise ValueError("not JSON")
    if fault == "no key":
        del answer["key"]
    elif fault == "another key":
        answer["key"] = "EXT-2"
    elif fault == "no text":
        answer["fields"]["description"] = None
    elif fault == "empty text":
        answer["fields"]["description"] = " \n"
    elif fault == "text that is an object":
        answer["fields"]["description"] = {"type": "doc", "content": []}
    else:
        answer["fields"]["description"] = "a string where the document belongs"
    return answer


BAD_REPLIES = [
    *[
        (position, fault)
        for position in (1, 4)  # the two text reads
        for fault in ("another key", "no key", "no text", "empty text", "text that is an object")
    ],
    *[
        (position, fault)
        for position in (2, 6)  # the two ticket reads
        for fault in ("another key", "no key", "not a document")
    ],
    # before the write, a reply of any of the three reads may not parse
    *[(position, "unreadable") for position in range(JUST_BEFORE_THE_WRITE)],
]


@pytest.mark.parametrize(("position", "fault"), BAD_REPLIES)
def test_a_reply_that_cannot_be_used_never_leads_to_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], position: int, fault: str
) -> None:
    jira = two_tickets(tmp_path)
    count = [0]

    def faulty(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        answer = jira.api(method, path, body)
        if about_cc1(path):
            if count[0] == position:
                answer = spoiled(answer, fault)
            count[0] += 1
        return answer

    capsys.readouterr()
    assert jg.apply(tmp_path, faulty) == 1
    out, err = capsys.readouterr()
    assert "written  CC-1" not in out
    if position < JUST_BEFORE_THE_WRITE:
        assert jira.writes == ["CC-2"] and "REFUSED  CC-1" in out
        assert not (tmp_path / "FAILED").exists()
    else:
        assert jira.writes == ["CC-1"] and (tmp_path / "FAILED").exists()
    if fault == "another key":
        assert "EXT-2" in out + err


def test_no_text_before_and_after_with_an_empty_history_entry_writes_nothing(
    tmp_path: Path,
) -> None:
    """Nothing on both sides must not read as a match."""
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def hollow(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        answer = jira.api(method, path, body)
        if path.startswith("/rest/api/2/"):
            answer["fields"]["description"] = None
        if "/changelog?" in path:
            for entry in answer["values"]:
                entry["items"] = [{"fieldId": "description"}]
        return answer

    assert jg.apply(tmp_path, hollow) == 1
    assert jira.writes == []


@pytest.mark.parametrize("where", [0, 1], ids=["listed first", "listed last"])
def test_a_second_description_change_in_the_same_history_entry_stops_the_run(
    tmp_path: Path, where: int
) -> None:
    jira = two_tickets(tmp_path)

    def doubled(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        answer = jira.api(method, path, body)
        if "/CC-1/changelog?" in path:
            for entry in answer["values"]:
                other = {"fieldId": "description", "fromString": "x", "toString": "y"}
                entry["items"].insert(where, other)
        return answer

    assert jg.apply(tmp_path, doubled) == 1
    assert jira.writes == ["CC-1"]
    assert "2 description changes" in (tmp_path / "FAILED").read_text(encoding="utf-8")


def test_a_history_entry_met_on_two_pages_counts_once(tmp_path: Path) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def overlapping(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        answer = jira.api(method, path, body)
        if "/changelog?" in path and jira.writes:
            return {"values": jira.history["CC-1"][-1:], "total": 2}
        return answer

    assert jg.apply(tmp_path, overlapping) == 0


def test_a_ticket_that_moved_after_its_write_is_not_reported_done(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)
    assert jg.apply(tmp_path, jira.api) == 0
    jira.moved["CC-1"] = "EXT-2"
    jira.writes.clear()
    capsys.readouterr()
    assert jg.apply(tmp_path, jira.api) == 1
    out = capsys.readouterr().out
    assert "REFUSED  CC-1" in out and "done     CC-1" not in out
    assert jira.writes == []


# --- a ticket the dry run cannot judge is not one without the wording --------------------------


def test_a_ticket_that_answers_under_another_key_is_not_snapshotted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    jira.moved["CC-1"] = "EXT-2"
    assert snapshot(jira, tmp_path) == 1
    assert "1 open ticket(s) read: 1 ticket(s) left to change, 1 refused" in capsys.readouterr().out
    manifest = json.loads((tmp_path / "manifest.json").read_bytes())
    assert list(manifest["tickets"]) == ["CC-2"]
    assert "EXT-2" in manifest["refused"]["CC-1"]


@pytest.mark.parametrize(
    "description",
    [
        "a carrier as a string",
        {"errorMessages": ["x"]},
        [],
        {"type": "doc"},
        {"type": "paragraph", "content": []},
        {"type": "doc", "content": "text where the blocks belong"},
    ],
    ids=[
        "a string",
        "an object that is no document",
        "a list",
        "a document with no content",
        "a node that is not a document",
        "content that is not a list",
    ],
)
def test_a_description_that_is_not_a_document_is_never_counted_as_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], description: Any
) -> None:
    jira = Jira(CC_1=ticket())
    if description == "a carrier as a string":
        description = as_text(ticket())

    def odd(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        answer = jira.api(method, path, body)
        answer["fields"]["description"] = description
        return answer

    assert jg.dry_run(tmp_path, jira.search, odd) == 1
    out = capsys.readouterr().out
    assert "REFUSED  CC-1" in out
    assert "0 open ticket(s) read: 0 ticket(s) left to change, 1 refused" in out
    assert not (tmp_path / "manifest.json").exists()


def test_an_empty_description_is_a_ticket_without_the_wording(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert snapshot(Jira(CC_1=None), tmp_path) == 0
    assert "1 open ticket(s) read: 0 ticket(s) left to change, 0 refused" in capsys.readouterr().out


def test_a_closed_ticket_is_dropped_whatever_its_description_holds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only open tickets are judged: a closed one is not refused for a description nobody edits."""
    jira = Jira(CC_1="not a document", CC_2=ticket())
    jira.closed.add("CC-1")
    assert snapshot(jira, tmp_path) == 0
    assert "1 open ticket(s) read: 1 ticket(s) left to change, 0 refused" in capsys.readouterr().out


def test_a_ticket_from_another_project_is_not_snapshotted(tmp_path: Path) -> None:
    assert snapshot(Jira(EXT_2=ticket()), tmp_path) == 1
    assert not (tmp_path / "manifest.json").exists()


@pytest.mark.parametrize("key", ["EXT-2", "CC-", "CC-two", "CC-1/../EXT-2"])
def test_a_listed_key_that_is_not_a_cc_number_is_never_asked_about(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    """The key goes into the request path, so it is judged before anything is asked with it."""
    out = tmp_path / "snapshots"
    assert jg.dry_run(out, lambda *args, **kwargs: [{"key": key}], never) == 1
    assert f"REFUSED  {key}  " in capsys.readouterr().out
    assert not out.exists()


def test_an_approved_set_that_lists_another_project_writes_nothing(tmp_path: Path) -> None:
    snapshot(Jira(CC_1=ticket()), tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_bytes())
    entry = manifest["tickets"].pop("CC-1")
    files = {}
    for name, digest in entry["files"].items():
        other = name.replace("CC-1", "EXT-2")
        (tmp_path / name).rename(tmp_path / other)
        files[other] = digest
    manifest["tickets"]["EXT-2"] = {**entry, "files": files}
    (tmp_path / "manifest.json").write_bytes(jg._dump(manifest))
    approve(tmp_path)
    assert jg.apply(tmp_path, never) == 2


# --- a limit that is kept, pinned so that a change in it is seen --------------------------------


def test_limit_another_history_entry_with_the_same_two_texts_passes_for_this_write(
    tmp_path: Path,
) -> None:
    """An entry says nothing about which request made it. While this write's own is not listed,
    another that goes between the same two texts is taken for it."""
    jira = Jira(CC_1=ticket())
    snapshot(jira, tmp_path)
    approve(tmp_path)

    def look_alike(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        answer = jira.api(method, path, body)
        if "/changelog?" in path:
            for entry in answer["values"]:
                entry["id"] = "9" + entry["id"]
                entry["author"] = {"accountId": "someone else"}
        return answer

    assert jg.apply(tmp_path, look_alike) == 0


# --- a reply that parses but is not the shape the script reads ---------------------------------

ANY_REPLY = ("a list", "a string", "nothing at all", "an empty object")
ISSUE_REPLY = (*ANY_REPLY, "fields that are not an object", "no description")
TICKET_REPLY = (
    *ISSUE_REPLY,
    "no status",
    "a status that is not an object",
    "a category not in text",
)
HISTORY_REPLY = (
    *ANY_REPLY,
    "entries that are not a list",
    "an entry that is not an object",
    "an entry without items",
    "items that are not a list",
    "an item that is not an object",
    "a description entry without an id",
    "no total",
    "a total that is not a number",
    "a page that ends before the total",
)
SHAPES = {"history": HISTORY_REPLY, "text": ISSUE_REPLY, "ticket": TICKET_REPLY}


def reshaped(answer: dict[str, Any], fault: str) -> Any:
    whole = {"a list": [answer], "a string": "x", "nothing at all": None, "an empty object": {}}
    if fault in whole:
        return whole[fault]
    if fault == "fields that are not an object":
        answer["fields"] = None
    elif fault == "no description":
        del answer["fields"]["description"]
    elif fault == "no status":
        del answer["fields"]["status"]
    elif fault == "a status that is not an object":
        answer["fields"]["status"] = None
    elif fault == "a category not in text":
        answer["fields"]["status"] = {"statusCategory": {"key": None}}
    elif fault == "entries that are not a list":
        answer["values"] = {}
    elif fault == "an entry that is not an object":
        answer["values"][-1] = "x"
    elif fault == "an entry without items":
        del answer["values"][-1]["items"]
    elif fault == "items that are not a list":
        answer["values"][-1]["items"] = {}
    elif fault == "an item that is not an object":
        answer["values"][-1]["items"] = ["x"]
    elif fault == "a description entry without an id":
        del answer["values"][-1]["id"]
    elif fault == "no total":
        del answer["total"]
    elif fault == "a total that is not a number":
        answer["total"] = "1"
    else:
        assert fault == "a page that ends before the total"
        answer["values"] = []
    return answer


@pytest.mark.parametrize(
    ("position", "fault"),
    [
        (position, fault)
        for position, kind in enumerate(REQUESTS)
        if kind != "write"  # the script reads nothing from the reply to its write
        for fault in SHAPES[kind]
    ],
)
def test_a_reply_of_the_wrong_shape_refuses_the_ticket_or_stops_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], position: int, fault: str
) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    jira.changed("CC-1")  # so that the history read before the write has an entry to spoil
    snapshot(jira, tmp_path)
    approve(tmp_path)
    count = [0]

    def faulty(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        answer = jira.api(method, path, body)
        if about_cc1(path):
            if count[0] == position:
                answer = reshaped(answer, fault)
            count[0] += 1
        return answer

    capsys.readouterr()
    assert jg.apply(tmp_path, faulty) == 1
    out = capsys.readouterr().out
    assert "written  CC-1" not in out
    if position < JUST_BEFORE_THE_WRITE:
        assert jira.writes == ["CC-2"] and "REFUSED  CC-1" in out
        assert not (tmp_path / "FAILED").exists()
    else:
        assert jira.writes == ["CC-1"]
        stopped = (tmp_path / "FAILED").read_text(encoding="utf-8")
        assert stopped.startswith("CC-1:") and "could not be confirmed" in stopped


@pytest.mark.parametrize("fault", TICKET_REPLY)
def test_a_dry_run_never_counts_a_reply_of_the_wrong_shape_as_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fault: str
) -> None:
    jira = Jira(CC_1=ticket(), CC_2=ticket())

    def faulty(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        answer = jira.api(method, path, body)
        return reshaped(answer, fault) if about_cc1(path) else answer

    assert jg.dry_run(tmp_path, jira.search, faulty) == 1
    out = capsys.readouterr().out
    assert "REFUSED  CC-1" in out
    assert "1 open ticket(s) read: 1 ticket(s) left to change, 1 refused" in out
    manifest = json.loads((tmp_path / "manifest.json").read_bytes())
    assert list(manifest["tickets"]) == ["CC-2"] and list(manifest["refused"]) == ["CC-1"]
    if fault == "no description":  # the name that was missing alone would say nothing
        assert "unusable reply (KeyError: 'description')" in manifest["refused"]["CC-1"]


# --- the stand-in answers in the shapes read from Jira -----------------------------------------


def test_the_stand_in_answers_in_the_shapes_read_from_jira() -> None:
    """As real replies read on 2026-11-25 (evidence/slice-6/cc-144/preflight-599a57d-live.txt).
    The script reads only some of these fields, so no other test would notice the rest drifting.
    Real issue and search replies also carry expand and self, which the stand-in leaves out."""
    jira = Jira(CC_1=ticket(), CC_2=ticket())
    jira.tickets["CC-2"] = None  # type: ignore[assignment]
    listed = jira.search("any", fields="status")
    assert [set(entry) for entry in listed] == [{"id", "key", "fields"}] * 2
    assert all("description" not in entry["fields"] for entry in listed)
    with pytest.raises(AssertionError):
        jira.search("any", fields="status,description")

    for path, asked in (
        ("/issue/CC-1?fields=description,status", {"description", "status"}),
        (f"{jg.TEXT_API}/issue/CC-1?fields=description", {"description"}),
    ):
        reply = jira.api("GET", path)
        assert set(reply) == {"id", "key", "fields"} and reply["key"] == "CC-1"
        assert set(reply["fields"]) == asked
        empty = jira.api("GET", path.replace("CC-1", "CC-2"))
        assert empty["fields"]["description"] is None

    jira.owner_adds_a_note("CC-1")
    jira.owner_adds_a_note("CC-1")
    path = "/issue/CC-1/changelog?startAt=0&maxResults=100"
    page = jira.api("GET", path)
    assert set(page) == {"isLast", "maxResults", "startAt", "total", "values"}
    assert [set(entry) for entry in page["values"]] == [{"author", "created", "id", "items"}] * 2
    item_fields = {"field", "fieldId", "fieldtype", "from", "fromString", "to", "toString"}
    assert all(set(item) == item_fields for entry in page["values"] for item in entry["items"])
    ids = [entry["id"] for entry in page["values"]]
    assert all(number.isdigit() for number in ids) and len(set(ids)) == 2
    kept = copy.deepcopy(page)
    page["values"][0]["items"].clear()  # a reply is the reader's own copy, as over HTTP
    assert jira.api("GET", path) == kept
