#!/usr/bin/env python3
"""AC/TC closure manifest check (CC-133).

    python scripts/closure.py check evidence/closure/CC-133.toml [--pre-merge] [--head SHA]
                                    [--require AC1,TC1] [--ref origin/main]
    python scripts/closure.py ticket feat/cc-145-one-source      prints CC-145, or exits 1

A manifest is evidence/closure/<KEY>.toml: one [[row]] per AC and TC, an optional [[amendment]]
per row the owner removed from scope, and one [post_merge] block. This checks that the record is
whole: every required ID has a row, every row is PASS (or AMENDED by a dated owner amendment), its
evidence exists and still hashes the same, it names the head it was tested at, a new test names its
mutation check, evidence is not stale against the files the row says it covers, and, to close, the
post-merge E2E ran on a commit that is on the base ref. Reviewers still verify the substance of a
row. This cannot stop a human from closing a ticket in Jira directly.

    required = ["AC1", "TC1"]      the ids this manifest claims to cover; each needs a row
    approved_ids, approved_sha256  the criteria approved at pre-flight (scripts/brief.py); each
                                   approved id needs a row too
    [[row]]  id status command expected observed evidence tested_head affects
             new_tests mutation reviewer
             (every row but an AMENDED one names its command)
             (a PASS row pins every evidence entry and its mutation check: {path, sha256})
    [[amendment]]  id date owner reason destination [criteria_sha256]
             (with criteria_sha256 it re-approves the criteria text; it removes no row from scope)
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
ROW_FIELDS = ("expected", "observed", "tested_head", "reviewer")  # what a PASS row also needs
GitFn = Callable[..., subprocess.CompletedProcess[str]]
HEX = set("0123456789abcdef")
# A merged change that touches one of these can move what `make eval` and `make demo` measure, so
# it owes a post-merge run: the product, the evals, and the run harness (the scripts those recipes
# execute, the recipes themselves, the dependency pins, and the web build `make demo` makes and
# run_demo.py checks is the one served). A trailing slash is a directory.
E2E_PATHS = (
    "api/src/",
    "evals/",
    "web/",
    "Makefile",
    "pyproject.toml",
    "api/pyproject.toml",
    "uv.lock",
    "scripts/run_demo.py",
    "scripts/run_grid.py",
    "scripts/label_grid_ambiguity.py",
    "scripts/eval_retrieval.py",
    "scripts/score_synthetic.py",
    "scripts/verify_golden_places.py",
    "scripts/metric_compare.py",
    "scripts/budget_log.py",  # metric_compare, and so run_demo, imports it
    "scripts/build_index.py",  # builds the index both recipes read
    "data/",  # the synthetic questions score_synthetic.py scores
)
LINE_NODES = {
    "paragraph",
    "heading",
    "listItem",
    "taskItem",
    "decisionItem",
    "codeBlock",
    "blockquote",
}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_commit_hash(value: Any) -> bool:
    """A hash, never a ref or an option: `HEAD`, `main` and `--stat` would all satisfy git."""
    return isinstance(value, str) and 7 <= len(value) <= 40 and set(value.lower()) <= HEX


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
    return inner + "\n" if node.get("type") in LINE_NODES else inner


def _digits(text: str) -> str:
    return text[: len(text) - len(text.lstrip("0123456789"))]


def required_ids(text: str) -> list[str]:
    """AC1, TC3 ... at the start of a line, in order, once each. Bullets, bold and a space before
    the number are tolerated ("- **AC 1.**"); the identifier is followed by `.`, `:`, `)`, a dash
    or the end of the line, so "AC1 is the first" is not one. "AC 6.2" is its own id (AC6.2), and
    "AC6-12" (a dash straight onto a number) requires every id from AC6 to AC12."""
    found: list[str] = []
    for line in text.replace("\u00a0", " ").splitlines():
        rest = line.strip().lstrip(" \t-*+#>_`|(\u2022\u2013\u2014").upper()
        if rest[:2] not in {"AC", "TC"}:
            continue
        digits = rest[2:].lstrip(" ")
        number = _digits(digits)
        tail = digits[len(number) :]
        parts = [number]
        while tail[:1] == "." and _digits(tail[1:]):  # AC6.2, AC6.2.1
            parts.append(_digits(tail[1:]))
            tail = tail[1 + len(parts[-1]) :]
        last = tail[:1] in {"-", "\u2013", "\u2014"} and _digits(tail[1:])
        after = tail.lstrip("*_` ")[:1]
        if not number or any(len(p) > 4 for p in parts):
            continue
        if last and len(parts) == 1 and 0 < int(last) - int(number) <= 50:
            names = [f"{rest[:2]}{n}" for n in range(int(number), int(last) + 1)]
        elif after in {"", ".", ":", ")", "-", "\u2013", "\u2014"}:
            names = [rest[:2] + ".".join(str(int(p)) for p in parts)]
        else:
            continue
        found += [name for name in names if name not in found]
    return found


ITEM_NODES = {"paragraph", "listItem", "taskItem", "decisionItem", "codeBlock", "blockquote"}


def _first_line(text: str) -> str:
    return (text.strip().splitlines() or [""])[0]


def criteria_blocks(description: object) -> list[str]:
    """Each criterion's whole text, whitespace collapsed, in order. A criterion is the block whose
    first line carries its id: a paragraph with its hard breaks, a list item with its sub-items,
    a table row whose first cell is the id, or a heading and everything under it up to the next
    heading or criterion. A paragraph after a paragraph criterion is not part of it, so editing
    a decision paragraph does not move the fingerprint. A plain string is read line by line."""
    if isinstance(description, str):
        return [" ".join(line.split()) for line in description.splitlines() if required_ids(line)]
    out: list[list[str]] = []

    def walk(nodes: list[Any]) -> None:
        section: list[str] | None = None  # the criterion an id heading opened
        for node in nodes:
            if not isinstance(node, dict):
                continue
            kind, text = node.get("type"), adf_text(node)
            if kind == "heading":
                section = [text] if required_ids(_first_line(text)) else None
                out.extend([section] if section else [])
                continue
            cells = node.get("content") or [] if kind == "tableRow" else []
            starts = adf_text(cells[0]) if cells else text
            if (kind in ITEM_NODES or kind == "tableRow") and required_ids(_first_line(starts)):
                section = None
                out.append([" | ".join(adf_text(c) for c in cells) if cells else text])
            elif section is not None:
                section.append(text)
            else:  # a container, or an item with a criterion further in
                walk(node.get("content") or [])

    walk(description.get("content") or [] if isinstance(description, dict) else [])
    return [" ".join(" ".join(parts).split()) for parts in out]


def criteria_fingerprint(description: object) -> str:
    """sha256 of the criteria's whole text (`criteria_blocks`): rewording any part of a criterion
    changes it, editing a paragraph that is not one does not."""
    return hashlib.sha256("\n".join(criteria_blocks(description)).encode("utf-8")).hexdigest()


BRANCH_TYPES = ("feat", "fix", "docs", "chore", "test", "refactor", "perf", "ci", "build", "style")
BRANCH_TYPES += ("revert", "evidence")  # conventional commits, plus this repo's evidence PRs


def branch_ticket(branch: str) -> tuple[str | None, str]:
    """The Jira key a branch names, or None and why not. A branch is `<type>/...`, its type a
    conventional-commit type, and carries one ticket key anywhere after it: feat/cc-145-x,
    fix/x-CC-145, evidence/cc145-post all name CC-145. Words are runs of letters and digits."""
    kind, _, rest = branch.partition("/")
    if kind.lower() not in BRANCH_TYPES or not rest:
        types = ", ".join(BRANCH_TYPES)
        return None, f"branch {branch!r} does not start with a conventional type ({types})/"
    words = "".join(ch.lower() if ch.isalnum() else " " for ch in rest).split()
    pairs = zip(words, [*words[1:], ""], strict=True)
    keys = {f"CC-{int(n)}" for w, n in pairs if w == "cc" and n.isdigit()}
    keys |= {f"CC-{int(w[2:])}" for w in words if w[:2] == "cc" and w[2:].isdigit()}
    if len(keys) != 1:
        found = ", ".join(sorted(keys)) or "none"
        return None, f"branch {branch!r} must name exactly one ticket (found {found})"
    return keys.pop(), ""


def amendment_problems(amendment: dict[str, Any]) -> list[str]:
    """The fields an owner amendment lacks: id, ISO date, owner, reason, destination."""
    missing = [k for k in ("id", "date", "owner", "reason", "destination") if not amendment.get(k)]
    try:
        date.fromisoformat(str(amendment.get("date")))
    except ValueError:
        missing.append("date (ISO)")
    return missing


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def _evidence_problems(item: Any, where: str, root: Path, *, pinned: bool = False) -> list[str]:
    spec = {"path": item} if isinstance(item, str) else item
    if not isinstance(spec, dict) or not spec.get("path"):
        return [f"{where}: evidence entry needs a path"]
    path = (root / str(spec["path"])).resolve()
    if not path.is_relative_to(root.resolve()):
        return [f"{where}: evidence {spec['path']} is outside the repository"]
    if not path.is_file():
        return [f"{where}: evidence {spec['path']} does not exist"]
    want = spec.get("sha256")
    if pinned and not want:  # a PASS must not rest on a file anyone can still rewrite
        return [f"{where}: evidence {spec['path']} must be pinned with a sha256"]
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
    # every criterion names the command that proves it, whether or not it has been run
    unnamed = [] if _text(row.get("command")) else [f"{name}: missing command"]
    if status != "PASS":
        return unnamed + ([f"{name}: {status} blocks closure"] if readiness else [])
    out = unnamed + [f"{name}: missing {key}" for key in ROW_FIELDS if not _text(row.get(key))]
    evidence = row.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        out.append(f"{name}: evidence must be a non-empty list")
    for item in evidence if isinstance(evidence, list) else []:
        out += _evidence_problems(item, name, root, pinned=True)
    if row.get("new_tests"):
        mutation = row.get("mutation")
        out += (
            _evidence_problems(mutation, name, root, pinned=True)
            if mutation
            else [f"{name}: new tests with no mutation check"]
        )
    tested = row.get("tested_head")
    if _text(tested) and not _is_commit_hash(tested):
        return [*out, f"{name}: tested_head must be a commit hash, not {tested!r}"]
    if not readiness or not _is_commit_hash(tested):
        return out
    affects = row.get("affects")
    if (
        not isinstance(affects, list)
        or not affects
        or not all(_text(p) and not p.startswith((":", "-")) for p in affects)
    ):
        return [*out, f"{name}: `affects` must be a non-empty list of plain paths"]
    missing = [p for p in affects if not (root / p).exists()]
    if missing:
        return [*out, f"{name}: `affects` names paths that do not exist: {missing}"]
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


def _landed_on(root: Path, commit: str, git: GitFn) -> str | None:
    """What a landed commit is diffed against, or None if git cannot say. A merge commit: the base
    it merged into. A commit made straight onto the base (a fast-forward, an owner's own commit):
    the last merge before it, so that a series which landed together is read whole. Its last
    commit alone would hide the product change in its first."""
    parents = git(root, "rev-list", "--parents", "-n", "1", commit)
    words = parents.stdout.split()
    if parents.returncode or not words:
        return None
    if len(words) > 2:
        return words[1]
    merge = git(root, "rev-list", "--first-parent", "--min-parents=2", "-n", "1", commit)
    return merge.stdout.strip() or None


def merged_e2e_paths(
    root: Path, manifest: str | None, tested: list[str], base: str, git: GitFn
) -> list[str] | None:
    """The product, eval and run-harness files this ticket's merges changed on `base`, or None when
    git cannot say. It is read from the diff, never declared: the merges are the first-parent
    commits of `base` that changed the manifest and the ones that brought in a row's tested head,
    each diffed against the `base` it landed on. A pull request that did neither is not seen, so a
    reviewer still checks that the rows cover what the ticket changed."""
    landed: set[str] = set()
    if manifest:
        log = git(root, "log", "--first-parent", "--format=%H", base, "--", manifest)
        if log.returncode:
            return None
        landed.update(log.stdout.split())
    for given in tested:
        # the full hash: a short or upper-case spelling must not read as a different commit
        full = git(root, "rev-parse", "--verify", "--quiet", f"{given}^{{commit}}")
        commit = full.stdout.strip()
        if full.returncode or not commit:
            return None
        after = git(root, "rev-list", "--first-parent", "--ancestry-path", f"{commit}..{base}")
        if after.returncode:
            return None
        # the oldest first-parent commit of base that contains `commit`: the merge that brought it
        # in, or `commit` itself when it was committed straight onto base
        merge = (after.stdout.split() or [commit])[-1]
        first = git(root, "rev-parse", "--verify", "--quiet", f"{merge}^1")
        landed.add(commit if first.stdout.strip() == commit or merge == commit else merge)
    changed: set[str] = set()
    for commit in sorted(landed):
        since = _landed_on(root, commit, git)
        if since is None:
            return None
        # --no-renames: a file moved out of api/src is a file that left api/src
        diff = git(root, "diff", "--name-only", "--no-renames", since, commit)
        if diff.returncode:
            return None
        changed.update(diff.stdout.splitlines())
    return sorted(
        path
        for path in changed
        if any(path.startswith(e) if e.endswith("/") else path == e for e in E2E_PATHS)
    )


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
    path: str | None = None,
) -> list[str]:
    """Every reason this manifest cannot back a closure. `readiness=False` checks only that the
    record is well formed, which is all a work-in-progress manifest in the tree must be. `path` is
    the manifest's own path in the repository, which names the merges that carried the ticket."""
    out: list[str] = []
    rows = [r for r in manifest.get("row") or [] if isinstance(r, dict)]
    ids = [str(r.get("id") or "") for r in rows]
    out += [f"{i}: listed more than once" for i in sorted({i for i in ids if ids.count(i) > 1})]
    amendments = [a for a in manifest.get("amendment") or [] if isinstance(a, dict)]
    for amendment in amendments:
        missing = amendment_problems(amendment)
        out += (
            [f"amendment {amendment.get('id', '?')}: missing {', '.join(missing)}"]
            if missing
            else []
        )
    # An amendment that re-approves the criteria text (criteria_sha256) adds or rewords scope; it
    # does not remove its id, so it cannot stand in for that row's evidence.
    amended = {str(a.get("id")) for a in amendments if not a.get("criteria_sha256")}
    for row in rows:
        out += _row_problems(row, root, head, amended, readiness, git)
    if not readiness:
        return out
    if not rows:
        out.append("the manifest has no rows; it cannot back a closure")
    declared = manifest.get("required")
    if not isinstance(declared, list) or not declared or not all(_text(i) for i in declared):
        out.append("the manifest must declare `required`, the AC/TC ids it covers")
        declared = []
    approved = manifest.get("approved_ids")  # approved at pre-flight (scripts/brief.py)
    approved = [str(i) for i in approved] if isinstance(approved, list) else []
    wanted = list(dict.fromkeys([*declared, *approved, *(required or [])]))
    out += [f"{i}: absent from the manifest" for i in wanted if i not in ids]
    block = manifest.get("post_merge") or {}
    if done:
        e2e, main_head = block.get("e2e"), block.get("main_head")
        passed = sorted({str(r.get("tested_head")) for r in rows if r.get("status") == "PASS"})
        if not e2e and not main_head:
            # no run is recorded: it is owed unless nothing the ticket merged can move a metric
            unmerged = [
                t for t in passed if git(root, "merge-base", "--is-ancestor", t, base).returncode
            ]
            touched = None if unmerged else merged_e2e_paths(root, path, passed, base, git)
            out += [f"post_merge: the work tested at {t[:7]} is not on {base}" for t in unmerged]
            if touched is None and not unmerged:
                out.append("post_merge: git cannot show what was merged; the E2E is required")
            elif touched:
                out.append(
                    "post_merge: the post-merge E2E (e2e, main_head) is not recorded, and the "
                    f"merged change touches {touched[0]}"
                    + (f" and {len(touched) - 1} more" if len(touched) > 1 else "")
                )
        elif not e2e or not main_head:
            out.append("post_merge: the post-merge E2E (e2e, main_head) is not recorded")
        elif not _is_commit_hash(main_head):
            out.append(f"post_merge: main_head must be a commit hash, not {main_head!r}")
        else:
            if not (isinstance(e2e, dict) and e2e.get("sha256")):
                out.append("post_merge: the E2E evidence must be pinned with a sha256")
            out += _evidence_problems(e2e, "post_merge", root)
            if git(root, "merge-base", "--is-ancestor", main_head, base).returncode:
                out.append(f"post_merge: {main_head[:7]} is not on {base}")
            for tested in passed:
                if git(root, "merge-base", "--is-ancestor", tested, main_head).returncode:
                    out.append(
                        f"post_merge: {main_head[:7]} does not contain the work tested at "
                        f"{tested[:7]}"
                    )
    return out


def load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def check_file(path: Path, **kwargs: Any) -> list[str]:
    try:
        root = Path(kwargs.get("root", ROOT)).resolve()
        full = path.resolve()
        inside = full.relative_to(root).as_posix() if full.is_relative_to(root) else None
        return problems(load(path), path=inside, **kwargs)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return [f"{path.name}: malformed manifest ({type(exc).__name__}: {exc})"]  # fails closed


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
    ticket = sub.add_parser("ticket", help="print the ticket key a branch names; exit 1 if none")
    ticket.add_argument("branch")
    args = parser.parse_args()
    if args.command == "ticket":
        key, why = branch_ticket(args.branch)
        print(key or why, file=sys.stdout if key else sys.stderr)
        return 0 if key else 1
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
