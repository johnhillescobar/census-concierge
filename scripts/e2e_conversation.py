"""End-to-end conversation round trip: real server, real model, real Census, real Postgres.

Create a conversation, append one real question, restart the server, reload the
thread, and check the stored turn is the answer the user was shown. Needs
OPENAI_API_KEY, CENSUS_API_KEY and DATABASE_URL (values are never printed).

    uv run python scripts/e2e_conversation.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"
QUESTION = "What is the population of Detroit, Michigan?"


@contextmanager
def server() -> Iterator[None]:
    argv = [sys.executable, "-m", "uvicorn", "src.main:app", "--port", str(PORT)]
    argv += ["--loop", "src.loop:selector_factory"]
    proc = subprocess.Popen(argv, cwd=ROOT / "api", stdout=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                httpx.get(f"{BASE}/openapi.json", timeout=2)
                break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise SystemExit("FAIL server did not start")
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=15)


def check(label: str, ok: bool) -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {label}", flush=True)
    if not ok:
        raise SystemExit(1)


def main() -> int:
    load_dotenv(ROOT / ".env")
    missing = [
        k for k in ("OPENAI_API_KEY", "CENSUS_API_KEY", "DATABASE_URL") if not os.environ.get(k)
    ]
    if missing:
        print(f"Missing {', '.join(missing)} in the environment.", file=sys.stderr)
        return 2
    user = {"x-user-id": str(uuid4())}
    with server():
        created = httpx.post(f"{BASE}/conversations", headers=user)
        check("POST /conversations 201", created.status_code == 201)
        path = f"{BASE}/conversations/{created.json()['thread_id']}"
        turn = httpx.post(f"{path}/turns", headers=user, json={"question": QUESTION}, timeout=120)
        answer = turn.json()
        check("POST turns 200", turn.status_code == 200)
        check(
            "answer has a Census URL, rows, GEOID, MOE",
            all(answer[k] for k in ("urls", "rows", "moe", "geoid")),
        )
    with server():  # a fresh process: nothing in memory
        loaded = httpx.get(path, headers=user)
        check("GET after restart 200", loaded.status_code == 200)
        turns = loaded.json()["turns"]
        check(
            "one stored turn with the asked question", [t["question"] for t in turns] == [QUESTION]
        )
        check("stored response equals the answer shown", turns[0]["response"] == answer)
        stranger = httpx.get(path, headers={"x-user-id": str(uuid4())})
        check("another user gets 404", stranger.status_code == 404)
    print("e2e_conversation OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
