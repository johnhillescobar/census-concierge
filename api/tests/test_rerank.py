"""Selector choose(): fallback and Gemini config. No live model."""

from __future__ import annotations

from types import SimpleNamespace

from src.retrieval.rerank import Candidate, choose


def test_gemini_selector_disables_thinking(monkeypatch) -> None:
    captured: dict[str, int | None] = {}

    class FakeModels:
        def generate_content(self, model: str, contents: str, config: object) -> SimpleNamespace:
            del model, contents
            thinking = getattr(config, "thinking_config", None)
            captured["budget"] = getattr(thinking, "thinking_budget", None)
            return SimpleNamespace(text='{"table": "B01003"}')

    class FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            del api_key
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
        def __init__(self, api_key: str | None = None) -> None:
            del api_key
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
