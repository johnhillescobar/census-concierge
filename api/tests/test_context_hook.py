"""The Claude Code hooks that carry a slice across /clear and warn before the context fills."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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


def gate(capsys: pytest.CaptureFixture[str], call: Any) -> dict[str, Any] | None:
    ctx.agent_gate({"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": call})
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"] if out else None


@pytest.mark.parametrize(
    ("agent", "label"),
    [
        ("general-purpose", "Gate 2 cold review, CC-1"),
        ("general-purpose", "gate2 re-run on fixes"),
        ("fork", "Gate-2 review"),
        (None, "GATE 2"),
        ("general-purpose", "Gate_2 review"),
        # the invariants pass goes through only when the label says nothing else
        ("general-purpose", "Gate 2 bug pass and invariants"),
        ("general-purpose", "Gate 2 cold review, then review-pr"),
        ("general-purpose", "Gate 2: review PR 151"),
        ("general-purpose", "Gate 2: /code-review then review-pr"),
        ("general-purpose", "Gate 2 code review, then invariants"),
        ("general-purpose", "Gate 2 full review incl. invariants"),
        ("general-purpose", "Gate 2 re-run on fixes (invariants too)"),
        ("general-purpose", "Gate 2 pass on the fixes"),
    ],
)
def test_a_gate_2_call_to_any_other_agent_is_denied_and_told_which_agent_to_use(
    capsys: pytest.CaptureFixture[str], agent: str | None, label: str
) -> None:
    decision = gate(capsys, {"subagent_type": agent, "description": label, "prompt": "p"})
    assert decision is not None and decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert ctx.GATE2_AGENT in decision["permissionDecisionReason"]


@pytest.mark.parametrize(
    ("agent", "label"),
    [
        (ctx.GATE2_AGENT, "Gate 2 cold review, CC-1"),
        ("general-purpose", "Gate 1 mutation check"),
        ("general-purpose", "Gate 2 invariants pass"),
        ("general-purpose", "Gate-2 review-pr invariants pass, CC-1"),
        ("general-purpose", "gate2 project invariants: re-run on the fix commit for slice 6"),
        ("general-purpose", "Read a file"),
        # "gate two" is also an ordinary verb and number
        ("general-purpose", "Gate two endpoints behind auth"),
        # "gate" then "2" only across a word edge: none of these names Gate 2
        ("general-purpose", "Investigate 2 failing tests"),
        ("general-purpose", "Aggregate 2 eval runs"),
        ("general-purpose", "Delegate 2 lookups"),
        ("general-purpose", "Gate 20 smoke"),
        ("general-purpose", "Gate 2nd look"),
    ],
)
def test_the_cold_agent_the_invariants_pass_and_other_work_go_through(
    capsys: pytest.CaptureFixture[str], agent: str, label: str
) -> None:
    call = {"subagent_type": agent, "description": label, "prompt": "Gate 2 is named here too"}
    assert gate(capsys, call) is None


@pytest.mark.parametrize("call", [None, "text", [], {}, {"description": None}])
def test_a_call_the_gate_cannot_read_goes_through_without_an_error(
    capsys: pytest.CaptureFixture[str], call: Any
) -> None:
    assert gate(capsys, call) is None


@pytest.mark.parametrize("override", [{"model": "fable"}, {"effort": "low"}])
def test_the_cold_agent_called_with_its_own_model_or_effort_is_denied(
    capsys: pytest.CaptureFixture[str], override: dict[str, str]
) -> None:
    # a `model` on the call beats the agent file's, so the review would run on the caller's choice
    call = {"subagent_type": ctx.GATE2_AGENT, "description": "Read a file", **override}
    decision = gate(capsys, call)
    assert decision is not None and decision["permissionDecision"] == "deny"


def test_a_label_that_is_not_text_is_still_read(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate(capsys, {"description": ["Gate 2"]}) is not None


def test_the_hook_command_denies_on_stdout_and_exits_zero() -> None:
    call = {"tool_input": {"subagent_type": "general-purpose", "description": "Gate 2 review"}}
    done = subprocess.run(
        [sys.executable, str(ROOT / ".claude" / "hooks" / "ctx.py"), "agent-gate"],
        input=json.dumps(call),
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0
    assert json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_committed_settings_put_the_gate_before_every_agent_call() -> None:
    hooks = json.loads((ROOT / ".claude" / "settings.json").read_text("utf-8"))["hooks"]
    commands = [
        h["command"]
        for group in hooks["PreToolUse"]
        if "Agent" in group["matcher"].split("|")
        for h in group["hooks"]
    ]
    # `|| true`: a checkout without the script must not block every subagent with python's exit 2
    assert any(".claude/hooks/ctx.py" in c and c.endswith("agent-gate || true") for c in commands)


def test_the_agent_the_gate_names_is_committed_and_names_its_own_model_and_effort() -> None:
    text = (ROOT / ".claude" / "agents" / f"{ctx.GATE2_AGENT}.md").read_text("utf-8")
    head = dict(
        line.split(": ", 1) for line in text.split("---")[1].strip().splitlines() if ": " in line
    )
    assert head["name"] == ctx.GATE2_AGENT
    # A named model. The hook does not check which model the caller runs on.
    assert head["model"] not in ("", "inherit")
    assert head["effort"]  # without one, the agent need not run at the session's level


@pytest.mark.parametrize(
    "rel",
    [
        "docs/playbooks/run-slice.md",
        ".claude/skills/run-slice/SKILL.md",
        "scripts/gate.sh",
        "scripts/gate.ps1",
    ],
)
def test_everything_that_sends_gates_to_a_subagent_names_the_agent_the_gate_allows(
    rel: str,
) -> None:
    # Each one sends gates to a general-purpose subagent, which the gate denies for Gate 2.
    assert ctx.GATE2_AGENT in (ROOT / rel).read_text("utf-8")


@pytest.mark.parametrize(
    ("shells", "probe", "run"),
    [
        (["bash"], ["-c", "exit 0"], ["scripts/gate.sh"]),
        (
            ["pwsh", "powershell"],
            ["-NoProfile", "-Command", "exit 0"],
            ["-NoProfile", "-File", "scripts/gate.ps1"],
        ),
    ],
)
def test_the_gate_2_handoff_sends_the_bug_pass_to_the_cold_agent_and_no_other_phase_does(
    shells: list[str], probe: list[str], run: list[str]
) -> None:
    shell = next((found for name in shells if (found := shutil.which(name))), None)
    # `bash` on Windows can be a launcher with nothing behind it: that is no shell, not a failure
    if shell is None or subprocess.run([shell, *probe], check=False).returncode != 0:
        pytest.skip(f"no working {shells[0]} on this machine")

    def handoff(phase: str) -> str:
        done = subprocess.run(
            [shell, *run, phase, "9"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return " ".join(done.stdout.split())

    gate2 = handoff("gate2")
    assert (
        f"first the {ctx.GATE2_AGENT} agent" in gate2 and "general-purpose, not fork" not in gate2
    )
    # the cold transcript has a named file, and the second agent is told not to redo that pass
    assert gate2.count("gate2-cold.txt") == 2
    gate1 = handoff("gate1")
    assert ctx.GATE2_AGENT not in gate1 and "general-purpose, not fork" in gate1
