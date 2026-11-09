#!/usr/bin/env python3
"""AC/TC closure manifest check (CC-133).

    python scripts/closure.py check evidence/closure/CC-133.toml [--pre-merge] [--head SHA]
                                    [--require AC1,TC1] [--ref origin/main]

A manifest is evidence/closure/<KEY>.toml: one [[row]] per AC and TC, an optional [[amendment]]
per row the owner removed from scope, and one [post_merge] block. This checks that the record is
whole: every required ID has a row, every row is PASS (or AMENDED by a dated owner amendment), its
evidence exists and still hashes the same, it names the head it was tested at, a new test names its
mutation check, evidence is not stale against the files the row says it covers, and, to close, the
post-merge E2E ran on a commit that is on the base ref. Reviewers still verify the substance of a
row. This cannot stop a human from closing a ticket in Jira directly.

    [[row]]  id status command expected observed evidence tested_head affects
             new_tests mutation reviewer
    [[amendment]]  id date owner reason destination
    [post_merge]   e2e main_head
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tomllib
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATUSES = {"PASS", "FAIL", "NOT RUN", "UNKNOWN", "AMENDED"}
ROW_FIELDS = ("command", "expected", "observed", "tested_head", "reviewer")
GitFn = Callable[..., subprocess.CompletedProcess[str]]


def adf_text(node: object) -> str:
    """Plain text of a Jira description (Atlassian Document Format), one line per break."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return str(node.get("text") or "")
    if node.get("type") == "hardBreak":
        return "\n"
    inner = "".join(adf_text(child) for child in node.get("content") or [])
    return inner + "\n" if node.get("type") in {"paragraph", "heading", "listItem"} else inner


def required_ids(text: str) -> list[str]:
    """AC1., TC3. ... at the start of a line, in order, once each. Exact identifiers only."""
    found: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        head = stripped.split(".", 1)[0].split(" ", 1)[0]
        listed = head[:2] in {"AC", "TC"} and head[2:].isdigit() and stripped.startswith(head + ".")
        if listed and head not in found:
            found.append(head)
    return found


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def _evidence_problems(item: Any, where: str, root: Path) -> list[str]:
    spec = {"path": item} if isinstance(item, str) else item
    if not isinstance(spec, dict) or not spec.get("path"):
        return [f"{where}: evidence entry needs a path"]
    path = (root / str(spec["path"])).resolve()
    if not path.is_relative_to(root.resolve()):
        return [f"{where}: evidence {spec['path']} is outside the repository"]
    if not path.is_file():
        return [f"{where}: evidence {spec['path']} does not exist"]
    want = spec.get("sha256")
    if want and hashlib.sha256(path.read_bytes()).hexdigest() != want:
        return [f"{where}: evidence {spec['path']} changed since it was recorded"]
    return []


def _row_problems(
    row: dict[str, Any], root: Path, head: str, amended: set[str], readiness: bool, git: GitFn
) -> list[str]:
    name = str(row.get("id") or "?")
    status = str(row.get("status") or "")
    if status not in STATUSES:
        return [f"{name}: status {status!r} is not one of {sorted(STATUSES)}"]
    if status == "AMENDED":
        return [] if name in amended else [f"{name}: AMENDED without an [[amendment]] for it"]
    if status != "PASS":
        return [f"{name}: {status} blocks closure"] if readiness else []
    out = [f"{name}: missing {field}" for field in ROW_FIELDS if not row.get(field)]
    evidence = row.get("evidence") or []
    out += [] if evidence else [f"{name}: no evidence"]
    for item in evidence:
        out += _evidence_problems(item, name, root)
    if row.get("new_tests"):
        mutation = row.get("mutation")
        out += (
            _evidence_problems(mutation, name, root)
            if mutation
            else [f"{name}: new tests with no mutation check"]
        )
    tested = str(row.get("tested_head") or "")
    if not readiness or not tested:
        return out
    affects = [str(p) for p in row.get("affects") or []]
    if not affects:
        return [*out, f"{name}: no `affects` paths, so staleness cannot be checked"]
    diff = git(root, "diff", "--name-only", tested, head, "--", *affects)
    if diff.returncode:  # git cannot diff against something that is not a commit
        return [
            *out,
            f"{name}: tested_head {tested} is not a commit that git can diff against {head}",
        ]
    changed = diff.stdout.split()
    if changed:
        out.append(f"{name}: stale, {len(changed)} covered file(s) changed since {tested[:7]}")
    return out


def problems(
    manifest: dict[str, Any],
    root: Path = ROOT,
    *,
    required: list[str] | None = None,
    head: str = "HEAD",
    readiness: bool = True,
    done: bool = True,
    base: str = "origin/main",
    git: GitFn = _git,
) -> list[str]:
    """Every reason this manifest cannot back a closure. `readiness=False` checks only that the
    record is well formed, which is all a work-in-progress manifest in the tree must be."""
    out: list[str] = []
    rows = [r for r in manifest.get("row") or [] if isinstance(r, dict)]
    ids = [str(r.get("id") or "") for r in rows]
    out += [f"{i}: listed more than once" for i in sorted({i for i in ids if ids.count(i) > 1})]
    amendments = [a for a in manifest.get("amendment") or [] if isinstance(a, dict)]
    for amendment in amendments:
        missing = [
            k for k in ("id", "date", "owner", "reason", "destination") if not amendment.get(k)
        ]
        try:
            date.fromisoformat(str(amendment.get("date")))
        except ValueError:
            missing.append("date (ISO)")
        out += (
            [f"amendment {amendment.get('id', '?')}: missing {', '.join(missing)}"]
            if missing
            else []
        )
    amended = {str(a.get("id")) for a in amendments}
    for row in rows:
        out += _row_problems(row, root, head, amended, readiness, git)
    if not readiness:
        return out
    out += [f"{i}: absent from the manifest" for i in (required or []) if i not in ids]
    block = manifest.get("post_merge") or {}
    if done:
        e2e, main_head = block.get("e2e"), str(block.get("main_head") or "")
        if not e2e or not main_head:
            out.append("post_merge: the post-merge E2E (e2e, main_head) is not recorded")
        else:
            out += _evidence_problems(e2e, "post_merge", root)
            if git(root, "merge-base", "--is-ancestor", main_head, base).returncode:
                out.append(f"post_merge: {main_head[:7]} is not on {base}")
    return out


def load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def check_file(path: Path, **kwargs: Any) -> list[str]:
    try:
        return problems(load(path), **kwargs)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"{path.name}: unreadable ({exc})"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("manifest", type=Path)
    check.add_argument("--head", default="HEAD")
    check.add_argument("--ref", default="origin/main")
    check.add_argument("--require", default="")
    check.add_argument("--pre-merge", action="store_true", help="skip the post-merge E2E")
    args = parser.parse_args()
    found = check_file(
        args.manifest,
        required=[i for i in args.require.split(",") if i],
        head=args.head,
        done=not args.pre_merge,
        base=args.ref,
    )
    for line in found:
        print(f"  BLOCKED  {line}")
    print("CLOSURE OK" if not found else f"CLOSURE BLOCKED: {len(found)} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
