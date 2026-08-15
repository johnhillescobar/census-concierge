"""OpenAI embeddings, batched and L2-normalized so cosine is a dot product.

`openai` is imported inside the functions, not at module scope. `index.py`
imports this module to embed a query, and the loader must stay importable in a
container that has no OpenAI client and no key — which is every container, since
the index is built offline and shipped as a pinned artifact.

No caching: ~1,300 documents is one batched call and a fraction of a cent, and a
cache keyed on text is a thing to invalidate wrongly. The expensive generation
step is `synthetic.py`, and that one does cache.
"""

from __future__ import annotations

import numpy as np

# Measured 2026-08-14, not assumed: `3-large` beat `3-small` by 8 points @1 and
# 0.08 MRR on the tuning set. At 636 documents the cost difference is under a
# cent to build, and this must stay the default or `make index` silently
# produces an index that scores lower than the recorded evidence.
DEFAULT_MODEL = "text-embedding-3-large"

# The API is not bit-deterministic across batch positions: the same string
# embedded at index 0 and index 3 of one call came back differing by 1.3e-3 in
# its largest component (measured 2026-08-15), enough to move a cosine by 6e-4.
# Two documents with identical text therefore do NOT tie exactly, and whichever
# wins can flip between builds. `build.py` folds the identical `B`/`C` twins for
# that reason; do not assume rebuilding produces byte-identical vectors.
BATCH = 256


def embed_texts(texts: list[str], model: str = DEFAULT_MODEL) -> np.ndarray:
    """(n, dim) float32, unit rows."""
    from openai import OpenAI

    client = OpenAI()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH):
        chunk = texts[start : start + BATCH]
        response = client.embeddings.create(model=model, input=chunk)
        vectors.extend(item.embedding for item in response.data)

    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def embed_query(text: str, model: str = DEFAULT_MODEL) -> np.ndarray:
    vector: np.ndarray = embed_texts([text], model=model)[0]
    return vector
