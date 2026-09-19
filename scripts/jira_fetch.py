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
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    except urllib.error.URLError as exc:
        print(f"Jira transport error {method} {path}: {exc.reason}", file=sys.stderr)
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


def _print_issue_markdown(issue: dict[str, Any]) -> None:
    summary = _summarize(issue)
    print(f"## {summary.key} — {summary.summary}")
    print()
    print(f"- Type: {summary.issue_type}")
    print(f"- Status: {summary.status}")
    print(f"- Epic: {summary.epic or '—'}")
    print()
    fields = issue.get("fields") or {}
    if not isinstance(fields, dict):
        return
    raw = fields.get("description")
    if isinstance(raw, dict) and raw.get("type") == "doc":
        rendered = _adf_to_markdown(raw)
        if rendered.strip():
            print("### Description")
            print()
            print(rendered.rstrip())
            print()
    elif isinstance(raw, str) and raw.strip():
        print("### Description")
        print()
        print(raw.strip())
        print()


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
        _print_issue_markdown(issue)
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
    _load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    issue = sub.add_parser("issue", help="fetch a single issue")
    issue.add_argument("key")
    issue.add_argument("--raw", action="store_true", help="print full JSON")
    issue.add_argument("--md", action="store_true", help="print a small markdown summary")
    issue.set_defaults(fn=cmd_issue)

    epic = sub.add_parser("epic", help="fetch an epic or list its children")
    epic.add_argument("key")
    epic.add_argument("--list", action="store_true", help="list issues in the epic (JQL)")
    epic.set_defaults(fn=cmd_epic)

    args = parser.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
