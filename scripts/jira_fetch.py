#!/usr/bin/env python3
"""Read-only Jira fetch helpers (issue + epic children) via the REST API.

This script is intentionally read-only: no transitions, no edits.

Examples:

  uv run python scripts/jira_fetch.py issue CC-75
  uv run python scripts/jira_fetch.py issue CC-75 --md
  uv run python scripts/jira_fetch.py epic CC-12 --list

Auth:
  Requires ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN in `.env`.
  Optional: ATLASSIAN_SITE (defaults to johnhillescobar.atlassian.net)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import closure  # the ADF helpers the closure gate reads criteria with
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE = "johnhillescobar.atlassian.net"


def env_file(root: Path = ROOT) -> Path | None:
    """This checkout's `.env`, or else the main checkout's: git does not copy an ignored file
    into a new worktree, and a worktree's git common dir is the main checkout's `.git`."""
    if (root / ".env").is_file():
        return root / ".env"
    found = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    main = Path(found.stdout.strip()).parent / ".env" if found.returncode == 0 else None
    return main if main and found.stdout.strip() and main.is_file() else None


def load_env(root: Path = ROOT) -> None:
    path = env_file(root)
    if path:
        load_dotenv(path)


def _site() -> str:
    return os.environ.get("ATLASSIAN_SITE", DEFAULT_SITE).removeprefix("https://").rstrip("/")


def _auth_header() -> dict[str, str]:
    email = os.environ.get("ATLASSIAN_EMAIL", "")
    token = os.environ.get("ATLASSIAN_API_TOKEN", "")
    if not email or not token:
        print("Missing ATLASSIAN_EMAIL or ATLASSIAN_API_TOKEN in .env", file=sys.stderr)
        sys.exit(2)
    encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Accept": "application/json"}


def _api(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"https://{_site()}/rest/api/3{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={**_auth_header(), "Content-Type": "application/json"} if body else _auth_header(),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        print(f"Jira HTTP {exc.code} {method} {path}", file=sys.stderr)
        print(exc.read().decode(errors="replace")[:1000], file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError) as exc:  # URLError, a timeout mid-read, a body that is not JSON
        print(f"Jira unreachable {method} {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def _issue(key: str) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "fields": "*all",
            "expand": "names,schema",
        }
    )
    return _api("GET", f"/issue/{key}?{params}")


def _search(jql: str, *, fields: str = "summary,status,issuetype,parent") -> list[dict[str, Any]]:
    # Jira Cloud removed GET /search; POST /search/jql paginates with nextPageToken.
    field_list = [part.strip() for part in fields.split(",") if part.strip()]
    found: list[dict[str, Any]] = []
    next_page: str | None = None
    seen_tokens: set[str] = set()
    while True:
        body: dict[str, Any] = {"jql": jql, "maxResults": 100, "fields": field_list}
        if next_page:
            body["nextPageToken"] = next_page
        payload = _api("POST", "/search/jql", body)
        page = payload.get("issues")
        if isinstance(page, list):
            found.extend(issue for issue in page if isinstance(issue, dict))
        token = payload.get("nextPageToken")
        if not isinstance(token, str) or not token or token in seen_tokens:
            break
        seen_tokens.add(token)
        next_page = token
    return found


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        key = value.get("key")
        if isinstance(key, str):
            return key
        name = value.get("name")
        if isinstance(name, str):
            return name
        return ""
    return ""


@dataclass(frozen=True)
class IssueSummary:
    key: str
    issue_type: str
    status: str
    summary: str
    epic: str


def _field_name_maps(issue: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    names = issue.get("names")
    schema = issue.get("schema")
    return (
        names if isinstance(names, dict) else {},
        schema if isinstance(schema, dict) else {},
    )


def _find_epic_key(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    if not isinstance(fields, dict):
        return ""

    parent = fields.get("parent")
    if isinstance(parent, dict):
        parent_key = parent.get("key")
        if isinstance(parent_key, str) and parent_key:
            return parent_key

    names, schema = _field_name_maps(issue)
    for field_id, field_name in names.items():
        if not isinstance(field_id, str) or not isinstance(field_name, str):
            continue
        if field_name.strip().casefold() != "epic link":
            continue
        value = fields.get(field_id)
        epic_key = _as_text(value)
        if epic_key:
            return epic_key

    for field_id, info in schema.items():
        if not isinstance(field_id, str) or not isinstance(info, dict):
            continue
        custom = field_id.startswith("customfield_")
        if not custom:
            continue
        value = fields.get(field_id)
        if isinstance(value, dict) and isinstance(value.get("key"), str):
            return str(value["key"])
        if isinstance(value, str) and value.upper().startswith("CC-"):
            return value
    return ""


def _summarize(issue: dict[str, Any]) -> IssueSummary:
    key = str(issue.get("key") or "")
    fields = issue.get("fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    issuetype = fields.get("issuetype") or {}
    status = fields.get("status") or {}
    return IssueSummary(
        key=key,
        issue_type=str(getattr(issuetype, "get", lambda *_: "")("name") or ""),
        status=str(getattr(status, "get", lambda *_: "")("name") or ""),
        summary=str(fields.get("summary") or ""),
        epic=_find_epic_key(issue),
    )


def _comments(key: str, last: int) -> list[dict[str, Any]]:
    """The ticket's newest `last` comments, oldest first."""
    if last <= 0:
        return []
    query = urllib.parse.urlencode({"orderBy": "-created", "maxResults": last})
    page = _api("GET", f"/issue/{key}/comment?{query}").get("comments")
    return [c for c in page if isinstance(c, dict)][::-1] if isinstance(page, list) else []


def _body_markdown(raw: Any) -> str:
    if isinstance(raw, dict) and raw.get("type") == "doc":
        return _adf_to_markdown(raw).rstrip()
    return raw.strip() if isinstance(raw, str) else ""


def issue_markdown(issue: dict[str, Any], comments: list[dict[str, Any]]) -> str:
    """The ticket as markdown: header, description, then its last comments. Built whole before
    anything is printed, so a failed fetch prints no part of a ticket."""
    summary = _summarize(issue)
    out = [f"## {summary.key} — {summary.summary}", ""]
    out += [f"- Type: {summary.issue_type}", f"- Status: {summary.status}"]
    out += [f"- Epic: {summary.epic or '—'}", ""]
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    description = _body_markdown(fields.get("description"))
    out += ["### Description", "", description, ""] if description else []
    if comments:
        out += [f"### Last {len(comments)} comment(s), oldest first", ""]
    for comment in comments:
        author = (comment.get("author") or {}).get("displayName") or "?"
        out += [f"#### {comment.get('created', '?')} — {author}", ""]
        out += [_body_markdown(comment.get("body")) or "(empty)", ""]
    return "\n".join(out).rstrip() + "\n"


def _adf_to_markdown(doc: dict[str, Any]) -> str:
    chunks: list[str] = []

    def render_node(node: Any, *, indent: str = "") -> None:
        if not isinstance(node, dict):
            return
        node_type = node.get("type")
        if node_type == "heading":
            level = int((node.get("attrs") or {}).get("level") or 2)
            level = max(2, min(level, 4))
            text = _render_inline(node.get("content") or [])
            if text.strip():
                chunks.append(f"{'#' * level} {text.strip()}")
                chunks.append("")
            return
        if node_type == "paragraph":
            text = _render_inline(node.get("content") or [])
            if text.strip():
                chunks.append(f"{indent}{text.strip()}")
                chunks.append("")
            return
        if node_type == "bulletList":
            for item in node.get("content") or []:
                render_node(item, indent=indent)
            chunks.append("")
            return
        if node_type == "orderedList":
            i = 1
            for item in node.get("content") or []:
                render_node(item, indent=f"{indent}{i}. ")
                i += 1
            chunks.append("")
            return
        if node_type == "listItem":
            items = node.get("content") or []
            if not isinstance(items, list):
                return
            first = True
            for child in items:
                if first:
                    if indent.endswith(". "):
                        render_node(child, indent=indent)
                    else:
                        render_node(child, indent=f"{indent}- ")
                    first = False
                else:
                    render_node(child, indent=f"{indent}  ")
            return
        if node_type in ("blockCard", "embedCard"):  # a link shown as a card, not inline
            link = closure.attr_text(node)
            chunks.extend([f"{indent}{link}", ""] if link else [])
            return
        if node_type == "codeBlock":
            chunks.extend(["```", _render_inline(node.get("content") or []), "```", ""])
            return
        if node_type in ("taskItem", "decisionItem"):  # their text sits inline, not in a paragraph
            mark = "- [x] " if (node.get("attrs") or {}).get("state") == "DONE" else "- [ ] "
            mark = mark if node_type == "taskItem" else "- "
            text = _render_inline(node.get("content") or [])
            chunks.extend([f"{indent}{mark}{text.strip()}"] if text.strip() else [])
            return

        # Fallback: try rendering children.
        for child in node.get("content") or []:
            render_node(child, indent=indent)

    def _render_inline(nodes: list[Any]) -> str:
        parts: list[str] = []
        for child in nodes:
            if not isinstance(child, dict):
                continue
            if child.get("type") == "text":
                text = str(child.get("text") or "")
                marks = child.get("marks") or []
                if isinstance(marks, list) and any(
                    isinstance(mark, dict) and mark.get("type") == "code" for mark in marks
                ):
                    parts.append(f"`{text}`")
                else:
                    parts.append(text)
            elif child.get("type") == "hardBreak":
                parts.append("\n")
            elif child.get("type") in closure.ATTR_TEXT_NODES:  # its text is in its attributes
                parts.append(closure.attr_text(child))
            else:
                inner = child.get("content")
                if isinstance(inner, list):
                    parts.append(_render_inline(inner))
        return "".join(parts)

    content = doc.get("content")
    if not isinstance(content, list):
        return ""
    for node in content:
        render_node(node)
    # Avoid huge trailing whitespace.
    while chunks and not chunks[-1].strip():
        chunks.pop()
    return "\n".join(chunks)


def cmd_issue(args: argparse.Namespace) -> int:
    issue = _issue(args.key.upper())
    if args.raw:
        print(json.dumps(issue, indent=2))
        return 0
    if args.md:
        print(issue_markdown(issue, _comments(args.key.upper(), args.comments)), end="")
        return 0
    summary = _summarize(issue)
    print(f"{summary.key}  {summary.status}  {summary.issue_type}")
    print(summary.summary)
    if summary.epic:
        print(f"epic: {summary.epic}")
    return 0


def cmd_epic(args: argparse.Namespace) -> int:
    key = args.key.upper()
    if not args.list:
        issue = _issue(key)
        summary = _summarize(issue)
        print(f"{summary.key}  {summary.status}  {summary.issue_type}")
        print(summary.summary)
        return 0

    # Support both classic and team-managed project JQL conventions.
    candidates = [
        f'parent = "{key}"',
        f'"Epic Link" = "{key}"',
    ]
    combined: dict[str, dict[str, Any]] = {}
    for jql in candidates:
        for issue in _search(jql):
            issue_key = str(issue.get("key") or "")
            if issue_key:
                combined[issue_key] = issue

    ordered = sorted(combined.values(), key=lambda row: str(row.get("key") or ""))
    for issue in ordered:
        fields = issue.get("fields") or {}
        if not isinstance(fields, dict):
            fields = {}
        issuetype = fields.get("issuetype") or {}
        status = fields.get("status") or {}
        line = (
            f"{issue.get('key', '?'):>8}  "
            f"{getattr(status, 'get', lambda *_: '')('name'):<12}  "
            f"{getattr(issuetype, 'get', lambda *_: '')('name'):<10}  "
            f"{fields.get('summary', '')}"
        )
        print(line.rstrip())
    return 0


def main() -> int:
    load_env()
    if hasattr(sys.stdout, "reconfigure"):  # a Windows console is cp1252; comments are not
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    issue = sub.add_parser("issue", help="fetch a single issue")
    issue.add_argument("key")
    issue.add_argument("--raw", action="store_true", help="print full JSON")
    issue.add_argument("--md", action="store_true", help="print a small markdown summary")
    issue.add_argument(
        "--comments", type=int, default=5, help="with --md: how many of the last comments"
    )
    issue.set_defaults(fn=cmd_issue)

    epic = sub.add_parser("epic", help="fetch an epic or list its children")
    epic.add_argument("key")
    epic.add_argument("--list", action="store_true", help="list issues in the epic (JQL)")
    epic.set_defaults(fn=cmd_epic)

    args = parser.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
