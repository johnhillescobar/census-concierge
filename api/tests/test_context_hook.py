"""The Claude Code hooks that carry a slice across /clear and warn before the context fills."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))

import ctx  # noqa: E402


def transcript(path: Path, *usages: dict[str, Any], sidechain_last: bool = False) -> str:
    rows = [json.dumps({"type": "summary"})]
    for usage in usages:
        rows.append(json.dumps({"message": {"usage": usage}}))
    if sidechain_last:  # a subagent's message is not the main conversation's size
        rows.append(json.dumps({"isSidechain": True, "message": {"usage": {"input_tokens": 9}}}))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(path)


FULL = {"input_tokens": 2, "cache_creation_input_tokens": 5000, "cache_read_input_tokens": 805000}


def watch(
    capsys: pytest.CaptureFixture[str], path: str, session: str = "s", event: str = "PostToolUse"
) -> dict[str, Any] | None:
    ctx.context_watch({"transcript_path": path, "session_id": session, "hook_event_name": event})
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"] if out else None


@pytest.fixture(autouse=True)
def private_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ctx.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(ctx, "WINDOW", 1_000_000)
    monkeypatch.setattr(ctx, "WARN", 0.8)


def test_tokens_are_the_whole_context_of_the_newest_main_thread_message(tmp_path: Path) -> None:
    older = {"input_tokens": 1, "cache_creation_input_tokens": 1, "cache_read_input_tokens": 1}
    path = transcript(tmp_path / "t.jsonl", older, FULL, sidechain_last=True)
    assert ctx.used_tokens(path) == 810_002  # the sidechain row and the older row are ignored


@pytest.mark.parametrize("path", [None, "", "/no/such/file"])
def test_an_unreadable_transcript_has_no_count(path: str | None) -> None:
    assert ctx.used_tokens(path) is None


def test_a_transcript_in_another_format_has_no_count_and_no_error(tmp_path: Path) -> None:
    other = tmp_path / "t.jsonl"
    other.write_text('{"message": "text"}\nnot json\n[1]\n{"message": {"usage": 5}}\n')
    assert ctx.used_tokens(str(other)) is None


def test_the_warning_names_the_percent_the_steps_and_that_only_the_user_can_clear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = transcript(tmp_path / "t.jsonl", FULL)
    note = watch(capsys, path, event="UserPromptSubmit")
    assert note is not None and note["hookEventName"] == "UserPromptSubmit"
    text = note["additionalContext"]
    assert "81%" in text and "STATE.md" in text and "/clear" in text and "commit" in text


def test_below_the_threshold_it_says_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    small = {
        "input_tokens": 1,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 700_000,
    }
    assert watch(capsys, transcript(tmp_path / "t.jsonl", small)) is None


def test_a_warning_repeats_only_when_the_context_climbs_another_ten_percent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "t.jsonl"
    assert watch(capsys, transcript(path, FULL)) is not None  # 81%
    assert watch(capsys, transcript(path, FULL)) is None  # still 81%: silent
    ninety = {
        "input_tokens": 1,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 910_000,
    }
    assert watch(capsys, transcript(path, ninety)) is not None  # 91%: one more


def test_after_a_clear_the_next_climb_warns_again(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "t.jsonl"
    assert watch(capsys, transcript(path, FULL)) is not None
    fresh = {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 20_000}
    assert watch(capsys, transcript(path, fresh)) is None  # cleared: the marker goes
    assert watch(capsys, transcript(path, FULL)) is not None


def test_two_sessions_do_not_share_a_marker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = transcript(tmp_path / "t.jsonl", FULL)
    assert watch(capsys, path, session="a") is not None
    assert watch(capsys, path, session="b") is not None


def test_session_start_prints_the_newest_state_and_the_reminder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    old = tmp_path / "evidence" / "slice-5" / "cc-1"
    new = tmp_path / "evidence" / "slice-6" / "cc-2"
    for folder, text in ((old, "OLD STATE"), (new, "NEW STATE")):
        folder.mkdir(parents=True)
        (folder / "STATE.md").write_text(text, encoding="utf-8")
    os.utime(old / "STATE.md", (1_000, 1_000))
    os.utime(new / "STATE.md", (2_000, 2_000))  # the newest modification
    monkeypatch.setattr(ctx, "ROOT", tmp_path)
    ctx.session_start()
    out = capsys.readouterr().out
    assert "NEW STATE" in out and "OLD STATE" not in out
    assert "CLAUDE.md" in out and "run-slice.md" in out


def test_session_start_with_no_state_file_still_prints_the_reminder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ctx, "ROOT", tmp_path)
    ctx.session_start()
    assert "run-slice.md" in capsys.readouterr().out


def test_the_committed_settings_wire_all_three_events_to_this_script() -> None:
    hooks = json.loads((ROOT / ".claude" / "settings.json").read_text("utf-8"))["hooks"]
    wanted = {
        "SessionStart": "session-start",
        "UserPromptSubmit": "context-watch",
        "PostToolUse": "context-watch",
    }
    for event, mode in wanted.items():
        commands = [h["command"] for group in hooks[event] for h in group["hooks"]]
        assert any(".claude/hooks/ctx.py" in c and c.endswith(mode) for c in commands), event


def test_the_warning_is_addressed_to_the_event_that_fired(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = transcript(tmp_path / "t.jsonl", FULL)
    note = watch(capsys, path, session="post", event="PostToolUse")
    assert note is not None and note["hookEventName"] == "PostToolUse"
    ctx.context_watch({"transcript_path": path, "session_id": "bare"})  # no event named
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["hookEventName"]
