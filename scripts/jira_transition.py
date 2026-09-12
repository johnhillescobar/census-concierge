#!/usr/bin/env python3
"""Update Jira issue status and comments via the REST API.

Host-agnostic: works the same in Claude Code and Cursor when
ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN are in .env. MCP is optional.

    python scripts/jira_transition.py CC-21 --status
    python scripts/jira_transition.py CC-21 --transitions
    python scripts/jira_transition.py CC-21 --comment "Gate met; see evidence/latest.json"
    python scripts/jira_transition.py CC-21 --done --comment-file evidence/latest.json
    python scripts/jira_transition.py CC-21 --transition Done

Exits non-zero on API or auth failure.
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

    text = _read_comment(args)
    if text:
        _add_comment(key, text)
        print(f"Comment added to {key}")

    target = "Done" if args.done else args.transition
    if target:
        before = _issue(key, "status")["fields"]["status"]["name"]
        _transition(key, target)
        after = _issue(key, "status")["fields"]["status"]["name"]
        print(f"{key}  {before} -> {after}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
