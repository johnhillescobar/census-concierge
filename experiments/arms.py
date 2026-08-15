"""The models under test, behind two small protocols.

An arm is an `Encoder` (axis A) or a `Reranker` (axis B). Everything else in the
sweep is held identical, so the only thing that varies between two rows of the
report is the thing named in that row.

**Instruction prefixes are the trap.** E5 wants `query:`/`passage:`, BGE wants a
query instruction and no document prefix, Nomic wants `search_query:`/
`search_document:`, Gemini takes a task type and Cohere an input type. Using the
wrong one costs several points silently, and a sweep that gets them wrong
produces a confident false ranking. Each arm carries its own and records them.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

BATCH = 128


def _unit(matrix: np.ndarray) -> np.ndarray:
    """L2-normalize rows so cosine similarity is a dot product."""
    matrix = np.asarray(matrix, dtype=np.float32)
    return matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)


class Encoder(Protocol):
    name: str
    note: str

    def encode(self, texts: list[str], kind: str) -> np.ndarray: ...


class Reranker(Protocol):
    name: str
    note: str
    failures: int
    last_error: str

    def rank(self, question: str, candidates: list[str]) -> list[int]:
        """Candidate indices, best first."""
        ...


# --- bi-encoders, hosted -----------------------------------------------------


@dataclass
class OpenAIEncoder:
    model: str
    name: str = ""
    note: str = "no prefixes; symmetric query/document"
    params: str = "undisclosed"

    def __post_init__(self) -> None:
        self.name = self.name or f"openai/{self.model}"

    def encode(self, texts: list[str], kind: str) -> np.ndarray:
        from openai import OpenAI

        client = OpenAI()
        out: list[list[float]] = []
        for start in range(0, len(texts), 256):
            chunk = texts[start : start + 256]
            out.extend(
                i.embedding for i in client.embeddings.create(model=self.model, input=chunk).data
            )
        return _unit(np.asarray(out))


@dataclass
class GeminiEncoder:
    model: str = "gemini-embedding-001"
    name: str = ""
    note: str = "task_type RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY"
    params: str = "undisclosed"

    def __post_init__(self) -> None:
        self.name = self.name or f"google/{self.model}"

    def encode(self, texts: list[str], kind: str) -> np.ndarray:
        """Batches, then verifies the batch was honoured.

        `gemini-embedding-2` accepts a list of 100 and returns ONE embedding,
        with no error. Trusting the call would have built an index of 756
        documents from a single vector and scored it as a real arm. So every
        response is length-checked and anything short falls back to one call
        per text.
        """
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        config = types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT"
        )

        def embed(chunk: list[str]) -> list[list[float]]:
            """Retry with backoff. An empty response is treated as a failure.

            Under concurrency this API returns an empty embedding list rather
            than raising, so an unchecked call silently drops documents from the
            index. Never accept a short response as an answer.
            """
            for attempt in range(5):
                try:
                    result = client.models.embed_content(
                        model=self.model, contents=chunk, config=config
                    )
                    values = [e.values for e in (result.embeddings or [])]
                    if values:
                        return values
                except Exception:  # noqa: BLE001 - retried below, raised if persistent
                    pass
                time.sleep(2**attempt)
            raise RuntimeError(
                f"{self.model}: no embeddings after 5 attempts for {len(chunk)} texts"
            )

        if len(embed(texts[:2])) == 2:
            out: list[list[float]] = []
            for start in range(0, len(texts), 100):
                chunk = texts[start : start + 100]
                got = embed(chunk)
                if len(got) != len(chunk):
                    raise RuntimeError(
                        f"{self.model} returned {len(got)} embeddings for {len(chunk)} inputs"
                    )
                out.extend(got)
            return _unit(np.asarray(out))

        with ThreadPoolExecutor(max_workers=4) as pool:
            singles = list(pool.map(lambda t: embed([t])[0], texts))
        return _unit(np.asarray(singles))


@dataclass
class CohereEncoder:
    model: str = "embed-v4.0"
    name: str = ""
    note: str = "input_type search_document / search_query"
    params: str = "undisclosed"

    def __post_init__(self) -> None:
        self.name = self.name or f"cohere/{self.model}"

    def encode(self, texts: list[str], kind: str) -> np.ndarray:
        import cohere

        client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
        input_type = "search_query" if kind == "query" else "search_document"
        out: list[list[float]] = []
        for start in range(0, len(texts), 96):
            chunk = texts[start : start + 96]
            response = client.embed(
                texts=chunk,
                model=self.model,
                input_type=input_type,
                embedding_types=["float"],
            )
            out.extend(response.embeddings.float_)
        return _unit(np.asarray(out))


# --- bi-encoders, local ------------------------------------------------------


@dataclass
class LocalEncoder:
    """sentence-transformers on CPU.

    `trust_remote_code` executes code downloaded from the Hub. It is off unless
    a model genuinely needs it, and the report names every arm that did.
    """

    model: str
    query_prefix: str = ""
    doc_prefix: str = ""
    prompt_name: str | None = None
    trust_remote_code: bool = False
    params: str = ""
    name: str = ""
    note: str = ""
    _loaded: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.name = self.name or self.model
        if not self.note:
            prefixes = f"q={self.query_prefix!r} d={self.doc_prefix!r}"
            self.note = self.prompt_name and f"prompt_name={self.prompt_name}" or prefixes

    def _model(self) -> Any:
        if self._loaded is None:
            from sentence_transformers import SentenceTransformer

            self._loaded = SentenceTransformer(
                self.model, trust_remote_code=self.trust_remote_code, device="cpu"
            )
        return self._loaded

    def encode(self, texts: list[str], kind: str) -> np.ndarray:
        model = self._model()
        if self.prompt_name:
            name = "query" if kind == "query" else "document"
            return _unit(
                model.encode(texts, prompt_name=name, batch_size=BATCH, show_progress_bar=False)
            )
        prefix = self.query_prefix if kind == "query" else self.doc_prefix
        prepared = [prefix + t for t in texts] if prefix else texts
        return _unit(model.encode(prepared, batch_size=BATCH, show_progress_bar=False))


# --- rerankers ---------------------------------------------------------------


@dataclass
class _Fallible:
    """Failure bookkeeping shared by every reranker.

    A reranker that errors used to return the candidates unchanged, which scores
    exactly like a reranker that ran and had no opinion. That is how a dead
    `gemini-2.0-flash` arm posted 42% — precisely the baseline top-1 rate — and
    read as a mediocre result instead of a 404. Failures are now counted and the
    sweep refuses to report an arm that had any.
    """

    failures: int = field(default=0, init=False)
    last_error: str = field(default="", init=False)

    def _failed(self, error: Exception, width: int) -> list[int]:
        self.failures += 1
        self.last_error = f"{type(error).__name__}: {error}"
        return list(range(width))


RERANK_PROMPT = (
    "Rank the ACS tables by how well each answers the question.\n\n"
    "Match the UNIVERSE — households, families, population and housing units are "
    "different denominators and picking the wrong one is the most common error in "
    "Census work. Prefer the table whose subject IS the question over one that "
    "crosses that subject with another variable.\n\n"
    'Return JSON: {"order": ["Bxxxxx", "Bxxxxx", ...]} — every candidate, best first.'
)


def _parse_order(payload: str, candidates: list[str]) -> list[int]:
    """Model output -> candidate indices. Unlisted candidates keep their order."""
    import json

    try:
        named = [str(t) for t in json.loads(payload).get("order", [])]
    except ValueError:
        return list(range(len(candidates)))
    position = {table: i for i, table in enumerate(candidates)}
    order = [position[t] for t in named if t in position]
    return order + [i for i in range(len(candidates)) if i not in set(order)]


@dataclass
class LLMReranker(_Fallible):
    model: str = "gpt-4o-mini"
    name: str = ""
    note: str = "generative, reads titles + universes"

    def __post_init__(self) -> None:
        self.name = self.name or f"llm/{self.model}"

    def rank(self, question: str, candidates: list[str]) -> list[int]:
        from openai import OpenAI

        ids = [c.split(":", 1)[0].strip() for c in candidates]
        listing = "\n".join(candidates)
        try:
            response = OpenAI().chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": RERANK_PROMPT},
                    {"role": "user", "content": f"Question: {question}\n\nCandidates:\n{listing}"},
                ],
            )
            return _parse_order(response.choices[0].message.content or "{}", ids)
        except Exception as error:  # noqa: BLE001
            return self._failed(error, len(candidates))


@dataclass
class GeminiReranker(_Fallible):
    model: str = "gemini-3.7-flash"
    name: str = ""
    note: str = "generative, reads titles + universes"

    def __post_init__(self) -> None:
        self.name = self.name or f"llm/{self.model}"

    def rank(self, question: str, candidates: list[str]) -> list[int]:
        from google import genai
        from google.genai import types

        ids = [c.split(":", 1)[0].strip() for c in candidates]
        listing = "\n".join(candidates)
        try:
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            response = client.models.generate_content(
                model=self.model,
                contents=f"{RERANK_PROMPT}\n\nQuestion: {question}\n\nCandidates:\n{listing}",
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            return _parse_order(response.text or "{}", ids)
        except Exception as error:  # noqa: BLE001
            return self._failed(error, len(candidates))


@dataclass
class CohereReranker(_Fallible):
    model: str = "rerank-v3.5"
    name: str = ""
    note: str = "purpose-built cross-encoder, hosted"

    def __post_init__(self) -> None:
        self.name = self.name or f"cohere/{self.model}"

    def rank(self, question: str, candidates: list[str]) -> list[int]:
        import cohere

        try:
            client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
            response = client.rerank(model=self.model, query=question, documents=candidates)
            return [r.index for r in response.results]
        except Exception as error:  # noqa: BLE001
            return self._failed(error, len(candidates))


@dataclass
class CrossEncoderReranker(_Fallible):
    model: str
    name: str = ""
    note: str = "cross-encoder, local CPU"
    trust_remote_code: bool = False
    _loaded: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.name = self.name or self.model

    def rank(self, question: str, candidates: list[str]) -> list[int]:
        from sentence_transformers import CrossEncoder

        if self._loaded is None:
            self._loaded = CrossEncoder(
                self.model, trust_remote_code=self.trust_remote_code, device="cpu"
            )
        scores = self._loaded.predict([(question, c) for c in candidates])
        return [int(i) for i in np.argsort(-np.asarray(scores))]


# --- the registry ------------------------------------------------------------


def encoders() -> dict[str, Encoder]:
    """Every bi-encoder arm. Keys are CLI names."""
    return {
        "openai-3-large": OpenAIEncoder("text-embedding-3-large"),
        "openai-3-small": OpenAIEncoder("text-embedding-3-small"),
        "gemini-001": GeminiEncoder("gemini-embedding-001"),
        "gemini-2": GeminiEncoder("gemini-embedding-2"),
        "cohere-v4": CohereEncoder(),
        "embeddinggemma": LocalEncoder(
            "google/embeddinggemma-300m", prompt_name="query", params="300M"
        ),
        "bge-large": LocalEncoder(
            "BAAI/bge-large-en-v1.5",
            query_prefix="Represent this sentence for searching relevant passages: ",
            params="335M",
        ),
        "e5-large": LocalEncoder(
            "intfloat/e5-large-v2", query_prefix="query: ", doc_prefix="passage: ", params="335M"
        ),
        "bge-m3": LocalEncoder("BAAI/bge-m3", params="568M"),
        "nomic": LocalEncoder(
            "nomic-ai/nomic-embed-text-v1.5",
            query_prefix="search_query: ",
            doc_prefix="search_document: ",
            trust_remote_code=True,
            params="137M",
        ),
        "mxbai": LocalEncoder(
            "mixedbread-ai/mxbai-embed-large-v1",
            query_prefix="Represent this sentence for searching relevant passages: ",
            params="335M",
        ),
    }


def rerankers() -> dict[str, Reranker]:
    return {
        "gpt-4o-mini": LLMReranker("gpt-4o-mini"),
        "gemini-flash": GeminiReranker(),
        "cohere-rerank": CohereReranker(),
        "bge-reranker": CrossEncoderReranker("BAAI/bge-reranker-v2-m3"),
        "mxbai-rerank": CrossEncoderReranker("mixedbread-ai/mxbai-rerank-base-v1"),
    }


def timed(fn: Any, *args: Any, **kwargs: Any) -> tuple[Any, float]:
    start = time.perf_counter()
    return fn(*args, **kwargs), time.perf_counter() - start
