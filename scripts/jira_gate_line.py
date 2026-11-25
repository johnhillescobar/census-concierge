#!/usr/bin/env python3
"""Replace the gate wording pasted into open tickets with one line that names the gate (CC-144).

    uv run python scripts/jira_gate_line.py --dry-run [--out DIR]
    uv run python scripts/jira_gate_line.py --apply --approved DIR

--dry-run only reads Jira. For each open ticket that carries the pasted wording it writes
DIR/<KEY>.before.md and .after.md (to read), .before.json and .after.json (the description as Jira
stores it) and DIR/manifest.json. Without --out, DIR is a folder in the system's temporary
directory, so that a routine run leaves a committed set alone. Jira's search can lag behind an
edit, so every ticket the search lists is read again from its own record; one that the search does
not list yet is not read.

The owner approves a set of snapshots by writing the sha256 of its manifest.json, which --dry-run
prints, into DIR/APPROVED. --apply writes nothing without it, and new snapshots void it.

A ticket is left unchanged when its AC/TC IDs would differ, when part of the pasted wording
would remain (the opening words of a paragraph, or any sentence of SENTENCE_MIN characters or more,
as in a reworded, formatted or linked copy; a copy rewritten in all of those is not recognised),
when a line would still point at the removed contract, when
it was closed or its description changed after the snapshot, or when its after snapshot is not what
this script's rule produces. A write that Jira cannot be shown to hold, that finds the ticket closed
afterwards, or that was interrupted, stops the run and leaves DIR/FAILED. Until a person deletes
it, no --apply of DIR runs and no --dry-run touches DIR, whose before snapshot is what to restore
from. One --apply of DIR runs at a time (DIR/APPLYING).

No way was found to make a Jira write conditional on what was read, so an edit made between the
last read and the write is overwritten. It cannot be prevented here, only caught. The history holds
each description change as the text before and after it, in the form API v2 returns. A write counts
only when the history shows exactly one new description change, and that change goes from the text
read before the write to the text read after it. A count alone would take another person's edit for
this write while this write's own entry is not listed yet. What that text form leaves out cannot be
compared. Do not edit the listed tickets while --apply runs. Auth as in jira_transition.py:
ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN in .env.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import http.client
import json
import os
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import closure
import jira_fetch
import jira_transition

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(tempfile.gettempdir()) / "jira-gate-line"
TEXT_API = "/rest/api/2"  # gives a description as the text its history holds; jira_transition is v3
OPEN_JQL = "project = CC AND statusCategory != Done ORDER BY key ASC"
GATE_LINE = (
    "Gate: docs/playbooks/run-slice.md; scripts/closure.py checks the AC/TC record, and "
    "scripts/metric_compare.py judges measured runs by evals/metric_protocol.toml."
)
# sha256 of each pasted paragraph (see fingerprint). Only an exact copy is replaced: a paragraph
# someone has reworded may say something this script would delete.
PASTED = {
    "f17f300c7ae9497232b5ee50bfe1d51e8312160f929970539956d05e72374327": "metric contract",
    "7059a2f941760e6c3a4a534f7a01cb30a3655b0ca09606fbbeedc28cf9ce2c5e": "metric contract",  # 104
    "db579783c61ff22a663eb865051b8172143dc2f93e8b6bac5d392039dcaf5d54": "AC/TC clearance",
    "8d17d73f28ba0ad83ab4e78542e0861c67481c23ae9d1b7b13308ec0f42cdbf7": "AC/TC clearance",  # 104
    "2e5d766b01f39c364c01b3a059cc657a9cab652ddc602c83feaebc73956718a4": "audit gates",
}
# How a copy of the pasted wording begins. One still there after the edit, anywhere and in any
# capitals, was not recognised.
MARKERS = (
    "Metric progression and non-regression contract",
    "Mandatory AC/TC clearance before shipping",
    "Existing AC/TC, earned floors,",
)
# The first line of a ticket's own section, which points at the contract being removed.
OLD_POINTER = (
    "Existing scope (the stricter metric contract above controls prospective migration; "
    "CC-114 keeps its scoped closeout)"
)
# The opening words are one way to see a copy that is not exact; any one of its sentences is the
# other, so that an edit to a heading does not hide the paragraph under it. These are the first 16
# hex digits of the sha256 of each sentence this long in the five pasted paragraphs.
SENTENCE_MIN = 40
_SENTENCE_MARKS = """
0116cdc21dd3ac94 09c8c2327763cc60 0b7075277f4b18ca 0fac4a13917852d3 11a39e66a1083741
13c8d0db76bbbbc3 1646792f77f86086 1703836568bccf26 190ee1e393f597ef 1aa47752536203bc
1fc58fa081f629ba 240e2603fbf0c6ed 25a4c78b9e135804 2ad62e2ac353500e 2ecdc8f2c0f43092
2f276a1fc97fbe26 2f36b8c840504a48 357521a258e42b9d 396f78a54915bcb5 3b21360896ab0a06
4185276b4c087754 454b9fd675b2f2c3 4912b413bde041ee 4ff566db80bc6fae 5f6f63f258021c53
613a99f987ea1b93 65a13f0685eae009 66a63de3a4315878 68d6c2b19dbd368f 6aae8f07c9f5658e
707048741f3049a8 716ddb76d2671bd3 75d5f02f814aa5f3 79a77c0b227eeadf 7d05e27ffa00e600
7e63af1ba5512e7d 7e89bcb3bdb3b600 89555afc45d54976 8a124ea335db82df 8b0b08accdde1436
969a8d869eb1f109 96bc6a13fa4634c5 998bcf28cda4af58 9bbc4a62e2849571 9cde65bf57b58af5
9ef89f8c4294e729 aa17258f953720c1 b0c96f5bb7888605 b34bef60a476fc41 b389443b78e0f3ce
b7591137773e922b c7bc189e22308abb ca3c7d1580559e87 cce59cb9085adbed cf17248becf2b5c8
e74704a8c7ec584f e94c1e53ebfc6638 eecdbfb916a23963 f066080af93b2d7b f1a21c8038d6bc5f
f77a5df7dc8c70dd f83816199faae969 fc2493cf008973f3 fd6bb98664503de3 ff225589aab0b043
ff6ff4818d83f638
"""
SENTENCES = frozenset(_SENTENCE_MARKS.split())
NEW_POINTER = "Existing scope"
POINTER_PHRASE = "the stricter metric contract above"

Doc = dict[str, Any]
ApiFn = Callable[..., dict[str, Any]]
SearchFn = Callable[..., list[dict[str, Any]]]


def _lines(node: Any) -> list[str]:
    """The text of a node, one entry per non-empty line, runs of spaces collapsed."""
    return [line for raw in closure.adf_text(node).splitlines() if (line := " ".join(raw.split()))]


def fingerprint(node: Any) -> str:
    return hashlib.sha256("\n".join(_lines(node)).encode("utf-8")).hexdigest()


def criterion_ids(doc: Any) -> list[str]:
    """Every AC/TC id in order, repeats kept: a ticket may number two sections from AC1, and a
    set of ids would not notice one of the two disappearing."""
    return [name for line in _lines(doc) for name in closure.required_ids(line)]


def _drop_pointer(node: Doc) -> None:
    for child in node.get("content") or []:
        text = child.get("text")
        if child.get("type") == "text" and str(text).startswith(OLD_POINTER):
            child["text"] = NEW_POINTER + str(text)[len(OLD_POINTER) :]
            return


def _plain(node: Doc) -> bool:
    """A paragraph of unformatted text and line breaks, which fingerprint reads in full. A link,
    mention or mark can carry something it cannot see, so such a copy is not an exact one."""
    return node.get("type") == "paragraph" and all(
        child.get("type") in {"text", "hardBreak"} and not child.get("marks")
        for child in node.get("content") or []
    )


def edit(doc: Doc) -> tuple[Doc, list[str]]:
    """The description with every pasted paragraph replaced by one gate line, where the first one
    stood, and the names of what was replaced. A description with none comes back equal."""
    after = copy.deepcopy(doc)
    kept: list[Doc] = []
    replaced: list[str] = []
    has_line = any(_lines(node) == [GATE_LINE] for node in after.get("content") or [])
    for node in after.get("content") or []:
        name = PASTED.get(fingerprint(node)) if _plain(node) else None
        if name is None:
            kept.append(node)
            continue
        if not replaced and not has_line:
            kept.append({"type": "paragraph", "content": [{"type": "text", "text": GATE_LINE}]})
        replaced.append(name)
    if "metric contract" in replaced:  # the pointer is stale only once its target is gone
        for node in kept:
            _drop_pointer(node)
    if replaced:
        after["content"] = kept
    return after, replaced


def _mentions(doc: Doc, phrase: str) -> bool:
    """In any capitals, mid-line or across a line break."""
    return phrase.casefold() in " ".join(_lines(doc)).casefold()


def _sentences(doc: Doc) -> list[str]:
    parts = (part.strip(" .").casefold() for line in _lines(doc) for part in line.split(". "))
    return [part for part in parts if len(part) >= SENTENCE_MIN]


def _sentence_mark(sentence: str) -> str:
    return hashlib.sha256(sentence.encode("utf-8")).hexdigest()[:16]


def _pasted_sentence(doc: Doc) -> str | None:
    return next((s for s in _sentences(doc) if _sentence_mark(s) in SENTENCES), None)


def refusal(before: Doc, after: Doc) -> str | None:
    """Why this edit must not be made, or None."""
    old, new = criterion_ids(before), criterion_ids(after)
    if old != new:
        was, would = ", ".join(old) or "none", ", ".join(new) or "none"
        return f"criterion IDs would change: {was} -> {would}"
    for marker in MARKERS:
        if _mentions(after, marker):
            return f"a copy of the pasted wording is reworded, formatted or linked: {marker!r}"
    if _mentions(before, MARKERS[0]) and _mentions(after, POINTER_PHRASE):
        return "a line would still point at the removed contract (formatted, nested or moved)"
    left = _pasted_sentence(after)
    if left:
        return f"a sentence of the pasted wording would remain, in an inexact copy: {left[:60]!r}"
    return None


@dataclass(frozen=True)
class Change:
    key: str
    before: Doc
    after: Doc
    replaced: list[str]
    refused: str | None


def changes(issues: list[dict[str, Any]]) -> list[Change]:
    """One per ticket that carries the wording, exactly or reworded."""
    found: list[Change] = []
    for issue in issues:
        before = (issue.get("fields") or {}).get("description")
        if not isinstance(before, dict):
            continue
        after, replaced = edit(before)
        why = refusal(before, after)
        carries = any(_mentions(before, marker) for marker in MARKERS) or bool(
            _pasted_sentence(before)
        )
        if replaced or carries:
            found.append(Change(str(issue.get("key")), before, after, replaced, why))
    return found


def _dump(value: Any) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _readable(doc: Doc) -> bytes:
    """One blank line between blocks, so the owner can read before against after. Trailing
    spaces and blank lines go: a commit hook would trim them and void the approved hashes."""
    text = "\n\n".join(closure.adf_text(node).strip() for node in doc.get("content") or [])
    return ("\n".join(line.rstrip() for line in text.strip().split("\n")) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _snapshot_names(key: str) -> set[str]:
    return {f"{key}.{side}" for side in ("before.json", "after.json", "before.md", "after.md")}


def _listed(raw: bytes) -> dict[str, Any]:
    """A manifest in which every ticket is an issue key and names its own four snapshot files and
    nothing else, so that no name in it can reach another file. ValueError otherwise."""
    listed = json.loads(raw)
    for key, entry in listed["tickets"].items():
        project, _, number = key.partition("-")
        if not (project.isalpha() and number.isdigit()):
            raise ValueError(f"the manifest lists {key!r}, which is not an issue key")
        if set(entry["files"]) != _snapshot_names(key):
            raise ValueError(f"the manifest names files for {key} that are not its four snapshots")
    return listed


def _discard(out: Path) -> None:
    """Remove an earlier snapshot set, and only its own files: it no longer describes Jira. All of
    the manifest is checked before the first file goes."""
    manifest = out / "manifest.json"
    if manifest.is_file():
        for key in _listed(manifest.read_bytes())["tickets"]:
            for name in _snapshot_names(key):
                (out / name).unlink(missing_ok=True)
        manifest.unlink()


def _read_each(listed: list[dict[str, Any]], api: ApiFn) -> list[dict[str, Any]]:
    """The listed tickets that are open, each as its own record reads now: what the search
    returns can be from before an edit made seconds or minutes ago."""
    now: list[dict[str, Any]] = []
    for issue in listed:
        description, closed = _issue(str(issue["key"]), api)
        if not closed:
            now.append({"key": issue["key"], "fields": {"description": description}})
    return now


def dry_run(out: Path, search: SearchFn, api: ApiFn) -> int:
    listed = search(OPEN_JQL, fields="status")
    if not listed:  # an empty answer is a fault to look at, not a project with nothing to change
        print("Jira returned no open ticket at all; nothing changed", file=sys.stderr)
        return 1
    issues = _read_each(listed, api)
    found = changes(issues)
    ready = [c for c in found if not c.refused]
    for change in found:
        if change.refused:
            print(f"REFUSED  {change.key}  {change.refused}")
        else:
            print(f"change   {change.key}  replaces: {', '.join(change.replaced)}")
    print(
        f"{len(issues)} open ticket(s) read: {len(ready)} ticket(s) left to change, "
        f"{len(found) - len(ready)} refused"
    )
    failed = 1 if len(found) > len(ready) else 0
    if (out / "FAILED").exists():
        print(
            f"{out} holds the snapshots to restore a failed write from and is not touched; "
            "use --out for new ones",
            file=sys.stderr,
        )
        return 1
    if (out / "APPROVED").exists():
        if not ready:
            return failed
        print(
            f"{out} holds approved snapshots and is not overwritten; use --out for new ones",
            file=sys.stderr,
        )
        return 1
    try:
        _discard(out)  # even with nothing to write: a stale set must not be left to approve
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"nothing removed or written in {out}: {exc}", file=sys.stderr)
        return 1
    if not ready:
        return failed
    out.mkdir(parents=True, exist_ok=True)
    tickets: dict[str, Any] = {}
    for change in ready:
        files = {
            f"{change.key}.before.json": _dump(change.before),
            f"{change.key}.after.json": _dump(change.after),
            f"{change.key}.before.md": _readable(change.before),
            f"{change.key}.after.md": _readable(change.after),
        }
        for name, data in files.items():
            (out / name).write_bytes(data)
        tickets[change.key] = {
            "ids": criterion_ids(change.before),
            "replaced": change.replaced,
            "files": {name: _sha(data) for name, data in files.items()},
        }
    skipped = {c.key: c.refused for c in found if c.refused}
    manifest = _dump({"gate_line": GATE_LINE, "refused": skipped, "tickets": tickets})
    (out / "manifest.json").write_bytes(manifest)
    print(f"snapshots in {out}")
    print(f"to approve, write this into {out / 'APPROVED'}: {_sha(manifest)}")
    return failed


def approved_snapshots(folder: Path) -> tuple[dict[str, tuple[Doc, Doc]], dict[str, str]]:
    """From an approved directory: key -> (before, after), and the tickets the dry run refused.
    ValueError when it is not one."""
    manifest = folder / "manifest.json"
    approval = folder / "APPROVED"
    if not manifest.is_file():
        raise ValueError(f"{folder} has no manifest.json; run --dry-run first")
    if not approval.is_file():
        raise ValueError(f"{folder} is not approved: it has no APPROVED file")
    raw = manifest.read_bytes()
    # utf-8-sig: Windows PowerShell writes a byte order mark
    if approval.read_text(encoding="utf-8-sig").strip() != _sha(raw):  # the hash and no more
        raise ValueError(f"{approval} does not name these snapshots (manifest {_sha(raw)})")
    listed = _listed(raw)
    docs: dict[str, tuple[Doc, Doc]] = {}
    for key, entry in listed["tickets"].items():
        for name, want in entry["files"].items():
            path = folder / name
            if not path.is_file() or _sha(path.read_bytes()) != want:
                raise ValueError(f"{path} is not the file that was approved")
        pair = [
            json.loads((folder / f"{key}.{side}.json").read_bytes()) for side in ("before", "after")
        ]
        docs[key] = (pair[0], pair[1])
    return docs, listed["refused"]


def _stored_form(node: Any) -> Any:
    """A document without what Jira may add of its own when it stores one: a localId, and the
    attrs that then holds nothing. Everything else, links and structure included, must match."""
    if isinstance(node, list):
        return [_stored_form(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: _stored_form(value) for key, value in node.items()}
    if "attrs" in out:
        out["attrs"] = {k: v for k, v in out["attrs"].items() if k != "localId"}
        if not out["attrs"]:
            del out["attrs"]
    return out


def _issue(key: str, api: ApiFn) -> tuple[Doc, bool]:
    """The description as Jira stores it now, and whether the ticket is closed."""
    fields = api("GET", f"/issue/{key}?fields=description,status")["fields"]
    return fields["description"], fields["status"]["statusCategory"]["key"] == "done"


def _text(key: str, api: ApiFn) -> Any:
    """The description as the history writes it."""
    return api("GET", f"{TEXT_API}/issue/{key}?fields=description")["fields"]["description"]


def _description_changes(key: str, api: ApiFn) -> dict[str, tuple[Any, Any]]:
    """The entries in the ticket's history that changed its description, by id: the text each one
    went from and to."""
    found: dict[str, tuple[Any, Any]] = {}
    start = 0
    while True:
        page = api("GET", f"/issue/{key}/changelog?startAt={start}&maxResults=100")
        for history in page["values"]:
            for item in history["items"]:
                if item.get("fieldId") == "description":
                    found[str(history["id"])] = (item.get("fromString"), item.get("toString"))
        start += len(page["values"])
        if not page["values"] or start >= page["total"]:
            return found


def _write(key: str, after: Doc, earlier: set[str], was: Any, api: ApiFn) -> str | None:
    """Write one description, read it back, and read the history: the only description change
    since `earlier` must go from the text `was` to the text the ticket reads as now. Why the write
    cannot be shown to hold, or None."""
    try:
        api("PUT", f"/issue/{key}", {"fields": {"description": after}})
        now = _text(key, api)
        stored, closed = _issue(key, api)
        history = _description_changes(key, api)
        new = [history[entry] for entry in history.keys() - earlier]
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        http.client.HTTPException,
        SystemExit,  # jira_transition._api exits on an HTTP error
    ) as exc:
        return f"the write could not be confirmed ({type(exc).__name__}: {exc})"
    check = "Read the ticket's History in Jira, which keeps each version, before restoring anything"
    if len(new) > 1:
        return (
            f"the history shows {len(new)} description changes where one was written: another "
            f"edit arrived during the write and may be overwritten. {check}"
        )
    if _stored_form(stored) != _stored_form(after):
        return "Jira does not hold the approved description"
    if not new:
        return "the history does not show this write, so an overlapping edit cannot be ruled out"
    if new[0] != (was, now):
        return (
            "the one new description change in the history is not shown to be this write: it does "
            "not go from the text read before the write to the text read after it, so another "
            f"edit may be overwritten. {check}"
        )
    if closed:
        return "the ticket reads as closed after the write: a closed ticket may have been changed"
    return None


def apply(folder: Path, api: ApiFn) -> int:
    try:
        snapshots, skipped = approved_snapshots(folder)
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        print(f"nothing written: {exc}", file=sys.stderr)
        return 2
    running = folder / "APPLYING"
    try:  # created only if absent, in one step: of two runs started together, one gets it
        os.close(os.open(running, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        print(
            f"nothing written: {running} exists, so another --apply of this folder is running "
            "or was killed. If none is running, delete the file",
            file=sys.stderr,
        )
        return 2
    try:
        return _apply_approved(folder, snapshots, skipped, api)
    finally:
        running.unlink(missing_ok=True)


def _apply_approved(
    folder: Path, snapshots: dict[str, tuple[Doc, Doc]], skipped: dict[str, str], api: ApiFn
) -> int:
    """What apply does while it holds DIR/APPLYING."""
    stop = folder / "FAILED"
    if stop.exists():
        print(
            f"nothing written: {stop} records a write that did not hold. Read that ticket and "
            "its History in Jira against its before snapshot, restore it if needed, then delete "
            "the file",
            file=sys.stderr,
        )
        return 2
    for key, why in skipped.items():
        print(f"REFUSED  {key}  at the dry run: {why}")
    written, refused = 0, len(skipped)
    for key, (before, after) in snapshots.items():
        # history, then text, then the description: an edit before the last of these is refused
        # below, and one after it cannot be part of what the history entry is compared with
        earlier = set(_description_changes(key, api))
        was = _text(key, api)
        live, closed = _issue(key, api)
        if _stored_form(live) == _stored_form(after):
            print(f"done     {key}  already reads as approved")
            continue
        why = refusal(before, after)
        if not why and closed:
            why = "the ticket was closed after the snapshot"
        if not why and live != before:
            why = "the description changed after the snapshot; run --dry-run again"
        if not why and edit(before)[0] != after:
            why = "the after snapshot is not what this script's rule produces"
        if why:
            print(f"REFUSED  {key}  {why}")
            refused += 1
            continue
        restore = (
            f"check the ticket and its History in Jira against {folder / f'{key}.before.json'}, "
            "and put back only what this write took out"
        )
        # there before the write, so that an interrupted run stays stopped too
        stop.write_text(
            f"{key}: a write was started and not confirmed; {restore}\n", encoding="utf-8"
        )
        problem = _write(key, after, earlier, was, api)
        if problem:
            # stop at once, and stay stopped: what went wrong here would go wrong on the next
            message = f"{key}: {problem}; {restore}"
            stop.write_text(message + "\n", encoding="utf-8")
            print(f"FAILED   {message}", file=sys.stderr)
            return 1
        stop.unlink()
        written += 1
        print(f"written  {key}  IDs unchanged: {', '.join(criterion_ids(after)) or 'none'}")
    print(f"{written} written, {refused} refused")
    return 1 if refused else 0


def _jira(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """jira_transition's client, plus the one read it has no path to."""
    if not path.startswith(TEXT_API):
        return jira_transition._api(method, path, body)
    request = urllib.request.Request(
        f"https://{jira_transition._site()}{path}",
        headers=jira_transition._auth_header(),
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="snapshot; never changes Jira")
    mode.add_argument("--apply", action="store_true", help="write the approved snapshots")
    parser.add_argument(
        "--out", type=Path, default=OUT, help="where --dry-run writes (default: %(default)s)"
    )
    parser.add_argument("--approved", type=Path, help="the approved snapshot directory")
    args = parser.parse_args(argv)
    if args.apply and not args.approved:
        parser.error("--apply needs --approved <snapshot dir>; nothing written")
    jira_transition._load_env()
    if args.apply:
        return apply(args.approved, _jira)
    return dry_run(args.out, jira_fetch._search, jira_transition._api)


if __name__ == "__main__":
    sys.exit(main())
