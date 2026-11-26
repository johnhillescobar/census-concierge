#!/usr/bin/env python3
"""Claude Code hooks that keep a long slice from losing its rules (stdlib only).

    ctx.py session-start    SessionStart (startup, resume, clear, compact): print the newest
                            evidence/slice-*/*/STATE.md and a reminder (added to context)
    ctx.py context-watch    UserPromptSubmit and PostToolUse: when the conversation is at or past
                            CLAUDE_CONTEXT_WARN (default 0.8) of CLAUDE_CONTEXT_WINDOW (default
                            1000000 tokens), tell the agent to finish the phase, update STATE.md,
                            commit, and ask the user to run /clear. Once per 10% step.
    ctx.py agent-gate       PreToolUse on the Agent tool: a subagent call labelled Gate 2 is
                            denied unless it goes to the gate2-cold agent, which runs on
                            another model, or is the invariants pass.

A hook cannot run /clear; only the user can. The transcript's line format is not documented, so
the token count is read defensively and a failure prints nothing, never an error.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WINDOW = int(os.environ.get("CLAUDE_CONTEXT_WINDOW", "1000000"))
WARN = float(os.environ.get("CLAUDE_CONTEXT_WARN", "0.8"))
TAIL = 400_000  # bytes of the transcript to scan: the newest assistant message is at the end
GATE2_AGENT = "gate2-cold"  # .claude/agents/gate2-cold.md


def session_start() -> None:
    states = list(ROOT.glob("evidence/slice-*/*/STATE.md"))
    lines = ["Before acting: read CLAUDE.md and docs/playbooks/run-slice.md, then the state below."]
    if states:
        newest = max(states, key=lambda p: p.stat().st_mtime)
        lines += [f"--- {newest.relative_to(ROOT).as_posix()} ---", newest.read_text("utf-8")]
    print("\n".join(lines))


def used_tokens(transcript: str | None) -> int | None:
    """Tokens in context at the newest main-thread assistant message, or None if unreadable."""
    if not transcript:
        return None
    try:
        with open(transcript, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - TAIL))
            rows = handle.read().decode("utf-8", "replace").splitlines()[1:]
    except OSError:
        return None
    for row in reversed(rows):
        try:
            entry = json.loads(row)
            usage = entry["message"]["usage"]
            if entry.get("isSidechain"):
                continue
            return sum(
                int(usage.get(k) or 0)
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return None


def context_watch(payload: dict) -> None:
    tokens = used_tokens(payload.get("transcript_path"))
    marker = Path(tempfile.gettempdir()) / f"claude-ctx-{payload.get('session_id', 'x')}"
    if tokens is None or tokens / WINDOW < WARN:
        marker.unlink(missing_ok=True)  # after a /clear the next climb warns again
        return
    step = int(tokens / WINDOW * 10)
    try:
        if step <= int(marker.read_text()):
            return
    except (OSError, ValueError):
        pass
    marker.write_text(str(step))
    note = (
        f"Context is about {tokens / WINDOW:.0%} full ({tokens:,} of {WINDOW:,} tokens). Do not "
        "start a new phase. Finish the current step, update the slice's STATE.md (phase, what is "
        "done, what is open, the next command), commit it, and tell the user to run /clear: a "
        "fresh session reads STATE.md back in. Do not let it auto-compact."
    )
    event = payload.get("hook_event_name") or "UserPromptSubmit"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": note}}))


def agent_gate(payload: dict) -> None:
    """Deny a subagent call labelled Gate 2 that is neither the cold-review agent nor the
    invariants pass. It reads the label the caller gave the call, nothing else: a review under
    another label, or one done without a subagent, is not seen."""
    call = payload.get("tool_input")
    if not isinstance(call, dict) or call.get("subagent_type") == GATE2_AGENT:
        return
    label = "".join(str(call.get("description") or "").lower().split()).replace("-", "")
    if "gate2" not in label or "invariant" in label or "reviewpr" in label:
        return
    reason = (
        f"Gate 2's cold bug pass goes to the `{GATE2_AGENT}` agent "
        f"(.claude/agents/{GATE2_AGENT}.md), which runs on a different model from the session "
        f"that wrote the code. Call the Agent tool again with subagent_type `{GATE2_AGENT}` and "
        "pass only the repo path, the review base and head, and the evidence path. The invariants "
        "pass (docs/playbooks/review-pr.md) is not affected: name it `invariants` in the "
        "description."
    )
    decision = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }
    print(json.dumps({"hookSpecificOutput": decision}))


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    if mode == "session-start":
        session_start()
    elif mode == "context-watch":
        context_watch(payload)
    elif mode == "agent-gate":
        agent_gate(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
