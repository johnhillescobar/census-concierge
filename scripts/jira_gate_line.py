#!/usr/bin/env python3
"""Replace the gate wording pasted into open tickets with one line that names the gate (CC-144).

    uv run python scripts/jira_gate_line.py --dry-run [--out DIR]
    uv run python scripts/jira_gate_line.py --apply --approved DIR

--dry-run only reads Jira. For each open ticket that carries the pasted wording it writes
DIR/<KEY>.before.md and .after.md (to read), .before.json and .after.json (the description as Jira
stores it) and DIR/manifest.json.

The owner approves a set of snapshots by writing the sha256 of its manifest.json, which --dry-run
prints, into DIR/APPROVED. --apply writes nothing without it, and new snapshots void it.

A ticket is left unchanged when its AC/TC IDs would differ, when a copy of the wording was
reworded, when its description changed after the snapshot, or when its after snapshot is not what
this script's rule produces. Auth as in jira_transition.py: ATLASSIAN_EMAIL and
ATLASSIAN_API_TOKEN in .env.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
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
# How a copy of the pasted wording begins. One still there after the edit was not recognised.
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


def edit(doc: Doc) -> tuple[Doc, list[str]]:
    """The description with every pasted paragraph replaced by one gate line, where the first one
    stood, and the names of what was replaced. A description with none comes back equal."""
    after = copy.deepcopy(doc)
    kept: list[Doc] = []
    replaced: list[str] = []
    has_line = any(_lines(node) == [GATE_LINE] for node in after.get("content") or [])
    for node in after.get("content") or []:
        name = PASTED.get(fingerprint(node))
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


def refusal(before: Doc, after: Doc) -> str | None:
    """Why this edit must not be made, or None."""
    old, new = criterion_ids(before), criterion_ids(after)
    if old != new:
        was, would = ", ".join(old) or "none", ", ".join(new) or "none"
        return f"criterion IDs would change: {was} -> {would}"
    for line in _lines(after):
        if line.startswith(MARKERS):
            return f"a copy of the pasted wording is not the text this script knows: {line[:60]!r}"
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
        carries = any(line.startswith(MARKERS) for line in _lines(before))
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


def dry_run(out: Path, search: SearchFn) -> int:
    found = changes(search(OPEN_JQL, fields="description"))
    ready = [c for c in found if not c.refused]
    for change in found:
        if change.refused:
            print(f"REFUSED  {change.key}  {change.refused}")
        else:
            print(f"change   {change.key}  replaces: {', '.join(change.replaced)}")
    print(f"{len(ready)} ticket(s) left to change, {len(found) - len(ready)} refused")
    failed = 1 if len(found) > len(ready) else 0
    if not ready:
        return failed
    if (out / "APPROVED").exists():
        print(
            f"{out} holds approved snapshots and is not overwritten; use --out for new ones",
            file=sys.stderr,
        )
        return 1
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").is_file():  # a ticket that dropped out must not look reviewable
        for entry in json.loads((out / "manifest.json").read_bytes())["tickets"].values():
            for name in entry["files"]:
                (out / name).unlink(missing_ok=True)
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
    manifest = _dump({"gate_line": GATE_LINE, "tickets": tickets})
    (out / "manifest.json").write_bytes(manifest)
    print(f"snapshots in {out}")
    print(f"to approve, write this into {out / 'APPROVED'}: {_sha(manifest)}")
    return failed


def approved_snapshots(folder: Path) -> dict[str, tuple[Doc, Doc]]:
    """key -> (before, after) from an approved directory. ValueError when it is not one."""
    manifest = folder / "manifest.json"
    approval = folder / "APPROVED"
    if not manifest.is_file():
        raise ValueError(f"{folder} has no manifest.json; run --dry-run first")
    if not approval.is_file():
        raise ValueError(f"{folder} is not approved: it has no APPROVED file")
    raw = manifest.read_bytes()
    # utf-8-sig: Windows PowerShell writes a byte order mark
    if _sha(raw) not in approval.read_text(encoding="utf-8-sig").split():
        raise ValueError(f"{approval} does not name these snapshots (manifest {_sha(raw)})")
    docs: dict[str, tuple[Doc, Doc]] = {}
    for key, entry in json.loads(raw)["tickets"].items():
        for name, want in entry["files"].items():
            path = folder / name
            if not path.is_file() or _sha(path.read_bytes()) != want:
                raise ValueError(f"{path} is not the file that was approved")
        pair = [
            json.loads((folder / f"{key}.{side}.json").read_bytes()) for side in ("before", "after")
        ]
        docs[key] = (pair[0], pair[1])
    return docs


def _description(key: str, api: ApiFn) -> Doc:
    return api("GET", f"/issue/{key}?fields=description")["fields"]["description"]


def apply(folder: Path, api: ApiFn) -> int:
    try:
        snapshots = approved_snapshots(folder)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"nothing written: {exc}", file=sys.stderr)
        return 2
    written = refused = 0
    for key, (before, after) in snapshots.items():
        live = _description(key, api)
        if _lines(live) == _lines(after):
            print(f"done     {key}  already reads as approved")
            continue
        why = refusal(before, after)
        if not why and live != before:
            why = "the description changed after the snapshot; run --dry-run again"
        if not why and edit(before)[0] != after:
            why = "the after snapshot is not what this script's rule produces"
        if why:
            print(f"REFUSED  {key}  {why}")
            refused += 1
            continue
        api("PUT", f"/issue/{key}", {"fields": {"description": after}})
        stored = _description(key, api)
        if criterion_ids(stored) != criterion_ids(before) or _lines(stored) != _lines(after):
            # stop at once: whatever went wrong would go wrong on the next ticket too
            print(
                f"FAILED   {key}  Jira does not hold the approved text; restore it from "
                f"{folder / f'{key}.before.json'}",
                file=sys.stderr,
            )
            return 1
        written += 1
        print(f"written  {key}  IDs unchanged: {', '.join(criterion_ids(stored)) or 'none'}")
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
