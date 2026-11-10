#!/usr/bin/env python3
"""Update Jira issue status and comments via the REST API.

Host-agnostic: works the same in Claude Code and Cursor when
ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN are in .env. MCP is optional.

    python scripts/jira_transition.py CC-21 --status
    python scripts/jira_transition.py CC-21 --transitions
    python scripts/jira_transition.py CC-21 --comment "Gate met; see evidence/latest.json"
    python scripts/jira_transition.py CC-21 --done --comment-file evidence/latest.json
    python scripts/jira_transition.py CC-21 --transition Done

Moving an issue to Done first runs the closure gate (scripts/closure.py): if the description
carries AC/TC identifiers, evidence/closure/<KEY>.toml must back every one of them. A refused
closure adds no comment and makes no transition. Exits non-zero on API, auth or gate failure.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import closure
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE = "johnhillescobar.atlassian.net"


def _load_env() -> None:
    load_dotenv(ROOT / ".env")


def _site() -> str:
    return os.environ.get("ATLASSIAN_SITE", DEFAULT_SITE).removeprefix("https://").rstrip("/")


def _auth_header() -> dict[str, str]:
    email = os.environ.get("ATLASSIAN_EMAIL", "")
    token = os.environ.get("ATLASSIAN_API_TOKEN", "")
    if not email or not token:
        print(
            "Missing ATLASSIAN_EMAIL or ATLASSIAN_API_TOKEN in .env\n"
            "Create an API token at https://id.atlassian.com/manage-profile/security/api-tokens",
            file=sys.stderr,
        )
        sys.exit(1)
    encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Accept": "application/json"}


def _api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"https://{_site()}/rest/api/3{path}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={**_auth_header(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        print(f"Jira HTTP {exc.code} {method} {path}", file=sys.stderr)
        print(exc.read().decode()[:1000], file=sys.stderr)
        sys.exit(1)


def _issue(key: str, fields: str = "summary,status,issuetype") -> dict:
    return _api("GET", f"/issue/{key}?fields={fields}")


def _transitions(key: str) -> list[dict]:
    payload = _api("GET", f"/issue/{key}/transitions")
    return payload.get("transitions", [])


def _comment_body(text: str) -> dict:
    return {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        }
    }


def _add_comment(key: str, text: str) -> None:
    _api("POST", f"/issue/{key}/comment", _comment_body(text))


def _transition(key: str, target: str) -> None:
    matches = [
        t for t in _transitions(key) if t.get("to", {}).get("name", "").lower() == target.lower()
    ]
    if not matches:
        names = sorted({t.get("to", {}).get("name", "?") for t in _transitions(key)})
        print(f"No transition to {target!r}. Available: {', '.join(names)}", file=sys.stderr)
        sys.exit(1)
    _api("POST", f"/issue/{key}/transitions", {"transition": {"id": matches[0]["id"]}})


def _is_done(key: str, target: str | None) -> bool:
    """Moving to any status Jira files under Done (Closed, Resolved...) is a closure, not just
    the one named Done."""
    wanted = str(target or "").strip().lower()
    for move in _transitions(key):
        to = move.get("to", {})
        if to.get("name", "").lower() == wanted:
            return to.get("statusCategory", {}).get("key") == "done"
    return wanted == "done"


def _closure_gate(key: str) -> None:
    """Refuse Done unless the AC/TC manifest is whole. Both Done paths come through here."""
    fields = _issue(key, "description,issuetype")["fields"]
    needed = closure.required_ids(closure.adf_text(fields.get("description")))
    manifest = ROOT / "evidence" / "closure" / f"{key}.toml"
    kind = str((fields.get("issuetype") or {}).get("name") or "").lower()
    if not needed and not manifest.is_file():
        if kind in {"story", "bug"}:  # these carry AC/TC; none found is a refusal, not a pass
            print(
                f"{key} cannot be closed: a {kind} with no AC/TC ids and no closure manifest",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"{key}: {kind or 'issue'} with no AC/TC identifiers; no closure manifest required")
        return
    found = (
        closure.check_file(manifest, required=needed, root=ROOT)
        if manifest.is_file()
        else [f"no closure manifest at {manifest.relative_to(ROOT).as_posix()}"]
    )
    if found:
        print(f"{key} cannot be closed:", file=sys.stderr)
        for line in found:
            print(f"  BLOCKED  {line}", file=sys.stderr)
        sys.exit(1)
    print(f"{key}: closure manifest covers {', '.join(needed) or 'its own rows'}")


def _read_comment(args: argparse.Namespace) -> str | None:
    if args.comment:
        return args.comment
    if args.comment_file:
        path = args.comment_file if args.comment_file.is_absolute() else ROOT / args.comment_file
        return path.read_text(encoding="utf-8")
    return None


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue", help="Jira issue key, e.g. CC-21")
    parser.add_argument("--status", action="store_true", help="print summary and status")
    parser.add_argument("--transitions", action="store_true", help="list workflow transitions")
    parser.add_argument("--comment", help="add a comment (plain text)")
    parser.add_argument("--comment-file", type=Path, help="add comment from file")
    parser.add_argument("--transition", metavar="STATUS", help='move issue, e.g. "Done"')
    parser.add_argument(
        "--done",
        action="store_true",
        help="shorthand for --transition Done (optional comment via --comment/--comment-file)",
    )
    args = parser.parse_args()
    key = args.issue.upper()
    project, _, number = key.partition("-")
    if not (project.isalpha() and number.isdigit()):
        parser.error(f"{args.issue!r} is not an issue key like CC-21")

    if args.status or not any(
        [args.transitions, args.comment, args.comment_file, args.transition, args.done]
    ):
        issue = _issue(key)
        fields = issue["fields"]
        print(f"{key}  {fields['status']['name']}  {fields['issuetype']['name']}")
        print(fields["summary"])

    if args.transitions:
        print(f"\nTransitions for {key}:")
        for t in _transitions(key):
            to_name = t.get("to", {}).get("name", "?")
            print(f"  {t.get('id', '?'):>3}  {t.get('name', '?')} -> {to_name}")

    target = "Done" if args.done else args.transition
    if _is_done(key, target):
        _closure_gate(key)

    text = _read_comment(args)
    if text:
        _add_comment(key, text)
        print(f"Comment added to {key}")

    if target:
        before = _issue(key, "status")["fields"]["status"]["name"]
        _transition(key, target)
        after = _issue(key, "status")["fields"]["status"]["name"]
        print(f"{key}  {before} -> {after}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
