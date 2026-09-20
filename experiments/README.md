# The retrieval experiments

A record of what we tried, what it cost, what it proved, and how to run any of
it again. Three documents carry the whole thing:

| | |
|---|---|
| **README.md** *(this file)* | what we did and what each file is for |
| **PROTOCOL.md** | the method and the decision rule, **written before any arm ran** |
| **FINDINGS.md** | the results, with confidence intervals |

Read PROTOCOL first if you want to know whether to believe the numbers. The
point of writing it in advance is that "which model won" cannot then be decided
by looking at the table afterwards.

## Why this directory exists at all

The product needs to find the right American Community Survey table from a
question typed by someone who does not know the table exists. Slice 0 shipped a
first attempt and scored `retrieval@1 = 0.45` against a floor of `0.70`. The
obvious explanation was "the embedding model is not good enough."

This directory exists to test that explanation properly instead of swapping
models until a number moved. It turned out to be wrong twice over: the model
barely mattered, and part of the gap was a broken benchmark rather than broken
ranking.

**It is throwaway and deliberately quarantined.** Nothing here imports from a
shipped path in a way that could change behaviour, it writes only to
`experiments/results/` and `experiments/cache/`, and it never touches
`budgets.toml`, `evidence/latest.json` or `api/src/`. Delete the whole directory
and the product is unchanged. `torch` alone is ~2 GB, which is why the
dependencies live in their own group and not in `api/pyproject.toml`.

---

## What we ran, in order

Five axes. Each one is a separate question, and the protocol insists on varying
**one at a time** — document changes were deliberately held back until after the
model comparison, because they would otherwise confound it.

### Axis A — does the encoder matter?

Fourteen bi-encoders defined, **eleven scored**: hosted (OpenAI, Gemini, Cohere,
Voyage) and local (BGE, E5, MXBAI, EmbeddingGemma, BGE-M3). The two 8B arms were
measured infeasible rather than scored — see *Hardware limits* — and `nomic` was
added late and not run. Ranked by `recall@10` on 600 questions, because in this
architecture the agent picks from a candidate list, so a first-stage retriever's
job is to *contain* the answer, not to order it.

**Result: 92.3% for the best, 66.8% for the worst — and the top two are not
separable.** `gemini-embedding-001` and `voyage-4-large` differ by +0.3 points
with a CI of [−1.8, +2.7]. Voyage produces a 3.1 MB index against 9.3 MB.

Two things worth carrying: **the general leaderboard did not transfer** — BGE-M3,
the common production default, came *last of eleven* — and **newer is not
better**: `gemini-embedding-001` beat its own successor on every metric.

### Axis B — can a reranker fix the ordering?

Five rerankers over a **frozen** candidate list (the top 10 from the incumbent
encoder, identical for every arm) so they are compared to each other rather than
to whatever retriever they came paired with.

**Result: only generative models help.** `gemini-3.7-flash` took `@1` from 42.5%
to 77.5%. **Every purpose-built cross-encoder scored *below* not reranking at
all.** They are trained on (query, natural-language passage) pairs; our documents
are twelve-word structured records with no passage to score, and the
discriminating fact is semantic — households are not families.

This reversed the recommendation made before running anything.

### Axis C — would a richer document help?

Three variants, every field *derived* from variable labels and never authored:
`rich` (everything derivable), `lean` (only what discriminates), and later
`twin` (a tie-break added only to documents that collide). Tested on both the
reranker path and the embedding path, because a reranker reasons and an embedder
cannot.

**Result: four enrichments tested, four neutral or harmful.** The rule that
survives all four:

> A field earns its place only if it **discriminates between sibling tables** —
> and even then, only outside the embedded text.

Describing the topic makes every sibling *more* similar. The fourth variant
sharpened it: cell count separates the colliding twins perfectly, and adding it
*only* where a twin exists still made things significantly worse. Discriminating
for a human reader is not the same as discriminating for a vector.

### Axis D — is low confidence detectable?

The product may never ask a blocking clarification question — this audience often
cannot answer one. So when two tables are similar and the question is vague, the
agent has to *show both*. That only works if it can tell a confident hit from a
coin flip.

**Result: the gap between the top two scores predicts correctness at AUC
0.73–0.77.** Usable, not strong. A cut at the 70th percentile covers 30% of
questions where the top hit is right 92% of the time; below the median it is
right 46% of the time. That is exactly the split the product needs.

Caveat: the absolute margins are tiny — a 50th-percentile cut sits at 0.0057
cosine — so the threshold is per-encoder and must be recalibrated if the encoder
changes.

### Axis E — what is left in the table ID?

The ID is structured: type prefix, two-digit subject, three-digit number,
optional race-iteration letter, optional `PR`. Two of those fields already did
more for retrieval than any model. This asked about the other two.

**Result: one more document drop, and a benchmark bug.** A `C` table is its `B`
counterpart with categories collapsed and publishes the same title, universe and
concept — so 120 of 756 documents were **byte-identical** to another document.
Splitting the improvement by whether the question's answer was one of them:

```
answer was a twin    n= 97   @1   0.0% → 47.4%
answer untouched     n=503   @1  51.3% → 51.5%
```

Those 97 questions could never have been answered — identical text, identical
vector, no ranker could put one above the other. They were being scored as
ranking failures. **`@1` was never 43%; it was 51% on the questions that were
answerable.** The fold shipped into `build.py`; the 2-digit subject code was also
tested as a confidence signal and measured *below* chance.

### What actually moved the number

Not models and not metadata. **Corpus structure** — and every step of it was read
off the table ID:

```
1,458 documents  →  636
  −588  race iterations and PR variants, folded into their parent
  −115  B00/B98/B99 survey-quality tables, dropped
  −120  C tables identical to their B, folded
```

Larger than every model difference measured here, combined.

---

## The files

### The three documents

- **`PROTOCOL.md`** — the pre-registered method: why the 600-question set is
  primary, why comparisons are paired, the decision rule for each axis, the
  fairness constraints, and what the sweep deliberately does not test. Written
  before any arm ran and not edited since.
- **`FINDINGS.md`** — results per axis with paired-bootstrap CIs, plus a
  **Limits** section that is not optional reading. The single "significant"
  golden-set result is also the one most likely to be a false positive.
- **`README.md`** — this file.

### The machinery

- **`harness.py`** — the shared spine. Builds the corpus (identically for every
  arm, regenerated from metadata rather than read out of a built index, so no arm
  can inherit a corpus another arm did not see), loads the two query sets, caches
  embeddings, and computes `metrics()` and `paired_delta()`. New writes pin
  `corpus_n` / `corpus_hash`; `result_corpus_status()` is what `table` uses to
  surface a missing, mixed, or live-mismatched hash. If you only read one file,
  read this one: everything else depends on its guarantees.

- **`arms.py`** — one class per model, behind two tiny `Encoder` / `Reranker`
  protocols. This is where each provider's quirks are absorbed: instruction
  prefixes, batching limits, rate limits, and the `_Fallible` mixin that **counts
  failures so a dead arm is excluded rather than ranked**. Adding a model is one
  entry here and nothing else.

- **`describe.py`** — derives facts about a table from its variable labels:
  statistic type, breakdown dimensions, cell counts. **Never authored by hand.**
  Asked to describe `B19131` a person writes "earnings of two-parent families";
  the table's own labels include *"Other family, Female householder, no spouse
  present."* A wrong fact in the index is the exact failure this product exists
  to prevent. This file is the material for Axis C, and it is the file whose
  output kept losing.

### The runners

- **`run_sweep.py`** — Axes A, B and C. Three stages: `encoders`, `rerankers`,
  and `table` (the comparison with CIs, computed from results already on disk).
- **`run_margin.py`** — Axis D. Does the top1−top2 gap predict correctness?
- **`run_codes.py`** — Axis E. The B/C prefix and the subject code. Note that it
  rebuilds the **pre-fold 756-table corpus from metadata**, because the fold it
  measures has since shipped; reading the current index would leave nothing to
  compare and report a clean zero.

### The data

- **`results/*.json`** — per-question ranks for every arm, one file per arm *and
  variant*: `encoder-gemini-001.json`, `encoder-gemini-001-lean.json`,
  `encoder-gemini-001-sampled40.json`. Separate filenames are the mechanism that
  stops a screening run or an A/B being ranked beside a full one. Committed, so
  the numbers in FINDINGS are auditable without re-running anything. Every file
  records `corpus_n` and `corpus_hash`. Full arms are the pre-fold 756-document
  corpus; the `sampled40` screening run is already post-fold 636. `table`
  fails on a missing or mixed hash and warns when the live corpus differs —
  do not overwrite the published files to silence that warning.
- **`cache/*.npy`** — embedding matrices keyed on `(model, hash of the exact text
  list)`. Gitignored, large, regenerable. This is why a re-run is free — and why
  a breakpoint inside an encoder often never fires.

---

## Running it yourself

```powershell
uv sync --group experiments          # torch, sentence-transformers, cohere, google-genai, voyageai (~2 GB)
make metadata                        # fetch ACS metadata into data/raw/; harness rebuilds the corpus from that cache
```

Keys come from `.env`. An arm whose key is missing fails loudly and the rest of
the sweep continues.

| key | unlocks |
|---|---|
| `OPENAI_API_KEY` | `openai-3-large`, `openai-3-small`, `gpt-4o-mini` reranker |
| `GEMINI_API_KEY` | `gemini-001`, `gemini-2`, `gemini-flash` reranker |
| `COHERE_API_KEY` | `cohere-v4`, `cohere-rerank` |
| `VOYAGE_API_KEY` | `voyage-4-large` |
| `HUGGINGFACE_API_KEY` | gated repos: `embeddinggemma`, `ingot-8b` |

The HF token is normalized into `HF_TOKEN` at startup, so `HUGGINGFACE_API_KEY`,
`HUGGINFACE_API_KEY` (the misspelling) and `HUGGING_FACE_HUB_TOKEN` all work.

```powershell
# Axis A — which encoder finds the table. Ranked by recall@10 on 600 questions.
uv run --group experiments python experiments/run_sweep.py encoders
uv run --group experiments python experiments/run_sweep.py encoders --only gemini-001,voyage-4-large

# Axis B — which reranker picks from the top 10, over a frozen candidate list.
uv run --group experiments python experiments/run_sweep.py rerankers

# Axis C — what the DOCUMENT says. An A/B on metadata design, not on models.
uv run --group experiments python experiments/run_sweep.py encoders  --rich lean
uv run --group experiments python experiments/run_sweep.py rerankers --rich rich

# Axis D and E — standalone. Both read cached embeddings and cost nothing.
uv run --group experiments python experiments/run_margin.py --encoder gemini-001
uv run --group experiments python experiments/run_codes.py  --encoder gemini-001

# The comparison table, with paired bootstrap CIs. No network.
uv run --group experiments python experiments/run_sweep.py table
```

`--sample N` screens on N self-retrieval questions instead of 600, for arms too
expensive to run in full:

```powershell
uv run --group experiments python experiments/run_sweep.py encoders --only nemotron-8b --sample 150
```

**Debugging:** `.vscode/launch.json` has a config per runner, pinned to this
repo's `.venv` with `justMyCode: false`. Start from *"sweep: one encoder,
sampled"*. The two free configs — *"sweep: comparison table"* and *"index: build,
no embeddings"* — need no network and are the ones to reach for first.

### Arm names

Bi-encoders: `openai-3-large` (the baseline everything is paired against),
`openai-3-small`, `gemini-001`, `gemini-2`, `cohere-v4`, `voyage-4-large`,
`embeddinggemma`, `bge-large`, `e5-large`, `bge-m3`, `mxbai`, `nomic`,
`nemotron-8b`, `ingot-8b`.

Rerankers: `gpt-4o-mini`, `gemini-flash`, `cohere-rerank`, `bge-reranker`,
`mxbai-rerank`. Definitive list: the keys of `encoders()` and `rerankers()`.

### Adding a model

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

### Changing what a document says

`describe.py` derives facts from variable labels — never authored by hand. Four
variants exist and all four lost or drew:

- `listing()` / `document()` — everything derived. Measured *worse*.
- `lean_listing()` / `lean_document()` — statistic type only where it separates.
- `twin_aware_documents()` — a tie-break only where two documents collide.

---

## Reading the output

`@10` decides the encoder axis, `@1` decides the reranker axis, and `*` marks a
paired-bootstrap CI that excludes zero. An unmarked difference **is not a
difference**: at n=40 the golden set cannot resolve anything smaller than about
five questions, which is why the 600-question self-retrieval set is primary.

The Spearman ρ at the foot of the table says whether the two query sets agree on
ordering. If it falls, the self-retrieval set has stopped proxying the real thing
and is measuring `gpt-4o-mini`'s phrasing instead. It fell from +0.82 to +0.73
when Voyage joined — that drop is itself a finding.

**One caveat the protocol did not pre-register:** dozens of paired tests have now
been run with no multiple-comparison correction. A single result whose CI barely
excludes zero is the one most likely to be a false positive — and it is usually
the one that would otherwise pick a winner.

## Hardware limits

CPU-only, 12 cores, 34 GB RAM. 335M-parameter models embed at 150–240 ms/text, so
the corpus plus queries takes 2–15 minutes.

The 8B class was **measured infeasible, not scored.** `Nemotron-3-Embed-8B` loads
correctly then embeds at **18.7 s/text**, about 4× worse than scaling linearly
from the 335M models, because CPU bf16 kernels upcast. The cost is not the reason
to stop: 18.7 s is also the *query* embedding cost, against a 20-second budget
for a whole answer. An 8B local encoder cannot ship here whatever it scores, so
measuring it would inform nothing.

## Things that bit us, so they will bite you

- **The cache means your breakpoints will not fire.** `cached_encode` returns
  before touching a model on a hit. To exercise an encoder, delete its one
  `.npy` — not the directory, or you pay for a full re-embed.
- **A reranker that errors returns the candidate list unchanged**, which scores
  identically to one that ran and had no opinion. A retired `gemini-2.0-flash`
  scored 42% — exactly the baseline top-1 rate — and read as a mediocre model
  rather than a 404. Arms count failures now and any arm with one is *excluded*
  from the table rather than ranked in it.
- **`gemini-embedding-2` accepts 100 texts and returns one embedding**, with no
  error. Responses are length-checked; short ones fall back to per-text calls.
- **The cache validated its inputs but not its outputs.** A truncated 8-vector
  matrix got cached and survived a re-run, because the key is a hash of the input
  texts and those had not changed. Row counts are checked both ways now. If an
  arm behaves impossibly, look in `experiments/cache/` first.
- **Embeddings are not bit-deterministic.** `text-embedding-3-large` returns
  different vectors for the *same string* at different batch positions — up to
  1.3e-3 per component, ≈6e-4 of cosine, which is the size of a real margin here.
  Exact ties do not stay tied between builds.
- **Voyage's free tier is 3 requests/min** without a payment method. The encoder
  paces itself and retries; a full corpus takes about 11 minutes.
- **Gemini model names retire.** `client.models.list()` finds what is current.
- **Gated repos 401 in a way that reads like a missing model.** That is a token
  problem, not a name problem.
