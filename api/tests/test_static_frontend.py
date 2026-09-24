"""The built UI is served from the same FastAPI process as POST /ask."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from src.contract import AskResponse
from src.main import create_app

EMPTY = {
    "answer": "",
    "urls": [],
    "requested_years": [],
    "attempted_years": [],
    "succeeded_years": [],
    "failed_years": [],
    "omitted_years": [],
    "omission_reasons": [],
    "legs": [],
    "rows": [],
    "moe": [],
    "geoid": "",
    "universe": "",
    "table_id": "",
    "alternatives": [],
    "comparisons": [],
    "warnings": [],
    "plan": {
        "table_id": "",
        "variables": [],
        "dataset": "acs5",
        "years": [],
        "requested_years": [],
        "geographies": [],
        "allow_overlapping_acs5": False,
    },
    "chart": None,
    "chart_unavailable": False,
}


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><html><head><title>census-concierge</title></head>"
        "<body><div id='root'></div></body></html>",
        encoding="utf-8",
    )
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ok');\n", encoding="utf-8")
    return dist


def test_get_root_serves_the_built_index(tmp_path: Path) -> None:
    response = TestClient(create_app(_dist(tmp_path))).get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "census-concierge" in response.text
    assert response.headers.get("access-control-allow-origin") is None


def test_built_assets_are_same_origin(tmp_path: Path) -> None:
    response = TestClient(create_app(_dist(tmp_path))).get("/assets/app.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.text.strip() == "console.log('ok');"


def test_post_ask_still_works_when_the_ui_is_mounted(tmp_path: Path, monkeypatch: Any) -> None:
    async def fake_loop(question: str) -> AskResponse:
        _ = question
        return AskResponse(**EMPTY)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    response = TestClient(create_app(_dist(tmp_path))).post(
        "/ask", json={"question": "population of Harris County"}
    )
    assert response.status_code == 200
    assert response.json() == EMPTY
    assert response.headers.get("access-control-allow-origin") is None


def test_openapi_stays_ask_only_when_the_ui_is_mounted(tmp_path: Path) -> None:
    schema = create_app(_dist(tmp_path)).openapi()
    assert list(schema["paths"]) == ["/ask"]
    assert list(schema["paths"]["/ask"]) == ["post"]


def test_docs_still_work_when_the_ui_is_mounted(tmp_path: Path) -> None:
    client = TestClient(create_app(_dist(tmp_path)))
    docs = client.get("/docs")
    assert docs.status_code == 200
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert list(openapi.json()["paths"]) == ["/ask"]


def test_missing_dist_does_not_take_down_ask(tmp_path: Path, monkeypatch: Any) -> None:
    async def fake_loop(question: str) -> AskResponse:
        _ = question
        return AskResponse(**EMPTY)

    monkeypatch.setattr("src.main.run_ask", fake_loop)
    client = TestClient(create_app(tmp_path / "no-dist"))
    assert client.get("/").status_code == 404
    response = client.post("/ask", json={"question": "population of Harris County"})
    assert response.status_code == 200


def test_serving_the_ui_does_not_install_cors(tmp_path: Path) -> None:
    assert create_app(_dist(tmp_path)).user_middleware == []
