"""The ticket reader: a ticket and its last comments, all or nothing, from any checkout."""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import jira_fetch as jf  # noqa: E402
import jira_transition as jt  # noqa: E402

ISSUE = {
    "key": "CC-9",
    "fields": {
        "summary": "A ticket",
        "status": {"name": "In Progress"},
        "issuetype": {"name": "Story"},
        "description": {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "AC1. it works"}]}
            ],
        },
    },
}


def comment(when: str, text: str) -> dict[str, Any]:
    body = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }
    return {"created": when, "author": {"displayName": "Owner"}, "body": body}


def run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(jf, "load_env", lambda root=jf.ROOT: None)
    monkeypatch.setenv("ATLASSIAN_EMAIL", "e@example.com")
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "t")
    monkeypatch.setattr(sys, "argv", ["jira_fetch.py", *argv])
    return jf.main()


def test_md_prints_the_description_then_the_last_comments_oldest_first(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # bodies the header cannot contain: it says "oldest first", so "first" would match it
    newest_first = [comment("2026-11-26", "body-two"), comment("2026-11-25", "body-one")]
    asked: list[str] = []

    def api(method: str, path: str, body: Any = None) -> dict[str, Any]:
        asked.append(path)
        return {"comments": newest_first} if "/comment" in path else ISSUE

    monkeypatch.setattr(jf, "_api", api)
    assert run(monkeypatch, "issue", "cc-9", "--md", "--comments", "2") == 0
    out = capsys.readouterr().out
    assert "AC1. it works" in out
    assert out.index("AC1. it works") < out.index("body-one") < out.index("body-two")
    assert any("orderBy=-created" in p and "maxResults=2" in p for p in asked)


@pytest.mark.parametrize("error", [urllib.error.URLError("no route"), TimeoutError("timed out")])
@pytest.mark.parametrize("failing_call", [1, 2])  # the issue itself, or its comments after it
def test_an_unreachable_jira_exits_non_zero_and_prints_no_ticket_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    failing_call: int,
) -> None:
    calls: list[str] = []
    real_api = jf._api

    def urlopen(request: Any, timeout: float) -> Any:
        calls.append(request.full_url)
        if len(calls) == failing_call:
            raise error

        class Response:
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

            def read(self) -> bytes:
                import json

                return json.dumps(ISSUE).encode()

        return Response()

    monkeypatch.setattr(jf.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(jf, "_api", real_api)
    with pytest.raises(SystemExit) as stopped:
        run(monkeypatch, "issue", "CC-9", "--md")
    assert stopped.value.code != 0
    assert capsys.readouterr().out == ""
    assert len(calls) == failing_call


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def main_and_worktree(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(
        main,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
    )
    (main / ".env").write_text("JIRA_FETCH_TEST_VALUE=from-main\n", encoding="utf-8")
    worktree = tmp_path / "wt"
    git(main, "worktree", "add", "-q", "-b", "side", str(worktree))
    return main, worktree


def test_a_worktree_with_no_env_reads_the_main_checkouts(
    main_and_worktree: tuple[Path, Path],
) -> None:
    main, worktree = main_and_worktree
    assert not (worktree / ".env").exists()
    assert jf.env_file(worktree).resolve() == (main / ".env").resolve()


def test_a_checkouts_own_env_comes_first(main_and_worktree: tuple[Path, Path]) -> None:
    _, worktree = main_and_worktree
    (worktree / ".env").write_text("X=1\n", encoding="utf-8")
    assert jf.env_file(worktree) == worktree / ".env"


def test_no_env_anywhere_is_none(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    assert jf.env_file(tmp_path) is None


def test_the_transition_script_loads_the_main_checkouts_env_from_a_worktree(
    monkeypatch: pytest.MonkeyPatch, main_and_worktree: tuple[Path, Path]
) -> None:
    _, worktree = main_and_worktree
    monkeypatch.setenv("JIRA_FETCH_TEST_VALUE", "unset")
    monkeypatch.delenv("JIRA_FETCH_TEST_VALUE")
    monkeypatch.setattr(jt, "ROOT", worktree)
    jt._load_env()
    assert os.environ.get("JIRA_FETCH_TEST_VALUE") == "from-main"


def node(kind: str, *content: dict[str, Any], **attrs: Any) -> dict[str, Any]:
    return {"type": kind, "content": list(content), "attrs": attrs}


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


@pytest.mark.parametrize(
    ("body", "shown"),
    [
        (node("doc", node("codeBlock", text("make check"))), "make check"),
        (
            node("doc", node("taskList", node("taskItem", text("rerun AC4"), state="TODO"))),
            "rerun AC4",
        ),
        (
            node("doc", node("decisionList", node("decisionItem", text("keep the waiver")))),
            "keep the waiver",
        ),
        (node("doc", node("paragraph", text("ask "), node("mention", text="@Owner"))), "@Owner"),
        (
            node("doc", node("paragraph", node("inlineCard", url="https://example.com/pr/1"))),
            "https://example.com/pr/1",
        ),
    ],
)
def test_a_comment_keeps_text_that_is_not_a_plain_paragraph(
    body: dict[str, Any], shown: str
) -> None:
    out = jf.issue_markdown(ISSUE, [{"created": "2026-11-26", "author": {}, "body": body}])
    assert shown in out and "(empty)" not in out
