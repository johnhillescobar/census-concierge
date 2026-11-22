"""Selector choose(): fallback and Gemini config. No live model."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import threading
import time
from types import SimpleNamespace

import httpx
from ask_fixtures import _harris
from src.ask import ExecutionRecord, assemble
from src.retrieval.rerank import WAIT_SECONDS, Candidate, choose
from src.tools import BuildUrlTool, SearchTablesTool


def test_gemini_selector_disables_thinking(monkeypatch) -> None:
    captured: dict[str, int | None] = {}

    class FakeModels:
        def generate_content(self, model: str, contents: str, config: object) -> SimpleNamespace:
            del model, contents
            thinking = getattr(config, "thinking_config", None)
            captured["budget"] = getattr(thinking, "thinking_budget", None)
            return SimpleNamespace(text='{"table": "B01003"}')

    class FakeClient:
        def __init__(self, api_key: str | None = None, **kwargs: object) -> None:
            del api_key, kwargs
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    import google.genai as genai

    monkeypatch.setattr(genai, "Client", FakeClient)
    picked = choose(
        "population",
        [Candidate("B01003", "Total Population", "Total population")],
    )
    assert picked == "B01003"
    assert captured["budget"] == 0


def test_selector_falls_back_to_retrieval_top_on_error(monkeypatch) -> None:
    class FakeModels:
        def generate_content(self, model: str, contents: str, config: object) -> SimpleNamespace:
            del model, contents, config
            raise RuntimeError("selector down")

    class FakeClient:
        def __init__(self, api_key: str | None = None, **kwargs: object) -> None:
            del api_key, kwargs
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    import google.genai as genai

    monkeypatch.setattr(genai, "Client", FakeClient)
    picked = choose(
        "population",
        [
            Candidate("B01003", "Total Population", "Total population"),
            Candidate("B19013", "Median Household Income", "Households"),
        ],
    )
    assert picked == "B01003"


def test_a_completed_rerank_keeps_the_model_pick(monkeypatch) -> None:
    class FakeModels:
        def generate_content(self, model: str, contents: str, config: object) -> SimpleNamespace:
            del model, contents, config
            return SimpleNamespace(text='{"table": "B19013"}')

    class FakeClient:
        def __init__(self, api_key: str | None = None, **kwargs: object) -> None:
            del api_key, kwargs
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    import google.genai as genai

    monkeypatch.setattr(genai, "Client", FakeClient)
    picked = choose(
        "income",
        [
            Candidate("B19113", "Median Family Income", "Families"),
            Candidate("B19013", "Median Household Income", "Households"),
        ],
    )
    assert picked == "B19013"


def _hang_server(box: dict[str, object]) -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    box["server"] = server
    box["port"] = server.getsockname()[1]
    ready = box["ready"]
    assert isinstance(ready, threading.Event)
    ready.set()
    server.settimeout(8)
    try:
        conn, _ = server.accept()
    except OSError:
        server.close()
        return
    box["conn"] = conn
    conn.settimeout(8)
    data = b""
    try:
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
    except OSError:
        data = b""
    box["request"] = data.decode("latin1", errors="replace")
    got = box["got"]
    assert isinstance(got, threading.Event)
    got.set()
    try:
        while True:
            chunk = conn.recv(1)
            if not chunk:
                break
    except OSError:
        pass
    finally:
        released = box["released"]
        assert isinstance(released, threading.Event)
        released.set()
        conn.close()
        server.close()


def test_a_stalled_call_is_abandoned_at_3_seconds_without_a_server_deadline(
    monkeypatch,
) -> None:
    box: dict[str, object] = {
        "ready": threading.Event(),
        "got": threading.Event(),
        "released": threading.Event(),
    }
    threading.Thread(target=_hang_server, args=(box,), daemon=True).start()
    ready = box["ready"]
    assert isinstance(ready, threading.Event)
    assert ready.wait(2)
    assert WAIT_SECONDS == 3.0

    import google.genai as genai
    from google.genai import types

    real = genai.Client
    port = box["port"]

    def factory(api_key: str | None = None, http_options: object | None = None) -> object:
        options = (
            http_options if isinstance(http_options, types.HttpOptions) else types.HttpOptions()
        )
        options.base_url = f"http://127.0.0.1:{port}"
        return real(api_key=api_key or "local", http_options=options)

    monkeypatch.setenv("GEMINI_API_KEY", "local")
    monkeypatch.setattr(genai, "Client", factory)
    holder: dict[str, str] = {}

    def run() -> None:
        before = {thread.ident for thread in threading.enumerate()}
        holder["picked"] = choose(
            "income",
            [
                Candidate("B19113", "Median Family Income", "Families"),
                Candidate("B19013", "Median Household Income", "Households"),
            ],
        )
        holder["left"] = str(
            [
                thread.name
                for thread in threading.enumerate()
                if thread.ident not in before and thread.is_alive()
            ]
        )

    worker = threading.Thread(target=run)
    started = time.perf_counter()
    worker.start()
    try:
        worker.join(6)
        elapsed = time.perf_counter() - started
        assert not worker.is_alive()
        assert holder["picked"] == "B19113"
        assert 2.0 <= elapsed < 6.0
        got = box["got"]
        released = box["released"]
        assert isinstance(got, threading.Event) and got.wait(1)
        request = box["request"]
        assert isinstance(request, str)
        assert "x-server-timeout" not in request.lower()
        assert isinstance(released, threading.Event) and released.wait(2)
        assert holder["left"] == "[]"
    finally:
        for key in ("conn", "server"):
            sock = box.get(key)
            if isinstance(sock, socket.socket):
                sock.close()
        worker.join(2)


def _family_income_url_tool() -> BuildUrlTool:
    facts = {"acs5": {2024: {"B19113": {"universe": "Families", "variables": ["001E"]}}}}
    return BuildUrlTool(
        allowed_tables=lambda: {"B19113", "B19013"},
        allowed_geographies=lambda: {("county:201", "state:48", "acs5")},
        latest_vintage=lambda dataset: 2024,
        table_facts=lambda dataset, year, table_id: (
            facts.get(dataset, {}).get(year, {}).get(table_id)
        ),
        last_geography=_harris,
    )


def _status_server(box: dict[str, object], status: bytes) -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    box["server"] = server
    box["port"] = server.getsockname()[1]
    ready = box["ready"]
    assert isinstance(ready, threading.Event)
    ready.set()
    server.settimeout(8)
    seen = 0
    while seen < 4:
        try:
            conn, _ = server.accept()
        except OSError:
            break
        data = b""
        conn.settimeout(8)
        with contextlib.suppress(OSError):
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
        body = b'{"error":{"code":503,"message":"unavailable","status":"UNAVAILABLE"}}'
        with contextlib.suppress(OSError):
            conn.sendall(
                b"HTTP/1.1 "
                + status
                + b"\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + body
            )
        seen += 1
        box["requests"] = seen
        conn.close()
    server.close()


def test_a_retriable_status_does_not_wait_out_a_backoff(monkeypatch) -> None:
    box: dict[str, object] = {"ready": threading.Event()}
    threading.Thread(
        target=_status_server, args=(box, b"503 Service Unavailable"), daemon=True
    ).start()
    ready = box["ready"]
    assert isinstance(ready, threading.Event)
    assert ready.wait(2)

    import google.genai as genai
    from google.genai import types

    real = genai.Client
    port = box["port"]

    def factory(api_key: str | None = None, http_options: object | None = None) -> object:
        options = (
            http_options if isinstance(http_options, types.HttpOptions) else types.HttpOptions()
        )
        options.base_url = f"http://127.0.0.1:{port}"
        return real(api_key=api_key or "local", http_options=options)

    monkeypatch.setenv("GEMINI_API_KEY", "local")
    monkeypatch.setattr(genai, "Client", factory)
    started = time.perf_counter()
    try:
        picked = choose(
            "income",
            [
                Candidate("B19113", "Median Family Income", "Families"),
                Candidate("B19013", "Median Household Income", "Households"),
            ],
        )
        elapsed = time.perf_counter() - started
        assert picked == "B19113"
        assert box.get("requests") == 1
        assert elapsed < WAIT_SECONDS
    finally:
        sock = box.get("server")
        if isinstance(sock, socket.socket):
            sock.close()


async def test_a_stalled_rerank_keeps_related_tables_universe_and_margins(monkeypatch) -> None:
    class DeadlineModels:
        def generate_content(self, model: str, contents: str, config: object) -> SimpleNamespace:
            del model, contents, config
            raise httpx.ReadTimeout("rerank deadline")

    class DeadlineClient:
        def __init__(self, api_key: str | None = None, **kwargs: object) -> None:
            del api_key, kwargs
            self.models = DeadlineModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    import google.genai as genai

    monkeypatch.setattr(genai, "Client", DeadlineClient)

    def describe(table_id: str) -> dict[str, object]:
        return {
            "B19113": {"title": "Median Family Income", "universe": "Families", "members": []},
            "B19013": {
                "title": "Median Household Income",
                "universe": "Households",
                "members": [],
            },
        }[table_id]

    message = await asyncio.wait_for(
        SearchTablesTool(
            search=lambda _question, k=10: ["B19113", "B19013"][:k],
            describe=describe,
        ).ainvoke(
            {
                "type": "tool_call",
                "name": "search_tables",
                "args": {"question": "median income"},
                "id": "c1",
            }
        ),
        timeout=2,
    )
    hits = message.artifact.hits
    assert hits[0]["table_id"] == "B19113"
    assert hits[0]["universe"] == "Families"
    assert [hit["table_id"] for hit in hits] == ["B19113", "B19013"]
    assert "Families" in message.content
    assert "related" in message.content

    built = await _family_income_url_tool().ainvoke(
        {
            "type": "tool_call",
            "name": "build_url",
            "args": {"table_id": "B19113"},
            "id": "c2",
        }
    )
    assert "B19113_001E" in built.artifact.url
    assert "B19113_001M" in built.artifact.url
    assert built.artifact.universe == "Families"

    record = ExecutionRecord()
    record.pool = list(hits)
    record.table_id = "B19113"
    record.universe = "Families"
    response = assemble("framed", record)
    assert response.table_id == "B19113"
    assert response.universe == "Families"
    households = next(item for item in response.alternatives if item.table_id == "B19013")
    assert households.universe == "Households"
