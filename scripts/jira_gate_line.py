#!/usr/bin/env python3
"""Replace the gate wording pasted into open tickets with one line that names the gate (CC-144).

    uv run python scripts/jira_gate_line.py --dry-run [--out DIR]
    uv run python scripts/jira_gate_line.py --apply --approved DIR

--dry-run only reads Jira. For each open ticket that carries the pasted wording it writes
DIR/<KEY>.before.md and .after.md (to read), .before.json and .after.json (the description as Jira
stores it) and DIR/manifest.json.

The owner approves a set of snapshots by writing the sha256 of its manifest.json, which --dry-run
prints, into DIR/APPROVED. --apply writes nothing without it, and new snapshots void it.

A ticket is left unchanged when its AC/TC IDs would differ, when a copy of the wording is not
exact (reworded, formatted or linked), when a line would still point at the removed contract, when
it was closed or its description changed after the snapshot, or when its after snapshot is not what
this script's rule produces. A write that Jira cannot be shown to hold, or that was interrupted,
stops the run and leaves DIR/FAILED. Until a person deletes it, no --apply of DIR runs and no
--dry-run touches DIR, whose before snapshot is what to restore from. Auth as in
jira_transition.py: ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN in .env.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import http.client
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import closure
import jira_fetch
import jira_transition

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evidence" / "slice-6" / "cc-144" / "snapshots"
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
        carries = any(_mentions(before, marker) for marker in MARKERS)
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


def _discard(out: Path) -> None:
    """Remove an earlier snapshot set, and only its own files: it no longer describes Jira."""
    manifest = out / "manifest.json"
    if manifest.is_file():
        for entry in json.loads(manifest.read_bytes())["tickets"].values():
            for name in entry["files"]:
                (out / name).unlink(missing_ok=True)
        manifest.unlink()


def dry_run(out: Path, search: SearchFn) -> int:
    issues = search(OPEN_JQL, fields="description")
    if not issues:  # an empty answer is a fault to look at, not a project with nothing to change
        print("Jira returned no open ticket at all; nothing changed", file=sys.stderr)
        return 1
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
    _discard(out)  # even with nothing to write: a stale set must not be left to approve
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
    listed = json.loads(raw)
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


def _write(key: str, before: Doc, after: Doc, api: ApiFn) -> str | None:
    """Write one description and read it back. Why it cannot be shown to hold, or None."""
    try:
        api("PUT", f"/issue/{key}", {"fields": {"description": after}})
        stored, _ = _issue(key, api)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        http.client.HTTPException,
        SystemExit,  # jira_transition._api exits on an HTTP error
    ) as exc:
        return f"the write could not be confirmed ({type(exc).__name__}: {exc})"
    if _stored_form(stored) != _stored_form(after):
        return "Jira does not hold the approved description"
    return None


def apply(folder: Path, api: ApiFn) -> int:
    stop = folder / "FAILED"
    if stop.exists():
        print(
            f"nothing written: {stop} records a write that did not hold. Compare that ticket "
            "with its before snapshot, restore it if needed, then delete the file",
            file=sys.stderr,
        )
        return 2
    try:
        snapshots, skipped = approved_snapshots(folder)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"nothing written: {exc}", file=sys.stderr)
        return 2
    for key, why in skipped.items():
        print(f"REFUSED  {key}  at the dry run: {why}")
    written, refused = 0, len(skipped)
    for key, (before, after) in snapshots.items():
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
            f"compare it with {folder / f'{key}.before.json'} and restore it from there if it "
            "differs"
        )
        # there before the write, so that an interrupted run stays stopped too
        stop.write_text(
            f"{key}: a write was started and not confirmed; {restore}\n", encoding="utf-8"
        )
        problem = _write(key, before, after, api)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="snapshot; never changes Jira")
    mode.add_argument("--apply", action="store_true", help="write the approved snapshots")
    parser.add_argument("--out", type=Path, default=OUT, help="where --dry-run writes")
    parser.add_argument("--approved", type=Path, help="the approved snapshot directory")
    args = parser.parse_args(argv)
    if args.apply and not args.approved:
        parser.error("--apply needs --approved <snapshot dir>; nothing written")
    jira_transition._load_env()
    if args.apply:
        return apply(args.approved, jira_transition._api)
    return dry_run(args.out, jira_fetch._search)


if __name__ == "__main__":
    sys.exit(main())
