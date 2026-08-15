# Running the sweep yourself

Methodology and the pre-registered decision rule are in `PROTOCOL.md`. This is
the operating manual.

Nothing here writes to `budgets.toml`, `evidence/latest.json`, or `api/src/`.
Delete the whole `experiments/` directory and the product is unchanged.

## Setup, once

```powershell
uv sync --group experiments        # torch + sentence-transformers + cohere + google-genai, ~2 GB
```

Keys come from `.env`: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `COHERE_API_KEY`.
An arm whose key is missing fails loudly and the rest of the sweep continues.

The index must exist, because the sweep takes the corpus from it:

```powershell
uv run python scripts/build_index.py
```

## Running

```powershell
# Axis A - bi-encoders. Everything, or a subset.
uv run --group experiments python experiments/run_sweep.py encoders
uv run --group experiments python experiments/run_sweep.py encoders --only gemini-001,bge-large

# Axis B - rerankers, over a frozen candidate list from the baseline encoder.
uv run --group experiments python experiments/run_sweep.py rerankers

# The comparison table, with paired bootstrap CIs.
uv run --group experiments python experiments/run_sweep.py table
```

Arm names are the keys of `encoders()` and `rerankers()` in `arms.py`.

**Re-runs are free.** Every embedding is cached in `experiments/cache/` on
`(model, kind, hash of the exact text list)`, so `table` and repeated scoring
cost nothing. The API arms only spend on the first run.

## Adding a model

One entry in `arms.py`. A local sentence-transformers model is a single line:

```python
"my-model": LocalEncoder(
    "org/model-name",
    query_prefix="query: ",      # whatever THIS model was trained with
    doc_prefix="passage: ",
    params="335M",
),
```

**Get the prefixes right or the result is meaningless.** E5 wants
`query:`/`passage:`, BGE wants a query instruction and no document prefix,
Nomic wants `search_query:`/`search_document:`. A model run with the wrong
prefix loses several points and looks like a worse model rather than a
misconfigured one. Check the model card.

For a hosted provider, copy `CohereEncoder` — it is 15 lines.

## Things that bit us, so they will bite you

- **A reranker that errors returns the candidate list unchanged**, which scores
  identically to one that ran and had no opinion. A retired `gemini-2.0-flash`
  scored 42% — exactly the baseline top-1 rate — and read as a mediocre model
  instead of a 404. Arms now count failures and any arm with one is *excluded*
  from the table rather than ranked in it. If you add a provider, make its
  failures visible the same way.
- **`gemini-embedding-2` accepts 100 texts and returns one embedding**, no
  error, no warning. Responses are length-checked and short ones fall back to
  per-text calls.
- **The cache validated its inputs but not its outputs.** That truncated
  8-vector matrix got cached and then survived a re-run, because the key is a
  hash of the input texts and those had not changed. Row counts are now checked
  on write *and* on read. If an arm behaves impossibly, look in
  `experiments/cache/` before you believe it.
- **Gemini model names retire.** `models.list()` is the fastest way to find what
  is current.

## Reading the output

`@10` decides Axis A, `@1` decides Axis B, and the `*` marks a paired-bootstrap
CI that excludes zero. An unmarked difference is not a difference — at n=40 the
golden set alone cannot resolve anything smaller than about 5 questions, which
is why the 600-question self-retrieval set is the primary discriminator.

The Spearman rho at the bottom of the table says whether the two query sets
agree on the ordering. If it drops, the self-retrieval set has stopped being a
proxy for the real thing and is measuring `gpt-4o-mini`'s phrasing instead.
