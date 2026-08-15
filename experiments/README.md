# Running the sweep yourself

Methodology and the pre-registered decision rule are in `PROTOCOL.md`. This is
the operating manual. Findings are in `FINDINGS.md`.

Nothing here writes to `budgets.toml`, `evidence/latest.json`, or `api/src/`.
Delete the whole `experiments/` directory and the product is unchanged.

## Setup, once

```powershell
uv sync --group experiments     # torch, sentence-transformers, cohere, google-genai, voyageai (~2 GB)
uv run python scripts/build_index.py    # the sweep reads its corpus from the built index
```

Keys are read from `.env`. An arm whose key is missing fails loudly and the rest
of the sweep continues.

| key | unlocks |
|---|---|
| `OPENAI_API_KEY` | `openai-3-large`, `openai-3-small`, `gpt-4o-mini` reranker |
| `GEMINI_API_KEY` | `gemini-001`, `gemini-2`, `gemini-flash` reranker |
| `COHERE_API_KEY` | `cohere-v4`, `cohere-rerank` |
| `VOYAGE_API_KEY` | `voyage-4-large` |
| `HUGGINGFACE_API_KEY` | gated repos: `embeddinggemma`, `ingot-8b` |

The HF token is normalized into `HF_TOKEN` at startup, so `HUGGINGFACE_API_KEY`,
`HUGGINFACE_API_KEY` (the misspelling) and `HUGGING_FACE_HUB_TOKEN` all work.

## The three things you can vary

Each is a separate axis. **Vary one at a time** — the protocol defers document
changes until after the model comparison precisely so they do not confound.

```powershell
# 1. Which encoder finds the table.  Ranked by recall@10 on 600 questions.
uv run --group experiments python experiments/run_sweep.py encoders
uv run --group experiments python experiments/run_sweep.py encoders --only gemini-001,voyage-4-large

# 2. Which reranker picks from the top 10.  Frozen candidate list, so rerankers
#    are compared to each other rather than to their retriever.
uv run --group experiments python experiments/run_sweep.py rerankers

# 3. What the DOCUMENT says.  An A/B on metadata design, not on models.
uv run --group experiments python experiments/run_sweep.py encoders  --rich lean
uv run --group experiments python experiments/run_sweep.py rerankers --rich rich

# The comparison table, with paired bootstrap CIs.
uv run --group experiments python experiments/run_sweep.py table
```

Two standalone questions have their own scripts. Both read cached embeddings,
so they cost nothing once an encoder has been run:

```powershell
# Does the top1-top2 gap predict whether top-1 is right? (Axis D)
uv run --group experiments python experiments/run_margin.py --encoder gemini-001

# What is left in the table ID: B/C prefix and subject code. (Axis E)
uv run --group experiments python experiments/run_codes.py --encoder gemini-001
```

`run_codes.py` rebuilds the pre-fold 756-table corpus from metadata rather than
reading the built index, because the fold it measures has since shipped. Reading
the index would leave nothing to compare and it would report a clean zero.

`--sample N` screens on N self-retrieval questions instead of 600, for arms too
expensive to run in full:

```powershell
uv run --group experiments python experiments/run_sweep.py encoders --only nemotron-8b --sample 150
```

Every variant writes to its own results file — `encoder-gemini-001-lean.json`,
`encoder-nemotron-8b-sampled150.json` — so a screening or A/B run can never
overwrite or be ranked beside a full one.

## Arm names

Bi-encoders: `openai-3-large` (the baseline everything is paired against),
`openai-3-small`, `gemini-001`, `gemini-2`, `cohere-v4`, `voyage-4-large`,
`embeddinggemma`, `bge-large`, `e5-large`, `bge-m3`, `mxbai`, `nomic`,
`nemotron-8b`, `ingot-8b`.

Rerankers: `gpt-4o-mini`, `gemini-flash`, `cohere-rerank`, `bge-reranker`,
`mxbai-rerank`.

Definitive list: the keys of `encoders()` and `rerankers()` in `arms.py`.

## Adding a model

One entry in `arms.py`. A local sentence-transformers model is a single line:

```python
"my-model": LocalEncoder(
    "org/model-name",
    query_prefix="query: ",      # whatever THIS model was trained with
    doc_prefix="passage: ",
    params="335M",
    dtype="bfloat16",            # halves resident memory; needed above ~1B params
),
```

**Get the prefixes right or the result is meaningless.** E5 wants
`query:`/`passage:`, BGE wants a query instruction and no document prefix, Nomic
wants `search_query:`/`search_document:`. A model run with the wrong prefix loses
several points and looks like a worse model rather than a misconfigured one.
Check the model card. For a hosted provider, copy `CohereEncoder` — 15 lines.

## Changing what a document says

`describe.py` derives facts from variable labels — **never authored by hand.**
Asked to describe `B19131`, a person writes "earnings of two-parent families";
the table's own labels include "Other family, Female householder, no spouse
present." It is not two-parent, and a wrong fact in the index is the failure
this product exists to prevent.

There are four variants, and the rule that decides between them is: **a field
earns its place only if it DISCRIMINATES between sibling tables.** Text that
describes the topic makes every sibling more similar, which is why synthetic
questions were slice 0's largest regression.

- `listing()` / `document()` — everything derived. Measured *worse*.
- `lean_listing()` / `lean_document()` — statistic type only where it separates.

## Hardware limits

CPU-only, 12 cores, 34 GB RAM. Measured throughput: 335M-parameter models embed
at 150–240 ms/text, so the 756-document corpus plus 640 queries takes 2–15
minutes. The 8B class needs ~16 GB resident and 1.4–2.7 hours per arm, must run
alone, and downloads ~16 GB of weights each. The top of both MTEB and RTEB is
7B+ and effectively out of reach here.

## Things that bit us, so they will bite you

- **A reranker that errors returns the candidate list unchanged**, which scores
  identically to one that ran and had no opinion. A retired `gemini-2.0-flash`
  scored 42% — exactly the baseline top-1 rate — and read as a mediocre model
  rather than a 404. Arms count failures now and any arm with one is *excluded*
  from the table rather than ranked in it.
- **`gemini-embedding-2` accepts 100 texts and returns one embedding**, with no
  error. Responses are length-checked; short ones fall back to per-text calls.
- **The cache validated its inputs but not its outputs.** That truncated
  8-vector matrix got cached and survived a re-run, because the key is a hash of
  the input texts and those had not changed. Row counts are checked both ways
  now. If an arm behaves impossibly, look in `experiments/cache/` first.
- **Voyage's free tier is 3 requests/min** without a payment method. The encoder
  paces itself and retries; a full corpus takes about 11 minutes.
- **Gemini model names retire.** `client.models.list()` finds what is current.
- **Gated repos 401 in a way that reads like a missing model.** That is a token
  problem, not a name problem.

## Reading the output

`@10` decides the encoder axis, `@1` decides the reranker axis, and `*` marks a
paired-bootstrap CI that excludes zero. An unmarked difference is not a
difference: at n=40 the golden set cannot resolve anything smaller than about
five questions, which is why the 600-question self-retrieval set is primary.

The Spearman rho at the foot of the table says whether the two query sets agree
on the ordering. If it falls, the self-retrieval set has stopped proxying the
real thing and is measuring `gpt-4o-mini`'s phrasing instead.

**One caveat the protocol did not pre-register:** dozens of paired tests have now
been run with no multiple-comparison correction. A single result whose CI barely
excludes zero is the one most likely to be a false positive — and it is usually
the one that would otherwise pick a winner.
