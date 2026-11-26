#!/usr/bin/env python3
"""Print the brief for one phase of a ticket. See docs/playbooks/run-slice.md.

    uv run python scripts/brief.py <phase> CC-N [--base origin/main] [--after-merge]

    phase   preflight | implement | gate1 | gate2 | final

Every brief opens with the two status commands. Before it prints, the live Jira criteria are
compared with the ones approved at pre-flight (`approved_ids` and `approved_sha256` in
evidence/closure/CC-N.toml). A difference stops the phase unless an [[amendment]] row names the
new fingerprint as `criteria_sha256`. It prints a prompt; it launches nothing. The phase's
evidence is written by the agent that runs it, never by the caller.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import check_budgets
import closure
import jira_fetch

ROOT = Path(__file__).resolve().parent.parent
PHASES = ("preflight", "implement", "gate1", "gate2", "final")
COLD = "gate2-cold"  # .claude/agents/gate2-cold.md; .claude/hooks/ctx.py holds the name too


def status_commands(key: str, *, landed: str | None = None) -> list[str]:
    """The ticket, then its closure record. An open ticket's record is judged on this checkout,
    before the merge. A closed ticket stays closed: its record is judged as it stood at `landed`,
    the main commit that last changed it, so later work elsewhere cannot make it read as broken."""
    check = f"uv run python scripts/closure.py check evidence/closure/{key}.toml"
    return [
        f"uv run python scripts/jira_fetch.py issue {key} --md",
        f"{check} --head {landed}" if landed else f"{check} --pre-merge",
    ]


def is_closed(fields: dict[str, Any]) -> bool:
    """Jira files the status under Done (Done, Won't Do, ...): no phase starts on it."""
    category = ((fields.get("status") or {}).get("statusCategory") or {}).get("key")
    return category == "done"


def landed_at(key: str, base: str) -> str | None:
    """The commit on `base` that last changed the ticket's closure file, or None."""
    done = subprocess.run(
        ["git", "log", "-1", "--format=%H", base, "--", f"evidence/closure/{key}.toml"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    found = done.stdout.strip()
    return found if done.returncode == 0 and closure._is_commit_hash(found) else None


def closed_status(key: str, status: str, landed: str | None) -> str:
    first, second = status_commands(key, landed=landed or "<none>")
    lines = [
        f"{key} is {status} in Jira and stays closed: no phase may start on it. Its status comes",
        "from these two commands, never from chat or memory. Run the second from a checkout of",
        "main (`git worktree add --detach <dir> origin/main`):",
        f"  {first}",
        f"  {second}"
        if landed
        else "  (no closure file on main: Jira's close comment is the record)",
        "From them state: the approved criteria and decisions, the commit tested, and what, if",
        "anything, is left for the owner. A regression in what it shipped is caught by its tests",
        "in `make check`; the change that caused it fixes it.",
    ]
    return "\n".join(lines) + "\n"


def compare(manifest: dict[str, Any] | None, description: object, phase: str) -> list[str]:
    """Why the live criteria may not be worked on: they differ from the approved ones with no
    owner amendment for the new text, or (after pre-flight) nothing was approved. `description`
    is the Jira document (or plain text, line by line)."""
    ids = closure.required_ids(closure.adf_text(description))
    sha = closure.criteria_fingerprint(description)
    approved = (manifest or {}).get("approved_ids")
    approved_sha = (manifest or {}).get("approved_sha256")
    if not isinstance(approved, list) or not approved_sha:
        if phase == "preflight":
            return []
        return ["no criteria were approved at pre-flight: run the preflight brief first"]
    if ids == approved and sha == approved_sha:
        return []
    amendments = [a for a in (manifest or {}).get("amendment") or [] if isinstance(a, dict)]
    whole = [a for a in amendments if not closure.amendment_problems(a)]  # dated, owned, reasoned
    if any(a.get("criteria_sha256") == sha for a in whole):
        return []
    out = [f"criterion {i} is in Jira but was not approved" for i in ids if i not in approved]
    out += [f"criterion {i} was approved but is gone from Jira" for i in approved if i not in ids]
    if not out and ids != approved:
        out.append(f"the criteria are in a different order: {ids} (approved {approved})")
    if not out:
        was = str(approved_sha)[:12]
        out.append(f"the criteria text changed with the same ids ({sha[:12]}, approved {was})")
    out.append(
        "no [[amendment]] row has criteria_sha256 = " + sha + "; only the owner amends a ticket"
    )
    return out


def changed_files(base: str) -> list[str] | None:
    """The paths this branch changes against `base`, or None when git cannot say. Renames are
    split into a deletion and an addition, so a rule file moved out of the rule set is seen."""
    done = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return [p for p in done.stdout.split("\0") if p] if done.returncode == 0 else None


def evidence_dir(key: str) -> str:
    found = sorted(p for p in (ROOT / "evidence").glob(f"*/{key.lower()}") if p.is_dir())
    return found[0].relative_to(ROOT).as_posix() if len(found) == 1 else f"evidence/{key.lower()}"


def brief(
    phase: str,
    key: str,
    changed: list[str] | None,
    folder: str,
    *,
    after_merge: bool = False,
    approve: tuple[list[str], str] | None = None,
) -> str:
    """The phase's prompt for a fresh agent. `changed` is the branch's diff (None: unknown)."""
    first, second = status_commands(key)
    name = (
        "e2e-post" if phase == "final" and after_merge else "e2e-pre" if phase == "final" else phase
    )
    out_file, cold = f"{folder}/{name}.txt", f"{folder}/gate2-cold.txt"
    lines = [
        f"{key} {name} brief. Status comes from these two commands, never from chat or memory:",
        f"  {first}",
        f"  {second}",
        "From them state: the approved criteria and decisions, the commit tested, which evidence",
        "is stale or missing, and the next permitted step. Then read AGENTS.md and",
        "docs/playbooks/run-slice.md, and the catalogs matching the touched paths.",
        "",
    ]
    if phase == "preflight":
        lines += [
            "Run every technical claim in the ticket against the thing it names before any code.",
            f"Facts and their commands go to {folder}/preflight.txt; decisions go to a Jira",
            "comment, each tagged owner or default. Ask one question batch, each with a default.",
            f"Record in evidence/closure/{key}.toml the approved criteria and one NOT RUN row per",
            "criterion, each naming the command that proves it.",
        ]
        if approve:
            ids = ", ".join(f'"{i}"' for i in approve[0])  # TOML, ready to paste
            lines += [f"  approved_ids = [{ids}]", f'  approved_sha256 = "{approve[1]}"']
    elif phase == "implement":
        lines += [
            "Implement in this interactive session only, against the approved criteria. End at",
            "one commit. Gate 1 and Gate 2 go to fresh agents with their own briefs.",
        ]
    elif phase == "gate1":
        lines += [
            "Hand to a fresh general-purpose subagent, not fork (Cursor: a fresh Task; Codex:",
            "fork_context false). Tests for the adversarial matrix; mutation-check every new test",
            "one behaviour at a time, GOOD/BAD labels above the real failure counts.",
            f"Capture raw output to {out_file}. Report back only the path and a one-line verdict.",
        ]
    elif phase == "gate2":
        lines += [
            f"First the {COLD} agent for the bug pass: give it only the repo path, the review",
            f"base and head, and {cold}. Then a general-purpose agent described as",
            "'Gate 2 invariants pass' runs docs/playbooks/review-pr.md; it names",
            f"{cold} and does not repeat that pass. Other hosts: a fresh session, code only first.",
            f"Capture raw output to {out_file}. Report the path, a verdict and the findings.",
        ]
        rules = (
            None if changed is None else [p for p in changed if check_budgets.is_prescriptive(p)]
        )
        if rules is None or rules:
            touched = "git could not list the change" if rules is None else ", ".join(rules)
            lines += [
                f"This change touches a prescriptive rule file ({touched}). Read every file in",
                "check_budgets.DOC_PATTERNS and list each contradiction between them, or 'none'.",
            ]
    else:
        lines += [
            "Run make eval and make demo (repeat 3 is in the recipe) in an isolated worktree;",
            "record HEAD at start and end. Never Read the transcript.",
        ]
        if after_merge:
            lines += [
                "Against merged main. Then metric_compare.py compare evidence/latest.json --record",
                "and the closure check above without --pre-merge; a non-zero exit blocks Done.",
            ]
        lines += [
            f"Redirect every command's output to {out_file} (no tee). Report only the path, a",
            "verdict and the gated keys plus demo.misses from evidence/latest.json.",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("phase", choices=PHASES)
    parser.add_argument("key")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--after-merge", action="store_true", help="final: the post-merge run")
    args = parser.parse_args()
    if args.after_merge and args.phase != "final":
        parser.error("--after-merge belongs to the final phase only")
    key = args.key.upper()
    path = ROOT / "evidence" / "closure" / f"{key}.toml"
    try:
        manifest = closure.load(path) if path.is_file() else None
    except (OSError, ValueError) as exc:  # tomllib.TOMLDecodeError is a ValueError
        print(f"  STOP  {path.name} cannot be read: {exc}", file=sys.stderr)
        return 1
    jira_fetch.load_env()
    fields = jira_fetch._issue(key).get("fields") or {}
    description = fields.get("description")
    if is_closed(fields):
        status = str((fields.get("status") or {}).get("name") or "closed")
        print(closed_status(key, status, landed_at(key, args.base)), end="")
        return 1
    ids = closure.required_ids(closure.adf_text(description))
    sha = closure.criteria_fingerprint(description)
    if problems := compare(manifest, description, args.phase):
        for line in problems:
            print(f"  STOP  {line}", file=sys.stderr)
        print(f"{key}: the criteria do not match the approved ones; this phase may not start.")
        if not (manifest or {}).get("approved_sha256"):  # a record from before CC-145
            record = f"evidence/closure/{key}.toml"
            print(f"Once the owner approves the live criteria, record in {record}:")
            print("  approved_ids = [" + ", ".join(f'"{i}"' for i in ids) + "]")
            print(f'  approved_sha256 = "{sha}"')
        return 1
    approve = (ids, sha) if args.phase == "preflight" else None
    changed = changed_files(args.base) if args.phase == "gate2" else []
    text = brief(
        args.phase, key, changed, evidence_dir(key), after_merge=args.after_merge, approve=approve
    )
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
