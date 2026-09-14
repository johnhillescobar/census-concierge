#!/usr/bin/env python3
"""Regenerate packages/client from FastAPI's OpenAPI schema.

    uv run python scripts/generate_client.py
    uv run python scripts/generate_client.py --check

--check exits 1 when the committed copy is stale. That is the CI drift gate.
Fix: run the command without --check and commit packages/client/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from src.main import app

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
CLIENT = ROOT / "packages" / "client"
OPENAPI_JSON = CLIENT / "openapi.json"
SCHEMA_DTS = CLIENT / "schema.d.ts"


def _openapi_typescript() -> str:
    win = WEB / "node_modules" / ".bin" / "openapi-typescript.cmd"
    unix = WEB / "node_modules" / ".bin" / "openapi-typescript"
    if win.exists():
        return str(win)
    if unix.exists():
        return str(unix)
    print(
        "openapi-typescript is not installed. Run: npm --prefix web ci",
        file=sys.stderr,
    )
    sys.exit(1)


def _dump_openapi() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _generate_schema(openapi: str) -> str:
    binary = _openapi_typescript()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "openapi.json"
        dst = Path(tmp) / "schema.d.ts"
        src.write_text(openapi, encoding="utf-8", newline="\n")
        subprocess.run([binary, str(src), "-o", str(dst)], cwd=ROOT, check=True)
        return _normalize(dst.read_text(encoding="utf-8"))


def generate() -> tuple[str, str]:
    openapi = _dump_openapi()
    return openapi, _generate_schema(openapi)


def write(openapi: str, schema: str) -> None:
    CLIENT.mkdir(parents=True, exist_ok=True)
    OPENAPI_JSON.write_text(openapi, encoding="utf-8", newline="\n")
    SCHEMA_DTS.write_text(schema, encoding="utf-8", newline="\n")


def _read(path: Path) -> str | None:
    if not path.is_file():
        return None
    return _normalize(path.read_text(encoding="utf-8"))


def check(openapi: str, schema: str) -> int:
    committed_json = _read(OPENAPI_JSON)
    committed_schema = _read(SCHEMA_DTS)
    stale = committed_json != openapi or committed_schema != schema
    if not stale:
        print("packages/client is up to date.")
        return 0
    print(
        "packages/client is stale relative to the live OpenAPI schema.\n"
        "Regenerate with:  uv run python scripts/generate_client.py",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the committed client does not match the live schema",
    )
    args = parser.parse_args()
    openapi, schema = generate()
    if args.check:
        return check(openapi, schema)
    write(openapi, schema)
    print(f"wrote {OPENAPI_JSON.relative_to(ROOT).as_posix()}")
    print(f"wrote {SCHEMA_DTS.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
