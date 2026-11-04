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


def _gemini_that(monkeypatch, replies: list[object], config_seen: list[object]) -> list[int]:
    """Gemini fake: each reply is returned as the answer, or raised when it is an exception."""
    calls: list[int] = []

    class FakeModels:
        def generate_content(self, model: str, contents: str, config: object) -> SimpleNamespace:
            del model, contents
            calls.append(1)
            config_seen.append(config)
            reply = replies[min(len(calls), len(replies)) - 1]
            if isinstance(reply, Exception):
                raise reply
            return SimpleNamespace(text=reply)

    class FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            del api_key
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    import google.genai as genai

    monkeypatch.setattr(genai, "Client", FakeClient)
    return calls


TWO = [
    Candidate("B01003", "Total Population", "Total population"),
    Candidate("B19013", "Median Household Income", "Households"),
]


def test_a_slow_selector_call_is_cut_off_and_asked_again(monkeypatch) -> None:
    seen: list[object] = []
    calls = _gemini_that(monkeypatch, [TimeoutError("slow"), '{"table": "B19013"}'], seen)
    assert choose("income", TWO) == "B19013"
    assert len(calls) == 2


def test_the_selector_request_carries_a_timeout(monkeypatch) -> None:
    from src.retrieval import rerank

    seen: list[object] = []
    _gemini_that(monkeypatch, ['{"table": "B19013"}'], seen)
    choose("income", TWO)
    assert seen[0].http_options.timeout == rerank.TIMEOUT_S * 1000  # type: ignore[attr-defined]


def test_a_good_first_answer_is_not_asked_for_twice(monkeypatch) -> None:
    calls = _gemini_that(monkeypatch, ['{"table": "B19013"}'], [])
    assert choose("income", TWO) == "B19013"
    assert len(calls) == 1


def test_two_failed_attempts_fall_back_to_the_retrieval_top(monkeypatch) -> None:
    from src.retrieval import rerank

    calls = _gemini_that(monkeypatch, [TimeoutError("slow")], [])
    assert choose("income", TWO) == "B01003"
    assert len(calls) == rerank.ATTEMPTS
